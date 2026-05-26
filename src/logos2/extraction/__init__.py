"""LOGOS 2.0 Extraction Module

Lightweight document extraction using Docling.

This module provides file-based extraction only:
- PDF → markdown document
- Tables → CSV files
- Figures → PNG files
- Section index → JSON
- Evidence index → JSON

NO heavy ontology building, NO Neo4j writes, NO LLM reasoning.
"""

from .docling_parser import DoclingExtractor, ExtractionResult
from .section_indexer import SectionIndexer, index_sections_from_markdown
from .evidence_indexer import EvidenceIndexer, index_evidence_from_docling_output
from .section_splitter import (
    SectionReference,
    classify_section_title,
    save_section_manifest,
    split_markdown_sections,
)

__all__ = [
    "DoclingExtractor",
    "ExtractionResult",
    "SectionIndexer",
    "index_sections_from_markdown",
    "EvidenceIndexer",
    "index_evidence_from_docling_output",
    "SectionReference",
    "classify_section_title",
    "save_section_manifest",
    "split_markdown_sections",
]
