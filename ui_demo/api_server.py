"""
Flask API server for the Research Graph UI Demo.
Exposes REST endpoints that query Neo4j via the existing Neo4jClient.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, jsonify, request, send_from_directory, send_file
from flask_cors import CORS
from dotenv import load_dotenv
from src.core.graph.neo4j_client import Neo4jClient

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# ── Neo4j Connection ────────────────────────────────────────────
NEO4J_URI  = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "420420420")

db = Neo4jClient(NEO4J_URI, NEO4J_USER, NEO4J_PASS)

# ── Static File Serving ─────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# ── API Endpoints ───────────────────────────────────────────────

@app.route('/api/image')
def api_serve_image():
    path = request.args.get('path')
    if path and os.path.exists(path):
        return send_file(path)
    return "Not found", 404

@app.route('/api/stats')
def api_stats():
    with db.driver.session() as s:
        papers    = s.run("MATCH (p:Paper) RETURN count(p) as c").single()["c"]
        entities  = s.run("MATCH (n) WHERE NOT n:Paper RETURN count(n) as c").single()["c"]
        relations = s.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
    return jsonify({"papers": papers, "entities": entities, "relations": relations})


@app.route('/api/papers')
def api_papers():
    """List all papers with their Summary metadata and keywords."""
    query = """
    MATCH (p:Paper)-[:HAS_SUMMARY]->(s:Summary)
    OPTIONAL MATCH (p)-[:HAS_KEYWORD]->(k:Keyword)
    RETURN p.title AS title, s.year AS year, s.short_claim AS claim,
           collect(DISTINCT k.name) AS keywords
    ORDER BY s.year DESC
    """
    with db.driver.session() as s:
        results = [dict(r) for r in s.run(query)]
    return jsonify(results)


@app.route('/api/keywords')
def api_keywords():
    """List all keywords with usage count."""
    query = """
    MATCH (k:Keyword)<-[:HAS_KEYWORD]-(p:Paper)
    RETURN k.name AS name, count(p) AS count
    ORDER BY count DESC
    """
    with db.driver.session() as s:
        results = [dict(r) for r in s.run(query)]
    return jsonify(results)


@app.route('/api/papers/filter', methods=['POST'])
def api_papers_filter():
    """Filter papers by selected keyword names (AND logic)."""
    data = request.json or {}
    keywords = data.get("keywords", [])
    if not keywords:
        return api_papers()

    query = """
    MATCH (p:Paper)-[:HAS_SUMMARY]->(s:Summary)
    WHERE ALL(kw IN $keywords WHERE (p)-[:HAS_KEYWORD]->(:Keyword {name: kw}))
    OPTIONAL MATCH (p)-[:HAS_KEYWORD]->(k:Keyword)
    RETURN p.title AS title, s.year AS year, s.short_claim AS claim,
           collect(DISTINCT k.name) AS keywords
    ORDER BY s.year DESC
    """
    with db.driver.session() as s:
        results = [dict(r) for r in s.run(query, keywords=keywords)]
    return jsonify(results)


@app.route('/api/paper/<path:title>/overview')
def api_paper_overview(title):
    """
    Stage 1 – Lightweight overview: Paper metadata + Keywords as a flat array.
    Used to populate the accordion card header without any graph clutter.
    """
    with db.driver.session() as s:
        res = s.run("""
            MATCH (p:Paper {title: $t})
            OPTIONAL MATCH (p)-[:HAS_SUMMARY]->(sm:Summary)
            OPTIONAL MATCH (p)-[:HAS_KEYWORD]->(k:Keyword)
            OPTIONAL MATCH (p)-[:ADDRESSES]->(rp:ResearchProblem)
            OPTIONAL MATCH (p)-[:HAS_METHOD]->(m:Method)
            OPTIONAL MATCH (p)-[:HAS_EXPERIMENT]->(e:Experiment)
            RETURN
                p.title AS title,
                sm.year AS year,
                sm.short_claim AS claim,
                collect(DISTINCT k.name) AS keywords,
                rp IS NOT NULL AS has_problem,
                m.high_level_description AS method_pitch,
                e.result AS experiment_summary
        """, t=title).single()
        if not res:
            return jsonify({"error": "Paper not found"}), 404
        return jsonify(dict(res))


@app.route('/api/paper/<path:title>/section/problem')
def api_section_problem(title):
    """Stage 2 – On-demand: Research Problem details (L2 + L3)."""
    with db.driver.session() as s:
        res = s.run("""
            MATCH (p:Paper {title: $t})-[:ADDRESSES]->(rp:ResearchProblem)
            OPTIONAL MATCH (rp)-[:ANALYZE]->(pl:PreviousLimitation)
            OPTIONAL MATCH (rp)-[:HAS_UNDERLYING_PROBLEM]->(up:UnderlyingResearchProblem)
            RETURN
                rp.summary AS summary,
                pl.limitation AS previous_limitation,
                up.detail AS underlying_problem
        """, t=title).single()
        if not res:
            return jsonify({"error": "Not found"}), 404
        return jsonify(dict(res))


@app.route('/api/paper/<path:title>/section/method')
def api_section_method(title):
    """Stage 2 – On-demand: Method details (L2 + L3)."""
    with db.driver.session() as s:
        res = s.run("""
            MATCH (p:Paper {title: $t})-[:HAS_METHOD]->(m:Method)
            OPTIONAL MATCH (m)-[:HAS_METHOD_DETAIL]->(md:MethodDetail)
            OPTIONAL MATCH (m)-[:REFER_TO]->(ra:ReferredAlgorithm)
            RETURN
                m.high_level_description AS overview,
                md.method_detail AS detail,
                md.method_section_pointer AS section_pointer,
                ra.algorithms AS algorithms,
                ra.description AS algorithm_description
        """, t=title).single()
        if not res:
            return jsonify({"error": "Not found"}), 404
        data = dict(res)
        # Algorithms may be stored as a list
        if isinstance(data.get("algorithms"), list):
            data["algorithms"] = data["algorithms"]  # keep as list for frontend
        return jsonify(data)


@app.route('/api/paper/<path:title>/section/experiment')
def api_section_experiment(title):
    """Stage 2 – On-demand: Experiment details (L2 + L3)."""
    with db.driver.session() as s:
        res = s.run("""
            MATCH (p:Paper {title: $t})-[:HAS_EXPERIMENT]->(e:Experiment)
            OPTIONAL MATCH (e)-[:HAS_ANALYSIS]->(ea:ExperimentAnalysis)
            OPTIONAL MATCH (e)-[:USES_DATASET]->(d:Dataset)
            OPTIONAL MATCH (e)-[:COMPARED_WITH]->(cm:ComparedMethod)
            RETURN
                e.result AS result,
                e.experiment_section_pointer AS section_pointer,
                ea.design_overview AS design,
                ea.comprehensive_analysis AS comprehensive_analysis,
                collect(DISTINCT d.name) AS datasets,
                collect(DISTINCT cm.name) AS compared_methods
        """, t=title).single()
        if not res:
            return jsonify({"error": "Not found"}), 404
        return jsonify(dict(res))


@app.route('/api/paper/<path:title>/anatomy')
def api_paper_anatomy(title):
    """Full intra-paper graph: all L1→L2→L3 nodes and edges (legacy)."""
    nodes = []
    edges = []


    with db.driver.session() as s:
        # Paper root
        nodes.append({"id": title, "label": title[:40], "type": "Paper", "level": 1, "properties": {"title": title}})

        # Summary (L2)
        res = s.run("MATCH (p:Paper {title: $t})-[:HAS_SUMMARY]->(n:Summary) RETURN n", t=title).single()
        if res:
            n = dict(res["n"])
            nid = f"Summary_{title}"
            emb_status = "embedding" in n and n["embedding"] is not None
            props = {k: v for k, v in n.items() if k != "embedding"}
            props["has_embedding"] = emb_status
            nodes.append({"id": nid, "label": "Summary", "type": "Summary", "level": 2, "properties": props})
            edges.append({"source": title, "target": nid, "type": "HAS_SUMMARY"})

        # Keywords (L2)
        kws = s.run("MATCH (p:Paper {title: $t})-[:HAS_KEYWORD]->(k:Keyword) RETURN k.name AS name", t=title)
        for r in kws:
            nid = f"Keyword_{r['name']}"
            nodes.append({"id": nid, "label": r["name"], "type": "Keyword", "level": 2,
                          "properties": {"name": r["name"], "has_embedding": True}})
            edges.append({"source": title, "target": nid, "type": "HAS_KEYWORD"})

        # ResearchProblem (L2) → PreviousLimitation, UnderlyingProblem (L3)
        rp = s.run("""
            MATCH (p:Paper {title: $t})-[:ADDRESSES]->(rp:ResearchProblem)
            OPTIONAL MATCH (rp)-[:ANALYZE]->(pl:PreviousLimitation)
            OPTIONAL MATCH (rp)-[:HAS_UNDERLYING_PROBLEM]->(up:UnderlyingResearchProblem)
            RETURN rp, pl, up
        """, t=title).single()
        if rp:
            # L2: ResearchProblem
            rp_node = dict(rp["rp"])
            rp_id = f"ResearchProblem_{title}"
            rp_props = {k: v for k, v in rp_node.items() if k != "embedding"}
            rp_props["has_embedding"] = "embedding" in rp_node and rp_node["embedding"] is not None
            nodes.append({"id": rp_id, "label": "Research Problem", "type": "ResearchProblem", "level": 2, "properties": rp_props})
            edges.append({"source": title, "target": rp_id, "type": "ADDRESSES"})

            # L3: PreviousLimitation
            if rp["pl"]:
                pl_node = dict(rp["pl"])
                pl_id = f"PreviousLimitation_{title}"
                pl_props = {k: v for k, v in pl_node.items() if k != "embedding"}
                pl_props["has_embedding"] = "embedding" in pl_node and pl_node["embedding"] is not None
                nodes.append({"id": pl_id, "label": "Previous Limitation", "type": "PreviousLimitation", "level": 3, "properties": pl_props, "parent": rp_id})
                edges.append({"source": rp_id, "target": pl_id, "type": "ANALYZE"})

            # L3: UnderlyingProblem
            if rp["up"]:
                up_node = dict(rp["up"])
                up_id = f"UnderlyingProblem_{title}"
                up_props = {k: v for k, v in up_node.items() if k != "embedding"}
                up_props["has_embedding"] = "embedding" in up_node and up_node["embedding"] is not None
                nodes.append({"id": up_id, "label": "Underlying Problem", "type": "UnderlyingResearchProblem", "level": 3, "properties": up_props, "parent": rp_id})
                edges.append({"source": rp_id, "target": up_id, "type": "HAS_UNDERLYING_PROBLEM"})

        # Method (L2) → MethodDetail, ReferredAlgorithm (L3)
        mth = s.run("""
            MATCH (p:Paper {title: $t})-[:HAS_METHOD]->(m:Method)
            OPTIONAL MATCH (m)-[:HAS_METHOD_DETAIL]->(md:MethodDetail)
            OPTIONAL MATCH (m)-[:REFER_TO]->(ra:ReferredAlgorithm)
            RETURN m, md, ra
        """, t=title).single()
        if mth:
            m_node = dict(mth["m"])
            m_id = f"Method_{title}"
            m_props = {k: v for k, v in m_node.items() if k != "embedding"}
            m_props["has_embedding"] = "embedding" in m_node and m_node["embedding"] is not None
            nodes.append({"id": m_id, "label": "Method", "type": "Method", "level": 2, "properties": m_props})
            edges.append({"source": title, "target": m_id, "type": "HAS_METHOD"})

            if mth["md"]:
                md_node = dict(mth["md"])
                md_id = f"MethodDetail_{title}"
                md_props = {k: v for k, v in md_node.items() if k != "embedding"}
                md_props["has_embedding"] = "embedding" in md_node and md_node["embedding"] is not None
                nodes.append({"id": md_id, "label": "Method Detail", "type": "MethodDetail", "level": 3, "properties": md_props, "parent": m_id})
                edges.append({"source": m_id, "target": md_id, "type": "HAS_METHOD_DETAIL"})

            if mth["ra"]:
                ra_node = dict(mth["ra"])
                ra_id = f"ReferredAlgorithm_{title}"
                ra_props = {k: v for k, v in ra_node.items() if k != "embedding"}
                ra_props["has_embedding"] = "embedding" in ra_node and ra_node["embedding"] is not None
                # Convert list to string for display
                if "algorithms" in ra_props and isinstance(ra_props["algorithms"], list):
                    ra_props["algorithms"] = ", ".join(ra_props["algorithms"])
                nodes.append({"id": ra_id, "label": "Referred Algorithms", "type": "ReferredAlgorithm", "level": 3, "properties": ra_props, "parent": m_id})
                edges.append({"source": m_id, "target": ra_id, "type": "REFER_TO"})

        # Experiment (L2) → ExperimentAnalysis, ComparedMethod, Dataset (L3)
        exp = s.run("""
            MATCH (p:Paper {title: $t})-[:HAS_EXPERIMENT]->(e:Experiment)
            OPTIONAL MATCH (e)-[:HAS_ANALYSIS]->(ea:ExperimentAnalysis)
            RETURN e, ea
        """, t=title).single()
        if exp:
            e_node = dict(exp["e"])
            e_id = f"Experiment_{title}"
            e_props = {k: v for k, v in e_node.items() if k != "embedding"}
            e_props["has_embedding"] = "embedding" in e_node and e_node["embedding"] is not None
            nodes.append({"id": e_id, "label": "Experiment", "type": "Experiment", "level": 2, "properties": e_props})
            edges.append({"source": title, "target": e_id, "type": "HAS_EXPERIMENT"})

            if exp["ea"]:
                ea_node = dict(exp["ea"])
                ea_id = f"ExperimentAnalysis_{title}"
                ea_props = {k: v for k, v in ea_node.items() if k != "embedding"}
                ea_props["has_embedding"] = "embedding" in ea_node and ea_node["embedding"] is not None
                nodes.append({"id": ea_id, "label": "Experiment Analysis", "type": "ExperimentAnalysis", "level": 3, "properties": ea_props, "parent": e_id})
                edges.append({"source": e_id, "target": ea_id, "type": "HAS_ANALYSIS"})

            # ComparedMethod (L3)
            cms = s.run("MATCH (p:Paper {title: $t})-[:HAS_EXPERIMENT]->(e)-[:COMPARED_WITH]->(c:ComparedMethod) RETURN c.name AS name", t=title)
            for r in cms:
                c_id = f"ComparedMethod_{r['name']}"
                nodes.append({"id": c_id, "label": r["name"], "type": "ComparedMethod", "level": 3,
                              "properties": {"name": r["name"], "has_embedding": True}, "parent": e_id})
                edges.append({"source": e_id, "target": c_id, "type": "COMPARED_WITH"})

            # Dataset (L3)
            dss = s.run("MATCH (p:Paper {title: $t})-[:HAS_EXPERIMENT]->(e)-[:USES_DATASET]->(d:Dataset) RETURN d.name AS name", t=title)
            for r in dss:
                d_id = f"Dataset_{r['name']}"
                nodes.append({"id": d_id, "label": r["name"], "type": "Dataset", "level": 3,
                              "properties": {"name": r["name"], "has_embedding": True}, "parent": e_id})
                edges.append({"source": e_id, "target": d_id, "type": "USES_DATASET"})

    return jsonify({"nodes": nodes, "edges": edges})


@app.route('/api/paper/<path:title>/relations')
def api_paper_relations(title):
    """Inter-paper edges: TACKLES_SIMILAR_PROBLEM, EVALUATED_ON_SAME_BENCHMARK, HAS_COMMON_BASELINE."""
    nodes = [{"id": title, "label": title[:40], "type": "Paper", "is_center": True}]
    edges = []
    seen_titles = {title}

    with db.driver.session() as s:
        # Problem similarity edges (Paper-level)
        rels = s.run("""
            MATCH (p1:Paper {title: $t})-[r:TACKLES_SIMILAR_PROBLEM]-(p2:Paper)
            RETURN p2.title AS target, r.shared_core_issue AS issue,
                   r.approach_contrast AS contrast, type(r) AS rel_type
        """, t=title)
        for r in rels:
            target = r["target"]
            if target not in seen_titles:
                nodes.append({"id": target, "label": target[:40], "type": "Paper", "is_center": False})
                seen_titles.add(target)
            edges.append({
                "source": title, "target": target,
                "type": "TACKLES_SIMILAR_PROBLEM",
                "properties": {"shared_core_issue": r["issue"], "approach_contrast": r["contrast"]}
            })

        # Benchmark edges (Experiment-level, but we map to Paper)
        rels2 = s.run("""
            MATCH (p1:Paper {title: $t})-[:HAS_EXPERIMENT]->(e1)-[r:EVALUATED_ON_SAME_BENCHMARK]-(e2)<-[:HAS_EXPERIMENT]-(p2:Paper)
            RETURN DISTINCT p2.title AS target, r.shared_datasets AS datasets,
                   r.micro_comparison_report AS report
        """, t=title)
        for r in rels2:
            target = r["target"]
            if target not in seen_titles:
                nodes.append({"id": target, "label": target[:40], "type": "Paper", "is_center": False})
                seen_titles.add(target)
            ds = r["datasets"]
            if isinstance(ds, list):
                ds = ", ".join(ds)
            edges.append({
                "source": title, "target": target,
                "type": "EVALUATED_ON_SAME_BENCHMARK",
                "properties": {"shared_datasets": ds, "micro_comparison_report": r["report"]}
            })

        # Baseline edges
        rels3 = s.run("""
            MATCH (p1:Paper {title: $t})-[:HAS_EXPERIMENT]->(e1)-[r:HAS_COMMON_BASELINE]-(e2)<-[:HAS_EXPERIMENT]-(p2:Paper)
            RETURN DISTINCT p2.title AS target, r.shared_baselines AS baselines,
                   r.who_won AS won
        """, t=title)
        for r in rels3:
            target = r["target"]
            if target not in seen_titles:
                nodes.append({"id": target, "label": target[:40], "type": "Paper", "is_center": False})
                seen_titles.add(target)
            bl = r["baselines"]
            if isinstance(bl, list):
                bl = ", ".join(bl)
            edges.append({
                "source": title, "target": target,
                "type": "HAS_COMMON_BASELINE",
                "properties": {"shared_baselines": bl, "who_won": r["won"]}
            })

    return jsonify({"nodes": nodes, "edges": edges})


if __name__ == '__main__':
    print("🚀 Starting Research Graph UI API on http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=True)
