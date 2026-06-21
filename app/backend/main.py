# FastAPI backend for the Knowledge Graph with Hybrid Storage project.
#
# This file connects:
# 1. Frontend: app/frontend/index.html
# 2. Elasticsearch: fast keyword and relevance search
# 3. MongoDB: full paper documents
# 4. Neo4j: paper-author-topic-reference graph relationships
#
# Run from the project root folder:
#     uvicorn app.backend.main:app --reload
#
# Then open:
#     Frontend: http://localhost:8000/
#     API docs: http://localhost:8000/docs

from pathlib import Path
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from neo4j import GraphDatabase
from elasticsearch import Elasticsearch
import time
import datetime
import requests as req
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI(title="LitGraph API")
# Frontend serving

# This backend file should be located at:
#     app/backend/main.py
#
# __file__ means the current file path.
# Path(__file__).resolve() converts it to the full absolute path.
# parents[0] = app/backend
# parents[1] = app
#
# Therefore BASE_DIR becomes the app folder.
BASE_DIR = Path(__file__).resolve().parents[1]

# FRONTEND_DIR becomes:
#     app/frontend
FRONTEND_DIR = BASE_DIR / "frontend"

# This serves frontend static files such as CSS, JS, and images.
# Example:
#     app/frontend/style.css
# can be reached as:
#     http://localhost:8000/static/style.css

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# This route serves the frontend homepage.
# When the browser opens http://localhost:8000/,
# FastAPI returns app/frontend/index.html.
@app.get("/")
def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

mongo  = MongoClient("mongodb://localhost:27017")
db     = mongo["literature_review"]
neo4j  = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password123"))
es     = Elasticsearch("http://localhost:9200", request_timeout=60,
                       retry_on_timeout=True, max_retries=3)

# Canonical contributor values stored in MongoDB.
# Frontend sends one of: "all", "Alekhya", "Mahe Noor", "shared"
# "shared" maps to the DB value "both".
CONTRIB_MAP = {
    "Alekhya":  "Alekhya",
    "Mahe Noor": "Mahe Noor",
    "shared":   "both",
}


def contributor_filter(contributor: str) -> dict:
    """Build a MongoDB filter fragment for a given contributor query param."""
    if contributor in CONTRIB_MAP:
        return {"contributor": CONTRIB_MAP[contributor]}
    return {}  # "all" or unknown -> no filter


# ── /api/stats ─────────────────────────────────────────────────────
@app.get("/api/stats")
def get_stats():
    total    = db.papers.count_documents({})
    mine     = db.papers.count_documents({"contributor": "Alekhya"})
    teammate = db.papers.count_documents({"contributor": "Mahe Noor"})
    shared   = db.papers.count_documents({"contributor": "both"})

    with neo4j.session() as session:
        authors = session.run("MATCH (a:Author) RETURN count(a) AS count").single()["count"]

    return {"total": total, "mine": mine, "teammate": teammate,
            "shared": shared, "authors": authors}


