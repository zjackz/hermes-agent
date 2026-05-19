---
name: arxiv
description: "Search arXiv papers by keyword, author, category, or ID."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Research, Arxiv, Papers, Academic, Science, API]
    related_skills: [ocr-and-documents]
---

# arXiv Research

Search and retrieve academic papers from arXiv via their free REST API. No API key, no dependencies — just curl.

## Quick Reference

| Action | Command |
|--------|---------|
| Search papers | `curl "https://export.arxiv.org/api/query?search_query=all:QUERY&max_results=5"` |
| Get specific paper | `curl "https://export.arxiv.org/api/query?id_list=2402.03300"` |
| Read abstract (web) | `web_extract(urls=["https://arxiv.org/abs/2402.03300"])` |
| Read full paper (PDF) | `web_extract(urls=["https://arxiv.org/pdf/2402.03300"])` |

## Searching Papers

The API returns Atom XML. Parse with `grep`/`sed` or pipe through `python3` for clean output.

### Basic search

```bash
curl -s "https://export.arxiv.org/api/query?search_query=all:GRPO+reinforcement+learning&max_results=5"
```

### Clean output (parse XML to readable format)

```bash
curl -s "https://export.arxiv.org/api/query?search_query=all:GRPO+reinforcement+learning&max_results=5&sortBy=submittedDate&sortOrder=descending" | python3 -c "
import sys, xml.etree.ElementTree as ET
ns = {'a': 'http://www.w3.org/2005/Atom'}
root = ET.parse(sys.stdin).getroot()
for i, entry in enumerate(root.findall('a:entry', ns)):
    title = entry.find('a:title', ns).text.strip().replace('\n', ' ')
    arxiv_id = entry.find('a:id', ns).text.strip().split('/abs/')[-1]
    published = entry.find('a:published', ns).text[:10]
    authors = ', '.join(a.find('a:name', ns).text for a in entry.findall('a:author', ns))
    summary = entry.find('a:summary', ns).text.strip()[:200]
    cats = ', '.join(c.get('term') for c in entry.findall('a:category', ns))
    print(f'{i+1}. [{arxiv_id}] {title}')
    print(f'   Authors: {authors}')
    print(f'   Published: {published} | Categories: {cats}')
    print(f'   Abstract: {summary}...')
    print(f'   PDF: https://arxiv.org/pdf/{arxiv_id}')
    print()
"
```

## Search Query Syntax

| Prefix | Searches | Example |
|--------|----------|---------|
| `all:` | All fields | `all:transformer+attention` |
| `ti:` | Title | `ti:large+language+models` |
| `au:` | Author | `au:vaswani` |
| `abs:` | Abstract | `abs:reinforcement+learning` |
| `cat:` | Category | `cat:cs.AI` |
| `co:` | Comment | `co:accepted+NeurIPS` |

### Boolean operators

```
# AND (default when using +)
search_query=all:transformer+attention

# OR
search_query=all:GPT+OR+all:BERT

# AND NOT
search_query=all:language+model+ANDNOT+all:vision

# Exact phrase
search_query=ti:"chain+of+thought"

# Combined
search_query=au:hinton+AND+cat:cs.LG
```

## Sort and Pagination

| Parameter | Options |
|-----------|---------|
| `sortBy` | `relevance`, `lastUpdatedDate`, `submittedDate` |
| `sortOrder` | `ascending`, `descending` |
| `start` | Result offset (0-based) |
| `max_results` | Number of results (default 10, max 30000) |

```bash
# Latest 10 papers in cs.AI
curl -s "https://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=10"
```

## Fetching Specific Papers

```bash
# By arXiv ID
curl -s "https://export.arxiv.org/api/query?id_list=2402.03300"

# Multiple papers
curl -s "https://export.arxiv.org/api/query?id_list=2402.03300,2401.12345,2403.00001"
```

## BibTeX Generation

After fetching metadata for a paper, generate a BibTeX entry:

{% raw %}
```bash
curl -s "https://export.arxiv.org/api/query?id_list=1706.03762" | python3 -c "
import sys, xml.etree.ElementTree as ET
ns = {'a': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
root = ET.parse(sys.stdin).getroot()
entry = root.find('a:entry', ns)
if entry is None: sys.exit('Paper not found')
title = entry.find('a:title', ns).text.strip().replace('\n', ' ')
authors = ' and '.join(a.find('a:name', ns).text for a in entry.findall('a:author', ns))
year = entry.find('a:published', ns).text[:4]
raw_id = entry.find('a:id', ns).text.strip().split('/abs/')[-1]
cat = entry.find('arxiv:primary_category', ns)
primary = cat.get('term') if cat is not None else 'cs.LG'
last_name = entry.find('a:author', ns).find('a:name', ns).text.split()[-1]
print(f'@article{{{last_name}{year}_{raw_id.replace(\".\", \"\")},')
print(f'  title     = {{{title}}},')
print(f'  author    = {{{authors}}},')
print(f'  year      = {{{year}}},')
print(f'  eprint    = {{{raw_id}}},')
print(f'  archivePrefix = {{arXiv}},')
print(f'  primaryClass  = {{{primary}}},')
print(f'  url       = {{https://arxiv.org/abs/{raw_id}}}')
print('}')
"
```
{% endraw %}

