See Video: https://drive.google.com/file/d/1I4nyw7RPsdz2xGRw5rJ-A89GQfuVIqrn/view?usp=share_link


# Knowledge Graph with Hybrid Storage

A beginner-friendly research-paper search and visualization project built using:

* **MongoDB** for structured document storage
* **Neo4j** for graph relationships
* **Elasticsearch** for full-text search
* **FastAPI** for the backend API
* **HTML, CSS, JavaScript, and Cytoscape.js** for the frontend knowledge graph
* **OpenAlex API** for collecting research papers

The system stores research-paper information in different databases and combines the results through one backend API.

---

# 1. What This Project Demonstrates

This project demonstrates how multiple storage technologies can work together in one literature-review system.

| Tool          | Purpose                                                                                                        |
| ------------- | -------------------------------------------------------------------------------------------------------------- |
| MongoDB       | Stores complete paper records, titles, abstracts, authors, publication years, topics, references, and metadata |
| Neo4j         | Stores relationships between papers, authors, concepts, references, contributors, and search topics            |
| Elasticsearch | Provides fast full-text search over paper titles, abstracts, concepts, and keywords                            |
| FastAPI       | Connects MongoDB, Neo4j, Elasticsearch, OpenAlex, and the frontend                                             |
| Cytoscape.js  | Displays the interactive visual knowledge graph                                                                |
| OpenAlex      | Downloads new research-paper records when a topic is added                                                     |

## Example Hybrid Search

Search:

```text
object detection
```

The system performs the following workflow:

```text
Elasticsearch
    ↓
Find matching stored papers
    ↓
MongoDB
    ↓
Return complete paper details
    ↓
Neo4j
    ↓
Return authors, concepts, citations, related papers, and search topics
    ↓
Frontend
    ↓
Display results and the visual knowledge graph
```

---

# 2. Project Topic Focus

This project is focused on literature-review search and knowledge-graph exploration for selected research topics.

Example topics:

```text
Computer Vision
Artificial Intelligence
Machine Learning
Deep Learning
Object Detection
Image Processing
```

You may replace these with your own topics.

These topics are used to:

* collect research papers,
* store paper metadata,
* search titles and abstracts,
* create graph relationships,
* discover related papers,
* compare contributor collections,
* visualize literature connections.

---

# 3. Main System Features

The project supports:

* full-text paper search,
* paper metadata storage,
* topic-based paper collection,
* author-paper relationships,
* paper-concept relationships,
* citation relationships,
* automatically generated related-paper relationships,
* contributor filtering,
* frontend graph search,
* live graph expansion from Neo4j,
* graph layout controls,
* graph relationship filters,
* paper details and OpenAlex links.

---

# 4. System Architecture

```text
                    OpenAlex API
                         |
                         v
                  Add Topic Endpoint
                         |
                         v
        +--------------------------------+
        |        FastAPI Backend         |
        +--------------------------------+
          |              |             |
          v              v             v
      MongoDB       Elasticsearch     Neo4j
      Documents      Text Search      Graph
          |              |             |
          +--------------+-------------+
                         |
                         v
                Frontend Application
                         |
                         v
                Cytoscape Knowledge Graph
```

---

# 5. Search and Add Topic Difference

## Normal Search

The normal search only searches papers already stored in the system.

```text
Search box
    ↓
Elasticsearch
    ↓
MongoDB
    ↓
Neo4j
    ↓
Frontend results
```

It does not download new papers from OpenAlex.

## Add Topic

The Add Topic feature downloads new papers from OpenAlex and stores them in all three databases.

```text
OpenAlex
    ↓
Download papers
    ↓
MongoDB
    ↓
Elasticsearch
    ↓
Neo4j
    ↓
Build relationships
```

After the papers are imported, they become searchable through the normal search bar.

---

# 6. Knowledge Graph Relationships

The Neo4j graph uses the following main relationships.

## Author to Paper

```text
Author -[:WROTE]-> Paper
```

Shows which author wrote a paper.

## Paper to Concept

```text
Paper -[:HAS_TOPIC]-> Concept
```

