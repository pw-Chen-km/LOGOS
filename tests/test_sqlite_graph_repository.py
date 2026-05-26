"""Tests for SQLite graph backend."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logos2.nodes.lightweight_graph_indexer import LightweightGraphIndexer
from logos2.nodes.profile_normalizer import ProfileNormalizer
from logos2.schemas import PaperNavigatorReading, SurveyTaxonomy
from logos2.storage import SQLiteGraphRepository


def _load_profiles(tmp_path):
    fixtures_dir = Path(__file__).parent / "fixtures"
    readings = [
        PaperNavigatorReading(**item)
        for item in json.loads(
            (fixtures_dir / "paper_navigator_reading.json").read_text(encoding="utf-8")
        )
    ]
    taxonomy = SurveyTaxonomy(
        **json.loads((fixtures_dir / "survey_taxonomy.json").read_text(encoding="utf-8"))
    )
    profiles = ProfileNormalizer(output_dir=str(tmp_path / "paper_skills")).normalize_batch(
        readings,
        taxonomy,
    )
    return taxonomy, profiles


def test_sqlite_graph_repository_indexes_and_searches(tmp_path):
    taxonomy, profiles = _load_profiles(tmp_path)
    repo = SQLiteGraphRepository(tmp_path / "graph.sqlite")
    indexer = LightweightGraphIndexer(repository=repo)

    result = indexer.run(taxonomy, profiles)

    assert result["success"] is True
    assert result["papers_indexed"] == 3
    assert repo.count_papers() == 3
    assert repo.count_relations() == 3

    theme_results = repo.search_papers_by_theme("Graph-Based Retrieval")
    assert {row["paper_id"] for row in theme_results} >= {
        "arxiv:2401.12345",
        "arxiv:2402.67890",
    }

    benchmark_results = repo.search_papers_by_benchmark("HotpotQA")
    assert {row["paper_id"] for row in benchmark_results} >= {
        "arxiv:2401.12345",
        "arxiv:2402.67890",
    }

    fulltext_results = repo.fulltext_search_papers("spectral graph retrieval")
    assert any(row["paper_id"] == "arxiv:2401.12345" for row in fulltext_results)

    neighbors = repo.get_paper_neighbors("arxiv:2401.12345", min_confidence=0.5)
    assert neighbors
    assert neighbors[0]["relation_type"] in {
        "same_method_family",
        "same_benchmark",
        "related_problem",
        "common_baseline",
    }

    repo.close()
