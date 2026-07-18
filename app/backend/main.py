from pathlib import Path
import datetime
import time
from typing import Any

import requests as req
from elasticsearch import Elasticsearch
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from neo4j import GraphDatabase
from pymongo import MongoClient

# Create the FastAPI application that connects the frontend to all three databases.
app = FastAPI(title="LitGraph API")

# Resolve the project folders relative to this file, so the app works on another computer too.
BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")

# Allow the browser-based frontend to call this API during local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connections. MongoDB stores complete paper records, Neo4j stores
# relationships, and Elasticsearch handles fast full-text search.
mongo = MongoClient("mongodb://localhost:27017")
db = mongo["literature_review"]
neo4j = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", "password123"),
)
es = Elasticsearch(
    "http://localhost:9200",
    request_timeout=60,
    retry_on_timeout=True,
    max_retries=3,
)

# Frontend labels are converted to the values stored in the database.
CONTRIB_MAP = {
    "me": "me",
    "teammate": "teammate",
    "shared": "both",
    "both": "both",
}


def contributor_filter(contributor: str) -> dict:
    """Build the small MongoDB filter used by contributor-specific views."""
    if contributor in CONTRIB_MAP:
        return {"contributor": CONTRIB_MAP[contributor]}
    return {}


def normalize_openalex_id(value: str | None) -> str:
    """Keep only the compact OpenAlex ID, for example W2336589871."""
    return (value or "").replace("https://openalex.org/", "")


def rebuild_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    """Turn OpenAlex's position-based abstract format back into readable text."""
    inv = inverted_index or {}
    words = [(position, word) for word, positions in inv.items() for position in positions]
    return " ".join(word for _, word in sorted(words))


def _favorites_for(paper_ids: list[str]) -> dict[str, list[str]]:
    """Return who favorited each paper, grouped by paper ID."""
    if not paper_ids:
        return {}
    docs = db.favorites.find(
        {"paperId": {"$in": paper_ids}},
        {"_id": 0, "paperId": 1, "markedBy": 1},
    )
    output: dict[str, list[str]] = {}
    for doc in docs:
        output.setdefault(doc["paperId"], []).append(doc["markedBy"])
    return output


def upsert_paper_graph(paper: dict[str, Any]) -> None:
    """Create one paper and its factual Neo4j relationships."""
    # MERGE is used throughout this function so rerunning an import updates the
    # graph instead of creating duplicate papers, authors, topics, or edges.
    with neo4j.session() as session:
        session.run(
            """
            MERGE (p:Paper {paperId: $paperId})
            SET p.title = $title,
                p.year = $year,
                p.search_topic = $search_topic,
                p.contributor = $contributor
            """,
            paperId=paper["paperId"],
            title=paper.get("title", ""),
            year=paper.get("year"),
            search_topic=paper.get("search_topic", ""),
            contributor=paper.get("contributor", "unknown"),
        )

        # Link every known author to the paper. A name-based fallback is used
        # only when OpenAlex does not provide an author ID.
        for author in paper.get("authors", []):
            author_id = author.get("authorId") or f"name:{author.get('name', '')}"
            session.run(
                """
                MERGE (a:Author {authorId: $authorId})
                SET a.name = $name
                MERGE (p:Paper {paperId: $paperId})
                MERGE (a)-[:WROTE]->(p)
                """,
                authorId=author_id,
                name=author.get("name", ""),
                paperId=paper["paperId"],
            )

        # Concepts become reusable graph nodes shared by many papers.
        for concept in paper.get("concepts", []):
            session.run(
                """
                MERGE (c:Concept {name: $concept})
                MERGE (p:Paper {paperId: $paperId})
                MERGE (p)-[:HAS_TOPIC]->(c)
                """,
                concept=concept,
                paperId=paper["paperId"],
            )

        # Keep track of the user-entered topic that brought this paper into the project.
        search_topic = paper.get("search_topic")
        if search_topic:
            session.run(
                """
                MERGE (t:SearchTopic {name: $topic})
                MERGE (p:Paper {paperId: $paperId})
                MERGE (p)-[:ADDED_UNDER]->(t)
                """,
                topic=search_topic,
                paperId=paper["paperId"],
            )

        # Referenced papers may not have full metadata yet. Creating a lightweight
        # Paper node here lets Neo4j preserve the citation relationship immediately.
        for ref_id in paper.get("references", []):
            session.run(
                """
                MATCH (p:Paper {paperId: $paperId})
                MERGE (r:Paper {paperId: $refId})
                MERGE (p)-[:REFERENCES]->(r)
                """,
                paperId=paper["paperId"],
                refId=ref_id,
            )


