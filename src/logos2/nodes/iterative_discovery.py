"""EvoScientist-style iterative paper discovery for LOGOS.

This node ports paper-navigator Branch 3 into LOGOS while keeping the existing
taxonomy/profile/skill/graph stages intact.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Any

from ..adapters.evoscientist.paper_navigator_adapter import (
    DirectPaperNavigatorAdapter,
    PaperCandidate,
    PaperMetadata,
    PdfManifestEntry,
)
from ..adapters.evoscientist.evo_agent_bridge import EvoScientistBridge
from ..config import LogosConfig
from ..schemas import PaperNavigatorReading, ResearchRequest


@dataclass
class IterativeDiscoveryResult:
    paper_candidates: list[PaperCandidate]
    metadata_map: dict[str, PaperMetadata]
    readings: list[PaperNavigatorReading]
    pdf_manifest: list[PdfManifestEntry] = field(default_factory=list)
    web_findings: list[dict[str, Any]] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)
    survey_taxonomy: Any | None = None
    survey_report_paths: dict[str, str] = field(default_factory=dict)
    evo_thread_id: str | None = None


class IterativeDiscovery:
    """Run S1-S5 iterative collection with optional web and deep reading."""

    def __init__(
        self,
        navigator: DirectPaperNavigatorAdapter,
        config: LogosConfig | None = None,
        agent_bridge: EvoScientistBridge | None = None,
    ):
        self.navigator = navigator
        self.config = config or LogosConfig.load()
        self.agent_bridge = agent_bridge or EvoScientistBridge(
            provider=self.config.evoscientist.provider,
            model=self.config.evoscientist.model,
            enabled=self.config.evoscientist.enabled,
        )

    def run(self, request: ResearchRequest) -> IterativeDiscoveryResult:
        target_n = min(request.paper_count_target, self.config.paper_navigator.max_papers)
        trace: dict[str, Any] = {
            "mode": self._route_intent(request),
            "target_n": target_n,
            "errors": [],
        }

        web_findings: list[dict[str, Any]] = []
        if self.config.evoscientist.use_tavily:
            evo_tavily = self.agent_bridge.web_search(request.research_goal, max_results=3)
            if evo_tavily:
                web_findings.append(
                    {
                        "title": "EvoScientist Tavily research context",
                        "url": "",
                        "content": evo_tavily[:6000],
                        "source": "evoscientist.tavily_search",
                    }
                )

        plan = self.agent_bridge.plan_survey(request, web_context=web_findings)
        if plan:
            subtopics = plan.subtopics[:5]
            queries = [_trim_query(query) for query in plan.queries[:6]]
            trace["s1_decompose"] = {
                "source": "evoscientist_bridge",
                "provider": self.config.evoscientist.provider,
                "model": self.config.evoscientist.model,
                "subtopics": subtopics,
                "queries": queries,
                "gap_hypotheses": plan.gap_hypotheses,
                "rationale": plan.rationale,
            }
        else:
            subtopics, queries = self._decompose(request)
            trace["s1_decompose"] = {
                "source": "heuristic",
                "subtopics": subtopics,
                "queries": queries,
                "bridge_error": self.agent_bridge.last_error,
            }

        pool: list[PaperCandidate] = []
        pool.extend(self._safe_candidates("local_library", trace, self.navigator.search_local_library, request.research_goal, min(10, target_n)))

        if os.getenv("TAVILY_API_KEY") and not web_findings:
            web_findings = self._safe_web("tavily_search", trace, request.research_goal, limit=5)

        for query in queries:
            pool.extend(
                self._safe_candidates(
                    f"scholar_search:{query}",
                    trace,
                    self.navigator.run_keyword_search,
                    query,
                    min(20, max(target_n, 20)),
                )
            )

        arxiv_keywords = ",".join(queries[:4])
        pool.extend(
            self._safe_candidates(
                "arxiv_monitor",
                trace,
                self.navigator.run_arxiv_monitor,
                arxiv_keywords,
                365,
            )
        )

        # S2 can surface citation velocity only when S2_API_KEY/rate limits allow it.
        pool.extend(
            self._safe_candidates(
                "trending",
                trace,
                self.navigator.run_trending,
                queries[0],
                180,
                min(10, target_n),
            )
        )
        pool = self._dedupe_and_rank(pool, request, subtopics)
        trace["s2_multi_search"] = {"pool_size": len(pool)}

        seeds = self._select_seeds(pool, subtopics)
        trace["s3_seeds"] = [seed.paper_id for seed in seeds]
        if seeds:
            pool.extend(
                self._safe_candidates(
                    "citation_co_citation",
                    trace,
                    self.navigator.run_citation_traversal,
                    seeds[0].paper_id,
                    "co-citation",
                    15,
                )
            )
            for seed in seeds[:2]:
                pool.extend(
                    self._safe_candidates(
                        f"citation_forward:{seed.paper_id}",
                        trace,
                        self.navigator.run_citation_traversal,
                        seed.paper_id,
                        "forward",
                        20,
                    )
                )
            for seed in seeds[-2:]:
                pool.extend(
                    self._safe_candidates(
                        f"citation_backward:{seed.paper_id}",
                        trace,
                        self.navigator.run_citation_traversal,
                        seed.paper_id,
                        "backward",
                        20,
                    )
                )
            pool.extend(
                self._safe_candidates(
                    "recommend",
                    trace,
                    self.navigator.run_recommendations,
                    [seed.paper_id for seed in seeds[:3]],
                    15,
                )
            )
        pool = self._dedupe_and_rank(pool, request, subtopics)
        trace["s3_citation_expand"] = {"pool_size": len(pool)}

        pool = self._gap_check(pool, request, subtopics, trace)
        final_candidates = self._dedupe_and_rank(pool, request, subtopics)[:target_n]
        trace["s5_finalize"] = {
            "final_count": len(final_candidates),
            "paper_ids": [candidate.paper_id for candidate in final_candidates],
        }

        metadata_map = {candidate.paper_id: candidate.to_metadata() for candidate in final_candidates}
        readings = self._build_readings(final_candidates, metadata_map, request, trace)

        return IterativeDiscoveryResult(
            paper_candidates=final_candidates,
            metadata_map=metadata_map,
            readings=readings,
            web_findings=web_findings,
            trace=trace,
        )

    def _route_intent(self, request: ResearchRequest) -> str:
        text = request.raw_user_input.lower()
        if request.paper_count_target >= 15 or any(word in text for word in ["survey", "comprehensive", "literature", "review", "調查", "綜述"]):
            return "ITERATIVE"
        if request.seed_papers or any(word in text for word in ["read this", "paper id", "arxiv"]):
            return "POINT"
        return "LIST"

    def _decompose(self, request: ResearchRequest) -> tuple[list[str], list[str]]:
        base_terms = _content_terms(request.research_goal)
        base_query = " ".join(base_terms[:5]) or request.research_goal
        keyword_query = " ".join(request.topic_keywords[:5]) if request.topic_keywords else base_query

        subtopics = [
            "methods and architectures",
            "benchmarks and datasets",
            "applications and systems",
            "limitations and evaluation",
        ]
        queries = [
            base_query,
            keyword_query,
            f"{base_query} benchmark",
            f"{base_query} dataset",
            f"{base_query} survey",
            f"{base_query} limitations",
        ]
        if "graphrag" in request.research_goal.lower():
            queries.extend(
                [
                    "graph retrieval augmented generation",
                    "knowledge graph retrieval generation",
                    "graph based RAG benchmark",
                ]
            )
        return subtopics, _dedupe_strings([_trim_query(query) for query in queries])[:6]

    def _gap_check(
        self,
        pool: list[PaperCandidate],
        request: ResearchRequest,
        subtopics: list[str],
        trace: dict[str, Any],
    ) -> list[PaperCandidate]:
        gap_counts: dict[str, int] = {}
        for subtopic in subtopics:
            terms = set(_content_terms(subtopic))
            gap_counts[subtopic] = sum(
                1 for candidate in pool if terms & set(_content_terms(candidate.title + " " + (candidate.abstract or "")))
            )

        gaps = [topic for topic, count in gap_counts.items() if count < 2]
        trace["s4_gap_check"] = {"coverage": gap_counts, "gaps": gaps}
        for gap in gaps[:2]:
            query = _trim_query(f"{request.research_goal} {gap}")
            pool.extend(
                self._safe_candidates(
                    f"gap_search:{gap}",
                    trace,
                    self.navigator.run_keyword_search,
                    query,
                    10,
                )
            )
        return pool

    def _build_readings(
        self,
        candidates: list[PaperCandidate],
        metadata_map: dict[str, PaperMetadata],
        request: ResearchRequest,
        trace: dict[str, Any],
    ) -> list[PaperNavigatorReading]:
        readings: list[PaperNavigatorReading] = []
        max_deep_reads = min(len(candidates), 12)

        for idx, candidate in enumerate(candidates):
            metadata = metadata_map[candidate.paper_id]
            if idx >= max_deep_reads:
                readings.append(metadata.to_paper_navigator_reading())
                continue

            level = (
                request.core_reading_level
                if idx < 3
                else request.related_reading_level
                if idx < 10
                else request.background_reading_level
            )
            try:
                reading = self.navigator.read(candidate.paper_id, reading_level=level)
                reading.title = metadata.title
                if metadata.tldr and (not reading.tldr or reading.tldr == candidate.paper_id):
                    reading.tldr = metadata.tldr
                readings.append(reading)
            except Exception as exc:
                trace.setdefault("errors", []).append(
                    {"stage": f"deep_read:{candidate.paper_id}", "error": str(exc)}
                )
                readings.append(metadata.to_paper_navigator_reading())

        return readings

    def _safe_candidates(self, stage: str, trace: dict[str, Any], func: Any, *args: Any) -> list[PaperCandidate]:
        try:
            results = func(*args)
            trace[stage] = {"count": len(results)}
            return results
        except Exception as exc:
            trace.setdefault("errors", []).append({"stage": stage, "error": str(exc)})
            trace[stage] = {"count": 0, "error": str(exc)}
            return []

    def _safe_web(self, stage: str, trace: dict[str, Any], query: str, limit: int) -> list[dict[str, Any]]:
        try:
            results = self.navigator.run_tavily_search(query, limit=limit)
            trace[stage] = {"count": len(results)}
            return results
        except Exception as exc:
            trace.setdefault("errors", []).append({"stage": stage, "error": str(exc)})
            trace[stage] = {"count": 0, "error": str(exc)}
            return []

    def _select_seeds(self, pool: list[PaperCandidate], subtopics: list[str]) -> list[PaperCandidate]:
        if not pool:
            return []
        seeds: list[PaperCandidate] = []
        used_subtopics: set[str] = set()
        for candidate in pool:
            matched = _best_subtopic(candidate, subtopics)
            if matched not in used_subtopics or len(seeds) < 2:
                seeds.append(candidate)
                used_subtopics.add(matched)
            if len(seeds) >= 3:
                break
        return seeds

    def _dedupe_and_rank(
        self,
        candidates: list[PaperCandidate],
        request: ResearchRequest,
        subtopics: list[str],
    ) -> list[PaperCandidate]:
        deduped: dict[str, PaperCandidate] = {}
        for candidate in candidates:
            key = _candidate_key(candidate)
            if not key:
                continue
            existing = deduped.get(key)
            if not existing or _candidate_score(candidate, request, subtopics) > _candidate_score(existing, request, subtopics):
                deduped[key] = candidate
        return sorted(
            deduped.values(),
            key=lambda candidate: _candidate_score(candidate, request, subtopics),
            reverse=True,
        )


def _candidate_key(candidate: PaperCandidate) -> str:
    if candidate.arxiv_id:
        return f"arxiv:{candidate.arxiv_id}".lower()
    return re.sub(r"\W+", " ", candidate.title.lower()).strip()


def _candidate_score(candidate: PaperCandidate, request: ResearchRequest, subtopics: list[str]) -> float:
    query_terms = set(_content_terms(request.research_goal + " " + " ".join(request.topic_keywords)))
    text_terms = set(_content_terms(candidate.title + " " + (candidate.abstract or "") + " " + (candidate.tldr or "")))
    overlap = len(query_terms & text_terms)
    citations = math.log1p(candidate.citation_count or 0)
    year_bonus = 0.0
    if candidate.year and candidate.year.isdigit():
        year_bonus = max(0, int(candidate.year) - 2018) * 0.05
    coverage_bonus = 0.2 if _best_subtopic(candidate, subtopics) else 0.0
    return overlap * 2.0 + citations + year_bonus + coverage_bonus


def _best_subtopic(candidate: PaperCandidate, subtopics: list[str]) -> str:
    text_terms = set(_content_terms(candidate.title + " " + (candidate.abstract or "")))
    best = ""
    best_score = 0
    for subtopic in subtopics:
        score = len(set(_content_terms(subtopic)) & text_terms)
        if score > best_score:
            best = subtopic
            best_score = score
    return best


def _content_terms(text: str) -> list[str]:
    stopwords = {
        "about",
        "and",
        "are",
        "for",
        "from",
        "into",
        "latest",
        "paper",
        "papers",
        "research",
        "search",
        "survey",
        "the",
        "with",
        "請",
        "搜尋",
        "論文",
        "調查",
    }
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]{2,}", text.lower())
    return [token for token in tokens if token not in stopwords]


def _trim_query(query: str, max_terms: int = 6) -> str:
    terms = _content_terms(query)
    return " ".join(terms[:max_terms]) or query.strip()


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result
