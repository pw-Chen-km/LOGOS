import json
from typing import List
from langchain_core.tools import tool


class GraphQAToolsFactory:
    """
    QA Tools for the final mixed-hierarchy ontology:
      L2 flat:  Summary, Keyword, ResearchProblem, PreviousLimitation, UnderlyingResearchProblem
      L2→L3:    Method → MethodDetail, ReferredAlgorithm
                Experiment → ComparedMethod, Dataset
    """
    def __init__(self, db_client, embeddings_model):
        self.db = db_client
        self.em = embeddings_model

    def get_tools(self) -> list:

        @tool
        def get_graph_schema_tool() -> str:
            """Returns the current graph schema (node labels + valid relationships)."""
            try:
                with self.db.driver.session() as session:
                    paths  = session.run(
                        "MATCH (a)-[r]->(b) "
                        "RETURN DISTINCT labels(a)[0]+'-['+type(r)+ ']->'+labels(b)[0] AS path"
                    )
                    labels = session.run(
                        "CALL db.labels() YIELD label RETURN collect(label) AS labels"
                    ).single()["labels"]
                return json.dumps({
                    "NodeLabels": labels,
                    "Valid_Connections": [r["path"] for r in paths]
                })
            except Exception as e:
                return f"Error: {e}"

        @tool
        def semantic_anchor_tool(
            query: str,
            entity_type: str = "Paper",
            property_focus: str = "research_problem",
            top_k: int = 3,
            score_threshold: float = 0.7
        ) -> str:
            """
            Finds relevant node anchors via vector similarity.

            entity_type='Paper' → searches a child-node index and returns parent Paper titles.
              property_focus options: 'research_problem', 'previous_limitation',
                                      'summary', 'method', 'method_detail',
                                      'referred_algorithms', 'experiment'

            entity_type='Keyword' | 'Dataset' | 'ComparedMethod' → searches shared entity indexes.
            """
            INDEX_MAP_PAPER = {
                "research_problem":    "research_problem_index",
                "previous_limitation": "previous_limitation_index",
                "underlying_problem":  "underlying_problem_index",
                "summary":             "summary_index",
                "method":              "method_index",
                "method_detail":       "method_detail_index",
                "referred_algorithms": "referred_algorithm_index",
                "experiment":          "experiment_index",
                "experiment_analysis": "experiment_analysis_index",
            }
            INDEX_MAP_ENTITY = {
                "Keyword":       "keyword_index",
                "Dataset":       "dataset_index",
                "ComparedMethod":"compared_method_index",
            }
            try:
                embedding = self.em.embed_query(query)

                if entity_type == "Paper":
                    index_name = INDEX_MAP_PAPER.get(property_focus, "research_problem_index")
                    cypher = """
                    CALL db.index.vector.queryNodes($index, $top_k, $embedding) YIELD node AS n, score
                    MATCH (p:Paper)-[:HAS_SUMMARY|HAS_METHOD|HAS_EXPERIMENT|HAS_KEYWORD|ADDRESSES|ANALYZE|HAS_UNDERLYING_PROBLEM*1..3]-(n)
                    RETURN DISTINCT p.title AS id, labels(n)[0] AS matched_child, score
                    ORDER BY score DESC
                    """
                    with self.db.driver.session() as session:
                        res = session.run(cypher, index=index_name, embedding=embedding, top_k=top_k)
                        hits = [{"title": r["id"], "score": r["score"], "matched_via": r["matched_child"]}
                                for r in res if r["score"] >= score_threshold]
                    return json.dumps(hits or {"note": "No results above threshold."})

                elif entity_type in INDEX_MAP_ENTITY:
                    index_name = INDEX_MAP_ENTITY[entity_type]
                    cypher = (
                        f"CALL db.index.vector.queryNodes('{index_name}', $top_k, $embedding) "
                        "YIELD node AS n, score RETURN n.name AS id, score"
                    )
                    with self.db.driver.session() as session:
                        res = session.run(cypher, embedding=embedding, top_k=top_k)
                        hits = [{"name": r["id"], "score": r["score"]}
                                for r in res if r["score"] >= score_threshold]
                    return json.dumps(hits or {"note": "No results above threshold."})

                else:
                    return f"Error: unsupported entity_type '{entity_type}'."

            except Exception as e:
                return f"Error: {e}"

        @tool
        def topological_navigate_tool(source_node_names: List[str], edge_type: str = None) -> str:
            """
            Bidirectional graph traversal from a set of node names.
            Optionally filter by edge_type.
            Returns source → relation → target triples.
            """
            try:
                rel_clause = f":{edge_type}" if edge_type else ""
                cypher = f"""
                MATCH (n)-[r{rel_clause}]-(m)
                WHERE n.name IN $names OR n.title IN $names
                RETURN n.name AS s_n, n.title AS s_t, type(r) AS rel,
                       m.name AS t_n, m.title AS t_t, labels(m) AS t_l,
                       m.summary AS t_summary, m.limitation AS t_lim,
                       m.detail AS t_det, m.result AS t_res,
                       m.high_level_description AS t_desc
                LIMIT 60
                """
                with self.db.driver.session() as session:
                    res = session.run(cypher, names=source_node_names)
                    rows = []
                    for r in res:
                        src = r["s_n"] or r["s_t"]
                        tgt = (r["t_n"] or r["t_t"] or r["t_summary"]
                               or r["t_lim"] or r["t_det"] or r["t_res"] or r["t_desc"])
                        rows.append({"source": src, "rel": r["rel"],
                                     "target": tgt, "target_labels": r["t_l"]})
                return json.dumps(rows)
            except Exception as e:
                return f"Error: {e}"

        @tool
        def read_properties_tool(node_title: str, level: str = "L1") -> str:
            """
            Reads detailed properties of a Paper by traversing its child nodes.

            L1 → Summary (year, short_claim)
            L2 → Research Problem cluster (ResearchProblem summary, PreviousLimitation, UnderlyingProblem)
            L3 → Method & Experiment (brief, detail, referred algorithms, results, datasets, baselines)
            """
            try:
                with self.db.driver.session() as session:
                    if level == "L1":
                        res = session.run(
                            "MATCH (p:Paper {title:$t})-[:HAS_SUMMARY]->(s:Summary) "
                            "RETURN s.year AS year, s.short_claim AS claim",
                            t=node_title
                        ).single()
                        return json.dumps(dict(res)) if res else "Not found."

                    elif level == "L2":
                        res = session.run("""
                            MATCH (p:Paper {title:$t})-[:ADDRESSES]->(rp:ResearchProblem)
                            OPTIONAL MATCH (rp)-[:ANALYZE]->(pl:PreviousLimitation)
                            OPTIONAL MATCH (rp)-[:HAS_UNDERLYING_PROBLEM]->(up:UnderlyingResearchProblem)
                            RETURN rp.summary AS problem_summary,
                                   pl.limitation AS prior_limitations,
                                   up.detail AS underlying_detail
                        """, t=node_title).single()
                        return json.dumps(dict(res)) if res else "Not found."

                    elif level == "L3":
                        res = session.run("""
                            MATCH (p:Paper {title:$t})
                            OPTIONAL MATCH (p)-[:HAS_METHOD]->(m:Method)
                            OPTIONAL MATCH (m)-[:HAS_METHOD_DETAIL]->(md:MethodDetail)
                            OPTIONAL MATCH (m)-[:REFER_TO]->(ra:ReferredAlgorithm)
                            OPTIONAL MATCH (p)-[:HAS_EXPERIMENT]->(e:Experiment)
                            OPTIONAL MATCH (e)-[:HAS_ANALYSIS]->(ea:ExperimentAnalysis)
                            OPTIONAL MATCH (e)-[:USES_DATASET]->(d:Dataset)
                            OPTIONAL MATCH (e)-[:COMPARED_WITH]->(c:ComparedMethod)
                            RETURN m.high_level_description AS method_brief,
                                   md.method_detail AS method_full,
                                   ra.algorithms AS referred_algorithms,
                                   e.result AS experiment_results,
                                   ea.design AS exp_design,
                                   ea.sota_comparison AS exp_sota,
                                   ea.ablation_study AS exp_ablation,
                                   collect(DISTINCT d.name) AS datasets,
                                   collect(DISTINCT c.name) AS baselines
                        """, t=node_title).single()
                        return json.dumps(dict(res)) if res else "Not found."

                    return "Invalid level. Use L1, L2, or L3."

            except Exception as e:
                return f"Error: {e}"

        @tool
        def broadcast_scan_tool(query: str, top_k: int = 3, score_threshold: float = 0.6) -> str:
            """
            Scans ALL vector indexes simultaneously and returns the best hits per node type.
            Use this as a first-pass discovery tool when you don't know which index to target.
            """
            INDEX_LABELS = {
                "summary_index":            "Summary",
                "research_problem_index":   "ResearchProblem",
                "previous_limitation_index":"PreviousLimitation",
                "underlying_problem_index": "UnderlyingResearchProblem",
                "method_index":             "Method",
                "method_detail_index":      "MethodDetail",
                "referred_algorithm_index": "ReferredAlgorithm",
                "experiment_index":         "Experiment",
                "experiment_analysis_index":"ExperimentAnalysis",
                "keyword_index":            "Keyword",
                "dataset_index":            "Dataset",
                "compared_method_index":    "ComparedMethod",
            }
            try:
                embedding = self.em.embed_query(query)
                results   = {}
                with self.db.driver.session() as session:
                    for idx_name, label in INDEX_LABELS.items():
                        res = session.run(
                            f"CALL db.index.vector.queryNodes('{idx_name}', $top_k, $embedding) "
                            "YIELD node AS n, score RETURN n, score",
                            embedding=embedding, top_k=top_k
                        )
                        for r in res:
                            if r["score"] < score_threshold:
                                continue
                            if label not in results:
                                results[label] = []
                            node = r["n"]
                            ident = (node.get("name") or node.get("title") or
                                     node.get("summary") or node.get("short_claim") or
                                     (node.get("limitation") or "")[:80] or
                                     (node.get("detail") or "")[:80] or
                                     str(node.get("algorithms", [])))
                            results[label].append({"id": ident, "score": round(r["score"], 4)})
                return json.dumps(results)
            except Exception as e:
                return f"Error: {e}"

        return [
            get_graph_schema_tool,
            semantic_anchor_tool,
            topological_navigate_tool,
            read_properties_tool,
            broadcast_scan_tool,
        ]
