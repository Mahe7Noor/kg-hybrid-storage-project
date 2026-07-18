from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password123"
MINIMUM_SCORE = 2.0

QUERY = """
MATCH (p1:Paper)
WHERE p1.title IS NOT NULL
MATCH (p2:Paper)
WHERE p2.title IS NOT NULL AND p1.paperId < p2.paperId

OPTIONAL MATCH (p1)-[:HAS_TOPIC]->(c:Concept)<-[:HAS_TOPIC]-(p2)
WITH p1, p2,
     [x IN collect(DISTINCT c.name) WHERE x IS NOT NULL] AS sharedConcepts

OPTIONAL MATCH (a:Author)-[:WROTE]->(p1)
OPTIONAL MATCH (a)-[:WROTE]->(p2)
WITH p1, p2, sharedConcepts,
     [x IN collect(DISTINCT a.name) WHERE x IS NOT NULL] AS sharedAuthors

OPTIONAL MATCH (p1)-[r1:REFERENCES]->(p2)
OPTIONAL MATCH (p2)-[r2:REFERENCES]->(p1)
WITH p1, p2, sharedConcepts, sharedAuthors,
     CASE WHEN r1 IS NOT NULL OR r2 IS NOT NULL THEN true ELSE false END AS directReference

WITH p1, p2, sharedConcepts, sharedAuthors, directReference,
     2.0 * size(sharedConcepts)
     + 3.0 * size(sharedAuthors)
     + CASE WHEN directReference THEN 4.0 ELSE 0.0 END AS score
WHERE score >= $minimumScore

MERGE (p1)-[rel:RELATED_TO]-(p2)
SET rel.score = score,
    rel.sharedConcepts = sharedConcepts,
    rel.sharedAuthors = sharedAuthors,
    rel.directReference = directReference,
    rel.updatedAt = datetime()
RETURN count(rel) AS relationships
"""


def main():
    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
    )
    try:
        with driver.session() as session:
            session.run("MATCH ()-[r:RELATED_TO]-() DELETE r")
            result = session.run(QUERY, minimumScore=MINIMUM_SCORE).single()
            print(f"RELATED_TO relationships created: {result['relationships']}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