Shows the research concepts associated with a paper.

## Paper to Referenced Paper

```text
Paper -[:REFERENCES]-> Paper
```

Shows citation relationships between papers.

## Paper to Related Paper

```text
Paper -[:RELATED_TO]-> Paper
```

Shows papers that are similar based on:

* shared concepts,
* shared authors,
* direct citations,
* similarity score.

## Paper to Search Topic

```text
Paper -[:ADDED_UNDER]-> SearchTopic
```

Shows which search topic was used when the paper was imported.

---

# 7. Build Related Papers Script

The Build Related Papers script analyzes papers already stored in Neo4j and creates `RELATED_TO` relationships.

It compares papers using information such as:

* shared concepts,
* shared authors,
* direct citation connections,
* calculated similarity scores.

Example:

```text
Paper A -[:RELATED_TO]-> Paper B
```

The relationship may store properties such as:

```text
score
sharedConcepts
sharedAuthors
directReference
reason
```

## Why It Is Important

Without the script, the graph mainly shows direct relationships such as:

```text
Author → Paper
Paper → Concept
Paper → Reference
```

After the script runs, the graph can also show similar papers that may not directly cite each other.

This makes the frontend behave more like a related-paper discovery system.

```text
Paper A
   |
   | RELATED_TO
   |
Paper B
```

The Build Related Papers script therefore helps the frontend:

* recommend similar papers,
* create paper-to-paper clusters,
* discover research beyond exact keyword matches,
* expand the visual graph,
* explain why two papers are connected.

---

# 8. Requirements

Install the following software first:

1. Docker Desktop
2. Python 3.11 or newer
3. Git
4. VS Code, PyCharm, or another code editor

Python 3.13 may also work, but Python 3.11 or 3.12 is generally recommended for better package compatibility.

---

# 9. Start the Databases

Open Terminal in the main project folder.

```bash
cd /Users/mahenoor/PycharmProjects/kg-hybrid-storage-project
```

Start the Docker containers:

```bash
docker compose up -d
```

Check the running containers:

```bash
docker ps
```

You should see containers similar to:

```text
kg_mongodb
kg_neo4j
kg_elasticsearch
```

---

# 10. Create a Python Virtual Environment

## macOS or Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

## Windows

```bash
python -m venv venv
venv\Scripts\activate
```

---

# 11. Install Python Packages

Run:

```bash
pip install -r requirements.txt
```

---

# 12. Data Output Files

Collected paper data is saved in the `data` folder.

Example:

```python
import os

os.makedirs("data", exist_ok=True)

output_file = "data/your_papers.json"
```

The exact filename may be different in your project.

Example:

```text
data/Alekhya_papers.json
```

## Git Merge Conflict Warning

If you see code like this:

```text
<<<<<<< HEAD
=======
>>>>>>> commit_id
```

these are Git merge-conflict markers.

They must be removed before running the project.

Keep only the correct code.

Example:

```python
import os

os.makedirs("data", exist_ok=True)

output_file = "data/your_papers.json"
```

---

# 13. Start the FastAPI Backend

Run the command from the project root folder.

For the current backend structure:

```bash
uvicorn app.backend.main:app --reload --port 8000
```

The project can then be opened at:

```text
http://127.0.0.1:8000
```

Open the API documentation at:

```text
http://127.0.0.1:8000/docs
```

If your backend file is stored directly as `app/main.py`, use:

```bash
uvicorn app.main:app --reload --port 8000
```

Use the command that matches your actual folder structure.

---

# 14. Check Database Health

Open:

```text
http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "mongodb": true,
  "neo4j": true,
  "elasticsearch": true
}
```

If one value is `false`, check the corresponding Docker container.

---

# 15. Ingest Sample Data

Open Swagger:

```text
http://127.0.0.1:8000/docs
```

Run:

```text
POST /ingest-sample
```

Or use:

```bash
curl -X POST http://127.0.0.1:8000/ingest-sample
```

This loads sample data into:

* MongoDB,
* Elasticsearch,
* Neo4j.

---

# 16. Main API Endpoints

