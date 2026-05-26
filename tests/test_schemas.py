"""Schema Validation Tests

Basic tests to validate Pydantic schemas and fixtures.
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Test only schemas (no storage dependencies)
from logos2.schemas.research_request import ResearchRequest
from logos2.schemas.paper_navigator_reading import PaperNavigatorReading
from logos2.schemas.survey_taxonomy import SurveyTaxonomy
from logos2.schemas.paper_profile import PaperProfile
from logos2.schemas.paper_skill_manifest import PaperSkillManifest
from logos2.schemas.candidate_edge import CandidateEdge
from logos2.schemas.verified_edge import VerifiedEdge


def test_research_request():
    """Test ResearchRequest schema"""
    request = ResearchRequest(
        request_id="req_001",
        raw_user_input="GraphRAG latest methods",
        research_goal="Survey GraphRAG methods",
        topic_keywords=["graph", "rag", "retrieval"],
        paper_count_target=50
    )
    assert request.request_id == "req_001"
    assert request.paper_count_target == 50
    print("[OK] ResearchRequest schema valid")


def test_paper_navigator_reading():
    """Test PaperNavigatorReading schema"""
    reading = PaperNavigatorReading(
        paper_id="arxiv:2401.12345",
        reading_level="L2",
        title="Test Paper",
        tldr="A test paper",
        benchmark_names=["HotpotQA"],
        confidence=0.85
    )
    assert reading.paper_id == "arxiv:2401.12345"
    assert reading.reading_level == "L2"
    print("[OK] PaperNavigatorReading schema valid")


def test_fixture_loading():
    """Test loading fixture files"""
    fixtures_dir = Path(__file__).parent / "fixtures"
    
    # Test paper_navigator_reading.json
    with open(fixtures_dir / "paper_navigator_reading.json", "r") as f:
        data = json.load(f)
    
    readings = [PaperNavigatorReading(**item) for item in data]
    assert len(readings) == 3
    assert readings[0].paper_id == "arxiv:2401.12345"
    print(f"[OK] Loaded {len(readings)} paper readings from fixture")
    
    # Test survey_taxonomy.json
    with open(fixtures_dir / "survey_taxonomy.json", "r") as f:
        data = json.load(f)
    
    taxonomy = SurveyTaxonomy(**data)
    assert taxonomy.taxonomy_id == "tax_graphrag_2024"
    assert len(taxonomy.themes) == 3
    assert len(taxonomy.candidate_relations) == 3
    print(f"[OK] Loaded taxonomy with {len(taxonomy.themes)} themes, {len(taxonomy.candidate_relations)} relations")


def test_candidate_edge():
    """Test CandidateEdge schema"""
    edge = CandidateEdge(
        source_paper_id="arxiv:2401.12345",
        target_paper_id="arxiv:2402.67890",
        relation_type="same_benchmark",
        confidence=0.72
    )
    assert edge.status == "candidate"  # default
    assert edge.source == "survey_taxonomy"  # default
    print("[OK] CandidateEdge schema valid")


if __name__ == "__main__":
    print("Running schema tests...")
    test_research_request()
    test_paper_navigator_reading()
    test_fixture_loading()
    test_candidate_edge()
    print("\nAll tests passed!")
