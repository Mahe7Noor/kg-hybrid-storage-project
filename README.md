# Knowledge Graph with Hybrid Storage

This is a beginner-friendly project using:

- MongoDB for structured document storage
- Neo4j for graph relationships
- Elasticsearch for full-text search
- FastAPI for the backend API

## 1. What this project demonstrates

The project stores the same document knowledge in three different systems:

| Tool | Purpose |
|---|---|
| MongoDB | Full document records and metadata |
| Neo4j | Entity relationships |
| Elasticsearch | Searchable text index |
| FastAPI | API layer that combines all three |

Example hybrid query:

```text
Search: machine learning

Elasticsearch finds matching documents.
MongoDB returns full document details.
Neo4j returns related authors, topics, and organizations.
```

## 2. Requirements

Install these first:

1. Docker Desktop
2. Python 3.11 or newer
3. VS Code or any code editor

## 3. Start the databases

Open Terminal in this project folder and run:

```bash
docker compose up -d
```

Check containers:

```bash
docker ps
```

You should see:

```text
kg_mongodb
kg_neo4j
kg_elasticsearch
```

## 4. Create Python virtual environment

macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

## 5. Install Python packages

```bash
pip install -r requirements.txt
```

## 6. Start the FastAPI backend

```bash
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Open API docs:

```text
http://127.0.0.1:8000/docs
```

## 7. Check database health

In the browser, open:

```text
http://127.0.0.1:8000/health
```

Expected result:

```json
{
  "mongodb": true,
  "neo4j": true,
  "elasticsearch": true
}
```

## 8. Ingest sample data

Use the Swagger API page:

```text
http://127.0.0.1:8000/docs
```

Run:

```text
POST /ingest-sample
```

Or use curl:

```bash
curl -X POST http://127.0.0.1:8000/ingest-sample
```

This loads the sample documents into:

- MongoDB
- Neo4j
- Elasticsearch

## 9. Try the APIs

### List documents from MongoDB

```text
GET /documents
```

Browser:

```text
http://127.0.0.1:8000/documents
```

### Search text with Elasticsearch

```text
GET /search?q=machine learning
```

Browser:

```text
http://127.0.0.1:8000/search?q=machine%20learning
```

### Search graph relationships with Neo4j

```text
GET /graph/entity/Dr. Smith
```

Browser:

```text
http://127.0.0.1:8000/graph/entity/Dr.%20Smith
```

### Hybrid search

```text
GET /hybrid-search?q=machine learning
```

Browser:

```text
http://127.0.0.1:8000/hybrid-search?q=machine%20learning
```

## 10. Open Neo4j browser

Open:

```text
http://localhost:7474
```

Login:

```text
Username: neo4j
Password: password123
```

Try this Cypher query:

```cypher
MATCH (n)-[r]-(m)
RETURN n, r, m
LIMIT 50
```

You should see a graph of people, documents, organizations, and topics.

## 11. Open Elasticsearch

Open:

```text
http://localhost:9200
```

You should see JSON information about Elasticsearch.

## 12. Reset demo data

To delete demo data from all three systems:

```text
DELETE /reset-demo
```

Or:

```bash
curl -X DELETE http://127.0.0.1:8000/reset-demo
```

## 13. Suggested demo flow for presentation

1. Show architecture diagram from `docs/PROJECT_EXECUTION_PLAN.md`.
2. Start Docker containers.
3. Open FastAPI docs.
4. Run `/health`.
5. Run `/ingest-sample`.
6. Run `/documents`.
7. Run `/search?q=machine learning`.
8. Run `/graph/entity/Dr. Smith`.
9. Run `/hybrid-search?q=machine learning`.
10. Open Neo4j browser and show graph visually.

## 14. Project folder structure

```text
kg-hybrid-storage-project/
│
├── app/
│   ├── __init__.py
│   └── main.py
│
├── docs/
│   └── PROJECT_EXECUTION_PLAN.md
│
├── docker-compose.yml
├── requirements.txt
├── sample_data.json
├── .env.example
└── README.md
```

## 15. Troubleshooting

### Elasticsearch not starting

Docker may need more memory.

Open Docker Desktop:

```text
Settings → Resources → Memory
```

Set at least 4 GB.

Then run:

```bash
docker compose down
docker compose up -d
```

### Neo4j login not working

Use:

```text
Username: neo4j
Password: password123
```

### Port already in use

Run:

```bash
docker compose down
docker compose up -d
```

### Delete all containers and saved database data

Warning: this deletes stored data.

```bash
docker compose down -v
```
