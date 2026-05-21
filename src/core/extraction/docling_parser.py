import os
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions

class PdfExtractor:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            
        pipeline_options = PdfPipelineOptions(generate_picture_images=True)
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )

    def extract(self, source_url: str) -> str:
        """Extracts markdown, tables, and images from URL, returns path to markdown."""
        print(f"[PdfExtractor] Processing source: {source_url}")
        result = self.converter.convert(source_url)
        doc = result.document
        
        md_path = os.path.join(self.output_dir, "document.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(doc.export_to_markdown())
        
        print(f"[PdfExtractor] Saved {len(doc.tables)} tables and {len(doc.pictures)} pictures.")
        
        for i, table in enumerate(doc.tables):
            df = table.export_to_dataframe(doc)
            df.to_csv(os.path.join(self.output_dir, f"table_{i}.csv"), index=False)
            
        for i, pic in enumerate(doc.pictures):
            try:
                pil_image = pic.get_image(doc)
                if pil_image:
                    pil_image.save(os.path.join(self.output_dir, f"figure_{i}.png"))
            except Exception:
                pass
                
        return md_path
