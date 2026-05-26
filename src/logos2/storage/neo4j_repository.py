"""Lightweight Neo4j Repository

Module 6: Lightweight Neo4j Index

Neo4j 不儲存完整 paper details，而是作為 research map 與 routing index。

Nodes:
- Paper: routing metadata only
- Theme, MethodFamily, Benchmark, Dataset, Baseline: indexing nodes

Edges:
- Paper -[:BELONGS_TO_THEME]-> Theme
- Paper -[:USES_METHOD_FAMILY]-> MethodFamily
- Paper -[:EVALUATED_ON]-> Benchmark
- Paper -[:USES_DATASET]-> Dataset
- Paper -[:COMPARES_WITH]-> Baseline
- Paper -[:RELATED_TO {status, source, confidence}]-> Paper

NOT stored in Neo4j:
- Claim, Evidence, Figure, Table, Result, Metric, Experiment details
- These stay in paper skill packs or original PDF
"""

import os
from typing import List, Optional, Dict, Any
from neo4j import GraphDatabase

from ..schemas import (
    PaperProfile,
    SurveyTaxonomy,
    Theme,
    MethodFamily,
    BenchmarkMatrixEntry,
    DatasetMatrixEntry,
    BaselineMatrixEntry,
    CandidateRelation,
    CandidateEdge,
    VerifiedEdge,
)


