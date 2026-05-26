"""LOGOS 2.0 Workflow

LangGraph-based research workflow components.
"""

from .state import LogosResearchState
from .trace import WorkflowTracer

# Workflow graph requires Neo4j nodes
try:
    from .graph import LogosResearchWorkflow
    __all__ = ["LogosResearchState", "LogosResearchWorkflow", "WorkflowTracer"]
except ImportError:
    __all__ = ["LogosResearchState", "WorkflowTracer"]