def create_related_for_paper(
    paper_id: str,
    minimum_score: float = 4.0,
    only_higher_id: bool = False,
) -> int:
    """Create explainable RELATED_TO relationships for one paper.

    When ``only_higher_id`` is True, the paper is compared only with papers
    whose paperId is lexicographically greater. This makes a full rebuild
    process every unordered paper pair exactly once.
    """
    # The score is intentionally simple and explainable: shared concepts, shared
    # authors, and direct citations each contribute a fixed number of points.
    with neo4j.session() as session:
        result = session.run(
            """
            MATCH (newPaper:Paper {paperId: $paperId})
            MATCH (other:Paper)
            WHERE other.paperId <> newPaper.paperId
              AND other.title IS NOT NULL
              AND (NOT $onlyHigherId OR other.paperId > newPaper.paperId)

            OPTIONAL MATCH (newPaper)-[:HAS_TOPIC]->(c:Concept)<-[:HAS_TOPIC]-(other)
            WITH newPaper, other,
                 [x IN collect(DISTINCT c.name) WHERE x IS NOT NULL] AS sharedConcepts

            OPTIONAL MATCH (a:Author)-[:WROTE]->(newPaper)
            OPTIONAL MATCH (a)-[:WROTE]->(other)
            WITH newPaper, other, sharedConcepts,
                 [x IN collect(DISTINCT a.name) WHERE x IS NOT NULL] AS sharedAuthors

            OPTIONAL MATCH (newPaper)-[r1:REFERENCES]->(other)
            OPTIONAL MATCH (other)-[r2:REFERENCES]->(newPaper)
            WITH newPaper, other, sharedConcepts, sharedAuthors,
                 CASE WHEN r1 IS NOT NULL OR r2 IS NOT NULL THEN true ELSE false END AS directReference

            WITH newPaper, other, sharedConcepts, sharedAuthors, directReference,
                 2.0 * size(sharedConcepts)
                 + 3.0 * size(sharedAuthors)
                 + CASE WHEN directReference THEN 4.0 ELSE 0.0 END AS score
            WHERE score >= $minimumScore

            MERGE (newPaper)-[rel:RELATED_TO]-(other)
            SET rel.score = score,
                rel.sharedConcepts = sharedConcepts,
                rel.sharedAuthors = sharedAuthors,
                rel.directReference = directReference,
                rel.updatedAt = datetime()
            RETURN count(rel) AS created
            """,
            paperId=paper_id,
            minimumScore=minimum_score,
            onlyHigherId=only_higher_id,
        ).single()
        return int(result["created"] if result else 0)


# ------------------------------ Dashboard data ------------------------------

@app.get("/api/stats")
def get_stats():
    total = db.papers.count_documents({})
    mine = db.papers.count_documents({"contributor": "me"})
    teammate = db.papers.count_documents({"contributor": "teammate"})
    shared = db.papers.count_documents({"contributor": "both"})
    with neo4j.session() as session:
        authors = session.run("MATCH (a:Author) RETURN count(a) AS count").single()["count"]
    return {
        "total": total,
        "mine": mine,
        "teammate": teammate,
        "shared": shared,
        "authors": authors,
    }


