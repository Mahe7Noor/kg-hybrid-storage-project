from pymongo import MongoClient

db = MongoClient("mongodb://localhost:27017")["literature_review"]

total = db.papers.count_documents({})
contributor_me = db.papers.count_documents({"contributor": "me"})
has_topic = db.papers.count_documents({
    "search_topic": {"$exists": True, "$nin": [None, "", "MISSING"]}
})
both = db.papers.count_documents({
    "contributor": "me",
    "search_topic": {"$exists": True, "$nin": [None, "", "MISSING"]}
})

print(f"Total papers:              {total}")
print(f"contributor = me:          {contributor_me}")
print(f"valid search_topic:        {has_topic}")
print(f"me AND valid search_topic: {both}")

# Show a sample of what's actually in the DB
print("\nSample of 5 papers:")
for p in db.papers.find({}, {"title": 1, "contributor": 1, "search_topic": 1, "_id": 0}).limit(5):
    print(f"  contributor={p.get('contributor','?')}  topic={p.get('search_topic','?')}  title={p.get('title','?')[:50]}")