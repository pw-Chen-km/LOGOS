"""Tests for direct paper-navigator filesystem integration."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logos2.config import LogosConfig
from logos2.adapters.evoscientist.paper_navigator_adapter import (
    DirectPaperNavigatorAdapter,
    PaperCandidate,
    PaperMetadata,
    _candidate_from_raw,
)
from logos2.runtime import IntentBridge
from logos2.nodes.iterative_discovery import IterativeDiscovery
from logos2.schemas import PaperNavigatorReading, ResearchRequest


def _make_fake_paper_navigator(path: Path) -> Path:
    scripts_dir = path / "scripts"
    scripts_dir.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        "---\nname: paper-navigator\n---\n# Paper Navigator\n",
        encoding="utf-8",
    )
    for script in ["scholar_search.py", "fetch_paper.py", "download_paper.py"]:
        (scripts_dir / script).write_text("print('[]')\n", encoding="utf-8")
    return path


def test_explicit_skill_dir_resolution(tmp_path):
    skill_dir = _make_fake_paper_navigator(tmp_path / "paper-navigator")
    config = LogosConfig.from_dict(
        {"paper_navigator": {"skill_dir": str(skill_dir)}}
    )

    assert config.resolve_paper_navigator_dir() == skill_dir.resolve()

    adapter = DirectPaperNavigatorAdapter(config=config)
    report = adapter.validate_installation()
    assert report.available is True
    assert report.skill_dir == str(skill_dir.resolve())


def test_missing_skill_has_shell_setup_hint(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOGOS_PAPER_NAVIGATOR_DIR", str(tmp_path / "missing"))
    config = LogosConfig.load()
    config.paper_navigator_candidate_dirs = lambda: [tmp_path / "missing"]

    adapter = DirectPaperNavigatorAdapter(config=config)
    report = adapter.validate_installation()

    assert report.available is False
    assert "setup-paper-navigator" in report.setup_hint
    assert "/install-skill EvoScientist/EvoSkills@skills/paper-navigator" in report.setup_hint


def test_load_batch_reading_artifact(tmp_path):
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    reading = {
        "paper_id": "arxiv:2401.12345",
        "reading_level": "L2",
        "title": "Test Paper",
        "tldr": "A test paper",
        "confidence": 0.8,
    }
    (artifact_dir / "paper_navigator_readings.json").write_text(
        json.dumps([reading]),
        encoding="utf-8",
    )

    adapter = DirectPaperNavigatorAdapter(artifact_dir=str(artifact_dir))
    readings = adapter.load_artifacts(str(artifact_dir))

    assert len(readings) == 1
    assert readings[0].paper_id == "arxiv:2401.12345"


def test_metadata_normalization_and_artifact_save(tmp_path):
    candidate = PaperCandidate(
        paper_id="arxiv:2401.12345",
        title="Metadata Title",
        year="2024",
        venue="SIGIR",
        authors=["Alice", "Bob"],
        tldr="Metadata TLDR",
        abstract="Metadata abstract",
        pdf_path="paper_library/arxiv_2401.12345/paper.pdf",
    )
    metadata = candidate.to_metadata()
    reading = metadata.to_paper_navigator_reading()

    adapter = DirectPaperNavigatorAdapter(paper_library_dir=str(tmp_path / "paper_library"))
    adapter.save_artifacts(
        tmp_path,
        candidates=[candidate],
        metadata_map={metadata.paper_id: metadata},
        readings=[reading],
        pdf_manifest=[],
    )
    artifacts = adapter.collect_run_artifacts(tmp_path)

    assert artifacts.paper_metadata["arxiv:2401.12345"]["title"] == "Metadata Title"
    assert artifacts.paper_navigator_readings[0].reading_level == "metadata_only"
    assert (tmp_path / "paper_navigator" / "paper_candidates.json").exists()


def test_intent_bridge_parses_confirmed_json():
    raw = {
        "request_id": "req_001",
        "raw_user_input": "GraphRAG survey",
        "research_goal": "Survey GraphRAG methods",
        "topic_keywords": ["GraphRAG", "retrieval"],
        "paper_count_target": 20,
    }
    result = IntentBridge().parse_response(json.dumps(raw))

    assert result.success is True
    assert result.request is not None
    assert result.request.request_id == "req_001"


def test_profile_normalizer_merges_paper_metadata(tmp_path):
    from logos2.nodes.profile_normalizer import ProfileNormalizer
    from logos2.schemas import PaperNavigatorReading, SurveyTaxonomy

    fixtures_dir = Path(__file__).parent / "fixtures"
    taxonomy = SurveyTaxonomy(
        **json.loads((fixtures_dir / "survey_taxonomy.json").read_text(encoding="utf-8"))
    )
    reading = PaperNavigatorReading(
        paper_id="arxiv:2401.12345",
        reading_level="metadata_only",
        title="Reading Title",
        tldr="Reading TLDR",
        confidence=0.3,
    )
    metadata = PaperMetadata(
        paper_id="arxiv:2401.12345",
        title="Metadata Title",
        year="2024",
        venue="SIGIR",
        authors=["Alice", "Bob"],
        pdf_path="paper_library/arxiv_2401.12345/paper.pdf",
    )

    profile = ProfileNormalizer(output_dir=str(tmp_path)).normalize(
        reading,
        taxonomy,
        metadata,
    )

    assert profile.title == "Metadata Title"
    assert profile.year == "2024"
    assert profile.venue == "SIGIR"
    assert profile.authors == ["Alice", "Bob"]
    assert profile.pdf_path == "paper_library/arxiv_2401.12345/paper.pdf"


def test_candidate_normalization_accepts_s2_author_dicts():
    candidate = _candidate_from_raw(
        {
            "paperId": "s2-001",
            "externalIds": {"ArXiv": "2501.00001"},
            "title": "Graph Retrieval-Augmented Generation",
            "authors": [{"name": "Alice"}, {"name": "Bob"}],
            "tldr": {"text": "A GraphRAG paper."},
            "citationCount": 12,
        }
    )

    assert candidate.paper_id == "s2-001"
    assert candidate.arxiv_id == "2501.00001"
    assert candidate.authors == ["Alice", "Bob"]
    assert candidate.tldr == "A GraphRAG paper."


class _FakeNavigator:
    def __init__(self):
        self.read_calls = []

    def search_local_library(self, query, limit=10):
        return []

    def run_keyword_search(self, query, limit):
        return [
            PaperCandidate(
                paper_id=f"arxiv:{query.replace(' ', '_')[:20]}",
                title=f"{query} paper",
                authors=["Alice"],
                abstract=f"{query} methods benchmark dataset",
                year="2025",
                citation_count=10,
            )
        ]

    def run_arxiv_monitor(self, keywords, days):
        return [
            PaperCandidate(
                paper_id="arxiv:monitor",
                title="Recent GraphRAG benchmark",
                abstract="GraphRAG benchmark dataset evaluation",
                year="2025",
            )
        ]

    def run_trending(self, query, period_days=180, limit=20):
        return [
            PaperCandidate(
                paper_id="arxiv:trending",
                title="Trending GraphRAG systems",
                abstract="GraphRAG systems applications",
                year="2025",
                citation_count=5,
            )
        ]

    def run_citation_traversal(self, seed_id, direction="co-citation", limit=15):
        return [
            PaperCandidate(
                paper_id=f"arxiv:{direction}",
                title=f"GraphRAG {direction}",
                abstract="GraphRAG related citation expansion",
                year="2024",
            )
        ]

    def run_recommendations(self, positive_ids, limit=15, negative_ids=None):
        return [
            PaperCandidate(
                paper_id="arxiv:recommend",
                title="Recommended GraphRAG method",
                abstract="GraphRAG recommended related work",
                year="2024",
            )
        ]

    def run_tavily_search(self, query, limit=5):
        return [{"title": "GraphRAG web overview", "url": "https://example.com"}]

    def read(self, paper_id, reading_level="L2", pdf_path=None):
        self.read_calls.append((paper_id, reading_level))
        return PaperNavigatorReading(
            paper_id=paper_id,
            reading_level=reading_level,
            title=paper_id,
            tldr="Deep read summary",
            main_contribution="Contribution",
            problem_statement="Problem",
            method_intuition="Method",
            rough_limitation="Limit",
            confidence=0.8,
        )


def test_iterative_discovery_runs_s1_to_s5(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    config = LogosConfig.from_dict({"paper_navigator": {"max_papers": 5}})
    navigator = _FakeNavigator()
    discovery = IterativeDiscovery(navigator, config=config)
    request = ResearchRequest(
        request_id="req_test",
        raw_user_input="Survey GraphRAG papers",
        research_goal="Survey GraphRAG papers",
        topic_keywords=["GraphRAG"],
        paper_count_target=5,
    )

    result = discovery.run(request)

    assert result.trace["mode"] == "ITERATIVE"
    assert result.trace["s1_decompose"]["queries"]
    assert len(result.paper_candidates) == 5
    assert len(result.readings) == 5
    assert result.web_findings
    assert navigator.read_calls