@app.get("/api/topics")
def get_topics(contributor: str = "all"):
    match_filter = {"search_topic": {"$exists": True, "$nin": [None, "", "MISSING"]}}
    match_filter.update(contributor_filter(contributor))
    pipeline = [
        {"$match": match_filter},
        {"$group": {"_id": "$search_topic", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 200},
    ]
    results = list(db.papers.aggregate(pipeline))
    return [{"topic": item["_id"], "count": item["count"]} for item in results]


@app.delete("/api/topics/{topic}")
def delete_topic(topic: str):
    papers = list(db.papers.find({"search_topic": topic}, {"paperId": 1}))
    paper_ids = [p["paperId"] for p in papers]
    if not paper_ids:
        return {"error": f"No papers found for topic '{topic}'"}

    mongo_result = db.papers.delete_many({"search_topic": topic})
    db.favorites.delete_many({"paperId": {"$in": paper_ids}})

    es_deleted = 0
    for paper_id in paper_ids:
        try:
            es.delete(index="papers", id=paper_id, ignore=[404])
            es_deleted += 1
        except Exception:
            pass
    es.indices.refresh(index="papers")

    with neo4j.session() as session:
        session.run(
            "MATCH (t:SearchTopic {name: $topic}) DETACH DELETE t",
            topic=topic,
        )
        session.run(
            """
            UNWIND $ids AS paperId
            MATCH (p:Paper {paperId: paperId})
            DETACH DELETE p
            """,
            ids=paper_ids,
        )

    return {
        "deleted_papers": mongo_result.deleted_count,
        "es_deleted": es_deleted,
        "topic": topic,
    }


# ------------------------------- Paper search --------------------------------

@app.get("/api/search")
def search(
    q: str = Query(default="", min_length=0),
    contributor: str = "all",
    topic: str | None = None,
    top_k: int = 20,
):
    timings: dict[str, float] = {}

    # Browsing a topic does not need Elasticsearch; MongoDB can return those
    # papers directly. A keyword search takes the Elasticsearch route below.
    if not q.strip() and topic:
        t0 = time.time()
        mongo_filter = {"search_topic": topic}
        mongo_filter.update(contributor_filter(contributor))
        mongo_papers = list(db.papers.find(mongo_filter, {"_id": 0}))
        timings["mongodb_ms"] = round((time.time() - t0) * 1000, 1)
    else:
        if not q.strip():
            return {"results": [], "timings": {}, "total": 0}

        # Ask Elasticsearch for more candidates than we finally display, then let
        # MongoDB apply contributor/topic filters without losing good matches.
        t0 = time.time()
        es_response = es.search(
            index="papers",
            body={
                "query": {
                    "multi_match": {
                        "query": q,
                        "fields": ["title^3", "abstract", "search_topic^2"],
                        "fuzziness": "AUTO",
                    }
                },
                "size": top_k * 4,
            },
        )
        hits = es_response["hits"]["hits"]
        es_scores = {
            hit["_source"]["paperId"]: round(hit["_score"], 3)
            for hit in hits
        }
        paper_ids = list(es_scores.keys())
        timings["elasticsearch_ms"] = round((time.time() - t0) * 1000, 1)

        if not paper_ids:
            return {"results": [], "timings": timings, "total": 0}

        t0 = time.time()
        mongo_filter = {"paperId": {"$in": paper_ids}}
        mongo_filter.update(contributor_filter(contributor))
        if topic:
            mongo_filter["search_topic"] = topic
        mongo_papers = list(db.papers.find(mongo_filter, {"_id": 0}))
        timings["mongodb_ms"] = round((time.time() - t0) * 1000, 1)

    if not mongo_papers:
        return {"results": [], "timings": timings, "total": 0}

    filtered_ids = [paper["paperId"] for paper in mongo_papers]

    # Neo4j enriches the search results with authors, concepts, and references.

    t0 = time.time()
    with neo4j.session() as session:
        result = session.run(
            """
            MATCH (p:Paper) WHERE p.paperId IN $ids
            OPTIONAL MATCH (a:Author)-[:WROTE]->(p)
            OPTIONAL MATCH (p)-[:HAS_TOPIC]->(c:Concept)
            OPTIONAL MATCH (p)-[:REFERENCES]->(ref:Paper)
            RETURN p.paperId AS paperId,
                   collect(DISTINCT a.name)[0..4] AS authors,
                   collect(DISTINCT c.name)[0..5] AS graph_topics,
                   collect(DISTINCT ref.title)[0..2] AS references
            """,
            ids=filtered_ids,
        )
        graph_data = {row["paperId"]: dict(row) for row in result}
    timings["neo4j_ms"] = round((time.time() - t0) * 1000, 1)
    timings["total_ms"] = round(sum(timings.values()), 1)

    # Favorites live in MongoDB, so they are merged into the final API response here.
    fav_map = _favorites_for(filtered_ids)
    es_scores = locals().get("es_scores", {})

    results = []
    for paper in mongo_papers:
        pid = paper["paperId"]
        graph = graph_data.get(pid, {})
        results.append(
            {
                "paperId": pid,
                "title": paper.get("title", ""),
                "year": paper.get("year"),
                "abstract": (paper.get("abstract", "")[:280] + "…") if paper.get("abstract") else "",
                "cited_by_count": paper.get("cited_by_count", 0),
                "relevance_score": es_scores.get(pid, 0),
                "authors": graph.get("authors", []),
                "graph_topics": graph.get("graph_topics", []),
                "references": graph.get("references", []),
                "search_topic": paper.get("search_topic", ""),
                "contributor": paper.get("contributor", "unknown"),
                "favorited_by": fav_map.get(pid, []),
            }
        )

    if q.strip():
        results.sort(key=lambda item: item["relevance_score"], reverse=True)
    else:
        results.sort(key=lambda item: item["cited_by_count"], reverse=True)

    return {"results": results[:top_k], "timings": timings, "total": len(results)}


# -------------------------- Search-result graph view --------------------------

@app.get("/api/keyword-graph")
def keyword_graph(
    q: str = Query(..., min_length=1),
    contributor: str = "all",
    topic: str | None = None,
    top_k: int = 20,
    neighbors_per_paper: int = 5,
):
    """Return graph-ready nodes and edges for a frontend keyword search."""
    es_response = es.search(
        index="papers",
        body={
            "query": {
                "multi_match": {
                    "query": q,
                    "fields": ["title^3", "abstract", "search_topic^2"],
                    "fuzziness": "AUTO",
                }
            },
            "size": top_k * 4,
        },
    )
    candidate_ids = [hit["_source"]["paperId"] for hit in es_response["hits"]["hits"]]
    if not candidate_ids:
        return {"nodes": [], "edges": [], "matched_paper_ids": []}

    mongo_filter: dict[str, Any] = {"paperId": {"$in": candidate_ids}}
    mongo_filter.update(contributor_filter(contributor))
    if topic:
        mongo_filter["search_topic"] = topic

    matched_docs = list(db.papers.find(mongo_filter, {"_id": 0, "paperId": 1}))
    matched_ids = [doc["paperId"] for doc in matched_docs][:top_k]
    if not matched_ids:
        return {"nodes": [], "edges": [], "matched_paper_ids": []}

    with neo4j.session() as session:
        rows = session.run(
            """
            MATCH (p:Paper)
            WHERE p.paperId IN $ids

            CALL {
                WITH p
                OPTIONAL MATCH (p)-[rel:RELATED_TO]-(other:Paper)
                WHERE other.title IS NOT NULL
                WITH rel, other
                ORDER BY rel.score DESC
                RETURN collect({
                    paperId: other.paperId,
                    title: other.title,
                    year: other.year,
                    score: rel.score,
                    sharedConcepts: rel.sharedConcepts,
                    sharedAuthors: rel.sharedAuthors,
                    directReference: rel.directReference
                })[0..$neighborLimit] AS related
            }

            OPTIONAL MATCH (a:Author)-[:WROTE]->(p)
            OPTIONAL MATCH (p)-[:HAS_TOPIC]->(c:Concept)
            OPTIONAL MATCH (p)-[:REFERENCES]->(ref:Paper)

            RETURN p.paperId AS paperId,
                   p.title AS title,
                   p.year AS year,
                   collect(DISTINCT a.name)[0..8] AS authors,
                   collect(DISTINCT c.name)[0..10] AS concepts,
                   collect(DISTINCT {
                       paperId: ref.paperId,
                       title: coalesce(ref.title, ref.paperId)
                   })[0..5] AS references,
                   related
            """,
            ids=matched_ids,
            neighborLimit=neighbors_per_paper,
        )

        records = [dict(row) for row in rows]

    # Dictionaries naturally remove duplicate frontend nodes and edges.
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}

    def add_node(node: dict[str, Any]) -> None:
        nodes[node["id"]] = node

    def add_edge(edge: dict[str, Any]) -> None:
        key = f"{edge['source']}|{edge['type']}|{edge['target']}"
        edges[key] = edge

    matched_set = set(matched_ids)
    for record in records:
        paper_node_id = f"paper:{record['paperId']}"
        add_node(
            {
                "id": paper_node_id,
                "type": "Paper",
                "label": record.get("title") or record["paperId"],
                "paperId": record["paperId"],
                "year": record.get("year"),
                "matched": True,
            }
        )

        for author in record.get("authors") or []:
            if not author:
                continue
            author_id = f"author:{author}"
            add_node({"id": author_id, "type": "Author", "label": author})
            add_edge({"source": author_id, "target": paper_node_id, "type": "WROTE"})

        for concept in record.get("concepts") or []:
            if not concept:
                continue
            concept_id = f"concept:{concept}"
            add_node({"id": concept_id, "type": "Concept", "label": concept})
            add_edge({"source": paper_node_id, "target": concept_id, "type": "HAS_TOPIC"})

        for reference in record.get("references") or []:
            ref_id = reference.get("paperId")
            if not ref_id:
                continue
            ref_node_id = f"paper:{ref_id}"
            add_node(
                {
                    "id": ref_node_id,
                    "type": "Reference",
                    "label": reference.get("title") or ref_id,
                    "paperId": ref_id,
                    "matched": ref_id in matched_set,
                }
            )
            add_edge({"source": paper_node_id, "target": ref_node_id, "type": "REFERENCES"})

        for related in record.get("related") or []:
            related_id = related.get("paperId")
            if not related_id:
                continue
            related_node_id = f"paper:{related_id}"
            add_node(
                {
                    "id": related_node_id,
                    "type": "Paper",
                    "label": related.get("title") or related_id,
                    "paperId": related_id,
                    "year": related.get("year"),
                    "matched": related_id in matched_set,
                }
            )
            add_edge(
                {
                    "source": paper_node_id,
                    "target": related_node_id,
                    "type": "RELATED_TO",
                    "score": related.get("score", 0),
                    "sharedConcepts": related.get("sharedConcepts") or [],
                    "sharedAuthors": related.get("sharedAuthors") or [],
                    "directReference": bool(related.get("directReference")),
                }
            )

    return {
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "matched_paper_ids": matched_ids,
    }


