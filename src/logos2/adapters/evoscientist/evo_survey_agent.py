"""Full EvoScientist survey-agent adapter for LOGOS.

This adapter runs the complete EvoScientist agent loop in-process and asks it
to produce a stable JSON artifact that LOGOS can normalize into its existing
paper/profile/graph pipeline.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...config import LOGOS_ROOT, REPO_ROOT, LogosConfig
from ...schemas import PaperNavigatorReading, ResearchRequest, SurveyTaxonomy
from .paper_navigator_adapter import PaperCandidate, PaperMetadata, PdfManifestEntry


ARTIFACT_VERSION = "logos-evo-survey-agent-v1"


@dataclass
class EvoSurveyAgentResult:
    """Normalized output from the full EvoScientist survey loop."""

    paper_candidates: list[PaperCandidate]
    metadata_map: dict[str, PaperMetadata]
    readings: list[PaperNavigatorReading]
    survey_taxonomy: SurveyTaxonomy | None = None
    pdf_manifest: list[PdfManifestEntry] = field(default_factory=list)
    web_findings: list[dict[str, Any]] = field(default_factory=list)
    report_paths: dict[str, str] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)
    thread_id: str | None = None
    final_response: str = ""


class EvoSurveyAgentAdapter:
    """Run EvoScientist's complete agent loop for survey generation."""

    def __init__(
        self,
        config: LogosConfig | None = None,
        run_dir: str | Path | None = None,
    ):
        self.config = config or LogosConfig.load()
        self.run_dir = Path(run_dir) if run_dir else self.config.runtime.runs_dir / "unknown"
        self.workspace_dir = self.run_dir / self.config.survey_agent.workspace_subdir
        self.artifact_path = self.workspace_dir / self.config.survey_agent.artifact_filename

    def run(self, request: ResearchRequest) -> EvoSurveyAgentResult:
        """Run the full EvoScientist loop and parse its JSON artifact."""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        prompt = self._build_prompt(request)
        (self.workspace_dir / "survey_agent_prompt.md").write_text(prompt, encoding="utf-8")

        final_response, thread_id, events = _run_async(
            self._run_agent(prompt),
            timeout_seconds=self.config.survey_agent.timeout_seconds,
        )
        (self.workspace_dir / "survey_agent_events.json").write_text(
            json.dumps(events, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.workspace_dir / "survey_agent_final_response.md").write_text(
            final_response,
            encoding="utf-8",
        )

        parsed = parse_survey_artifact(
            self.artifact_path,
            request_id=request.request_id,
            workspace_dir=self.workspace_dir,
        )
        parsed.thread_id = thread_id
        parsed.final_response = final_response
        parsed.trace.update(
            {
                "mode": "SURVEY_AGENT",
                "source": "evoscientist_full_loop",
                "thread_id": thread_id,
                "workspace_dir": str(self.workspace_dir),
                "artifact_path": str(self.artifact_path),
                "events_path": str(self.workspace_dir / "survey_agent_events.json"),
                "final_response_path": str(
                    self.workspace_dir / "survey_agent_final_response.md"
                ),
            }
        )
        return parsed

    async def _run_agent(self, prompt: str) -> tuple[str, str, list[dict[str, Any]]]:
        self._ensure_evo_on_path()

        from EvoScientist import create_cli_agent
        from EvoScientist.config import apply_config_to_env, get_effective_config
        from EvoScientist.sessions import generate_thread_id
        from EvoScientist.stream.events import stream_agent_events

        evo_config = get_effective_config(
            {
                "provider": self.config.evoscientist.provider,
                "model": self.config.evoscientist.model,
                "auto_approve": self.config.survey_agent.auto_approve,
                "auto_mode": self.config.survey_agent.auto_mode,
                "enable_async_subagents": self.config.survey_agent.enable_async_subagents,
                "default_workdir": str(self.workspace_dir),
            }
        )
        apply_config_to_env(evo_config)
        _prime_skill_environment(self.config)

        agent = create_cli_agent(
            workspace_dir=str(self.workspace_dir),
            config=evo_config,
        )
        thread_id = generate_thread_id()
        events: list[dict[str, Any]] = []
        final_response = ""
        async for event in stream_agent_events(
            agent,
            prompt,
            thread_id,
            metadata={
                "agent_name": "logos-evo-survey-agent",
                "request_id": self.run_dir.name,
            },
        ):
            serializable = _json_safe(event)
            events.append(serializable)
            if event.get("type") == "done":
                final_response = str(event.get("content") or event.get("full_response") or "")
            elif event.get("event") == "done":
                final_response = str(event.get("content") or event.get("full_response") or "")
        return final_response, thread_id, events

    def _build_prompt(self, request: ResearchRequest) -> str:
        target = min(request.paper_count_target, self.config.paper_navigator.max_papers)
        artifact_name = self.config.survey_agent.artifact_filename
        report_instruction = ""
        if self.config.survey_agent.write_reports:
            report_instruction = (
                "- Write `survey_report_en.md` and `survey_report_zh.md` in the current workspace.\n"
            )

        schema = {
            "artifact_version": ARTIFACT_VERSION,
            "research_goal": request.research_goal,
            "papers": [
                {
                    "paper_id": "arxiv:0000.00000",
                    "title": "Paper title",
                    "authors": ["Author"],
                    "year": "2025",
                    "venue": "arXiv",
                    "abstract": "Abstract text",
                    "tldr": "One sentence summary",
                    "main_contribution": "Main contribution",
                    "problem_statement": "Problem addressed",
                    "method_intuition": "High-level method",
                    "design_rationale": "Why this design",
                    "tradeoffs": "Tradeoffs",
                    "rough_limitation": "Limitations",
                    "benchmark_names": ["HotpotQA"],
                    "dataset_names": ["Wikipedia"],
                    "baseline_names": ["BM25"],
                    "url": "https://arxiv.org/abs/0000.00000",
                    "pdf_url": "https://arxiv.org/pdf/0000.00000",
                    "citation_count": 0,
                }
            ],
            "taxonomy": {
                "themes": [
                    {
                        "theme_id": "T1",
                        "name": "Theme name",
                        "description": "Theme description",
                        "keywords": ["keyword"],
                    }
                ],
                "subthemes": [],
                "paper_assignments": [
                    {"paper_id": "arxiv:0000.00000", "theme_id": "T1", "confidence": 0.9}
                ],
                "method_families": [
                    {
                        "family_id": "MF1",
                        "name": "Method family",
                        "description": "Description",
                        "representative_papers": ["arxiv:0000.00000"],
                    }
                ],
                "problem_clusters": [],
                "benchmark_matrix": [],
                "dataset_matrix": [],
                "baseline_matrix": [],
                "candidate_relations": [],
            },
            "web_findings": [],
            "survey_reports": {
                "en": "survey_report_en.md",
                "zh": "survey_report_zh.md",
            },
        }

        return f"""Use the `/skills/paper-navigator` skill to run a complete systematic literature survey.

Research goal:
{request.research_goal}

Target paper count: {target}
Topic keywords: {", ".join(request.topic_keywords) if request.topic_keywords else "(infer from goal)"}
Time range: {request.time_range or "(none)"}

Required workflow:
1. Decompose the topic into search angles.
2. Discover papers with arXiv/Semantic Scholar and citation traversal.
3. Read the selected papers with structured evaluation.
4. Build a thematic taxonomy, method families, problem clusters, benchmark/dataset/baseline matrices, and candidate paper relations.
5. Draft a survey synthesis with grounded citations.

Required outputs:
- Write `{artifact_name}` in the current workspace.
{report_instruction}- Do not finish until `{artifact_name}` exists and contains valid JSON.
- The JSON must follow this shape. Keep the exact top-level keys and fill unknown list fields with []:

```json
{json.dumps(schema, indent=2, ensure_ascii=False)}
```

Rules:
- Use stable paper IDs when possible, preferably `arxiv:<id>` or Semantic Scholar paper IDs.
- Do not invent citations, benchmark names, datasets, or paper metadata.
- Include only papers you actually discovered/read.
- Keep the artifact machine-readable JSON only; no markdown fences inside the file.
"""

    def _ensure_evo_on_path(self) -> None:
        repo_root = str(Path(REPO_ROOT).resolve())
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)


