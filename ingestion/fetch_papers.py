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
    "Fundamentals of Computer Vision and Its Applications",
    "Object Detection Techniques in Computer Vision",
    "Traditional vs Deep Learning-Based Object Detection Methods",
    "Evolution of Object Detection: From Haar Cascades to YOLO",
    "Comparative Study of YOLO, SSD, and Faster R-CNN for Object Detection",
    "Role of Convolutional Neural Networks in Object Detection",
    "Real-Time Object Detection Using YOLO Models",
    "Object Tracking Techniques in Video Surveillance",
    "Detection-Based Tracking in Computer Vision",
    "Comparative Review of SORT, DeepSORT, ByteTrack, and BoT-SORT",
    "Person Detection and Tracking in Video Sequences",
    "Multi-Object Tracking: Methods, Challenges, and Applications",
    "Challenges in Object Detection and Tracking Under Occlusion",
    "Impact of Camera Viewpoint on Object Detection Performance",
    "Computer Vision for Human Monitoring and Surveillance Systems",
    "Object Detection and Tracking Using Overhead Cameras",
    "Person Detection in Fisheye Camera Images",
    "Tracking Humans in Overhead Fisheye Camera Videos",
    "Deep Learning-Based Human Detection in Surveillance Videos",
    "Evaluation Metrics for Object Detection and Tracking",
    "Datasets for Object Detection and Tracking Research",
    "Data Augmentation for Improving Object Detection Performance",
    "Real-Time Person Tracking Using Deep Learning",
    "Computer Vision for Smart Monitoring Systems",
    "Challenges and Future Trends in Object Detection and Tracking"
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
output_file = "../data/Mahenoor_papers.json"

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_papers, f, indent=2, ensure_ascii=False)

print(f"Saved to {output_file}")
print("\nDone! Run load_to_db.py next to load into all three databases")