# ---------------------------- Interactive expansion ---------------------------

@app.get("/api/graph-expand")
def graph_expand(
    node_id: str = Query(..., min_length=1),
    contributor: str = "all",
    limit: int = 30,
    strict_contributor: bool = False,
):
    """Expand one Neo4j node and return its immediate graph neighbourhood.

    Supported frontend IDs:
      paper:<paperId>
      author:<authorId or name>
      concept:<concept name>
      topic:<topic name>

    By default, contributor filtering is contextual: the selected node can expose
    connected papers from other contributors. Set strict_contributor=true to
    restrict every returned Paper neighbour to the selected contributor.
    """
    if ":" not in node_id:
        return {"nodes": [], "edges": [], "error": "Invalid node_id"}

    prefix, raw_id = node_id.split(":", 1)
    prefix = prefix.strip().lower()
    raw_id = raw_id.strip()
    if not raw_id:
        return {"nodes": [], "edges": [], "error": "Invalid node_id"}

    label_map = {
        "paper": "Paper",
        "author": "Author",
        "concept": "Concept",
        "topic": "SearchTopic",
        "searchtopic": "SearchTopic",
    }
    label = label_map.get(prefix)
    if not label:
        return {"nodes": [], "edges": [], "error": f"Unsupported node type: {prefix}"}

    property_map = {
        "Paper": "paperId",
        "Author": "authorId",
        "Concept": "name",
        "SearchTopic": "name",
    }
    property_name = property_map[label]

    mapped_contributor = CONTRIB_MAP.get(contributor, contributor)
    allowed_contributors: list[str] = []
    if mapped_contributor and mapped_contributor != "all":
        allowed_contributors = [mapped_contributor]
        # Shared papers are relevant in Me and Teammate views.
        if mapped_contributor in {"me", "teammate"}:
            allowed_contributors.append("both")

    match_clause = (
        "MATCH (center:Author) WHERE center.authorId = $raw_id OR center.name = $raw_id"
        if label == "Author"
        else f"MATCH (center:{label} {{{property_name}: $raw_id}})"
    )

    query = f"""
    {match_clause}
    OPTIONAL MATCH (center)-[r]-(neighbor)
    WHERE r IS NULL
       OR NOT neighbor:Paper
       OR NOT $strictContributor
       OR size($allowedContributors) = 0
       OR neighbor.contributor IN $allowedContributors
    WITH center, r, neighbor
    LIMIT $rowLimit
    RETURN center,
           CASE WHEN r IS NULL THEN null ELSE type(r) END AS relationType,
           properties(r) AS relationProperties,
           neighbor,
           CASE WHEN r IS NULL THEN null ELSE startNode(r) = center END AS centerIsSource
    """

    with neo4j.session() as session:
        rows = [dict(row) for row in session.run(
            query,
            raw_id=raw_id,
            rowLimit=max(1, min(limit, 100)),
            strictContributor=strict_contributor,
            allowedContributors=allowed_contributors,
        )]

    if not rows:
        return {"nodes": [], "edges": [], "expanded_node_id": node_id}

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}

    def neo4j_node_to_frontend(node) -> dict[str, Any] | None:
        if node is None:
            return None
        props = dict(node)
        labels = set(node.labels)
        if "Paper" in labels:
            paper_id = str(props.get("paperId", "")).strip()
            if not paper_id:
                return None
            return {
                "id": f"paper:{paper_id}",
                "type": "Paper",
                "label": props.get("title") or paper_id,
                "paperId": paper_id,
                "title": props.get("title") or "",
                "year": props.get("year"),
                "abstract": props.get("abstract") or "",
                "cited_by_count": props.get("cited_by_count", 0),
                "contributor": props.get("contributor", "unknown"),
                "matched": False,
            }
        if "Author" in labels:
            author_id = str(props.get("authorId") or props.get("name") or "").strip()
            if not author_id:
                return None
            return {
                "id": f"author:{author_id}",
                "type": "Author",
                "label": props.get("name") or author_id,
                "authorId": author_id,
            }
        if "Concept" in labels:
            name = str(props.get("name", "")).strip()
            if not name:
                return None
            return {"id": f"concept:{name}", "type": "Concept", "label": name}
        if "SearchTopic" in labels:
            name = str(props.get("name", "")).strip()
            if not name:
                return None
            return {"id": f"topic:{name}", "type": "SearchTopic", "label": name}
        return None

    for row in rows:
        center_data = neo4j_node_to_frontend(row.get("center"))
        neighbor_data = neo4j_node_to_frontend(row.get("neighbor"))
        if center_data:
            center_data["matched"] = True
            nodes[center_data["id"]] = center_data
        if neighbor_data:
            nodes[neighbor_data["id"]] = neighbor_data

        relation_type = row.get("relationType")
        if not center_data or not neighbor_data or not relation_type:
            continue

        props = row.get("relationProperties") or {}
        center_is_source = bool(row.get("centerIsSource"))
        source = center_data["id"] if center_is_source else neighbor_data["id"]
        target = neighbor_data["id"] if center_is_source else center_data["id"]
        edge = {
            "source": source,
            "target": target,
            "type": relation_type,
            "score": props.get("score", 0),
            "sharedConcepts": props.get("sharedConcepts") or [],
            "sharedAuthors": props.get("sharedAuthors") or [],
            "directReference": bool(props.get("directReference")),
            "reason": props.get("reason") or "",
        }
        edge_key = f"{source}|{relation_type}|{target}"
        edges[edge_key] = edge

    return {
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "expanded_node_id": node_id,
        "strict_contributor": strict_contributor,
    }


