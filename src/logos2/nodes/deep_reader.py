"""OnDemandDeepReaderAgent

Module: OnDemandDeepReaderAgent (Optional High-Cost Agent)

Read original PDF sections or parsed sections when paper profile and skill
references are insufficient.

Input:
- user question
- PaperSkillPack
- section_index.json
- evidence_index.json
- original PDF path
- optional parsed markdown section path

Output:
- DeepReadingResult
- cited section/page/table/figure evidence

Uses Docling extraction output (document.md, tables/, figures/).
NO Neo4j writes. File-based reading only.
"""

import re
import json
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

from ..schemas import PaperSkillManifest, SectionIndex, EvidenceIndex


@dataclass
class DeepReadingResult:
    """Result of on-demand deep reading"""
    content: str
    source_type: str  # "markdown_section", "figure", "table", "pdf_page"
    section_name: Optional[str] = None
    page_number: Optional[int] = None
    evidence_id: Optional[str] = None
    citation: str = ""  # Formatted citation for answer
    full_text: Optional[str] = None  # Full section text if truncated


class OnDemandDeepReaderAgent:
    """OnDemandDeepReaderAgent
    
    Reads specific sections, figures, tables from Docling extraction output.
    Only invoked when paper skill pack reference guides are insufficient.
    
    Usage:
        reader = OnDemandDeepReaderAgent()
        
        # Read specific section
        result = reader.read_section(
            skill_manifest=manifest,
            section_name="Method",
            extraction_dir=extraction_dir
        )
        
        # Read specific figure
        result = reader.read_evidence(
            skill_manifest=manifest,
            evidence_id="fig_001",
            extraction_dir=extraction_dir
        )
    """
    
    def __init__(self, max_content_length: int = 4000):
        """
        Args:
            max_content_length: Maximum characters to return in content
        """
        self.max_content_length = max_content_length
    
    def read_section(
        self,
        skill_manifest: PaperSkillManifest,
        section_name: str,
        extraction_dir: Path,
        include_subsections: bool = True
    ) -> Optional[DeepReadingResult]:
        """Read specific section from document
        
        Args:
            skill_manifest: Paper skill manifest with indexes
            section_name: Section name to read (e.g., "Method")
            extraction_dir: Docling extraction directory
            include_subsections: Whether to include subsections
            
        Returns:
            DeepReadingResult with section content, or None if not found
        """
        # Find section in index
        section_idx = self._find_section_index(
            skill_manifest.section_index, section_name
        )
        
        if not section_idx:
            return None
        
        # Read from document.md
        document_md = extraction_dir / "document.md"
        if not document_md.exists():
            return None
        
        content = self._read_section_from_markdown(
            document_md, section_idx, include_subsections
        )
        
        if not content:
            return None
        
        # Create result
        truncated = len(content) > self.max_content_length
        display_content = content[:self.max_content_length] + ("..." if truncated else "")
        
        return DeepReadingResult(
            content=display_content,
            source_type="markdown_section",
            section_name=section_idx.section_name,
            page_number=section_idx.pdf_page_start,
            citation=self._format_citation(
                skill_manifest.paper_id,
                section_name=section_idx.section_name,
                page=section_idx.pdf_page_start
            ),
            full_text=content if truncated else None
        )
    
    def read_evidence(
        self,
        skill_manifest: PaperSkillManifest,
        evidence_id: str,
        extraction_dir: Path
    ) -> Optional[DeepReadingResult]:
        """Read specific figure or table
        
        Args:
            skill_manifest: Paper skill manifest with evidence index
            evidence_id: Evidence ID (e.g., "fig_001", "tab_001")
            extraction_dir: Docling extraction directory
            
        Returns:
            DeepReadingResult with evidence info and path, or None if not found
        """
        # Find evidence in index
        evidence_idx = self._find_evidence_index(
            skill_manifest.evidence_index, evidence_id
        )
        
        if not evidence_idx:
            return None
        
        # Get evidence file path
        if evidence_idx.evidence_type == "figure":
            evidence_path = extraction_dir / "figures" / f"{evidence_id}.png"
            if not evidence_path.exists():
                # Try numbered format
                match = re.search(r'(\d+)', evidence_id)
                if match:
                    num = int(match.group(1))
                    evidence_path = extraction_dir / "figures" / f"figure_{num:03d}.png"
        else:  # table
            evidence_path = extraction_dir / "tables" / f"{evidence_id}.csv"
            if not evidence_path.exists():
                match = re.search(r'(\d+)', evidence_id)
                if match:
                    num = int(match.group(1))
                    evidence_path = extraction_dir / "tables" / f"table_{num:03d}.csv"
        
        if not evidence_path or not evidence_path.exists():
            # Return info even if file not found
            return DeepReadingResult(
                content=f"Evidence {evidence_id}: {evidence_idx.caption or 'No caption'}",
                source_type=evidence_idx.evidence_type,
                page_number=evidence_idx.pdf_page,
                evidence_id=evidence_id,
                citation=self._format_citation(
                    skill_manifest.paper_id,
                    evidence_type=evidence_idx.evidence_type,
                    evidence_id=evidence_id,
                    page=evidence_idx.pdf_page
                )
            )
        
        # Read content based on type
        if evidence_idx.evidence_type == "figure":
            content = f"[Figure: {evidence_path}]\nCaption: {evidence_idx.caption or 'N/A'}"
        else:
            # Read CSV content
            try:
                import csv
                rows = []
                with open(evidence_path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    for i, row in enumerate(reader):
                        if i >= 20:  # Limit rows
                            rows.append("...")
                            break
                        rows.append(", ".join(row))
                content = f"[Table: {evidence_path}]\n" + "\n".join(rows)
            except Exception:
                content = f"[Table: {evidence_path}]\nCaption: {evidence_idx.caption or 'N/A'}"
        
        return DeepReadingResult(
            content=content[:self.max_content_length],
            source_type=evidence_idx.evidence_type,
            page_number=evidence_idx.pdf_page,
            evidence_id=evidence_id,
            citation=self._format_citation(
                skill_manifest.paper_id,
                evidence_type=evidence_idx.evidence_type,
                evidence_id=evidence_id,
                page=evidence_idx.pdf_page
            ),
            full_text=content if len(content) > self.max_content_length else None
        )
    
    def read_page_range(
        self,
        skill_manifest: PaperSkillManifest,
        start_page: int,
        end_page: int,
        extraction_dir: Path
    ) -> Optional[DeepReadingResult]:
        """Read specific page range (requires PDF access)
        
        Args:
            skill_manifest: Paper skill manifest
            start_page: Start page number
            end_page: End page number
            extraction_dir: Directory with original.pdf
            
        Returns:
            DeepReadingResult, or None if PDF not available
        """
        # Check for original PDF
        pdf_path = extraction_dir / "original.pdf"
        if not pdf_path.exists():
            return None
        
        # MVP: Return marker indicating PDF page range
        # Full implementation would use PDF parser
        return DeepReadingResult(
            content=f"[PDF pages {start_page}-{end_page}: {pdf_path}]",
            source_type="pdf_page",
            page_number=start_page,
            citation=self._format_citation(
                skill_manifest.paper_id,
                page=start_page,
                page_end=end_page
            )
        )
    
    def find_and_read(
        self,
        query: str,
        skill_manifest: PaperSkillManifest,
        extraction_dir: Path
    ) -> Optional[DeepReadingResult]:
        """Find and read content based on query
        
        Tries to intelligently match query to section or evidence.
        
        Args:
            query: User query (e.g., "What does Figure 3 show?")
            skill_manifest: Paper skill manifest
            extraction_dir: Docling extraction directory
            
        Returns:
            DeepReadingResult, or None if no match found
        """
        query_lower = query.lower()
        
        # Check for figure references
        fig_match = re.search(r'fig(?:ure)?\.?\s*(\d+)', query_lower)
        if fig_match:
            fig_num = int(fig_match.group(1))
            evidence_id = f"fig_{fig_num:03d}"
            result = self.read_evidence(skill_manifest, evidence_id, extraction_dir)
            if result:
                return result
        
        # Check for table references
        table_match = re.search(r'table\.?\s*(\d+)', query_lower)
        if table_match:
            table_num = int(table_match.group(1))
            evidence_id = f"tab_{table_num:03d}"
            result = self.read_evidence(skill_manifest, evidence_id, extraction_dir)
            if result:
                return result
        
        # Check for section references
        sections = ["introduction", "method", "methodology", "approach",
                   "experiment", "results", "ablation", "conclusion",
                   "related work", "background"]
        
        for section in sections:
            if section in query_lower:
                # Try to find section in index
                result = self.read_section(
                    skill_manifest, section.capitalize(), extraction_dir
                )
                if result:
                    return result
                # Try with exact match from index
                for idx in skill_manifest.section_index:
                    if section.lower() in idx.section_name.lower():
                        result = self.read_section(
                            skill_manifest, idx.section_name, extraction_dir
                        )
                        if result:
                            return result
        
        # No specific match found
        return None
    
    def _find_section_index(
        self,
        section_indexes: List[SectionIndex],
        section_name: str
    ) -> Optional[SectionIndex]:
        """Find section in index"""
        # Exact match
        for idx in section_indexes:
            if idx.section_name.lower() == section_name.lower():
                return idx
        
        # Partial match
        for idx in section_indexes:
            if section_name.lower() in idx.section_name.lower():
                return idx
        
        return None
    
    def _find_evidence_index(
        self,
        evidence_indexes: List[EvidenceIndex],
        evidence_id: str
    ) -> Optional[EvidenceIndex]:
        """Find evidence in index"""
        for idx in evidence_indexes:
            if idx.evidence_id == evidence_id:
                return idx
        return None
    
    def _read_section_from_markdown(
        self,
        document_md: Path,
        section_idx: SectionIndex,
        include_subsections: bool
    ) -> Optional[str]:
        """Read section content from markdown file"""
        with open(document_md, "r", encoding="utf-8") as f:
            content = f.read()
        
        lines = content.split('\n')
        
        # Find section anchor
        anchor = section_idx.markdown_anchor
        if not anchor:
            return None
        
        # Find start line
        start_line = None
        for i, line in enumerate(lines):
            if anchor in line or line.strip().lstrip('#').strip() == section_idx.section_name:
                start_line = i
                break
        
        if start_line is None:
            return None
        
        # Find end line
        end_line = len(lines)
        if include_subsections:
            # Look for next section at same or higher level
            current_level = anchor.count('#')
            for i in range(start_line + 1, len(lines)):
                if lines[i].strip().startswith('#'):
                    level = lines[i].count('#')
                    if level <= current_level:
                        end_line = i
                        break
        else:
            # Only include until next section at any level
            for i in range(start_line + 1, len(lines)):
                if lines[i].strip().startswith('#'):
                    end_line = i
                    break
        
        # Extract content
        section_lines = lines[start_line:end_line]
        return '\n'.join(section_lines).strip()
    
    def _format_citation(
        self,
        paper_id: str,
        section_name: Optional[str] = None,
        evidence_type: Optional[str] = None,
        evidence_id: Optional[str] = None,
        page: Optional[int] = None,
        page_end: Optional[int] = None
    ) -> str:
        """Format citation string"""
        parts = [f"{paper_id}"]
        
        if section_name:
            parts.append(f"Section: {section_name}")
        
        if evidence_type and evidence_id:
            parts.append(f"{evidence_type.capitalize()}: {evidence_id}")
        
        if page:
            if page_end and page_end != page:
                parts.append(f"pp. {page}-{page_end}")
            else:
                parts.append(f"p. {page}")
        
        return " | ".join(parts)
