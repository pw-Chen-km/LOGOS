"""Verified Edge Schema

Module 8: Edge Verifier 的輸出格式。
經過 expensive verification 後的 paper relation。
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class EdgeEvidence(BaseModel):
    """Edge verification 證據"""
    paper_id: str = Field(..., description="來源論文 ID")
    source: str = Field(..., description="證據來源: paper_profile | skill_md | reference_guide | original_pdf")
    reference_file: Optional[str] = Field(None, description="參考檔案路徑")
    section: Optional[str] = Field(None, description="章節名稱")
    page: Optional[int] = Field(None, description="PDF 頁碼")
    excerpt: Optional[str] = Field(None, description="相關文字摘錄")


class VerifiedEdge(BaseModel):
    """Verified Paper Relation
    
    經過 Edge Verifier 驗證的 paper relation。
    取代 CandidateEdge，寫入 Neo4j 時 status 更新為 verified/rejected。
    """
    edge_id: str = Field(..., description="邊緣唯一 ID")
    
    source_paper_id: str = Field(..., description="來源論文 ID")
    target_paper_id: str = Field(..., description="目標論文 ID")
    
    relation_type: str = Field(
        ...,
        description="關係類型",
        pattern="^(same_method_family|same_benchmark|related_problem|common_baseline|extends|improves|contradicts)$"
    )
    
    # 最終狀態
    status: str = Field(
        ...,
        description="驗證狀態: verified | rejected | weak_verified",
        pattern="^(verified|rejected|weak_verified)$"
    )
    
    # 更新後的信心分數
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Verification 後的信心分數"
    )
    
    # 詳細證據
    evidence: List[EdgeEvidence] = Field(default_factory=list)
    
    # 驗證理由
    rationale: str = Field(..., description="詳細驗證理由")
    
    # 驗證資訊
    verified_at: str = Field(..., description="驗證時間 ISO 格式")
    verifier_version: str = Field(default="1.0.0", description="Edge Verifier 版本")
    
    class Config:
        json_schema_extra = {
            "example": {
                "edge_id": "edge_001",
                "source_paper_id": "arxiv:2401.12345",
                "target_paper_id": "arxiv:2402.67890",
                "relation_type": "same_benchmark",
                "status": "verified",
                "confidence": 0.94,
                "evidence": [
                    {
                        "paper_id": "arxiv:2401.12345",
                        "source": "reference_guide",
                        "reference_file": "references/benchmark_and_baselines.md",
                        "excerpt": "We evaluate on HotpotQA, a popular multi-hop QA benchmark..."
                    },
                    {
                        "paper_id": "arxiv:2402.67890",
                        "source": "paper_profile",
                        "reference_file": "paper_profile.json",
                        "excerpt": "Benchmark names: ['HotpotQA', 'Natural Questions']"
                    }
                ],
                "rationale": "兩篇論文明確都使用 HotpotQA 作為主要評估 benchmark，且都報告了 EM 和 F1 指標",
                "verified_at": "2024-01-20T15:30:00Z",
                "verifier_version": "1.0.0"
            }
        }
