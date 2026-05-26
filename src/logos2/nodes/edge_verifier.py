"""Edge Verifier

Module 8: Optional Cross-Paper Edge Verifier

Cross-Paper Edge Verifier 是 high-cost optional module，
用來將 candidate relation 升級成 verified relation。

何時啟動：
1. 使用者要求驗證兩篇 paper 是否真的解決同一問題
2. QA answer 依賴某條 candidate edge
3. 使用者希望產生可信度較高的 related work / survey graph
4. candidate edge confidence 低但重要
5. 使用者手動按下 "verify relation"

設計原則：
- 只讀 paper skills / reference guides
- 不足時讀 PDF section
- 不呼叫舊 PeerReviewer 預設流程
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from ..schemas import (
    CandidateRelation,
    VerifiedEdge,
    EdgeEvidence,
    PaperProfile,
    CandidateEdge,
)
from ..storage import GraphRepositoryProtocol, SQLiteGraphRepository, SkillRegistry


@dataclass
class VerificationResult:
    """Verification 結果"""
    success: bool
    verified_edge: Optional[VerifiedEdge]
    evidence_found: List[EdgeEvidence]
    rationale: str
    error: Optional[str] = None


class EdgeVerifier:
    """Cross-Paper Edge Verifier
    
    驗證 candidate relation 是否為真，並產生 verified edge。
    
    Process:
    1. Open source paper skill
    2. Open target paper skill
    3. Read paper_profile.json for both
    4. Read relevant reference guides
    5. If needed, read PDF sections
    6. Decide whether relation is valid
    7. Update graph edge status
    """
    
    def __init__(
        self,
        repository: Optional[GraphRepositoryProtocol] = None,
        skill_registry: Optional[SkillRegistry] = None
    ):
        """
        Args:
            repository: graph repository 實例
            skill_registry: SkillRegistry 實例
        """
        self.repository = repository or SQLiteGraphRepository()
        self.registry = skill_registry or SkillRegistry()
    
    def verify(self, candidate: CandidateRelation) -> VerificationResult:
        """驗證單個 candidate relation
        
        Args:
            candidate: 候選關係
            
        Returns:
            VerificationResult: 驗證結果
        """
        try:
            self.repository.connect()
            
            source_id = candidate.source_paper_id
            target_id = candidate.target_paper_id
            relation_type = candidate.relation_type
            
            # 1. 載入兩篇論文的 profiles
            source_profile = self.registry.load_profile(source_id)
            target_profile = self.registry.load_profile(target_id)
            
            if not source_profile or not target_profile:
                return VerificationResult(
                    success=False,
                    verified_edge=None,
                    evidence_found=[],
                    rationale="Could not load one or both paper profiles",
                    error="Missing paper profile"
                )
            
            # 2. 根據 relation_type 決定驗證策略
            evidence, rationale, status = self._verify_by_type(
                candidate,
                source_profile,
                target_profile
            )
            
            # 3. 建立 verified edge
            verified_edge = VerifiedEdge(
                edge_id=f"edge_{source_id}_{target_id}_{relation_type}",
                source_paper_id=source_id,
                target_paper_id=target_id,
                relation_type=relation_type,
                status=status,
                confidence=self._calculate_confidence(evidence, status),
                evidence=evidence,
                rationale=rationale,
                verified_at=datetime.utcnow().isoformat() + "Z",
                verifier_version="1.0.0"
            )
            
            # 4. 更新 graph backend
            self.repository.update_relation_status(verified_edge)
            
            return VerificationResult(
                success=True,
                verified_edge=verified_edge,
                evidence_found=evidence,
                rationale=rationale
            )
            
        except Exception as e:
            return VerificationResult(
                success=False,
                verified_edge=None,
                evidence_found=[],
                rationale="Verification failed",
                error=str(e)
            )
        finally:
            self.repository.close()
    
    def verify_batch(
        self,
        candidates: List[CandidateRelation],
        min_confidence: float = 0.5
    ) -> List[VerificationResult]:
        """批次驗證多個 candidates
        
        Args:
            candidates: 候選關係列表
            min_confidence: 只驗證信心分數高於此值的 candidates
            
        Returns:
            List[VerificationResult]: 所有驗證結果
        """
        results = []
        
        for candidate in candidates:
            if candidate.confidence >= min_confidence:
                result = self.verify(candidate)
                results.append(result)
            else:
                # 跳過低信心 candidate
                results.append(VerificationResult(
                    success=False,
                    verified_edge=None,
                    evidence_found=[],
                    rationale=f"Skipped: confidence {candidate.confidence} below threshold {min_confidence}",
                    error="Below confidence threshold"
                ))
        
        return results
    
    def verify_from_qa_context(
        self,
        paper_id: str,
        related_paper_id: str,
        relation_type_hint: str
    ) -> VerificationResult:
        """從 QA context 觸發驗證
        
        當 QA agent 發現某條 edge 是回答問題的關鍵時觸發。
        
        Args:
            paper_id: 主要論文 ID
            related_paper_id: 相關論文 ID
            relation_type_hint: 建議的關係類型
            
        Returns:
            VerificationResult: 驗證結果
        """
        # 建立臨時 candidate
        candidate = CandidateRelation(
            source_paper_id=paper_id,
            target_paper_id=related_paper_id,
            relation_type=relation_type_hint,
            status="candidate",
            source="qa_context",
            confidence=0.5,  # 預設中等信心
            rationale="Triggered from QA context"
        )
        
        return self.verify(candidate)
    
    def _verify_by_type(
        self,
        candidate: CandidateRelation,
        source_profile: PaperProfile,
        target_profile: PaperProfile
    ) -> tuple[List[EdgeEvidence], str, str]:
        """根據關係類型執行驗證
        
        Returns:
            (evidence_list, rationale, status)
        """
        relation_type = candidate.relation_type
        
        if relation_type == "same_benchmark":
            return self._verify_same_benchmark(candidate, source_profile, target_profile)
        
        elif relation_type == "same_method_family":
            return self._verify_same_method_family(candidate, source_profile, target_profile)
        
        elif relation_type == "related_problem":
            return self._verify_related_problem(candidate, source_profile, target_profile)
        
        elif relation_type == "common_baseline":
            return self._verify_common_baseline(candidate, source_profile, target_profile)
        
        elif relation_type in ["extends", "improves"]:
            return self._verify_citation_relation(candidate, source_profile, target_profile)
        
        else:
            return (
                [],
                f"Unknown relation type: {relation_type}",
                "rejected"
            )
    
    def _verify_same_benchmark(
        self,
        candidate: CandidateRelation,
        source_profile: PaperProfile,
        target_profile: PaperProfile
    ) -> tuple[List[EdgeEvidence], str, str]:
        """驗證 same_benchmark 關係"""
        evidence = []
        
        # 檢查 profiles 中的 benchmark lists
        source_benchmarks = set(source_profile.benchmark_names)
        target_benchmarks = set(target_profile.benchmark_names)
        common_benchmarks = source_benchmarks & target_benchmarks
        
        if common_benchmarks:
            # 找到共同 benchmark
            evidence.append(EdgeEvidence(
                paper_id=source_profile.paper_id,
                source="paper_profile",
                reference_file="paper_profile.json",
                excerpt=f"Benchmarks: {list(source_benchmarks)}"
            ))
            evidence.append(EdgeEvidence(
                paper_id=target_profile.paper_id,
                source="paper_profile",
                reference_file="paper_profile.json",
                excerpt=f"Benchmarks: {list(target_benchmarks)}"
            ))
            
            # 嘗試讀取更詳細的 benchmark guide
            bench_guide_evidence = self._read_benchmark_guide(
                source_profile.paper_id,
                target_profile.paper_id,
                common_benchmarks
            )
            evidence.extend(bench_guide_evidence)
            
            rationale = (
                f"Both papers evaluate on common benchmarks: {', '.join(common_benchmarks)}. "
                f"Source: {source_profile.title}, Target: {target_profile.title}"
            )
            status = "verified" if len(bench_guide_evidence) > 0 else "weak_verified"
        else:
            rationale = "No common benchmarks found in paper profiles"
            status = "rejected"
        
        return evidence, rationale, status
    
    def _verify_same_method_family(
        self,
        candidate: CandidateRelation,
        source_profile: PaperProfile,
        target_profile: PaperProfile
    ) -> tuple[List[EdgeEvidence], str, str]:
        """驗證 same_method_family 關係"""
        evidence = []
        
        # 檢查 method_family
        source_family = source_profile.method_family
        target_family = target_profile.method_family
        
        if source_family and target_family and source_family == target_family:
            evidence.append(EdgeEvidence(
                paper_id=source_profile.paper_id,
                source="paper_profile",
                reference_file="paper_profile.json",
                excerpt=f"Method family: {source_family}"
            ))
            evidence.append(EdgeEvidence(
                paper_id=target_profile.paper_id,
                source="paper_profile",
                reference_file="paper_profile.json",
                excerpt=f"Method family: {target_family}"
            ))
            
            rationale = f"Both papers belong to method family: {source_family}"
            status = "verified"
        else:
            # 嘗試從 method intuition 比較
            source_method = source_profile.rough_method_intuition or ""
            target_method = target_profile.rough_method_intuition or ""
            
            # 簡化比較：檢查是否有共同關鍵字
            common_keywords = self._find_common_keywords(source_method, target_method)
            
            if common_keywords:
                evidence.append(EdgeEvidence(
                    paper_id=source_profile.paper_id,
                    source="reference_guide",
                    reference_file="references/method_guide.md",
                    excerpt=f"Method keywords: {', '.join(common_keywords[:5])}"
                ))
                
                rationale = f"Papers share method keywords: {', '.join(common_keywords[:5])}"
                status = "weak_verified"
            else:
                rationale = "No common method family or keywords found"
                status = "rejected"
        
        return evidence, rationale, status
    
    def _verify_related_problem(
        self,
        candidate: CandidateRelation,
        source_profile: PaperProfile,
        target_profile: PaperProfile
    ) -> tuple[List[EdgeEvidence], str, str]:
        """驗證 related_problem 關係"""
        evidence = []
        
        source_problem = source_profile.rough_research_problem or ""
        target_problem = target_profile.rough_research_problem or ""
        
        # 比較問題關鍵字
        common_keywords = self._find_common_keywords(source_problem, target_problem)
        
        if common_keywords:
            evidence.append(EdgeEvidence(
                paper_id=source_profile.paper_id,
                source="paper_profile",
                reference_file="paper_profile.json",
                excerpt=f"Problem: {source_problem[:200]}..."
            ))
            evidence.append(EdgeEvidence(
                paper_id=target_profile.paper_id,
                source="paper_profile",
                reference_file="paper_profile.json",
                excerpt=f"Problem: {target_problem[:200]}..."
            ))
            
            # 嘗試讀取 problem guide
            problem_guide = self._read_file(
                source_profile.paper_id,
                "references/problem_and_motivation.md"
            )
            if problem_guide:
                evidence.append(EdgeEvidence(
                    paper_id=source_profile.paper_id,
                    source="reference_guide",
                    reference_file="references/problem_and_motivation.md",
                    excerpt=problem_guide[:300]
                ))
            
            rationale = (
                f"Both papers address similar research problems. "
                f"Common keywords: {', '.join(common_keywords[:5])}"
            )
            status = "verified" if len(evidence) > 2 else "weak_verified"
        else:
            rationale = "Research problems appear different"
            status = "rejected"
        
        return evidence, rationale, status
    
    def _verify_common_baseline(
        self,
        candidate: CandidateRelation,
        source_profile: PaperProfile,
        target_profile: PaperProfile
    ) -> tuple[List[EdgeEvidence], str, str]:
        """驗證 common_baseline 關係"""
        evidence = []
        
        source_baselines = set(source_profile.baseline_names)
        target_baselines = set(target_profile.baseline_names)
        common_baselines = source_baselines & target_baselines
        
        if common_baselines:
            evidence.append(EdgeEvidence(
                paper_id=source_profile.paper_id,
                source="paper_profile",
                reference_file="paper_profile.json",
                excerpt=f"Baselines: {list(source_baselines)}"
            ))
            evidence.append(EdgeEvidence(
                paper_id=target_profile.paper_id,
                source="paper_profile",
                reference_file="paper_profile.json",
                excerpt=f"Baselines: {list(target_baselines)}"
            ))
            
            rationale = f"Both papers compare against: {', '.join(common_baselines)}"
            status = "verified"
        else:
            rationale = "No common baselines found"
            status = "rejected"
        
        return evidence, rationale, status
    
    def _verify_citation_relation(
        self,
        candidate: CandidateRelation,
        source_profile: PaperProfile,
        target_profile: PaperProfile
    ) -> tuple[List[EdgeEvidence], str, str]:
        """驗證 extends/improves 引用關係（MVP: 基於主題相似性）"""
        evidence = []
        
        # 檢查主題是否相同
        if source_profile.theme and target_profile.theme:
            if source_profile.theme == target_profile.theme:
                evidence.append(EdgeEvidence(
                    paper_id=source_profile.paper_id,
                    source="paper_profile",
                    reference_file="paper_profile.json",
                    excerpt=f"Theme: {source_profile.theme}"
                ))
                evidence.append(EdgeEvidence(
                    paper_id=target_profile.paper_id,
                    source="paper_profile",
                    reference_file="paper_profile.json",
                    excerpt=f"Theme: {target_profile.theme}"
                ))
                
                rationale = (
                    f"Source paper '{source_profile.title}' extends work in same theme "
                    f"as target paper '{target_profile.title}'"
                )
                status = "weak_verified"  # 需要更多引用證據才能 fully verified
            else:
                rationale = "Different themes, citation relation uncertain"
                status = "rejected"
        else:
            rationale = "Missing theme information"
            status = "rejected"
        
        return evidence, rationale, status
    
    def _read_benchmark_guide(
        self,
        source_id: str,
        target_id: str,
        common_benchmarks: set
    ) -> List[EdgeEvidence]:
        """讀取 benchmark guide 取得更詳細證據"""
        evidence = []
        
        for paper_id in [source_id, target_id]:
            content = self._read_file(paper_id, "references/benchmark_and_baselines.md")
            if content:
                # 尋找提及 common benchmarks 的部分
                for bench in common_benchmarks:
                    if bench.lower() in content.lower():
                        # 擷取相關段落
                        start = content.lower().find(bench.lower())
                        excerpt = content[max(0, start-100):min(len(content), start+300)]
                        evidence.append(EdgeEvidence(
                            paper_id=paper_id,
                            source="reference_guide",
                            reference_file="references/benchmark_and_baselines.md",
                            excerpt=excerpt
                        ))
                        break
        
        return evidence
    
    def _read_file(self, paper_id: str, filename: str) -> Optional[str]:
        """讀取指定檔案"""
        skill_path = self.registry.get_skill_path(paper_id)
        if not skill_path:
            return None
        
        if filename == "paper_profile.json":
            file_path = Path(skill_path).parent / "paper_profile.json"
        else:
            refs_dir = Path(skill_path).parent / "references"
            file_path = refs_dir / filename.replace("references/", "")
        
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        
        return None
    
    def _find_common_keywords(self, text1: str, text2: str) -> List[str]:
        """尋找兩段文字的共同關鍵字"""
        # 簡化實作：抽取常見研究關鍵字
        common_research_terms = [
            "graph", "retrieval", "generation", "attention", "embedding",
            "neural", "network", "learning", "model", "algorithm",
            "optimization", "classification", "prediction", "clustering"
        ]
        
        found = []
        text1_lower = text1.lower()
        text2_lower = text2.lower()
        
        for term in common_research_terms:
            if term in text1_lower and term in text2_lower:
                found.append(term)
        
        return found[:10]  # 最多 10 個
    
    def _calculate_confidence(self, evidence: List[EdgeEvidence], status: str) -> float:
        """計算驗證信心分數"""
        if status == "rejected":
            return 0.0
        
        # 基於證據數量計算
        base_confidence = min(0.9, 0.5 + len(evidence) * 0.1)
        
        # verified > weak_verified
        if status == "verified":
            return base_confidence
        elif status == "weak_verified":
            return base_confidence * 0.7
        
        return 0.5
    
    def close(self):
        """關閉連線"""
        self.repository.close()
