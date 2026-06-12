import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"

SECTION_ALIASES = {
    "appearance": [
        "appearance",
        "physical appearance",
        "design",
        "looks",
        "description",
        "costume",
        "costumes",
        "outfit",
        "outfits",
    ],
    "personality": [
        "personality",
        "character",
        "personality and character",
        "personality & character",
        "temperament",
        "traits",
        "behavior",
        "demeanor",
    ],
    "abilities": [
        "abilities",
        "skills",
        "powers",
        "capabilities",
        "techniques",
        "fighting style",
        "combat style",
        "weapon",
        "weapons",
    ],
    "relationships": [
        "relationships",
        "family",
        "friends",
        "allies",
        "enemies",
        "associates",
        "relatives",
        "companions",
    ],
    "history": [
        "history",
        "biography",
        "background",
        "early life",
        "story",
        "past",
        "overview",
        "plot",
        "synopsis",
        "origin",
    ],
}

INFOBOX_ALIASES = {
    "age": ["age"],
    "gender": ["gender", "sex"],
    "occupation": ["occupation", "job", "profession", "class", "role"],
    "affiliation": ["affiliation", "allegiance", "team", "organization", "group", "alignment"],
    "origin": ["origin", "series", "franchise", "source", "game", "debut"],
    "species": ["species", "race", "kind"],
    "height": ["height"],
    "weight": ["weight"],
    "eyes": ["eye color", "eyes"],
    "hair": ["hair color", "hair"],
    "weapons": ["weapon", "weapons", "armament", "equipment"],
}

NOISE_HEADINGS = {
    "contents",
    "references",
    "external links",
    "gallery",
    "navigation",
    "see also",
    "notes",
    "citations",
    "trivia",
    "cultural impact",
    "promotion and merchandising",
    "critical reception",
    "sex symbol",
    "series appearances",
    "appearances in other media",
    "etymology",
    "theme music",
    "stages",
}

NOISE_SELECTORS = [
    "script",
    "style",
    "noscript",
    ".toc",
    ".portable-infobox .reference",
    ".reference",
    ".error",
    ".mw-editsection",
    ".noprint",
    ".navbox",
    ".navigation-not-searchable",
    ".catlinks",
    ".license-description",
    ".wds-tab__content",  # image tab junk on some fandom pages
]

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"])" )


def normalize_text(text: str) -> str:
    text = text.lower().replace("&", "and")
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        key = normalize_text(item)
        if item and key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def split_traits(text: str, max_len: int = 180) -> List[str]:
    if not text:
        return []
    parts = []
    for chunk in SENTENCE_SPLIT_RE.split(clean_text(text)):
        chunk = chunk.strip(" -•\t\n")
        if not chunk:
            continue
        if len(chunk) <= max_len:
            parts.append(chunk)
        else:
            comma_parts = [p.strip() for p in chunk.split(",") if p.strip()]
            if 1 < len(comma_parts) <= 6:
                parts.extend(comma_parts)
            else:
                parts.append(chunk)
    return dedupe_keep_order(parts)


def classify_section(heading: str) -> Optional[str]:
    normalized = normalize_text(heading)
    if not normalized or normalized in NOISE_HEADINGS:
        return None

    for category, aliases in SECTION_ALIASES.items():
        alias_norms = [normalize_text(a) for a in aliases]
        if normalized in alias_norms:
            return category
        if any(alias in normalized or normalized in alias for alias in alias_norms):
            return category
    return None


