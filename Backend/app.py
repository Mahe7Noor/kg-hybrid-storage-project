"""
FastAPI backend for the Knowledge Graph with Hybrid Storage project.

Wraps the combined search logic (Elasticsearch -> MongoDB -> Neo4j) from
queries/combined_search.py and exposes it as a JSON API for the frontend.

Run with:
    uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from neo4j import GraphDatabase
from elasticsearch import Elasticsearch
import time
import requests

app = FastAPI(title="Knowledge Graph Hybrid Storage API")

# Allow the frontend (served from a different port/file) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────
# Database connections
# ─────────────────────────────────────────
mongo = MongoClient("mongodb://localhost:27017")
db = mongo["literature_review"]

neo4j_driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password123"))

es = Elasticsearch("http://localhost:9200", request_timeout=60)


@app.get("/api/search")
def search(
    q: str = Query(..., description="Search query text"),
    contributor: str | None = Query(None, description="Filter by contributor: 'me' or 'teammate'"),
    top_k: int = Query(8, description="Number of results to return"),
):
    """Combined search across Elasticsearch, MongoDB, and Neo4j."""

    timings = {}

    # Step 1 — Elasticsearch: relevance search
    t0 = time.time()
    es_query: dict = {
        "multi_match": {
            "query": q,
            "fields": ["title^3", "abstract", "concepts^2"],
            "fuzziness": "AUTO",
        }
    }

    if contributor:
        es_query = {
            "bool": {
                "must": [es_query],
                "filter": [{"term": {"contributor": contributor}}],
            }
        }

    es_response = es.search(index="papers", query=es_query, size=top_k)
    timings["elasticsearch_ms"] = round((time.time() - t0) * 1000, 2)

    hits = es_response["hits"]["hits"]
    paper_ids = [h["_source"]["paperId"] for h in hits]
    es_scores = {h["_source"]["paperId"]: round(h["_score"], 3) for h in hits}

    if not paper_ids:
        return {"query": q, "results": [], "timings": timings, "total": 0}

    # Step 2 — MongoDB: full document fetch
    t0 = time.time()
    mongo_papers = list(db.papers.find({"paperId": {"$in": paper_ids}}, {"_id": 0}))
    timings["mongodb_ms"] = round((time.time() - t0) * 1000, 2)

    # Step 3 — Neo4j: relationship traversal
    t0 = time.time()
    with neo4j_driver.session() as session:
        result = session.run(
            """
            MATCH (p:Paper)
            WHERE p.paperId IN $paper_ids
            OPTIONAL MATCH (a:Author)-[:WROTE]->(p)
            OPTIONAL MATCH (p)-[:HAS_TOPIC]->(c:Concept)
            OPTIONAL MATCH (p)-[:REFERENCES]->(ref:Paper)
            RETURN p.paperId AS paperId,
                   collect(DISTINCT a.name) AS authors,
                   collect(DISTINCT c.name) AS topics,
                   collect(DISTINCT ref.title) AS referenced_papers
            """,
            paper_ids=paper_ids,
        )
        graph_data = {
            r["paperId"]: {
                "authors": r["authors"],
                "topics": r["topics"],
                "referenced_papers": [t for t in r["referenced_papers"] if t][:3],
            }
            for r in result
        }
    timings["neo4j_ms"] = round((time.time() - t0) * 1000, 2)

    # Step 4 — merge
    results = []
    for paper in mongo_papers:
        pid = paper["paperId"]
        g = graph_data.get(pid, {})
        results.append({
            "paperId": pid,
            "title": paper.get("title", ""),
            "year": paper.get("year"),
            "abstract": (paper.get("abstract") or "")[:280],
            "citedByCount": paper.get("cited_by_count", 0),
            "relevance": es_scores.get(pid, 0),
            "authors": g.get("authors", []),
            "topics": g.get("topics", []),
            "referencedPapers": g.get("referenced_papers", []),
            "contributor": paper.get("contributor", "unknown"),
        })

    results.sort(key=lambda r: r["relevance"], reverse=True)
    timings["total_ms"] = round(sum(timings.values()), 2)

    return {"query": q, "results": results, "timings": timings, "total": len(results)}


@app.get("/api/topics")
def topics(contributor: str | None = Query(None)):
    """Return distinct topics/concepts, optionally filtered by contributor."""
    match_filter = {"contributor": contributor} if contributor else {}
    pipeline = [
        {"$match": match_filter} if contributor else {"$match": {}},
        {"$unwind": "$concepts"},
        {"$group": {"_id": "$concepts", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 30},
    ]
    rows = list(db.papers.aggregate(pipeline))
    return {"topics": [{"name": r["_id"], "count": r["count"]} for r in rows if r["_id"]]}


class TopicRequest(BaseModel):
    topic: str


def reconstruct_abstract(inverted_index):
    if not inverted_index:
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort(key=lambda x: x[0])
    return " ".join(w for _, w in word_positions)


@app.post("/api/add-topic")
def add_topic(req: TopicRequest):
    """
    Live-fetch papers on a new topic from OpenAlex and load them into all
    three databases immediately. This is the 'extend the collection from
    the frontend' feature — kept deliberately simple and synchronous so
    failures are visible rather than silent.
    """
    topic = req.topic.strip()
    if not topic:
        return {"added": 0, "error": "Empty topic"}

    url = "https://api.openalex.org/works"
    params = {
        "search": topic,
        "per-page": 10,
        "filter": "has_abstract:true",
        "select": "id,title,abstract_inverted_index,publication_year,authorships,cited_by_count,referenced_works,concepts",
        "mailto": "your-email@example.com",
    }

    try:
        response = requests.get(url, params=params, timeout=20)
        response.raise_for_status()
        works = response.json().get("results", [])
    except Exception as e:
        return {"added": 0, "error": f"OpenAlex request failed: {e}"}

    existing_ids = {p["paperId"] for p in db.papers.find({}, {"paperId": 1})}
    added = 0

    with neo4j_driver.session() as session:
        for work in works:
            paper_id = (work.get("id") or "").replace("https://openalex.org/", "")
            if not paper_id or paper_id in existing_ids or not work.get("title"):
                continue

            authors = [
                {
                    "authorId": (a.get("author", {}).get("id") or "").replace("https://openalex.org/", ""),
                    "name": a.get("author", {}).get("display_name", ""),
                }
                for a in (work.get("authorships") or [])
                if a.get("author", {}).get("display_name")
            ]
            concepts = [c.get("display_name", "") for c in (work.get("concepts") or []) if c.get("score", 0) > 0.3]
            abstract = reconstruct_abstract(work.get("abstract_inverted_index"))

            # MongoDB
            db.papers.insert_one({
                "paperId": paper_id,
                "title": work.get("title", ""),
                "abstract": abstract,
                "year": work.get("publication_year"),
                "authors": authors,
                "cited_by_count": work.get("cited_by_count", 0),
                "concepts": concepts,
                "references": [],
                "contributor": "added-live",
            })

            # Elasticsearch
            es.index(index="papers", id=paper_id, document={
                "paperId": paper_id,
                "title": work.get("title", ""),
                "abstract": abstract,
                "year": work.get("publication_year"),
                "concepts": concepts,
                "cited_by_count": work.get("cited_by_count", 0),
                "contributor": "added-live",
            })

            # Neo4j
            session.run(
                "MERGE (p:Paper {paperId: $pid}) SET p.title = $title, p.year = $year",
                pid=paper_id, title=work.get("title", ""), year=work.get("publication_year"),
            )
            for author in authors:
                if not author["name"]:
                    continue
                session.run(
                    """
                    MERGE (a:Author {authorId: $aid}) SET a.name = $name
                    MERGE (p:Paper {paperId: $pid})
                    MERGE (a)-[:WROTE]->(p)
                    """,
                    aid=author["authorId"], name=author["name"], pid=paper_id,
                )
            for concept in concepts:
                session.run(
                    """
                    MERGE (c:Concept {name: $name})
                    MERGE (p:Paper {paperId: $pid})
                    MERGE (p)-[:HAS_TOPIC]->(c)
                    """,
                    name=concept, pid=paper_id,
                )

            existing_ids.add(paper_id)
            added += 1

    es.indices.refresh(index="papers")
    return {"added": added, "topic": topic}


@app.get("/api/stats")
def stats():
    """Quick overview counts for the dashboard header."""
    total_papers = db.papers.count_documents({})
    mine = db.papers.count_documents({"contributor": "me"})
    teammate = db.papers.count_documents({"contributor": "teammate"})

    with neo4j_driver.session() as session:
        graph_counts = session.run(
            """
            MATCH (p:Paper) WITH count(p) AS papers
            MATCH (a:Author) WITH papers, count(a) AS authors
            MATCH (c:Concept) WITH papers, authors, count(c) AS concepts
            RETURN papers, authors, concepts
            """
        ).single()

    return {
        "totalPapers": total_papers,
        "mine": mine,
        "teammate": teammate,
        "authors": graph_counts["authors"] if graph_counts else 0,
        "concepts": graph_counts["concepts"] if graph_counts else 0,
    }