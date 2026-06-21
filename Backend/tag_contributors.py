"""
One-time helper: tags every paper in MongoDB and Elasticsearch with a
'contributor' field so the frontend can filter "my papers" vs "teammate's papers".

Run this AFTER merging and loading the combined dataset, once both of you
know which paperIds came from which source file.

Usage:
    python ingestion/tag_contributors.py
"""

import json
from pymongo import MongoClient
from elasticsearch import Elasticsearch

mongo = MongoClient("mongodb://localhost:27017")
db = mongo["literature_review"]

es = Elasticsearch("http://localhost:9200", request_timeout=60)

# Load the two original source files to know who fetched what
with open("data/Alekhya_papers.json", encoding="utf-8") as f:
    my_ids = {p["paperId"] for p in json.load(f)}

with open("data/Mahenoor_papers.json", encoding="utf-8") as f:
    teammate_ids = {p["paperId"] for p in json.load(f)}

print(f"My papers: {len(my_ids)}")
print(f"Teammate papers: {len(teammate_ids)}")

updated_mongo = 0
updated_es = 0

for paper_id in my_ids:
    db.papers.update_one({"paperId": paper_id}, {"$set": {"contributor": "me"}})
    es.update(index="papers", id=paper_id, doc={"contributor": "me"}, ignore=[404])
    updated_mongo += 1
    updated_es += 1

for paper_id in teammate_ids:
    # if a paper appears in both (shared topic overlap), mark it "both"
    contributor = "both" if paper_id in my_ids else "teammate"
    db.papers.update_one({"paperId": paper_id}, {"$set": {"contributor": contributor}})
    es.update(index="papers", id=paper_id, doc={"contributor": contributor}, ignore=[404])
    updated_mongo += 1
    updated_es += 1

es.indices.refresh(index="papers")

print(f"Tagged {updated_mongo} papers in MongoDB")
print(f"Tagged {updated_es} papers in Elasticsearch")
print("Done. Papers now have a 'contributor' field: 'me', 'teammate', or 'both'")