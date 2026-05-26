"""LOGOS 2.0 adapters.

The paper-navigator adapter is safe for the default open-source install.
EvoScientist bridge and survey-agent integrations are imported lazily so
``import logos2`` does not require the full EvoScientist runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .evoscientist.paper_navigator_adapter import (
    DirectPaperNavigatorAdapter,
    PaperCandidate,
    PaperMetadata,
    PaperNavigatorAdapter,
    PaperNavigatorInstallReport,
    PaperNavigatorRunArtifacts,
    PdfManifestEntry,
)

if TYPE_CHECKING:
    from .evoscientist.evo_agent_bridge import EvoScientistBridge, SurveyPlanningOutput
    from .evoscientist.evo_survey_agent import (
        EvoSurveyAgentAdapter,
        EvoSurveyAgentResult,
    )

__all__ = [
    "DirectPaperNavigatorAdapter",
    "EvoScientistBridge",
    "EvoSurveyAgentAdapter",
    "EvoSurveyAgentResult",
    "PaperCandidate",
    "PaperMetadata",
    "PaperNavigatorAdapter",
    "PaperNavigatorInstallReport",
    "PaperNavigatorRunArtifacts",
    "PdfManifestEntry",
    "SurveyPlanningOutput",
    "parse_survey_artifact",
]


def __getattr__(name: str) -> Any:
    if name in {"EvoScientistBridge", "SurveyPlanningOutput"}:
        from .evoscientist.evo_agent_bridge import (
            EvoScientistBridge,
            SurveyPlanningOutput,
        )

        return {
            "EvoScientistBridge": EvoScientistBridge,
            "SurveyPlanningOutput": SurveyPlanningOutput,
        }[name]

    if name in {
        "EvoSurveyAgentAdapter",
        "EvoSurveyAgentResult",
        "parse_survey_artifact",
    }:
        from .evoscientist.evo_survey_agent import (
            EvoSurveyAgentAdapter,
            EvoSurveyAgentResult,
            parse_survey_artifact,
        )

        return {
            "EvoSurveyAgentAdapter": EvoSurveyAgentAdapter,
            "EvoSurveyAgentResult": EvoSurveyAgentResult,
            "parse_survey_artifact": parse_survey_artifact,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
