import os
import json
from datetime import datetime
from src.core.extraction.docling_parser import PdfExtractor
from src.core.agent.deep_reader import DeepReaderAgent
from src.core.graph.neo4j_client import Neo4jClient
from langchain_openai import OpenAIEmbeddings

# Config
PAPER_URL = "https://aclanthology.org/2025.ijcnlp-short.32.pdf"
API_KEY = os.getenv("OPENAI_API_KEY") # Get from environment variable
NEO4J_URI = "neo4j://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "420420420"

def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"test_output_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Extraction
    print("--- Stage 0: Extraction ---")
    extractor = PdfExtractor(output_dir)
    md_path = extractor.extract(PAPER_URL)
    
    # 2. Deep Reading
    print("\n--- Stage 1: Deep Reading ---")
    reader = DeepReaderAgent(api_key=API_KEY, model_name="gpt-4o-mini")
    result = reader.run(md_path, output_json_path=f"{output_dir}/deep_reading.json")
    
    print("\n--- Verification: Comprehensive Analysis ---")
    print(result.experiment.analysis.comprehensive_analysis)
    
    # 3. Embedding & Ingestion
    print("\n--- Stage 2: Embedding & Ingestion ---")
    em = OpenAIEmbeddings(api_key=API_KEY, model="text-embedding-3-small")
    db = Neo4jClient(NEO4J_URI, NEO4J_USER, NEO4J_PASS)
    
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
    
    db.ingest_paper_base(paper_data, node_embeddings)
    print("\n✅ Successfully ingested to Neo4j.")

if __name__ == "__main__":
    main()
