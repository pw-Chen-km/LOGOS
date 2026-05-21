import json
import sys
import os
from langchain_openai import OpenAIEmbeddings

from src.core.extraction.docling_parser import PdfExtractor
from src.core.agent.deep_reader import DeepReaderAgent
from src.core.agent.peer_reviewer import PeerReviewAgent
from src.core.graph.neo4j_client import Neo4jClient


def run_phase2_pipeline(api_key: str, arxiv_url: str, output_dir: str,
                        neo4j_uri: str, neo4j_user: str, neo4j_pass: str):

    extractor = PdfExtractor(output_dir)
    reader    = DeepReaderAgent(api_key=api_key)
    reviewer  = PeerReviewAgent(api_key=api_key)
    em        = OpenAIEmbeddings(api_key=api_key, model="text-embedding-3-small")
    db        = Neo4jClient(neo4j_uri, neo4j_user, neo4j_pass)

    try:
        db.setup_database()

        # ── Stage 0: PDF extraction ──────────────────────────────────────────
        print("\n=== STAGE 0: Docling Extraction ===")
        md_path = extractor.extract(arxiv_url)

        # ── Stage 1: Deep reading (LLM extraction) ───────────────────────────
        print("\n=== STAGE 1: Deep Reading ===")
        result    = reader.run(md_path, output_json_path=f"{output_dir}/deep_reading_output.json")
        paper_data = result.model_dump()

        # ── Stage 2: Batch embedding generation ─────────────────────────────
        print("\n=== STAGE 2: Embedding Generation ===")

        sm  = paper_data["summary"]
        rp  = paper_data["research_problem"]
        pl  = paper_data["research_problem"]["previous_limitation"]
        up  = paper_data["research_problem"]["underlying_problem"]
        m   = paper_data["method"]

        ra  = paper_data["method"]["referred_algorithms"]
        exp = paper_data["experiment"]

        # Build ordered text list for a single batch embed call
        core_texts = [
            f"{sm['year']} {sm['short_claim']}",      # 0  summary
            rp["summary"],                              # 1  research_problem
            pl["limitation"],                           # 2  previous_limitation
            up["detail"],                               # 3  underlying_problem
            m["high_level_description"],                # 4  method
            m["detail"]["method_detail"],               # 5  method_detail
            ra["description"],                          # 6  referred_algorithms
            exp["result"],                              # 7  experiment
            f"Design: {exp['analysis']['design_overview']}\nAnalysis: {exp['analysis']['comprehensive_analysis']}" # 8 experiment_analysis

        ]

        kw_names  = [k["name"] for k in paper_data["keywords"]]
        ds_names  = [d["name"] for d in exp["datasets"]]
        cm_names  = [c["name"] for c in exp["compared_methods"]]

        all_texts = core_texts + kw_names + ds_names + cm_names
        print(f"  Vectorizing {len(all_texts)} text blocks...")
        all_embs  = em.embed_documents(all_texts)

        # Map core embeddings
        node_embeddings = {
            "summary":            all_embs[0],
            "research_problem":   all_embs[1],
            "previous_limitation":all_embs[2],
            "underlying_problem": all_embs[3],
            "method":             all_embs[4],
            "method_detail":      all_embs[5],
            "referred_algorithms":all_embs[6],
            "experiment":         all_embs[7],
            "experiment_analysis":all_embs[8],
        }
        idx = 9

        # Attach embeddings to entity lists
        for k in paper_data["keywords"]:
            k["embedding"] = all_embs[idx]; idx += 1
        for d in exp["datasets"]:
            d["embedding"] = all_embs[idx]; idx += 1
        for c in exp["compared_methods"]:
            c["embedding"] = all_embs[idx]; idx += 1

        # ── Stage 3: Graph ingestion ─────────────────────────────────────────
        print("\n=== STAGE 3: Graph Ingestion ===")
        db.ingest_paper_base(paper_data, node_embeddings)

        # ── Stage 4: Setup Fulltext Indexes ─────────────────────────
        print("\n=== STAGE 4: Full-text Index Setup ===")
        db.setup_fulltext_indexes()

        # ── Stage 5A: Problem Similarity Retrieval (Vector) ──────────
        print("\n=== STAGE 5A: Problem Candidate Retrieval ===")
        problem_candidates_raw = db.find_problem_candidates(
            up_embedding=node_embeddings["underlying_problem"],
            pl_embedding=node_embeddings["previous_limitation"],
            exclude_title=paper_data["paper"]["title"],
            top_k=5,
            threshold=0.6,
        )
        print(f"  Found {len(problem_candidates_raw)} problem candidates.")

        # Enrich candidates with their graph context for the LLM
        problem_candidates = []
        for c in problem_candidates_raw:
            ctx = db.get_paper_context_for_review(c["title"])
            problem_candidates.append({"title": c["title"], "score": c["score"], "context": ctx})

        # ── Stage 5B: Experiment Retrieval (Full-Text) ───────────────
        print("\n=== STAGE 5B: Experiment Candidate Retrieval ===")
        new_ds_names  = [d["name"] for d in paper_data["experiment"].get("datasets", [])]
        new_bl_names  = [c["name"] for c in paper_data["experiment"].get("compared_methods", [])]

        dataset_candidates_raw  = db.find_experiment_candidates_by_dataset(new_ds_names, paper_data["paper"]["title"])
        baseline_candidates_raw = db.find_experiment_candidates_by_baseline(new_bl_names, paper_data["paper"]["title"])
        print(f"  Dataset candidates: {len(dataset_candidates_raw)}, Baseline candidates: {len(baseline_candidates_raw)}")

        # Enrich with experiment context
        def enrich_exp(raw_list):
            out = []
            for c in raw_list:
                ctx = db.get_experiment_context_for_review(c["title"])
                out.append({"title": c["title"], "score": c["score"], "context": ctx})
            return out

        dataset_candidates  = enrich_exp(dataset_candidates_raw)
        baseline_candidates = enrich_exp(baseline_candidates_raw)

        # ── Stage 5C: LLM Peer Review ────────────────────────────────
        print("\n=== STAGE 5C: LLM Peer Review ===")
        new_ctx      = db.get_paper_context_for_review(paper_data["paper"]["title"])
        new_exp_ctx  = db.get_experiment_context_for_review(paper_data["paper"]["title"])
        new_title    = paper_data["paper"]["title"]

        problem_review   = reviewer.run_problem_review(new_title, new_ctx, problem_candidates)
        benchmark_review = reviewer.run_benchmark_review(new_title, new_exp_ctx, dataset_candidates)
        baseline_review  = reviewer.run_baseline_review(new_title, new_exp_ctx, baseline_candidates)

        # ── Stage 6: Write Edges Back to Graph ───────────────────────
        print("\n=== STAGE 6: Writing Graph Edges ===")

        def _dedup_insights(insights):
            """Keep only the first (highest-confidence) insight per target paper."""
            seen, out = set(), []
            for ins in insights:
                if ins.target_paper_title not in seen:
                    seen.add(ins.target_paper_title)
                    out.append(ins)
            return out

        for ins in _dedup_insights(problem_review.insights):
            if ins.is_match:
                db.write_problem_similarity_edge(
                    new_title, ins.target_paper_title,
                    ins.shared_core_issue, ins.approach_contrast
                )
                print(f"  [TACKLES_SIMILAR_PROBLEM] {new_title[:40]} <-> {ins.target_paper_title[:40]}")

        for ins in _dedup_insights(benchmark_review.insights):
            if ins.is_match:
                db.write_benchmark_edge(
                    new_title, ins.target_paper_title,
                    ins.shared_datasets, ins.micro_comparison_report
                )
                print(f"  [EVALUATED_ON_SAME_BENCHMARK] {new_title[:40]} <-> {ins.target_paper_title[:40]}")

        for ins in _dedup_insights(baseline_review.insights):
            if ins.is_match:
                db.write_baseline_edge(
                    new_title, ins.target_paper_title,
                    ins.shared_baselines, ins.who_won
                )
                print(f"  [HAS_COMMON_BASELINE] {new_title[:40]} <-> {ins.target_paper_title[:40]}")

        print("\n!!! Phase 2 Pipeline Complete !!!")


    finally:
        db.close()


if __name__ == "__main__":
    API_KEY = os.getenv("OPENAI_API_KEY") # Get from environment variable

    if len(sys.argv) < 3:
        print("Usage: python run_phase2.py <URL> <OUTPUT_DIR>")
        sys.exit(1)

    run_phase2_pipeline(
        api_key=API_KEY,
        arxiv_url=sys.argv[1],
        output_dir=sys.argv[2],
        neo4j_uri="neo4j://127.0.0.1:7687",
        neo4j_user="neo4j",
        neo4j_pass="420420420",
    )
