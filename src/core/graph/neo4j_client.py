from neo4j import GraphDatabase
from typing import List, Dict

class Neo4jClient:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def setup_database(self):
        """11 Vector Indexes setup."""
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Paper) REQUIRE p.title IS UNIQUE;",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (k:Keyword) REQUIRE k.name IS UNIQUE;",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Dataset) REQUIRE d.name IS UNIQUE;",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:ComparedMethod) REQUIRE c.name IS UNIQUE;",

            """CREATE VECTOR INDEX summary_index IF NOT EXISTS FOR (n:Summary) ON (n.embedding) OPTIONS {indexConfig: {`vector.dimensions`:1536,`vector.similarity_function`:'cosine'}}""",
            """CREATE VECTOR INDEX research_problem_index IF NOT EXISTS FOR (n:ResearchProblem) ON (n.embedding) OPTIONS {indexConfig: {`vector.dimensions`:1536,`vector.similarity_function`:'cosine'}}""",
            """CREATE VECTOR INDEX previous_limitation_index IF NOT EXISTS FOR (n:PreviousLimitation) ON (n.embedding) OPTIONS {indexConfig: {`vector.dimensions`:1536,`vector.similarity_function`:'cosine'}}""",
            """CREATE VECTOR INDEX underlying_problem_index IF NOT EXISTS FOR (n:UnderlyingResearchProblem) ON (n.embedding) OPTIONS {indexConfig: {`vector.dimensions`:1536,`vector.similarity_function`:'cosine'}}""",
            """CREATE VECTOR INDEX method_index IF NOT EXISTS FOR (n:Method) ON (n.embedding) OPTIONS {indexConfig: {`vector.dimensions`:1536,`vector.similarity_function`:'cosine'}}""",
            """CREATE VECTOR INDEX method_detail_index IF NOT EXISTS FOR (n:MethodDetail) ON (n.embedding) OPTIONS {indexConfig: {`vector.dimensions`:1536,`vector.similarity_function`:'cosine'}}""",
            """CREATE VECTOR INDEX referred_algorithm_index IF NOT EXISTS FOR (n:ReferredAlgorithm) ON (n.embedding) OPTIONS {indexConfig: {`vector.dimensions`:1536,`vector.similarity_function`:'cosine'}}""",
            """CREATE VECTOR INDEX experiment_index IF NOT EXISTS FOR (n:Experiment) ON (n.embedding) OPTIONS {indexConfig: {`vector.dimensions`:1536,`vector.similarity_function`:'cosine'}}""",
            """CREATE VECTOR INDEX experiment_analysis_index IF NOT EXISTS FOR (n:ExperimentAnalysis) ON (n.embedding) OPTIONS {indexConfig: {`vector.dimensions`:1536,`vector.similarity_function`:'cosine'}}""",
            """CREATE VECTOR INDEX keyword_index IF NOT EXISTS FOR (n:Keyword) ON (n.embedding) OPTIONS {indexConfig: {`vector.dimensions`:1536,`vector.similarity_function`:'cosine'}}""",
            """CREATE VECTOR INDEX dataset_index IF NOT EXISTS FOR (n:Dataset) ON (n.embedding) OPTIONS {indexConfig: {`vector.dimensions`:1536,`vector.similarity_function`:'cosine'}}""",
            """CREATE VECTOR INDEX compared_method_index IF NOT EXISTS FOR (n:ComparedMethod) ON (n.embedding) OPTIONS {indexConfig: {`vector.dimensions`:1536,`vector.similarity_function`:'cosine'}}""",

            # Full-Text Indexes for Fuzzy String Search (Benchmark matching)
            "CREATE FULLTEXT INDEX dataset_fulltext_idx IF NOT EXISTS FOR (n:Dataset) ON EACH [n.name];",
            "CREATE FULLTEXT INDEX compared_method_fulltext_idx IF NOT EXISTS FOR (n:ComparedMethod) ON EACH [n.name];",
        ]
        with self.driver.session() as session:
            for q in queries:
                session.run(q)
            # Full-text indexes for peer review fuzzy matching
            session.run("CREATE FULLTEXT INDEX dataset_fulltext_idx IF NOT EXISTS FOR (n:Dataset) ON EACH [n.name]")
            session.run("CREATE FULLTEXT INDEX compared_method_fulltext_idx IF NOT EXISTS FOR (n:ComparedMethod) ON EACH [n.name]")



    def ingest_paper_base(self, paper_data: dict, embeddings: dict):
        """Ingest using separate sub-queries to avoid skip-on-empty issue."""
        p_title = paper_data["paper"]["title"]

        queries = [
            # 1. Base Paper
            ("MERGE (p:Paper {title: $title})", {"title": p_title}),

            # 2. Summary
            ("""
            MATCH (p:Paper {title: $title})
            CREATE (s:Summary {year: $year, short_claim: $claim, embedding: $emb})
            MERGE (p)-[:HAS_SUMMARY]->(s)
            """, {
                "title": p_title, "year": paper_data["summary"]["year"],
                "claim": paper_data["summary"]["short_claim"], "emb": embeddings["summary"]
            }),

            # 3. Keywords
            ("""
            MATCH (p:Paper {title: $title})
            UNWIND $keywords AS kw
            MERGE (k:Keyword {name: kw.name})
            SET k.embedding = kw.embedding
            MERGE (p)-[:HAS_KEYWORD]->(k)
            """, {"title": p_title, "keywords": paper_data.get("keywords", [])}),

            # 4. Research Problem branch (L2 -> L3)
            ("""
            MATCH (p:Paper {title: $title})
            CREATE (rp:ResearchProblem {summary: $rp_sum, embedding: $rp_emb})
            CREATE (pl:PreviousLimitation {limitation: $pl_text, embedding: $pl_emb})
            CREATE (up:UnderlyingResearchProblem {detail: $up_text, embedding: $up_emb})
            MERGE (p)-[:ADDRESSES]->(rp)
            MERGE (rp)-[:ANALYZE]->(pl)
            MERGE (rp)-[:HAS_UNDERLYING_PROBLEM]->(up)
            """, {
                "title": p_title,
                "rp_sum": paper_data["research_problem"]["summary"], "rp_emb": embeddings["research_problem"],
                "pl_text": paper_data["research_problem"]["previous_limitation"]["limitation"], "pl_emb": embeddings["previous_limitation"],
                "up_text": paper_data["research_problem"]["underlying_problem"]["detail"], "up_emb": embeddings["underlying_problem"]
            }),

            # 5. Method branch
            ("""
            MATCH (p:Paper {title: $title})
            CREATE (m:Method {high_level_description: $m_desc, embedding: $m_emb})
            CREATE (md:MethodDetail {method_detail: $md_text, method_section_pointer: $md_ptr, embedding: $md_emb})
            CREATE (ra:ReferredAlgorithm {algorithms: $ra_list, description: $ra_desc, embedding: $ra_emb})
            MERGE (p)-[:HAS_METHOD]->(m)
            MERGE (m)-[:HAS_METHOD_DETAIL]->(md)
            MERGE (m)-[:REFER_TO]->(ra)
            """, {
                "title": p_title,
                "m_desc": paper_data["method"]["high_level_description"], "m_emb": embeddings["method"],
                "md_text": paper_data["method"]["detail"]["method_detail"],
                "md_ptr": paper_data["method"]["detail"]["method_section_pointer"], "md_emb": embeddings["method_detail"],
                "ra_list": paper_data["method"]["referred_algorithms"]["algorithms"],
                "ra_desc": paper_data["method"]["referred_algorithms"]["description"], "ra_emb": embeddings["referred_algorithms"]
            }),

            # 6. Experiment
            ("""
            MATCH (p:Paper {title: $title})
            CREATE (e:Experiment {result: $r, experiment_section_pointer: $ptr, embedding: $emb})
            CREATE (ea:ExperimentAnalysis {design_overview: $ea_design, comprehensive_analysis: $ea_analysis, embedding: $ea_emb})
            MERGE (p)-[:HAS_EXPERIMENT]->(e)
            MERGE (e)-[:HAS_ANALYSIS]->(ea)
            """, {
                "title": p_title, "r": paper_data["experiment"]["result"],
                "ptr": paper_data["experiment"]["experiment_section_pointer"], "emb": embeddings["experiment"],
                "ea_design": paper_data["experiment"]["analysis"]["design_overview"],
                "ea_analysis": paper_data["experiment"]["analysis"]["comprehensive_analysis"],
                "ea_emb": embeddings["experiment_analysis"]
            }),

            # 7. Experiment Sub-nodes (ComparedMethod)
            ("""
            MATCH (p:Paper {title: $title})-[:HAS_EXPERIMENT]->(e:Experiment)
            UNWIND $compared AS cm
            MERGE (c:ComparedMethod {name: cm.name})
            SET c.embedding = cm.embedding
            MERGE (e)-[:COMPARED_WITH]->(c)
            """, {"title": p_title, "compared": paper_data["experiment"].get("compared_methods", [])}),

            # 8. Experiment Sub-nodes (Dataset)
            ("""
            MATCH (p:Paper {title: $title})-[:HAS_EXPERIMENT]->(e:Experiment)
            UNWIND $datasets AS ds
            MERGE (d:Dataset {name: ds.name})
            SET d.embedding = ds.embedding
            MERGE (e)-[:USES_DATASET]->(d)
            """, {"title": p_title, "datasets": paper_data["experiment"].get("datasets", [])}),
        ]

        with self.driver.session() as session:
            for q, p in queries:
                if "UNWIND" in q:
                    # check if list is empty
                    list_key = "keywords" if "keywords" in p else ("compared" if "compared" in p else "datasets")
                    if not p[list_key]:
                        continue
                session.run(q, **p)

    def find_similar_papers(self, target_embedding: List[float], exclude_title: str,
                            index_name: str = "research_problem_index", top_k: int = 5) -> List[Dict]:
        query = """
        CALL db.index.vector.queryNodes($index, $top_k, $embedding) YIELD node AS n, score
        MATCH (p:Paper)-[:HAS_SUMMARY|ADDRESSES|HAS_METHOD|HAS_EXPERIMENT|HAS_KEYWORD|ANALYZE|HAS_UNDERLYING_PROBLEM|HAS_ANALYSIS*1..3]-(n)
        WHERE p.title <> $exclude_title
        RETURN DISTINCT p.title AS title, labels(n)[0] AS matched_node_type, score
        ORDER BY score DESC
        """
        with self.driver.session() as session:
            res = session.run(query, index=index_name, embedding=target_embedding, top_k=top_k, exclude_title=exclude_title)
            return [dict(r) for r in res]

    def establish_subjective_relations(self, source_title: str, insights: List[dict]):
        if not insights: return
        with self.driver.session() as session:
            for insight in insights:
                q = (f"MATCH (a:Paper {{title: $s}}), (b:Paper {{title: $t}}) "
                     f"MERGE (a)-[r:{insight.relation_type}]->(b) SET r.reason = $r")
                session.run(q, s=source_title, t=insight.target_paper_title, r=insight.reason)

    # ─────────────────────────────────────────────────────────────
    # Peer Review Support Methods
    # ─────────────────────────────────────────────────────────────

    def setup_fulltext_indexes(self):
        """Create Lucene full-text indexes for fuzzy dataset/baseline matching."""
        with self.driver.session() as session:
            session.run("CREATE FULLTEXT INDEX dataset_fulltext_idx IF NOT EXISTS FOR (n:Dataset) ON EACH [n.name]")
            session.run("CREATE FULLTEXT INDEX compared_method_fulltext_idx IF NOT EXISTS FOR (n:ComparedMethod) ON EACH [n.name]")


    def find_problem_candidates(
        self,
        up_embedding: List[float],
        pl_embedding: List[float],
        exclude_title: str,
        top_k: int = 5,
        threshold: float = 0.6
    ) -> List[Dict]:
        """
        Vector search on UnderlyingProblem and PreviousLimitation indexes.
        Returns top-K unique Paper candidates with argmax score across both signals.
        """
        query = """
        CALL db.index.vector.queryNodes($index, $k, $emb) YIELD node AS n, score
        MATCH (rp:ResearchProblem)-[:ANALYZE|HAS_UNDERLYING_PROBLEM]->(n)
        MATCH (p:Paper)-[:ADDRESSES]->(rp)
        WHERE p.title <> $exclude AND score >= $threshold
        RETURN DISTINCT p.title AS title, score
        ORDER BY score DESC
        """
        scores: Dict[str, float] = {}
        with self.driver.session() as session:
            for index, emb in [("underlying_problem_index", up_embedding),
                                ("previous_limitation_index", pl_embedding)]:
                res = session.run(query, index=index, k=top_k, emb=emb,
                                  exclude=exclude_title, threshold=threshold)
                for r in res:
                    title = r["title"]
                    # argmax: keep highest score per paper across both searches
                    if title not in scores or r["score"] > scores[title]:
                        scores[title] = r["score"]

        # Return top-K by score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [{"title": t, "score": s} for t, s in ranked]

    @staticmethod
    def _lucene_fuzzy_term(name: str) -> str:
        """Extract the most distinctive single token for Lucene fuzzy search.
        Strips parenthetical content and takes the first non-trivial word."""
        import re
        clean = re.sub(r'\(.*?\)', '', name).strip()
        tokens = [t for t in clean.split() if len(t) > 2]
        return f"{tokens[0]}~" if tokens else f"{clean[:15]}~"

    def find_experiment_candidates_by_dataset(
        self,
        dataset_names: List[str],
        exclude_title: str,
        fuzzy_threshold: float = 0.5
    ) -> List[Dict]:
        """
        Full-text (Lucene fuzzy) search on Dataset nodes.
        Returns Paper candidates that share similar datasets.
        """
        if not dataset_names:
            return []
        candidates: Dict[str, float] = {}
        query = """
        CALL db.index.fulltext.queryNodes("dataset_fulltext_idx", $q) YIELD node AS n, score
        MATCH (e:Experiment)-[:USES_DATASET]->(n)
        MATCH (p:Paper)-[:HAS_EXPERIMENT]->(e)
        WHERE p.title <> $exclude AND score >= $threshold
        RETURN p.title AS title, max(score) AS best_score
        """
        with self.driver.session() as session:
            for name in dataset_names:
                fuzzy_q = self._lucene_fuzzy_term(name)
                try:
                    res = session.run(query, q=fuzzy_q, exclude=exclude_title, threshold=fuzzy_threshold)
                    for r in res:
                        t = r["title"]
                        if t not in candidates or r["best_score"] > candidates[t]:
                            candidates[t] = r["best_score"]
                except Exception:
                    continue  # skip bad tokens

        ranked = sorted(candidates.items(), key=lambda x: x[1], reverse=True)[:3]
        return [{"title": t, "score": s} for t, s in ranked]

    def find_experiment_candidates_by_baseline(
        self,
        baseline_names: List[str],
        exclude_title: str,
        fuzzy_threshold: float = 0.5
    ) -> List[Dict]:
        """
        Full-text (Lucene fuzzy) search on ComparedMethod nodes.
        Returns Paper candidates that share similar baselines.
        """
        if not baseline_names:
            return []
        candidates: Dict[str, float] = {}
        query = """
        CALL db.index.fulltext.queryNodes("compared_method_fulltext_idx", $q) YIELD node AS n, score
        MATCH (e:Experiment)-[:COMPARED_WITH]->(n)
        MATCH (p:Paper)-[:HAS_EXPERIMENT]->(e)
        WHERE p.title <> $exclude AND score >= $threshold
        RETURN p.title AS title, max(score) AS best_score
        """
        with self.driver.session() as session:
            for name in baseline_names:
                fuzzy_q = self._lucene_fuzzy_term(name)
                try:
                    res = session.run(query, q=fuzzy_q, exclude=exclude_title, threshold=fuzzy_threshold)
                    for r in res:
                        t = r["title"]
                        if t not in candidates or r["best_score"] > candidates[t]:
                            candidates[t] = r["best_score"]
                except Exception:
                    continue

        ranked = sorted(candidates.items(), key=lambda x: x[1], reverse=True)[:3]
        return [{"title": t, "score": s} for t, s in ranked]

    def get_paper_context_for_review(self, title: str) -> Dict:
        """
        Fetch UnderlyingProblem.detail, PreviousLimitation.limitation, and
        Method.high_level_description for LLM problem review.
        """
        query = """
        MATCH (p:Paper {title: $title})-[:ADDRESSES]->(rp:ResearchProblem)
        OPTIONAL MATCH (rp)-[:ANALYZE]->(pl:PreviousLimitation)
        OPTIONAL MATCH (rp)-[:HAS_UNDERLYING_PROBLEM]->(up:UnderlyingResearchProblem)
        OPTIONAL MATCH (p)-[:HAS_METHOD]->(m:Method)
        RETURN pl.limitation AS prior_limitation,
               up.detail AS underlying_problem,
               m.high_level_description AS method
        """
        with self.driver.session() as session:
            res = session.run(query, title=title).single()
            return dict(res) if res else {}

    def get_experiment_context_for_review(self, title: str) -> Dict:
        """
        Fetch Experiment result, ExperimentAnalysis, datasets, and baselines.
        """
        query = """
        MATCH (p:Paper {title: $title})-[:HAS_EXPERIMENT]->(e:Experiment)
        OPTIONAL MATCH (e)-[:HAS_ANALYSIS]->(ea:ExperimentAnalysis)
        OPTIONAL MATCH (e)-[:USES_DATASET]->(d:Dataset)
        OPTIONAL MATCH (e)-[:COMPARED_WITH]->(c:ComparedMethod)
        RETURN e.result AS result,
               ea.design_overview AS design,
               ea.comprehensive_analysis AS comprehensive_analysis,
               collect(DISTINCT d.name) AS datasets,
               collect(DISTINCT c.name) AS baselines
        """
        with self.driver.session() as session:
            res = session.run(query, title=title).single()
            return dict(res) if res else {}

    # ─── Edge Writers ───────────────────────────────────────────

    def write_problem_similarity_edge(
        self, paper_a: str, paper_b: str, shared_core_issue: str, approach_contrast: str
    ):
        with self.driver.session() as session:
            session.run("""
            MATCH (a:Paper {title: $a}), (b:Paper {title: $b})
            MERGE (a)-[r:TACKLES_SIMILAR_PROBLEM]->(b)
            SET r.shared_core_issue = $issue, r.approach_contrast = $contrast
            MERGE (b)-[r2:TACKLES_SIMILAR_PROBLEM]->(a)
            SET r2.shared_core_issue = $issue, r2.approach_contrast = $contrast
            """, a=paper_a, b=paper_b, issue=shared_core_issue, contrast=approach_contrast)

    def write_benchmark_edge(
        self, paper_a: str, paper_b: str, shared_datasets: List[str], micro_comparison: str
    ):
        with self.driver.session() as session:
            session.run("""
            MATCH (p1:Paper {title: $a})-[:HAS_EXPERIMENT]->(e1:Experiment)
            MATCH (p2:Paper {title: $b})-[:HAS_EXPERIMENT]->(e2:Experiment)
            MERGE (e1)-[r:EVALUATED_ON_SAME_BENCHMARK]->(e2)
            SET r.shared_datasets = $ds, r.micro_comparison_report = $report
            MERGE (e2)-[r2:EVALUATED_ON_SAME_BENCHMARK]->(e1)
            SET r2.shared_datasets = $ds, r2.micro_comparison_report = $report
            """, a=paper_a, b=paper_b, ds=shared_datasets, report=micro_comparison)

    def write_baseline_edge(
        self, paper_a: str, paper_b: str, shared_baselines: List[str], who_won: str
    ):
        with self.driver.session() as session:
            session.run("""
            MATCH (p1:Paper {title: $a})-[:HAS_EXPERIMENT]->(e1:Experiment)
            MATCH (p2:Paper {title: $b})-[:HAS_EXPERIMENT]->(e2:Experiment)
            MERGE (e1)-[r:HAS_COMMON_BASELINE]->(e2)
            SET r.shared_baselines = $bl, r.who_won = $won
            MERGE (e2)-[r2:HAS_COMMON_BASELINE]->(e1)
            SET r2.shared_baselines = $bl, r2.who_won = $won
            """, a=paper_a, b=paper_b, bl=shared_baselines, won=who_won)

