from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import os

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from fastapi import FastAPI, HTTPException, Query
from neo4j import GraphDatabase
from pydantic import BaseModel, Field
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "knowledge_graph")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ELASTICSEARCH_INDEX = os.getenv("ELASTICSEARCH_INDEX", "kg_documents")

app = FastAPI(
    title="Knowledge Graph with Hybrid Storage",
    description="Demo project using MongoDB + Neo4j + Elasticsearch.",
    version="1.0.0",
)

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB]
documents_collection = mongo_db["documents"]

neo4j_driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)

es = Elasticsearch(ELASTICSEARCH_URL)


class DocumentInput(BaseModel):
    document_id: str = Field(..., examples=["doc_001"])
    title: str
    author: str
    organization: str
    topic: str
    content: str
    published_date: Optional[str] = None
    keywords: List[str] = []


def create_elasticsearch_index() -> None:
    """Create Elasticsearch index with beginner-friendly mappings."""
    if es.indices.exists(index=ELASTICSEARCH_INDEX):
        return

    mapping = {
        "mappings": {
            "properties": {
                "document_id": {"type": "keyword"},
                "title": {"type": "text"},
                "author": {"type": "keyword"},
                "organization": {"type": "keyword"},
                "topic": {"type": "keyword"},
                "content": {"type": "text"},
                "published_date": {"type": "keyword"},
                "keywords": {"type": "keyword"}
            }
        }
    }
    es.indices.create(index=ELASTICSEARCH_INDEX, body=mapping)


def upsert_mongodb(doc: Dict[str, Any]) -> None:
    """Store complete document and metadata in MongoDB."""
    documents_collection.update_one(
        {"document_id": doc["document_id"]},
        {"$set": doc},
        upsert=True
    )


def upsert_neo4j(doc: Dict[str, Any]) -> None:
    """Create knowledge graph nodes and relationships in Neo4j."""
    cypher = """
    MERGE (d:Document {document_id: $document_id})
    SET d.title = $title,
        d.published_date = $published_date

    MERGE (p:Person {name: $author})
    MERGE (o:Organization {name: $organization})
    MERGE (t:Topic {name: $topic})

    MERGE (p)-[:AUTHORED]->(d)
    MERGE (p)-[:AFFILIATED_WITH]->(o)
    MERGE (d)-[:MENTIONS]->(t)
    MERGE (o)-[:WORKS_ON]->(t)
    """
    with neo4j_driver.session() as session:
        session.run(
            cypher,
            document_id=doc["document_id"],
            title=doc["title"],
            published_date=doc.get("published_date"),
            author=doc["author"],
            organization=doc["organization"],
            topic=doc["topic"],
        )


def upsert_elasticsearch(doc: Dict[str, Any]) -> None:
    """Index searchable document fields in Elasticsearch."""
    create_elasticsearch_index()
    es.index(
        index=ELASTICSEARCH_INDEX,
        id=doc["document_id"],
        document=doc,
        refresh=True
    )


def ingest_document(doc: Dict[str, Any]) -> None:
    """Send one document to all three systems."""
    upsert_mongodb(doc)
    upsert_neo4j(doc)
    upsert_elasticsearch(doc)


@app.get("/")
def home() -> Dict[str, Any]:
    return {
        "message": "Knowledge Graph Hybrid Storage API is running",
        "open_api_docs": "http://127.0.0.1:8000/docs",
        "neo4j_browser": "http://localhost:7474",
        "elasticsearch": "http://localhost:9200",
    }


@app.get("/health")
def health() -> Dict[str, Any]:
    """Check whether MongoDB, Neo4j, and Elasticsearch are reachable."""
    result = {
        "mongodb": False,
        "neo4j": False,
        "elasticsearch": False
    }

    try:
        mongo_client.admin.command("ping")
        result["mongodb"] = True
    except Exception:
        result["mongodb"] = False

    try:
        with neo4j_driver.session() as session:
            session.run("RETURN 1")
        result["neo4j"] = True
    except Exception:
        result["neo4j"] = False

    try:
        result["elasticsearch"] = bool(es.ping())
    except Exception:
        result["elasticsearch"] = False

    return result


@app.post("/documents")
def add_document(document: DocumentInput) -> Dict[str, Any]:
    """Add one document to MongoDB, Neo4j, and Elasticsearch."""
    doc = document.model_dump()
    ingest_document(doc)
    return {"message": "Document ingested successfully", "document_id": doc["document_id"]}


@app.post("/ingest-sample")
def ingest_sample_data() -> Dict[str, Any]:
    """Load sample_data.json into all three databases."""
    sample_path = Path(__file__).resolve().parent.parent / "sample_data.json"

    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="sample_data.json not found")

    data = json.loads(sample_path.read_text(encoding="utf-8"))

    for doc in data:
        ingest_document(doc)

    return {
        "message": "Sample data ingested into MongoDB, Neo4j, and Elasticsearch",
        "count": len(data)
    }