The exact endpoint names may differ slightly depending on the current backend version.

## Health Check

```text
GET /health
```

## List Documents

```text
GET /documents
```

Example:

```text
http://127.0.0.1:8000/documents
```

## Full-Text Search

```text
GET /api/search?q=computer vision
```

or, in an older backend version:

```text
GET /search?q=computer vision
```

Example:

```text
http://127.0.0.1:8000/api/search?q=computer%20vision
```

The search uses Elasticsearch to find matching stored papers.

## Add a Topic

```text
POST /api/add-topic
```

This endpoint:

1. searches OpenAlex,
2. downloads papers,
3. stores the papers in MongoDB,
4. indexes the papers in Elasticsearch,
5. creates graph nodes and relationships in Neo4j.

## Keyword Knowledge Graph

```text
GET /api/keyword-graph
```

This endpoint returns graph data for the frontend, including:

* papers,
* authors,
* concepts,
* references,
* related papers,
* search topics.

## Expand a Graph Node

```text
GET /api/graph-expand
```

This endpoint retrieves additional Neo4j neighbours for a selected graph node.

It supports expansion from:

* Paper nodes,
* Author nodes,
* Concept nodes,
* SearchTopic nodes.

## Rebuild Related Papers

```text
POST /api/rebuild-related
```

This endpoint rebuilds `RELATED_TO` connections between stored papers.

## Hybrid Search

An older version of the backend may also provide:

```text
GET /hybrid-search?q=object detection
```

This combines:

* Elasticsearch search results,
* MongoDB paper details,
* Neo4j graph relationships.

---

# 17. Open the Frontend

Depending on the project structure, the frontend may be served automatically by FastAPI.

Open:

```text
http://127.0.0.1:8000
```

The frontend provides:

* a main paper-search bar,
* contributor filters,
* search results,
* a visual knowledge graph,
* graph relationship toggles,
* graph layout controls,
* graph expansion,
* paper details.

---

# 18. How to Use the Main Search

Enter a topic such as:

```text
computer vision
```

The main search:

1. searches Elasticsearch,
2. finds stored matching papers,
3. retrieves full paper details from MongoDB,
4. retrieves graph connections from Neo4j,
5. displays the results in the frontend.

The main search searches the stored database.

It does not automatically search OpenAlex.

To download new papers, use Add Topic.

---

# 19. How to Use the Keyword Knowledge Graph

After searching for a topic, the visual graph is displayed.

## Click a Node

Click a node to view its details.

Possible node types include:

* Paper,
* Author,
* Concept,
* SearchTopic.

## Double-Click a Node

Double-click a node to expand it from Neo4j.

The frontend calls:

```text
/api/graph-expand
```

The returned nodes and relationships are added to the existing graph.

## Paper Expansion

Expanding a paper can load:

* authors,
* concepts,
* references,
* related papers,
* search topics.

## Author Expansion

Expanding an author can load additional papers written by that author.

## Concept Expansion

Expanding a concept can load more papers connected to that concept.

## SearchTopic Expansion

Expanding a search topic can load papers imported under that topic.

---

# 20. Graph Search Bar

The search bar inside the knowledge graph is different from the main search bar.

It searches only the nodes already loaded in the frontend graph.

It can locate:

* paper titles,
* author names,
* concept names,
* search-topic names.

Example:

```text
transformer
```

The graph search may highlight a loaded paper or concept containing that word.

It does not search:

* the full MongoDB collection,
* the full Elasticsearch index,
* the full Neo4j database,
* OpenAlex,
* the internet.

To load more graph data, use node expansion.

---

# 21. Contributor Filter

The contributor dropdown filters papers by collection ownership.

Available options may include:

## All

Shows papers from all contributors.

## Me

Shows papers associated with your collection.

## Teammate

Shows papers associated with your teammate's collection.

## Shared

Shows papers that belong to both collections.

The contributor filter mainly controls the starting paper set.

Connected authors and concepts may still appear because they provide graph context.

---

# 22. Strict Contributor Filter

The Strict Contributor checkbox controls graph expansion.

## Strict Contributor Disabled

