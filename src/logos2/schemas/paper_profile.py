"""Paper Profile Schema

Module 4: LOGOS Profile Normalizer 的輸出格式。
統一的 paper profile，合併 paper-navigator reading 與 survey taxonomy 資訊。
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class PaperRelation(BaseModel):
    """論文與其他論文的關係"""
    target_paper_id: str = Field(..., description="目標論文 ID")
    relation_type: str = Field(
        ...,
        description="關係類型: same_method_family | same_benchmark | related_problem | common_baseline | extends | improves"
    )
    status: str = Field(
        default="candidate",
        description="狀態: candidate | verified | rejected | weak_verified",
        pattern="^(candidate|verified|rejected|weak_verified)$"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="信心分數")
    rationale: Optional[str] = Field(None, description="關係推論理由")


class PaperProfile(BaseModel):
    """Paper Profile
    
    單篇論文的 canonical knowledge entry。
    合併 paper-navigator reading output 與 survey taxonomy 資訊。
    """
    # 身份識別
    paper_id: str = Field(..., description="論文唯一 ID")
    
    # 基本元數據
    title: str = Field(..., description="論文標題")
    year: Optional[str] = Field(None, description="發表年份")
    venue: Optional[str] = Field(None, description="發表會議/期刊")
    authors: List[str] = Field(default_factory=list, description="作者列表")
    
    # 核心摘要
    tldr: str = Field(..., description="一句話 TL;DR")
    
    # 分類資訊（來自 survey taxonomy）
    theme: Optional[str] = Field(None, description="主題名稱")
    taxonomy_path: List[str] = Field(default_factory=list, description="分類路徑")
    method_family: Optional[str] = Field(None, description="方法家族")
    
    # 研究內容（來自 paper-navigator，保持輕量）
    rough_research_problem: Optional[str] = Field(None, description="研究問題概述")
    rough_contribution: Optional[str] = Field(None, description="主要貢獻概述")
    rough_method_intuition: Optional[str] = Field(None, description="方法直覺概述")
    rough_limitation: Optional[str] = Field(None, description="局限性概述")
    
    # 評估資訊（用於 routing 與索引）
    benchmark_names: List[str] = Field(default_factory=list, description="Benchmark 名稱")
    dataset_names: List[str] = Field(default_factory=list, description="Dataset 名稱")
    baseline_names: List[str] = Field(default_factory=list, description="Baseline 方法名稱")
    
    # 關係（來自 survey taxonomy candidate relations）
    relationship_to_other_papers: List[PaperRelation] = Field(default_factory=list)
    
    # 品質與來源資訊
    reading_level: str = Field(
        ...,
        description="閱讀深度: L1 | L2 | L3 | metadata_only",
        pattern="^(L1|L2|L3|metadata_only)$"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="整體資料品質信心分數"
    )
    missing_fields: List[str] = Field(
        default_factory=list,
        description="缺失欄位（由 QA/PDF fallback 處理）"
    )
    
    # 檔案路徑（用於 routing）
    pdf_path: Optional[str] = Field(None, description="原始 PDF 路徑")
    section_index_path: Optional[str] = Field(None, description="章節索引 JSON 路徑")
    skill_path: str = Field(..., description="SKILL.md 路徑")
    
    class Config:
        json_schema_extra = {
            "example": {
                "paper_id": "arxiv:2401.12345",
                "title": "MRAG: Multi-hop Retrieval-Augmented Generation with Graph Connectivity",
                "year": "2024",
                "venue": "SIGIR",
                "authors": ["Alice Chen", "Bob Smith"],
                "tldr": "利用圖連通性改善多跳檢索的 GraphRAG 方法",
                "theme": "Graph-based Retrieval",
                "taxonomy_path": ["GraphRAG", "Graph Connectivity", "Multi-hop Retrieval"],
                "method_family": "Spectral Graph Methods",
                "rough_research_problem": "GraphRAG 忽略圖結構導致檢索失敗",
                "rough_contribution": "提出基於連通性的重排序策略",
                "rough_method_intuition": "利用譜圖理論分析圖碎片化",
                "rough_limitation": "未考慮動態圖更新",
                "benchmark_names": ["HotpotQA", "MultiHop-RAG"],
                "dataset_names": ["Wikipedia Graph"],
                "baseline_names": ["GraphRAG", "VectorRAG"],
                "relationship_to_other_papers": [
                    {
                        "target_paper_id": "arxiv:2402.67890",
                        "relation_type": "same_benchmark",
                        "status": "candidate",
                        "confidence": 0.72
                    }
                ],
                "reading_level": "L2",
                "confidence": 0.85,
                "missing_fields": ["exact experimental results"],
                "pdf_path": "paper_library/arxiv_2401_12345.pdf",
                "section_index_path": "paper_skills/arxiv_2401_12345/section_index.json",
                "skill_path": "paper_skills/arxiv_2401_12345/SKILL.md"
            }
        }
