"""Scam Intelligence: real scam reports (Apify) in a Moss index, explained by Claude. Owner: Lead (P1).

1. ONCE, ahead of time:  python -m services.scam_intel seed
     Apify's Google Search Scraper collects recent news / FTC / consumer-alert results about
     voice-clone and family-emergency money scams. They're saved to data/scam_reports.json and put
     in the Moss index "scam-patterns" (one document per report).
2. During a case:  check_story(text) finds the closest reports in Moss and Claude writes one short
     line like: "This matches the 'car crash + urgent money + keep it secret' scam pattern seen in
     5 recent reports (ftc.gov, nbcnews.com)."

This is information for the parent only. It NEVER decides green or red: only the student's own
answer on the verification call does.

Needs in .env: APIFY_TOKEN (for seeding), MOSS_PROJECT_ID, MOSS_PROJECT_KEY, ANTHROPIC_API_KEY (optional).
"""
import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from services.claude_tools import _ask_json
from services.data_tools import MOSS_CACHE, _moss_client, _run

load_dotenv()
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
APIFY_ACTOR = os.getenv("APIFY_ACTOR") or "apify~google-search-scraper"
SCAM_INDEX = os.getenv("SCAM_INDEX") or "scam-patterns"
REPORTS_FILE = Path(__file__).resolve().parent.parent / "data" / "scam_reports.json"

SEARCH_QUERIES = [
    "AI voice cloning scam parents money",
    "family emergency scam voice clone gift cards",
    "grandparent scam AI cloned voice",
    "FTC alert family emergency scam voice cloning",
    "scammers clone child's voice ask parents for money",
    "fake arrest bail money scam phone call family",
    "car accident emergency money scam call son daughter",
    "student scam call parents abroad money urgent",
]

_loaded = threading.Event()
_loading = threading.Lock()


# ---------- 1. Collect reports with Apify ----------

def scrape_reports(queries: list[str] = SEARCH_QUERIES, per_query: int = 10) -> list[dict]:
    """Run Apify's Google Search Scraper and return [{"title", "url", "snippet", "query"}]."""
    if not APIFY_TOKEN:
        raise SystemExit("Set APIFY_TOKEN in .env first (apify.com -> Settings -> API & Integrations)")
    response = requests.post(
        f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items",
        params={"token": APIFY_TOKEN},
        json={"queries": "\n".join(queries), "resultsPerPage": per_query, "maxPagesPerQuery": 1,
              "languageCode": "en", "countryCode": "us"},
        timeout=300,
    )
    if not response.ok:
        raise SystemExit(f"Apify run failed ({response.status_code}): {response.text[:300]}")
    reports, seen = [], set()
    for page in response.json():
        query = (page.get("searchQuery") or {}).get("term", "")
        results = page.get("organicResults")
        if results is None:  # some actors return one result per item
            results = [page]
        for r in results:
            url, title = r.get("url") or "", (r.get("title") or "").strip()
            snippet = (r.get("description") or r.get("snippet") or "").strip()
            if not url or not title or url in seen:
                continue
            seen.add(url)
            reports.append({"title": title, "url": url, "snippet": snippet, "query": query})
    return reports


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


# ---------- 2. Store them in Moss ----------

def _docs(reports: list[dict]):
    from moss import DocumentInfo
    return [
        DocumentInfo(
            id=f"r{i}",
            text=f"{r['title']}. {r['snippet']}",
            metadata={"title": r["title"][:300], "url": r["url"], "source": _domain(r["url"])},
        )
        for i, r in enumerate(reports)
    ]


def seed(reports: list[dict] | None = None) -> int:
    """Scrape (unless reports are given), save to data/scam_reports.json, and (re)build the Moss index."""
    client = _moss_client()
    if client is None:
        raise SystemExit("Set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in .env first")
    if reports is None:
        print("Collecting scam reports with Apify (can take a minute)...")
        reports = scrape_reports()
    if not reports:
        raise SystemExit("Apify returned no results; nothing to index")
    REPORTS_FILE.parent.mkdir(exist_ok=True)
    REPORTS_FILE.write_text(json.dumps(reports, indent=2))
    existing = {i.name for i in _run(client.list_indexes())}
    if SCAM_INDEX in existing:
        _run(client.delete_index(SCAM_INDEX), timeout=60)
    _run(client.create_index(SCAM_INDEX, _docs(reports)), timeout=180)
    print(f"Moss index '{SCAM_INDEX}' has {len(reports)} scam reports (saved to {REPORTS_FILE.name})")
    return len(reports)