Expanding one of your papers may reveal:

* your papers,
* teammate papers,
* shared papers,
* connected authors,
* connected concepts,
* connected references.

This is useful for discovering cross-contributor relationships.

## Strict Contributor Enabled

Expansion is limited to papers matching the selected contributor.

For example, when `Me` is selected, teammate-only papers are excluded.

This is useful when you want a clean contributor-specific graph.

---

# 23. Relationship Filters

The graph includes relationship toggles.

## WROTE

```text
Author -[:WROTE]-> Paper
```

Shows which authors wrote which papers.

## HAS_TOPIC

```text
Paper -[:HAS_TOPIC]-> Concept
```

Shows the concepts associated with each paper.

## REFERENCES

```text
Paper -[:REFERENCES]-> Paper
```

Shows citation relationships.

## RELATED_TO

```text
Paper -[:RELATED_TO]-> Paper
```

Shows similar papers created by the Build Related Papers process.

This is especially useful for discovering related work beyond exact keyword matches.

## ADDED_UNDER

```text
Paper -[:ADDED_UNDER]-> SearchTopic
```

Shows which topic was used when importing a paper.

Turning a relationship filter off hides that relationship type from the current graph view.

It does not delete anything from Neo4j.

---

# 24. Graph Layouts

The layout menu changes only the visual arrangement.

## Connected

Best general layout for exploring connected papers.

## Concentric

Places important or selected nodes near the center.

## Hierarchy

Shows directional graph structure.

Useful for:

```text
Author → Paper → Concept
```

## Circle

Places all nodes around a circle.

## Grid

Places nodes in rows and columns.

Changing the layout does not change database results.

---

# 25. Graph Control Buttons

## Focus Selected

Emphasizes the selected node and its immediate neighbours.

## Hide Selected

Temporarily hides a selected node or relationship.

It does not delete data.

## Restore Hidden

Restores nodes or edges hidden in the frontend.

## Fit

Fits the entire graph into the visible area.

## Reset

Restores the graph view or reloads the initial graph state, depending on the frontend implementation.

## Expand from Neo4j

Queries the backend and loads additional connected graph data.

---

# 26. Does the Graph Only Search Keywords?

No.

The initial graph begins with papers found through the main keyword search, but the graph can also show related information from other stored papers.

It can display:

```text
Keyword-matching papers
+
authors
+
concepts
+
citations
+
similar papers
+
papers connected through shared authors
+
papers connected through shared concepts
+
search topics
```

A related paper does not need to contain the exact original keyword.

For example, a search for:

```text
computer vision
```

may reveal another paper through:

* a shared `Object Detection` concept,
* a shared author,
* a direct citation,
* a `RELATED_TO` similarity connection.

However, the paper must already be stored in the project databases.

---

# 27. Open Neo4j Browser

Open:

```text
http://localhost:7474
```

Login:

```text
Username: neo4j
Password: password123
```

---

# 28. Basic Neo4j Queries

## Show the Full Graph

```cypher
MATCH (n)-[r]-(m)
RETURN n, r, m
LIMIT 50;
```

## Check Whether a Concept Exists

```cypher
MATCH (c:Concept)
WHERE toLower(c.name) CONTAINS toLower("Object Detection")
RETURN c
LIMIT 20;
```

## Show Papers Connected to a Concept

```cypher
MATCH (p:Paper)-[:HAS_TOPIC]->(c:Concept)
WHERE toLower(c.name) CONTAINS toLower("Object Detection")
RETURN p.title AS paper, p.year AS year, c.name AS topic
LIMIT 25;
```

## Show Topic, Papers, and Authors

```cypher
MATCH (a:Author)-[:WROTE]->(p:Paper)-[:HAS_TOPIC]->(c:Concept)
WHERE toLower(c.name) CONTAINS toLower("Object Detection")
RETURN a, p, c
LIMIT 50;
```

## Show Related Concepts Through Shared Papers