# ----------------------------- OpenAlex importing -----------------------------

@app.post("/api/add-topic")
def add_topic(payload: dict):
    topic = payload.get("topic", "").strip()
    contributor = payload.get("contributor", "me").strip().lower() or "me"
    if not topic:
        return {"error": "No topic provided"}

    # Start with a precise title search. Broader fallbacks are used only when
    # OpenAlex returns too few useful records.
    works: list[dict[str, Any]] = []
    params = {
        "filter": f"title.search:{topic},has_abstract:true",
        "per-page": 10,
        "sort": "cited_by_count:desc",
        "select": "id,title,abstract_inverted_index,publication_year,authorships,cited_by_count,referenced_works,concepts",
    }

    response = req.get("https://api.openalex.org/works", params=params, timeout=20)
    if response.status_code == 200:
        works = response.json().get("results", [])

    if len(works) < 5:
        params2 = dict(params)
        params2["filter"] = f"abstract.search:{topic},has_abstract:true"
        response2 = req.get("https://api.openalex.org/works", params=params2, timeout=20)
        if response2.status_code == 200:
            existing = {work["id"] for work in works}
            works += [
                work
                for work in response2.json().get("results", [])
                if work["id"] not in existing
            ]

    if len(works) < 3:
        params3 = dict(params)
        params3.pop("filter")
        params3["search"] = topic
        response3 = req.get("https://api.openalex.org/works", params=params3, timeout=20)
        if response3.status_code == 200:
            existing = {work["id"] for work in works}
            works += [
                work
                for work in response3.json().get("results", [])
                if work["id"] not in existing
            ]

    if not works:
        return {"error": f"No papers found for '{topic}' — try different keywords"}

    added_ids: list[str] = []

    # Store each new paper in all three systems so search and graph features stay aligned.
    for work in works:
        paper_id = normalize_openalex_id(work.get("id"))
        if not paper_id or db.papers.find_one({"paperId": paper_id}):
            continue

        authors = []
        for authorship in work.get("authorships") or []:
            author = authorship.get("author") or {}
            if author.get("display_name"):
                authors.append(
                    {
                        "authorId": normalize_openalex_id(author.get("id")),
                        "name": author["display_name"],
                    }
                )

        concepts = [
            concept["display_name"]
            for concept in work.get("concepts") or []
            if concept.get("display_name") and concept.get("score", 0) > 0.3
        ]

        references = [
            normalize_openalex_id(reference)
            for reference in work.get("referenced_works") or []
            if normalize_openalex_id(reference)
        ]

        paper = {
            "paperId": paper_id,
            "title": work.get("title", ""),
            "abstract": rebuild_abstract(work.get("abstract_inverted_index")),
            "year": work.get("publication_year"),
            "authors": authors,
            "citations": [],
            "cited_by_count": work.get("cited_by_count", 0),
            "references": references,
            "concepts": concepts,
            "search_topic": topic,
            "contributor": contributor,
        }

        db.papers.insert_one(dict(paper))

        es.index(
            index="papers",
            id=paper_id,
            document={
                "paperId": paper_id,
                "title": paper["title"],
                "abstract": paper["abstract"],
                "year": paper["year"],
                "search_topic": topic,
                "contributor": contributor,
                "cited_by_count": paper["cited_by_count"],
            },
        )

        upsert_paper_graph(paper)
        added_ids.append(paper_id)

    es.indices.refresh(index="papers")

    # New papers must be compared with every existing paper, so do not use
    # only_higher_id here. MERGE prevents duplicate RELATED_TO edges.
    for paper_id in added_ids:
        create_related_for_paper(paper_id, minimum_score=4.0)

    with neo4j.session() as session:
        related_total = session.run(
            "MATCH ()-[r:RELATED_TO]-() RETURN count(r) AS count"
        ).single()["count"]

    return {
        "added": len(added_ids),
        "topic": topic,
        "paper_ids": added_ids,
        "total_related_relationships": related_total,
    }