def _load() -> None:
    if _loaded.is_set() or not _loading.acquire(blocking=False):
        return
    try:
        started = time.time()
        asyncio.run(_moss_client().load_index(SCAM_INDEX, cache_path=MOSS_CACHE))
        _loaded.set()
        print(f"[Scam Intel] scam reports loaded in {time.time() - started:.0f}s")
    except Exception as e:
        print(f"[Scam Intel] could not load '{SCAM_INDEX}': {e}. Run: python -m services.scam_intel seed")
    finally:
        _loading.release()


def warm() -> None:
    """Start loading the scam index in the background (call at agent startup)."""
    if _moss_client() is not None and not _loaded.is_set():
        threading.Thread(target=_load, daemon=True).start()


def find_matches(text: str, top_k: int = 6) -> list[dict]:
    """Closest scam reports to this story: [{"title", "url", "source"}]. [] if not ready."""
    if _moss_client() is None or not _loaded.is_set() or not text.strip():
        return []
    from moss import QueryOptions
    result = _run(_moss_client().query(SCAM_INDEX, text[:1000], QueryOptions(top_k=top_k, alpha=0.6)))
    return [dict(d.metadata or {}) for d in result.docs if (d.metadata or {}).get("url")]


# ---------- 3. Explain with Claude ----------

EXPLAIN_SYSTEM = """A parent received a suspicious message claiming to be from their child. You get the
message (or its transcript) and numbered real-world scam reports found by search.
Decide which reports describe the SAME kind of scam (same tactics, e.g. fake emergency, cloned voice,
urgent money, gift cards, secrecy). Ignore unrelated ones. Return:
- "match": true if at least one report clearly describes the same kind of scam
- "pattern": 3-8 words naming the pattern, e.g. "car crash + urgent money + keep it secret"
- "used": list of the matching report numbers
Never invent reports or numbers."""


def check_story(text: str) -> dict:
    """{"summary": one line for the parent (or ""), "matches": count, "sources": "a.com, b.org"}."""
    empty = {"summary": "", "matches": 0, "sources": ""}
    try:
        reports = find_matches(text)
    except Exception as e:
        print(f"[Scam Intel] search failed: {e}")
        return empty
    if not reports:
        return empty
    numbered = "\n".join(f"{i + 1}. {r.get('title', '')} ({r.get('source', '')})" for i, r in enumerate(reports))
    data = _ask_json(EXPLAIN_SYSTEM, f"Message:\n{text[:1500]}\n\nReports:\n{numbered}")
    if data:
        if not data.get("match"):
            return empty
        used = [reports[n - 1] for n in data.get("used", []) if isinstance(n, int) and 1 <= n <= len(reports)]
        pattern = str(data.get("pattern") or "").strip()
    else:  # no Claude: just point to the closest reports, without claiming a match
        used, pattern = reports[:3], ""
    if not used:
        return empty
    sources = []
    for r in used:
        if r.get("source") and r["source"] not in sources:
            sources.append(r["source"])
    n = f"{len(used)} real scam report{'s' if len(used) != 1 else ''}"
    if pattern:
        summary = f"⚠️ Pattern check: this matches the \"{pattern}\" pattern described in {n} ({', '.join(sources[:3])})."
    else:
        summary = f"⚠️ Pattern check: the closest {n} found: {', '.join(sources[:3])}."
    return {"summary": summary, "matches": len(used), "sources": ", ".join(sources[:5])}


if __name__ == "__main__":
    if sys.argv[1:] == ["seed"]:
        seed()
    print("Loading the scam index...")
    _load()
    example = "Mom it's Arjun, I crashed the car, I need two thousand dollars in gift cards right now, don't tell dad"
    print(check_story(example))