## Reading Paper Content

After finding a paper, read it:

```
# Abstract page (fast, metadata + abstract)
web_extract(urls=["https://arxiv.org/abs/2402.03300"])

# Full paper (PDF → markdown via Firecrawl)
web_extract(urls=["https://arxiv.org/pdf/2402.03300"])
```

For local PDF processing, see the `ocr-and-documents` skill.

## Common Categories

| Category | Field |
|----------|-------|
| `cs.AI` | Artificial Intelligence |
| `cs.CL` | Computation and Language (NLP) |
| `cs.CV` | Computer Vision |
| `cs.LG` | Machine Learning |
| `cs.CR` | Cryptography and Security |
| `stat.ML` | Machine Learning (Statistics) |
| `math.OC` | Optimization and Control |
| `physics.comp-ph` | Computational Physics |

Full list: https://arxiv.org/category_taxonomy

## Helper Script

The `scripts/search_arxiv.py` script handles XML parsing and provides clean output:

```bash
python scripts/search_arxiv.py "GRPO reinforcement learning"
python scripts/search_arxiv.py "transformer attention" --max 10 --sort date
python scripts/search_arxiv.py --author "Yann LeCun" --max 5
python scripts/search_arxiv.py --category cs.AI --sort date
python scripts/search_arxiv.py --id 2402.03300
python scripts/search_arxiv.py --id 2402.03300,2401.12345
```

No dependencies — uses only Python stdlib.

---

## Semantic Scholar (Citations, Related Papers, Author Profiles)

arXiv doesn't provide citation data or recommendations. Use the **Semantic Scholar API** for that — free, no key needed for basic use (1 req/sec), returns JSON.

### Get paper details + citations

```bash
# By arXiv ID
curl -s "https://api.semanticscholar.org/graph/v1/paper/arXiv:2402.03300?fields=title,authors,citationCount,referenceCount,influentialCitationCount,year,abstract" | python3 -m json.tool

# By Semantic Scholar paper ID or DOI
curl -s "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/example?fields=title,citationCount"
```

### Get citations OF a paper (who cited it)

```bash
curl -s "https://api.semanticscholar.org/graph/v1/paper/arXiv:2402.03300/citations?fields=title,authors,year,citationCount&limit=10" | python3 -m json.tool
```

### Get references FROM a paper (what it cites)

```bash
curl -s "https://api.semanticscholar.org/graph/v1/paper/arXiv:2402.03300/references?fields=title,authors,year,citationCount&limit=10" | python3 -m json.tool
```

### Search papers (alternative to arXiv search, returns JSON)

```bash
curl -s "https://api.semanticscholar.org/graph/v1/paper/search?query=GRPO+reinforcement+learning&limit=5&fields=title,authors,year,citationCount,externalIds" | python3 -m json.tool
```

### Get paper recommendations

```bash
curl -s -X POST "https://api.semanticscholar.org/recommendations/v1/papers/" \
  -H "Content-Type: application/json" \
  -d '{"positivePaperIds": ["arXiv:2402.03300"], "negativePaperIds": []}' | python3 -m json.tool
```

### Author profile

```bash
curl -s "https://api.semanticscholar.org/graph/v1/author/search?query=Yann+LeCun&fields=name,hIndex,citationCount,paperCount" | python3 -m json.tool
```

### Useful Semantic Scholar fields

`title`, `authors`, `year`, `abstract`, `citationCount`, `referenceCount`, `influentialCitationCount`, `isOpenAccess`, `openAccessPdf`, `fieldsOfStudy`, `publicationVenue`, `externalIds` (contains arXiv ID, DOI, etc.)

---

## Complete Research Workflow

1. **Discover**: `python scripts/search_arxiv.py "your topic" --sort date --max 10`
2. **Assess impact**: `curl -s "https://api.semanticscholar.org/graph/v1/paper/arXiv:ID?fields=citationCount,influentialCitationCount"`
3. **Read abstract**: `web_extract(urls=["https://arxiv.org/abs/ID"])`
4. **Read full paper**: `web_extract(urls=["https://arxiv.org/pdf/ID"])`
5. **Find related work**: `curl -s "https://api.semanticscholar.org/graph/v1/paper/arXiv:ID/references?fields=title,citationCount&limit=20"`
6. **Get recommendations**: POST to Semantic Scholar recommendations endpoint
7. **Track authors**: `curl -s "https://api.semanticscholar.org/graph/v1/author/search?query=NAME"`

## Rate Limits

