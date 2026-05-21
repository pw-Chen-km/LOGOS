import os
from dotenv import load_dotenv
from neo4j import GraphDatabase
from langchain_openai import OpenAIEmbeddings

load_dotenv()

def backfill_entity_embeddings():
    api_key = os.getenv("OPENAI_API_KEY") # Get from environment variable
    if not api_key:
        print("OPENAI_API_KEY not found in environment.")
        return

    neo4j_uri  = os.getenv("NEO4J_URI",      "neo4j://127.0.0.1:7687")
    neo4j_user = os.getenv("NEO4J_USER",     "neo4j")
    neo4j_pass = os.getenv("NEO4J_PASSWORD", "420420420")

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
    em = OpenAIEmbeddings(api_key=api_key, model="text-embedding-3-small")

    # Shared entity nodes (MERGE'd across papers) that carry .name and need embeddings
    name_labels = ["Dataset", "Keyword", "ComparedMethod"]

    total_updated = 0
    with driver.session() as session:
        for label in name_labels:
            cypher_find = f"MATCH (n:{label}) WHERE n.embedding IS NULL RETURN n.name AS name"
            res   = session.run(cypher_find)
            names = [r["name"] for r in res]

            if not names:
                print(f"[{label}] No nodes need embedding.")
                continue

            print(f"[{label}] Vectorizing {len(names)} nodes...")
            embeddings = em.embed_documents(names)

            cypher_update = f"""
            UNWIND $updates AS update
            MATCH (n:{label} {{name: update.name}})
            SET n.embedding = update.embedding
            """
            updates = [{"name": n, "embedding": e} for n, e in zip(names, embeddings)]
            session.run(cypher_update, updates=updates)

            total_updated += len(names)
            print(f"[{label}] Successfully updated {len(names)} nodes.")

    driver.close()
    print(f"Backfill complete! Total nodes vectorized: {total_updated}")

if __name__ == "__main__":
    backfill_entity_embeddings()