# -------------------------- Relationship maintenance -------------------------

@app.post("/api/rebuild-related")
def rebuild_related(payload: dict | None = None):
    """Optional maintenance endpoint to rebuild RELATED_TO for all full papers."""
    minimum_score = float((payload or {}).get("minimum_score", 4.0))
    # Rebuild from a clean slate. This prevents old scores or stale links from
    # surviving after the scoring rule or threshold changes.
    with neo4j.session() as session:
        session.run("MATCH ()-[r:RELATED_TO]-() DELETE r")
        paper_ids = [
            row["paperId"]
            for row in session.run(
                "MATCH (p:Paper) WHERE p.title IS NOT NULL RETURN p.paperId AS paperId"
            )
        ]

    # Compare each unordered pair only once. This avoids recalculating A-B
    # again when B is processed and keeps the reported count accurate.
    for paper_id in paper_ids:
        create_related_for_paper(
            paper_id,
            minimum_score=minimum_score,
            only_higher_id=True,
        )

    with neo4j.session() as session:
        relationship_count = session.run(
            "MATCH ()-[r:RELATED_TO]-() RETURN count(r) AS count"
        ).single()["count"]

    return {
        "papers_processed": len(paper_ids),
        "relationships_created": relationship_count,
        "minimum_score": minimum_score,
    }


