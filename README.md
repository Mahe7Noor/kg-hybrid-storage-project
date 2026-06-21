# Knowledge Graph with Hybrid Storage

This is a beginner-friendly project that demonstrates how to build a hybrid Research paper search system using:

* MongoDB for structured document storage
* Neo4j for graph relationships
* Elasticsearch for full-text search
* FastAPI for the backend API

The project stores research-paper information in different databases and combines them through one API.

## 1. What this project demonstrates

The project stores document knowledge in three different systems:

| Tool          | Purpose                                                                    |
| ------------- | -------------------------------------------------------------------------- |
| MongoDB       | Stores full paper records, metadata, abstracts, authors, years, and topics |
| Neo4j         | Stores relationships between papers, authors, and topics                   |
| Elasticsearch | Provides fast full-text search over titles, abstracts, and keywords        |
| FastAPI       | Provides API endpoints that connect MongoDB, Neo4j, and Elasticsearch      |

Example hybrid query:

```text
Search: object detection

Elasticsearch finds matching papers.
MongoDB returns full paper details.
Neo4j returns related authors, topics, and connected papers.
```

## 2. Project topic focus

This project is focused on literature review and knowledge graph search for your topics 
[
    "Your topic 1"
    "Your topic 2"....
]
```

These topics are used to collect, store, search, and visualize literature-review papers.

## 3. Requirements

Install these first:

1. Docker Desktop
2. Python 3.11 or newer
3. VS Code, PyCharm, or any code editor
4. Git

## 4. Start the databases

Open Terminal in the main project folder and run:

```bash
docker compose up -d
```

Check running containers:

```bash
docker ps
```

You should see containers similar to:

```text
kg_mongodb
kg_neo4j
kg_elasticsearch
```

## 5. Create Python virtual environment

For macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

For Windows:

```bash
python -m venv venv
venv\Scripts\activate
```

## 6. Install Python packages

```bash
pip install -r requirements.txt
```

## 7. Data output file

Collected paper data is saved inside the `data` folder.

Example:

```python
import os

os.makedirs("data", exist_ok=True)

output_file = "data/your_papers.json"
```

Important: if you see lines like this in your code:

```text
<<<<<<< HEAD
=======
>>>>>>> commit_id
```

These are Git merge-conflict markers. They must be removed before running the code.

Only one output file path should remain, for example:

```python
output_file = "data/your_papers.json"
```
matches your own file name and project structure.

## 8. Start the FastAPI backend

Run this command from the main project folder:

```bash
uvicorn app.main:app --reload
```

Open the backend in the browser:

```text
http://127.0.0.1:8000
```

Open API documentation:

```text
http://127.0.0.1:8000/docs
```

## 9. Check database health

Open this in the browser:

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

## 10. Ingest sample data

Open the Swagger API page:

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

This loads sample documents into:

* MongoDB
* Neo4j
* Elasticsearch

## 11. Try the API endpoints

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
GET /search?q=object detection
```

Browser:

```text
http://127.0.0.1:8000/search?q=object%20detection
```

### Search graph relationships with Neo4j

```text
GET /graph/entity/Object Detection
```

Browser:

```text
http://127.0.0.1:8000/graph/entity/Object%20Detection
```

### Hybrid search

```text
GET /hybrid-search?q=object detection
```

Browser:

```text
http://127.0.0.1:8000/hybrid-search?q=object%20detection
```

The hybrid search combines:

* Elasticsearch search results
* MongoDB paper details
* Neo4j graph relationships

## 12. Open Neo4j browser

Open:

```text
http://localhost:7474
```

Login:

```text
Username: neo4j
Password: password123
```

## 13. Basic Neo4j graph query

Use this query to see the full graph:

```cypher
MATCH (n)-[r]-(m)
RETURN n, r, m
LIMIT 50
```

This should show relationships between papers, authors, and topics.

## 14. Test relationship of a certain topic in Neo4j

### Check if a topic exists

```cypher
MATCH (c:Concept)
WHERE toLower(c.name) CONTAINS toLower("Object Detection")
RETURN c
LIMIT 20;
```

### Show papers connected to one topic

```cypher
MATCH (p:Paper)-[:HAS_TOPIC]->(c:Concept)
WHERE toLower(c.name) CONTAINS toLower("Object Detection")
RETURN p.title AS paper, p.year AS year, c.name AS topic
LIMIT 25;
```

### Show topic, papers, and authors as a graph

```cypher
MATCH (a:Author)-[:WROTE]->(p:Paper)-[:HAS_TOPIC]->(c:Concept)
WHERE toLower(c.name) CONTAINS toLower("Object Detection")
RETURN a, p, c
LIMIT 50;
```

### Show related topics connected through the same papers

```cypher
MATCH (p:Paper)-[:HAS_TOPIC]->(c1:Concept),
      (p)-[:HAS_TOPIC]->(c2:Concept)
WHERE toLower(c1.name) CONTAINS toLower("Object Detection")
  AND c1.name <> c2.name
RETURN c1.name AS searched_topic, c2.name AS related_topic, count(p) AS shared_papers
ORDER BY shared_papers DESC
LIMIT 20;
```

## 15. Open Elasticsearch

Open:

```text
http://localhost:9200
```

You should see JSON information about Elasticsearch.

## 16. Reset demo data

To delete demo data from all three systems:

```text
DELETE /reset-demo
```

Or use curl:

```bash
curl -X DELETE http://127.0.0.1:8000/reset-demo
```

## 17. Suggested demo flow for presentation

1. Show the project architecture.
2. Explain the role of MongoDB, Neo4j, Elasticsearch, and FastAPI.
3. Start Docker containers.
4. Open FastAPI docs.
5. Run `/health`.
6. Run `/ingest-sample`.
7. Run `/documents`.
8. Run `/search?q=object detection`.
9. Run `/graph/entity/Object Detection`.
10. Run `/hybrid-search?q=object detection`.
11. Open Neo4j browser.
12. Run a Cypher query to show topic-paper-author relationships visually.

## 18. Project folder structure

```text
kg-hybrid-storage-project/
│
├── app/
│   ├── __init__.py
│   └── main.py
│
├── data/
│   └── Alekhya_papers.json
│
├── docs/
│   └── PROJECT_EXECUTION_PLAN.md
│
├── ingestion/
│   └── build_neo4j_graph.py
│
├── docker-compose.yml
├── requirements.txt
├── sample_data.json
├── .env.example
└── README.md
```

The exact file names may be different depending on your local setup.

## 19. Troubleshooting

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

Then start again:

```bash
docker compose up -d
```

### Git conflict markers error

If Python shows an error near this:

```text
<<<<<<< HEAD
=======
>>>>>>> commit_id
```

It means a Git merge conflict was not fixed.

Remove those lines and keep only the correct code.

Example fixed version:

```python
import os

os.makedirs("data", exist_ok=True)

output_file = "data/your_papers.json"
```

### Delete all containers and saved database data

Warning: this deletes stored database data.

```bash
docker compose down -v
```

## 20. Final purpose of the project

This project demonstrates how a literature-review system can combine:

* full document storage
* searchable text
* graph-based relationships
* API-based access

The final system helps users search research papers, view paper metadata, and explore relationships between topics, authors, and documents using a knowledge graph.
