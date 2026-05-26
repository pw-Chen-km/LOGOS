"""LOGOS 2.0 configuration.

This module keeps LOGOS independent from EvoScientist's virtual ``/skills``
mount.  It resolves EvoSkills paper-navigator from real filesystem paths only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - requirements include pyyaml
    yaml = None


LOGOS_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = LOGOS_ROOT.parent
DEFAULT_CONFIG_PATH = LOGOS_ROOT / "configs" / "logos2.yaml"


def _expand_path(value: str | Path, base_dir: Path = LOGOS_ROOT) -> Path:
    """Expand env vars/user markers and resolve relative paths from LOGOS root."""
    raw = os.path.expandvars(str(value))
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


@dataclass
class PaperNavigatorConfig:
    """Configuration for direct paper-navigator integration."""

    mode: str = "direct"
    skill_dir: Path | None = None
    scripts_dir: Path | None = None
    references_dir: Path | None = None
    papers_dir_env: str = "PAPERS_DIR"
    artifact_fallback: bool = True
    max_papers: int = 50
    citation_traversal_depth: int = 1


@dataclass
class EvoScientistBridgeConfig:
    """Optional bridge to EvoScientist's onboard/model/tool layer."""

    enabled: bool = True
    provider: str = "deepseek"
    model: str = "deepseek-v4-pro"
    use_tavily: bool = True


@dataclass
class SurveyAgentConfig:
    """Configuration for the full EvoScientist survey-agent loop."""

    enabled: bool = True
    workspace_subdir: str = "evo_survey_agent"
    artifact_filename: str = "logos_survey_artifact.json"
    timeout_seconds: int = 1800
    auto_approve: bool = True
    auto_mode: bool = True
    enable_async_subagents: bool = False
    write_reports: bool = True
    fallback_to_direct: bool = True


@dataclass
class RuntimeConfig:
    runs_dir: Path = field(default_factory=lambda: LOGOS_ROOT / "runs")
    artifacts_dir: Path = field(default_factory=lambda: LOGOS_ROOT / "artifacts")
    paper_library_dir: Path = field(default_factory=lambda: LOGOS_ROOT / "paper_library")
    paper_skills_dir: Path = field(default_factory=lambda: LOGOS_ROOT / "paper_skills")


@dataclass
class Neo4jConfig:
    uri_env: str = "NEO4J_URI"
    user_env: str = "NEO4J_USER"
    password_env: str = "NEO4J_PASSWORD"


@dataclass
class GraphConfig:
    backend: str = "sqlite"
    sqlite_path: Path = field(default_factory=lambda: LOGOS_ROOT / "graph_index.sqlite")


@dataclass
class DoclingConfig:
    enabled: bool = True
    force_reextract: bool = False


@dataclass
class LogosConfig:
    paper_navigator: PaperNavigatorConfig = field(default_factory=PaperNavigatorConfig)
    evoscientist: EvoScientistBridgeConfig = field(default_factory=EvoScientistBridgeConfig)
    survey_agent: SurveyAgentConfig = field(default_factory=SurveyAgentConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    docling: DoclingConfig = field(default_factory=DoclingConfig)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "LogosConfig":
        """Load config from YAML, then apply environment overrides."""
        path = _expand_path(config_path) if config_path else DEFAULT_CONFIG_PATH
        data: dict[str, Any] = {}

        if path.exists():
            if yaml is None:
                raise RuntimeError("pyyaml is required to load LOGOS config files")
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"LOGOS config must be a mapping: {path}")
            data = loaded

        config = cls.from_dict(data)
        env_skill_dir = os.getenv("LOGOS_PAPER_NAVIGATOR_DIR")
        if env_skill_dir:
            config.paper_navigator.skill_dir = _expand_path(env_skill_dir)
        return config

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LogosConfig":
        paper_navigator = _paper_navigator_from_dict(data.get("paper_navigator", {}))
        evoscientist = _evoscientist_from_dict(data.get("evoscientist", {}))
        survey_agent = _survey_agent_from_dict(data.get("survey_agent", {}))
        runtime = _runtime_from_dict(data.get("runtime", {}))
        graph = _graph_from_dict(data.get("graph", {}))
        neo4j = _neo4j_from_dict(data.get("neo4j", {}))
        docling = _docling_from_dict(data.get("docling", {}))
        return cls(
            paper_navigator=paper_navigator,
            evoscientist=evoscientist,
            survey_agent=survey_agent,
            runtime=runtime,
            graph=graph,
            neo4j=neo4j,
            docling=docling,
        )

    def resolve_paper_navigator_dir(self) -> Path | None:
        """Return the first installed paper-navigator directory, if any."""
        for candidate in self.paper_navigator_candidate_dirs():
            if is_paper_navigator_dir(candidate):
                return candidate
        return None

    def paper_navigator_candidate_dirs(self) -> list[Path]:
        """Filesystem-only lookup order for EvoSkills paper-navigator."""
        explicit: list[Path] = []
        if self.paper_navigator.skill_dir:
            explicit.append(self.paper_navigator.skill_dir)

        env_skill_dir = os.getenv("LOGOS_PAPER_NAVIGATOR_DIR")
        if env_skill_dir:
            explicit.append(_expand_path(env_skill_dir))

        candidates = explicit + [
            # EvoScientist workspace-local tier. Check process cwd first, then LOGOS root.
            (Path.cwd() / "skills" / "paper-navigator").resolve(),
            (LOGOS_ROOT / "skills" / "paper-navigator").resolve(),
            # Current EvoScientist global tier.
            (Path.home() / ".evoscientist" / "skills" / "paper-navigator").resolve(),
            # Legacy global tier mentioned by older docs/release notes.
            (
                Path.home()
                / ".config"
                / "evoscientist"
                / "skills"
                / "paper-navigator"
            ).resolve(),
            # Development sibling clone.
            (REPO_ROOT / "EvoSkills" / "skills" / "paper-navigator").resolve(),
        ]

        unique: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            key = str(path)
            if key not in seen:
                unique.append(path)
                seen.add(key)
        return unique