def parse_survey_artifact(
    artifact_path: str | Path,
    request_id: str,
    workspace_dir: str | Path | None = None,
) -> EvoSurveyAgentResult:
    """Parse `logos_survey_artifact.json` into LOGOS schema objects."""
    path = Path(artifact_path)
    if not path.exists():
        raise FileNotFoundError(f"EvoScientist survey artifact not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("EvoScientist survey artifact must be a JSON object")

    papers = data.get("papers") or data.get("paper_readings") or []
    if not isinstance(papers, list):
        raise ValueError("EvoScientist survey artifact field `papers` must be a list")

    candidates: list[PaperCandidate] = []
    metadata_map: dict[str, PaperMetadata] = {}
    readings: list[PaperNavigatorReading] = []
    pdf_manifest: list[PdfManifestEntry] = []

    for index, raw in enumerate(papers):
        if not isinstance(raw, dict):
            continue
        candidate, metadata, reading, pdf_entry = _paper_from_artifact(raw, index)
        candidates.append(candidate)
        metadata_map[metadata.paper_id] = metadata
        readings.append(reading)
        if pdf_entry:
            pdf_manifest.append(pdf_entry)

    taxonomy = _taxonomy_from_artifact(data.get("taxonomy"), request_id)
    report_paths = _report_paths_from_artifact(data, workspace_dir)
    web_findings = data.get("web_findings") if isinstance(data.get("web_findings"), list) else []
    trace = {
        "mode": "SURVEY_AGENT",
        "artifact_version": data.get("artifact_version", ""),
        "taxonomy_source": "evoscientist_survey_agent" if taxonomy else "",
        "paper_count": len(readings),
        "report_paths": report_paths,
    }

    return EvoSurveyAgentResult(
        paper_candidates=candidates,
        metadata_map=metadata_map,
        readings=readings,
        survey_taxonomy=taxonomy,
        pdf_manifest=pdf_manifest,
        web_findings=[item for item in web_findings if isinstance(item, dict)],
        report_paths=report_paths,
        trace=trace,
    )


def _paper_from_artifact(
    raw: dict[str, Any],
    index: int,
) -> tuple[PaperCandidate, PaperMetadata, PaperNavigatorReading, PdfManifestEntry | None]:
    paper_id = _paper_id(raw, index)
    title = str(raw.get("title") or paper_id)
    authors = _string_list(raw.get("authors"))
    year = _optional_str(raw.get("year"))
    venue = _optional_str(raw.get("venue"))
    abstract = _optional_str(raw.get("abstract"))
    tldr = _optional_str(raw.get("tldr") or raw.get("summary")) or title
    citation_count = _optional_int(raw.get("citation_count") or raw.get("citationCount"))
    arxiv_id = _optional_str(raw.get("arxiv_id") or raw.get("arxivId"))
    doi = _optional_str(raw.get("doi"))
    pdf_url = _optional_str(raw.get("pdf_url") or raw.get("pdfUrl"))
    url = _optional_str(raw.get("url"))
    pdf_path = _optional_str(raw.get("pdf_path") or raw.get("pdfPath"))

    candidate = PaperCandidate(
        paper_id=paper_id,
        title=title,
        year=year,
        venue=venue,
        authors=authors,
        tldr=tldr,
        abstract=abstract,
        citation_count=citation_count,
        doi=doi,
        arxiv_id=arxiv_id,
        pdf_path=pdf_path,
        source="evoscientist_survey_agent",
    )
    metadata = candidate.to_metadata()
    metadata.url = url
    metadata.pdf_url = pdf_url
    metadata.raw_data = raw

    reading_fields = raw.get("reading") if isinstance(raw.get("reading"), dict) else raw
    reading_level = str(reading_fields.get("reading_level") or "L2")
    if reading_level not in {"L1", "L2", "L3", "metadata_only"}:
        reading_level = "L2"
    reading = PaperNavigatorReading(
        paper_id=paper_id,
        reading_level=reading_level,
        title=title,
        tldr=tldr[:500],
        main_contribution=_optional_str(reading_fields.get("main_contribution")),
        problem_statement=_optional_str(reading_fields.get("problem_statement")),
        method_intuition=_optional_str(reading_fields.get("method_intuition")),
        design_rationale=_optional_str(reading_fields.get("design_rationale")),
        tradeoffs=_optional_str(reading_fields.get("tradeoffs")),
        rough_limitation=_optional_str(
            reading_fields.get("rough_limitation") or reading_fields.get("limitations")
        ),
        benchmark_names=_string_list(reading_fields.get("benchmark_names")),
        dataset_names=_string_list(reading_fields.get("dataset_names")),
        baseline_names=_string_list(reading_fields.get("baseline_names")),
        mentioned_figures=_string_list(reading_fields.get("mentioned_figures")),
        mentioned_tables=_string_list(reading_fields.get("mentioned_tables")),
        confidence=float(reading_fields.get("confidence") or 0.75),
        missing_fields=_missing_fields(reading_fields),
    )

    pdf_entry = None
    if pdf_path or pdf_url:
        pdf_entry = PdfManifestEntry(
            paper_id=paper_id,
            pdf_path=pdf_path,
            status="available" if pdf_path else "remote_only",
            source=pdf_url or "evoscientist_survey_agent",
        )
    return candidate, metadata, reading, pdf_entry


def _taxonomy_from_artifact(raw: Any, request_id: str) -> SurveyTaxonomy | None:
    if not isinstance(raw, dict):
        return None
    payload = dict(raw)
    payload.setdefault("taxonomy_id", f"evo_tax_{request_id}")
    payload.setdefault("request_id", request_id)
    for key in (
        "themes",
        "subthemes",
        "paper_assignments",
        "method_families",
        "problem_clusters",
        "benchmark_matrix",
        "dataset_matrix",
        "baseline_matrix",
        "candidate_relations",
    ):
        payload.setdefault(key, [])
    return SurveyTaxonomy(**payload)


def _report_paths_from_artifact(
    data: dict[str, Any],
    workspace_dir: str | Path | None,
) -> dict[str, str]:
    reports = data.get("survey_reports") or data.get("reports") or {}
    if not isinstance(reports, dict):
        return {}
    base = Path(workspace_dir) if workspace_dir else None
    out: dict[str, str] = {}
    for key, value in reports.items():
        if not value:
            continue
        path = Path(str(value))
        if base and not path.is_absolute():
            path = base / path
        out[str(key)] = str(path)
    return out


def _paper_id(raw: dict[str, Any], index: int) -> str:
    for key in ("paper_id", "paperId", "id"):
        value = raw.get(key)
        if value:
            return str(value)
    arxiv_id = raw.get("arxiv_id") or raw.get("arxivId")
    if arxiv_id:
        value = str(arxiv_id)
        return value if value.startswith("arxiv:") else f"arxiv:{value}"
    title = str(raw.get("title") or f"paper-{index + 1}")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48]
    return f"evo:{slug or index + 1}"


def _missing_fields(fields: dict[str, Any]) -> list[str]:
    required = [
        "main_contribution",
        "problem_statement",
        "method_intuition",
        "rough_limitation",
    ]
    return [name for name in required if not fields.get(name)]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("name") or item.get("title") or item.get("text")
            else:
                text = item
            if text is not None and str(text).strip():
                out.append(str(text).strip())
        return out
    return [str(value)]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _prime_skill_environment(config: LogosConfig) -> None:
    """Expose LOGOS-local paper-navigator as EvoScientist workspace skill."""
    skill_dir = config.resolve_paper_navigator_dir()
    if skill_dir and skill_dir.parent:
        os.environ.setdefault("EVOSCIENTIST_SKILLS_DIR", str(skill_dir.parent))
    os.environ.setdefault("PAPERS_DIR", str(config.runtime.paper_library_dir))


def _run_async(coro, timeout_seconds: int) -> Any:
    async def _with_timeout():
        return await asyncio.wait_for(coro, timeout=timeout_seconds)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_with_timeout())

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_with_timeout())
    finally:
        loop.close()


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_json_safe(item) for item in value]
        return str(value)
