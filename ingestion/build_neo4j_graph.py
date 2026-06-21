# ingestion/build_neo4j_graph.py
#
# Build or rebuild the Neo4j knowledge graph from papers stored in MongoDB.
#
# Compatible with the FastAPI backend:
#
# Paper node:
#   (:Paper {paperId, title, year, abstract, cited_by_count, contributor})
#
# Author node:
#   (:Author {authorId, name})
#
# Concept node:
#   (:Concept {name})
#
# Relationships:
#   (:Author)-[:WROTE]->(:Paper)
#   (:Paper)-[:HAS_TOPIC]->(:Concept)
#   (:Paper)-[:REFERENCES]->(:Paper)
#
# Run from project root:
#   python ingestion/build_neo4j_graph.py
#
# Optional full clean rebuild:
#   python ingestion/build_neo4j_graph.py --clear
#
# Optional test run:
#   python ingestion/build_neo4j_graph.py --limit 25

import argparse
from typing import Any

from pymongo import MongoClient
from neo4j import GraphDatabase


# ─────────────────────────────────────────
# Database settings
# ─────────────────────────────────────────

MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "literature_review"
MONGO_COLLECTION = "papers"

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password123"


# ─────────────────────────────────────────
# Normalization helpers
# ─────────────────────────────────────────

def normalize_authors(authors: list[Any] | None) -> list[dict[str, str]]:
    """
    Convert authors into a clean list of dictionaries.

    Supports both:
        [{"authorId": "A123", "name": "John Smith"}]
    and:
        ["John Smith", "Jane Doe"]
    """

    clean_authors: list[dict[str, str]] = []

    for author in authors or []:
        if isinstance(author, dict):
            name = str(author.get("name", "")).strip()
            author_id = str(author.get("authorId", "")).strip()

            if name:
                clean_authors.append({
                    "authorId": author_id or name,
                    "name": name,
                })

        elif isinstance(author, str):
            name = author.strip()

            if name:
                clean_authors.append({
                    "authorId": name,
                    "name": name,
                })

    return clean_authors


def normalize_concepts(concepts: list[Any] | None) -> list[str]:
    """
    Convert concepts/topics into a clean unique list of concept names.

    Supports:
        ["Knowledge graph", "Data mining"]
    and:
        [{"name": "Knowledge graph"}, {"display_name": "Data mining"}]
    """

    clean_concepts: list[str] = []
    seen: set[str] = set()

    for concept in concepts or []:
        name = ""

        if isinstance(concept, str):
            name = concept.strip()

        elif isinstance(concept, dict):
            name = str(
                concept.get("name")
                or concept.get("display_name")
                or concept.get("displayName")
                or ""
            ).strip()

        if name and name.lower() not in seen:
            clean_concepts.append(name)
            seen.add(name.lower())

    return clean_concepts


def normalize_references(references: list[Any] | None) -> list[str]:
    """
    Convert references into a clean unique list of OpenAlex-style paper IDs.

    Supports:
        ["W123", "https://openalex.org/W456"]
    and:
        [{"paperId": "W123"}, {"id": "https://openalex.org/W456"}]
    """

    clean_references: list[str] = []
    seen: set[str] = set()

    for ref in references or []:
        ref_id = ""

        if isinstance(ref, str):
            ref_id = ref

        elif isinstance(ref, dict):
            ref_id = (
                ref.get("paperId")
                or ref.get("id")
                or ref.get("openalex_id")
                or ""
            )

        ref_id = str(ref_id).replace("https://openalex.org/", "").strip()

        if ref_id and ref_id.lower() not in seen:
            clean_references.append(ref_id)
            seen.add(ref_id.lower())

    return clean_references


# ─────────────────────────────────────────
# Neo4j setup
# ─────────────────────────────────────────

def create_constraints(tx) -> None:
    """
    Create uniqueness constraints to avoid duplicate nodes.
    """

    tx.run("""
    CREATE CONSTRAINT paper_id_unique IF NOT EXISTS
    FOR (p:Paper)
    REQUIRE p.paperId IS UNIQUE
    """)

    tx.run("""
    CREATE CONSTRAINT author_id_unique IF NOT EXISTS
    FOR (a:Author)
    REQUIRE a.authorId IS UNIQUE
    """)

    tx.run("""
    CREATE CONSTRAINT concept_name_unique IF NOT EXISTS
    FOR (c:Concept)
    REQUIRE c.name IS UNIQUE
    """)


def clear_neo4j_graph(tx) -> None:
    """
    Delete all Neo4j nodes and relationships.

    Use only when you want a complete graph rebuild from MongoDB.
    """

    tx.run("MATCH (n) DETACH DELETE n")