```cypher
MATCH (p:Paper)-[:HAS_TOPIC]->(c1:Concept),
      (p)-[:HAS_TOPIC]->(c2:Concept)
WHERE toLower(c1.name) CONTAINS toLower("Object Detection")
  AND c1.name <> c2.name
RETURN
    c1.name AS searched_topic,
    c2.name AS related_topic,
    count(p) AS shared_papers
ORDER BY shared_papers DESC
LIMIT 20;
```

## Show Related Papers

```cypher
MATCH (p1:Paper)-[r:RELATED_TO]->(p2:Paper)
RETURN
    p1.title AS source_paper,
    p2.title AS related_paper,
    r.score AS similarity_score,
    r.sharedConcepts AS shared_concepts,
    r.sharedAuthors AS shared_authors
ORDER BY r.score DESC
LIMIT 25;
```

## Show the Related-Paper Graph

```cypher
MATCH (p1:Paper)-[r:RELATED_TO]-(p2:Paper)
RETURN p1, r, p2
LIMIT 50;
```

## Show Papers Imported Under a Topic

```cypher
MATCH (p:Paper)-[:ADDED_UNDER]->(s:SearchTopic)
WHERE toLower(s.name) CONTAINS toLower("Computer Vision")
RETURN p, s
LIMIT 50;
```

---

# 29. Open Elasticsearch

Open:

```text
http://localhost:9200
```

You should see JSON information confirming that Elasticsearch is running.

---

# 30. Reset Demo Data

To remove demo data from all three systems:

```text
DELETE /reset-demo
```

Or use:

```bash
curl -X DELETE http://127.0.0.1:8000/reset-demo
```

The endpoint name may differ in the latest backend version.

Check:

```text
http://127.0.0.1:8000/docs
```

before running it.

---

# 31. Suggested Testing Flow

Use the following sequence to test the complete project.

## Step 1: Start Docker

```bash
docker compose up -d
```

## Step 2: Start FastAPI

```bash
uvicorn app.backend.main:app --reload --port 8000
```

## Step 3: Open the Frontend

```text
http://127.0.0.1:8000
```

## Step 4: Search for a Topic

```text
computer vision
```

## Step 5: Test Contributor Filters

Try:

* All,
* Me,
* Teammate,
* Shared.

## Step 6: Test Graph Nodes

Click:

* a Paper node,
* an Author node,
* a Concept node,
* a SearchTopic node.

## Step 7: Test Relationship Filters

Turn the following relationships on and off:

* WROTE,
* HAS_TOPIC,
* REFERENCES,
* RELATED_TO,
* ADDED_UNDER.

## Step 8: Test Graph Expansion

Double-click a Paper node or use:

```text
Expand from Neo4j
```

Confirm that the node count increases.

## Step 9: Test Strict Contributor Mode

Enable Strict Contributor and expand another node.

Confirm that unrelated contributor-only papers are excluded.

## Step 10: Test Graph Search

Search for a loaded:

* paper title,
* author name,
* concept,
* topic.

## Step 11: Test Layouts

Try:

* Connected,
* Concentric,
* Hierarchy,
* Circle,
* Grid.

## Step 12: Test Paper Details

Click a paper and verify that metadata and the OpenAlex link appear correctly.

## Step 13: Test Add Topic

Add a new topic and confirm that new papers become available in later searches.

## Step 14: Rebuild Related Papers

Run:

```text
POST /api/rebuild-related
```

Then search again and verify that `RELATED_TO` edges appear.

---

# 32. Suggested Presentation Flow

For a project demonstration:

1. Explain the hybrid architecture.
2. Explain the role of MongoDB, Elasticsearch, Neo4j, and FastAPI.
3. Start the Docker containers.
4. Open FastAPI Swagger documentation.
5. Run `/health`.
6. Search for `computer vision`.
7. Show the returned paper metadata.
8. Open the visual knowledge graph.
9. Explain Paper, Author, Concept, and SearchTopic nodes.
10. Turn relationship filters on and off.
11. Expand a paper from Neo4j.
12. Explain `RELATED_TO` links.
13. Show contributor filtering.
14. Open Neo4j Browser.
15. Run a Cypher query.
16. Explain how the frontend differs from a simple keyword-search system.

