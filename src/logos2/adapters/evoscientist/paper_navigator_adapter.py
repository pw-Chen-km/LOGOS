"""Direct EvoSkills paper-navigator adapter.

LOGOS uses paper-navigator as a real filesystem tool package.  It never reads
EvoScientist's virtual ``/skills`` mount and does not require entering the
EvoScientist CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib import request as urlrequest

from pydantic import BaseModel, Field

from ...config import LogosConfig
from ...schemas import PaperNavigatorReading, ResearchRequest


class DiscoveryResult(BaseModel):
    """Paper discovery 結果"""
    paper_candidates: list[dict[str, Any]] = Field(default_factory=list, description="候選論文列表")
    total_found: int = Field(default=0, description="找到的總數")
    source: str = Field(default="unknown", description="來源：external_skill | artifact")


class PaperMetadata(BaseModel):
    """Complete paper metadata from paper-navigator discovery."""

    paper_id: str = Field(..., description="論文唯一 ID")
    title: str = Field(..., description="論文標題")
    authors: list[str] = Field(default_factory=list, description="作者列表")
    year: Optional[str] = Field(None, description="發表年份")
    venue: Optional[str] = Field(None, description="發表會議/期刊")
    abstract: Optional[str] = Field(None, description="摘要")
    tldr: Optional[str] = Field(None, description="一句話摘要")
    citation_count: Optional[int] = Field(None, description="引用次數")
    doi: Optional[str] = Field(None, description="DOI")
    arxiv_id: Optional[str] = Field(None, description="arXiv ID")
    url: Optional[str] = Field(None, description="論文 URL")
    pdf_url: Optional[str] = Field(None, description="PDF 下載 URL")
    pdf_path: Optional[str] = Field(None, description="本地 PDF 路徑")
    source: str = Field("paper-navigator", description="資料來源")
    raw_data: dict[str, Any] = Field(default_factory=dict, description="原始 API 回應資料")

    def to_paper_navigator_reading(self) -> "PaperNavigatorReading":
        """將 metadata 轉為最簡 PaperNavigatorReading（metadata_only level）。"""
        return PaperNavigatorReading(
            paper_id=self.paper_id,
            reading_level="metadata_only",
            title=self.title,
            tldr=self.tldr or self.abstract or self.title,
            confidence=0.3,
            missing_fields=[
                "main_contribution",
                "problem_statement",
                "method_intuition",
                "rough_limitation",
            ],
        )


class PaperCandidate(BaseModel):
    """Normalized paper search result."""

    paper_id: str
    title: str
    year: Optional[str] = None
    venue: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    tldr: Optional[str] = None
    abstract: Optional[str] = None
    citation_count: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    pdf_path: Optional[str] = None
    source: str = "paper-navigator"

    def to_metadata(self) -> PaperMetadata:
        """轉為完整的 PaperMetadata。"""
        arxiv_id = self.arxiv_id
        if not arxiv_id and "arxiv" in self.paper_id.lower():
            arxiv_id = self.paper_id
        return PaperMetadata(
            paper_id=self.paper_id,
            title=self.title,
            authors=self.authors,
            year=self.year,
            venue=self.venue,
            abstract=self.abstract,
            tldr=self.tldr,
            citation_count=self.citation_count,
            doi=self.doi,
            arxiv_id=arxiv_id,
            pdf_path=self.pdf_path,
            source=self.source,
        )


class PdfManifestEntry(BaseModel):
    """Downloaded or cached PDF metadata."""

    paper_id: str
    pdf_path: Optional[str] = None
    status: str = "unknown"
    source: str = "paper-navigator"
    error: Optional[str] = None


class PaperNavigatorInstallReport(BaseModel):
    """Result of locating a real paper-navigator skill directory."""

    available: bool
    skill_dir: Optional[str] = None
    scripts_dir: Optional[str] = None
    references_dir: Optional[str] = None
    checked_paths: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    setup_hint: str = ""


class PaperNavigatorCommandResult(BaseModel):
    """Subprocess execution record."""

    command: list[str]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str


class PaperNavigatorRunArtifacts(BaseModel):
    """Collected artifacts for a LOGOS run."""

    paper_candidates: list[dict[str, Any]] = Field(default_factory=list)
    paper_metadata: dict[str, dict[str, Any]] = Field(default_factory=dict)
    paper_navigator_readings: list[PaperNavigatorReading] = Field(default_factory=list)
    pdf_manifest: list[PdfManifestEntry] = Field(default_factory=list)


class DirectPaperNavigatorAdapter:
    """Adapter that calls EvoSkills paper-navigator scripts directly."""

    def __init__(
        self,
        artifact_dir: Optional[str] = None,
        paper_library_dir: str = "paper_library",
        config: Optional[LogosConfig] = None,
        run_dir: Optional[str | Path] = None,
    ):
        """
        Args:
            artifact_dir: paper-navigator artifact 檔案目錄（離線 replay）
            paper_library_dir: PDF 下載/快取目錄
            config: LOGOS config with paper-navigator path resolution
            run_dir: command log and collection directory
        """
        self.config = config or LogosConfig.load()
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        self.paper_library_dir = Path(paper_library_dir)
        self.paper_library_dir.mkdir(parents=True, exist_ok=True)
        self.run_dir = Path(run_dir) if run_dir else None

        self.skill_dir = self.config.resolve_paper_navigator_dir()
        self.scripts_dir = (
            self.config.paper_navigator.scripts_dir
            or (self.skill_dir / "scripts" if self.skill_dir else None)
        )
        self.references_dir = (
            self.config.paper_navigator.references_dir
            or (self.skill_dir / "references" if self.skill_dir else None)
        )

    def validate_installation(self) -> PaperNavigatorInstallReport:
        """Validate that a real paper-navigator directory is available."""
        checked_paths = [str(p) for p in self.config.paper_navigator_candidate_dirs()]
        skill_dir = self.config.resolve_paper_navigator_dir()
        if not skill_dir:
            return PaperNavigatorInstallReport(
                available=False,
                checked_paths=checked_paths,
                missing=["paper-navigator skill directory"],
                setup_hint=_setup_hint(),
            )

        missing = []
        scripts_dir = self.config.paper_navigator.scripts_dir or (skill_dir / "scripts")
        references_dir = self.config.paper_navigator.references_dir or (skill_dir / "references")
        for rel in [
            "SKILL.md",
            "scripts/scholar_search.py",
            "scripts/fetch_paper.py",
            "scripts/download_paper.py",
        ]:
            if not (skill_dir / rel).exists():
                missing.append(rel)

        available = not missing
        return PaperNavigatorInstallReport(
            available=available,
            skill_dir=str(skill_dir),
            scripts_dir=str(scripts_dir),
            references_dir=str(references_dir),
            checked_paths=checked_paths,
            missing=missing,
            setup_hint="" if available else _setup_hint(),
        )

    def build_queries(self, request: ResearchRequest) -> list[str]:
        """Build paper-navigator search queries from a ResearchRequest."""
        queries = []
        if request.topic_keywords:
            queries.append(" ".join(request.topic_keywords[:5]))
        if request.research_goal:
            queries.append(request.research_goal)
        for seed in request.seed_papers:
            queries.append(seed)
        return _dedupe([q.strip() for q in queries if q and q.strip()])

    def discover(self, request: ResearchRequest) -> DiscoveryResult:
        """根據 ResearchRequest 發現候選論文

        Direct mode:
        - 若 paper-navigator 已安裝，直接呼叫 scholar_search.py
        - 若未安裝且 artifact_fallback 開啟，從 artifact replay

        Args:
            request: 研究請求

        Returns:
            DiscoveryResult: 候選論文列表

        Raises:
            FileNotFoundError: 若無法找到 skill 或 discovery artifact
        """
        report = self.validate_installation()
        if report.available:
            candidates: list[dict[str, Any]] = []
            limit = min(request.paper_count_target, self.config.paper_navigator.max_papers)
            for query in self.build_queries(request):
                candidates.extend(
                    candidate.model_dump()
                    for candidate in self.run_keyword_search(query, limit=limit)
                )
            candidates = _dedupe_candidates(candidates)
            return DiscoveryResult(
                paper_candidates=candidates,
                total_found=len(candidates),
                source="external_skill",
            )

        if self.config.paper_navigator.artifact_fallback:
            artifact_result = self._load_discovery_artifact()
            if artifact_result:
                return artifact_result

        raise FileNotFoundError(
            "paper-navigator is not installed and no discovery artifact was found.\n"
            + report.setup_hint
        )

    def run_keyword_search(self, query: str, limit: int) -> list[PaperCandidate]:
        """Run paper-navigator scholar_search.py and normalize candidates."""
        payload = self._run_script(
            "scholar_search.py",
            ["--query", query, "--limit", str(limit), "--json"],
        )
        return [_candidate_from_raw(item) for item in _items_from_json(payload)]

    def search_local_library(self, query: str, limit: int = 10) -> list[PaperCandidate]:
        """Search the local PDF library before spending network/API budget."""
        payload = self._run_script(
            "library_search.py",
            ["--query", query, "--limit", str(limit), "--json"],
        )
        return [_candidate_from_raw(item) for item in _items_from_json(payload)]

    def run_arxiv_monitor(self, keywords: str, days: int) -> list[PaperCandidate]:
        """Run paper-navigator arxiv_monitor.py when available."""
        payload = self._run_script(
            "arxiv_monitor.py",
            [
                "--keywords",
                keywords,
                "--days",
                str(days),
                "--limit",
                str(self.config.paper_navigator.max_papers),
                "--match-mode",
                "flexible",
                "--json",
            ],
        )
        return [_candidate_from_raw(item) for item in _items_from_json(payload)]

    def run_citation_traversal(
        self,
        seed_id: str,
        direction: str = "co-citation",
        limit: int = 15,
    ) -> list[PaperCandidate]:
        """Run paper-navigator citation_traverse.py when available."""
        payload = self._run_script(
            "citation_traverse.py",
            [
                "--paper-id",
                seed_id,
                "--direction",
                direction,
                "--limit",
                str(limit),
                "--json",
            ],
        )
        return [_candidate_from_raw(item) for item in _items_from_json(payload)]

    def run_recommendations(
        self,
        positive_ids: list[str],
        limit: int = 15,
        negative_ids: Optional[list[str]] = None,
    ) -> list[PaperCandidate]:
        """Run paper-navigator recommend.py for seed-based similar papers."""
        args = ["--positive", ",".join(positive_ids), "--limit", str(limit), "--json"]
        if negative_ids:
            args.extend(["--negative", ",".join(negative_ids)])
        payload = self._run_script("recommend.py", args)
        return [_candidate_from_raw(item) for item in _items_from_json(payload)]

    def run_trending(self, query: str, period_days: int = 180, limit: int = 20) -> list[PaperCandidate]:
        """Run paper-navigator trending.py for recent high-velocity papers."""
        payload = self._run_script(
            "trending.py",
            [
                "--query",
                query,
                "--period",
                str(period_days),
                "--limit",
                str(limit),
                "--json",
            ],
        )
        return [_candidate_from_raw(item) for item in _items_from_json(payload)]

    def run_author_search(self, author_name: str, limit: int = 20) -> list[PaperCandidate]:
        """Run paper-navigator author_search.py for author/year metadata lookups."""
        payload = self._run_script(
            "author_search.py",
            ["--name", author_name, "--papers", "--limit", str(limit), "--json"],
        )
        return [_candidate_from_raw(item) for item in _items_from_json(payload)]

    def find_code(self, candidate: PaperCandidate, limit: int = 5) -> list[dict[str, Any]]:
        """Find official or high-star code repositories for a candidate paper."""
        args = ["--limit", str(limit), "--json"]
        if candidate.arxiv_id:
            args.extend(["--arxiv-id", candidate.arxiv_id])
        else:
            args.extend(["--title", candidate.title])
        payload = self._run_script("find_code.py", args)
        return _items_from_json(payload)

    def search_sota(self, task: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search HuggingFace models for SOTA/baseline hints."""
        payload = self._run_script(
            "sota.py",
            ["--task", task, "--limit", str(limit), "--json"],
        )
        return _items_from_json(payload)

    def run_tavily_search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search the web through Tavily when TAVILY_API_KEY is configured."""
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return []

        body = json.dumps(
            {
                "api_key": api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": limit,
                "include_answer": True,
            }
        ).encode("utf-8")
        req = urlrequest.Request(
            "https://api.tavily.com/search",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        results = payload.get("results") or []
        if payload.get("answer"):
            results.insert(
                0,
                {
                    "title": "Tavily synthesized answer",
                    "url": "",
                    "content": payload["answer"],
                    "source": "tavily",
                },
            )
        return results[:limit]

    def fetch_or_download_pdf(self, paper_id: str) -> PdfManifestEntry:
        """Fetch a paper into the local paper library."""
        try:
            result = self._run_script(
                "download_paper.py",
                ["--paper-id", paper_id],
                parse_json=False,
            )
            return PdfManifestEntry(
                paper_id=paper_id,
                status="completed",
                pdf_path=_extract_pdf_path(result.stdout),
            )
        except Exception as exc:
            return PdfManifestEntry(
                paper_id=paper_id,
                status="failed",
                error=str(exc),
            )

    def read(
        self,
        paper_id: str,
        reading_level: str = "L2",
        pdf_path: Optional[str] = None
    ) -> PaperNavigatorReading:
        """對單篇論文執行指定深度的閱讀
        
        Direct mode uses fetch_paper.py for the raw reading payload and maps
        available fields into LOGOS's stable PaperNavigatorReading schema.

        Args:
            paper_id: 論文 ID
            reading_level: 閱讀深度 (L1 | L2 | L3 | metadata_only)
            pdf_path: PDF 檔案路徑（可選，未來版本使用）

        Returns:
            PaperNavigatorReading: 結構化閱讀輸出

        Raises:
            FileNotFoundError: 若無法找到 reading artifact
        """
        artifact = self._load_single_reading_artifact(paper_id)
        if artifact:
            return artifact

        report = self.validate_installation()
        if not report.available:
            raise FileNotFoundError(
                f"Reading artifact not found for paper {paper_id}, "
                "and paper-navigator is not installed.\n"
                + report.setup_hint
            )

        args = ["--cache", "--paper-id", paper_id]
        payload = self._run_script("fetch_paper.py", args, parse_json=False)
        text = payload.stdout.strip()
        title = _extract_markdown_title(text) or paper_id
        tldr = _extract_first_paragraph(text) or paper_id
        extracted = _extract_reading_fields(text)
        return PaperNavigatorReading(
            paper_id=paper_id,
            reading_level=reading_level,
            title=title,
            tldr=tldr[:500],
            main_contribution=extracted.get("main_contribution"),
            problem_statement=extracted.get("problem_statement"),
            method_intuition=extracted.get("method_intuition"),
            rough_limitation=extracted.get("rough_limitation"),
            confidence=0.65 if reading_level in {"L1", "L2"} else 0.45,
            missing_fields=_missing_fields_for_level(reading_level, extracted),
        )

    def save_artifacts(
        self,
        run_dir: Path,
        candidates: list[PaperCandidate],
        metadata_map: dict[str, PaperMetadata],
        readings: list[PaperNavigatorReading],
        pdf_manifest: list[PdfManifestEntry],
    ) -> None:
        """Save paper-navigator artifacts to run directory.

        Args:
            run_dir: Run directory path
            candidates: Paper candidates from discovery
            metadata_map: Paper ID -> metadata mapping
            readings: Paper navigator readings
            pdf_manifest: PDF download manifest
        """
        base = run_dir / "paper_navigator"
        base.mkdir(parents=True, exist_ok=True)

        # Save candidates
        (base / "paper_candidates.json").write_text(
            json.dumps([c.model_dump() for c in candidates], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Save metadata
        (base / "paper_metadata.json").write_text(
            json.dumps(
                {pid: m.model_dump() for pid, m in metadata_map.items()},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # Save readings
        (base / "paper_navigator_readings.json").write_text(
            json.dumps([r.model_dump() for r in readings], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Save PDF manifest
        (base / "pdf_manifest.json").write_text(
            json.dumps([p.model_dump() for p in pdf_manifest], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def collect_run_artifacts(self, run_dir: Path) -> PaperNavigatorRunArtifacts:
        """Load normalized paper-navigator artifacts from a run directory."""
        base = run_dir / "paper_navigator"
        readings: list[PaperNavigatorReading] = []
        readings_file = base / "paper_navigator_readings.json"
        if readings_file.exists():
            data = json.loads(readings_file.read_text(encoding="utf-8"))
            readings = [PaperNavigatorReading(**item) for item in data]

        candidates = _load_json_if_exists(base / "paper_candidates.json", [])
        metadata = _load_json_if_exists(base / "paper_metadata.json", {})
        pdf_items = _load_json_if_exists(base / "pdf_manifest.json", [])
        return PaperNavigatorRunArtifacts(
            paper_candidates=candidates,
            paper_metadata=metadata,
            paper_navigator_readings=readings,
            pdf_manifest=[PdfManifestEntry(**item) for item in pdf_items],
        )

    def load_artifacts(self, artifact_file: str) -> list[PaperNavigatorReading]:
        """批次載入 paper-navigator reading artifacts

        從單一 JSON 檔案或目錄載入多篇論文的 reading outputs。

        Args:
            artifact_file: artifact 檔案路徑或目錄路徑

        Returns:
            list[PaperNavigatorReading]: 所有 reading artifacts
        """
        artifact_path = Path(artifact_file)

        if artifact_path.is_file():
            # 單一檔案：可能是批次檔案或單篇檔案
            with open(artifact_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 檢查是否為批次檔案
            if isinstance(data, list):
                return [PaperNavigatorReading(**item) for item in data]
            return [PaperNavigatorReading(**data)]

        if artifact_path.is_dir():
            readings: list[PaperNavigatorReading] = []
            for pattern in ["*_reading.json", "paper_navigator_reading.json", "paper_navigator_readings.json"]:
                for file_path in artifact_path.glob(pattern):
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        readings.extend(PaperNavigatorReading(**item) for item in data)
                    else:
                        readings.append(PaperNavigatorReading(**data))
            batch_file = artifact_path / "paper_navigator" / "paper_navigator_readings.json"
            if batch_file.exists():
                with open(batch_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                readings.extend(PaperNavigatorReading(**item) for item in data)
            return readings

        raise FileNotFoundError(f"Artifact path not found: {artifact_file}")

    def get_reading_policy(self, paper_importance: str) -> str:
        """根據論文重要性取得建議閱讀深度

        Reading level policy:
        - Core papers: L1 or L2+ reading
        - Important related papers: L2 reading
        - Background papers: L3 reading
        - Peripheral papers: metadata_only

        Args:
            paper_importance: 論文重要性 (core | important | background | peripheral)

        Returns:
            str: 建議閱讀深度
        """
        policy_map = {
            "core": "L1",
            "important": "L2",
            "background": "L3",
            "peripheral": "metadata_only"
        }
        return policy_map.get(paper_importance, "L2")

    def check_external_skill_available(self) -> bool:
        """檢查外部 EvoSkills paper-navigator 是否可用

        Returns:
            bool: True 若外部技能可用
        """
        return self.validate_installation().available

    def _run_script(
        self,
        script_name: str,
        args: list[str],
        parse_json: bool = True,
    ) -> Any:
        report = self.validate_installation()
        if not report.available or not self.scripts_dir:
            raise FileNotFoundError(report.setup_hint)

        script_path = self.scripts_dir / script_name
        if not script_path.exists():
            raise FileNotFoundError(f"paper-navigator script not found: {script_path}")

        command = [sys.executable, str(script_path), *args]
        env = {
            **dict(os.environ),
            self.config.paper_navigator.papers_dir_env: str(self.paper_library_dir),
        }
        completed = subprocess.run(
            command,
            cwd=str(self.skill_dir),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        result = PaperNavigatorCommandResult(
            command=command,
            cwd=str(self.skill_dir),
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        self._log_command(result)
        if completed.returncode != 0:
            raise RuntimeError(
                f"paper-navigator command failed ({completed.returncode}): "
                f"{script_name}\n{completed.stderr}"
            )
        if not parse_json:
            return result
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"paper-navigator script did not return JSON: {script_name}"
            ) from exc

    def _log_command(self, result: PaperNavigatorCommandResult) -> None:
        if not self.run_dir:
            return
        log_dir = self.run_dir / "paper_navigator"
        log_dir.mkdir(parents=True, exist_ok=True)
        entry = result.model_dump()
        entry["timestamp"] = datetime.utcnow().isoformat() + "Z"
        with open(log_dir / "commands.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _load_discovery_artifact(self) -> Optional[DiscoveryResult]:
        if not self.artifact_dir:
            return None
        for filename in ["discovery_result.json", "paper_candidates.json"]:
            discovery_file = self.artifact_dir / filename
            if discovery_file.exists():
                data = json.loads(discovery_file.read_text(encoding="utf-8"))
                candidates = data.get("candidates", data) if isinstance(data, dict) else data
                return DiscoveryResult(
                    paper_candidates=candidates,
                    total_found=len(candidates),
                    source="artifact",
                )
        nested = self.artifact_dir / "paper_navigator" / "paper_candidates.json"
        if nested.exists():
            candidates = json.loads(nested.read_text(encoding="utf-8"))
            return DiscoveryResult(
                paper_candidates=candidates,
                total_found=len(candidates),
                source="artifact",
            )
        return None

    def _load_single_reading_artifact(self, paper_id: str) -> Optional[PaperNavigatorReading]:
        if not self.artifact_dir:
            return None

        safe_ids = {
            paper_id.replace(":", "_").replace("/", "_"),
            paper_id.replace(":", "_"),
            paper_id.replace("/", "_"),
        }
        for safe_id in safe_ids:
            reading_file = self.artifact_dir / f"{safe_id}_reading.json"
            if reading_file.exists():
                return PaperNavigatorReading(
                    **json.loads(reading_file.read_text(encoding="utf-8"))
                )
        return None


def _normalize_authors(authors: Any) -> list[str]:
    if not authors:
        return []
    if isinstance(authors, str):
        return [a.strip() for a in authors.split(",") if a.strip()]
    if not isinstance(authors, list):
        return []
    normalized: list[str] = []
    for author in authors:
        if isinstance(author, str) and author.strip():
            normalized.append(author.strip())
        elif isinstance(author, dict):
            name = author.get("name") or author.get("author")
            if name:
                normalized.append(str(name).strip())
    return normalized


def _extract_tldr(raw: dict[str, Any]) -> Optional[str]:
    tldr = raw.get("tldr") or raw.get("TLDR")
    if isinstance(tldr, dict):
        return tldr.get("text") or tldr.get("model")
    if tldr is not None:
        return str(tldr)
    return None


def _candidate_from_raw(raw: dict[str, Any]) -> PaperCandidate:
    external_ids = raw.get("externalIds") or {}
    arxiv_from_external = None
    if isinstance(external_ids, dict):
        arxiv_from_external = external_ids.get("ArXiv") or external_ids.get("arXiv")
    arxiv_id = raw.get("arxiv_id") or raw.get("arxivId") or arxiv_from_external

    paper_id = (
        raw.get("paper_id")
        or raw.get("paperId")
        or raw.get("id")
        or raw.get("key")
        or (f"arxiv:{arxiv_id}" if arxiv_id else None)
        or raw.get("doi")
        or raw.get("url")
        or raw.get("title")
    )
    venue = raw.get("venue") or raw.get("publicationVenue") or raw.get("source")
    if isinstance(venue, dict):
        venue = venue.get("name") or venue.get("id")

    return PaperCandidate(
        paper_id=str(paper_id),
        title=str(raw.get("title") or paper_id),
        year=str(raw["year"]) if raw.get("year") is not None else None,
        venue=str(venue) if venue is not None else None,
        authors=_normalize_authors(raw.get("authors")),
        tldr=_extract_tldr(raw),
        abstract=raw.get("abstract") or raw.get("summary") or raw.get("content"),
        citation_count=raw.get("citation_count") or raw.get("citationCount") or raw.get("citations"),
        doi=raw.get("doi") or (external_ids.get("DOI") if isinstance(external_ids, dict) else None),
        arxiv_id=arxiv_id,
        pdf_path=raw.get("pdf_path") or raw.get("path"),
        source=raw.get("source", "paper-navigator"),
    )


def _items_from_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ["papers", "results", "candidates", "data"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _dedupe(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for candidate in candidates:
        key = candidate.get("paper_id") or candidate.get("title")
        if key and key not in seen:
            result.append(candidate)
            seen.add(key)
    return result


def _extract_pdf_path(stdout: str) -> Optional[str]:
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.lower().endswith(".pdf"):
            return stripped
    return None


def _load_json_if_exists(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_markdown_title(text: str) -> Optional[str]:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
        if stripped.lower().startswith("title:"):
            return stripped.split(":", 1)[1].strip()
    return None


def _extract_first_paragraph(text: str) -> Optional[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    for paragraph in paragraphs:
        lowered = paragraph.lower()
        if paragraph.startswith("#") or lowered.startswith(("title:", "url:", "authors:")):
            continue
        return " ".join(paragraph.split())
    return None


def _extract_section_like(text: str, keywords: tuple[str, ...], max_chars: int = 900) -> Optional[str]:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        lowered = line.lower()
        if not any(keyword in lowered for keyword in keywords):
            continue
        chunk: list[str] = []
        for follow in lines[idx + 1 : idx + 20]:
            if follow.startswith("#") and chunk:
                break
            if follow.strip():
                chunk.append(follow.strip())
            if sum(len(part) for part in chunk) >= max_chars:
                break
        if chunk:
            return " ".join(chunk)[:max_chars]
    return None


def _extract_reading_fields(text: str) -> dict[str, Optional[str]]:
    return {
        "problem_statement": _extract_section_like(
            text, ("problem", "motivation", "introduction", "challenge")
        ),
        "main_contribution": _extract_section_like(
            text, ("contribution", "propose", "abstract", "summary")
        ),
        "method_intuition": _extract_section_like(
            text, ("method", "approach", "framework", "model")
        ),
        "rough_limitation": _extract_section_like(
            text, ("limitation", "discussion", "future work")
        ),
    }


def _missing_fields_for_level(reading_level: str, fields: dict[str, Optional[str]]) -> list[str]:
    expected_by_level = {
        "L1": ["main_contribution", "problem_statement", "method_intuition", "rough_limitation"],
        "L2": ["main_contribution", "problem_statement", "method_intuition", "rough_limitation"],
        "L3": ["main_contribution", "problem_statement"],
        "metadata_only": [],
    }
    return [field for field in expected_by_level.get(reading_level, []) if not fields.get(field)]


def _setup_hint() -> str:
    return (
        "paper-navigator not found. Install it without entering EvoScientist CLI:\n"
        "  python -m logos2.cli.main setup-paper-navigator --global\n"
        "or install it in EvoScientist CLI:\n"
        "  /install-skill EvoScientist/EvoSkills@skills/paper-navigator\n"
        "or set LOGOS_PAPER_NAVIGATOR_DIR / paper_navigator.skill_dir."
    )


# Backward-compatible name used by existing workflow imports.
PaperNavigatorAdapter = DirectPaperNavigatorAdapter
