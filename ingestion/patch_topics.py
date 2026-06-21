"""
patch_topics.py
Reads search_topic from Alekhya_papers.json and updates MongoDB + Elasticsearch directly.
Fixes the case where load_to_db.py ran before the topic patch was applied.
"""

from pymongo import MongoClient
from elasticsearch import Elasticsearch
import json

mongo = MongoClient("mongodb://localhost:27017")
db    = mongo["literature_review"]
es    = Elasticsearch("http://localhost:9200", request_timeout=60)

# Load your JSON file — this has the correct search_topic on every paper
with open("data/Alekhya_papers.json", encoding="utf-8") as f:
    papers = json.load(f)

print(f"Loaded {len(papers)} papers from JSON")

# Check what topics exist in the JSON
topics = {}
for p in papers:
    t = p.get("search_topic", "MISSING")
    topics[t] = topics.get(t, 0) + 1

print("\nTopics in your JSON file:")
for t, c in sorted(topics.items(), key=lambda x: -x[1]):
    print(f"  {c:3d}  {t}")

# Patch MongoDB and Elasticsearch for each paper
print("\nPatching databases...")
updated = 0
skipped = 0

for paper in papers:
    pid   = paper.get("paperId")
    topic = paper.get("search_topic", "")

    if not pid or not topic or topic == "MISSING":
        skipped += 1
        continue

    # Update MongoDB
    db.papers.update_one(
        {"paperId": pid},
        {"$set": {"search_topic": topic}}
    )

    # Update Elasticsearch
    try:
        es.update(
            index="papers",
            id=pid,
            body={"doc": {"search_topic": topic}}
        )
    except Exception:
        pass  # paper might not be in ES index, that's ok

    updated += 1

es.indices.refresh(index="papers")

print(f"Updated: {updated} papers")
print(f"Skipped: {skipped} papers (no topic in JSON)")

# Verify
valid = db.papers.count_documents({
    "search_topic": {"$exists": True, "$nin": [None, "", "MISSING"]}
})
print(f"\nMongoDB papers with valid search_topic now: {valid}")
print("\nDone — refresh your browser, all topic chips should appear now.")