"""Build progressive-disclosure paper reference packs from Docling output."""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..extraction import (
    SectionReference,
    save_section_manifest,
    split_markdown_sections,
)


@dataclass
class ReferencePack:
    """Reference files available to a paper skill."""

    document_path: str | None = None
    sections: list[SectionReference] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    figures: list[dict[str, Any]] = field(default_factory=list)
    manifest_path: str | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "document_path": self.document_path,
            "sections": [asdict(section) for section in self.sections],
            "tables": self.tables,
            "figures": self.figures,
            "manifest_path": self.manifest_path,
        }


class PaperReferencePackBuilder:
    """Create `references/` files that SKILL.md can point to directly."""

    def build(
        self,
        extraction_dir: str | Path,
        skill_dir: str | Path,
    ) -> ReferencePack:
        extraction_dir = Path(extraction_dir)
        skill_dir = Path(skill_dir)
        refs_dir = skill_dir / "references"
        refs_dir.mkdir(parents=True, exist_ok=True)

        pack = ReferencePack()
        document_src = extraction_dir / "document.md"
        if document_src.exists():
            document_dst = refs_dir / "document.md"
            shutil.copyfile(document_src, document_dst)
            pack.document_path = _rel(skill_dir, document_dst)

            sections_dir = refs_dir / "sections"
            pack.sections = split_markdown_sections(document_dst, sections_dir)
            save_section_manifest(pack.sections, refs_dir / "section_manifest.json")

        pack.tables = self._build_table_references(extraction_dir, refs_dir, skill_dir)
        pack.figures = self._build_figure_references(extraction_dir, refs_dir, skill_dir)

        manifest_path = refs_dir / "reference_manifest.json"
        pack.manifest_path = _rel(skill_dir, manifest_path)
        manifest_path.write_text(
            json.dumps(pack.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return pack

    def load(self, skill_dir: str | Path) -> ReferencePack | None:
        manifest_path = Path(skill_dir) / "references" / "reference_manifest.json"
        if not manifest_path.exists():
            return None
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return ReferencePack(
            document_path=data.get("document_path"),
            sections=[SectionReference(**item) for item in data.get("sections", [])],
            tables=data.get("tables", []),
            figures=data.get("figures", []),
            manifest_path=data.get("manifest_path"),
        )

    def _build_table_references(
        self,
        extraction_dir: Path,
        refs_dir: Path,
        skill_dir: Path,
    ) -> list[dict[str, Any]]:
        tables_src_dir = extraction_dir / "tables"
        if not tables_src_dir.exists():
            return []

        out_dir = refs_dir / "tables"
        out_dir.mkdir(parents=True, exist_ok=True)
        entries: list[dict[str, Any]] = []

        for idx, table_src in enumerate(sorted(tables_src_dir.glob("table_*.csv")), 1):
            csv_dst = out_dir / table_src.name
            shutil.copyfile(table_src, csv_dst)
            md_dst = out_dir / f"{table_src.stem}.md"
            preview = _csv_preview(table_src)
            md_dst.write_text(
                "\n".join(
                    [
                        f"# Table {idx}",
                        "",
                        f"CSV source: `{_rel(skill_dir, csv_dst)}`",
                        "",
                        "Use this reference when the query asks for exact quantitative results, metrics, baselines, comparisons, or ablation values.",
                        "",
                        "## Preview",
                        "",
                        preview or "(No table preview extracted.)",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            entries.append(
                {
                    "id": f"table_{idx:03d}",
                    "path": _rel(skill_dir, md_dst),
                    "csv_path": _rel(skill_dir, csv_dst),
                    "query_intents": ["experiments", "results", "table_or_figure", "exact_values"],
                    "likely_contains": ["metrics", "datasets", "baselines", "quantitative comparisons"],
                }
            )
        return entries

    def _build_figure_references(
        self,
        extraction_dir: Path,
        refs_dir: Path,
        skill_dir: Path,
    ) -> list[dict[str, Any]]:
        figures_src_dir = extraction_dir / "figures"
        if not figures_src_dir.exists():
            return []

        out_dir = refs_dir / "figures"
        out_dir.mkdir(parents=True, exist_ok=True)
        entries: list[dict[str, Any]] = []

        for idx, figure_src in enumerate(sorted(figures_src_dir.glob("figure_*.png")), 1):
            image_dst = out_dir / figure_src.name
            shutil.copyfile(figure_src, image_dst)
            md_dst = out_dir / f"{figure_src.stem}.md"
            md_dst.write_text(
                "\n".join(
                    [
                        f"# Figure {idx}",
                        "",
                        f"Image source: `{_rel(skill_dir, image_dst)}`",
                        "",
                        "Use this reference when the query asks about architecture, diagrams, visual evidence, plotted trends, or figure-specific claims.",
                        "",
                        f"![Figure {idx}]({image_dst.name})",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            entries.append(
                {
                    "id": f"figure_{idx:03d}",
                    "path": _rel(skill_dir, md_dst),
                    "image_path": _rel(skill_dir, image_dst),
                    "query_intents": ["method", "architecture", "table_or_figure", "visual_evidence"],
                    "likely_contains": ["architecture", "pipeline", "visual evidence", "plots"],
                }
            )
        return entries


def _csv_preview(path: Path, limit: int = 12) -> str:
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))[:limit]
    except UnicodeDecodeError:
        with path.open("r", newline="") as f:
            rows = list(csv.reader(f))[:limit]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    header = padded[0]
    body = padded[1:]
    lines = [
        "| " + " | ".join(_escape(cell) for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(_escape(cell) for cell in row) + " |" for row in body)
    return "\n".join(lines)


def _escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
