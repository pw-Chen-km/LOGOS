"""Section Indexer

Generate section_index.json from Docling output (document.md).

Maps:
- Section headers → page numbers
- Section content → markdown anchors
- Creates index for quick section lookup
"""

import re
import json
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict

from ..schemas.paper_skill_manifest import SectionIndex


@dataclass
class SectionInfo:
    """Intermediate section info during parsing"""
    section_name: str
    level: int  # Header level (# = 1, ## = 2, etc.)
    markdown_anchor: str
    content_start_line: int
    content_end_line: Optional[int] = None
    estimated_page: Optional[int] = None


def extract_page_hints(text: str) -> Optional[int]:
    """Try to extract page number from text hints
    
    Docling sometimes includes page markers like <!-- page 5 -->
    """
    # Look for HTML comments or markers
    patterns = [
        r'<!--\s*page\s*(\d+)\s*-->',
        r'\[page\s*(\d+)\]',
        r'---\s*page\s*(\d+)\s*---',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    
    return None


def estimate_page_from_position(
    line_num: int,
    total_lines: int,
    total_pages: int
) -> int:
    """Estimate page number from position in document"""
    if total_pages <= 0:
        return 1
    
    ratio = line_num / total_lines
    estimated = int(ratio * total_pages) + 1
    return min(estimated, total_pages)


class SectionIndexer:
    """Generate section index from parsed markdown document
    
    Usage:
        indexer = SectionIndexer()
        sections = indexer.index_from_markdown(
            markdown_path="paper_library/arxiv_2401_12345/document.md",
            total_pages=10
        )
        
        # Save index
        indexer.save_index(sections, output_path=".../section_index.json")
    """
    
    def __init__(self):
        self.section_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    
    def index_from_markdown(
        self,
        markdown_path: Path,
        total_pages: int = 0,
        extraction_meta: Optional[Dict] = None
    ) -> List[SectionIndex]:
        """Generate section index from markdown file
        
        Args:
            markdown_path: Path to document.md from Docling
            total_pages: Total pages in original PDF
            extraction_meta: Optional extraction metadata
            
        Returns:
            List of SectionIndex entries
        """
        if not markdown_path.exists():
            return []
        
        with open(markdown_path, "r", encoding="utf-8") as f:
            content = f.read()
            lines = content.split('\n')
        
        # Find all section headers
        section_infos = self._find_sections(lines)
        
        # Assign end lines and pages
        section_infos = self._complete_section_info(
            section_infos, lines, total_pages
        )
        
        # Convert to SectionIndex schema
        indexes = []
        for info in section_infos:
            index = SectionIndex(
                section_name=info.section_name,
                pdf_page_start=info.estimated_page,
                pdf_page_end=info.estimated_page,  # Single page by default
                markdown_anchor=info.markdown_anchor
            )
            indexes.append(index)
        
        return indexes
    
    def _find_sections(self, lines: List[str]) -> List[SectionInfo]:
        """Find all section headers in document"""
        sections = []
        
        for line_num, line in enumerate(lines, 1):
            match = self.section_pattern.match(line)
            if match:
                hashes = match.group(1)
                title = match.group(2).strip()
                level = len(hashes)
                anchor = f"{'#' * level} {title}"
                
                sections.append(SectionInfo(
                    section_name=title,
                    level=level,
                    markdown_anchor=anchor,
                    content_start_line=line_num
                ))
        
        return sections
    
    def _complete_section_info(
        self,
        sections: List[SectionInfo],
        lines: List[str],
        total_pages: int
    ) -> List[SectionInfo]:
        """Assign end lines and page numbers to sections"""
        
        for i, section in enumerate(sections):
            # Set content end to start of next section
            if i + 1 < len(sections):
                section.content_end_line = sections[i + 1].content_start_line - 1
            else:
                section.content_end_line = len(lines)
            
            # Estimate page from position
            mid_line = (section.content_start_line + section.content_end_line) // 2
            section.estimated_page = estimate_page_from_position(
                mid_line, len(lines), total_pages
            )
            
            # Try to find explicit page markers in content
            section_content = '\n'.join(
                lines[section.content_start_line:section.content_end_line]
            )
            explicit_page = extract_page_hints(section_content)
            if explicit_page:
                section.estimated_page = explicit_page
        
        return sections
    
    def save_index(
        self,
        indexes: List[SectionIndex],
        output_path: Path
    ):
        """Save section index to JSON file"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                [asdict(idx) for idx in indexes],
                f,
                indent=2,
                ensure_ascii=False
            )


def index_sections_from_markdown(
    markdown_path: Path,
    total_pages: int = 0,
    output_path: Optional[Path] = None
) -> List[SectionIndex]:
    """Convenience function to index sections from markdown
    
    Args:
        markdown_path: Path to document.md
        total_pages: Total pages in PDF
        output_path: Optional path to save index
        
    Returns:
        List of SectionIndex
    """
    indexer = SectionIndexer()
    indexes = indexer.index_from_markdown(markdown_path, total_pages)
    
    if output_path:
        indexer.save_index(indexes, output_path)
    
    return indexes
