import requests
import json
import time
import os

def fetch_papers_openalex(query, limit=15):
    """Fetch papers from OpenAlex API - free, no key, no rate limits"""
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per-page": limit,
        "filter": "has_abstract:true",
        "select": "id,title,abstract_inverted_index,publication_year,authorships,cited_by_count,referenced_works,concepts"
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            works = data.get("results", [])
            print(f"  ✓ Fetched {len(works)} papers for: '{query}'")
            return works
        else:
            print(f"  Error {response.status_code} for: '{query}'")
            return []
            
    except Exception as e:
        print(f"  Failed: {e}")
        return []

def reconstruct_abstract(inverted_index):
    """OpenAlex stores abstracts in inverted index format - this converts it back to text"""
    if not inverted_index:
        return ""
    
    # inverted_index = {"word": [position1, position2], ...}
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    
    word_positions.sort(key=lambda x: x[0])
    return " ".join(word for _, word in word_positions)

def clean_paper(work):
    """Convert OpenAlex format to our standard format"""
    
    # Extract authors
    authors = []
    for authorship in (work.get("authorships") or []):
        author = authorship.get("author", {})
        if author.get("display_name"):
            authors.append({
                "authorId": (author.get("id") or "").replace("https://openalex.org/", ""),
                "name": author.get("display_name", "")
            })
    
    # Extract topics/concepts
    concepts = [
        c.get("display_name", "")
        for c in (work.get("concepts") or [])
        if c.get("score", 0) > 0.3
    ]
    
    # Extract references (just IDs)
    references = [
        {"paperId": r.replace("https://openalex.org/", ""), "title": ""}
        for r in (work.get("referenced_works") or [])[:20]  # limit to 20
    ]
    
    # Clean paper ID
    paper_id = work.get("id", "").replace("https://openalex.org/", "")
    
    return {
        "paperId": paper_id,
        "title": work.get("title", ""),
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "year": work.get("publication_year"),
        "authors": authors,
        "citations": [],  # how many times cited
        "cited_by_count": work.get("cited_by_count", 0),
        "references": references,
        "concepts": concepts
    }

# Your topics
my_topics = [
<<<<<<< HEAD
    "process mining event logs manufacturing",
    "digital twin learning discrete event simulation",
    "feature cluster product configurator discovery",
    "value added process manufacturing discovery",
    "transformation model input output material flow",
    "feature selection probability customer demand",
    "synthetic data generation manufacturing simulation",
    "process mining generalization real world industrial data",
    "evaluation methodology synthetic simulation data",
    "discrete event simulation manufacturing systems"
=======
    "computer vision",
    "fisheye camera datasets",
    "illuminations and occlusions in fisheye cameras ",
    "tracking in fisheye cameras and public datasets",
    "multi person tracking",
    "detector"
>>>>>>> 32cec71e96703c306967eb49647eaf36c305cb5b
]

print("Fetching papers from OpenAlex — free, no API key needed")
print("=" * 55)

all_papers = []
seen_ids = set()

for topic in my_topics:
    print(f"\nSearching: {topic}")
    works = fetch_papers_openalex(topic, limit=15)
    
    for work in works:
        if not work.get("title"):
            continue
            
        paper = clean_paper(work)
        
        if paper["paperId"] in seen_ids:
            continue
            
        seen_ids.add(paper["paperId"])
        all_papers.append(paper)
    
    # Small wait to be polite
    time.sleep(1)

print("\n" + "=" * 55)
print(f"Total unique papers fetched: {len(all_papers)}")

# Save to file
os.makedirs("data", exist_ok=True)
<<<<<<< HEAD
output_file = "data/Alekhya_papers.json"
=======
output_file = "../data/Mahenoor_papers.json"
>>>>>>> 32cec71e96703c306967eb49647eaf36c305cb5b

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_papers, f, indent=2, ensure_ascii=False)

print(f"Saved to {output_file}")
print("\nDone! Run load_to_db.py next to load into all three databases")