---

# 33. Project Folder Structure

A typical project structure is:

```text
kg-hybrid-storage-project/
│
├── app/
│   ├── __init__.py
│   ├── backend/
│   │   ├── __init__.py
│   │   └── main.py
│   └── frontend/
│       ├── index.html
│       ├── styles.css
│       └── script.js
│
├── data/
│   ├── Alekhya_papers.json
│   └── other_topic_papers.json
│
├── ingestion/
│   ├── fetch_papers.py
│   ├── load_to_db.py
│   ├── build_neo4j_graph.py
│   └── build_related_papers.py
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

The exact file names may differ depending on the current local version.

---

# 34. Troubleshooting

## Elasticsearch Is Not Starting

Docker may need more memory.

Open:

```text
Docker Desktop
→ Settings
→ Resources
→ Memory
```

Set at least 4 GB.

Then restart:

```bash
docker compose down
docker compose up -d
```

## Neo4j Login Is Not Working

Use:

```text
Username: neo4j
Password: password123
```

Check `docker-compose.yml` if the credentials were changed.

## Port 8000 Is Already in Use

Run FastAPI on another port:

```bash
uvicorn app.backend.main:app --reload --port 8001
```

Then open:

```text
http://127.0.0.1:8001
```

## Docker Port Is Already in Use

Stop previous containers:

```bash
docker compose down
```

Then start again:

```bash
docker compose up -d
```

## Git Conflict Marker Error

Remove lines such as:

```text
<<<<<<< HEAD
=======
>>>>>>> commit_id
```

Keep only the correct code.

## No Search Results

Check that:

* papers were imported,
* MongoDB contains paper records,
* Elasticsearch contains indexed documents,
* the query matches searchable fields,
* the backend is connected to Elasticsearch.

## Graph Is Empty

Check that:

* Neo4j contains nodes,
* paper IDs match across databases,
* graph relationships were created,
* the keyword graph endpoint returns nodes and edges.

## RELATED_TO Edges Are Missing

Run the related-paper rebuild endpoint or script.

Example:

```text
POST /api/rebuild-related
```

Then verify in Neo4j:

```cypher
MATCH (p1:Paper)-[r:RELATED_TO]->(p2:Paper)
RETURN p1, r, p2
LIMIT 25;
```

## Expansion Does Not Work

Check that:

* `/api/graph-expand` is available,
* the frontend sends the correct node ID,
* the node type is correct,
* the backend returns `nodes` and `edges`,
* the frontend merges returned graph elements into Cytoscape.

## Delete All Containers and Saved Database Data

Warning: this permanently deletes stored Docker database volumes.

```bash
docker compose down -v
```

Start again:

```bash
docker compose up -d
```

---

# 35. Old System vs Latest System

## Older Version

```text
Search
    ↓
Fixed graph result
```

The graph was generated once and could not query Neo4j again after loading.

## Latest Version

```text
Search
    ↓
Initial graph
    ↓
Select or double-click a node
    ↓
Live Neo4j expansion
    ↓
New nodes and relationships added
```

The latest system supports:

* dynamic graph exploration,
* contributor-aware expansion,
* strict contributor filtering,
* `RELATED_TO` explanations,
* paper, author, concept, and topic expansion,
* richer frontend controls.

The main difference is:

```text
Old system
=
Search + fixed graph

Latest system
=
Search + dynamic graph exploration
```

---

# 36. Final Purpose of the Project

This project demonstrates how a literature-review system can combine:

* complete document storage,
* fast full-text search,
* graph-based relationships,
* related-paper discovery,
* contributor-based filtering,
* API-based data access,
* interactive knowledge-graph visualization.

The final system helps users:

* search research papers,
* inspect paper metadata,
* discover authors and concepts,
* explore citations,
* identify similar papers,
* expand graph relationships dynamically,
* understand how research papers are connected.

The project is not only a keyword-search engine.

It is a hybrid research-paper discovery system that combines:

```text
Search
+
Document storage
+
Knowledge graphs
+
Related-paper analysis
+
Interactive visualization
```
