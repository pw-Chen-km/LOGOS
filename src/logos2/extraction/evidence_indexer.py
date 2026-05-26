"""Evidence Indexer

Generate evidence_index.json from Docling output.

Indexes:
- Figures (PNG files with captions)
- Tables (CSV files with captions)
- Maps evidence to sections and page numbers
"""

import re
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict

from ..schemas.paper_skill_manifest import EvidenceIndex


@dataclass
class EvidenceInfo:
    """Intermediate evidence info"""
    evidence_id: str
    evidence_type: str  # "figure" or "table"
    filename: str
    caption: Optional[str] = None
    pdf_page: Optional[int] = None
    section: Optional[str] = None
    markdown_anchor: Optional[str] = None


def extract_caption_from_nearby_text(
    text: str,
    figure_num: Optional[int] = None,
    table_num: Optional[int] = None
) -> Optional[str]:
    """Try to extract caption from text near figure/table reference"""
    
    if figure_num:
        # Look for "Figure X: caption" or "Fig. X: caption"
        patterns = [
            rf'[Ff]igure\s*{figure_num}[.:]\s*([^\n]+)',
            rf'[Ff]ig\.\s*{figure_num}[.:]\s*([^\n]+)',
        ]
    elif table_num:
        # Look for "Table X: caption"
        patterns = [
            rf'[Tt]able\s*{table_num}[.:]\s*([^\n]+)',
        ]
    else:
        return None
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    
    return None


class EvidenceIndexer:
    """Generate evidence index from Docling extraction output
    
    Usage:
        indexer = EvidenceIndexer()
        evidence = indexer.index_from_docling_output(
            extraction_dir="paper_library/arxiv_2401_12345/"
        )
        
        # Save index
        indexer.save_index(evidence, output_path=".../evidence_index.json")
    """
    
    def __init__(self):
        self.figure_pattern = re.compile(r'[Ff]ig(?:ure)?\.?\s*(\d+)', re.IGNORECASE)
        self.table_pattern = re.compile(r'[Tt]able\.?\s*(\d+)', re.IGNORECASE)
    
    def index_from_docling_output(
        self,
        extraction_dir: Path,
        document_md_path: Optional[Path] = None
    ) -> List[EvidenceIndex]:
        """Generate evidence index from Docling extraction
        
        Args:
            extraction_dir: Directory with tables/, figures/, document.md
            document_md_path: Optional explicit path to document.md
            
        Returns:
            List of EvidenceIndex entries
        """
        if not extraction_dir.exists():
            return []
        
        # Find subdirectories
        tables_dir = extraction_dir / "tables"
        figures_dir = extraction_dir / "figures"
        
        # Default document.md path
        if document_md_path is None:
            document_md_path = extraction_dir / "document.md"
        
        # Read document content for caption extraction
        document_content = ""
        if document_md_path.exists():
            with open(document_md_path, "r", encoding="utf-8") as f:
                document_content = f.read()
        
        evidence_list = []
        
        # Index figures
        if figures_dir.exists():
            figure_files = sorted(figures_dir.glob("figure_*.png"))
            for i, fig_path in enumerate(figure_files, 1):
                evidence = self._create_figure_index(
                    fig_path, i, document_content
                )
                evidence_list.append(evidence)
        
        # Index tables
        if tables_dir.exists():
            table_files = sorted(tables_dir.glob("table_*.csv"))
            for i, table_path in enumerate(table_files, 1):
                evidence = self._create_table_index(
                    table_path, i, document_content
                )
                evidence_list.append(evidence)
        
        return evidence_list
    
    def _create_figure_index(
        self,
        fig_path: Path,
        fig_num: int,
        document_content: str
    ) -> EvidenceIndex:
        """Create EvidenceIndex for a figure"""
        # Extract caption from document
        caption = extract_caption_from_nearby_text(
            document_content, figure_num=fig_num
        )
        
        # Try to find which section mentions this figure
        section = self._find_containing_section(
            document_content, f"Figure {fig_num}", f"Fig. {fig_num}"
        )
        
        # Estimate page (would need position mapping for accuracy)
        pdf_page = None
        
        return EvidenceIndex(
            evidence_id=f"fig_{fig_num:03d}",
            evidence_type="figure",
            caption=caption or f"Figure {fig_num}",
            pdf_page=pdf_page,
            section=section
        )
    
    def _create_table_index(
        self,
        table_path: Path,
        table_num: int,
        document_content: str
    ) -> EvidenceIndex:
        """Create EvidenceIndex for a table"""
        # Extract caption from document
        caption = extract_caption_from_nearby_text(
            document_content, table_num=table_num
        )
        
        # Try to find which section mentions this table
        section = self._find_containing_section(
            document_content, f"Table {table_num}"
        )
        
        # Estimate page
        pdf_page = None
        
        return EvidenceIndex(
            evidence_id=f"tab_{table_num:03d}",
            evidence_type="table",
            caption=caption or f"Table {table_num}",
            pdf_page=pdf_page,
            section=section
        )
    
    def _find_containing_section(
        self,
        document_content: str,
        *search_terms: str
    ) -> Optional[str]:
        """Find which section contains the search terms"""
        lines = document_content.split('\n')
        current_section = None
        
        for line in lines:
            # Check for section header
            if line.startswith('#'):
                current_section = line.lstrip('#').strip()
            
            # Check if line contains search term
            for term in search_terms:
                if term in line:
                    return current_section
        
        return None
    
    def save_index(
        self,
        indexes: List[EvidenceIndex],
        output_path: Path
    ):
        """Save evidence index to JSON file"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                [asdict(idx) for idx in indexes],
                f,
                indent=2,
                ensure_ascii=False
            )


def index_evidence_from_docling_output(
    extraction_dir: Path,
    output_path: Optional[Path] = None
) -> List[EvidenceIndex]:
    """Convenience function to index evidence from Docling output
    
    Args:
        extraction_dir: Directory with Docling output
        output_path: Optional path to save index
        
    Returns:
        List of EvidenceIndex
    """
    indexer = EvidenceIndexer()
    indexes = indexer.index_from_docling_output(extraction_dir)
    
    if output_path:
        indexer.save_index(indexes, output_path)
    
    return indexes
