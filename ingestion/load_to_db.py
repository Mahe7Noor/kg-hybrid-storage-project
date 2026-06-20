from pymongo import MongoClient
from neo4j import GraphDatabase
from elasticsearch import Elasticsearch
import json
import os

# Load papers
print("Loading papers from file...")
with open("data/your_papers.json", encoding="utf-8") as f:
    papers = json.load(f)
print(f"Found {len(papers)} papers to load")

# Connect to all three databases
mongo = MongoClient("mongodb://localhost:27017")
db = mongo["literature_review"]

neo4j = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password123"))

es = Elasticsearch(
    "http://localhost:9200",
    request_timeout=60
)

# ─────────────────────────────────────────
# MONGODB — store full paper documents
# ─────────────────────────────────────────
print("\n--- Loading into MongoDB ---")

db.papers.drop()  # fresh start each time

mongo_docs = []
for paper in papers:
    mongo_docs.append({
        "paperId":       paper["paperId"],
        "title":         paper.get("title", ""),
        "abstract":      paper.get("abstract", ""),
        "year":          paper.get("year"),
        "authors":       paper.get("authors", []),
        "cited_by_count": paper.get("cited_by_count", 0),
        "concepts":      paper.get("concepts", []),
        "references":    paper.get("references", [])
    })

db.papers.insert_many(mongo_docs)
print(f"✓ MongoDB: inserted {db.papers.count_documents({})} papers")

# ─────────────────────────────────────────
# ELASTICSEARCH — index for text search
# ─────────────────────────────────────────
print("\n--- Loading into Elasticsearch ---")

# Delete and recreate index for fresh start
if es.indices.exists(index="papers"):
    es.indices.delete(index="papers")

es.indices.create(index="papers", body={
    "mappings": {
        "properties": {
            "paperId":  {"type": "keyword"},
            "title":    {"type": "text"},
            "abstract": {"type": "text"},
            "year":     {"type": "integer"},
            "concepts": {"type": "keyword"},
            "cited_by_count": {"type": "integer"}
        }
    }
})

for paper in papers:
    es.index(index="papers", id=paper["paperId"], document={
        "paperId":        paper["paperId"],
        "title":          paper.get("title", ""),
        "abstract":       paper.get("abstract", ""),
        "year":           paper.get("year"),
        "concepts":       paper.get("concepts", []),
        "cited_by_count": paper.get("cited_by_count", 0)
    })

es.indices.refresh(index="papers")
count = es.count(index="papers")["count"]
print(f"✓ Elasticsearch: indexed {count} papers")

# ─────────────────────────────────────────
# NEO4J — build the knowledge graph
# ─────────────────────────────────────────
print("\n--- Loading into Neo4j ---")

with neo4j.session() as session:
    # Clear existing data
    session.run("MATCH (n) DETACH DELETE n")
    
    # Create paper nodes
    for paper in papers:
        session.run("""
            MERGE (p:Paper {paperId: $paperId})
            SET p.title = $title,
                p.year = $year,
                p.cited_by_count = $cited_by_count
        """,
            paperId=paper["paperId"],
            title=paper.get("title", ""),
            year=paper.get("year"),
            cited_by_count=paper.get("cited_by_count", 0)
        )
    
    # Create author nodes and WROTE relationships
    for paper in papers:
        for author in paper.get("authors", []):
            if not author.get("name"):
                continue
            session.run("""
                MERGE (a:Author {authorId: $authorId})
                SET a.name = $name
                MERGE (p:Paper {paperId: $paperId})
                MERGE (a)-[:WROTE]->(p)
            """,
                authorId=author.get("authorId", ""),
                name=author.get("name", ""),
                paperId=paper["paperId"]
            )
    
    # Create concept nodes and HAS_TOPIC relationships
    for paper in papers:
        for concept in paper.get("concepts", []):
            if not concept:
                continue
            session.run("""
                MERGE (c:Concept {name: $name})
                MERGE (p:Paper {paperId: $paperId})
                MERGE (p)-[:HAS_TOPIC]->(c)
            """,
                name=concept,
                paperId=paper["paperId"]
            )
    
    # Create REFERENCES relationships between papers
    paper_ids = {p["paperId"] for p in papers}
    for paper in papers:
        for ref in paper.get("references", []):
            ref_id = ref.get("paperId", "")
            if ref_id and ref_id in paper_ids:
                session.run("""
                    MERGE (p1:Paper {paperId: $from_id})
                    MERGE (p2:Paper {paperId: $to_id})
                    MERGE (p1)-[:REFERENCES]->(p2)
                """,
                    from_id=paper["paperId"],
                    to_id=ref_id
                )
    
    # Count what we created
    result = session.run("""
        MATCH (p:Paper) WITH count(p) as papers
        MATCH (a:Author) WITH papers, count(a) as authors
        MATCH (c:Concept) WITH papers, authors, count(c) as concepts
        RETURN papers, authors, concepts
    """)
    row = result.single()
    print(f"✓ Neo4j: {row['papers']} papers, {row['authors']} authors, {row['concepts']} concepts")

print("\n" + "=" * 50)
print("All three databases loaded successfully!")
print("Open http://localhost:7474 to see your knowledge graph visually")