class Neo4jRepository:
    """Lightweight Neo4j Repository
    
    輕量級 Neo4j 存取層，只儲存 routing metadata。
    取代舊版 heavy ontology client。
    """
    
    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None):
        """
        Args:
            uri: Neo4j URI (預設從環境變數 NEO4J_URI)
            user: Neo4j 使用者 (預設從環境變數 NEO4J_USER)
            password: Neo4j 密碼 (預設從環境變數 NEO4J_PASSWORD)
        """
        self.uri = uri or os.getenv("NEO4J_URI", "neo4j://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "")
        
        self.driver = None
    
    def connect(self):
        """建立 Neo4j 連線"""
        if not self.driver:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password) if self.password else None
            )
        return self
    
    def close(self):
        """關閉 Neo4j 連線"""
        if self.driver:
            self.driver.close()
            self.driver = None
    
    def setup_schema(self):
        """建立輕量級 schema：constraints 和 indexes"""
        if not self.driver:
            self.connect()
        
        constraints = [
            # Paper nodes
            "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.paper_id IS UNIQUE",
            # Indexing nodes
            "CREATE CONSTRAINT theme_name IF NOT EXISTS FOR (t:Theme) REQUIRE t.name IS UNIQUE",
            "CREATE CONSTRAINT method_family_name IF NOT EXISTS FOR (m:MethodFamily) REQUIRE m.name IS UNIQUE",
            "CREATE CONSTRAINT benchmark_name IF NOT EXISTS FOR (b:Benchmark) REQUIRE b.name IS UNIQUE",
            "CREATE CONSTRAINT dataset_name IF NOT EXISTS FOR (d:Dataset) REQUIRE d.name IS UNIQUE",
            "CREATE CONSTRAINT baseline_name IF NOT EXISTS FOR (bl:Baseline) REQUIRE bl.name IS UNIQUE",
        ]
        
        # Full-text indexes for string matching
        indexes = [
            "CREATE FULLTEXT INDEX paper_search IF NOT EXISTS FOR (p:Paper) ON EACH [p.title, p.tldr]",
            "CREATE FULLTEXT INDEX theme_search IF NOT EXISTS FOR (t:Theme) ON EACH [t.name, t.keywords]",
        ]
        
        with self.driver.session() as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception as e:
                    print(f"Constraint creation warning (may already exist): {e}")
            
            for index in indexes:
                try:
                    session.run(index)
                except Exception as e:
                    print(f"Index creation warning (may already exist): {e}")
    
    def create_paper_node(self, profile: PaperProfile):
        """建立 Paper node（輕量級，只有 routing metadata）"""
        if not self.driver:
            self.connect()
        
        query = """
        MERGE (p:Paper {paper_id: $paper_id})
        SET p.title = $title,
            p.year = $year,
            p.venue = $venue,
            p.tldr = $tldr,
            p.theme = $theme,
            p.taxonomy_path = $taxonomy_path,
            p.method_family = $method_family,
            p.rough_problem = $rough_problem,
            p.rough_contribution = $rough_contribution,
            p.reading_level = $reading_level,
            p.confidence = $confidence,
            p.skill_path = $skill_path,
            p.profile_path = $profile_path,
            p.pdf_path = $pdf_path
        """
        
        with self.driver.session() as session:
            session.run(
                query,
                paper_id=profile.paper_id,
                title=profile.title,
                year=profile.year or "Unknown",
                venue=profile.venue or "Unknown",
                tldr=profile.tldr,
                theme=profile.theme or "Unknown",
                taxonomy_path=profile.taxonomy_path,
                method_family=profile.method_family or "Unknown",
                rough_problem=profile.rough_research_problem or "",
                rough_contribution=profile.rough_contribution or "",
                reading_level=profile.reading_level,
                confidence=profile.confidence,
                skill_path=profile.skill_path or "",
                profile_path=profile.skill_path.replace("SKILL.md", "paper_profile.json") if profile.skill_path else "",
                pdf_path=profile.pdf_path or ""
            )
    
    def create_theme_nodes(self, themes: List[Theme]):
        """建立 Theme nodes"""
        if not self.driver:
            self.connect()
        
        query = """
        UNWIND $themes AS theme
        MERGE (t:Theme {name: theme.name})
        SET t.description = theme.description,
            t.keywords = theme.keywords,
            t.theme_id = theme.theme_id
        """
        
        with self.driver.session() as session:
            session.run(query, themes=[t.model_dump() for t in themes])
    
    def create_method_family_nodes(self, families: List[MethodFamily]):
        """建立 MethodFamily nodes"""
        if not self.driver:
            self.connect()
        
        query = """
        UNWIND $families AS family
        MERGE (m:MethodFamily {name: family.name})
        SET m.description = family.description,
            m.family_id = family.family_id
        """
        
        with self.driver.session() as session:
            session.run(query, families=[f.model_dump() for f in families])
    
    def create_benchmark_nodes(self, benchmarks: List[BenchmarkMatrixEntry]):
        """建立 Benchmark nodes"""
        if not self.driver:
            self.connect()
        
        query = """
        UNWIND $benchmarks AS bench
        MERGE (b:Benchmark {name: bench.benchmark_name})
        SET b.metric_names = bench.metric_names
        """
        
        with self.driver.session() as session:
            session.run(query, benchmarks=[b.model_dump() for b in benchmarks])
    
    def create_dataset_nodes(self, datasets: List[DatasetMatrixEntry]):
        """建立 Dataset nodes"""
        if not self.driver:
            self.connect()
        
        query = """
        UNWIND $datasets AS ds
        MERGE (d:Dataset {name: ds.dataset_name})
        SET d.task_types = ds.task_types
        """
        
        with self.driver.session() as session:
            session.run(query, datasets=[d.model_dump() for d in datasets])
    
    def create_baseline_nodes(self, baselines: List[BaselineMatrixEntry]):
        """建立 Baseline nodes"""
        if not self.driver:
            self.connect()
        
        query = """
        UNWIND $baselines AS bl
        MERGE (b:Baseline {name: bl.baseline_name})
        """
        
        with self.driver.session() as session:
            session.run(query, baselines=[b.model_dump() for b in baselines])
    
    def create_paper_relationships(self, profile: PaperProfile, taxonomy: SurveyTaxonomy):
        """建立 Paper 與其他 nodes 的關係"""
        if not self.driver:
            self.connect()
        
        paper_id = profile.paper_id
        
        with self.driver.session() as session:
            # Paper -> Theme
            if profile.theme and profile.theme != "Unknown":
                session.run("""
                    MATCH (p:Paper {paper_id: $paper_id})
                    MATCH (t:Theme {name: $theme})
                    MERGE (p)-[:BELONGS_TO_THEME]->(t)
                """, paper_id=paper_id, theme=profile.theme)
            
            # Paper -> MethodFamily
            if profile.method_family and profile.method_family != "Unknown":
                session.run("""
                    MATCH (p:Paper {paper_id: $paper_id})
                    MATCH (m:MethodFamily {name: $family})
                    MERGE (p)-[:USES_METHOD_FAMILY]->(m)
                """, paper_id=paper_id, family=profile.method_family)
            
            # Paper -> Benchmark
            for bench in profile.benchmark_names:
                session.run("""
                    MATCH (p:Paper {paper_id: $paper_id})
                    MATCH (b:Benchmark {name: $bench})
                    MERGE (p)-[:EVALUATED_ON]->(b)
                """, paper_id=paper_id, bench=bench)
            
            # Paper -> Dataset
            for dataset in profile.dataset_names:
                session.run("""
                    MATCH (p:Paper {paper_id: $paper_id})
                    MATCH (d:Dataset {name: $dataset})
                    MERGE (p)-[:USES_DATASET]->(d)
                """, paper_id=paper_id, dataset=dataset)
            
            # Paper -> Baseline
            for baseline in profile.baseline_names:
                session.run("""
                    MATCH (p:Paper {paper_id: $paper_id})
                    MATCH (b:Baseline {name: $baseline})
                    MERGE (p)-[:COMPARES_WITH]->(b)
                """, paper_id=paper_id, baseline=baseline)
    
    def create_candidate_relation(self, edge: CandidateEdge):
        """建立候選 paper-to-paper relation"""
        if not self.driver:
            self.connect()
        
        query = """
        MATCH (a:Paper {paper_id: $source_id})
        MATCH (b:Paper {paper_id: $target_id})
        MERGE (a)-[r:RELATED_TO]->(b)
        SET r.relation_type = $relation_type,
            r.status = $status,
            r.source = $source,
            r.confidence = $confidence,
            r.rationale = $rationale,
            r.verified = false
        """
        
        with self.driver.session() as session:
            session.run(
                query,
                source_id=edge.source_paper_id,
                target_id=edge.target_paper_id,
                relation_type=edge.relation_type,
                status=edge.status,
                source=edge.source,
                confidence=edge.confidence,
                rationale=edge.rationale or ""
            )
    
    def update_relation_status(self, edge: VerifiedEdge):
        """更新 relation 為 verified/rejected"""
        if not self.driver:
            self.connect()
        
        query = """
        MATCH (a:Paper {paper_id: $source_id})-[r:RELATED_TO]->(b:Paper {paper_id: $target_id})
        WHERE r.relation_type = $relation_type
        SET r.status = $status,
            r.confidence = $confidence,
            r.verified = true,
            r.verified_at = $verified_at,
            r.verifier_version = $verifier_version
        """
        
        with self.driver.session() as session:
            session.run(
                query,
                source_id=edge.source_paper_id,
                target_id=edge.target_paper_id,
                relation_type=edge.relation_type,
                status=edge.status,
                confidence=edge.confidence,
                verified_at=edge.verified_at,
                verifier_version=edge.verifier_version
            )
    
    def search_papers_by_theme(self, theme_name: str) -> List[Dict[str, Any]]:
        """依主題搜尋論文"""
        if not self.driver:
            self.connect()
        
        query = """
        MATCH (p:Paper)-[:BELONGS_TO_THEME]->(t:Theme {name: $theme})
        RETURN p.paper_id as paper_id, p.title as title, p.tldr as tldr,
               p.skill_path as skill_path, p.confidence as confidence
        """
        
        with self.driver.session() as session:
            result = session.run(query, theme=theme_name)
            return [dict(record) for record in result]
    
    def search_papers_by_benchmark(self, benchmark_name: str) -> List[Dict[str, Any]]:
        """依 benchmark 搜尋論文"""
        if not self.driver:
            self.connect()
        
        query = """
        MATCH (p:Paper)-[:EVALUATED_ON]->(b:Benchmark {name: $benchmark})
        RETURN p.paper_id as paper_id, p.title as title, p.tldr as tldr,
               p.skill_path as skill_path
        """
        
        with self.driver.session() as session:
            result = session.run(query, benchmark=benchmark_name)
            return [dict(record) for record in result]
    
    def get_paper_neighbors(self, paper_id: str, min_confidence: float = 0.5) -> List[Dict[str, Any]]:
        """取得論文的相關論文（candidate relations）"""
        if not self.driver:
            self.connect()
        
        query = """
        MATCH (p:Paper {paper_id: $paper_id})-[r:RELATED_TO]->(other:Paper)
        WHERE r.confidence >= $min_conf
        RETURN other.paper_id as paper_id, other.title as title, 
               r.relation_type as relation_type, r.confidence as confidence,
               r.status as status, other.skill_path as skill_path
        ORDER BY r.confidence DESC
        """
        
        with self.driver.session() as session:
            result = session.run(query, paper_id=paper_id, min_conf=min_confidence)
            return [dict(record) for record in result]
    
    def fulltext_search_papers(self, query_text: str, limit: int = 10) -> List[Dict[str, Any]]:
        """全文搜尋論文"""
        if not self.driver:
            self.connect()
        
        query = """
        CALL db.index.fulltext.queryNodes('paper_search', $query) YIELD node, score
        RETURN node.paper_id as paper_id, node.title as title, node.tldr as tldr,
               node.skill_path as skill_path, score
        ORDER BY score DESC
        LIMIT $limit
        """
        
        with self.driver.session() as session:
            result = session.run(query, query=query_text, limit=limit)
            return [dict(record) for record in result]


