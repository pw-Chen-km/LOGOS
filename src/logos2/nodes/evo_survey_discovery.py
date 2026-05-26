"""Discovery backend powered by the full EvoScientist survey agent."""

from __future__ import annotations

from pathlib import Path

from ..config import LogosConfig
from ..schemas import ResearchRequest
from .iterative_discovery import IterativeDiscoveryResult


class EvoSurveyAgentDiscovery:
    """Run discovery, reading, taxonomy, and synthesis via EvoScientist."""

    def __init__(
        self,
        config: LogosConfig | None = None,
        run_dir: str | Path | None = None,
    ):
        self.config = config or LogosConfig.load()
        self.run_dir = Path(run_dir) if run_dir else None

    def run(self, request: ResearchRequest) -> IterativeDiscoveryResult:
        from ..adapters.evoscientist.evo_survey_agent import EvoSurveyAgentAdapter

        run_dir = self.run_dir or self.config.runtime.runs_dir / request.request_id
        agent = EvoSurveyAgentAdapter(config=self.config, run_dir=run_dir)
        result = agent.run(request)
        return IterativeDiscoveryResult(
            paper_candidates=result.paper_candidates,
            metadata_map=result.metadata_map,
            readings=result.readings,
            pdf_manifest=result.pdf_manifest,
            web_findings=result.web_findings,
            trace=result.trace,
            survey_taxonomy=result.survey_taxonomy,
            survey_report_paths=result.report_paths,
            evo_thread_id=result.thread_id,
        )
