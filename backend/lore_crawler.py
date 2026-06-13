"""
lore_crawler.py — Multi-page lore scraping
==========================================
Crawls multiple wiki pages starting from a seed URL and builds a
lorebook project from the results. Used by the Lore Studio's
multi-URL mode.

MAIN ENTRY POINT
----------------
crawl_worldbook(seed_url, max_pages, max_depth, crawl_id,
                provider, model, job_id, update_job) -> None
    Spawns a BFS crawl from seed_url, scrapes each page it finds,
    generates a lore entry for each, and saves them to the DB under
    the given crawl_id. Runs in a background thread.

    seed_url    Starting wiki page URL
    max_pages   Hard cap on total pages scraped (default 20)
    max_depth   BFS depth limit (1 = seed page only, 2 = seed + links)
    crawl_id    DB ID of the lore_crawls row to attach entries to
    provider    AI provider string ("nanogpt"|"openrouter"|"local")
    model       Model ID string
    job_id      Job ID for progress updates via update_job()
    update_job  Callback: update_job(job_id, status, stage, progress, message)

CRAWL BEHAVIOUR
---------------
- Only follows links that stay on the same wiki domain
- Skips Special:, Help:, User:, File:, Template:, and talk pages
  (see BLOCKED_PATH_PARTS)
- Deduplicates URLs before fetching
- Each page is scraped with scraper.scrape_url() then passed to
  generator.generate_lore_entry()
- Progress is reported back to the job system after each page

HOW TO EXTEND
-------------
- Block more page types: add patterns to BLOCKED_PATH_PARTS
- Change crawl strategy: replace the deque (BFS) with a stack (DFS)
  or a priority queue (relevance-first)
- Add crawl filtering: filter discovered links by title keywords
  before adding them to the queue
- Support non-wiki sites: modify the link-discovery logic in
  _discover_links() to handle different HTML structures
"""

from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag, unquote

import requests
from bs4 import BeautifulSoup

from scraper import scrape_url


BLOCKED_PATH_PARTS = [
    "/wiki/Special:",
    "/wiki/Help:",
    "/wiki/User:",
    "/wiki/File:",
    "/wiki/Template:",
    "/wiki/Template_talk:",
    "/wiki/User_blog:",
    "/wiki/Forum:",
]

LOW_VALUE_TERMS = [
    "gallery",
    "quote",
    "quotes",
    "image",
    "images",
    "voice",
    "ending",
    "move",
    "moves",
    "gameplay",
    "weapon_skin",
    "costume",
    "alternate_costume",
    "trivia",
]

HIGH_VALUE_TERMS = [
    "organization",
    "faction",
    "group",
    "clan",
    "order",
    "empire",
    "kingdom",
    "city",
    "planet",
    "location",
    "region",
    "history",
    "timeline",
    "event",
    "war",
    "force",
    "magic",
    "power",
    "artifact",
    "ethnicity",
    "race",
]


def same_domain(a: str, b: str) -> bool:
    return urlparse(a).netloc == urlparse(b).netloc


def normalize_url(url: str) -> str:
    clean, _frag = urldefrag(url)
    return clean.rstrip("/")


def is_probably_wiki_article(url: str) -> bool:
    lowered = url.lower()
    if "/wiki/" not in lowered:
        return False
    if any(part.lower() in lowered for part in BLOCKED_PATH_PARTS):
        return False
    return True


def extract_internal_links(url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    seen: set[str] = set()

    for a in soup.select("a[href]"):
        href = a.get("href", "").strip()
        if not href or href.startswith("#"):
            continue

        full = normalize_url(urljoin(url, href))

        if not same_domain(url, full):
            continue

        if not is_probably_wiki_article(full):
            continue

        if full in seen:
            continue

        seen.add(full)
        links.append(full)

    return links


def score_link(url: str, anchor_text: str = "") -> int:
    score = 0
    lowered = unquote(url).lower()
    anchor = anchor_text.strip().lower()

    if "/wiki/" in lowered:
        score += 1

    if any(term in lowered for term in HIGH_VALUE_TERMS):
        score += 4

    if any(term in lowered for term in LOW_VALUE_TERMS):
        score -= 4

    # Slight preference for cleaner article URLs
    path_tail = lowered.split("/wiki/")[-1]
    if path_tail and ":" not in path_tail:
        score += 1

    # Prefer links with readable anchor text
    if anchor and len(anchor) >= 3:
        score += 1

    return score


def fetch_html(url: str, timeout: int = 20) -> str:
    r = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    r.raise_for_status()
    return r.text


def crawl_worldbook(seed_url: str, max_pages: int = 10, max_depth: int = 1) -> list[dict]:
    seed_url = normalize_url(seed_url)

    seen: set[str] = set()
    queued: set[str] = {seed_url}
    queue = deque([(seed_url, 0)])
    results: list[dict] = []

    while queue and len(results) < max_pages:
        url, depth = queue.popleft()
        queued.discard(url)

        if url in seen:
            continue
        seen.add(url)

        try:
            source = scrape_url(url)
            results.append(
                {
                    "url": url,
                    "depth": depth,
                    "source": source,
                }
            )

            if depth >= max_depth:
                continue

            html = fetch_html(url)
            soup = BeautifulSoup(html, "html.parser")

            scored_links: list[tuple[int, str]] = []

            for a in soup.select("a[href]"):
                href = a.get("href", "").strip()
                if not href or href.startswith("#"):
                    continue

                full = normalize_url(urljoin(url, href))

                if not same_domain(url, full):
                    continue

                if not is_probably_wiki_article(full):
                    continue

                if full in seen or full in queued:
                    continue

                anchor_text = a.get_text(" ", strip=True)
                score = score_link(full, anchor_text)

                if score <= 0:
                    continue

                scored_links.append((score, full))

            scored_links.sort(key=lambda x: x[0], reverse=True)

            for _score, link in scored_links[:15]:
                queue.append((link, depth + 1))
                queued.add(link)

        except Exception as e:
            print(f"[LORE CRAWLER] Failed to process {url}: {e}")
            continue

    return results