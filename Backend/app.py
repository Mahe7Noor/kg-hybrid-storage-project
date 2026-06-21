from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from neo4j import GraphDatabase
from elasticsearch import Elasticsearch
import time
import requests as req

app = FastAPI(title="LitGraph API")

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


# ── /api/stats ─────────────────────────────────────────────────────
@app.get("/api/stats")
def get_stats():
    total    = db.papers.count_documents({})
    mine     = db.papers.count_documents({"contributor": "me"})
    teammate = db.papers.count_documents({"contributor": "teammate"})
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
    if contributor == "mine":
        match_filter["contributor"] = "me"
    elif contributor == "teammate":
        match_filter["contributor"] = "teammate"
    elif contributor == "shared":
        match_filter["contributor"] = "both"

    pipeline = [
        {"$match": match_filter},
        {"$group": {"_id": "$search_topic", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 50}
    ]
    results = list(db.papers.aggregate(pipeline))
    return [{"topic": r["_id"], "count": r["count"]} for r in results]


# ── /api/search ────────────────────────────────────────────────────
@app.get("/api/search")
def search(
    q:           str = Query(default="", min_length=0),
    contributor: str = "all",
    topic:       str = None,
    top_k:       int = 20   # increased from 8 so you see all results
):
    timings = {}

    # If no search query but a topic chip is selected —
    # fetch ALL papers for that topic directly from MongoDB
    # instead of going through Elasticsearch (which needs a query string)
    if not q.strip() and topic:
        t0           = time.time()
        mongo_filter = {"search_topic": topic}

        if contributor == "mine":
            mongo_filter["contributor"] = "me"
        elif contributor == "teammate":
            mongo_filter["contributor"] = "teammate"
        elif contributor == "shared":
            mongo_filter["contributor"] = "both"

        mongo_papers = list(db.papers.find(mongo_filter, {"_id": 0}))
        timings["mongodb_ms"] = round((time.time() - t0) * 1000, 1)

        if not mongo_papers:
            return {"results": [], "timings": timings, "total": 0}

        filtered_ids = [p["paperId"] for p in mongo_papers]

        # Still enrich with Neo4j relationships
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
            })

        # Sort by citation count when no search query
        results.sort(key=lambda x: x["cited_by_count"], reverse=True)
        return {"results": results[:top_k], "timings": timings, "total": len(results)}

    # Normal search — go through Elasticsearch first
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
        "size": top_k * 4   # fetch more so filters still leave enough
    })

    hits      = es_response["hits"]["hits"]
    paper_ids = [h["_source"]["paperId"] for h in hits]
    es_scores = {h["_source"]["paperId"]: round(h["_score"], 3) for h in hits}
    timings["elasticsearch_ms"] = round((time.time() - t0) * 1000, 1)

    if not paper_ids:
        return {"results": [], "timings": timings, "total": 0}

    # MongoDB — fetch full details + apply filters
    t0           = time.time()
    mongo_filter = {"paperId": {"$in": paper_ids}}

    if contributor == "mine":
        mongo_filter["contributor"] = "me"
    elif contributor == "teammate":
        mongo_filter["contributor"] = "teammate"
    elif contributor == "shared":
        mongo_filter["contributor"] = "both"

    if topic:
        mongo_filter["search_topic"] = topic

    mongo_papers = list(db.papers.find(mongo_filter, {"_id": 0}))
    timings["mongodb_ms"] = round((time.time() - t0) * 1000, 1)

    if not mongo_papers:
        return {"results": [], "timings": timings, "total": 0}

    filtered_ids = [p["paperId"] for p in mongo_papers]

    # Neo4j — graph relationships
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
        })

    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return {"results": results[:top_k], "timings": timings, "total": len(results)}


# ── /api/add-topic ─────────────────────────────────────────────────
@app.post("/api/add-topic")
def add_topic(payload: dict):
    topic = payload.get("topic", "").strip()
    if not topic:
        return {"error": "No topic provided"}

    works = []

    # Title search first
    params = {
        "filter": f"title.search:{topic},has_abstract:true",
        "per-page": 10,
        "sort": "cited_by_count:desc",
        "select": "id,title,abstract_inverted_index,publication_year,authorships,cited_by_count,referenced_works,concepts"
    }
    r = req.get("https://api.openalex.org/works", params=params, timeout=20)
    if r.status_code == 200:
        works = r.json().get("results", [])

    # Fall back to abstract search if too few results
    if len(works) < 5:
        params2 = dict(params)
        params2["filter"] = f"abstract.search:{topic},has_abstract:true"
        r2 = req.get("https://api.openalex.org/works", params=params2, timeout=20)
        if r2.status_code == 200:
            existing = {w["id"] for w in works}
            works += [w for w in r2.json().get("results", []) if w["id"] not in existing]

    # Last resort — broad keyword search
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
            "contributor":    "me"
        }

        db.papers.insert_one({k: v for k, v in paper.items()})

        es.index(index="papers", id=paper_id, document={
            "paperId":        paper_id,
            "title":          paper["title"],
            "abstract":       paper["abstract"],
            "year":           paper["year"],
            "search_topic":   topic,
            "contributor":    "me",
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