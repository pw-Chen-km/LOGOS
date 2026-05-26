"""Research Request Schema

Module 1: Research Intent Intake Agent 的輸出格式。
將使用者模糊的研究想法轉成可執行的 research request。
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    """時間範圍設定"""
    from_year: int = Field(..., description="起始年份")
    to_year: int = Field(..., description="結束年份")


class ResearchRequest(BaseModel):
    """研究請求的結構化表示
    
    由 Research Intent Intake Agent 從自然語言輸入產生。
    """
    request_id: str = Field(..., description="唯一請求 ID")
    raw_user_input: str = Field(..., description="原始使用者輸入")
    
    # 釐清後的研究目標
    research_goal: str = Field(..., description="釐清後的研究目標")
    target_venue: Optional[str] = Field(None, description="目標會議/期刊，如 NeurIPS, ICML, ACL")
    topic_keywords: List[str] = Field(default_factory=list, description="主題關鍵字列表")
    
    # 種子論文與時間範圍
    seed_papers: List[str] = Field(default_factory=list, description="使用者提供的種子論文（arXiv ID, DOI, 或標題）")
    time_range: Optional[TimeRange] = Field(None, description="時間範圍")
    
    # 收錄標準
    paper_count_target: int = Field(default=50, ge=1, le=500, description="目標論文數量")
    survey_profile: str = Field(
        default="survey",
        description="調查類型: survey | ideation | proposal | baseline_search"
    )
    inclusion_criteria: List[str] = Field(default_factory=list, description="納入條件")
    exclusion_criteria: List[str] = Field(default_factory=list, description="排除條件")
    
    # 閱讀深度政策
    core_reading_level: str = Field(
        default="L1",
        description="核心論文閱讀深度: L1 (technical) | L2 (motivation/tradeoff) | L3 (contextual)"
    )
    related_reading_level: str = Field(default="L2", description="相關論文閱讀深度")
    background_reading_level: str = Field(default="L3", description="背景論文閱讀深度")

    class Config:
        json_schema_extra = {
            "example": {
                "request_id": "req_2024_001",
                "raw_user_input": "我想了解 GraphRAG 領域的最新進展",
                "research_goal": "調查 GraphRAG (Graph-based Retrieval-Augmented Generation) 的最新方法、benchmarks 與 open challenges",
                "target_venue": "SIGIR, NeurIPS, ACL",
                "topic_keywords": ["GraphRAG", "retrieval-augmented generation", "knowledge graph", "LLM"],
                "seed_papers": ["arxiv:2401.12345"],
                "time_range": {"from_year": 2023, "to_year": 2026},
                "paper_count_target": 50,
                "survey_profile": "survey",
                "inclusion_criteria": ["必須包含 GraphRAG 或 graph-based retrieval 方法"],
                "exclusion_criteria": ["純粹的 vector DB retrieval 不包含 graph"],
                "core_reading_level": "L1",
                "related_reading_level": "L2",
                "background_reading_level": "L3"
            }
        }