@app.get("/documents")
def list_documents() -> Dict[str, Any]:
    """List documents from MongoDB."""
    docs = list(documents_collection.find({}, {"_id": 0}))
    return {"count": len(docs), "documents": docs}


@app.get("/documents/{document_id}")
def get_document(document_id: str) -> Dict[str, Any]:
    """Get one document from MongoDB."""
    doc = documents_collection.find_one({"document_id": document_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@app.get("/search")
def search_documents(q: str = Query(..., description="Text query, e.g. machine learning")) -> Dict[str, Any]:
    """Search title/content in Elasticsearch."""
    create_elasticsearch_index()

    body = {
        "query": {
            "multi_match": {
                "query": q,
                "fields": ["title^3", "content", "keywords^2", "topic"]
            }
        },
        "highlight": {
            "fields": {
                "title": {},
                "content": {}
            }
        }
    }

    response = es.search(index=ELASTICSEARCH_INDEX, body=body)
    hits = response["hits"]["hits"]

    results = []
    for hit in hits:
        source = hit["_source"]
        results.append({
            "document_id": source["document_id"],
            "title": source["title"],
            "author": source["author"],
            "topic": source["topic"],
            "score": hit["_score"],
            "highlight": hit.get("highlight", {})
        })

    return {
        "query": q,
        "count": len(results),
        "results": results
    }


@app.get("/graph/entity/{entity_name}")
def get_entity_graph(entity_name: str) -> Dict[str, Any]:
    """Find graph relationships for a person, document title, topic, or organization."""
    cypher = """
    MATCH (n)
    WHERE n.name = $entity_name OR n.title = $entity_name OR n.document_id = $entity_name
    OPTIONAL MATCH (n)-[r]-(m)
    RETURN labels(n) AS source_labels,
           coalesce(n.name, n.title, n.document_id) AS source,
           type(r) AS relationship,
           labels(m) AS target_labels,
           coalesce(m.name, m.title, m.document_id) AS target
    """

    with neo4j_driver.session() as session:
        rows = list(session.run(cypher, entity_name=entity_name))

    relationships = []
    for row in rows:
        if row["relationship"] is not None:
            relationships.append({
                "source": row["source"],
                "source_labels": row["source_labels"],
                "relationship": row["relationship"],
                "target": row["target"],
                "target_labels": row["target_labels"],
            })

    if not relationships:
        return {
            "entity": entity_name,
            "message": "No relationships found. Make sure you have ingested sample data first.",
            "relationships": []
        }

    return {
        "entity": entity_name,
        "relationships": relationships
    }


@app.get("/hybrid-search")
def hybrid_search(q: str = Query(..., description="Example: machine learning")) -> Dict[str, Any]:
    """
    Hybrid search:
    1. Search documents using Elasticsearch.
    2. Use document IDs to fetch full records from MongoDB.
    3. Use document IDs to fetch relationships from Neo4j.
    """
    create_elasticsearch_index()

    search_body = {
        "query": {
            "multi_match": {
                "query": q,
                "fields": ["title^3", "content", "keywords^2", "topic"]
            }
        }
    }

    es_response = es.search(index=ELASTICSEARCH_INDEX, body=search_body)
    hits = es_response["hits"]["hits"]

    hybrid_results = []

    for hit in hits:
        document_id = hit["_source"]["document_id"]

        mongo_doc = documents_collection.find_one(
            {"document_id": document_id},
            {"_id": 0}
        )

        cypher = """
        MATCH (d:Document {document_id: $document_id})
        OPTIONAL MATCH (p:Person)-[:AUTHORED]->(d)
        OPTIONAL MATCH (d)-[:MENTIONS]->(t:Topic)
        OPTIONAL MATCH (p)-[:AFFILIATED_WITH]->(o:Organization)
        RETURN d.document_id AS document_id,
               d.title AS title,
               collect(DISTINCT p.name) AS authors,
               collect(DISTINCT t.name) AS topics,
               collect(DISTINCT o.name) AS organizations
        """

        with neo4j_driver.session() as session:
            graph_row = session.run(cypher, document_id=document_id).single()

        hybrid_results.append({
            "search_score": hit["_score"],
            "mongo_document": mongo_doc,
            "graph_context": {
                "authors": graph_row["authors"] if graph_row else [],
                "topics": graph_row["topics"] if graph_row else [],
                "organizations": graph_row["organizations"] if graph_row else [],
            }
        })

    return {
        "query": q,
        "count": len(hybrid_results),
        "results": hybrid_results
    }


@app.delete("/reset-demo")
def reset_demo() -> Dict[str, Any]:
    """
    Delete demo data from MongoDB, Neo4j, and Elasticsearch.
    Useful when you want to restart the project demo.
    """
    documents_collection.delete_many({})

    with neo4j_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

    if es.indices.exists(index=ELASTICSEARCH_INDEX):
        es.indices.delete(index=ELASTICSEARCH_INDEX)

    return {"message": "Demo data removed from all three systems"}