def is_paper_navigator_dir(path: Path) -> bool:
    """Check whether a directory looks like EvoSkills paper-navigator."""
    skill_md = path / "SKILL.md"
    scripts_dir = path / "scripts"
    required_scripts = [
        "scholar_search.py",
        "fetch_paper.py",
        "download_paper.py",
    ]
    return (
        path.is_dir()
        and skill_md.is_file()
        and "name: paper-navigator" in skill_md.read_text(encoding="utf-8")
        and scripts_dir.is_dir()
        and all((scripts_dir / script).is_file() for script in required_scripts)
    )


def _paper_navigator_from_dict(data: dict[str, Any]) -> PaperNavigatorConfig:
    data = data or {}
    skill_dir = data.get("skill_dir")
    scripts_dir = data.get("scripts_dir")
    references_dir = data.get("references_dir")
    return PaperNavigatorConfig(
        mode=data.get("mode", "direct"),
        skill_dir=_expand_path(skill_dir) if skill_dir else None,
        scripts_dir=_expand_path(scripts_dir) if scripts_dir else None,
        references_dir=_expand_path(references_dir) if references_dir else None,
        papers_dir_env=data.get("papers_dir_env", "PAPERS_DIR"),
        artifact_fallback=bool(data.get("artifact_fallback", True)),
        max_papers=int(data.get("max_papers", 50)),
        citation_traversal_depth=int(data.get("citation_traversal_depth", 1)),
    )


def _evoscientist_from_dict(data: dict[str, Any]) -> EvoScientistBridgeConfig:
    data = data or {}
    return EvoScientistBridgeConfig(
        enabled=bool(data.get("enabled", True)),
        provider=data.get("provider", "deepseek"),
        model=data.get("model", "deepseek-v4-pro"),
        use_tavily=bool(data.get("use_tavily", True)),
    )


def _survey_agent_from_dict(data: dict[str, Any]) -> SurveyAgentConfig:
    data = data or {}
    return SurveyAgentConfig(
        enabled=bool(data.get("enabled", True)),
        workspace_subdir=data.get("workspace_subdir", "evo_survey_agent"),
        artifact_filename=data.get("artifact_filename", "logos_survey_artifact.json"),
        timeout_seconds=int(data.get("timeout_seconds", 1800)),
        auto_approve=bool(data.get("auto_approve", True)),
        auto_mode=bool(data.get("auto_mode", True)),
        enable_async_subagents=bool(data.get("enable_async_subagents", False)),
        write_reports=bool(data.get("write_reports", True)),
        fallback_to_direct=bool(data.get("fallback_to_direct", True)),
    )


def _runtime_from_dict(data: dict[str, Any]) -> RuntimeConfig:
    data = data or {}
    return RuntimeConfig(
        runs_dir=_expand_path(data.get("runs_dir", "runs")),
        artifacts_dir=_expand_path(data.get("artifacts_dir", "artifacts")),
        paper_library_dir=_expand_path(data.get("paper_library_dir", "paper_library")),
        paper_skills_dir=_expand_path(data.get("paper_skills_dir", "paper_skills")),
    )


def _neo4j_from_dict(data: dict[str, Any]) -> Neo4jConfig:
    data = data or {}
    return Neo4jConfig(
        uri_env=data.get("uri_env", "NEO4J_URI"),
        user_env=data.get("user_env", "NEO4J_USER"),
        password_env=data.get("password_env", "NEO4J_PASSWORD"),
    )


def _graph_from_dict(data: dict[str, Any]) -> GraphConfig:
    data = data or {}
    backend = data.get("backend", "sqlite")
    sqlite_path = data.get("sqlite_path", "graph_index.sqlite")
    return GraphConfig(
        backend=backend,
        sqlite_path=_expand_path(sqlite_path),
    )


def _docling_from_dict(data: dict[str, Any]) -> DoclingConfig:
    data = data or {}
    return DoclingConfig(
        enabled=bool(data.get("enabled", True)),
        force_reextract=bool(data.get("force_reextract", False)),
    )
