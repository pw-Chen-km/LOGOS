"""Split Docling markdown into paper section reference files.

The splitter does not assume a fixed paper structure. It discovers markdown
headings, writes each discovered section as original paper text, and labels
likely query intents for progressive-disclosure routing.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SectionReference:
    """A paper section written to a reference markdown file."""

    title: str
    level: int
    filename: str
    path: str
    start_line: int
    end_line: int
    query_intents: list[str] = field(default_factory=list)
    likely_contains: list[str] = field(default_factory=list)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def split_markdown_sections(
    markdown_path: str | Path,
    output_dir: str | Path,
    *,
    max_sections: int = 80,
) -> list[SectionReference]:
    """Split a markdown document into one file per discovered section.

    Args:
        markdown_path: Docling `document.md`.
        output_dir: Destination directory for section markdown files.
        max_sections: Safety cap to avoid creating noisy tiny files.

    Returns:
        SectionReference manifest entries.
    """
    markdown_path = Path(markdown_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    headings = _discover_headings(lines)

    if not headings:
        content = "\n".join(lines).strip()
        return [_write_section(output_dir, 0, "Document", 1, 1, len(lines), content)]

    sections: list[SectionReference] = []
    for idx, heading in enumerate(headings[:max_sections]):
        line_idx, level, title = heading
        next_line_idx = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        section_lines = lines[line_idx:next_line_idx]
        content = "\n".join(section_lines).strip()
        if not content:
            continue
        sections.append(
            _write_section(
                output_dir,
                idx,
                title,
                level,
                line_idx + 1,
                next_line_idx,
                content,
            )
        )

    return sections


def save_section_manifest(
    sections: list[SectionReference],
    output_path: str | Path,
) -> None:
    """Save section references as JSON for deterministic builders/tests."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([asdict(section) for section in sections], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _discover_headings(lines: list[str]) -> list[tuple[int, int, str]]:
    headings: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if not match:
            continue
        title = _clean_title(match.group(2))
        if not title:
            continue
        headings.append((idx, len(match.group(1)), title))
    return headings


def _write_section(
    output_dir: Path,
    index: int,
    title: str,
    level: int,
    start_line: int,
    end_line: int,
    content: str,
) -> SectionReference:
    slug = _slugify(title) or "section"
    filename = f"{index:02d}_{slug}.md"
    path = output_dir / filename
    intents, contains = classify_section_title(title)
    path.write_text(
        "\n".join(
            [
                "---",
                f'section_title: "{title.replace(chr(34), chr(39))}"',
                f"source_lines: {start_line}-{end_line}",
                "---",
                "",
                content,
                "",
            ]
        ),
        encoding="utf-8",
    )
    return SectionReference(
        title=title,
        level=level,
        filename=filename,
        path=_posix(path),
        start_line=start_line,
        end_line=end_line,
        query_intents=intents,
        likely_contains=contains,
    )


def classify_section_title(title: str) -> tuple[list[str], list[str]]:
    """Infer likely query intents from a paper section title."""
    normalized = title.lower()
    rules: list[tuple[tuple[str, ...], list[str], list[str]]] = [
        (("abstract",), ["summary", "overview"], ["main claim", "short summary"]),
        (
            ("introduction", "motivation"),
            ["motivation", "research_problem", "summary"],
            ["research problem", "motivation", "prior limitations"],
        ),
        (
            ("related work", "background", "preliminar"),
            ["related_work", "prior_work"],
            ["prior methods", "positioning", "background"],
        ),
        (
            ("method", "approach", "framework", "model", "architecture", "algorithm"),
            ["method", "algorithm", "technical_detail"],
            ["algorithm details", "architecture", "method components", "design rationale"],
        ),
        (
            ("experiment", "evaluation", "setup", "implementation detail"),
            ["experiments", "datasets", "metrics"],
            ["experimental setup", "datasets", "baselines", "metrics"],
        ),
        (
            ("result", "analysis", "ablation", "performance"),
            ["results", "comparison", "table_or_figure"],
            ["quantitative results", "ablation study", "comparisons"],
        ),
        (
            ("discussion", "limitation", "future work"),
            ["limitations", "discussion", "future_work"],
            ["limitations", "failure modes", "future work"],
        ),
        (("conclusion",), ["summary", "future_work"], ["conclusion", "takeaways"]),
        (("appendix", "supplement"), ["appendix", "technical_detail"], ["extra details"]),
    ]

    intents: list[str] = []
    contains: list[str] = []
    for needles, rule_intents, rule_contains in rules:
        if any(needle in normalized for needle in needles):
            intents.extend(rule_intents)
            contains.extend(rule_contains)

    if not intents:
        intents = ["general_reference"]
        contains = ["paper text"]

    return _dedupe(intents), _dedupe(contains)


def _clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().strip("#")).strip()


def _slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")[:64]


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def _posix(path: Path) -> str:
    return path.as_posix()
