"""Extraction Module Tests

Test Docling extraction components without requiring Docling installation.
"""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Test schema imports (should work without Docling)
from logos2.extraction.section_indexer import SectionIndexer, index_sections_from_markdown
from logos2.extraction.evidence_indexer import EvidenceIndexer, index_evidence_from_docling_output
from logos2.extraction.section_splitter import split_markdown_sections
from logos2.nodes.paper_reference_pack_builder import PaperReferencePackBuilder
from logos2.schemas.paper_skill_manifest import SectionIndex, EvidenceIndex


def test_section_indexer_from_text():
    """Test section indexing from markdown content"""
    
    # Create test markdown
    markdown_content = """# Introduction

This is the introduction.

## Related Work

Previous work discussion.

# Method

Our approach details.

## Architecture

System design.

# Experiments

Results and evaluation.

# Conclusion

Summary and future work.
"""
    
    # Write to temp file
    test_dir = Path("test_output")
    test_dir.mkdir(exist_ok=True)
    
    md_path = test_dir / "test_doc.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    
    # Index sections
    indexer = SectionIndexer()
    sections = indexer.index_from_markdown(md_path, total_pages=10)
    
    assert len(sections) == 6, f"Expected 6 sections, got {len(sections)}"
    assert sections[0].section_name == "Introduction"
    assert sections[2].section_name == "Method"
    
    print(f"[OK] Indexed {len(sections)} sections")
    
    # Cleanup
    md_path.unlink()


def test_evidence_indexer_from_files():
    """Test evidence indexing from file structure"""
    
    # Create mock extraction directory
    test_dir = Path("test_output")
    test_dir.mkdir(exist_ok=True)
    
    figures_dir = test_dir / "figures"
    tables_dir = test_dir / "tables"
    figures_dir.mkdir(exist_ok=True)
    tables_dir.mkdir(exist_ok=True)
    
    # Create mock figure
    (figures_dir / "figure_001.png").touch()
    (figures_dir / "figure_002.png").touch()
    
    # Create mock table
    (tables_dir / "table_001.csv").touch()
    
    # Create document.md
    doc_md = test_dir / "document.md"
    doc_md.write_text("""
# Paper Title

See Figure 1: System Architecture.

Table 1 shows the results.
""")
    
    # Index evidence
    indexer = EvidenceIndexer()
    evidence = indexer.index_from_docling_output(test_dir)
    
    assert len(evidence) == 3, f"Expected 3 evidence items, got {len(evidence)}"
    
    figs = [e for e in evidence if e.evidence_type == "figure"]
    tabs = [e for e in evidence if e.evidence_type == "table"]
    
    assert len(figs) == 2
    assert len(tabs) == 1
    
    print(f"[OK] Indexed {len(figs)} figures, {len(tabs)} tables")
    
    # Cleanup
    import shutil
    shutil.rmtree(test_dir)


def test_paper_skill_builder_with_extraction():
    """Test PaperSkillBuilder accepts extraction directory"""
    from logos2.nodes.paper_skill_builder import PaperSkillBuilder
    from logos2.schemas import PaperProfile
    
    builder = PaperSkillBuilder(paper_skills_dir="test_paper_skills")
    
    # Create profile
    profile = PaperProfile(
        paper_id="arxiv:2401.12345",
        title="Test Paper",
        tldr="A test paper",
        reading_level="L2",
        skill_path="paper_skills/test/SKILL.md",
        pdf_path="paper_library/arxiv_2401_12345/original.pdf"
    )
    
    # Build without extraction (should work with placeholder)
    manifest = builder.build(profile, extraction_dir=None)
    
    assert manifest.paper_id == "arxiv:2401.12345"
    assert len(manifest.section_index) > 0
    
    print(f"[OK] Built skill pack with {len(manifest.section_index)} sections")
    
    # Cleanup
    import shutil
    if Path("test_paper_skills").exists():
        shutil.rmtree("test_paper_skills")


def test_section_splitter_writes_original_section_references(tmp_path):
    document = tmp_path / "document.md"
    document.write_text(
        """# Abstract

This paper studies GraphRAG.

# 1 Introduction

Motivation and prior limitations.

# 3 Method

Algorithm details and architecture.

# 4 Experiments

Datasets, baselines, and metrics.
""",
        encoding="utf-8",
    )

    sections = split_markdown_sections(document, tmp_path / "sections")

    assert len(sections) == 4
    assert sections[2].title == "3 Method"
    assert "method" in sections[2].query_intents
    method_text = (tmp_path / "sections" / sections[2].filename).read_text(encoding="utf-8")
    assert "Algorithm details and architecture." in method_text


