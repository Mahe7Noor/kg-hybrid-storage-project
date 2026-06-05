# Project Execution Plan: Knowledge Graph with Hybrid Storage

## Project title

Knowledge Graph with Hybrid Storage using MongoDB, Neo4j, and Elasticsearch

## Objective

The goal of this project is to build a hybrid knowledge graph system that stores documents, models relationships, and supports full-text search.

The system uses:

- MongoDB to store structured and semi-structured document records.
- Neo4j to model relationships between entities.
- Elasticsearch to index and search document text.
- FastAPI to provide an API layer that combines all three systems.

## System architecture

```text
Sample Documents
      |
      v
FastAPI Ingestion API
      |
      +------------------> MongoDB
      |                    Stores full document records
      |
      +------------------> Neo4j
      |                    Stores graph nodes and relationships
      |
      +------------------> Elasticsearch
                           Stores searchable text index

User Query
      |
      v
FastAPI Hybrid Search
      |
      +--> Elasticsearch finds matching documents
      +--> MongoDB returns full document details
      +--> Neo4j returns related entities
      |
      v
Combined Result
```

## Data model

### MongoDB

MongoDB stores full document records.

Example:

```json
{
  "document_id": "doc_001",
  "title": "AI in Healthcare",
  "author": "Dr. Smith",
  "organization": "Health AI Lab",
  "topic": "Artificial Intelligence",
  "content": "Machine learning and artificial intelligence are used in medical diagnosis.",
  "published_date": "2025-01-10",
  "keywords": ["AI", "machine learning", "healthcare"]
}
```

### Neo4j

Neo4j stores entities and relationships.

Node labels:

- Person
- Document
- Organization
- Topic

Relationship types:

```text
(Person)-[:AUTHORED]->(Document)
(Person)-[:AFFILIATED_WITH]->(Organization)
(Document)-[:MENTIONS]->(Topic)
(Organization)-[:WORKS_ON]->(Topic)
```

### Elasticsearch

Elasticsearch indexes searchable fields:

- title
- content
- keywords
- topic

## Main API endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | API home |
| `/health` | GET | Check MongoDB, Neo4j, and Elasticsearch |
| `/ingest-sample` | POST | Load sample data into all databases |
| `/documents` | GET | List documents from MongoDB |
| `/documents/{document_id}` | GET | Get one document from MongoDB |
| `/documents` | POST | Add one new document |
| `/search?q=` | GET | Search text using Elasticsearch |
| `/graph/entity/{entity_name}` | GET | Show graph relationships from Neo4j |
| `/hybrid-search?q=` | GET | Combine Elasticsearch + MongoDB + Neo4j |
| `/reset-demo` | DELETE | Delete demo data |

## Execution steps

### Step 1: Install software

Install:

- Docker Desktop
- Python 3.11+
- VS Code

### Step 2: Start databases

Run:

```bash
docker compose up -d
```

### Step 3: Start backend

Run:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Step 4: Load data

Open:

```text
http://127.0.0.1:8000/docs
```

Run:

```text
POST /ingest-sample
```

### Step 5: Demonstrate search

Run:

```text
GET /search?q=machine learning
```

This shows text search results from Elasticsearch.

### Step 6: Demonstrate graph

Run:

```text
GET /graph/entity/Dr. Smith
```

This shows relationships from Neo4j.

### Step 7: Demonstrate hybrid query

Run:

```text
GET /hybrid-search?q=machine learning
```

This combines:

- Elasticsearch search result
- MongoDB document details
- Neo4j graph context

## Demonstration use cases

### Use case 1: Text search

Question:

```text
Find documents about machine learning.
```

System behavior:

- Elasticsearch searches title, content, keywords, and topic.
- The API returns relevant documents.

### Use case 2: Entity relationship search

Question:

```text
Show all relationships of Dr. Smith.
```

System behavior:

- Neo4j finds documents authored by Dr. Smith.
- Neo4j finds Dr. Smith's organization.
- Neo4j returns connected topics.

### Use case 3: Hybrid graph + text query

Question:

```text
Find documents about machine learning and show authors and organizations.
```

System behavior:

- Elasticsearch finds matching documents.
- MongoDB returns full records.
- Neo4j returns authors, topics, and organizations.

## Success criteria

The project is successful if:

1. MongoDB stores full document data.
2. Neo4j shows entity relationships visually.
3. Elasticsearch searches document text.
4. FastAPI returns results from all three systems.
5. Hybrid search returns documents with graph context.

## Future improvements

Possible improvements:

- Add automatic entity extraction using NLP.
- Add frontend graph visualization using React and Cytoscape.js.
- Add user authentication.
- Add PDF upload and indexing.
- Add duplicate entity detection.
- Add recommendation endpoint based on graph similarity.
