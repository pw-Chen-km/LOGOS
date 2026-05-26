"""Paper Navigator Reading Schema

Module 2: Paper Navigator Adapter 的輸出格式。
來自 paper-navigator 的 structured reading artifact。
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class PaperNavigatorReading(BaseModel):
    """Paper Navigator Reading Output
    
    paper-navigator 對單篇論文的閱讀輸出，支援 L1/L2/L3 不同深度。
    """
    paper_id: str = Field(..., description="論文唯一 ID（如 arXiv ID）")
    reading_level: str = Field(
        ...,
        description="閱讀深度: L1 | L2 | L3 | metadata_only",
        pattern="^(L1|L2|L3|metadata_only)$"
    )
    
    # 基本資訊（所有 level 都有）
    title: str = Field(..., description="論文標題")
    tldr: str = Field(..., description="一句話 TL;DR")
    
    # L1/L2 深度：主要貢獻與問題
    main_contribution: Optional[str] = Field(None, description="主要貢獻")
    problem_statement: Optional[str] = Field(None, description="問題陳述")
    
    # L2 深度：方法直覺與設計原理
    method_intuition: Optional[str] = Field(None, description="方法直覺與 high-level 設計")
    design_rationale: Optional[str] = Field(None, description="設計原理與 tradeoff 討論")
    tradeoffs: Optional[str] = Field(None, description="方法 tradeoff 與 limitation")
    
    # L2 深度：限制
    rough_limitation: Optional[str] = Field(None, description="粗略的局限性分析")
    
    # L1 深度：實驗相關資訊
    benchmark_names: List[str] = Field(default_factory=list, description="評估的 benchmark 名稱")
    dataset_names: List[str] = Field(default_factory=list, description="使用的 dataset 名稱")
    baseline_names: List[str] = Field(default_factory=list, description="比較的 baseline 方法名稱")
    
    # L1 深度：圖表資訊
    mentioned_figures: List[str] = Field(default_factory=list, description="提及的重要 figures")
    mentioned_tables: List[str] = Field(default_factory=list, description="提及的重要 tables")
    
    # 品質控制
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="閱讀品質信心分數（0-1）"
    )
    missing_fields: List[str] = Field(
        default_factory=list,
        description="因閱讀深度或解析問題而缺失的欄位"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "paper_id": "arxiv:2401.12345",
                "reading_level": "L2",
                "title": "MRAG: Multi-hop Retrieval-Augmented Generation with Graph Connectivity",
                "tldr": "MRAG 利用圖連通性來改善多跳檢索，解決 GraphRAG 中的圖碎片化問題",
                "main_contribution": "提出基於圖連通性的檢索方法，顯著提升多跳問答的準確率",
                "problem_statement": "現有 GraphRAG 方法忽略了圖結構連通性，導致檢索失敗",
                "method_intuition": "利用譜圖理論分析圖碎片化，設計基於連通性的重排序策略",
                "design_rationale": "在準確率與效率之間取得平衡，犧牲部分速度換取顯著準確率提升",
                "tradeoffs": "需要額外的圖預處理時間，對超大圖的記憶體需求較高",
                "rough_limitation": "未考慮動態更新的知識圖譜",
                "benchmark_names": ["HotpotQA", "MultiHop-RAG"],
                "dataset_names": ["Wikipedia Graph", "PubMed Graph"],
                "baseline_names": ["GraphRAG", "VectorRAG", "HyDE"],
                "mentioned_figures": ["Figure 1: System architecture", "Figure 3: Ablation study"],
                "mentioned_tables": ["Table 2: Main results on HotpotQA"],
                "confidence": 0.85,
                "missing_fields": ["exact numerical results"]
            }
        }
