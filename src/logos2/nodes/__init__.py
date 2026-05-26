"""LOGOS 2.0 Workflow Nodes

LangGraph nodes for the research workflow.
"""

from .survey_taxonomy import SurveyTaxonomyGenerator
from .profile_normalizer import ProfileNormalizer
from .paper_skill_builder import PaperSkillBuilder
from .deep_reader import OnDemandDeepReaderAgent, DeepReadingResult
from .iterative_discovery import IterativeDiscovery, IterativeDiscoveryResult
from .evo_survey_discovery import EvoSurveyAgentDiscovery
from .paper_reference_pack_builder import PaperReferencePackBuilder, ReferencePack

# Nodes requiring Neo4j are optional
try:
    from .lightweight_graph_indexer import LightweightGraphIndexer
    from .qa_agent import QAAgent
    from .edge_verifier import EdgeVerifier
    __all__ = [
        "SurveyTaxonomyGenerator",
        "ProfileNormalizer",
        "PaperSkillBuilder",
        "OnDemandDeepReaderAgent",
        "DeepReadingResult",
        "IterativeDiscovery",
        "IterativeDiscoveryResult",
        "EvoSurveyAgentDiscovery",
        "PaperReferencePackBuilder",
        "ReferencePack",
        "LightweightGraphIndexer",
        "QAAgent",
        "EdgeVerifier",
    ]
except ImportError:
    # Neo4j not available
    __all__ = [
        "SurveyTaxonomyGenerator",
        "ProfileNormalizer",
        "PaperSkillBuilder",
        "OnDemandDeepReaderAgent",
        "DeepReadingResult",
        "IterativeDiscovery",
        "IterativeDiscoveryResult",
        "EvoSurveyAgentDiscovery",
        "PaperReferencePackBuilder",
        "ReferencePack",
    ]
