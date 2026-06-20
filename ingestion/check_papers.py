import json


with open("data/your_papers.json", encoding="utf-8") as f:
    papers = json.load(f)

print(f"Total papers: {len(papers)}\n")
for p in papers[:10]:
    print(f"{p['year']} | {p['title'][:80]}")