# ─────────────────────────────────────────
# Graph creation
# ─────────────────────────────────────────

def remove_old_relationships_for_paper(tx, paper_id: str) -> None:
    """
    Remove old relationships for one paper before recreating them.

    This prevents stale graph data when the MongoDB paper record changes.
    """

    tx.run("""
    MATCH (a:Author)-[r:WROTE]->(p:Paper {paperId: $paper_id})
    DELETE r
    """, paper_id=paper_id)

    tx.run("""
    MATCH (p:Paper {paperId: $paper_id})-[r:HAS_TOPIC]->(:Concept)
    DELETE r
    """, paper_id=paper_id)

    tx.run("""
    MATCH (p:Paper {paperId: $paper_id})-[r:REFERENCES]->(:Paper)
    DELETE r
    """, paper_id=paper_id)


def create_graph_for_paper(tx, paper: dict[str, Any]) -> None:
    """
    Create or update one Paper node and its Neo4j relationships.
    """

    paper_id = str(paper.get("paperId", "")).strip()

    if not paper_id:
        return

    title = str(paper.get("title", "") or "")
    abstract = str(paper.get("abstract", "") or "")
    year = paper.get("year")
    cited_by_count = int(paper.get("cited_by_count", 0) or 0)
    contributor = str(paper.get("contributor", "unknown") or "unknown")

    authors = normalize_authors(paper.get("authors", []))
    concepts = normalize_concepts(paper.get("concepts", []))
    references = normalize_references(paper.get("references", []))

    # Remove old relationships first so repeated runs stay clean.
    remove_old_relationships_for_paper(tx, paper_id)

    # Create or update Paper node.
    tx.run(
        """
        MERGE (p:Paper {paperId: $paper_id})
        SET p.title = $title,
            p.year = $year,
            p.abstract = $abstract,
            p.cited_by_count = $cited_by_count,
            p.contributor = $contributor
        """,
        paper_id=paper_id,
        title=title,
        year=year,
        abstract=abstract,
        cited_by_count=cited_by_count,
        contributor=contributor,
    )

    # Create Author nodes and WROTE relationships.
    for author in authors:
        tx.run(
            """
            MERGE (a:Author {authorId: $author_id})
            SET a.name = $author_name
            MERGE (p:Paper {paperId: $paper_id})
            MERGE (a)-[:WROTE]->(p)
            """,
            author_id=author["authorId"],
            author_name=author["name"],
            paper_id=paper_id,
        )

    # Create Concept nodes and HAS_TOPIC relationships.
    for concept in concepts:
        tx.run(
            """
            MERGE (c:Concept {name: $concept_name})
            MERGE (p:Paper {paperId: $paper_id})
            MERGE (p)-[:HAS_TOPIC]->(c)
            """,
            concept_name=concept,
            paper_id=paper_id,
        )

    # Create Paper-to-Paper reference relationships.
    for ref_id in references:
        if ref_id == paper_id:
            continue

        tx.run(
            """
            MERGE (p:Paper {paperId: $paper_id})
            MERGE (ref:Paper {paperId: $ref_id})
            MERGE (p)-[:REFERENCES]->(ref)
            """,
            paper_id=paper_id,
            ref_id=ref_id,
        )


# ─────────────────────────────────────────
# Main execution
# ─────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Neo4j knowledge graph from MongoDB papers."
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete all existing Neo4j graph data before rebuilding.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process only the first N MongoDB papers for testing.",
    )
    args = parser.parse_args()

    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[MONGO_DB]
    papers_collection = db[MONGO_COLLECTION]

    neo4j_driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
    )

    total_papers = papers_collection.count_documents({})
    print(f"Found {total_papers} papers in MongoDB.")

    cursor = papers_collection.find({})
    if args.limit and args.limit > 0:
        cursor = cursor.limit(args.limit)
        print(f"Test mode: processing only {args.limit} papers.")

    processed = 0

    try:
        with neo4j_driver.session() as session:
            if args.clear:
                print("Clearing existing Neo4j graph...")
                session.execute_write(clear_neo4j_graph)

            session.execute_write(create_constraints)

            for paper in cursor:
                session.execute_write(create_graph_for_paper, paper)
                processed += 1

                if processed % 25 == 0:
                    print(f"Processed {processed}/{total_papers} papers...")

        print(f"Neo4j knowledge graph created successfully for {processed} papers.")

    finally:
        mongo_client.close()
        neo4j_driver.close()


if __name__ == "__main__":
    main()
