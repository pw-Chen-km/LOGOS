"""Profile Normalizer

Module 4: LOGOS Profile Normalizer

將 paper-navigator reading output 與 survey taxonomy output 正規化成
LOGOS 可用的 paper_profile.json。

設計原則：
1. 不重複 LLM parsing
2. 直接使用 paper-navigator 的 reading output
3. 直接使用 survey taxonomy 的 taxonomy / method family / benchmark matrix
4. 缺漏資訊只標記 missing_fields，不立即補抽
5. 只有 QA 或 verification 需要時才啟動 on-demand deep parser
"""

import json
import re
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from ..schemas import (
    PaperProfile,
    PaperRelation,
    PaperNavigatorReading,
    SurveyTaxonomy,
)


class ProfileNormalizer:
    """Profile Normalizer
    
    合併 paper-navigator reading output 與 survey taxonomy，
    產生每篇論文的統一 paper_profile.json。
    """
    
    def __init__(self, output_dir: str = "paper_skills"):
        """
        Args:
            output_dir: paper_profile.json 輸出目錄
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def normalize(
        self,
        reading: PaperNavigatorReading,
        taxonomy: SurveyTaxonomy,
        paper_metadata: Optional[Dict[str, Any]] = None
    ) -> PaperProfile:
        """將單篇論文的 reading 與 taxonomy 合併為 profile
        
        Args:
            reading: paper-navigator reading artifact
            taxonomy: survey taxonomy（包含該論文的 assignment 與 relations）
            paper_metadata: 額外論文元資料（作者、年份、venue 等）
            
        Returns:
            PaperProfile: 統一的論文 profile
        """
        paper_id = reading.paper_id
        
        # 從 taxonomy 找到該論文的資訊
        theme, taxonomy_path = self._get_theme_info(paper_id, taxonomy)
        method_family = self._get_method_family(paper_id, taxonomy)
        relations = self._get_relations(paper_id, taxonomy)
        
        # 合併元資料；支援 dict 或 PaperMetadata/Pydantic object。
        metadata = self._metadata_to_dict(paper_metadata)
        
        # 建立 paper skill 路徑：prefer readable title slug, not arXiv IDs.
        title = metadata.get("title") or reading.title
        safe_id = paper_title_slug(title, paper_id)
        skill_dir = self.output_dir / safe_id
        
        # 建立 profile
        profile = PaperProfile(
            paper_id=paper_id,
            title=title,
            year=metadata.get("year") or self._extract_year_from_id(paper_id),
            venue=metadata.get("venue"),
            authors=metadata.get("authors", []),
            
            tldr=reading.tldr or metadata.get("tldr") or metadata.get("abstract") or reading.title,
            
            theme=theme,
            taxonomy_path=taxonomy_path,
            method_family=method_family,
            
            rough_research_problem=reading.problem_statement,
            rough_contribution=reading.main_contribution,
            rough_method_intuition=reading.method_intuition,
            rough_limitation=reading.rough_limitation,
            
            benchmark_names=reading.benchmark_names,
            dataset_names=reading.dataset_names,
            baseline_names=reading.baseline_names,
            
            relationship_to_other_papers=relations,
            
            reading_level=reading.reading_level,
            confidence=reading.confidence,
            missing_fields=reading.missing_fields.copy(),
            
            pdf_path=metadata.get("pdf_path") or metadata.get("pdf_url") or str(skill_dir / "original.pdf"),
            section_index_path=str(skill_dir / "section_index.json"),
            skill_path=str(skill_dir / "SKILL.md"),
        )
        
        # 儲存 profile
        self._save_profile(profile, skill_dir)
        
        return profile
    
    def normalize_batch(
        self,
        readings: List[PaperNavigatorReading],
        taxonomy: SurveyTaxonomy,
        metadata_map: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[PaperProfile]:
        """批次處理多篇論文
        
        Args:
            readings: 多篇論文的 reading artifacts
            taxonomy: survey taxonomy
            metadata_map: paper_id -> metadata 映射
            
        Returns:
            List[PaperProfile]: 所有論文的 profiles
        """
        metadata_map = metadata_map or {}
        
        profiles = []
        for reading in readings:
            metadata = metadata_map.get(reading.paper_id, {})
            profile = self.normalize(reading, taxonomy, metadata)
            profiles.append(profile)
        
        return profiles

    def _metadata_to_dict(self, paper_metadata: Optional[Any]) -> Dict[str, Any]:
        """Normalize metadata input to a plain dict."""
        if paper_metadata is None:
            return {}
        if isinstance(paper_metadata, dict):
            return paper_metadata
        if hasattr(paper_metadata, "model_dump"):
            return paper_metadata.model_dump()
        return dict(paper_metadata)
    
    def _get_theme_info(
        self,
        paper_id: str,
        taxonomy: SurveyTaxonomy
    ) -> Tuple[Optional[str], List[str]]:
        """從 taxonomy 取得論文的主題資訊"""
        # 找到該論文的 assignment
        assignment = None
        for a in taxonomy.paper_assignments:
            if a.paper_id == paper_id:
                assignment = a
                break
        
        if not assignment:
            return None, []
        
        # 找到對應的主題
        theme = None
        for t in taxonomy.themes:
            if t.theme_id == assignment.theme_id:
                theme = t.name
                break
        
        # 建立 taxonomy path
        path = [theme] if theme else []
        
        # 加入子主題
        for st in taxonomy.subthemes:
            if st.subtheme_id == assignment.subtheme_id:
                path.append(st.name)
                break
        
        return theme, path
    
    def _get_method_family(
        self,
        paper_id: str,
        taxonomy: SurveyTaxonomy
    ) -> Optional[str]:
        """從 taxonomy 取得論文的方法家族"""
        for family in taxonomy.method_families:
            if paper_id in family.representative_papers:
                return family.name
        return None
    
    def _get_relations(
        self,
        paper_id: str,
        taxonomy: SurveyTaxonomy
    ) -> List[PaperRelation]:
        """從 taxonomy 的 candidate relations 取得該論文的關係"""
        relations = []
        
        for candidate in taxonomy.candidate_relations:
            if candidate.source_paper_id == paper_id:
                relations.append(PaperRelation(
                    target_paper_id=candidate.target_paper_id,
                    relation_type=candidate.relation_type,
                    status=candidate.status,
                    confidence=candidate.confidence
                ))
            elif candidate.target_paper_id == paper_id:
                # 對稱關係，反向也加入
                relations.append(PaperRelation(
                    target_paper_id=candidate.source_paper_id,
                    relation_type=candidate.relation_type,
                    status=candidate.status,
                    confidence=candidate.confidence
                ))
        
        return relations
    
    def _extract_year_from_id(self, paper_id: str) -> Optional[str]:
        """從 paper_id 抽取年份（簡化版本）"""
        # 嘗試從 arXiv ID 抽取年份
        if "arxiv" in paper_id.lower():
            # arXiv ID 格式：arxiv:YYMM.number
            parts = paper_id.split(":")
            if len(parts) > 1:
                year_part = parts[1][:2]
                if year_part.isdigit():
                    year_int = int(year_part)
                    if year_int >= 90:
                        return f"19{year_part}"
                    else:
                        return f"20{year_part}"
        return None
    
    def _save_profile(self, profile: PaperProfile, skill_dir: Path):
        """儲存 profile 到檔案"""
        skill_dir.mkdir(parents=True, exist_ok=True)
        
        profile_file = skill_dir / "paper_profile.json"
        with open(profile_file, "w", encoding="utf-8") as f:
            json.dump(profile.model_dump(), f, indent=2, ensure_ascii=False)
    
    def load_profile(self, paper_id: str) -> PaperProfile:
        """從檔案載入 profile"""
        profile_file = None
        legacy_safe_id = paper_id.replace(":", "_").replace("/", "_")
        legacy_profile = self.output_dir / legacy_safe_id / "paper_profile.json"
        if legacy_profile.exists():
            profile_file = legacy_profile
        else:
            for candidate in self.output_dir.iterdir():
                candidate_profile = candidate / "paper_profile.json"
                if not candidate_profile.exists():
                    continue
                try:
                    data = json.loads(candidate_profile.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if data.get("paper_id") == paper_id:
                    profile_file = candidate_profile
                    break
        if profile_file is None:
            raise FileNotFoundError(f"No paper_profile.json found for {paper_id}")
        
        with open(profile_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return PaperProfile(**data)


def paper_title_slug(title: str, paper_id: str | None = None, max_length: int = 96) -> str:
    """Create a readable filesystem slug from a paper title."""
    source = title or paper_id or "paper"
    slug = re.sub(r"[^A-Za-z0-9]+", "_", source).strip("_").lower()
    slug = re.sub(r"_+", "_", slug)
    if not slug:
        slug = re.sub(r"[^A-Za-z0-9]+", "_", paper_id or "paper").strip("_").lower()
    return slug[:max_length].strip("_") or "paper"