class LightweightNeo4jIndexer:
    """Lightweight Neo4j Indexer Node
    
    將 Survey Taxonomy 和 Paper Profiles 寫入 Neo4j 輕量級 index。
    """
    
    def __init__(self, repository: Optional[Neo4jRepository] = None):
        self.repository = repository or Neo4jRepository()
    
    def index_taxonomy(self, taxonomy: SurveyTaxonomy):
        """索引整個 taxonomy"""
        self.repository.connect()
        self.repository.setup_schema()
        
        # 建立 indexing nodes
        self.repository.create_theme_nodes(taxonomy.themes)
        self.repository.create_method_family_nodes(taxonomy.method_families)
        self.repository.create_benchmark_nodes(taxonomy.benchmark_matrix)
        self.repository.create_dataset_nodes(taxonomy.dataset_matrix)
        self.repository.create_baseline_nodes(taxonomy.baseline_matrix)
    
    def index_paper(self, profile: PaperProfile, taxonomy: SurveyTaxonomy):
        """索引單篇論文"""
        self.repository.create_paper_node(profile)
        self.repository.create_paper_relationships(profile, taxonomy)
    
    def index_papers_batch(self, profiles: List[PaperProfile], taxonomy: SurveyTaxonomy):
        """批次索引多篇論文"""
        for profile in profiles:
            self.index_paper(profile, taxonomy)
    
    def index_candidate_relations(self, relations: List[CandidateRelation]):
        """索引候選 paper-to-paper relations"""
        for relation in relations:
            edge = CandidateEdge(
                source_paper_id=relation.source_paper_id,
                target_paper_id=relation.target_paper_id,
                relation_type=relation.relation_type,
                status=relation.status,
                source=relation.source,
                confidence=relation.confidence,
                rationale=relation.rationale
            )
            self.repository.create_candidate_relation(edge)
