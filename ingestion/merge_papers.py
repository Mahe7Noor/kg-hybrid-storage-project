import json
import os

# Load both files
with open("../data/Alekhya_papers.json", encoding="utf-8") as f:
    Alekhya_papers = json.load(f)

with open("../data/Mahenoor_papers.json", encoding="utf-8") as f:
    Mahenoor_papers = json.load(f)

print(f"Alekhya papers: {len(Alekhya_papers)}")
print(f"Mahe Noor papers: {len(Mahenoor_papers)}")

# Combine and remove duplicates by paperId
all_papers = Alekhya_papers + Mahenoor_papers
seen_ids = set()
unique_papers = []

for paper in all_papers:
    pid = paper.get("paperId")
    if pid and pid not in seen_ids:
        seen_ids.add(pid)
        unique_papers.append(paper)

print(f"Total unique papers combined: {len(unique_papers)}")

# Save as the final combined dataset
with open("data/combined_papers.json", "w", encoding="utf-8") as f:
    json.dump(unique_papers, f, indent=2, ensure_ascii=False)

print("Saved to data/combined_papers.json")