# ── /api/topics ────────────────────────────────────────────────────
@app.get("/api/topics")
def get_topics(contributor: str = "all"):
    match_filter = {
        "search_topic": {"$exists": True, "$nin": [None, "", "MISSING"]}
    }
    match_filter.update(contributor_filter(contributor))

    pipeline = [
        {"$match": match_filter},
        {"$group": {"_id": "$search_topic", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 200}
    ]
    results = list(db.papers.aggregate(pipeline))
    return [{"topic": r["_id"], "count": r["count"]} for r in results]


# ── /api/topics/{topic} (DELETE) ──────────────────────────────────
@app.delete("/api/topics/{topic}")
def delete_topic(topic: str):
    """Delete every paper tagged with this search_topic from Mongo, ES, and Neo4j."""
    papers = list(db.papers.find({"search_topic": topic}, {"paperId": 1}))
    paper_ids = [p["paperId"] for p in papers]

    if not paper_ids:
        return {"error": f"No papers found for topic '{topic}'"}

    # MongoDB
    mongo_result = db.papers.delete_many({"search_topic": topic})

    # Also remove any favorites pointing at these papers
    db.favorites.delete_many({"paperId": {"$in": paper_ids}})

    # Elasticsearch
    es_deleted = 0
    for pid in paper_ids:
        try:
            es.delete(index="papers", id=pid, ignore=[404])
            es_deleted += 1
        except Exception:
            pass
    es.indices.refresh(index="papers")

    # Neo4j — remove the Topic node's relationship and delete Paper nodes
    # that aren't referenced by any other topic/relationship of value.
    with neo4j.session() as session:
        session.run("""
            MATCH (t:Topic {name: $topic})
            DETACH DELETE t
        """, topic=topic)

        session.run("""
            UNWIND $ids AS pid
            MATCH (p:Paper {paperId: pid})
            DETACH DELETE p
        """, ids=paper_ids)

    return {
        "deleted_papers": mongo_result.deleted_count,
        "es_deleted": es_deleted,
        "topic": topic
    }


# ── /api/search ────────────────────────────────────────────────────
@app.get("/api/search")
def search(
    q:           str = Query(default="", min_length=0),
    contributor: str = "all",
    topic:       str = None,
    top_k:       int = 20
):
    timings = {}

    if not q.strip() and topic:
        t0           = time.time()
        mongo_filter = {"search_topic": topic}
        mongo_filter.update(contributor_filter(contributor))

        mongo_papers = list(db.papers.find(mongo_filter, {"_id": 0}))
        timings["mongodb_ms"] = round((time.time() - t0) * 1000, 1)

        if not mongo_papers:
            return {"results": [], "timings": timings, "total": 0}

        filtered_ids = [p["paperId"] for p in mongo_papers]

        t0 = time.time()
        with neo4j.session() as session:
            result = session.run("""
                MATCH (p:Paper) WHERE p.paperId IN $ids
                OPTIONAL MATCH (a:Author)-[:WROTE]->(p)
                OPTIONAL MATCH (p)-[:HAS_TOPIC]->(c:Concept)
                RETURN
                    p.paperId                       AS paperId,
                    collect(DISTINCT a.name)[0..4]  AS authors,
                    collect(DISTINCT c.name)[0..5]  AS graph_topics
            """, ids=filtered_ids)
            graph_data = {r["paperId"]: dict(r) for r in result}
        timings["neo4j_ms"] = round((time.time() - t0) * 1000, 1)
        timings["total_ms"] = round(sum(timings.values()), 1)

        fav_map = _favorites_for(filtered_ids)

        results = []
        for paper in mongo_papers:
            pid = paper["paperId"]
            g   = graph_data.get(pid, {})
            results.append({
                "paperId":         pid,
                "title":           paper.get("title", ""),
                "year":            paper.get("year"),
                "abstract":        (paper.get("abstract", "")[:280] + "…") if paper.get("abstract") else "",
                "cited_by_count":  paper.get("cited_by_count", 0),
                "relevance_score": 0,
                "authors":         g.get("authors", []),
                "graph_topics":    g.get("graph_topics", []),
                "search_topic":    paper.get("search_topic", ""),
                "contributor":     paper.get("contributor", "unknown"),
                "favorited_by":    fav_map.get(pid, []),
            })

        results.sort(key=lambda x: x["cited_by_count"], reverse=True)
        return {"results": results[:top_k], "timings": timings, "total": len(results)}

    if not q.strip():
        return {"results": [], "timings": {}, "total": 0}

    t0 = time.time()
    es_response = es.search(index="papers", body={
        "query": {
            "multi_match": {
                "query":     q,
                "fields":    ["title^3", "abstract", "search_topic^2"],
                "fuzziness": "AUTO"
            }
        },
        "size": top_k * 4
    })

    hits      = es_response["hits"]["hits"]
    paper_ids = [h["_source"]["paperId"] for h in hits]
    es_scores = {h["_source"]["paperId"]: round(h["_score"], 3) for h in hits}
    timings["elasticsearch_ms"] = round((time.time() - t0) * 1000, 1)

    if not paper_ids:
        return {"results": [], "timings": timings, "total": 0}

    t0           = time.time()
    mongo_filter = {"paperId": {"$in": paper_ids}}
    mongo_filter.update(contributor_filter(contributor))

    if topic:
        mongo_filter["search_topic"] = topic

    mongo_papers = list(db.papers.find(mongo_filter, {"_id": 0}))
    timings["mongodb_ms"] = round((time.time() - t0) * 1000, 1)

    if not mongo_papers:
        return {"results": [], "timings": timings, "total": 0}

    filtered_ids = [p["paperId"] for p in mongo_papers]

    t0 = time.time()
    with neo4j.session() as session:
        result = session.run("""
            MATCH (p:Paper) WHERE p.paperId IN $ids
            OPTIONAL MATCH (a:Author)-[:WROTE]->(p)
            OPTIONAL MATCH (p)-[:HAS_TOPIC]->(c:Concept)
            OPTIONAL MATCH (p)-[:REFERENCES]->(ref:Paper)
            RETURN
                p.paperId                         AS paperId,
                collect(DISTINCT a.name)[0..4]    AS authors,
                collect(DISTINCT c.name)[0..5]    AS graph_topics,
                collect(DISTINCT ref.title)[0..2] AS references
        """, ids=filtered_ids)
        graph_data = {r["paperId"]: dict(r) for r in result}

    timings["neo4j_ms"] = round((time.time() - t0) * 1000, 1)
    timings["total_ms"] = round(sum(timings.values()), 1)

    fav_map = _favorites_for(filtered_ids)

    results = []
    for paper in mongo_papers:
        pid = paper["paperId"]
        g   = graph_data.get(pid, {})
        results.append({
            "paperId":         pid,
            "title":           paper.get("title", ""),
            "year":            paper.get("year"),
            "abstract":        (paper.get("abstract", "")[:280] + "…") if paper.get("abstract") else "",
            "cited_by_count":  paper.get("cited_by_count", 0),
            "relevance_score": es_scores.get(pid, 0),
            "authors":         g.get("authors", []),
            "graph_topics":    g.get("graph_topics", []),
            "references":      g.get("references", []),
            "search_topic":    paper.get("search_topic", ""),
            "contributor":     paper.get("contributor", "unknown"),
            "favorited_by":    fav_map.get(pid, []),
        })

    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return {"results": results[:top_k], "timings": timings, "total": len(results)}


# ── /api/add-topic ─────────────────────────────────────────────────
@app.post("/api/add-topic")
def add_topic(payload: dict):
    topic = payload.get("topic", "").strip()
    contributor = payload.get("contributor", "Alekhya").strip() or "Alekhya"
    if not topic:
        return {"error": "No topic provided"}

    works = []

    params = {
        "filter": f"title.search:{topic},has_abstract:true",
        "per-page": 10,
        "sort": "cited_by_count:desc",
        "select": "id,title,abstract_inverted_index,publication_year,authorships,cited_by_count,referenced_works,concepts"
    }
    r = req.get("https://api.openalex.org/works", params=params, timeout=20)
    if r.status_code == 200:
        works = r.json().get("results", [])

    if len(works) < 5:
        params2 = dict(params)
        params2["filter"] = f"abstract.search:{topic},has_abstract:true"
        r2 = req.get("https://api.openalex.org/works", params=params2, timeout=20)
        if r2.status_code == 200:
            existing = {w["id"] for w in works}
            works += [w for w in r2.json().get("results", []) if w["id"] not in existing]

    if len(works) < 3:
        params3 = dict(params)
        params3.pop("filter")
        params3["search"] = topic
        r3 = req.get("https://api.openalex.org/works", params=params3, timeout=20)
        if r3.status_code == 200:
            existing = {w["id"] for w in works}
            works += [w for w in r3.json().get("results", []) if w["id"] not in existing]

    if not works:
        return {"error": f"No papers found for '{topic}' — try different keywords"}

    added = 0
    for work in works:
        paper_id = (work.get("id") or "").replace("https://openalex.org/", "")
        if not paper_id or db.papers.find_one({"paperId": paper_id}):
            continue

        inv      = work.get("abstract_inverted_index") or {}
        word_pos = [(pos, w) for w, positions in inv.items() for pos in positions]
        abstract = " ".join(w for _, w in sorted(word_pos))

        authors = []
        for auth in (work.get("authorships") or []):
            a = auth.get("author") or {}
            if a.get("display_name"):
                authors.append({
                    "authorId": (a.get("id") or "").replace("https://openalex.org/", ""),
                    "name":     a["display_name"]
                })

        concepts = [
            c["display_name"] for c in (work.get("concepts") or [])
            if c.get("score", 0) > 0.3
        ]

        paper = {
            "paperId":        paper_id,
            "title":          work.get("title", ""),
            "abstract":       abstract,
            "year":           work.get("publication_year"),
            "authors":        authors,
            "citations":      [],
            "cited_by_count": work.get("cited_by_count", 0),
            "references":     [],
            "concepts":       concepts,
            "search_topic":   topic,
            "contributor":    contributor
        }

        db.papers.insert_one({k: v for k, v in paper.items()})

        es.index(index="papers", id=paper_id, document={
            "paperId":        paper_id,
            "title":          paper["title"],
            "abstract":       paper["abstract"],
            "year":           paper["year"],
            "search_topic":   topic,
            "contributor":    contributor,
            "cited_by_count": paper["cited_by_count"]
        })

        with neo4j.session() as session:
            session.run("""
                MERGE (p:Paper {paperId: $pid})
                SET p.title=$title, p.year=$year
            """, pid=paper_id, title=paper["title"], year=paper["year"])

            for author in authors:
                session.run("""
                    MERGE (a:Author {authorId: $aid}) SET a.name=$name
                    MERGE (p:Paper {paperId: $pid})
                    MERGE (a)-[:WROTE]->(p)
                """, aid=author["authorId"], name=author["name"], pid=paper_id)

            session.run("""
                MERGE (t:Topic {name: $name})
                MERGE (p:Paper {paperId: $pid})
                MERGE (p)-[:HAS_TOPIC]->(t)
            """, name=topic, pid=paper_id)

        added += 1

    es.indices.refresh(index="papers")
    return {"added": added, "topic": topic}


# ── Favorites (mark for future reference) ───────────────────────────
# Stored in a separate Mongo collection `favorites`:
#   { paperId, markedBy, markedAt, title, year, search_topic }
# One document per (paperId, markedBy) pair — same person can't double-favorite.

def _favorites_for(paper_ids):
    """Return {paperId: [list of names who favorited it]} for the given ids."""
    if not paper_ids:
        return {}
    docs = db.favorites.find({"paperId": {"$in": paper_ids}}, {"_id": 0, "paperId": 1, "markedBy": 1})
    out = {}
    for d in docs:
        out.setdefault(d["paperId"], []).append(d["markedBy"])
    return out


@app.post("/api/favorites")
def add_favorite(payload: dict):
    paper_id  = payload.get("paperId", "").strip()
    marked_by = payload.get("markedBy", "").strip()

    if not paper_id or not marked_by:
        return {"error": "paperId and markedBy are required"}

    paper = db.papers.find_one({"paperId": paper_id}, {"_id": 0})
    if not paper:
        return {"error": "Paper not found"}

    existing = db.favorites.find_one({"paperId": paper_id, "markedBy": marked_by})
    if existing:
        return {"already_favorited": True, "paperId": paper_id, "markedBy": marked_by}

    db.favorites.insert_one({
        "paperId":      paper_id,
        "markedBy":     marked_by,
        "markedAt":     datetime.datetime.utcnow().isoformat(),
        "title":        paper.get("title", ""),
        "year":         paper.get("year"),
        "search_topic": paper.get("search_topic", ""),
    })

    return {"favorited": True, "paperId": paper_id, "markedBy": marked_by}


@app.delete("/api/favorites/{paper_id}")
def remove_favorite(paper_id: str, markedBy: str = Query(...)):
    result = db.favorites.delete_one({"paperId": paper_id, "markedBy": markedBy})
    return {"removed": result.deleted_count > 0, "paperId": paper_id, "markedBy": markedBy}


@app.get("/api/favorites")
def list_favorites(markedBy: str = None, page: int = 1, per_page: int = 10):
    mongo_filter = {}
    if markedBy and markedBy != "all":
        mongo_filter["markedBy"] = markedBy

    total = db.favorites.count_documents(mongo_filter)

    skip = (page - 1) * per_page
    docs = list(
        db.favorites.find(mongo_filter, {"_id": 0})
        .sort("markedAt", -1)
        .skip(skip)
        .limit(per_page)
    )

    # Enrich with full paper info (abstract, authors, etc.)
    paper_ids = [d["paperId"] for d in docs]
    papers_by_id = {
        p["paperId"]: p
        for p in db.papers.find({"paperId": {"$in": paper_ids}}, {"_id": 0})
    }

    results = []
    for d in docs:
        p = papers_by_id.get(d["paperId"], {})
        results.append({
            "paperId":        d["paperId"],
            "markedBy":       d["markedBy"],
            "markedAt":       d["markedAt"],
            "title":          p.get("title", d.get("title", "")),
            "year":           p.get("year", d.get("year")),
            "abstract":       (p.get("abstract", "")[:280] + "…") if p.get("abstract") else "",
            "cited_by_count": p.get("cited_by_count", 0),
            "authors":        [a.get("name") for a in p.get("authors", [])][:4],
            "search_topic":   p.get("search_topic", d.get("search_topic", "")),
            "contributor":    p.get("contributor", "unknown"),
        })

    return {
        "results": results,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }