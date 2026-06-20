from pymongo import MongoClient
from neo4j import GraphDatabase
from elasticsearch import Elasticsearch
import json
import time

# ─────────────────────────────────────────
# Connect to all three databases
# ─────────────────────────────────────────
mongo = MongoClient("mongodb://localhost:27017")
db = mongo["literature_review"]

neo4j = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password123"))

es = Elasticsearch(
    "http://localhost:9200",
    request_timeout=60
)

def combined_search(query_text, top_k=5):
    """
    Combined search across all three databases.
    
    Step 1: Elasticsearch finds most relevant papers by keyword
    Step 2: MongoDB fetches full details for those papers
    Step 3: Neo4j finds related authors and connected papers
    Step 4: Merge everything into one result
    """
    
    print(f"\n{'='*60}")
    print(f"Searching for: '{query_text}'")
    print(f"{'='*60}")
    
    results = []
    
    # ─────────────────────────────────────────
    # STEP 1: Elasticsearch — keyword search
    # ─────────────────────────────────────────
    print("\n[Step 1] Elasticsearch — finding relevant papers...")
    es_start = time.time()
    
    es_response = es.search(index="papers", body={
        "query": {
            "multi_match": {
                "query": query_text,
                "fields": ["title^3", "abstract", "concepts^2"],
                "fuzziness": "AUTO"
            }
        },
        "size": top_k
    })
    
    es_time = round((time.time() - es_start) * 1000, 2)
    
    hits = es_response["hits"]["hits"]
    paper_ids = [hit["_source"]["paperId"] for hit in hits]
    es_scores = {hit["_source"]["paperId"]: hit["_score"] for hit in hits}
    
    print(f"  Found {len(hits)} papers in {es_time}ms")
    
    if not paper_ids:
        print("  No results found in Elasticsearch")
        return []
    
    # ─────────────────────────────────────────
    # STEP 2: MongoDB — get full paper details
    # ─────────────────────────────────────────
    print("\n[Step 2] MongoDB — fetching full paper details...")
    mongo_start = time.time()
    
    mongo_papers = list(db.papers.find(
        {"paperId": {"$in": paper_ids}},
        {"_id": 0}  # exclude MongoDB internal ID
    ))
    
    mongo_time = round((time.time() - mongo_start) * 1000, 2)
    print(f"  Fetched {len(mongo_papers)} papers in {mongo_time}ms")
    
    # ─────────────────────────────────────────
    # STEP 3: Neo4j — find graph relationships
    # ─────────────────────────────────────────
    print("\n[Step 3] Neo4j — traversing knowledge graph...")
    neo4j_start = time.time()
    
    with neo4j.session() as session:
        neo4j_result = session.run("""
            MATCH (p:Paper)
            WHERE p.paperId IN $paper_ids
            
            OPTIONAL MATCH (a:Author)-[:WROTE]->(p)
            OPTIONAL MATCH (p)-[:HAS_TOPIC]->(c:Concept)
            OPTIONAL MATCH (p)-[:REFERENCES]->(ref:Paper)
            
            RETURN 
                p.paperId AS paperId,
                collect(DISTINCT a.name) AS authors,
                collect(DISTINCT c.name) AS topics,
                collect(DISTINCT ref.title) AS referenced_papers
        """, paper_ids=paper_ids)
        
        neo4j_data = {}
        for record in neo4j_result:
            neo4j_data[record["paperId"]] = {
                "authors":           record["authors"],
                "topics":            record["topics"],
                "referenced_papers": record["referenced_papers"][:3]
            }
    
    neo4j_time = round((time.time() - neo4j_start) * 1000, 2)
    print(f"  Graph traversal completed in {neo4j_time}ms")
    
    # ─────────────────────────────────────────
    # STEP 4: Merge all results
    # ─────────────────────────────────────────
    print("\n[Step 4] Merging results from all three databases...")
    
    for paper in mongo_papers:
        pid = paper["paperId"]
        graph_data = neo4j_data.get(pid, {})
        
        merged = {
            "title":             paper.get("title", ""),
            "year":              paper.get("year", ""),
            "abstract":          paper.get("abstract", "")[:200] + "...",
            "cited_by_count":    paper.get("cited_by_count", 0),
            "relevance_score":   round(es_scores.get(pid, 0), 3),
            "authors":           graph_data.get("authors", []),
            "topics":            graph_data.get("topics", []),
            "referenced_papers": graph_data.get("referenced_papers", [])
        }
        results.append(merged)
    
    # Sort by relevance score
    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    
    # ─────────────────────────────────────────
    # STEP 5: Print results clearly
    # ─────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"TOP {len(results)} RESULTS FOR: '{query_text}'")
    print(f"{'='*60}")
    
    for i, paper in enumerate(results, 1):
        print(f"\n#{i} {paper['title']}")
        print(f"    Year:          {paper['year']}")
        print(f"    Relevance:     {paper['relevance_score']}")
        print(f"    Cited by:      {paper['cited_by_count']} papers")
        print(f"    Authors:       {', '.join(paper['authors'][:3])}")
        print(f"    Topics:        {', '.join(paper['topics'][:4])}")
        print(f"    Abstract:      {paper['abstract']}")
        if paper['referenced_papers']:
            print(f"    Also references: {paper['referenced_papers'][0]}")
    
    # ─────────────────────────────────────────
    # STEP 6: Print performance summary
    # ─────────────────────────────────────────
    print(f"\n{'='*60}")
    print("PERFORMANCE SUMMARY")
    print(f"{'='*60}")
    print(f"  Elasticsearch search:  {es_time}ms")
    print(f"  MongoDB fetch:         {mongo_time}ms")
    print(f"  Neo4j traversal:       {neo4j_time}ms")
    print(f"  Total query time:      {round(es_time + mongo_time + neo4j_time, 2)}ms")
    
    return results


# ─────────────────────────────────────────
# Test with different search queries
# ─────────────────────────────────────────
if __name__ == "__main__":
    
    # Test 1 — your main topic
    combined_search("graph mining")
    
    # Test 2 — another topic
    combined_search("transformer attention mechanism")
    
    # Test 3 — fuzzy search (intentional typo to show fuzziness)
    combined_search("assocation rules")