def test_reference_pack_and_skill_use_progressive_disclosure(tmp_path):
    from logos2.nodes.paper_skill_builder import PaperSkillBuilder
    from logos2.schemas import PaperProfile

    extraction_dir = tmp_path / "paper_library" / "arxiv_2501.00001"
    (extraction_dir / "tables").mkdir(parents=True)
    (extraction_dir / "figures").mkdir()
    (extraction_dir / "document.md").write_text(
        """# Abstract

GraphRAG benchmark paper.

# Introduction

The paper motivates unified evaluation.

# Methodology

The method section describes the pipeline.

# Experiments

Table 1 reports datasets, baselines, and metrics.
""",
        encoding="utf-8",
    )
    (extraction_dir / "extraction_meta.json").write_text(
        json.dumps({"num_pages": 8, "num_tables": 1, "num_figures": 1}),
        encoding="utf-8",
    )
    (extraction_dir / "tables" / "table_001.csv").write_text(
        "Dataset,Metric,Score\nHotpotQA,F1,0.82\n",
        encoding="utf-8",
    )
    (extraction_dir / "figures" / "figure_001.png").write_bytes(b"fake")

    profile = PaperProfile(
        paper_id="arxiv:2501.00001",
        title="GraphRAG Benchmark Paper",
        tldr="A GraphRAG benchmark paper.",
        reading_level="L2",
        skill_path="paper_skills/arxiv_2501.00001/SKILL.md",
    )
    builder = PaperSkillBuilder(paper_skills_dir=str(tmp_path / "paper_skills"))
    manifest = builder.build(profile, extraction_dir=extraction_dir)
    skill_dir = Path(manifest.skill_md_path).parent

    assert (skill_dir / "references" / "document.md").exists()
    assert (skill_dir / "references" / "sections").exists()
    assert (skill_dir / "references" / "tables" / "table_001.md").exists()
    assert (skill_dir / "references" / "figures" / "figure_001.md").exists()

    skill_md = Path(manifest.skill_md_path).read_text(encoding="utf-8")
    assert "## Query Routing" in skill_md
    assert "references/sections/" in skill_md
    assert "references/tables/table_001.md" in skill_md
    assert "paper_profile.json" not in skill_md.split("## Start Here", 1)[1].split("## Query Routing", 1)[0]


def test_qa_progressive_reference_selection(tmp_path):
    from logos2.nodes.paper_skill_builder import PaperSkillBuilder
    from logos2.nodes.qa_agent import QAAgent
    from logos2.schemas import PaperProfile

    extraction_dir = tmp_path / "paper_library" / "arxiv_2501.00002"
    (extraction_dir / "tables").mkdir(parents=True)
    (extraction_dir / "figures").mkdir()
    (extraction_dir / "document.md").write_text(
        """# Introduction

Problem motivation.

# Proposed Method

Algorithm details.

# Results

Table 1 gives scores.
""",
        encoding="utf-8",
    )
    (extraction_dir / "tables" / "table_001.csv").write_text(
        "Method,Score\nGraphRAG,0.9\n",
        encoding="utf-8",
    )

    profile = PaperProfile(
        paper_id="arxiv:2501.00002",
        title="GraphRAG Results Paper",
        tldr="A results paper.",
        reading_level="L2",
        skill_path="paper_skills/arxiv_2501.00002/SKILL.md",
    )
    manifest = PaperSkillBuilder(paper_skills_dir=str(tmp_path / "paper_skills")).build(
        profile,
        extraction_dir=extraction_dir,
    )

    class _Registry:
        def get_skill_path(self, paper_id):
            return manifest.skill_md_path

    qa = QAAgent(repository=None, skill_registry=_Registry())

    method_target = qa._select_progressive_reference(
        "arxiv:2501.00002",
        "method_intuition",
        "What are the algorithm details?",
    )
    table_target = qa._select_progressive_reference(
        "arxiv:2501.00002",
        "benchmark_comparison",
        "What does Table 1 report?",
    )

    assert method_target and "proposed_method" in method_target
    assert table_target == "references/tables/table_001.md"


if __name__ == "__main__":
    print("Running extraction module tests...")
    test_section_indexer_from_text()
    test_evidence_indexer_from_files()
    test_paper_skill_builder_with_extraction()
    print("\nAll extraction tests passed!")
