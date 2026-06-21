import requests
import json
import time
import os

def fetch_papers_openalex(query, limit=15):
    """Fetch papers from OpenAlex API - free, no key, no rate limits.
    
    Uses title.search for focused relevance — keywords must appear in title.
    Falls back to abstract search if title search returns too few results.
    Only fetches open access papers so every paper can be read directly.
    """
    url = "https://api.openalex.org/works"
    params = {
        # title.search = keywords must appear in the TITLE → much more relevant
        # open_access.is_oa:true = only papers freely readable online
        "filter": f"title.search:{query},has_abstract:true,open_access.is_oa:true",
        "per-page": limit,
        "sort": "cited_by_count:desc",   # most cited = higher quality papers first
        "select": "id,title,abstract_inverted_index,publication_year,authorships,cited_by_count,referenced_works,concepts,doi,primary_location"
    }

    try:
        response = requests.get(url, params=params, timeout=15)

        if response.status_code == 200:
            data = response.json()
            works = data.get("results", [])

            # If title search returns too few, supplement with abstract search
            if len(works) < 5:
                params2 = dict(params)
                params2["filter"] = f"abstract.search:{query},has_abstract:true,open_access.is_oa:true"
                r2 = requests.get(url, params=params2, timeout=15)
                if r2.status_code == 200:
                    extra = r2.json().get("results", [])
                    existing = {w["id"] for w in works}
                    works += [w for w in extra if w["id"] not in existing]

            print(f"  ✓ Fetched {len(works)} open access papers for: '{query}'")
            return works
        else:
            print(f"  Error {response.status_code} for: '{query}'")
            return []

    except Exception as e:
        print(f"  Failed: {e}")
        return []


def reconstruct_abstract(inverted_index):
    """OpenAlex stores abstracts in inverted index format - converts back to text."""
    if not inverted_index:
        return ""

    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))

    word_positions.sort(key=lambda x: x[0])
    return " ".join(word for _, word in word_positions)


def clean_paper(work, search_topic):
    """Convert OpenAlex format to our standard format."""

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
        for r in (work.get("referenced_works") or [])[:20]
    ]

    paper_id = work.get("id", "").replace("https://openalex.org/", "")

    # Extract DOI and direct PDF URL for open access papers
    doi     = work.get("doi", "") or ""
    pdf_url = (work.get("primary_location") or {}).get("pdf_url", "") or ""

    return {
        "paperId":        paper_id,
        "title":          work.get("title", ""),
        "abstract":       reconstruct_abstract(work.get("abstract_inverted_index")),
        "year":           work.get("publication_year"),
        "authors":        authors,
        "citations":      [],
        "cited_by_count": work.get("cited_by_count", 0),
        "references":     references,
        "concepts":       concepts,
        "doi":            doi,
        "pdf_url":        pdf_url,
        # exact topic that found this paper — powers frontend topic filter chips
        "search_topic":   search_topic,
    }


# ── Your thesis topics ─────────────────────────────────────────────────────────
# Based on your research questions (SQ1-SQ5) from the exposé.
# These run automatically when you start the script.
# Add more at the bottom anytime — re-running only fetches new ones (duplicates skipped).

MY_TOPICS = [
    # SQ1 — discovering Feature Clusters and VAPs from event logs
    "process mining event logs manufacturing",
    "feature cluster product configurator",
    "value added process manufacturing",

    # SQ2 — Historical Quotas, demand patterns, feature probabilities
    "feature selection probability demand manufacturing",
    "historical quota production planning",

    # SQ3 — Transformation Models, input/output behavior
    "transformation model manufacturing process",
    "discrete event simulation manufacturing systems",

    # SQ4 — Generalization to real-world data
    "process mining generalization industrial data",
    "synthetic data generation manufacturing simulation",

    # SQ5 — Evaluation methodology
    "evaluation simulation data generation",

    # Background / motivation
    "digital twin discrete event simulation learning",
    "knowledge graph manufacturing process",
]


# ── Load existing papers so we append instead of overwrite ─────────────────────
output_file = "data/Alekhya_papers.json"
os.makedirs("data", exist_ok=True)

if os.path.exists(output_file):
    with open(output_file, encoding="utf-8") as f:
        all_papers = json.load(f)
    seen_ids = {p["paperId"] for p in all_papers}
    print(f"Loaded {len(all_papers)} existing papers from {output_file}")
else:
    all_papers = []
    seen_ids = set()
    print("Starting fresh — no existing file found")

print("\n" + "=" * 55)
print("Fetching open access papers from OpenAlex")
print("=" * 55)

# ── Run all predefined topics automatically ────────────────────────────────────
print(f"\nFetching {len(MY_TOPICS)} predefined thesis topics...\n")

for topic in MY_TOPICS:
    print(f"Searching: {topic}")
    works = fetch_papers_openalex(topic, limit=15)

    new_count = 0
    for work in works:
        if not work.get("title"):
            continue
        paper = clean_paper(work, search_topic=topic)
        if paper["paperId"] in seen_ids:
            continue
        seen_ids.add(paper["paperId"])
        all_papers.append(paper)
        new_count += 1

    print(f"  → {new_count} new papers added (duplicates skipped)")

    # Save after every topic so nothing is lost if script crashes
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_papers, f, indent=2, ensure_ascii=False)

    time.sleep(1)   # be polite to OpenAlex

print(f"\n{'=' * 55}")
print(f"Predefined topics done. Total papers so far: {len(all_papers)}")

# ── Interactive mode for extra topics ─────────────────────────────────────────
# Use this to add more topics without re-fetching the ones above
print("\nWant to fetch additional topics? (type 'done' to skip)\n")

while True:
    topic = input("Extra topic (or 'done'): ").strip()

    if not topic or topic.lower() in ("done", "exit", "quit"):
        break

    raw = input("How many papers? [default 15]: ").strip()
    limit = int(raw) if raw.isdigit() else 15

    print()
    works = fetch_papers_openalex(topic, limit=limit)

    new_papers = []
    for work in works:
        if not work.get("title"):
            continue
        paper = clean_paper(work, search_topic=topic)
        if paper["paperId"] in seen_ids:
            continue
        seen_ids.add(paper["paperId"])
        all_papers.append(paper)
        new_papers.append(paper)

    # Print titles so you can judge relevance immediately
    if new_papers:
        print(f"\n  Titles fetched (check these are on-topic):")
        for i, p in enumerate(new_papers[:10], 1):
            print(f"    {i:2}. [{p['year']}] {p['title'][:75]}")
            if p.get("pdf_url"):
                print(f"        PDF: {p['pdf_url']}")

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_papers, f, indent=2, ensure_ascii=False)
        print(f"\n  ✓ Added {len(new_papers)} new papers  |  Total: {len(all_papers)}")
    else:
        print("  No new papers — all were duplicates or none found")

    print()

# ── Final summary ──────────────────────────────────────────────────────────────
print("=" * 55)
print(f"Done. Total papers saved: {len(all_papers)}")
print(f"File: {output_file}")

# Show breakdown by topic
print("\nBreakdown by topic:")
topics = {}
for p in all_papers:
    t = p.get("search_topic", "unknown")
    topics[t] = topics.get(t, 0) + 1
for t, c in sorted(topics.items(), key=lambda x: -x[1]):
    print(f"  {c:3d}  {t}")

