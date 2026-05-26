"""Minimal EvoScientist runtime bridge for LOGOS survey planning.

The bridge reuses EvoScientist's onboard/provider/model configuration without
starting the full CLI agent, MCP servers, workspace middleware, or async
sub-agent runtime.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ...config import REPO_ROOT
from ...schemas import ResearchRequest


class SurveyPlanningOutput(BaseModel):
    """Structured planning output produced by EvoScientist's model bridge."""

    subtopics: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    gap_hypotheses: list[str] = Field(default_factory=list)
    rationale: str = ""


@dataclass
class EvoScientistBridge:
    """Optional bridge to EvoScientist's model/onboard/provider layer."""

    provider: str = "deepseek"
    model: str = "deepseek-v4-pro"
    enabled: bool = True
    last_error: str | None = None
    _config: Any = field(default=None, init=False, repr=False)
    _model: Any = field(default=None, init=False, repr=False)

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        try:
            self._ensure_env()
        except Exception as exc:
            self.last_error = str(exc)
            return False
        return bool(os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENROUTER_API_KEY"))

    def plan_survey(
        self,
        request: ResearchRequest,
        web_context: list[dict[str, Any]] | None = None,
    ) -> SurveyPlanningOutput | None:
        """Ask EvoScientist's configured model to produce S1/S4 planning JSON."""
        if not self.is_available():
            return None

        prompt = _build_planning_prompt(request, web_context or [])
        try:
            model = self._get_model()
            response = model.invoke(prompt)
            content = getattr(response, "content", response)
            parsed = _parse_json_object(str(content))
            return SurveyPlanningOutput(**parsed)
        except Exception as exc:
            self.last_error = str(exc)
            return None

    def web_search(self, query: str, max_results: int = 3) -> str:
        """Use EvoScientist's Tavily tool when available."""
        if not self.enabled:
            return ""
        try:
            self._ensure_env()
            if not os.getenv("TAVILY_API_KEY"):
                return ""
            self._ensure_evo_on_path()
            from EvoScientist.tools.search import tavily_search

            return asyncio.run(
                tavily_search.ainvoke(
                    {
                        "query": query,
                        "max_results": max_results,
                        "topic": "general",
                    }
                )
            )
        except Exception as exc:
            self.last_error = str(exc)
            return ""

    def _ensure_env(self) -> None:
        self._ensure_evo_on_path()
        from EvoScientist.config.settings import apply_config_to_env, get_effective_config

        self._config = get_effective_config(
            {
                "provider": self.provider,
                "model": self.model,
                "enable_async_subagents": False,
            }
        )
        apply_config_to_env(self._config)

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        self._ensure_env()
        from EvoScientist.llm import get_chat_model

        self._model = get_chat_model(
            model=self.model,
            provider=self.provider,
            temperature=0,
        )
        return self._model

    def _ensure_evo_on_path(self) -> None:
        repo_root = str(Path(REPO_ROOT).resolve())
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)


def _build_planning_prompt(
    request: ResearchRequest,
    web_context: list[dict[str, Any]],
) -> str:
    web_lines = []
    for item in web_context[:5]:
        title = item.get("title") or "Untitled"
        url = item.get("url") or ""
        content = (item.get("content") or item.get("snippet") or "")[:800]
        web_lines.append(f"- {title} {url}\n  {content}")

    return f"""You are EvoScientist's research-agent planner for an academic survey.

Task: produce search planning JSON for LOGOS paper discovery.

Research goal:
{request.research_goal}

Known topic keywords:
{", ".join(request.topic_keywords) if request.topic_keywords else "(none)"}

Target paper count: {request.paper_count_target}
Survey profile: {request.survey_profile}

Optional web context from Tavily:
{chr(10).join(web_lines) if web_lines else "(none)"}

Return ONLY valid JSON with this exact shape:
{{
  "subtopics": ["3-5 distinct coverage areas"],
  "queries": ["4-6 short English academic search queries, 3-6 words each"],
  "gap_hypotheses": ["2-5 likely blind spots or alternate terminology"],
  "rationale": "brief explanation"
}}

Rules:
- Queries must be atomic, English, and useful for paper search.
- Include alternate terminology across research communities.
- For GraphRAG, include variants around graph retrieval augmented generation,
  knowledge graph QA, graph-based retrieval, benchmarks, and evaluation.
- Do not include markdown fences.
"""


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise
        data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("survey planning response must be a JSON object")
    return data
