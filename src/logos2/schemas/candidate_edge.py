"""Candidate Edge Schema

Module 6/8: Cross-Paper Edge 的候選狀態。
由 Survey Taxonomy Generator 產生，可被 Edge Verifier 更新。
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class CandidateEdge(BaseModel):
    """Candidate Paper Relation
    
    尚未經過 verification 的 cheap candidate relation。
    存在於 lightweight Neo4j index 中，status="candidate"。
    """
    edge_id: Optional[str] = Field(None, description="邊緣唯一 ID（可選）")
    
    source_paper_id: str = Field(..., description="來源論文 ID")
    target_paper_id: str = Field(..., description="目標論文 ID")
    
    relation_type: str = Field(
        ...,
        description="關係類型",
        pattern="^(same_method_family|same_benchmark|related_problem|common_baseline|extends|improves|contradicts)$"
    )
    
    # 狀態追蹤
    status: str = Field(
        default="candidate",
        description="狀態: candidate | verified | rejected | weak_verified",
        pattern="^(candidate|verified|rejected|weak_verified)$"
    )
    
    # 來源資訊
    source: str = Field(
        default="survey_taxonomy",
        description="產生來源: survey_taxonomy | metadata_analysis | user_defined"
    )
    
    # 信心分數
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="信心分數（cheap source 可能較低）"
    )
    
    # 推論理由
    rationale: Optional[str] = Field(None, description="為何推論此關係")
    
    # 證據引用（僅在 verified 後填寫）
    evidence: Optional[List[dict]] = Field(None, description="Verification 後的證據")
    
    class Config:
        json_schema_extra = {
            "example": {
                "edge_id": "edge_001",
                "source_paper_id": "arxiv:2401.12345",
                "target_paper_id": "arxiv:2402.67890",
                "relation_type": "same_benchmark",
                "status": "candidate",
                "source": "survey_taxonomy",
                "confidence": 0.72,
                "rationale": "兩篇論文都評估於 HotpotQA benchmark"
            }
        }