def normalize_infobox(infobox: Dict[str, str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for raw_key, raw_value in infobox.items():
        key_norm = normalize_text(raw_key)
        for standard_key, aliases in INFOBOX_ALIASES.items():
            alias_norms = [normalize_text(a) for a in aliases]
            if key_norm in alias_norms or any(alias in key_norm for alias in alias_norms):
                normalized.setdefault(standard_key, raw_value)
                break
    return normalized


def remove_noise(root: Tag) -> None:
    for selector in NOISE_SELECTORS:
        for node in root.select(selector):
            node.decompose()


def text_from_node(node: Tag) -> str:
    return clean_text(node.get_text(" ", strip=True))


def extract_summary(content: Tag) -> str:
    for child in content.children:
        if isinstance(child, NavigableString):
            continue
        if not isinstance(child, Tag):
            continue
        if child.name == "p":
            text = text_from_node(child)
            if len(text) >= 40:
                return text
    paragraphs = [text_from_node(p) for p in content.select("p")]
    for p in paragraphs:
        if len(p) >= 40:
            return p
    return ""


def extract_infobox(soup: BeautifulSoup) -> Dict[str, str]:
    data: Dict[str, str] = {}

    for row in soup.select(".portable-infobox .pi-item"):
        label = row.select_one(".pi-data-label")
        value = row.select_one(".pi-data-value")
        if label and value:
            k = text_from_node(label)
            v = text_from_node(value)
            if k and v:
                data[k] = v

    for row in soup.select("table.infobox tr"):
        header = row.find(["th", "td"], class_=re.compile(r"label|header", re.I))
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            key = text_from_node(cells[0])
            value = text_from_node(cells[-1])
            if key and value and key != value:
                data.setdefault(key, value)
        elif header and len(cells) == 2:
            key = text_from_node(header)
            value = text_from_node(cells[1])
            if key and value:
                data.setdefault(key, value)

    return data


def heading_text(node: Tag) -> str:
    headline = node.select_one(".mw-headline")
    text = headline.get_text(" ", strip=True) if headline else node.get_text(" ", strip=True)
    text = clean_text(text).replace("[edit]", "").strip()
    text = re.sub(r"\[\]$", "", text).strip()
    return text


def iter_section_nodes(content: Tag):
    for child in content.children:
        if isinstance(child, NavigableString):
            continue
        if isinstance(child, Tag):
            yield child


def extract_sections(content: Tag) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {}
    current_heading: Optional[str] = None

    for child in iter_section_nodes(content):
        if child.name in {"h2", "h3", "h4"}:
            title = heading_text(child)
            if not title:
                current_heading = None
                continue
            current_heading = title
            sections.setdefault(current_heading, [])
            continue

        if not current_heading:
            continue

        if child.name == "p":
            text = text_from_node(child)
            if text:
                sections[current_heading].append(text)
        elif child.name in {"ul", "ol"}:
            for li in child.select("li"):
                text = text_from_node(li)
                if text:
                    sections[current_heading].append(text)
        elif child.name == "dl":
            for item in child.find_all(["dt", "dd"], recursive=False):
                text = text_from_node(item)
                if text:
                    sections[current_heading].append(text)

    return {k: dedupe_keep_order(v) for k, v in sections.items() if v}


def merge_sections(raw_sections: Dict[str, List[str]]) -> Dict[str, List[str]]:
    merged = {"appearance": [], "personality": [], "abilities": [], "relationships": [], "history": []}
    uncategorized: Dict[str, List[str]] = {}

    for heading, blocks in raw_sections.items():
        category = classify_section(heading)
        if category:
            merged[category].extend(blocks)
        else:
            uncategorized[heading] = blocks

    merged = {k: dedupe_keep_order(v) for k, v in merged.items()}
    merged["uncategorized"] = uncategorized
    return merged


def infer_franchise(normalized_infobox: Dict[str, str], infobox: Dict[str, str], title: str, url: str) -> str:
    candidates = [
        normalized_infobox.get("origin", ""),
        infobox.get("Series", ""),
        infobox.get("Origin", ""),
        infobox.get("Game", ""),
    ]
    for candidate in candidates:
        if candidate:
            return candidate

    host_match = re.search(r"https?://([^.]+)\.fandom\.com", url)
    if host_match:
        host = host_match.group(1).replace("-", " ").strip()
        if host:
            return host.title()

    return ""


def build_profile_lists(summary: str, merged: Dict[str, List[str]], normalized_infobox: Dict[str, str]) -> Dict[str, List[str] | str]:
    appearance_bits = []
    personality_bits = []
    abilities_bits = []
    history_bits = []

    for text in merged["appearance"]:
        appearance_bits.extend(split_traits(text))
    for text in merged["personality"]:
        personality_bits.extend(split_traits(text))
    for text in merged["abilities"]:
        abilities_bits.extend(split_traits(text))
    for text in merged["history"]:
        history_bits.extend(split_traits(text, max_len=240))

    if normalized_infobox.get("hair"):
        appearance_bits.append(f"Hair: {normalized_infobox['hair']}")
    if normalized_infobox.get("eyes"):
        appearance_bits.append(f"Eyes: {normalized_infobox['eyes']}")
    if normalized_infobox.get("height"):
        appearance_bits.append(f"Height: {normalized_infobox['height']}")
    if normalized_infobox.get("weight"):
        appearance_bits.append(f"Weight: {normalized_infobox['weight']}")
    if normalized_infobox.get("weapons"):
        abilities_bits.append(f"Weapon: {normalized_infobox['weapons']}")
    if normalized_infobox.get("occupation"):
        history_bits.insert(0, f"Occupation/Role: {normalized_infobox['occupation']}")
    if normalized_infobox.get("affiliation"):
        history_bits.insert(0, f"Affiliation: {normalized_infobox['affiliation']}")

    if summary and not history_bits:
        history_bits.extend(split_traits(summary, max_len=220))

    return {
        "appearance_list": dedupe_keep_order(appearance_bits),
        "personality_traits": dedupe_keep_order(personality_bits),
        "abilities_list": dedupe_keep_order(abilities_bits),
        "history_list": dedupe_keep_order(history_bits),
    }


def parse_page(html: str, fallback_title: Optional[str] = None, url: str = "") -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    remove_noise(soup)

    content = soup.select_one(".mw-parser-output") or soup.select_one("main") or soup
    summary = extract_summary(content)
    infobox = extract_infobox(soup)
    raw_sections = extract_sections(content)
    merged = merge_sections(raw_sections)
    normalized_infobox = normalize_infobox(infobox)
    list_views = build_profile_lists(summary, merged, normalized_infobox)

    title = fallback_title or text_from_node(soup.select_one("h1") or soup.title or soup)
    franchise = infer_franchise(normalized_infobox, infobox, title, url)

    return {
        "title": title,
        "summary": summary,
        "franchise": franchise,
        "appearance": "\n".join(merged["appearance"]),
        "personality": "\n".join(merged["personality"]),
        "abilities": "\n".join(merged["abilities"]),
        "relationships": "\n".join(merged["relationships"]),
        "history": "\n".join(merged["history"]),
        "appearance_list": list_views["appearance_list"],
        "personality_traits": list_views["personality_traits"],
        "abilities_list": list_views["abilities_list"],
        "history_list": list_views["history_list"],
        "infobox": infobox,
        "normalized_infobox": normalized_infobox,
        "raw_sections": raw_sections,
        "uncategorized_sections": merged["uncategorized"],
    }


def fetch_via_mediawiki_api(wiki_base: str, page_name: str, session: Optional[requests.Session] = None) -> Tuple[str, str]:
    sess = session or requests.Session()
    params = {
        "action": "parse",
        "page": page_name,
        "prop": "text",
        "format": "json",
        "formatversion": 2,
    }
    headers = {"User-Agent": USER_AGENT}
    response = sess.get(f"{wiki_base.rstrip('/')}/api.php", params=params, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    title = data["parse"]["title"]
    html = data["parse"]["text"]
    return title, html


def fetch_generic_page(url: str, session: Optional[requests.Session] = None) -> Tuple[str, str]:
    sess = session or requests.Session()
    headers = {"User-Agent": USER_AGENT}
    response = sess.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    title = text_from_node(soup.select_one("h1") or soup.title or soup)
    return title, html


def scrape_fandom_page(wiki_base: str, page_name: str, session: Optional[requests.Session] = None) -> Dict[str, Any]:
    wiki_base = wiki_base.rstrip("/")
    title, html = fetch_via_mediawiki_api(wiki_base, page_name, session=session)
    url = f"{wiki_base}/wiki/{quote(page_name.replace(' ', '_'))}"
    parsed = parse_page(html, fallback_title=title, url=url)
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


def scrape_url(url: str, session: Optional[requests.Session] = None) -> Dict[str, Any]:
    session = session or requests.Session()
    url = url.strip()

    # Match Fandom URLs in all common forms:
    #   https://gundam.fandom.com/wiki/Gigi_Andalucia   (standard)
    #   https://gundam.fandom.com/en/wiki/Gigi_Andalucia (lang prefix)
    #   https://gundam.fandom.com/Gigi_Andalucia         (bare, no /wiki/)
    fandom_match = re.match(
        r"^(https?://[^/]+\.fandom\.com)"
        r"(?:/(?:[a-z]{2}(?:-[a-z]{2})?/)?wiki)?/(.+)$",
        url,
    )
    if fandom_match:
        wiki_base = fandom_match.group(1)
        page_name = fandom_match.group(2).replace("_", " ")
        try:
            return scrape_fandom_page(wiki_base, page_name, session=session)
        except Exception as e:
            print(f"[SCRAPER] Fandom API failed for {url!r}: {e} — falling back to generic fetch")

    title, html = fetch_generic_page(url, session=session)
    parsed = parse_page(html, fallback_title=title, url=url)
    return {
        "wiki_base": re.sub(r"/+$", "", re.match(r"^(https?://[^/]+)", url).group(1)) if re.match(r"^(https?://[^/]+)", url) else "",
        "page_name": title,
        "url": url,
        "title": title,
        "raw_html": html,
        "raw_infobox": parsed["infobox"],
        "raw_sections": parsed["raw_sections"],
        "normalized": parsed,
    }


if __name__ == "__main__":
    example_url = "https://soulcalibur.fandom.com/wiki/Ivy"
    result = scrape_url(example_url)
    print("Title:", result["title"])
    print("Summary:", result["normalized"]["summary"][:250], "...")
    print("Infobox keys:", list(result["raw_infobox"].keys())[:10])
    print("Section keys:", list(result["raw_sections"].keys())[:10])
    print("Personality traits:", result["normalized"]["personality_traits"][:8])