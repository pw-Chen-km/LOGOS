"""Survey Taxonomy Schema

Module 3: Survey Taxonomy Generator 的輸出格式。
從 paper pool 產生 research landscape 的分類與矩陣。
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class Theme(BaseModel):
    """研究主題"""
    theme_id: str = Field(..., description="主題唯一 ID")
    name: str = Field(..., description="主題名稱")
    description: str = Field(..., description="主題描述")
    keywords: List[str] = Field(default_factory=list, description="主題相關關鍵字")


class SubTheme(BaseModel):
    """子主題"""
    subtheme_id: str = Field(..., description="子主題唯一 ID")
    theme_id: str = Field(..., description="所屬主題 ID")
    name: str = Field(..., description="子主題名稱")
    description: str = Field(..., description="子主題描述")


class PaperTaxonomyAssignment(BaseModel):
    """論文分類分配"""
    paper_id: str = Field(..., description="論文 ID")
    theme_id: str = Field(..., description="主題 ID")
    subtheme_id: Optional[str] = Field(None, description="子主題 ID（可選）")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="分類信心分數")


class MethodFamily(BaseModel):
    """方法家族"""
    family_id: str = Field(..., description="家族唯一 ID")
    name: str = Field(..., description="方法家族名稱")
    description: str = Field(..., description="描述")
    representative_papers: List[str] = Field(default_factory=list, description="代表性論文 IDs")


class ProblemCluster(BaseModel):
    """問題群集"""
    cluster_id: str = Field(..., description="群集唯一 ID")
    problem_summary: str = Field(..., description="問題摘要")
    related_papers: List[str] = Field(default_factory=list, description="相關論文 IDs")


class BenchmarkMatrixEntry(BaseModel):
    """Benchmark 矩陣項目"""
    benchmark_name: str = Field(..., description="Benchmark 名稱")
    paper_ids: List[str] = Field(default_factory=list, description="使用此 benchmark 的論文")
    metric_names: List[str] = Field(default_factory=list, description="評估指標")


class DatasetMatrixEntry(BaseModel):
    """Dataset 矩陣項目"""
    dataset_name: str = Field(..., description="Dataset 名稱")
    paper_ids: List[str] = Field(default_factory=list, description="使用此 dataset 的論文")
    task_types: List[str] = Field(default_factory=list, description="相關任務類型")


class BaselineMatrixEntry(BaseModel):
    """Baseline 矩陣項目"""
    baseline_name: str = Field(..., description="Baseline 方法名稱")
    paper_ids: List[str] = Field(default_factory=list, description="與此 baseline 比較的論文")


class CandidateRelation(BaseModel):
    """候選論文關係
    
    由 Survey Taxonomy Generator 產生的 cheap candidate relation，
    尚未經過 expensive verification。
    """
    source_paper_id: str = Field(..., description="來源論文 ID")
    target_paper_id: str = Field(..., description="目標論文 ID")
    relation_type: str = Field(
        ...,
        description="關係類型",
        pattern="^(same_method_family|same_benchmark|related_problem|common_baseline)$"
    )
    status: str = Field(
        default="candidate",
        description="狀態: candidate | verified | rejected",
        pattern="^(candidate|verified|rejected)$"
    )
    source: str = Field(default="survey_taxonomy", description="來源: survey_taxonomy | edge_verifier | user")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="信心分數")
    rationale: Optional[str] = Field(None, description="關係推論理由")


class SurveyTaxonomy(BaseModel):
    """Survey Taxonomy Output
    
    Module 3 的完整輸出，包含研究主題分類、方法家族、問題群集、
    benchmark/dataset/baseline 矩陣，以及候選論文關係。
    """
    taxonomy_id: str = Field(..., description="分類 ID")
    request_id: str = Field(..., description="對應的 ResearchRequest ID")
    
    # 主題分類
    themes: List[Theme] = Field(default_factory=list)
    subthemes: List[SubTheme] = Field(default_factory=list)
    paper_assignments: List[PaperTaxonomyAssignment] = Field(default_factory=list)
    
    # 方法與問題
    method_families: List[MethodFamily] = Field(default_factory=list)
    problem_clusters: List[ProblemCluster] = Field(default_factory=list)
    
    # 評估矩陣
    benchmark_matrix: List[BenchmarkMatrixEntry] = Field(default_factory=list)
    dataset_matrix: List[DatasetMatrixEntry] = Field(default_factory=list)
    baseline_matrix: List[BaselineMatrixEntry] = Field(default_factory=list)
    
    # 候選關係
    candidate_relations: List[CandidateRelation] = Field(default_factory=list)
    
    class Config:
        json_schema_extra = {
            "example": {
                "taxonomy_id": "tax_001",
                "request_id": "req_2024_001",
                "themes": [
                    {
                        "theme_id": "T1",
                        "name": "Graph-based Retrieval",
                        "description": "利用圖結構進行資訊檢索的方法",
                        "keywords": ["graph traversal", "entity linking", "relation extraction"]
                    }
                ],
                "subthemes": [
                    {
                        "subtheme_id": "ST1_1",
                        "theme_id": "T1",
                        "name": "Graph Neural Networks for Retrieval",
                        "description": "使用 GNN 改善檢索表現"
                    }
                ],
                "paper_assignments": [
                    {
                        "paper_id": "arxiv:2401.12345",
                        "theme_id": "T1",
                        "subtheme_id": "ST1_1",
                        "confidence": 0.92
                    }
                ],
                "method_families": [
                    {
                        "family_id": "MF1",
                        "name": "Spectral Graph Methods",
                        "description": "基於譜圖理論的方法",
                        "representative_papers": ["arxiv:2401.12345"]
                    }
                ],
                "candidate_relations": [
                    {
                        "source_paper_id": "arxiv:2401.12345",
                        "target_paper_id": "arxiv:2402.67890",
                        "relation_type": "same_benchmark",
                        "status": "candidate",
                        "source": "survey_taxonomy",
                        "confidence": 0.72,
                        "rationale": "兩篇論文都使用 HotpotQA benchmark"
                    }
                ]
            }
        }
