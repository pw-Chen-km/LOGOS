"""LOGOS 2.0: Paper-Skill-Centered Research Management.

A research management agent that turns a vague research direction into:
- Paper pool
- Survey taxonomy
- Paper skill packs
- Lightweight research graph
- Graph-guided deep QA system
"""

from __future__ import annotations

from typing import Any

__version__ = "2.0.0"

# Core schemas (always available)
from .schemas import (
    ResearchRequest,
    PaperNavigatorReading,
    SurveyTaxonomy,
    PaperProfile,
    PaperSkillManifest,
    CandidateEdge,
    VerifiedEdge,
)

# Storage base (always available)
from .storage import SkillRegistry

# Default adapter (always available)
from .adapters import PaperNavigatorAdapter

__all__ = [
    "__version__",
    # Schemas
    "ResearchRequest",
    "PaperNavigatorReading", 
    "SurveyTaxonomy",
    "PaperProfile",
    "PaperSkillManifest",
    "CandidateEdge",
    "VerifiedEdge",
    # Storage
    "SkillRegistry",
    # Adapters
    "PaperNavigatorAdapter",
    # Workflow
    "LogosResearchWorkflow",
]


def __getattr__(name: str) -> Any:
    if name == "LogosResearchWorkflow":
        from .workflow.graph import LogosResearchWorkflow

        return LogosResearchWorkflow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
