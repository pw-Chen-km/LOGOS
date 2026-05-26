"""LOGOS 2.0 Schemas

Pydantic models defining the data structures for the research workflow.
"""

from .research_request import ResearchRequest, TimeRange
from .paper_navigator_reading import PaperNavigatorReading
from .survey_taxonomy import (
    SurveyTaxonomy,
    Theme,
    SubTheme,
    PaperTaxonomyAssignment,
    MethodFamily,
    ProblemCluster,
    BenchmarkMatrixEntry,
    DatasetMatrixEntry,
    BaselineMatrixEntry,
    CandidateRelation,
)
from .paper_profile import PaperProfile, PaperRelation
from .paper_skill_manifest import (
    PaperSkillManifest,
    ReferenceGuideInfo,
    RoutingPolicy,
    SectionIndex,
    EvidenceIndex,
)
from .candidate_edge import CandidateEdge
from .verified_edge import VerifiedEdge, EdgeEvidence

__all__ = [
    # Research Request
    "ResearchRequest",
    "TimeRange",
    # Paper Navigator
    "PaperNavigatorReading",
    # Survey Taxonomy
    "SurveyTaxonomy",
    "Theme",
    "SubTheme",
    "PaperTaxonomyAssignment",
    "MethodFamily",
    "ProblemCluster",
    "BenchmarkMatrixEntry",
    "DatasetMatrixEntry",
    "BaselineMatrixEntry",
    "CandidateRelation",
    # Paper Profile
    "PaperProfile",
    "PaperRelation",
    # Paper Skill Manifest
    "PaperSkillManifest",
    "ReferenceGuideInfo",
    "RoutingPolicy",
    "SectionIndex",
    "EvidenceIndex",
    # Edges
    "CandidateEdge",
    "VerifiedEdge",
    "EdgeEvidence",
]
