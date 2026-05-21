import streamlit as st
import os
import time
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Import backend components
from src.core.extraction.docling_parser import PdfExtractor
from src.core.agent.deep_reader import DeepReaderAgent
from src.core.agent.peer_reviewer import PeerReviewAgent
from src.core.graph.neo4j_client import Neo4jClient
from langchain_openai import OpenAIEmbeddings

# Load environment variables
load_dotenv()

st.set_page_config(page_title="Research Graph Demo", page_icon="🧬", layout="wide")

# --- Styling ---
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    .stMetric {
        background-color: #1e2130;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #3e4150;
    }
    .paper-card {
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #3e4150;
        margin-bottom: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.title("🧬 Settings")
    
    default_api_key = os.getenv("OPENAI_API_KEY", "")
    default_uri = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
    default_user = os.getenv("NEO4J_USER", "neo4j")
    default_pass = os.getenv("NEO4J_PASSWORD", "420420420")
    
    api_key = st.text_input("OpenAI API Key", value=default_api_key, type="password")
    neo4j_uri = st.text_input("Neo4j URI", value=default_uri)
    neo4j_user = st.text_input("Neo4j Username", value=default_user)
    neo4j_pass = st.text_input("Neo4j Password", value=default_pass, type="password")
    
    st.markdown("---")
    if st.button("Clear Cache"):
        st.cache_resource.clear()
        st.success("Cache cleared!")

# --- Backend Initialization ---
@st.cache_resource
def get_db_client(_uri, _user, _pwd):
    try:
        client = Neo4jClient(_uri, _user, _pwd)
        return client
    except Exception as e:
        st.error(f"Failed to connect to Neo4j: {e}")
        return None

db = get_db_client(neo4j_uri, neo4j_user, neo4j_pass)

# --- Helper Functions ---
def get_stats(db_client):
    if not db_client: return {"papers": 0, "entities": 0, "relations": 0}
    with db_client.driver.session() as session:
        papers = session.run("MATCH (p:Paper) RETURN count(p) as c").single()["c"]
        entities = session.run("MATCH (n) WHERE NOT n:Paper RETURN count(n) as c").single()["c"]
        relations = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
        return {"papers": papers, "entities": entities, "relations": relations}

def get_papers_list(db_client):
    if not db_client: return []
    with db_client.driver.session() as session:
        res = session.run("MATCH (p:Paper)-[:HAS_SUMMARY]->(s:Summary) RETURN p.title as title, s.year as year ORDER BY s.year DESC")
        return [dict(r) for r in res]

def get_paper_full_details(db_client, title):
    if not db_client: return None
    with db_client.driver.session() as session:
        # Get Summary and Metadata
        summary = session.run("""
            MATCH (p:Paper {title: $title})-[:HAS_SUMMARY]->(s:Summary)
            RETURN s.year as year, s.short_claim as claim
        """, title=title).single()
        
        # Get Method
        method = session.run("""
            MATCH (p:Paper {title: $title})-[:HAS_METHOD]->(m:Method)
            OPTIONAL MATCH (m)-[:HAS_METHOD_DETAIL]->(md:MethodDetail)
            RETURN m.high_level_description as desc, md.method_detail as detail
        """, title=title).single()
        
        # Get Relationships (TACKLES_SIMILAR_PROBLEM, etc.)
        rels = session.run("""
            MATCH (p1:Paper {title: $title})-[r:TACKLES_SIMILAR_PROBLEM|EVALUATED_ON_SAME_BENCHMARK|HAS_COMMON_BASELINE]-(p2:Paper)
            RETURN type(r) as rel_type, p2.title as target, 
                   r.shared_core_issue as issue, r.approach_contrast as contrast,
                   r.shared_datasets as datasets, r.micro_comparison_report as report,
                   r.shared_baselines as baselines, r.who_won as won
        """, title=title)
        
        return {
            "summary": dict(summary) if summary else None,
            "method": dict(method) if method else None,
            "relations": [dict(r) for r in rels]
        }

# --- Main Page ---
st.title("🧬 Research Paper Knowledge Graph")

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📥 Ingest Paper", "🔍 Explorer"])

with tab1:
    st.header("Graph Overview")
    stats = get_stats(db)
    col1, col2, col3 = st.columns(3)
    col1.metric("Papers", stats["papers"])
    col2.metric("Entities", stats["entities"])
    col3.metric("Relationships", stats["relations"])
    
    st.markdown("---")
    st.subheader("Recent Activity")
    # Placeholder for recent ingestion logs or newly added papers
    papers = get_papers_list(db)
    if papers:
        st.write(f"Latest Paper: **{papers[0]['title']}** ({papers[0]['year']})")
    else:
        st.write("No papers in database yet.")

with tab2:
    st.header("Process New Research Paper")
    arxiv_url = st.text_input("ArXiv PDF URL", placeholder="https://arxiv.org/pdf/2401.00001.pdf")
    
    if st.button("🚀 Start Ingestion Pipeline"):
        if not api_key:
            st.warning("Please provide an OpenAI API Key in the sidebar.")
        elif not arxiv_url:
            st.warning("Please provide a valid ArXiv URL.")
        else:
            # Create output dir
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = f"output_{timestamp}"
            os.makedirs(output_dir, exist_ok=True)
            
            with st.status("Initializing Ingestion Pipeline...", expanded=True) as status:
                try:
                    # Stage 0: Extraction
                    status.update(label="🧬 Stage 0: Docling Extraction...")
                    extractor = PdfExtractor(output_dir)
                    md_path = extractor.extract(arxiv_url)
                    st.write(f"✅ Extracted Markdown to {md_path}")
                    
                    # Stage 1: Deep Reading
                    status.update(label="🧠 Stage 1: Deep Reading (LLM)...")
                    reader = DeepReaderAgent(api_key=api_key, model_name="gpt-4o-mini")
                    result = reader.run(md_path, output_json_path=f"{output_dir}/deep_reading_output.json")
                    paper_data = result.model_dump()
                    st.write(f"✅ Extracted metadata for: **{paper_data['paper']['title']}**")
                    
                    # Stage 2: Embeddings
                    status.update(label="🔢 Stage 2: Embedding Generation...")
                    em = OpenAIEmbeddings(api_key=api_key, model="text-embedding-3-small")
                    
                    # (Simplified embedding logic from run_phase2.py)
                    sm = paper_data["summary"]
                    rp = paper_data["research_problem"]
                    m  = paper_data["method"]
                    exp = paper_data["experiment"]
                    
                    core_texts = [
                        f"{sm['year']} {sm['short_claim']}", # 0
                        rp["summary"],                        # 1
                        rp["previous_limitation"]["limitation"], # 2
                        rp["underlying_problem"]["detail"],     # 3
                        m["high_level_description"],           # 4
                        m["detail"]["method_detail"],          # 5
                        m["referred_algorithms"]["description"], # 6
                        exp["result"],                         # 7
                        f"Design: {exp['analysis']['design_overview']}\nAnalysis:\n{exp['analysis']['comprehensive_analysis']}" # 8
                    ]
                    
                    # Keywords, Datasets, Baselines
                    kw_names = [k["name"] for k in paper_data.get("keywords", [])]
                    ds_names = [d["name"] for d in exp.get("datasets", [])]
                    cm_names = [c["name"] for c in exp.get("compared_methods", [])]
                    
                    all_texts = core_texts + kw_names + ds_names + cm_names
                    all_embs = em.embed_documents(all_texts)
                    
                    node_embeddings = {
                        "summary": all_embs[0],
                        "research_problem": all_embs[1],
                        "previous_limitation": all_embs[2],
                        "underlying_problem": all_embs[3],
                        "method": all_embs[4],
                        "method_detail": all_embs[5],
                        "referred_algorithms": all_embs[6],
                        "experiment": all_embs[7],
                        "experiment_analysis": all_embs[8],
                    }
                    
                    idx = 9
                    for k in paper_data.get("keywords", []): k["embedding"] = all_embs[idx]; idx += 1
                    for d in exp.get("datasets", []): d["embedding"] = all_embs[idx]; idx += 1
                    for c in exp.get("compared_methods", []): c["embedding"] = all_embs[idx]; idx += 1
                    
                    st.write("✅ Vectorized all text blocks.")
                    
                    # Stage 3: Ingestion
                    status.update(label="🕸️ Stage 3: Graph Ingestion...")
                    db.ingest_paper_base(paper_data, node_embeddings)
                    db.setup_fulltext_indexes()
                    st.write("✅ Ingested base paper data to Neo4j.")
                    
                    # Stage 4: Peer Review
                    status.update(label="🔭 Stage 4: Cross-Paper Peer Review...")
                    reviewer = PeerReviewAgent(api_key=api_key, model_name="gpt-4o-mini")
                    
                    # Problem candidates
                    prob_cands_raw = db.find_problem_candidates(
                        up_embedding=node_embeddings["underlying_problem"],
                        pl_embedding=node_embeddings["previous_limitation"],
                        exclude_title=paper_data["paper"]["title"]
                    )
                    prob_cands = [{"title": c["title"], "score": c["score"], "context": db.get_paper_context_for_review(c["title"])} for c in prob_cands_raw]
                    
                    # Dataset candidates
                    new_ds_names = [d["name"] for d in paper_data["experiment"].get("datasets", [])]
                    ds_cands_raw = db.find_experiment_candidates_by_dataset(new_ds_names, paper_data["paper"]["title"])
                    ds_cands = [{"title": c["title"], "score": c["score"], "context": db.get_experiment_context_for_review(c["title"])} for c in ds_cands_raw]
                    
                    # Baseline candidates
                    new_bl_names = [c["name"] for c in paper_data["experiment"].get("compared_methods", [])]
                    bl_cands_raw = db.find_experiment_candidates_by_baseline(new_bl_names, paper_data["paper"]["title"])
                    bl_cands = [{"title": c["title"], "score": c["score"], "context": db.get_experiment_context_for_review(c["title"])} for c in bl_cands_raw]
                    
                    # Run LLM reviews
                    new_ctx = db.get_paper_context_for_review(paper_data["paper"]["title"])
                    new_exp_ctx = db.get_experiment_context_for_review(paper_data["paper"]["title"])
                    
                    problem_review = reviewer.run_problem_review(paper_data["paper"]["title"], new_ctx, prob_cands)
                    benchmark_review = reviewer.run_benchmark_review(paper_data["paper"]["title"], new_exp_ctx, ds_cands)
                    baseline_review = reviewer.run_baseline_review(paper_data["paper"]["title"], new_exp_ctx, bl_cands)
                    
                    # Write Edges
                    def dedupe(insights):
                        seen, out = set(), []
                        for ins in insights:
                            if ins.target_paper_title not in seen:
                                seen.add(ins.target_paper_title)
                                out.append(ins)
                        return out

                    new_title = paper_data["paper"]["title"]
                    for ins in dedupe(problem_review.insights):
                        if ins.is_match:
                            db.write_problem_similarity_edge(new_title, ins.target_paper_title, ins.shared_core_issue, ins.approach_contrast)
                            st.write(f"🔗 Added similarity edge to: *{ins.target_paper_title}*")
                    
                    for ins in dedupe(benchmark_review.insights):
                        if ins.is_match:
                            db.write_benchmark_edge(new_title, ins.target_paper_title, ins.shared_datasets, ins.micro_comparison_report)
                            st.write(f"📊 Added benchmark edge to: *{ins.target_paper_title}*")

                    for ins in dedupe(baseline_review.insights):
                        if ins.is_match:
                            db.write_baseline_edge(new_title, ins.target_paper_title, ins.shared_baselines, ins.who_won)
                            st.write(f"⚖️ Added baseline edge to: *{ins.target_paper_title}*")

                    status.update(label="🎉 Pipeline Complete!", state="complete")
                    st.success(f"Fully processed and linked: {new_title}")
                    
                except Exception as e:
                    status.update(label="❌ Pipeline Failed", state="error")
                    st.error(f"Error during processing: {e}")
                    import traceback
                    st.code(traceback.format_exc())

with tab3:
    st.header("Search & Explore Papers")
    all_papers = get_papers_list(db)
    
    if not all_papers:
        st.info("No papers found in the database. Go to 'Ingest Paper' to add one.")
    else:
        titles = [p["title"] for p in all_papers]
        selected_title = st.selectbox("Select a Paper", titles)
        
        if selected_title:
            details = get_paper_full_details(db, selected_title)
            
            if details:
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.subheader(f"📄 {selected_title}")
                    if details["summary"]:
                        st.markdown(f"**Year:** {details['summary']['year']}")
                        st.markdown(f"**Key Claim:** {details['summary']['claim']}")
                    
                    st.markdown("---")
                    st.subheader("🛠️ Method Overview")
                    if details["method"]:
                        st.markdown(details["method"]["desc"])
                        with st.expander("Show detailed description"):
                            st.markdown(details["method"]["detail"])
                
                with col2:
                    st.subheader("🔗 Knowledge Graph Links")
                    if not details["relations"]:
                        st.write("No cross-paper relationships found yet.")
                    else:
                        for rel in details["relations"]:
                            rtype = rel["rel_type"]
                            target = rel["target"]
                            
                            with st.expander(f"{rtype}: {target}"):
                                if rtype == "TACKLES_SIMILAR_PROBLEM":
                                    st.write(f"**Shared Issue:** {rel['issue']}")
                                    st.write(f"**Contrast:** {rel['contrast']}")
                                elif rtype == "EVALUATED_ON_SAME_BENCHMARK":
                                    st.write(f"**Datasets:** {rel['datasets']}")
                                    st.write(f"**Report:** {rel['report']}")
                                elif rtype == "HAS_COMMON_BASELINE":
                                    st.write(f"**Baselines:** {rel['baselines']}")
                                    st.write(f"**Comparison:** {rel['won']}")

st.markdown("---")
st.caption("Agentic Research Graph Demo | Built with Streamlit, Neo4j & OpenAI")