# ------------------------------- Favorites API --------------------------------

@app.post("/api/favorites")
def add_favorite(payload: dict):
    paper_id = payload.get("paperId", "").strip()
    marked_by = payload.get("markedBy", "").strip()
    if not paper_id or not marked_by:
        return {"error": "paperId and markedBy are required"}

    paper = db.papers.find_one({"paperId": paper_id}, {"_id": 0})
    if not paper:
        return {"error": "Paper not found"}

    existing = db.favorites.find_one({"paperId": paper_id, "markedBy": marked_by})
    if existing:
        return {"already_favorited": True, "paperId": paper_id, "markedBy": marked_by}

    db.favorites.insert_one(
        {
            "paperId": paper_id,
            "markedBy": marked_by,
            "markedAt": datetime.datetime.now(datetime.UTC).isoformat(),
            "title": paper.get("title", ""),
            "year": paper.get("year"),
            "search_topic": paper.get("search_topic", ""),
        }
    )
    return {"favorited": True, "paperId": paper_id, "markedBy": marked_by}


@app.delete("/api/favorites/{paper_id}")
def remove_favorite(paper_id: str, markedBy: str = Query(...)):
    result = db.favorites.delete_one({"paperId": paper_id, "markedBy": markedBy})
    return {"removed": result.deleted_count > 0, "paperId": paper_id, "markedBy": markedBy}


