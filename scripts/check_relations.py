
from neo4j import GraphDatabase

uri = "neo4j://127.0.0.1:7687"
user = "neo4j"
password = "420420420"

driver = GraphDatabase.driver(uri, auth=(user, password))

def count_relations():
    rel_types = ["IMPROVES_UPON", "SOLVES_SAME_PROBLEM", "CONCEPTUALLY_SIMILAR_TO"]
    counts = {}
    
    with driver.session() as session:
        for rel in rel_types:
            query = f"MATCH ()-[r:{rel}]->() RETURN count(r) as count"
            result = session.run(query)
            counts[rel] = result.single()["count"]
            
        # Also check all others just in case
        query = "MATCH ()-[r]->() WHERE NOT type(r) IN ['TACKLES', 'PROPOSES_OR_USES', 'EVALUATES_ON', 'COMPARES_AGAINST', 'TAGGED_WITH'] RETURN type(r) as type, count(r) as count"
        result = session.run(query)
        for record in result:
            if record["type"] not in counts:
                counts[record["type"]] = record["count"]
                
    return counts

if __name__ == "__main__":
    try:
        results = count_relations()
        print("Relationship counts:")
        for rel, count in results.items():
            print(f"- {rel}: {count}")
    finally:
        driver.close()
