import os
import glob
from datetime import datetime
from src.core.extraction.docling_parser import PdfExtractor
from src.core.agent.deep_reader import DeepReaderAgent
from src.core.agent.peer_reviewer import PeerReviewAgent
from src.core.graph.neo4j_client import Neo4jClient
from langchain_openai import OpenAIEmbeddings

# Config
TESTING_DIR = "/Users/patrick/Desktop/V2_research_agent/testing_paper"
API_KEY = os.getenv("OPENAI_API_KEY") # Get from environment variable
NEO4J_URI = "neo4j://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "420420420"

def process_paper(pdf_path, db, reader, em, reviewer):
    print(f"\n🚀 Processing: {os.path.basename(pdf_path)}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    paper_id = os.path.basename(pdf_path).replace(".pdf", "").replace(" ", "_")[:20]
    output_dir = f"output_{paper_id}_{timestamp}"
    
    # 1. Extraction
    extractor = PdfExtractor(output_dir)
    md_path = extractor.extract(pdf_path)
    
    # 2. Deep Reading
    result = reader.run(md_path, output_json_path=f"{output_dir}/deep_reading.json")
    paper_title = result.paper.title
    
    # 3. Embedding
    paper_data = result.model_dump()
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
    
    # 4. Ingestion
    db.ingest_paper_base(paper_data, node_embeddings)
    db.setup_fulltext_indexes()
    print(f"✅ Ingested base paper: {paper_title}")
    
    # 5. Peer Review
    print("🔭 Running Peer Review...")
    prob_cands_raw = db.find_problem_candidates(
        up_embedding=node_embeddings["underlying_problem"],
        pl_embedding=node_embeddings["previous_limitation"],
        exclude_title=paper_title
    )
    if not prob_cands_raw:
        print("ℹ️ No peer review candidates found (First paper?). skipping...")
        return
        
    prob_cands = [{"title": r["title"], "score": r["score"], "context": db.get_paper_context_for_review(r["title"])} for r in prob_cands_raw]
    ds_cands_raw = db.find_experiment_candidates_by_dataset(ds_names, paper_title)
    ds_cands = [{"title": r["title"], "score": r["score"], "context": db.get_experiment_context_for_review(r["title"])} for r in ds_cands_raw]
    bl_cands_raw = db.find_experiment_candidates_by_baseline(cm_names, paper_title)
    bl_cands = [{"title": r["title"], "score": r["score"], "context": db.get_experiment_context_for_review(r["title"])} for r in bl_cands_raw]
    
    new_ctx = db.get_paper_context_for_review(paper_title)
    new_exp_ctx = db.get_experiment_context_for_review(paper_title)
    
    prob_rev = reviewer.run_problem_review(paper_title, new_ctx, prob_cands)
    ds_rev = reviewer.run_benchmark_review(paper_title, new_exp_ctx, ds_cands)
    bl_rev = reviewer.run_baseline_review(paper_title, new_exp_ctx, bl_cands)
    
    # Write edges
    for ins in prob_rev.insights:
        if ins.is_match: db.write_problem_similarity_edge(paper_title, ins.target_paper_title, ins.shared_core_issue, ins.approach_contrast)
    for ins in ds_rev.insights:
        if ins.is_match: db.write_benchmark_edge(paper_title, ins.target_paper_title, ins.shared_datasets, ins.micro_comparison_report)
    for ins in bl_rev.insights:
        if ins.is_match: db.write_baseline_edge(paper_title, ins.target_paper_title, ins.shared_baselines, ins.who_won)
    
    print(f"✅ Peer review completed for {paper_title}")

def main():
    db = Neo4jClient(NEO4J_URI, NEO4J_USER, NEO4J_PASS)
    reader = DeepReaderAgent(api_key=API_KEY, model_name="gpt-4o-mini")
    reviewer = PeerReviewAgent(api_key=API_KEY, model_name="gpt-4o-mini")
    em = OpenAIEmbeddings(api_key=API_KEY, model="text-embedding-3-small")
    
    pdfs = glob.glob(os.path.join(TESTING_DIR, "*.pdf"))
    print(f"Found {len(pdfs)} papers in {TESTING_DIR}")
    
    for pdf in sorted(pdfs):
        try:
            process_paper(pdf, db, reader, em, reviewer)
        except Exception as e:
            print(f"❌ Error processing {pdf}: {e}")

if __name__ == "__main__":
    main()