| API | Rate | Auth |
|-----|------|------|
| arXiv | ~1 req / 3 seconds | None needed |
| Semantic Scholar | 1 req / second | None (100/sec with API key) |

## Notes

- arXiv returns Atom XML — use the helper script or parsing snippet for clean output
- Semantic Scholar returns JSON — pipe through `python3 -m json.tool` for readability
- arXiv IDs: old format (`hep-th/0601001`) vs new (`2402.03300`)
- PDF: `https://arxiv.org/pdf/{id}` — Abstract: `https://arxiv.org/abs/{id}`
- HTML (when available): `https://arxiv.org/html/{id}`
- For local PDF processing, see the `ocr-and-documents` skill

## Pitfalls & Production Use

### arXiv API rate limiting is aggressive at certain times

The arXiv API (`export.arxiv.org`) frequently returns **HTTP 429 Too Many Requests** and **read timeouts**, especially during these windows:
- **00:00–02:00 UTC** (08:00–10:00 CST) — this is arXiv's daily submission cutoff window; API traffic spikes as new papers are indexed
- This is exactly when our cron job (`ai-tracker-daily`, 08:00 CST) runs, so rate limiting is **expected, not exceptional**

**When 429s happen, the API becomes unusable for 30–60 minutes** — even simple single queries with proper delays will fail. This is not a retry-logic problem; it's an API-side capacity issue. Plan accordingly.

### Handling 429s in production scripts

```python
import urllib.request, time

def arxiv_search(query, label, max_results=3, retries=2, timeout=15):
    url = f"https://export.arxiv.org/api/query?..."
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": "arXivBot/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as f:
                raw = f.read().decode("utf-8")
        except Exception as e:
            err_msg = str(e)
            if attempt < retries - 1 and ("429" in err_msg or "timeout" in err_msg.lower()):
                wait = 10 * (attempt + 1)
                time.sleep(wait)
                continue
            return {"results": [], "error": err_msg}
        # parse XML...
    return {"results": [], "error": "Max retries exceeded"}
```

Key choices:
- **`urllib.request` over `subprocess`+`curl`** — removes external command dependency; critical for cron environments where PATH may be minimal
- **retries=2, timeout=15** — keeps worst-case per-query to ~45s; balanced against cron timeout limits
- **Hard MAX_RUNTIME guard** — if the script runs under cron with a 120s limit, enforce a ~90s ceiling to leave time for output serialization

### Weekend schedule

arXiv does **not** publish new submissions on weekends (Saturday/Sunday UTC). Queries on those days will return papers from Thursday/Friday at best, or empty results if the time window has rotated. **Detect weekends upfront and skip arXiv queries entirely:**

```python
from datetime import datetime
weekday = datetime.now(timezone.utc).weekday()
IS_WEEKEND = weekday >= 5  # Saturday=5, Sunday=6
if IS_WEEKEND:
    print("Weekend — arXiv has no new papers. Skipping API calls.")
```

### Fallback strategy when API is down

When the export API is saturated (429s across all categories), use HTML scraping as a fallback:

```python
# Scrape the "new submissions" listing pages directly
# These are static HTML and bypass the API entirely
import urllib.request, re, html as html_mod

url = f"https://arxiv.org/list/cs.AI/new"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=30) as f:
    content = f.read().decode("utf-8")

# Extract paper titles and IDs
pattern = r'arXiv:(\d+\.\d+).*?<span class="descriptor">Title:</span>\s*(.*?)</div>'
matches = re.findall(pattern, content, re.DOTALL)
for aid, title in matches:
    title = html_mod.unescape(re.sub(r'<[^>]+>', '', title)).strip()
```

**Caveat**: The HTML structure of `arxiv.org/list/` can change. The API is preferred when available; scraping is a fallback for when the API is saturated.

### Summary of known issues

| Issue | Symptom | Workaround |
|-------|---------|------------|
| 429 rate limit (peak hours) | All queries fail at 00:00–02:00 UTC | Skip or use HTML fallback |
| Read timeout (API overloaded) | Individual queries hang >25s | Set timeout=15, retry once |
| Weekend empty results | No papers returned on Sat/Sun | Skip arXiv entirely; use blogwatcher or HN |
| `curl` not found in cron | Script fails silently | Use `urllib.request` not `subprocess` |

## ID Versioning

- `arxiv.org/abs/1706.03762` always resolves to the **latest** version
- `arxiv.org/abs/1706.03762v1` points to a **specific** immutable version
- When generating citations, preserve the version suffix you actually read to prevent citation drift (a later version may substantially change content)
- The API `<id>` field returns the versioned URL (e.g., `http://arxiv.org/abs/1706.03762v7`)

## Withdrawn Papers

Papers can be withdrawn after submission. When this happens:
- The `<summary>` field contains a withdrawal notice (look for "withdrawn" or "retracted")
- Metadata fields may be incomplete
- Always check the summary before treating a result as a valid paper
