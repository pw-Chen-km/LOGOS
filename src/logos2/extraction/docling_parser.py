"""Docling Extractor

Lightweight wrapper around Docling for PDF extraction.

Extracts:
- document.md: Full parsed document in markdown
- tables/: CSV files for each table
- figures/: PNG files for each figure
- metadata: Page info, structure mapping

NO LLM processing. NO Neo4j writes. File-based output only.
"""

import os
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

DOCLING_AVAILABLE = None


def _load_document_converter():
    """Import Docling lazily to avoid optional dependency import failures."""
    global DOCLING_AVAILABLE
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions

        DOCLING_AVAILABLE = True
        pipeline_options = PdfPipelineOptions(generate_picture_images=True)
        return lambda: DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
    except Exception:
        DOCLING_AVAILABLE = False
        return None


@dataclass
class ExtractionResult:
    """Result of PDF extraction"""
    paper_id: str
    output_dir: Path
    document_md_path: Optional[Path] = None
    tables_dir: Optional[Path] = None
    figures_dir: Optional[Path] = None
    success: bool = False
    error: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class DoclingExtractor:
    """Docling-based PDF Extractor
    
    Extracts document structure, tables, and figures from PDF.
    Outputs are file-based (markdown, CSV, PNG), not Neo4j nodes.
    
    Usage:
        extractor = DoclingExtractor(output_base_dir="paper_library")
        result = extractor.extract(pdf_path, paper_id="arxiv:2401.12345")
        
        # result.output_dir contains:
        #   - original.pdf
        #   - document.md
        #   - tables/table_001.csv
        #   - figures/figure_001.png
        #   - extraction_meta.json
    """
    
    def __init__(self, output_base_dir: str = "paper_library"):
        """
        Args:
            output_base_dir: Base directory for all paper extractions
        """
        self.output_base_dir = Path(output_base_dir)
        self.output_base_dir.mkdir(parents=True, exist_ok=True)
        
        self._converter: Optional[Any] = None
        document_converter_factory = _load_document_converter()
        if document_converter_factory:
            self._converter = document_converter_factory()
    
    def extract(
        self,
        pdf_path: str,
        paper_id: str,
        force_reextract: bool = False
    ) -> ExtractionResult:
        """Extract PDF using Docling
        
        Args:
            pdf_path: Path to PDF file or URL
            paper_id: Unique paper identifier
            force_reextract: If True, re-extract even if output exists
            
        Returns:
            ExtractionResult with paths to extracted files
        """
        # Create safe directory name from paper_id
        safe_id = paper_id.replace(":", "_").replace("/", "_")
        output_dir = self.output_base_dir / safe_id
        
        # Check if already extracted
        if not force_reextract and self._is_already_extracted(output_dir):
            return self._load_existing_extraction(output_dir, paper_id)
        
        # Create output directory structure
        output_dir.mkdir(parents=True, exist_ok=True)
        tables_dir = output_dir / "tables"
        figures_dir = output_dir / "figures"
        tables_dir.mkdir(exist_ok=True)
        figures_dir.mkdir(exist_ok=True)
        
        result = ExtractionResult(
            paper_id=paper_id,
            output_dir=output_dir,
            tables_dir=tables_dir,
            figures_dir=figures_dir
        )
        
        if not self._converter:
            result.error = "Docling not installed. Install with: pip install docling"
            return result
        
        try:
            # Convert PDF
            doc = self._converter.convert(pdf_path)
            
            # Export document markdown
            document_md_path = output_dir / "document.md"
            with open(document_md_path, "w", encoding="utf-8") as f:
                f.write(doc.document.export_to_markdown())
            result.document_md_path = document_md_path
            
            # Export tables as CSV
            table_count = 0
            for table in doc.document.tables:
                table_count += 1
                table_path = tables_dir / f"table_{table_count:03d}.csv"
                # Docling table to CSV
                try:
                    df = table.export_to_dataframe(doc.document)
                except TypeError:
                    df = table.export_to_dataframe()
                df.to_csv(table_path, index=False)
            
            # Export figures as PNG
            figure_count = 0
            for picture in doc.document.pictures:
                figure_count += 1
                figure_path = figures_dir / f"figure_{figure_count:03d}.png"
                # Save image
                if hasattr(picture, 'image') and picture.image:
                    picture.image.pil_image.save(figure_path)
                elif hasattr(picture, "get_image"):
                    image = picture.get_image(doc.document)
                    if image:
                        image.save(figure_path)
            
            # Count sections from document structure (approximate from headers)
            num_sections = 0
            if hasattr(doc.document, 'iterate_items'):
                for item in doc.document.iterate_items():
                    if hasattr(item, 'label') and item.label in ['header', 'h1', 'h2', 'h3']:
                        num_sections += 1
            
            # Save extraction metadata
            metadata = {
                "paper_id": paper_id,
                "pdf_source": pdf_path,
                "num_pages": len(doc.document.pages) if hasattr(doc.document, 'pages') else 0,
                "num_sections": num_sections,
                "num_tables": table_count,
                "num_figures": figure_count,
                "document_md": str(document_md_path.relative_to(self.output_base_dir)),
                "tables_dir": str(tables_dir.relative_to(self.output_base_dir)),
                "figures_dir": str(figures_dir.relative_to(self.output_base_dir)),
            }
            
            import json
            meta_path = output_dir / "extraction_meta.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            
            result.metadata = metadata
            result.success = True
            
        except Exception as e:
            result.error = f"Extraction failed: {str(e)}"
            result.success = False
        
        return result
    
    def _is_already_extracted(self, output_dir: Path) -> bool:
        """Check if paper has already been extracted"""
        return (output_dir / "extraction_meta.json").exists()
    
    def _load_existing_extraction(
        self,
        output_dir: Path,
        paper_id: str
    ) -> ExtractionResult:
        """Load existing extraction result"""
        import json
        
        meta_path = output_dir / "extraction_meta.json"
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        
        return ExtractionResult(
            paper_id=paper_id,
            output_dir=output_dir,
            document_md_path=output_dir / "document.md" if metadata.get("document_md") else None,
            tables_dir=output_dir / "tables" if metadata.get("tables_dir") else None,
            figures_dir=output_dir / "figures" if metadata.get("figures_dir") else None,
            success=True,
            metadata=metadata
        )
    
    def get_extraction_path(self, paper_id: str) -> Optional[Path]:
        """Get extraction directory for a paper if it exists"""
        safe_id = paper_id.replace(":", "_").replace("/", "_")
        output_dir = self.output_base_dir / safe_id
        
        if (output_dir / "extraction_meta.json").exists():
            return output_dir
        return None
