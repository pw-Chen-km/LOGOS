"""Tests for EvoScientist full survey-agent integration."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logos2.adapters.evoscientist.evo_survey_agent import parse_survey_artifact
from logos2.adapters.evoscientist.paper_navigator_adapter import PaperCandidate
from logos2.config import LogosConfig
from logos2.nodes.iterative_discovery import IterativeDiscoveryResult
from logos2.schemas import PaperNavigatorReading, SurveyTaxonomy
from logos2.workflow.graph import LogosResearchWorkflow


def _taxonomy(request_id="req_test"):
    return SurveyTaxonomy(
        taxonomy_id="evo_tax_req_test",
        request_id=request_id,
        themes=[
            {
                "theme_id": "T1",
                "name": "GraphRAG Evaluation",
                "description": "Evaluation-focused GraphRAG papers",
                "keywords": ["graphrag", "evaluation"],
            }
        ],
        paper_assignments=[
            {
                "paper_id": "arxiv:2501.00001",
                "theme_id": "T1",
                "confidence": 0.95,
            }
        ],
        method_families=[
            {
                "family_id": "MF1",
                "name": "Graph retrieval",
                "description": "Graph-based retrieval methods",
                "representative_papers": ["arxiv:2501.00001"],
            }
        ],
    )


def test_parse_survey_artifact_maps_to_logos_schema(tmp_path):
    artifact = {
        "artifact_version": "logos-evo-survey-agent-v1",
        "papers": [
            {
                "paper_id": "arxiv:2501.00001",
                "title": "GraphRAG Evaluation",
                "authors": [{"name": "Alice"}],
                "year": 2025,
                "abstract": "A GraphRAG evaluation paper.",
                "tldr": "Evaluates GraphRAG.",
                "main_contribution": "A benchmark.",
                "problem_statement": "GraphRAG lacks evaluation.",
                "method_intuition": "Use graph retrieval benchmarks.",
                "rough_limitation": "Small scale.",
                "benchmark_names": ["HotpotQA"],
                "dataset_names": ["Wikipedia"],
                "baseline_names": ["BM25"],
                "pdf_url": "https://arxiv.org/pdf/2501.00001",
            }
        ],
        "taxonomy": _taxonomy().model_dump(),
        "survey_reports": {"en": "survey_report_en.md"},
    }
    artifact_path = tmp_path / "logos_survey_artifact.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    result = parse_survey_artifact(artifact_path, "req_test", tmp_path)

    assert result.paper_candidates[0].paper_id == "arxiv:2501.00001"
    assert result.metadata_map["arxiv:2501.00001"].authors == ["Alice"]
    assert result.readings[0].benchmark_names == ["HotpotQA"]
    assert result.survey_taxonomy is not None
    assert result.survey_taxonomy.themes[0].name == "GraphRAG Evaluation"
    assert result.report_paths["en"] == str(tmp_path / "survey_report_en.md")


class _FakeSurveyAgentDiscovery:
    def __init__(self):
        self.run_dir = None

    def run(self, request):
        candidate = PaperCandidate(
            paper_id="arxiv:2501.00001",
            title="GraphRAG Evaluation",
            year="2025",
            authors=["Alice"],
            abstract="A GraphRAG evaluation paper.",
        )
        reading = PaperNavigatorReading(
            paper_id="arxiv:2501.00001",
            reading_level="L2",
            title="GraphRAG Evaluation",
            tldr="Evaluates GraphRAG.",
            main_contribution="A benchmark.",
            problem_statement="GraphRAG lacks evaluation.",
            method_intuition="Use graph retrieval benchmarks.",
            rough_limitation="Small scale.",
            benchmark_names=["HotpotQA"],
            confidence=0.9,
        )
        return IterativeDiscoveryResult(
            paper_candidates=[candidate],
            metadata_map={candidate.paper_id: candidate.to_metadata()},
            readings=[reading],
            survey_taxonomy=_taxonomy(request.request_id),
            survey_report_paths={"en": str(Path("survey_report_en.md"))},
            evo_thread_id="thread123",
            trace={"mode": "SURVEY_AGENT", "taxonomy_source": "evoscientist_survey_agent"},
        )


def test_workflow_uses_survey_agent_taxonomy(tmp_path):
    config = LogosConfig.from_dict(
        {
            "paper_navigator": {"mode": "survey_agent"},
            "survey_agent": {"enabled": True, "fallback_to_direct": False},
            "runtime": {
                "runs_dir": str(tmp_path / "runs"),
                "artifacts_dir": str(tmp_path / "artifacts"),
                "paper_library_dir": str(tmp_path / "paper_library"),
                "paper_skills_dir": str(tmp_path / "paper_skills"),
            },
            "graph": {"backend": "sqlite", "sqlite_path": str(tmp_path / "graph.sqlite")},
        }
    )
    workflow = LogosResearchWorkflow(
        paper_skills_dir=str(tmp_path / "paper_skills"),
        artifacts_dir=str(tmp_path / "artifacts"),
        paper_library_dir=str(tmp_path / "paper_library"),
        config=config,
    )
    workflow.survey_agent_discovery = _FakeSurveyAgentDiscovery()

    try:
        state = workflow.run_research_pipeline(
            "Survey 1 papers about GraphRAG evaluation",
            request_id="req_test",
        )
    finally:
        workflow.close()

    assert state.workflow_complete is True
    assert state.taxonomy_source == "evoscientist_survey_agent"
    assert state.evo_thread_id == "thread123"
    assert state.survey_taxonomy["themes"][0]["name"] == "GraphRAG Evaluation"
    assert state.paper_profiles[0]["paper_id"] == "arxiv:2501.00001"
