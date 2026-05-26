"""Survey Taxonomy Generator

Module 3: Survey Taxonomy Generator

從 paper pool 產生 research landscape，輸出：
- themes, subthemes
- taxonomy paths
- method families
- problem clusters
- benchmark/dataset/baseline matrix
- candidate paper relations

MVP 策略：
- 先以 LLM structured output 實作
- 之後可接外部 research-survey 技能或 deterministic clustering
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from ..schemas import (
    SurveyTaxonomy,
    Theme,
    SubTheme,
    PaperTaxonomyAssignment,
    MethodFamily,
    ProblemCluster,
    BenchmarkMatrixEntry,
    DatasetMatrixEntry,
    BaselineMatrixEntry,
    CandidateRelation,
    PaperNavigatorReading,
)


class SurveyTaxonomyGenerator:
    """Survey Taxonomy Generator
    
    根據 paper-navigator reading artifacts 產生研究領域的：
    1. 主題分類（themes, subthemes）
    2. 方法家族（method families）
    3. 問題群集（problem clusters）
    4. 評估矩陣（benchmark/dataset/baseline）
    5. 候選論文關係（cheap candidate relations）
    """
    
    def __init__(self, output_dir: str = "artifacts"):
        """
        Args:
            output_dir: 輸出目錄
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate(
        self,
        readings: List[PaperNavigatorReading],
        request_id: str,
        taxonomy_id: Optional[str] = None
    ) -> SurveyTaxonomy:
        """從 paper readings 產生 survey taxonomy
        
        MVP 版本使用基於規則的方法：
        - 從 benchmark_names, dataset_names, baseline_names 建立矩陣
        - 從 method_intuition 抽取 method family 關鍵字
        - 從 problem_statement 群集問題
        
        未來版本可整合 LLM 或 external research-survey skill。
        
        Args:
            readings: paper-navigator reading artifacts
            request_id: 對應的 ResearchRequest ID
            taxonomy_id: 自訂 taxonomy ID（可選）
            
        Returns:
            SurveyTaxonomy: 完整的分類與矩陣
        """
        if not readings:
            raise ValueError("No readings provided for taxonomy generation")
        
        taxonomy_id = taxonomy_id or f"tax_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 1. 建立評估矩陣（基於規則）
        benchmark_matrix = self._build_benchmark_matrix(readings)
        dataset_matrix = self._build_dataset_matrix(readings)
        baseline_matrix = self._build_baseline_matrix(readings)
        
        # 2. 建立方法家族（基於關鍵字群集）
        method_families = self._extract_method_families(readings)
        
        # 3. 建立問題群集
        problem_clusters = self._cluster_problems(readings)
        
        # 4. 建立主題（從 method families 和 problems 綜合）
        themes, subthemes = self._build_themes(readings, method_families)
        
        # 5. 分配論文到主題
        paper_assignments = self._assign_papers_to_themes(readings, themes, subthemes)
        
        # 6. 產生候選關係（cheap candidate relations）
        candidate_relations = self._generate_candidate_relations(
            readings, benchmark_matrix, dataset_matrix, baseline_matrix, method_families
        )
        
        taxonomy = SurveyTaxonomy(
            taxonomy_id=taxonomy_id,
            request_id=request_id,
            themes=themes,
            subthemes=subthemes,
            paper_assignments=paper_assignments,
            method_families=method_families,
            problem_clusters=problem_clusters,
            benchmark_matrix=benchmark_matrix,
            dataset_matrix=dataset_matrix,
            baseline_matrix=baseline_matrix,
            candidate_relations=candidate_relations,
        )
        
        # 儲存輸出
        self._save_taxonomy(taxonomy)
        
        return taxonomy
    
    def _build_benchmark_matrix(
        self,
        readings: List[PaperNavigatorReading]
    ) -> List[BenchmarkMatrixEntry]:
        """建立 benchmark 矩陣"""
        benchmark_to_papers: Dict[str, Dict[str, Any]] = {}
        
        for reading in readings:
            for bench in reading.benchmark_names:
                if bench not in benchmark_to_papers:
                    benchmark_to_papers[bench] = {"papers": [], "metrics": set()}
                benchmark_to_papers[bench]["papers"].append(reading.paper_id)
        
        return [
            BenchmarkMatrixEntry(
                benchmark_name=bench,
                paper_ids=data["papers"],
                metric_names=list(data["metrics"])
            )
            for bench, data in benchmark_to_papers.items()
        ]
    
    def _build_dataset_matrix(
        self,
        readings: List[PaperNavigatorReading]
    ) -> List[DatasetMatrixEntry]:
        """建立 dataset 矩陣"""
        dataset_to_papers: Dict[str, Dict[str, Any]] = {}
        
        for reading in readings:
            for dataset in reading.dataset_names:
                if dataset not in dataset_to_papers:
                    dataset_to_papers[dataset] = {"papers": [], "tasks": set()}
                dataset_to_papers[dataset]["papers"].append(reading.paper_id)
        
        return [
            DatasetMatrixEntry(
                dataset_name=dataset,
                paper_ids=data["papers"],
                task_types=list(data["tasks"])
            )
            for dataset, data in dataset_to_papers.items()
        ]
    
    def _build_baseline_matrix(
        self,
        readings: List[PaperNavigatorReading]
    ) -> List[BaselineMatrixEntry]:
        """建立 baseline 矩陣"""
        baseline_to_papers: Dict[str, List[str]] = {}
        
        for reading in readings:
            for baseline in reading.baseline_names:
                if baseline not in baseline_to_papers:
                    baseline_to_papers[baseline] = []
                baseline_to_papers[baseline].append(reading.paper_id)
        
        return [
            BaselineMatrixEntry(baseline_name=baseline, paper_ids=papers)
            for baseline, papers in baseline_to_papers.items()
        ]
    
    def _extract_method_families(
        self,
        readings: List[PaperNavigatorReading]
    ) -> List[MethodFamily]:
        """抽取方法家族（MVP：簡化版本）"""
        # 從 method_intuition 抽取關鍵方法關鍵字
        method_keywords = {}
        
        for reading in readings:
            if reading.method_intuition:
                # 簡化：使用論文標題中的方法相關關鍵字
                # 未來版本可用 LLM 抽取
                keywords = self._extract_keywords_from_text(reading.method_intuition)
                for kw in keywords:
                    if kw not in method_keywords:
                        method_keywords[kw] = []
                    method_keywords[kw].append(reading.paper_id)
        
        # 建立方法家族（只有超過 1 篇論文的方法）
        families = []
        for idx, (keyword, papers) in enumerate(method_keywords.items()):
            if len(papers) >= 1:  # MVP：只要有論文就建立
                families.append(MethodFamily(
                    family_id=f"MF{idx+1}",
                    name=keyword,
                    description=f"Papers related to {keyword} methods",
                    representative_papers=papers[:5]  # 最多 5 篇代表
                ))
        
        return families[:10]  # MVP：最多 10 個方法家族
    
    def _cluster_problems(
        self,
        readings: List[PaperNavigatorReading]
    ) -> List[ProblemCluster]:
        """問題群集（MVP：簡化版本）"""
        # 從 problem_statement 群集
        problem_keywords = {}
        
        for reading in readings:
            if reading.problem_statement:
                keywords = self._extract_keywords_from_text(reading.problem_statement)
                for kw in keywords:
                    if kw not in problem_keywords:
                        problem_keywords[kw] = []
                    problem_keywords[kw].append(reading.paper_id)
        
        clusters = []
        for idx, (keyword, papers) in enumerate(problem_keywords.items()):
            if len(papers) >= 2:  # 至少 2 篇論文才形成群集
                clusters.append(ProblemCluster(
                    cluster_id=f"PC{idx+1}",
                    problem_summary=f"Papers addressing {keyword} challenges",
                    related_papers=papers
                ))
        
        return clusters[:10]  # MVP：最多 10 個問題群集
    
    def _build_themes(
        self,
        readings: List[PaperNavigatorReading],
        method_families: List[MethodFamily]
    ) -> tuple[List[Theme], List[SubTheme]]:
        """建立主題與子主題"""
        # MVP：簡化版本，從方法家族建立主題
        themes = []
        subthemes = []
        
        # 建立主題（最多 5 個主要方法家族成為主題）
        for idx, family in enumerate(method_families[:5]):
            theme = Theme(
                theme_id=f"T{idx+1}",
                name=family.name,
                description=family.description,
                keywords=[family.name]
            )
            themes.append(theme)
        
        # 若沒有足夠的方法家族，從論文問題建立主題
        if len(themes) < 3:
            for idx, reading in enumerate(readings[:3]):
                if reading.problem_statement:
                    theme_id = f"T{len(themes)+1}"
                    theme = Theme(
                        theme_id=theme_id,
                        name=f"Theme {theme_id}",
                        description=reading.problem_statement[:100],
                        keywords=[]
                    )
                    themes.append(theme)
        
        return themes, subthemes
    
    def _assign_papers_to_themes(
        self,
        readings: List[PaperNavigatorReading],
        themes: List[Theme],
        subthemes: List[SubTheme]
    ) -> List[PaperTaxonomyAssignment]:
        """分配論文到主題"""
        assignments = []
        
        for reading in readings:
            # 簡化分配：根據方法相似性分配
            best_theme = None
            best_confidence = 0.5
            
            for theme in themes:
                # 檢查論文是否與主題關鍵字匹配
                if reading.method_intuition and theme.keywords:
                    for keyword in theme.keywords:
                        if keyword.lower() in reading.method_intuition.lower():
                            best_theme = theme
                            best_confidence = 0.8
                            break
            
            if best_theme:
                assignments.append(PaperTaxonomyAssignment(
                    paper_id=reading.paper_id,
                    theme_id=best_theme.theme_id,
                    subtheme_id=None,
                    confidence=best_confidence
                ))
        
        return assignments
    
    def _generate_candidate_relations(
        self,
        readings: List[PaperNavigatorReading],
        benchmark_matrix: List[BenchmarkMatrixEntry],
        dataset_matrix: List[DatasetMatrixEntry],
        baseline_matrix: List[BaselineMatrixEntry],
        method_families: List[MethodFamily]
    ) -> List[CandidateRelation]:
        """產生候選論文關係（cheap candidates）"""
        relations = []
        
        # 1. same_benchmark 關係
        for entry in benchmark_matrix:
            papers = entry.paper_ids
            for i, paper_a in enumerate(papers):
                for paper_b in papers[i+1:]:
                    relations.append(CandidateRelation(
                        source_paper_id=paper_a,
                        target_paper_id=paper_b,
                        relation_type="same_benchmark",
                        status="candidate",
                        source="survey_taxonomy",
                        confidence=0.7,
                        rationale=f"Both papers evaluated on {entry.benchmark_name}"
                    ))
        
        # 2. same_benchmark via dataset 關係
        for entry in dataset_matrix:
            papers = entry.paper_ids
            for i, paper_a in enumerate(papers):
                for paper_b in papers[i+1:]:
                    # 檢查是否已存在
                    exists = any(
                        r.source_paper_id == paper_a and r.target_paper_id == paper_b
                        and r.relation_type == "same_benchmark"
                        for r in relations
                    )
                    if not exists:
                        relations.append(CandidateRelation(
                            source_paper_id=paper_a,
                            target_paper_id=paper_b,
                            relation_type="same_benchmark",
                            status="candidate",
                            source="survey_taxonomy",
                            confidence=0.6,
                            rationale=f"Both papers use {entry.dataset_name} dataset"
                        ))
        
        # 3. common_baseline 關係
        for entry in baseline_matrix:
            papers = entry.paper_ids
            for i, paper_a in enumerate(papers):
                for paper_b in papers[i+1:]:
                    relations.append(CandidateRelation(
                        source_paper_id=paper_a,
                        target_paper_id=paper_b,
                        relation_type="common_baseline",
                        status="candidate",
                        source="survey_taxonomy",
                        confidence=0.65,
                        rationale=f"Both papers compare against {entry.baseline_name}"
                    ))
        
        # 4. same_method_family 關係
        for family in method_families:
            papers = family.representative_papers
            for i, paper_a in enumerate(papers):
                for paper_b in papers[i+1:]:
                    relations.append(CandidateRelation(
                        source_paper_id=paper_a,
                        target_paper_id=paper_b,
                        relation_type="same_method_family",
                        status="candidate",
                        source="survey_taxonomy",
                        confidence=0.75,
                        rationale=f"Both papers in {family.name} method family"
                    ))
        
        return relations[:100]  # MVP：最多 100 個候選關係
    
    def _extract_keywords_from_text(self, text: str) -> List[str]:
        """從文字抽取關鍵字（MVP：簡化版本）"""
        # 簡化實作：抽取常見方法關鍵字
        common_keywords = [
            "graph", "retrieval", "generation", "attention", "transformer",
            "gnn", "embedding", "vector", "neural", "language model",
            "rag", "llm", "knowledge", "query", "index"
        ]
        
        found = []
        text_lower = text.lower()
        for keyword in common_keywords:
            if keyword in text_lower:
                found.append(keyword)
        
        return found[:5]  # 最多 5 個關鍵字
    
    def _save_taxonomy(self, taxonomy: SurveyTaxonomy):
        """儲存 taxonomy 到檔案"""
        output_file = self.output_dir / f"{taxonomy.taxonomy_id}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(taxonomy.model_dump(), f, indent=2, ensure_ascii=False)
    
    def load_taxonomy(self, taxonomy_id: str) -> SurveyTaxonomy:
        """從檔案載入 taxonomy"""
        input_file = self.output_dir / f"{taxonomy_id}.json"
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return SurveyTaxonomy(**data)
