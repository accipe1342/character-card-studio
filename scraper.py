import re
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

SECTION_ALIASES = {
    "appearance": ["appearance", "physical appearance", "design"],
    "personality": ["personality", "personality and character", "personality & character", "character"],
    "abilities": ["abilities", "skills", "skills and abilities", "skills & abilities", "powers"],
    "relationships": ["relationships", "family", "friends", "allies", "associates"],
    "history": ["history", "biography", "background", "early life", "story", "past"],
}

INFOBOX_ALIASES = {
    "age": ["age"],
    "gender": ["gender", "sex"],
    "occupation": ["occupation", "job", "role", "profession"],
    "affiliation": ["affiliation", "allegiance", "team", "organization"],
    "origin": ["origin", "series", "franchise", "anime", "source"],
}


def normalize_text(text: str) -> str:
    text = text.lower().strip().replace("[edit]", "").replace("&", "and")
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def classify_section(heading: str) -> Optional[str]:
    normalized = normalize_text(heading)
    for category, aliases in SECTION_ALIASES.items():
        if normalized in {normalize_text(a) for a in aliases}:
            return category
    return None


def normalize_infobox(infobox: dict) -> dict:
    normalized = {}
    for raw_key, raw_value in infobox.items():
        key_norm = normalize_text(raw_key)
        for standard_key, aliases in INFOBOX_ALIASES.items():
            if key_norm in {normalize_text(a) for a in aliases}:
                normalized[standard_key] = raw_value
                break
    return normalized


def scrape_fandom_page(wiki_base: str, page_name: str) -> Dict[str, Any]:
    api_url = f"{wiki_base}/api.php"
    params = {"action": "parse", "page": page_name, "prop": "text", "format": "json", "formatversion": 2}
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(api_url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    title = data["parse"]["title"]
    html = data["parse"]["text"]
    url = f"{wiki_base}/wiki/{page_name}"
    parsed = parse_page(html, fallback_title=title)
    return {
        "wiki_base": wiki_base,
        "page_name": page_name,
        "url": url,
        "title": title,
        "raw_html": html,
        "raw_infobox": parsed["infobox"],
        "raw_sections": parsed["raw_sections"],
        "normalized": parsed,
    }


def parse_page(html: str, fallback_title: Optional[str] = None) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one(".mw-parser-output") or soup

    summary = None
    for child in content.children:
        if getattr(child, "name", None) == "p":
            text = child.get_text(" ", strip=True)
            if text:
                summary = text
                break

    infobox = {}
    for row in soup.select(".portable-infobox .pi-item"):
        label = row.select_one(".pi-data-label")
        value = row.select_one(".pi-data-value")
        if label and value:
            infobox[label.get_text(" ", strip=True)] = value.get_text(" ", strip=True)

    raw_sections: Dict[str, list[str]] = {}
    current_heading = None
    for child in content.children:
        tag_name = getattr(child, "name", None)
        if tag_name in ("h2", "h3"):
            heading_text = child.get_text(" ", strip=True).replace("[edit]", "").strip()
            if heading_text:
                current_heading = heading_text
                raw_sections[current_heading] = []
        elif current_heading and tag_name in ("p", "ul", "ol"):
            text = child.get_text(" ", strip=True)
            if text:
                raw_sections[current_heading].append(text)

    merged = {"appearance": [], "personality": [], "abilities": [], "relationships": [], "history": []}
    for heading, blocks in raw_sections.items():
        category = classify_section(heading)
        if category:
            merged[category].extend(blocks)

    normalized_infobox = normalize_infobox(infobox)
    return {
        "title": fallback_title,
        "summary": summary,
        "franchise": normalized_infobox.get("origin") or infobox.get("Series") or infobox.get("Origin"),
        "appearance": "\n".join(merged["appearance"]) or "",
        "personality": "\n".join(merged["personality"]) or "",
        "abilities": "\n".join(merged["abilities"]) or "",
        "relationships": "\n".join(merged["relationships"]) or "",
        "history": "\n".join(merged["history"]) or "",
        "infobox": infobox,
        "normalized_infobox": normalized_infobox,
        "raw_sections": raw_sections,
    }