@app.get("/api/favorites")
def list_favorites(markedBy: str | None = None, page: int = 1, per_page: int = 10):
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

    paper_ids = [doc["paperId"] for doc in docs]
    papers_by_id = {
        paper["paperId"]: paper
        for paper in db.papers.find({"paperId": {"$in": paper_ids}}, {"_id": 0})
    }

    results = []
    for doc in docs:
        paper = papers_by_id.get(doc["paperId"], {})
        results.append(
            {
                "paperId": doc["paperId"],
                "markedBy": doc["markedBy"],
                "markedAt": doc["markedAt"],
                "title": paper.get("title", doc.get("title", "")),
                "year": paper.get("year", doc.get("year")),
                "abstract": (paper.get("abstract", "")[:280] + "…") if paper.get("abstract") else "",
                "cited_by_count": paper.get("cited_by_count", 0),
                "authors": [author.get("name") for author in paper.get("authors", [])][:4],
                "search_topic": paper.get("search_topic", doc.get("search_topic", "")),
                "contributor": paper.get("contributor", "unknown"),
            }
        )

    return {
        "results": results,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
    }


# A lightweight endpoint used to confirm that the API and core services are alive.
@app.get("/health")
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "mongodb": mongo.admin.command("ping").get("ok") == 1,
        "elasticsearch": bool(es.ping()),
    }
