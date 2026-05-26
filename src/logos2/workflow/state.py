"""LangGraph State Definition

Workflow state for LOGOS 2.0 research pipeline.
"""

from typing import List, Dict, Any, Optional, Annotated
from dataclasses import dataclass, field


# Custom reducer for appending to lists
def append_unique(existing: List[Any], new: List[Any]) -> List[Any]:
    """Reducer that appends unique items to a list"""
    result = existing.copy()
    for item in new:
        if item not in result:
            result.append(item)
    return result


@dataclass
class LogosResearchState:
    """Research Workflow State
    
    完整的 LangGraph workflow 狀態，包含：
    - 使用者請求
    - Paper discovery 結果
    - Taxonomy 與 profiles
    - QA trace
    - Edges (candidate and verified)
    - Errors
    """
    
    # Input
    user_request: str = ""
    research_request: Dict[str, Any] = field(default_factory=dict)
    request_id: Optional[str] = None
    
    # Discovery Phase
    paper_candidates: List[Dict[str, Any]] = field(default_factory=list)
    paper_metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    paper_navigator_readings: List[Dict[str, Any]] = field(default_factory=list)
    web_findings: List[Dict[str, Any]] = field(default_factory=list)
    discovery_trace: Dict[str, Any] = field(default_factory=dict)
    survey_report_paths: Dict[str, str] = field(default_factory=dict)
    taxonomy_source: str = ""
    evo_thread_id: Optional[str] = None
    discovery_status: str = "pending"  # pending | completed | failed
    discovery_error: Optional[str] = None
    
    # Taxonomy Phase
    survey_taxonomy: Dict[str, Any] = field(default_factory=dict)
    taxonomy_id: Optional[str] = None
    taxonomy_status: str = "pending"
    taxonomy_error: Optional[str] = None
    
    # Profile Phase
    paper_profiles: List[Dict[str, Any]] = field(default_factory=list)
    profile_status: str = "pending"
    profile_error: Optional[str] = None
    
    # Skill Building Phase
    paper_skill_paths: List[str] = field(default_factory=list)
    skill_build_status: str = "pending"
    skill_build_error: Optional[str] = None
    
    # Graph Indexing Phase
    neo4j_index_status: Dict[str, Any] = field(default_factory=dict)
    indexing_status: str = "pending"
    indexing_error: Optional[str] = None
    
    # QA Phase
    qa_trace: List[Dict[str, Any]] = field(default_factory=list)
    current_query: str = ""
    qa_answer: Optional[str] = None
    qa_status: str = "pending"
    qa_error: Optional[str] = None
    
    # Edge Verification Phase
    candidate_edges: List[Dict[str, Any]] = field(default_factory=list)
    verified_edges: List[Dict[str, Any]] = field(default_factory=list)
    rejected_edges: List[Dict[str, Any]] = field(default_factory=list)
    verification_status: str = "pending"
    verification_error: Optional[str] = None
    
    # Overall Workflow
    errors: List[Dict[str, Any]] = field(default_factory=list)
    current_phase: str = "init"  # init | discovery | taxonomy | profile | skill | index | qa | verify | complete
    workflow_complete: bool = False
    trace_file: Optional[str] = None
    
    def add_error(self, phase: str, error: str, details: Optional[dict] = None):
        """Add an error to the state"""
        error_entry = {
            "phase": phase,
            "error": error,
            "timestamp": None,  # Will be set by workflow
            "details": details or {}
        }
        self.errors.append(error_entry)
    
    def get_paper_by_id(self, paper_id: str) -> Optional[Dict[str, Any]]:
        """Get a paper profile by ID"""
        for profile in self.paper_profiles:
            if profile.get("paper_id") == paper_id:
                return profile
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary"""
        return {
            "user_request": self.user_request,
            "research_request": self.research_request,
            "request_id": self.request_id,
            "paper_candidates": self.paper_candidates,
            "paper_metadata": self.paper_metadata,
            "paper_navigator_readings": self.paper_navigator_readings,
            "web_findings": self.web_findings,
            "discovery_trace": self.discovery_trace,
            "survey_report_paths": self.survey_report_paths,
            "taxonomy_source": self.taxonomy_source,
            "evo_thread_id": self.evo_thread_id,
            "discovery_status": self.discovery_status,
            "survey_taxonomy": self.survey_taxonomy,
            "taxonomy_id": self.taxonomy_id,
            "taxonomy_status": self.taxonomy_status,
            "paper_profiles": self.paper_profiles,
            "profile_status": self.profile_status,
            "paper_skill_paths": self.paper_skill_paths,
            "skill_build_status": self.skill_build_status,
            "neo4j_index_status": self.neo4j_index_status,
            "indexing_status": self.indexing_status,
            "qa_trace": self.qa_trace,
            "current_query": self.current_query,
            "qa_answer": self.qa_answer,
            "qa_status": self.qa_status,
            "candidate_edges": self.candidate_edges,
            "verified_edges": self.verified_edges,
            "rejected_edges": self.rejected_edges,
            "verification_status": self.verification_status,
            "current_phase": self.current_phase,
            "workflow_complete": self.workflow_complete,
        }
