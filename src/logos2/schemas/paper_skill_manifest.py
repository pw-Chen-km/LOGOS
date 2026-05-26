"""Paper Skill Manifest Schema

Module 5: Paper Skill Builder 輸出格式。
定義 paper skill pack 的結構。
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ReferenceGuideInfo(BaseModel):
    """Reference guide 檔案資訊"""
    filename: str = Field(..., description="檔案名稱")
    description: str = Field(..., description="用途描述")
    query_types: List[str] = Field(default_factory=list, description="適用的查詢類型")


class RoutingPolicy(BaseModel):
    """Routing policy 項目"""
    query_pattern: str = Field(..., description="查詢模式描述")
    target_file: str = Field(..., description="目標檔案")
    fallback_to_pdf: bool = Field(default=False, description="是否允許 fallback 到 PDF")


class SectionIndex(BaseModel):
    """章節索引項目"""
    section_name: str = Field(..., description="章節名稱")
    pdf_page_start: Optional[int] = Field(None, description="PDF 起始頁碼")
    pdf_page_end: Optional[int] = Field(None, description="PDF 結束頁碼")
    markdown_anchor: Optional[str] = Field(None, description="Markdown 中的錨點")


class EvidenceIndex(BaseModel):
    """證據索引（圖表）"""
    evidence_id: str = Field(..., description="證據 ID")
    evidence_type: str = Field(..., description="類型: figure | table", pattern="^(figure|table)$")
    caption: Optional[str] = Field(None, description="標題/說明")
    pdf_page: Optional[int] = Field(None, description="PDF 頁碼")
    section: Optional[str] = Field(None, description="所屬章節")


class PaperSkillManifest(BaseModel):
    """Paper Skill Manifest
    
    描述單篇 paper skill pack 的內容與 routing policy。
    對應 SKILL.md + metadata.json 的結構化表示。
    """
    paper_id: str = Field(..., description="論文 ID")
    
    # SKILL.md frontmatter 資訊
    skill_name: str = Field(..., description="Skill 名稱")
    skill_description: str = Field(..., description="Skill 描述（trigger mechanism）")
    tags: List[str] = Field(default_factory=list, description="標籤")
    
    # Reference guides
    reference_guides: List[ReferenceGuideInfo] = Field(default_factory=list)
    
    # Routing policies
    routing_policies: List[RoutingPolicy] = Field(default_factory=list)
    
    # 索引檔案
    section_index: List[SectionIndex] = Field(default_factory=list)
    evidence_index: List[EvidenceIndex] = Field(default_factory=list)
    
    # 路徑資訊
    skill_md_path: str = Field(..., description="SKILL.md 路徑")
    metadata_json_path: str = Field(..., description="metadata.json 路徑")
    paper_profile_path: str = Field(..., description="paper_profile.json 路徑")
    references_dir: str = Field(..., description="references/ 目錄路徑")
    original_pdf_path: str = Field(..., description="原始 PDF 路徑")
    
    # 建構資訊
    created_at: str = Field(..., description="建立時間 ISO 格式")
    builder_version: str = Field(default="1.0.0", description="Paper Skill Builder 版本")
    
    class Config:
        json_schema_extra = {
            "example": {
                "paper_id": "arxiv:2401.12345",
                "skill_name": "paper-mrag",
                "skill_description": "Use this skill when the user asks about MRAG, graph connectivity in GraphRAG, or multi-hop retrieval",
                "tags": ["graphrag", "retrieval", "multi-hop"],
                "reference_guides": [
                    {
                        "filename": "problem_and_motivation.md",
                        "description": "研究問題與動機",
                        "query_types": ["what problem does it solve", "motivation", "limitation"]
                    },
                    {
                        "filename": "method_guide.md",
                        "description": "方法詳細說明",
                        "query_types": ["how does it work", "method intuition", "algorithm"]
                    },
                    {
                        "filename": "experiment_guide.md",
                        "description": "實驗設計與結果",
                        "query_types": ["experiments", "results", "ablation"]
                    },
                    {
                        "filename": "benchmark_and_baselines.md",
                        "description": "Benchmark 與 Baseline 比較",
                        "query_types": ["benchmark", "dataset", "baseline comparison"]
                    },
                    {
                        "filename": "figures_and_tables.md",
                        "description": "重要圖表",
                        "query_types": ["figure", "table", "visual evidence"]
                    },
                    {
                        "filename": "limitations.md",
                        "description": "局限性與未來工作",
                        "query_types": ["limitation", "future work"]
                    }
                ],
                "routing_policies": [
                    {
                        "query_pattern": "What is this paper about",
                        "target_file": "paper_profile.json",
                        "fallback_to_pdf": False
                    },
                    {
                        "query_pattern": "How does the method work",
                        "target_file": "references/method_guide.md",
                        "fallback_to_pdf": True
                    }
                ],
                "section_index": [
                    {
                        "section_name": "Introduction",
                        "pdf_page_start": 1,
                        "pdf_page_end": 2,
                        "markdown_anchor": "# Introduction"
                    },
                    {
                        "section_name": "Method",
                        "pdf_page_start": 3,
                        "pdf_page_end": 6,
                        "markdown_anchor": "# Methodology"
                    }
                ],
                "evidence_index": [
                    {
                        "evidence_id": "fig1",
                        "evidence_type": "figure",
                        "caption": "System architecture",
                        "pdf_page": 3,
                        "section": "Method"
                    }
                ],
                "skill_md_path": "paper_skills/arxiv_2401_12345/SKILL.md",
                "metadata_json_path": "paper_skills/arxiv_2401_12345/metadata.json",
                "paper_profile_path": "paper_skills/arxiv_2401_12345/paper_profile.json",
                "references_dir": "paper_skills/arxiv_2401_12345/references/",
                "original_pdf_path": "paper_skills/arxiv_2401_12345/original.pdf",
                "created_at": "2024-01-15T10:30:00Z",
                "builder_version": "1.0.0"
            }
        }
