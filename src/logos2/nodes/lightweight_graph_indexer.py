"""Lightweight Graph Indexer.

Module 6 Node: writes Survey Taxonomy and Paper Profiles to the configured
lightweight graph backend.  SQLite is the default; Neo4j is optional.
"""

from typing import List, Optional

from ..schemas import CandidateEdge, CandidateRelation, PaperProfile, SurveyTaxonomy
from ..storage import GraphRepositoryProtocol, SQLiteGraphRepository


class LightweightGraphIndexer:
    """Lightweight Graph Indexer Workflow Node
    
    在 LangGraph workflow 中使用，負責：
    1. 建立 graph schema
    2. 索引 taxonomy（themes, method families, benchmarks...）
    3. 索引所有 paper profiles
    4. 索引 candidate relations
    """
    
    def __init__(self, repository: Optional[GraphRepositoryProtocol] = None):
        """
        Args:
            repository: graph repository 實例（可選，預設 SQLite）
        """
        self.repository = repository or SQLiteGraphRepository()
    
    def run(
        self,
        taxonomy: SurveyTaxonomy,
        paper_profiles: List[PaperProfile],
        candidate_relations: Optional[List[CandidateRelation]] = None
    ) -> dict:
        """執行索引
        
        Args:
            taxonomy: Survey Taxonomy
            paper_profiles: 所有論文的 profiles
            candidate_relations: 候選論文關係（可選，預設從 taxonomy 取得）
            
        Returns:
            dict: 索引結果統計
        """
        try:
            # 連線並建立 schema
            self.repository.connect()
            self.repository.setup_schema()
            
            # 索引 taxonomy nodes
            self.repository.create_theme_nodes(taxonomy.themes)
            self.repository.create_method_family_nodes(taxonomy.method_families)
            self.repository.create_benchmark_nodes(taxonomy.benchmark_matrix)
            self.repository.create_dataset_nodes(taxonomy.dataset_matrix)
            self.repository.create_baseline_nodes(taxonomy.baseline_matrix)
            
            # 索引所有 papers
            for profile in paper_profiles:
                self.repository.create_paper_node(profile)
                self.repository.create_paper_relationships(profile, taxonomy)
            
            # 索引 candidate relations
            relations = candidate_relations or taxonomy.candidate_relations
            for relation in relations:
                edge = CandidateEdge(
                    source_paper_id=relation.source_paper_id,
                    target_paper_id=relation.target_paper_id,
                    relation_type=relation.relation_type,
                    status=relation.status,
                    source=relation.source,
                    confidence=relation.confidence,
                    rationale=relation.rationale,
                )
                self.repository.create_candidate_relation(edge)
            
            return {
                "success": True,
                "papers_indexed": len(paper_profiles),
                "themes_indexed": len(taxonomy.themes),
                "method_families_indexed": len(taxonomy.method_families),
                "relations_indexed": len(relations),
                "error": None
            }
            
        except Exception as e:
            return {
                "success": False,
                "papers_indexed": 0,
                "themes_indexed": 0,
                "method_families_indexed": 0,
                "relations_indexed": 0,
                "error": str(e)
            }
        finally:
            self.repository.close()
    
    def close(self):
        """關閉連線"""
        self.repository.close()
