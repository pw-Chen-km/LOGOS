"""Skill Registry

管理 paper skill packs 的註冊與查找。
提供 skill_path -> paper_profile 的映射。
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any

from ..schemas import PaperProfile, PaperSkillManifest


class SkillRegistry:
    """Paper Skill Registry
    
    管理 paper_skills/ 目錄下的所有 skill packs。
    提供：
    - 註冊新 skill pack
    - 依 paper_id 查找 skill
    - 依主題/方法家族查找 skills
    - 列出所有可用 skills
    """
    
    def __init__(self, paper_skills_dir: str = "paper_skills"):
        """
        Args:
            paper_skills_dir: paper skill packs 根目錄
        """
        self.paper_skills_dir = Path(paper_skills_dir)
        self.paper_skills_dir.mkdir(parents=True, exist_ok=True)
        
        self._index: Dict[str, str] = {}  # paper_id -> skill_path
        self._build_index()
    
    def _build_index(self):
        """重建 index"""
        self._index.clear()
        
        if not self.paper_skills_dir.exists():
            return
        
        for skill_dir in self.paper_skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                metadata_json = skill_dir / "metadata.json"
                
                if skill_md.exists() and metadata_json.exists():
                    try:
                        with open(metadata_json, "r", encoding="utf-8") as f:
                            metadata = json.load(f)
                            paper_id = metadata.get("paper_id")
                            if paper_id:
                                self._index[paper_id] = str(skill_md)
                    except Exception:
                        pass
    
    def register(self, manifest: PaperSkillManifest):
        """註冊新的 skill pack"""
        self._index[manifest.paper_id] = manifest.skill_md_path
    
    def get_skill_path(self, paper_id: str) -> Optional[str]:
        """取得指定論文的 SKILL.md 路徑"""
        # 檢查 cache
        if paper_id in self._index:
            return self._index[paper_id]
        
        # 嘗試查找
        safe_id = paper_id.replace(":", "_").replace("/", "_")
        skill_dir = self.paper_skills_dir / safe_id
        skill_md = skill_dir / "SKILL.md"
        
        if skill_md.exists():
            self._index[paper_id] = str(skill_md)
            return str(skill_md)
        
        return None
    
    def get_profile_path(self, paper_id: str) -> Optional[str]:
        """取得指定論文的 paper_profile.json 路徑"""
        skill_path = self.get_skill_path(paper_id)
        if skill_path:
            return str(Path(skill_path).parent / "paper_profile.json")
        return None
    
    def get_references_dir(self, paper_id: str) -> Optional[str]:
        """取得指定論文的 references/ 目錄路徑"""
        skill_path = self.get_skill_path(paper_id)
        if skill_path:
            return str(Path(skill_path).parent / "references")
        return None
    
    def get_pdf_path(self, paper_id: str) -> Optional[str]:
        """取得指定論文的 original.pdf 路徑"""
        skill_path = self.get_skill_path(paper_id)
        if skill_path:
            return str(Path(skill_path).parent / "original.pdf")
        return None
    
    def load_profile(self, paper_id: str) -> Optional[PaperProfile]:
        """載入指定論文的 profile"""
        profile_path = self.get_profile_path(paper_id)
        if profile_path and Path(profile_path).exists():
            with open(profile_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return PaperProfile(**data)
        return None
    
    def load_manifest(self, paper_id: str) -> Optional[PaperSkillManifest]:
        """載入指定論文的 manifest"""
        skill_path = self.get_skill_path(paper_id)
        if not skill_path:
            return None
        
        manifest_path = Path(skill_path).parent / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return PaperSkillManifest(**data)
        return None
    
    def list_all_skills(self) -> List[Dict[str, str]]:
        """列出所有註冊的 skills"""
        return [
            {"paper_id": pid, "skill_path": path}
            for pid, path in self._index.items()
        ]
    
    def search_by_theme(self, theme: str) -> List[str]:
        """依主題搜尋 paper_ids（需要從 profile 讀取）"""
        matching_papers = []
        
        for paper_id in self._index.keys():
            profile = self.load_profile(paper_id)
            if profile and profile.theme and theme.lower() in profile.theme.lower():
                matching_papers.append(paper_id)
        
        return matching_papers
    
    def search_by_method_family(self, method_family: str) -> List[str]:
        """依方法家族搜尋 paper_ids"""
        matching_papers = []
        
        for paper_id in self._index.keys():
            profile = self.load_profile(paper_id)
            if profile and profile.method_family and method_family.lower() in profile.method_family.lower():
                matching_papers.append(paper_id)
        
        return matching_papers
    
    def reindex(self):
        """重新建立 index"""
        self._build_index()
