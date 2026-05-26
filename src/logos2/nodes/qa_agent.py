"""QA Agent

Module 7: QA Agent

透過 lightweight graph index 找到 relevant paper，
再透過 Paper Skill Pack 決定要讀哪裡。

Progressive disclosure:
Graph search -> paper_profile.json -> SKILL.md -> reference guide -> PDF

Query types supported:
- single_paper_summary
- single_paper_problem
- method_intuition
- technical_detail
- experiment_evidence
- benchmark_comparison
- table_or_figure_question
- cross_paper_comparison
- research_gap
- survey_landscape
"""

import json
import re
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

from ..schemas import PaperProfile, VerifiedEdge, PaperSkillManifest
from ..storage import GraphRepositoryProtocol, SQLiteGraphRepository, SkillRegistry
from ..extraction import DoclingExtractor
from .deep_reader import OnDemandDeepReaderAgent, DeepReadingResult


@dataclass
class QAResult:
    """QA 結果"""
    answer: str
    source_paper_ids: List[str]
    files_read: List[str]
    confidence: float
    needs_verification: bool = False
    verification_edge: Optional[VerifiedEdge] = None


class QAAgent:
    """QA Agent
    
    根據使用者問題：
    1. Query classifier: 分類問題類型
    2. Search graph index: 找到相關論文
    3. Open paper skill: 讀取 SKILL.md
    4. Follow routing policy: 決定讀哪個檔案
    5. Read reference file 或 fallback 到 PDF
    6. 回答並標註來源
    
    PDF/section fallback uses OnDemandDeepReaderAgent with Docling extraction output.
    """
    
    def __init__(
        self,
        repository: Optional[GraphRepositoryProtocol] = None,
        skill_registry: Optional[SkillRegistry] = None,
        paper_library_dir: str = "paper_library"
    ):
        """
        Args:
            repository: graph repository 實例
            skill_registry: SkillRegistry 實例
            paper_library_dir: Docling extraction output directory
        """
        self.repository = repository or SQLiteGraphRepository()
        self.registry = skill_registry or SkillRegistry()
        self.paper_library_dir = Path(paper_library_dir)
        self.deep_reader = OnDemandDeepReaderAgent()
    
    def answer(self, query: str) -> QAResult:
        """回答使用者問題
        
        Args:
            query: 使用者問題
            
        Returns:
            QAResult: 答案與來源資訊
        """
        try:
            self.repository.connect()
            
            # 1. 分類問題類型
            query_type = self._classify_query(query)
            
            # 2. 搜尋相關論文
            paper_candidates = self._search_papers(query, query_type)
            
            if not paper_candidates:
                return QAResult(
                    answer="No relevant papers found in the knowledge base.",
                    source_paper_ids=[],
                    files_read=[],
                    confidence=0.0
                )
            
            # 3. 選擇主要論文（MVP：選第一個，未來可排序）
            main_paper = paper_candidates[0]
            paper_id = main_paper.get("paper_id")
            
            # 4. 根據問題類型 routing
            answer_data = self._route_and_answer(query, query_type, paper_id)
            
            # 5. 檢查是否需要 cross-paper comparison
            if query_type in ["cross_paper_comparison", "survey_landscape"] and len(paper_candidates) > 1:
                comparison_data = self._add_comparison_context(query, paper_candidates)
                answer_data["answer"] += "\n\n" + comparison_data
            
            return QAResult(
                answer=answer_data["answer"],
                source_paper_ids=[paper_id],
                files_read=answer_data["files_read"],
                confidence=answer_data["confidence"],
                needs_verification=answer_data.get("needs_verification", False)
            )
            
        finally:
            self.repository.close()
    
    def _classify_query(self, query: str) -> str:
        """分類問題類型
        
        MVP: 基於關鍵字規則分類
        """
        query_lower = query.lower()
        
        # Cross-paper comparison patterns
        if any(word in query_lower for word in ["compare", "vs", "versus", "difference between", "similar to"]):
            return "cross_paper_comparison"
        
        # Benchmark comparison patterns
        if any(word in query_lower for word in ["benchmark", "performance", "accuracy", "f1", "em", "score"]):
            return "benchmark_comparison"
        
        # Table/Figure patterns
        if any(word in query_lower for word in ["table", "figure", "fig", "diagram", "chart"]):
            return "table_or_figure_question"
        
        # Method patterns
        if any(word in query_lower for word in ["how does", "algorithm", "method", "approach", "technique"]):
            return "method_intuition"
        
        # Technical detail patterns
        if any(word in query_lower for word in ["implementation", "equation", "formula", "parameter", "hyperparameter"]):
            return "technical_detail"
        
        # Experiment patterns
        if any(word in query_lower for word in ["experiment", "ablation", "evaluation", "result", "metrics"]):
            return "experiment_evidence"
        
        # Problem patterns
        if any(word in query_lower for word in ["problem", "motivation", "why", "challenge", "issue"]):
            return "single_paper_problem"
        
        # Survey/landscape patterns
        if any(word in query_lower for word in ["landscape", "survey", "overview", "state of the art", "sota"]):
            return "survey_landscape"
        
        # Default: summary
        return "single_paper_summary"
    
    def _search_papers(self, query: str, query_type: str) -> List[Dict[str, Any]]:
        """搜尋相關論文
        
        策略：
        - 先嘗試全文搜尋
        - 若無結果，嘗試主題/方法家族搜尋
        """
        # 嘗試全文搜尋
        results = self.repository.fulltext_search_papers(query, limit=5)
        
        if results:
            return results
        
        # 嘗試依主題搜尋（從 query 抽取主題關鍵字）
        # MVP: 簡化版本
        themes = self._extract_themes_from_query(query)
        for theme in themes:
            results = self.repository.search_papers_by_theme(theme)
            if results:
                return results
        
        return []
    
    def _extract_themes_from_query(self, query: str) -> List[str]:
        """從 query 抽取可能的主題"""
        # MVP: 常見研究主題關鍵字
        common_themes = [
            "graph", "retrieval", "generation", "attention", "transformer",
            "gnn", "rag", "llm", "knowledge", "language model"
        ]
        
        found = []
        query_lower = query.lower()
        for theme in common_themes:
            if theme in query_lower:
                found.append(theme)
        
        return found[:2]  # 最多 2 個主題
    
    def _route_and_answer(
        self,
        query: str,
        query_type: str,
        paper_id: str
    ) -> Dict[str, Any]:
        """根據問題類型 routing 並回答
        
        根據 query_type 決定：
        - 讀什麼檔案
        - 是否 fallback 到 PDF
        """
        files_read = []
        
        # 總是讀 paper_profile.json（fast answer scope）
        profile = self.registry.load_profile(paper_id)
        if profile:
            files_read.append("paper_profile.json")
        skill_md = self._read_file(paper_id, "SKILL.md")
        if skill_md:
            files_read.append("SKILL.md")
        
        # 根據 query_type 決定 routing
        routing_map = {
            "single_paper_summary": ("paper_profile.json", False),
            "single_paper_problem": ("references/problem_and_motivation.md", True),
            "method_intuition": ("references/method_guide.md", True),
            "technical_detail": ("references/method_guide.md", True),
            "experiment_evidence": ("references/experiment_guide.md", True),
            "benchmark_comparison": ("references/benchmark_and_baselines.md", True),
            "table_or_figure_question": ("references/figures_and_tables.md", True),
            "cross_paper_comparison": ("paper_profile.json", False),
            "survey_landscape": ("paper_profile.json", False),
        }
        
        target_file, allow_pdf_fallback = routing_map.get(query_type, ("paper_profile.json", False))
        progressive_target = self._select_progressive_reference(paper_id, query_type, query)
        if progressive_target:
            target_file = progressive_target
            allow_pdf_fallback = True
        
        # 讀取 target file
        content = self._read_file(paper_id, target_file)
        if content:
            files_read.append(target_file)
        
        # 若內容不足且允許 fallback，嘗試 PDF
        if not content and allow_pdf_fallback:
            pdf_content = self._read_pdf_section(
                paper_id=paper_id,
                section_type=query_type,
                query=query  # Pass full query for intelligent matching
            )
            if pdf_content:
                content = pdf_content
                files_read.append("original.pdf")
        
        # 產生答案
        if content:
            answer = self._generate_answer(query, content, profile, query_type)
            confidence = 0.8 if target_file != "original.pdf" else 0.6
        else:
            answer = f"Found paper '{profile.title if profile else paper_id}' but detailed information is not available. Please check the original PDF."
            confidence = 0.3
        
        return {
            "answer": answer,
            "files_read": files_read,
            "confidence": confidence,
            "needs_verification": query_type == "cross_paper_comparison"
        }
    
    def _read_file(self, paper_id: str, filename: str) -> Optional[str]:
        """讀取指定檔案"""
        skill_path = self.registry.get_skill_path(paper_id)
        if not skill_path:
            return None
        
        if filename == "paper_profile.json":
            file_path = Path(skill_path).parent / "paper_profile.json"
        elif filename == "SKILL.md":
            file_path = Path(skill_path)
        else:
            refs_dir = Path(skill_path).parent / "references"
            file_path = refs_dir / filename.replace("references/", "")
        
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                if filename.endswith(".json"):
                    data = json.load(f)
                    return json.dumps(data, indent=2)
                else:
                    return f.read()
        
        return None

    def _select_progressive_reference(
        self,
        paper_id: str,
        query_type: str,
        query: str,
    ) -> Optional[str]:
        """Select a section/table/figure reference from reference_manifest.json."""
        skill_path = self.registry.get_skill_path(paper_id)
        if not skill_path:
            return None
        manifest_path = Path(skill_path).parent / "references" / "reference_manifest.json"
        if not manifest_path.exists():
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        wanted = {
            "single_paper_summary": ["summary", "overview"],
            "single_paper_problem": ["motivation", "research_problem"],
            "method_intuition": ["method", "algorithm", "technical_detail"],
            "technical_detail": ["technical_detail", "algorithm", "method"],
            "experiment_evidence": ["experiments", "datasets", "metrics"],
            "benchmark_comparison": ["results", "comparison", "experiments", "exact_values"],
            "table_or_figure_question": ["table_or_figure", "visual_evidence", "exact_values"],
        }.get(query_type, [])

        query_lower = query.lower()
        if any(term in query_lower for term in ["table", "score", "accuracy", "result", "metric"]):
            for table in manifest.get("tables", []):
                return table.get("path")
        if any(term in query_lower for term in ["figure", "fig", "diagram", "architecture"]):
            for figure in manifest.get("figures", []):
                return figure.get("path")

        for section in manifest.get("sections", []):
            intents = section.get("query_intents", [])
            title = str(section.get("title", "")).lower()
            if any(intent in intents for intent in wanted):
                return section.get("path")
            if title and any(token in title for token in query_lower.split()):
                return section.get("path")

        return manifest.get("document_path")
    
    def _read_pdf_section(
        self,
        paper_id: str,
        section_type: str,
        query: str = ""
    ) -> Optional[str]:
        """讀取 PDF section using OnDemandDeepReaderAgent
        
        Uses Docling extraction output (document.md, section_index.json, evidence_index.json)
        to read actual section content.
        
        Args:
            paper_id: Paper ID
            section_type: Section type (e.g., "method", "experiment")
            query: Original query for intelligent matching
            
        Returns:
            Section content as string, or None if unavailable
        """
        # Find extraction directory
        safe_id = paper_id.replace(":", "_").replace("/", "_")
        extraction_dir = self.paper_library_dir / safe_id
        
        if not extraction_dir.exists():
            return None
        
        # Check if extraction exists
        if not (extraction_dir / "extraction_meta.json").exists():
            return None
        
        # Load skill manifest for indexes
        skill_path = self.registry.get_skill_path(paper_id)
        if not skill_path:
            return None
        
        skill_dir = Path(skill_path).parent
        section_index_path = skill_dir / "section_index.json"
        evidence_index_path = skill_dir / "evidence_index.json"
        
        # Load indexes
        section_indexes = []
        evidence_indexes = []
        
        if section_index_path.exists():
            import json
            with open(section_index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                from ..schemas import SectionIndex
                section_indexes = [SectionIndex(**item) for item in data]
        
        if evidence_index_path.exists():
            import json
            with open(evidence_index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                from ..schemas import EvidenceIndex
                evidence_indexes = [EvidenceIndex(**item) for item in data]
        
        # Create minimal manifest for deep reader
        manifest = PaperSkillManifest(
            paper_id=paper_id,
            skill_name=f"paper-{safe_id}",
            skill_description="",
            skill_md_path=str(skill_path),
            metadata_json_path=str(skill_dir / "metadata.json"),
            paper_profile_path=str(skill_dir / "paper_profile.json"),
            references_dir=str(skill_dir / "references"),
            original_pdf_path=str(extraction_dir / "original.pdf"),
            section_index=section_indexes,
            evidence_index=evidence_indexes,
            created_at="",
        )
        
        # Use deep reader to find and read content
        if query:
            result = self.deep_reader.find_and_read(
                query=query,
                skill_manifest=manifest,
                extraction_dir=extraction_dir
            )
        else:
            # Try to read section by type
            section_name = self._map_section_type(section_type)
            result = self.deep_reader.read_section(
                skill_manifest=manifest,
                section_name=section_name,
                extraction_dir=extraction_dir
            )
        
        if result:
            return result.content
        
        return None
    
    def _map_section_type(self, section_type: str) -> str:
        """Map query section type to common section names"""
        mapping = {
            "method": "Method",
            "methodology": "Method",
            "approach": "Method",
            "experiment": "Experiments",
            "experiments": "Experiments",
            "results": "Results",
            "evaluation": "Evaluation",
            "ablation": "Ablation",
            "problem": "Introduction",
            "motivation": "Introduction",
            "related work": "Related Work",
            "conclusion": "Conclusion",
        }
        return mapping.get(section_type.lower(), section_type.capitalize())
    
    def _generate_answer(
        self,
        query: str,
        content: str,
        profile: Optional[PaperProfile],
        query_type: str
    ) -> str:
        """產生答案
        
        MVP: 基於 template 的答案生成
        未來版本可整合 LLM 進行 synthesis
        """
        paper_title = profile.title if profile else "the paper"
        
        if query_type == "single_paper_summary":
            return f"Based on {paper_title}:\n\n{content[:500]}...\n\n[Source: paper_profile.json]"
        
        elif query_type == "single_paper_problem":
            return f"The research problem addressed in {paper_title}:\n\n{content[:800]}...\n\n[Source: references/problem_and_motivation.md]"
        
        elif query_type == "method_intuition":
            return f"Method overview for {paper_title}:\n\n{content[:800]}...\n\n[Source: references/method_guide.md]"
        
        elif query_type == "experiment_evidence":
            return f"Experimental evidence from {paper_title}:\n\n{content[:800]}...\n\n[Source: references/experiment_guide.md]"
        
        elif query_type == "benchmark_comparison":
            return f"Benchmark results from {paper_title}:\n\n{content[:800]}...\n\n[Source: references/benchmark_and_baselines.md]"
        
        else:
            return f"Regarding '{query}' from {paper_title}:\n\n{content[:800]}...\n\n[Source: extracted content]"
    
    def _add_comparison_context(
        self,
        query: str,
        paper_candidates: List[Dict[str, Any]]
    ) -> str:
        """加入跨論文比較上下文"""
        papers_info = []
        for p in paper_candidates[:3]:  # 最多 3 篇
            profile = self.registry.load_profile(p.get("paper_id"))
            if profile:
                papers_info.append(f"- {profile.title}: {profile.tldr}")
        
        if papers_info:
            return "Related papers:\n" + "\n".join(papers_info)
        
        return ""
    
    def close(self):
        """關閉連線"""
        self.repository.close()
