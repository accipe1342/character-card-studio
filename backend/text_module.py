"""
text_module.py — TEXT studio backend (fanfiction / long-form text -> lorebook)
================================================================================
A self-contained Flask Blueprint. It is registered from app.py with:

    from text_module import register_text_module
    register_text_module(app, create_job, update_job)

PIPELINE
--------
1. INGEST   paste text / upload .txt .md .html .epub / fetch URLs (AO3-aware)
             -> stored in text_projects, split into ~6k-char chunks on
             chapter boundaries.
2. EXTRACT  one LLM call per chunk -> entities (characters, places, factions,
             events, items, concepts) with age, short facts, voice samples.
             Per-chunk results are saved, so a failed run resumes.
3. MERGE    alias-based dedupe across chunks ("Dr. Smith" == "Smith"), then an
             optional LLM condense pass for entities mentioned many times.
4. REVIEW   entities live in text_entities; the UI lets you edit / merge /
             delete / keep. Age flags: 'minor', 'check', 'unknown'.
5. COMMIT   kept entities become lore_entries in a NEW Lore project, so the
             existing LORE studio and /api/lore/export take over.

TABLES (created on startup): text_projects, text_chunk_results, text_entities

ENDPOINTS
---------
POST   /api/text/ingest                 text or file (multipart) -> project
POST   /api/text/ingest-urls            urls[] (+follow_next) -> job
GET    /api/text/projects               list
GET    /api/text/project/<id>           project + chunk status + entities
DELETE /api/text/project/<id>
POST   /api/text/project/<id>/rechunk   {chunk_chars}
POST   /api/text/project/<id>/extract   {provider, model, condense, force, merge_only} -> job
POST   /api/text/project/<id>/merge     {ids:[entity ids]}  manual merge
POST   /api/text/project/<id>/commit    -> new lore project
PATCH  /api/text/entity/<id>            edit
DELETE /api/text/entity/<id>

CONTENT RULE
------------
The extraction prompt forbids romantic/sexual details for anyone who is or
appears to be under 18, and records ages so the review screen can flag them.
"""

import hashlib
import io
import json
import re
import sys
import threading
import time
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Blueprint, jsonify, request

from database import (_conn, create_lore_project, create_or_update_card, get_card, list_lore_projects,
                      save_lore_entry, save_source)
from preview import build_export_card_json, character_book_from_items, normalise_lore_items
from generator import _request
from lore_extract import extract_chunk_deep, norm_origin, norm_relations

bp = Blueprint("text_module", __name__)
_create_job = None
_update_job = None

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)
MAX_TOTAL_CHARS = 3_000_000
DEFAULT_CHUNK_CHARS = 4000
URL_DELAY_SECONDS = 2.0

ENTITY_TYPES = {"character", "place", "faction", "event", "item", "ability", "concept"}
TYPE_ALIASES = {
    "rule": "concept", "world": "concept", "organization": "faction",
    "organisation": "faction", "group": "faction", "location": "place",
    "setting": "place", "object": "item", "artifact": "item", "power": "ability",
    "magic": "ability", "person": "character", "npc": "character",
}


def _log(msg):
    sys.stdout.write(f"[TEXT] {time.strftime('%H:%M:%S')} {msg}\n")  # one write per line so threads don't interleave
    sys.stdout.flush()


# ══════════════════════════════════════════════════════════════════════════════
# DB
# ══════════════════════════════════════════════════════════════════════════════
def init_text_tables():
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS text_critiques (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            scope TEXT DEFAULT '',
            focus TEXT DEFAULT '',
            provider TEXT DEFAULT '',
            model TEXT DEFAULT '',
            result_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS text_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            origin TEXT DEFAULT 'paste',
            raw_text TEXT NOT NULL,
            chunks_json TEXT NOT NULL DEFAULT '[]',
            chunk_chars INTEGER DEFAULT 6000,
            status TEXT DEFAULT 'ingested',
            lore_project_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS text_chunk_results (
            project_id INTEGER NOT NULL,
            idx INTEGER NOT NULL,
            result_json TEXT NOT NULL,
            PRIMARY KEY (project_id, idx)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS text_entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            aliases_json TEXT DEFAULT '[]',
            entity_type TEXT DEFAULT 'concept',
            age TEXT DEFAULT '',
            age_flag TEXT DEFAULT '',
            keywords_json TEXT DEFAULT '[]',
            summary TEXT DEFAULT '',
            content TEXT DEFAULT '',
            voice_json TEXT DEFAULT '[]',
            mentions INTEGER DEFAULT 1,
            keep INTEGER DEFAULT 1,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    for table, col in (("text_entities", "evidence TEXT DEFAULT ''"), ("text_entities", "confidence TEXT DEFAULT ''"),
                       ("text_entities", "story_order TEXT DEFAULT ''"),
                       ("text_entities", "deleted INTEGER DEFAULT 0"),      # in the trash (restorable)
                       ("text_entities", "edited INTEGER DEFAULT 0"),       # hand-edited in review: survives Rebuild list / re-extract
                       ("text_entities", "origin TEXT DEFAULT ''"),         # canon | altered | original
                       ("text_entities", "relations_json TEXT DEFAULT '[]'"),
                       ("text_entities", "first_chunk INTEGER DEFAULT -1"),
                       ("text_projects", "recap_text TEXT DEFAULT ''"),     # hand-edited Story So Far ('' = automatic)
                       ("text_projects", "recap_upto INTEGER DEFAULT -1"),  # roleplay starts after this chunk (-1 = end)
                       ("text_projects", "timeline_text TEXT DEFAULT ''"),
                       ("text_projects", "recap_position TEXT DEFAULT 'before'")):  # before (card) | depth (@4, system)  # AI/hand-written chapter log ('' = event lines)
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col}")
            conn.commit()
        except Exception:
            pass  # column already exists
    conn.close()


def _row_entity(r):
    d = dict(r)
    for k in ("aliases", "keywords", "voice", "relations"):
        try:
            d[k] = json.loads(d.pop(f"{k}_json", None) or "[]")
        except Exception:
            d[k] = []
    d["keep"] = bool(d.get("keep"))
    d["deleted"] = bool(d.get("deleted"))
    d["edited"] = bool(d.get("edited"))
    d.setdefault("origin", "")
    d.setdefault("first_chunk", -1)
    return d


def _entities(project_id, trash=False):
    """Live entries (or, with trash=True, the deleted ones waiting in the trash)."""
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM text_entities WHERE project_id=? AND COALESCE(deleted,0)=? "
        "ORDER BY entity_type, name COLLATE NOCASE",
        (project_id, 1 if trash else 0),
    ).fetchall()
    conn.close()
    return [_row_entity(r) for r in rows]


def entity_tier(e, chunk_total):
    """main / supporting / one-off, from how many chunks mention the entry (events have no tier)."""
    if e["entity_type"] == "event":
        return ""
    m = int(e.get("mentions") or 1)
    if m >= max(3, -(-chunk_total // 5)) or (e["entity_type"] == "character" and m >= 3):
        return "main"
    return "supporting" if m >= 2 else "one-off"


ENTITY_COLS = ("name", "aliases_json", "entity_type", "age", "age_flag", "keywords_json", "summary", "content",
               "voice_json", "mentions", "keep", "evidence", "confidence", "story_order", "deleted", "edited",
               "origin", "relations_json", "first_chunk")


def _insert_entity(conn, pid, d):
    vals = {
        "name": d["name"], "aliases_json": json.dumps(d.get("aliases") or [], ensure_ascii=False),
        "entity_type": d.get("entity_type") or d.get("type") or "concept", "age": d.get("age") or "",
        "age_flag": d.get("age_flag") or "", "keywords_json": json.dumps(d.get("keywords") or [], ensure_ascii=False),
        "summary": d.get("summary") or "", "content": d.get("content") or "",
        "voice_json": json.dumps(d.get("voice") or [], ensure_ascii=False), "mentions": int(d.get("mentions") or 1),
        "keep": 1 if d.get("keep", True) else 0, "evidence": d.get("evidence") or "",
        "confidence": d.get("confidence") or "", "story_order": d.get("story_order") or "",
        "deleted": 1 if d.get("deleted") else 0, "edited": 1 if d.get("edited") else 0,
        "origin": d.get("origin") or "", "relations_json": json.dumps(d.get("relations") or [], ensure_ascii=False),
        "first_chunk": int(d.get("first_chunk", -1) if d.get("first_chunk") is not None else -1),
    }
    conn.execute(f"INSERT INTO text_entities (project_id,{','.join(ENTITY_COLS)}) VALUES (?{',?' * len(ENTITY_COLS)})",
                 [pid] + [vals[c] for c in ENTITY_COLS])


def _project_row(project_id):
    conn = _conn()
    r = conn.execute("SELECT * FROM text_projects WHERE id=?", (project_id,)).fetchone()
    conn.close()
    return r


# ══════════════════════════════════════════════════════════════════════════════
# Text cleaning + chunking
# ══════════════════════════════════════════════════════════════════════════════
_NUM_WORDS = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
              r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty)")
# A heading must be "Chapter 3", "Part II", "Act one", "Prologue" ... optionally followed by ": title".
# Ordinary lines that merely start with the word ("Act normal.", "Part of me wanted...") do NOT match.
CHAPTER_RE = re.compile(
    r"^\s*(?:(?:chapter|part|book|act|episode|arc|ch\.?)(?:\s+|(?=\d))(?:\d+|[ivxlc]+|" + _NUM_WORDS + r")(?![a-z0-9])"
    r"|(?:prologue|epilogue|interlude|intermission|omake|afterword|foreword))"
    r"\s*(?:[:.\-–—)]\s*[^\n]{0,80})?\s*$",
    re.I,
)

MIN_SECTION_CHARS = 400

# ── mojibake / replacement-character repair ──────────────────────────────────
_MOJIBAKE = [
    ("â€™", "’"), ("â€˜", "‘"), ("â€œ", "“"),
    ("â€”", "—"), ("â€“", "–"), ("â€¦", "…"),
    ("â€\u009d", "”"), ("â€", "”"), ("Â ", " "),
]


def fix_replacement_chars(text: str) -> str:
    """Many old fics lost their curly quotes / apostrophes / dashes and show U+FFFD instead.
    Rebuild them from context (don�t -> don’t, �Hi!� -> “Hi!”) rather than
    deleting them, so names and contractions stay readable for the model."""
    for bad, good in _MOJIBAKE:
        text = text.replace(bad, good)
    if "�" not in text:
        return text
    t = text
    t = re.sub(r"(?<=[A-Za-z])�(?=(?:t|s|m|d|re|ll|ve)\b)", "’", t)          # contractions / possessives
    t = re.sub(r"(?:^|(?<=[\s(\[—–-]))�(?=\S)", "“", t, flags=re.M)  # opening quote
    t = re.sub(r"(?<=\S)�(?=\s|$|[,.;:!?)\]])", "”", t, flags=re.M)           # closing quote
    t = re.sub(r"(?<=[A-Za-z0-9.,!?])�(?=[A-Za-z])", "—", t)                  # dash between words
    return t.replace("�", "")                                                        # anything left


def decode_bytes(data: bytes) -> str:
    """UTF-8 if it is valid UTF-8, otherwise Windows-1252 (what most old fic exports are)."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", "replace")


# ── site chrome (menus, nav, icon names, chapter dropdowns) ──────────────────
_ICON_SNAKE = re.compile(r"^[a-z]+(?:_[a-z]+)+$")
_ICON_WORDS = {"folder", "flag", "bookmark", "favorite", "visibility", "person", "login", "logout",
               "settings", "print", "download", "share", "menu"}
_NAV_LINE = re.compile(
    r"^(?:previous|prev|next|previous chapter|next chapter|back to top|report story|write a review|"
    r"view reviews?(?: \(\d+\))?|add to favou?rites|skip to (?:main )?content|table of contents|"
    r"back to archive|back to [^\n.!?\"“”]{1,60}|read more|log ?in|sign in|register)$", re.I)
_META_KEY = re.compile(
    r"^(?:by|rating|chapters?|views?|reviews?|recommended|currently reading|category|categories|words?|"
    r"status|published|updated|genre|characters?|pairings?|warnings?|language|fandom|tags|series|author|"
    r"posted|completed):$", re.I)
_BREADCRUMB = re.compile(r"\s[›»]\s")


def strip_boilerplate(text: str) -> str:
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s and len(s) < 140:
            if _ICON_SNAKE.match(s) or s in _ICON_WORDS or (len(s) < 70 and _NAV_LINE.match(s)) \
                    or _BREADCRUMB.search(s):
                i += 1
                continue
            if _META_KEY.match(s):  # "Rating:" + short value line
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and len(lines[j].strip()) <= 60:
                    i = j + 1
                    continue
        out.append(lines[i])
        i += 1

    # chapter dropdowns: 2+ consecutive "Chapter N - title" lines are a menu, not story text
    res, k = [], 0
    while k < len(out):
        if out[k].strip() and CHAPTER_RE.match(out[k]) and len(out[k].strip()) < 90:
            run = [k]
            m = k + 1
            while m < len(out):
                if not out[m].strip():
                    m += 1
                    continue
                if CHAPTER_RE.match(out[m]) and len(out[m].strip()) < 90:
                    run.append(m)
                    m += 1
                    continue
                break
            if len(run) >= 2:
                # keep "Chapter N: title" lines (our own page headers use that form); the dash/dot
                # forms are dropdown options. Any colon-form menu leftovers are tiny sections that
                # chunk_text folds into the next one.
                for ri in run:
                    if re.match(r"^\s*chapter\s+\d+\s*:", out[ri], re.I):
                        res.append(out[ri])
                k = m
                continue
        res.append(out[k])
        k += 1
    return "\n".join(res)


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    text = fix_replacement_chars(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = strip_boilerplate(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # single-newline prose (from get_text) -> paragraphs, so chunk packing has boundaries to use
    return text.strip()


def _split_sections(text):
    sections, label, buf = [], "Start", []
    for line in text.split("\n"):
        if CHAPTER_RE.match(line) and len(line.strip()) < 90:
            if "".join(buf).strip():
                sections.append((label, "\n".join(buf).strip()))
            label, buf = line.strip(), []
        else:
            buf.append(line)
    if "".join(buf).strip():
        sections.append((label, "\n".join(buf).strip()))
    return sections


def _split_long_paragraph(p, limit):
    sents = re.split(r"(?<=[.!?])\s+", p)
    out, cur = [], ""
    for s in sents:
        if len(cur) + len(s) + 1 > limit and cur:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


def _sig(s: str) -> str:
    return hashlib.md5(re.sub(r"\s+", " ", s).strip().lower().encode("utf8", "ignore")).hexdigest()


def chunk_text(text: str, target: int = DEFAULT_CHUNK_CHARS):
    """Split on real chapter headings, fold tiny sections into their neighbour, drop exact
    duplicates, then pack paragraphs up to ~target chars."""
    target = max(1500, min(int(target or DEFAULT_CHUNK_CHARS), 20000))

    # 1. sections: drop exact repeats, fold tiny ones (headers, author-note scraps) into the next
    seen, uniq = set(), []
    for label, body in _split_sections(clean_text(text)):
        sg = _sig(body)
        if sg in seen:
            continue
        seen.add(sg)
        uniq.append((label, body))
    sections, carry = [], ""
    for label, body in uniq:
        if carry:
            body = f"{carry}\n\n{body}"
            carry = ""
        if len(body) < MIN_SECTION_CHARS:
            carry = f"[{label}]\n{body}" if label != "Start" else body
            continue
        sections.append([label, body])
    if carry:
        if sections:
            sections[-1][1] += "\n\n" + carry
        else:
            sections.append(["Start", carry])

    # 2. pack
    chunks, seen_chunks = [], set()
    for label, body in sections:
        paras = []
        for p in re.split(r"\n\s*\n|\n", body) if body.count("\n\n") < 3 else re.split(r"\n\s*\n", body):
            p = p.strip()
            if not p:
                continue
            paras.extend(_split_long_paragraph(p, target) if len(p) > target * 1.5 else [p])
        parts, cur = [], ""
        for p in paras:
            if cur and len(cur) + len(p) + 2 > target:
                parts.append(cur)
                cur = p
            else:
                cur = f"{cur}\n\n{p}".strip()
        if cur:
            parts.append(cur)
        if len(parts) > 1 and len(parts[-1]) < target * 0.25:  # no tiny trailing chunk
            last = parts.pop()
            parts[-1] += "\n\n" + last
        uniq_parts = []
        for part in parts:
            sg = _sig(part)
            if sg in seen_chunks:
                continue
            seen_chunks.add(sg)
            uniq_parts.append(part)
        for k, part in enumerate(uniq_parts):
            lab = label if len(uniq_parts) == 1 else f"{label} (part {k + 1}/{len(uniq_parts)})"
            chunks.append({"idx": len(chunks), "label": lab, "text": part})
    return chunks


# ══════════════════════════════════════════════════════════════════════════════
# Source readers: html / epub / url
# ══════════════════════════════════════════════════════════════════════════════
def _paras(root):
    ps = [p.get_text(" ", strip=True) for p in root.find_all("p")]
    ps = [p for p in ps if p]
    return "\n\n".join(ps) if ps else root.get_text("\n", strip=True)


def html_to_text(html: str):
    """Return (title, text). AO3 / FFN / generic aware."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "nav", "footer", "header", "select", "button", "form", "aside"]):
        t.decompose()
    title = ""
    h = soup.select_one("h2.title.heading") or soup.select_one("h1") or soup.title
    if h:
        title = h.get_text(" ", strip=True)

    # AO3 full work: several chapter divs
    chapters = soup.select("#chapters > div[id^=chapter-]") or soup.select("#chapters div[id^=chapter-]")
    if chapters:
        out = []
        for i, ch in enumerate(chapters, 1):
            t = ch.select_one("h3.title")
            body = ch.select_one("div.userstuff[role=article]") or ch.select_one("div.userstuff")
            if body:
                for junk in body.select("h3.landmark"):
                    junk.decompose()
                head = t.get_text(" ", strip=True) if t else ""
                out.append(f"Chapter {i}: {head}".strip() + "\n\n" + _paras(body))
        if out:
            return title, "\n\n".join(out)

    for sel in ("#chapters div.userstuff", "div.userstuff[role=article]", "#storytext",
                "article", ".chapter-content", "#chapter-content", ".entry-content", "main"):
        node = soup.select_one(sel)
        if node:
            return title, _paras(node)
    return title, _paras(soup.body or soup)


def epub_to_text(data: bytes):
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    order = []
    try:
        cont = z.read("META-INF/container.xml").decode("utf8", "ignore")
        opf_path = re.search(r'full-path="([^"]+)"', cont).group(1)
        opf = z.read(opf_path).decode("utf8", "ignore")
        base = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""
        manifest = {}
        for m in re.finditer(r"<item\b[^>]*>", opf):
            tag = m.group(0)
            i = re.search(r'\bid="([^"]+)"', tag)
            h = re.search(r'\bhref="([^"]+)"', tag)
            if i and h:
                manifest[i.group(1)] = h.group(1)
        for m in re.finditer(r'<itemref\b[^>]*idref="([^"]+)"', opf):
            href = manifest.get(m.group(1))
            if href:
                order.append(base + href.split("#")[0])
    except Exception:
        pass
    if not order:
        order = sorted(n for n in names if n.lower().endswith((".xhtml", ".html", ".htm")))
    title = ""
    mt = re.search(r"<dc:title[^>]*>(.*?)</dc:title>", locals().get("opf", ""), re.S)
    if mt:
        title = re.sub(r"<[^>]+>", "", mt.group(1)).strip()
    parts = []
    for n in order:
        if n in names:
            soup = BeautifulSoup(z.read(n).decode("utf8", "ignore"), "html.parser")
            heading = soup.find(["h1", "h2", "h3"])
            body = _paras(soup.body or soup)
            if len(body) < 80:
                continue
            if heading and not CHAPTER_RE.match(heading.get_text(" ", strip=True)):
                body = f"Chapter: {heading.get_text(' ', strip=True)}\n\n{body}"
            parts.append(body)
    return title, "\n\n".join(parts)


CHAT_PART_MESSAGES = 40     # a "Part N" heading every this many chat messages, so chunks get readable labels


def stchat_to_text(data: bytes):
    """A SillyTavern chat export (.jsonl: a metadata line, then one message per line) -> (title, text).
    Hidden/system messages are skipped; each message becomes 'Name: text'."""
    raw = decode_bytes(data) if isinstance(data, (bytes, bytearray)) else str(data)
    meta, msgs = {}, []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        if "mes" not in obj:
            meta = meta or obj
            continue
        if obj.get("is_system") or not str(obj.get("mes") or "").strip():
            continue
        msgs.append(obj)
    if not msgs:
        raise ValueError("No chat messages found. Export the chat from SillyTavern as .jsonl.")
    out = []
    for i, m in enumerate(msgs):
        if i % CHAT_PART_MESSAGES == 0:
            out.append(f"Part {i // CHAT_PART_MESSAGES + 1}: messages {i + 1}-{min(len(msgs), i + CHAT_PART_MESSAGES)}")
        name = str(m.get("name") or ("You" if m.get("is_user") else "Character")).strip()
        text = re.sub(r"\n{3,}", "\n\n", str(m["mes"]).strip())
        out.append(f"{name}: {text}")
    title = f"Chat with {meta.get('character_name')}" if meta.get("character_name") else "SillyTavern chat"
    return title, "\n\n".join(out)


def normalize_url(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?archiveofourown\.(?:org|gay)/works/(\d+)", url)
    if m:  # whole work in one page, skip the adult-content interstitial
        return f"https://archiveofourown.org/works/{m.group(1)}?view_adult=true&view_full_work=true"
    return url


WIKI_PATH_RE = re.compile(r"^/(?:[a-z]{2,3}(?:-[a-z]+)?/)?wiki/(.+)$")
WIKI_JUNK = (".mw-editsection, .reference, .reflist, .references, #toc, .toc, .navbox, .navigation-not-searchable, "
             "table.metadata, .mbox, .ambox, .noprint, .gallery, figure, .thumb, sup, .portable-infobox, .infobox, "
             "style, script")


def wiki_api_candidates(url: str):
    """MediaWiki api.php URLs (action=parse) for a /wiki/Title page, or [] for any other URL."""
    u = urlparse(url)
    m = WIKI_PATH_RE.match(u.path)
    if not m:
        return []
    title = unquote(m.group(1)).replace("_", " ")
    if ":" in title and title.split(":")[0].strip() in ("Special", "Category", "File", "Template", "User", "Talk", "Help"):
        return []
    lang = u.path.split("/wiki/")[0]          # Fandom language wikis: /fr/wiki/...
    q = {"action": "parse", "page": title, "format": "json", "prop": "text|displaytitle", "redirects": "1",
         "disableeditsection": "1", "formatversion": "2"}
    base = f"{u.scheme}://{u.netloc}"
    return [(f"{base}{lang}/api.php", q), (f"{base}/w/api.php", q)]


def mediawiki_text(html: str, title: str = ""):
    """Readable text from MediaWiki parse output: the infobox as 'Label: value' lines, then headings, paragraphs
    and list items in page order (no references, navboxes, edit links or galleries)."""
    soup = BeautifulSoup(html, "html.parser")
    facts = []
    for box in soup.select(".portable-infobox, table.infobox"):
        for row in box.select(".pi-data, tr"):
            lab = row.select_one(".pi-data-label, th")
            val = row.select_one(".pi-data-value, td")
            if lab and val:
                lt, vt = lab.get_text(" ", strip=True), val.get_text(", ", strip=True)
                if lt and vt and len(vt) < 300:
                    facts.append(f"{lt}: {vt}")
    for junk in soup.select(WIKI_JUNK):
        junk.decompose()
    lines = []
    for node in soup.find_all(["h2", "h3", "h4", "p", "li", "dd"]):
        if node.name == "li" and node.find_parent(["li"]):
            continue
        txt = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        txt = re.sub(r"\s+([,.;:!?])", r"\1", txt)
        if not txt:
            continue
        if node.name in ("h2", "h3", "h4"):
            if txt.lower() in ("references", "external links", "see also", "navigation", "gallery", "notes", "sources"):
                continue
            lines.append(f"\n{'#' * int(node.name[1])} {txt}")
        elif node.name == "li":
            lines.append(f"- {txt}")
        else:
            lines.append(txt)
    body = "\n\n".join(l for l in lines)
    head = (f"{title}\n\n" if title else "") + ("\n".join(facts) + "\n\n" if facts else "")
    return (head + body).strip()


def fetch_wiki_page(url: str):
    """(title, text) through the wiki's own API, or None when the URL is not a MediaWiki page or the API fails."""
    for api, q in wiki_api_candidates(url):
        try:
            r = requests.get(api, params=q, headers={"User-Agent": USER_AGENT}, timeout=30)
            if r.status_code != 200:
                continue
            data = r.json()
            parse = data.get("parse") or {}
            html = parse.get("text")
            if isinstance(html, dict):       # formatversion=1 shape
                html = html.get("*")
            if not html:
                continue
            title = re.sub(r"<[^>]+>", "", str(parse.get("displaytitle") or parse.get("title") or "")).strip()
            text = mediawiki_text(html, title)
            if len(text) >= 200:
                _log(f"wiki page via {api}: '{title}' {len(text):,} chars")
                return title, text
        except Exception as e:      # not a MediaWiki, or blocked: fall back to fetching the page
            _log(f"wiki API {api} failed: {str(e)[:100]}")
    return None


def fetch_page(url: str):
    wiki = fetch_wiki_page(url)
    if wiki:
        return wiki[0], wiki[1], None
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    if r.status_code in (403, 429, 503):
        raise RuntimeError(
            f"{url} blocked the request (HTTP {r.status_code}). Sites behind bot protection "
            "(e.g. FanFiction.net) can't be scraped; paste the text or upload an .epub/.html instead."
        )
    r.raise_for_status()
    html = decode_bytes(r.content)
    soup = BeautifulSoup(html, "html.parser")
    nxt = None
    a = soup.select_one("a[rel=next]")
    if not a:
        for cand in soup.find_all("a"):
            if re.match(r"^\s*(next( chapter)?|›|»)\s*$", cand.get_text(" ", strip=True), re.I):
                a = cand
                break
    if a and a.get("href"):
        nxt = urljoin(url, a["href"])
    title, text = html_to_text(html)
    return title, text, nxt


# ══════════════════════════════════════════════════════════════════════════════
# Ingest routes
# ══════════════════════════════════════════════════════════════════════════════
def _create_project(name, origin, text, chunk_chars):
    raw_len, bad = len(text), text.count("\ufffd")
    text = clean_text(text)
    _log(f"clean: {raw_len:,} -> {len(text):,} chars ({raw_len - len(text):,} removed as menus/blank space; "
         f"{bad} broken quote/apostrophe characters repaired)")
    if len(text) < 200:
        raise ValueError("Not enough text found (under 200 characters).")
    if len(text) > MAX_TOTAL_CHARS:
        raise ValueError(f"Text too large ({len(text):,} chars; max {MAX_TOTAL_CHARS:,}).")
    chunks = chunk_text(text, chunk_chars)
    if chunks:
        sizes = [len(c["text"]) for c in chunks]
        _log(f"chunking: {len(chunks)} chunks (target {chunk_chars}), size min/avg/max "
             f"{min(sizes):,}/{sum(sizes) // len(sizes):,}/{max(sizes):,}")
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO text_projects (name, origin, raw_text, chunks_json, chunk_chars) VALUES (?,?,?,?,?)",
        (name or "Untitled Text", origin, text, json.dumps(chunks, ensure_ascii=False), chunk_chars),
    )
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid, len(text), len(chunks)


@bp.post("/api/text/ingest")
def api_text_ingest():
    try:
        chunk_chars = DEFAULT_CHUNK_CHARS
        if request.files.get("file"):
            f = request.files["file"]
            name = (request.form.get("name") or f.filename or "Untitled Text").rsplit(".", 1)[0]
            chunk_chars = int(request.form.get("chunk_chars") or DEFAULT_CHUNK_CHARS)
            data = f.read()
            ext = (f.filename or "").lower().rsplit(".", 1)[-1]
            if ext == "epub":
                t, text = epub_to_text(data)
                name = request.form.get("name") or t or name
                origin = "epub"
            elif ext == "jsonl":
                t, text = stchat_to_text(data)
                name = request.form.get("name") or t or name
                origin = "st-chat"
            elif ext in ("html", "htm", "xhtml"):
                t, text = html_to_text(decode_bytes(data))
                name = request.form.get("name") or t or name
                origin = "html"
            else:
                text = decode_bytes(data)
                origin = "file"
        else:
            body = request.get_json(force=True) or {}
            text = body.get("text", "")
            name = (body.get("name") or "Untitled Text").strip()
            chunk_chars = int(body.get("chunk_chars") or DEFAULT_CHUNK_CHARS)
            origin = "paste"
        pid, n_chars, n_chunks = _create_project(name, origin, text, chunk_chars)
        _log(f"ingest id={pid} chars={n_chars} chunks={n_chunks} origin={origin}")
        return jsonify({"id": pid, "name": name, "chars": n_chars, "chunks": n_chunks})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/api/text/ingest-urls")
def api_text_ingest_urls():
    body = request.get_json(force=True) or {}
    urls = [u.strip() for u in body.get("urls", []) if u and u.strip()]
    if not urls:
        return jsonify({"error": "No URLs provided"}), 400
    name = (body.get("name") or "").strip()
    follow = bool(body.get("follow_next"))
    max_pages = max(1, min(int(body.get("max_pages") or 30), 200))
    chunk_chars = int(body.get("chunk_chars") or DEFAULT_CHUNK_CHARS)
    job_id = _create_job()

    def run():
        try:
            parts, titles, seen, fetched = [], [], set(), 0
            page_sigs, skipped_dupes = set(), 0
            queue = [normalize_url(u) for u in urls]
            while queue and fetched < max_pages:
                url = queue.pop(0)
                ukey = url.split("#")[0].rstrip("/")
                if ukey in seen:
                    continue
                seen.add(ukey)
                _update_job(job_id, status="running", stage="fetching_page",
                            progress=min(5 + int(fetched / max_pages * 80), 85),
                            message=f"Fetching page {fetched + 1}: {url[:70]}")
                t_fetch = time.time()
                title, text, nxt = fetch_page(url)
                fetched += 1
                _log(f"fetched page {fetched}: {url[:80]} -> {len(text):,} chars in {time.time() - t_fetch:.1f}s"
                     + (f", next: {nxt[:70]}" if nxt else ", no next link"))
                if title:
                    titles.append(title)
                psig = (_sig(text), (_sig(text[:600]), _sig(text[-600:]))) if text else None
                if text and (psig[0] in page_sigs or psig[1] in page_sigs):
                    skipped_dupes += 1  # same page served again under another URL
                    _log(f"skipped duplicate page: {url[:80]}")
                    text = ""
                elif text:
                    page_sigs.update(psig)
                if text:
                    n = len(parts) + 1
                    parts.append(text if CHAPTER_RE.search(text[:120]) else f"Chapter {n}: {title}\n\n{text}")
                if follow and nxt and nxt not in seen:
                    queue.append(nxt)
                if queue:
                    time.sleep(URL_DELAY_SECONDS)
            _update_job(job_id, stage="saving_source", progress=92, message="Chunking text...")
            pid, n_chars, n_chunks = _create_project(
                name or (titles[0] if titles else "Fetched Text"), "url", "\n\n".join(parts), chunk_chars
            )
            _update_job(job_id, status="done", stage="done", progress=100,
                        message=f"{fetched} page(s), {n_chars:,} chars, {n_chunks} chunks"
                                + (f" ({skipped_dupes} duplicate page(s) skipped)" if skipped_dupes else ""),
                        result={"project_id": pid})
        except Exception as e:
            _update_job(job_id, status="failed", stage="failed", progress=100,
                        message=str(e), error=str(e))

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})


# ══════════════════════════════════════════════════════════════════════════════
# Project routes
# ══════════════════════════════════════════════════════════════════════════════
@bp.get("/api/text/projects")
def api_text_projects():
    conn = _conn()
    rows = conn.execute(
        """
        SELECT p.id, p.name, p.origin, p.status, p.chunk_chars, p.lore_project_id, p.created_at,
               LENGTH(p.raw_text) AS chars, p.chunks_json,
               (SELECT COUNT(*) FROM text_entities e WHERE e.project_id = p.id AND COALESCE(e.deleted,0)=0) AS entity_count,
               (SELECT COUNT(*) FROM text_chunk_results c WHERE c.project_id = p.id AND c.idx >= 0) AS done_chunks
        FROM text_projects p ORDER BY p.id DESC
        """
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["chunk_count"] = len(json.loads(d.pop("chunks_json") or "[]"))
        out.append(d)
    return jsonify(out)


@bp.get("/api/text/project/<int:pid>")
def api_text_project(pid):
    r = _project_row(pid)
    if not r:
        return jsonify({"error": "Not found"}), 404
    chunks = json.loads(r["chunks_json"])
    conn = _conn()
    done = {}
    for x in conn.execute("SELECT idx, result_json FROM text_chunk_results WHERE project_id=? AND idx>=0", (pid,)):
        try:
            rj = json.loads(x["result_json"])
            done[x["idx"]] = (len(rj.get("entities", [])), len(rj.get("beats", [])))
        except Exception:
            done[x["idx"]] = (0, 0)
    conn.close()
    return jsonify({
        "id": pid, "name": r["name"], "origin": r["origin"], "status": r["status"],
        "chars": len(r["raw_text"]), "chunk_chars": r["chunk_chars"],
        "lore_project_id": r["lore_project_id"],
        "chunks": [{"idx": c["idx"], "label": c["label"], "chars": len(c["text"]), "done": c["idx"] in done,
                    "entities": done.get(c["idx"], (0, 0))[0], "beats": done.get(c["idx"], (0, 0))[1]}
                   for c in chunks],
        "entities": [{**e, "tier": entity_tier(e, len(chunks))} for e in _entities(pid)],
        "trash": [{"id": e["id"], "name": e["name"], "entity_type": e["entity_type"]} for e in _entities(pid, trash=True)],
        "recap_saved": bool((r["recap_text"] or "").strip()) if "recap_text" in r.keys() else False,
        "recap_upto": r["recap_upto"] if "recap_upto" in r.keys() else -1,
    })


@bp.delete("/api/text/project/<int:pid>")
def api_text_delete(pid):
    conn = _conn()
    for t in ("text_entities", "text_chunk_results", "text_critiques"):
        conn.execute(f"DELETE FROM {t} WHERE project_id=?", (pid,))
    conn.execute("DELETE FROM text_projects WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"deleted": pid})


@bp.post("/api/text/project/<int:pid>/rechunk")
def api_text_rechunk(pid):
    r = _project_row(pid)
    if not r:
        return jsonify({"error": "Not found"}), 404
    if pid in _EXTRACT_RUNNING:
        return jsonify({"error": "Extraction is running for this text. Wait for it to finish first."}), 409
    size = int((request.get_json(force=True) or {}).get("chunk_chars") or DEFAULT_CHUNK_CHARS)
    chunks = chunk_text(r["raw_text"], size)
    conn = _conn()
    conn.execute("UPDATE text_projects SET chunks_json=?, chunk_chars=?, status='ingested' WHERE id=?",
                 (json.dumps(chunks, ensure_ascii=False), size, pid))
    conn.execute("DELETE FROM text_chunk_results WHERE project_id=?", (pid,))
    conn.commit()
    conn.close()
    _log(f"rechunk project={pid}: {len(chunks)} chunks (target {size}); earlier extraction results cleared")
    return jsonify({"chunks": len(chunks)})


@bp.post("/api/text/project/<int:pid>/append")
def api_text_append(pid):
    """Add more text to the END of a project (new chapters, or a SillyTavern chat log that continues the story).
    Only the new text is chunked; existing chunks and their extraction stay, so EXTRACT only runs the new parts.
    Form upload (file: .jsonl/.txt/.md/.html/.epub) or JSON {"text"}."""
    r = _project_row(pid)
    if not r:
        return jsonify({"error": "Not found"}), 404
    if pid in _EXTRACT_RUNNING:
        return jsonify({"error": "Extraction is running for this text. Wait for it to finish first."}), 409
    try:
        if request.files.get("file"):
            f = request.files["file"]
            data = f.read()
            ext = (f.filename or "").lower().rsplit(".", 1)[-1]
            if ext == "jsonl":
                _, text = stchat_to_text(data)
            elif ext == "epub":
                _, text = epub_to_text(data)
            elif ext in ("html", "htm", "xhtml"):
                _, text = html_to_text(decode_bytes(data))
            else:
                text = decode_bytes(data)
        else:
            text = str((request.get_json(force=True) or {}).get("text") or "")
        text = clean_text(text)
        if len(text) < 200:
            return jsonify({"error": "Not enough text to add (under 200 characters)."}), 400
        old_raw = r["raw_text"] or ""
        if len(old_raw) + len(text) > MAX_TOTAL_CHARS:
            return jsonify({"error": f"Too large together ({len(old_raw) + len(text):,} chars; max {MAX_TOTAL_CHARS:,})."}), 400
        old = json.loads(r["chunks_json"] or "[]")
        new = chunk_text(text, r["chunk_chars"] or DEFAULT_CHUNK_CHARS)
        start = len(old)
        for k, c in enumerate(new):
            c["idx"] = start + k
            if c["label"].startswith("Start"):
                c["label"] = f"Added {c['label'].replace('Start', '').strip(' ()') or 'text'}".strip()
        conn = _conn()
        conn.execute("UPDATE text_projects SET raw_text=?, chunks_json=?, status='ingested' WHERE id=?",
                     (old_raw + "\n\n" + text, json.dumps(old + new, ensure_ascii=False), pid))
        conn.commit()
        conn.close()
        _log(f"append project={pid}: +{len(text):,} chars -> {len(new)} new chunk(s) (now {start + len(new)})")
        return jsonify({"added_chars": len(text), "new_chunks": len(new), "chunks": start + len(new)})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ══════════════════════════════════════════════════════════════════════════════
# Extraction
# ══════════════════════════════════════════════════════════════════════════════
EXTRACT_SYSTEM = """You extract world-building data from one chunk of a story (fanfiction) for a SillyTavern lorebook.
Return ONLY valid JSON, no markdown fences.

Shape:
{
  "chapter_summary": "1-2 sentences: what happens in this chunk",
  "entities": [
    {
      "name": "canonical name as used in the text",
      "aliases": ["other names, nicknames, titles used for the same entity in this chunk"],
      "type": "character|place|faction|event|item|ability|concept",
      "age": "stated or clearly implied age, e.g. '17', 'late twenties', 'adult'; empty string if the text gives no basis",
      "facts": "40-120 words of dense, factual notes about this entity as shown in THIS chunk",
      "voice": ["up to 3 short verbatim dialogue lines (max 25 words each) that show how a CHARACTER speaks; [] for non-characters"],
      "keywords": ["3-6 trigger words/phrases"],
      "origin": "canon | altered | original | empty (see rules)",
      "relations": [{"with": "other named character", "relation": "e.g. cousin; teammate"}]
    }
  ]
}

Rules:
- Only include named or clearly distinct entities that matter to the setting. Skip one-off extras.
- Use only what the chunk says. Do not invent or infer backstory. Leave age empty rather than guess.
- Use "concept" for world rules, magic systems, customs, laws, technology.
- Use "event" for notable incidents, with who was involved and the outcome.
- Condense. Never copy long passages; voice lines are the only quotes allowed.
- If a character is or appears to be under 18, record their age but do NOT include any romantic or sexual details about them.
- Keep the same spelling of names as the text.
- origin: for fan fiction of a known work, "canon" = as in the original work, "altered" = from the original work but
  changed by this story, "original" = invented by this story; "" if not fan fiction or unsure.
- relations: for characters only, up to 5 relationships the chunk shows; [] otherwise."""


def _norm_type(t):
    t = (t or "").strip().lower()
    t = TYPE_ALIASES.get(t, t)
    return t if t in ENTITY_TYPES else "concept"


def extract_chunk(chunk, provider, model, mode="quick"):
    if mode == "deep":
        return extract_chunk_deep(chunk, provider, model)
    user = f"CHUNK: {chunk['label']}\n\n{chunk['text']}"
    res = _request(provider, model, user, system=EXTRACT_SYSTEM)
    ents = []
    for e in res.get("entities", []) or []:
        if not isinstance(e, dict) or not str(e.get("name", "")).strip():
            continue
        ents.append({
            "name": str(e["name"]).strip(),
            "aliases": [str(a).strip() for a in (e.get("aliases") or []) if str(a).strip()],
            "type": _norm_type(e.get("type")),
            "age": str(e.get("age") or "").strip(),
            "facts": str(e.get("facts") or "").strip(),
            "voice": [str(v).strip() for v in (e.get("voice") or []) if str(v).strip()][:3],
            "keywords": [str(k).strip() for k in (e.get("keywords") or []) if str(k).strip()],
            "origin": norm_origin(e.get("origin")),
            "relations": norm_relations(e.get("relations")),
        })
    return {"chapter_summary": str(res.get("chapter_summary") or "").strip(), "entities": ents,
            "beats": [], "stats": {"entities": len(ents), "beats": 0}}


# ══════════════════════════════════════════════════════════════════════════════
# Merge / dedupe
# ══════════════════════════════════════════════════════════════════════════════
_TITLES = {"dr", "mr", "mrs", "ms", "miss", "lord", "lady", "sir", "captain", "professor",
           "prof", "king", "queen", "prince", "princess", "the", "a", "an", "of"}


def norm_name(s: str) -> str:
    s = re.sub(r"[^\w\s'-]", " ", (s or "").lower())
    return " ".join(t for t in s.split() if t not in _TITLES)


_MINOR_WORDS = re.compile(
    r"\b(child|kid|toddler|infant|baby|teen|teenage|teenager|minor|adolescent|schoolboy|schoolgirl|"
    r"high[- ]school|middle[- ]school|elementary|preteen|pre-teen|underage)\b", re.I)
_ADULT_WORDS = re.compile(
    r"\b(twenties|thirties|forties|fifties|sixties|adult|middle-aged|elderly|centuries|immortal|ancient)\b", re.I)


def classify_age(ages, etype):
    """Return '' | 'minor' | 'check' | 'unknown'."""
    nums, minor_w, adult_w = [], False, False
    for s in ages:
        for n in re.findall(r"\b(\d{1,3})\b", s):
            n = int(n)
            if 0 < n < 130:
                nums.append(n)
        minor_w = minor_w or bool(_MINOR_WORDS.search(s))
        adult_w = adult_w or bool(_ADULT_WORDS.search(s))
    has_minor = minor_w or any(n < 18 for n in nums)
    has_adult = adult_w or any(n >= 18 for n in nums)
    if has_minor and has_adult:
        return "check"
    if has_minor:
        return "minor"
    if has_adult:
        return ""
    return "unknown" if etype == "character" else ""


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def merge_entities(chunk_results):
    """chunk_results: {idx: {chapter_summary, entities[]}} -> list of merged dicts."""
    recs = []
    for idx in sorted(chunk_results):
        for e in chunk_results[idx]["entities"]:
            recs.append({**e, "chunk": idx})
    if not recs:
        return _merge_beats(chunk_results, [])
    uf = _UF(len(recs))
    keys = []
    owner = {}
    for i, r in enumerate(recs):
        ks = {norm_name(r["name"])} | {norm_name(a) for a in r["aliases"]}
        ks.discard("")
        keys.append(ks)
        for k in ks:
            tk = (r["type"], k)
            if tk in owner:
                uf.union(owner[tk], i)
            else:
                owner[tk] = i

    # single-token name -> unique multi-token name of same type
    clusters = defaultdict(list)
    for i in range(len(recs)):
        clusters[uf.find(i)].append(i)

    def cluster_keys(c):
        return set().union(*[keys[i] for i in clusters[c]])

    ckeys = {c: cluster_keys(c) for c in clusters}
    for c, ks in list(ckeys.items()):
        if any(" " in k for k in ks):
            continue
        etype = recs[clusters[c][0]]["type"]
        cands = set()
        for c2, ks2 in ckeys.items():
            if c2 == c or recs[clusters[c2][0]]["type"] != etype:
                continue
            for k2 in ks2:
                toks = k2.split()
                if len(toks) > 1 and any(k == toks[0] or k == toks[-1] for k in ks):
                    cands.add(c2)
        if len(cands) == 1:
            uf.union(clusters[next(iter(cands))][0], clusters[c][0])

    groups = defaultdict(list)
    for i in range(len(recs)):
        groups[uf.find(i)].append(recs[i])

    merged = []
    for grp in groups.values():
        names = Counter(r["name"] for r in grp)
        name = sorted(names, key=lambda n: (-names[n], -len(n)))[0]
        aliases, seen = [], {name.lower()}
        for r in grp:
            for a in [r["name"]] + r["aliases"]:
                if a.lower() not in seen:
                    seen.add(a.lower())
                    aliases.append(a)
        etype = Counter(r["type"] for r in grp).most_common(1)[0][0]
        ages = [r["age"] for r in grp if r["age"]]
        age = Counter(ages).most_common(1)[0][0] if ages else ""
        kws, kseen = [], set()
        for k in [name] + aliases[:6] + [k for r in grp for k in r["keywords"]]:
            if k.lower() not in kseen:
                kseen.add(k.lower())
                kws.append(k)
        voice, vseen = [], set()
        for r in grp:
            for v in r["voice"]:
                if v.lower() not in vseen:
                    vseen.add(v.lower())
                    voice.append(v)
        frags, fseen = [], set()
        for ch, f in sorted(((r["chunk"], r["facts"]) for r in grp if r["facts"])):
            if f.lower() not in fseen:
                fseen.add(f.lower())
                frags.append((ch, f))
        origins = Counter(r.get("origin") for r in grp if r.get("origin"))
        origin = origins.most_common(1)[0][0] if origins else ""
        if origin == "canon" and origins.get("altered"):
            origin = "altered"            # any chunk showing a change makes it fic-specific
        rel = {}
        for r in grp:
            for x in r.get("relations") or []:
                k = norm_name(x["with"])
                if not k or k in {norm_name(n) for n in [name] + aliases}:
                    continue
                cur = rel.setdefault(k, {"with": x["with"], "relation": []})
                for part in re.split(r"[;,/]", x["relation"]):
                    part = part.strip()
                    if part and part.lower() not in [p.lower() for p in cur["relation"]]:
                        cur["relation"].append(part)
        relations = [{"with": v["with"], "relation": "; ".join(v["relation"][:3])} for v in rel.values()][:8]
        merged.append({
            "name": name, "aliases": aliases[:8], "type": etype, "age": age,
            "age_flag": classify_age(ages, etype), "keywords": kws[:10],
            "voice": voice[:5], "fragments": frags,
            "mentions": len({r["chunk"] for r in grp}),
            "origin": origin, "relations": relations, "first_chunk": min(r["chunk"] for r in grp),
        })
    merged.extend(_merge_beats(chunk_results, merged))
    # events keep the story order _merge_beats gave them; everything else sorts by importance
    merged.sort(key=lambda m: (True, 0, "") if m["type"] == "event"
                else (False, -m["mentions"], m["name"].lower()))
    return merged


def _jaccard(a, b):
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a and b else 0.0


def _merge_beats(chunk_results, merged):
    """Turn per-chunk beats into 'event' entities (deduping retold events) and
    attach each beat's state_changes to the matching character/entity as a fragment."""
    groups = []  # {title, chunks:set, items:[beat+chunk]}
    for idx in sorted(chunk_results):
        for b in chunk_results[idx].get("beats", []) or []:
            tt = norm_name(b["title"]).split()
            pp = {norm_name(p) for p in b.get("participants", []) if norm_name(p)}
            hit = None
            for g in groups:
                near = min(abs(idx - c) for c in g["chunks"]) <= 1
                same_place = b.get("place") and b["place"].lower() == g["place"].lower()
                if _jaccard(tt, g["tt"]) >= 0.6 or (near and same_place and _jaccard(pp, g["pp"]) >= 0.67):
                    hit = g
                    break
            if hit is None:
                hit = {"tt": tt, "pp": pp, "place": b.get("place", ""), "chunks": set(), "items": []}
                groups.append(hit)
            hit["chunks"].add(idx)
            hit["items"].append({**b, "chunk": idx})

    # state changes -> entity fragments
    key_to_ent = {}
    for m in merged:
        for n in [m["name"]] + m["aliases"]:
            key_to_ent.setdefault(norm_name(n), m)
    for g in groups:
        for it in g["items"]:
            for sc in it.get("state_changes", []):
                m = key_to_ent.get(norm_name(sc["entity"]))
                if m is not None:
                    m["fragments"].append((it["chunk"], f"{sc['change']} (after '{it['title']}')."))
    for m in merged:
        m["fragments"].sort(key=lambda x: x[0])

    events = []
    for g in groups:
        items = g["items"]
        best = max(items, key=lambda x: len(x.get("what_happened", "")))
        parts = [best["what_happened"]] if best.get("what_happened") else []
        ppl = list(dict.fromkeys(p for it in items for p in it.get("participants", [])))
        if ppl:
            parts.append("Involved: " + ", ".join(ppl) + ".")
        if best.get("place"):
            parts.append("Place: " + best["place"] + ".")
        when = best.get("marker") or ""
        if best.get("flashback"):
            when = (when + " (flashback)").strip()
        if when:
            parts.append("When: " + when + ".")
        confs = [it.get("confidence", "medium") for it in items]
        conf = "high" if "high" in confs else ("medium" if "medium" in confs else "low")
        kws = list(dict.fromkeys([best["title"]] + ppl[:4] + ([best["place"]] if best.get("place") else [])))
        events.append({
            "name": best["title"], "aliases": [], "type": "event", "age": "", "age_flag": "",
            "keywords": kws[:10], "voice": [], "fragments": [(items[0]["chunk"], " ".join(parts))],
            "mentions": len(g["chunks"]), "evidence": best.get("evidence", ""), "confidence": conf,
            "story_order": best.get("order", ""), "keep": 0 if conf == "low" else 1,
            "first_chunk": items[0]["chunk"],
        })
    return events


CONDENSE_SYSTEM = """You consolidate notes into ONE SillyTavern lorebook entry. Return ONLY JSON: {"content": "..."}.
Write 60-150 words, present tense, using only facts in the notes. Where the notes show change over the story,
keep it as 'early ... later ...'. Do not invent. Do not include romantic or sexual details about anyone under 18."""


def build_content(m, labels, provider, model, condense):
    frags = m["fragments"]
    if not frags:
        return ""
    joined = " ".join(f for _, f in frags)
    if len(frags) == 1 or len(joined.split()) <= 160:
        return joined
    if condense:
        try:
            notes = "\n".join(f"[{labels.get(i, i)}] {f}" for i, f in frags)
            res = _request(provider, model,
                           f"Entity: {m['name']} ({m['type']})\n\nNotes in story order:\n{notes[:9000]}",
                           system=CONDENSE_SYSTEM)
            c = str(res.get("content") or "").strip()
            if c:
                return c
        except Exception as e:
            _log(f"condense failed for {m['name']}: {e}")
    return joined[:900]


def _first_sentence(content):
    content = (content or "").strip()
    return (content.split(". ")[0].rstrip(".") + ".")[:200] if content else ""


def _save_entities(pid, merged, labels, provider, model, condense, job_id=None):
    """Write the merged list, keeping review work from the previous list:
    hand-edited entries keep the user's version, trashed ones stay in the trash, keep/skip choices stick,
    and entries the user merged by hand are not split apart again."""
    conn = _conn()
    prev = [_row_entity(r) for r in conn.execute("SELECT * FROM text_entities WHERE project_id=?", (pid,))]
    conn.execute("DELETE FROM text_entities WHERE project_id=?", (pid,))
    conn.commit()
    conn.close()
    by_key = {}
    for p in sorted(prev, key=lambda p: (not p["edited"], not p["deleted"])):   # edited/deleted win key clashes
        for n in [p["name"]] + p["aliases"]:
            by_key.setdefault((p["entity_type"] == "event", norm_name(n)), p)
    used, kept_user, restored, trashed = set(), 0, 0, 0
    chunk_total = len(labels) or 1
    total = len(merged)
    for n, m in enumerate(merged, 1):
        match = None
        for nm in [m["name"]] + m["aliases"]:
            match = by_key.get((m["type"] == "event", norm_name(nm)))
            if match is not None:
                break
        conn = _conn()
        if match is not None and (match["edited"] or match["deleted"]):
            if match["id"] in used:            # already represented (e.g. merged into a hand-edited entry)
                conn.close()
                continue
            used.add(match["id"])
            if match["deleted"]:
                trashed += 1
                d = {**match, "mentions": m["mentions"], "first_chunk": m.get("first_chunk", -1), "deleted": True}
            else:
                kept_user += 1
                d = {**match, "mentions": max(m["mentions"], match["mentions"]),
                     "first_chunk": m.get("first_chunk", -1), "edited": True}
            _insert_entity(conn, pid, d)
        else:
            content = build_content(m, labels, provider, model, condense)
            keep = m.get("keep", 1)
            if match is not None:
                used.add(match["id"])
                keep = match["keep"]           # the user's keep/skip choice sticks
                restored += 1
            elif (m["type"] in ("item", "ability") and m["mentions"] == 1 and chunk_total >= 4):
                keep = 0                       # one-off items/abilities are skipped by default (still listed)
            _insert_entity(conn, pid, {
                "name": m["name"], "aliases": m["aliases"], "entity_type": m["type"], "age": m["age"],
                "age_flag": m["age_flag"], "keywords": m["keywords"], "summary": _first_sentence(content),
                "content": content, "voice": m["voice"], "mentions": m["mentions"], "keep": keep,
                "evidence": m.get("evidence", ""), "confidence": m.get("confidence", ""),
                "story_order": m.get("story_order", ""), "origin": m.get("origin", ""),
                "relations": m.get("relations", []), "first_chunk": m.get("first_chunk", -1),
            })
        conn.commit()
        conn.close()
        if n % 10 == 0 or n == total:
            _log(f"writing entries {n}/{total}")
        if job_id and n % 3 == 0:
            _update_job(job_id, stage="generating", progress=70 + int(n / total * 28),
                        message=f"Merging entities {n}/{total}")
    # hand-edited entries that the new extraction did not find again are kept as they were
    conn = _conn()
    for p in prev:
        if p["edited"] and not p["deleted"] and p["id"] not in used:
            _insert_entity(conn, pid, p)
            kept_user += 1
    conn.commit()
    conn.close()
    if prev:
        _log(f"review work kept: {kept_user} hand-edited, {trashed} still in trash, {restored} keep/skip choices")


_EXTRACT_RUNNING = {}          # project id -> job id, so a second click can't start a duplicate run
_EXTRACT_LOCK = threading.Lock()
MIN_EXTRACT_CHARS = 150        # shorter chunks (menus, stray headers) are never worth a model call


def _empty_result():
    return {"chapter_summary": "", "entities": [], "beats": [], "stats": {"entities": 0, "beats": 0},
            "skipped": True}


@bp.post("/api/text/project/<int:pid>/extract")
def api_text_extract(pid):
    r = _project_row(pid)
    if not r:
        return jsonify({"error": "Not found"}), 404
    body = request.get_json(force=True) or {}
    provider = body.get("provider", "nanogpt")
    model = body.get("model", "")
    condense = bool(body.get("condense", True))
    force = bool(body.get("force", False))
    merge_only = bool(body.get("merge_only", False))
    only = {int(i) for i in (body.get("only") or []) if str(i).lstrip("-").isdigit()}   # redo just these chunks
    mode = "deep" if body.get("mode") == "deep" else "quick"
    chunks = json.loads(r["chunks_json"])
    try:
        workers = max(1, min(int(body.get("parallel") or 3), 6))
    except (TypeError, ValueError):
        workers = 3
    with _EXTRACT_LOCK:
        if pid in _EXTRACT_RUNNING:
            _log(f"extract project={pid}: already running as job {_EXTRACT_RUNNING[pid]}, not starting a second run")
            return jsonify({"job_id": _EXTRACT_RUNNING[pid], "already_running": True})
        job_id = _create_job()
        _EXTRACT_RUNNING[pid] = job_id

    def run():
        t_job = time.time()
        try:
            conn = _conn()
            if only:
                conn.executemany("DELETE FROM text_chunk_results WHERE project_id=? AND idx=?",
                                 [(pid, i) for i in only])
                conn.commit()
            elif force and not merge_only:
                conn.execute("DELETE FROM text_chunk_results WHERE project_id=?", (pid,))
                conn.commit()
            done = set()
            degraded = 0
            for x in conn.execute("SELECT idx, result_json FROM text_chunk_results WHERE project_id=? AND idx>=0",
                                  (pid,)):
                if (json.loads(x["result_json"]).get("stats") or {}).get("degraded"):
                    degraded += 1          # its events step failed last time: redo it
                else:
                    done.add(x["idx"])
            conn.close()
            todo = [] if merge_only else [c for c in chunks if c["idx"] not in done and (not only or c["idx"] in only)]
            failed, errors = 0, []
            _log(f"extract project={pid} '{r['name']}' job={job_id}: mode={mode} provider={provider} "
                 f"model={model or '(default)'} parallel={workers} chunks={len(chunks)} already_done={len(done)} "
                 f"to_do={len(todo)} force={force} merge_only={merge_only} condense={condense}"
                 + (f" (retrying {degraded} chunk(s) whose events step failed)" if degraded and not merge_only else ""))

            def work(c):
                t0 = time.time()
                if len(c["text"].strip()) < MIN_EXTRACT_CHARS:
                    _log(f"chunk {c['idx'] + 1}/{len(chunks)} skipped (only {len(c['text'].strip())} chars)")
                    res = _empty_result()
                else:
                    _log(f"chunk {c['idx'] + 1}/{len(chunks)} start: {c['label'][:50]} ({len(c['text']):,} chars)")
                    res = extract_chunk(c, provider, model, mode)
                    _log(f"chunk {c['idx'] + 1}/{len(chunks)} done in {time.time() - t0:.1f}s: "
                         f"{len(res.get('entities', []))} entities, {len(res.get('beats', []))} events")
                payload = json.dumps(res, ensure_ascii=False)
                for attempt in range(4):
                    try:
                        cn = _conn()
                        cn.execute("INSERT OR REPLACE INTO text_chunk_results VALUES (?,?,?)",
                                   (pid, c["idx"], payload))
                        cn.commit()
                        cn.close()
                        return
                    except Exception:
                        time.sleep(0.5 * (attempt + 1))
                raise RuntimeError("could not save chunk result (database busy)")

            if todo:
                _update_job(job_id, status="running", stage="requesting_model", progress=5,
                            message=f"Extracting {len(todo)} chunk(s), {workers} at a time...")
                done_n = 0
                t_chunks = time.time()
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futs = {ex.submit(work, c): c for c in todo}
                    for fut in as_completed(futs):
                        c = futs[fut]
                        done_n += 1
                        try:
                            fut.result()
                        except Exception as e:
                            failed += 1
                            errors.append(str(e)[:200])
                            _log(f"chunk {c['idx'] + 1}/{len(chunks)} FAILED: {e}")
                        left = len(todo) - done_n
                        eta = (time.time() - t_chunks) / done_n * left   # wall time per finished chunk, so parallelism is included
                        eta_txt = f" - about {int(eta // 60)}m {int(eta % 60):02d}s left" if left else ""
                        _update_job(job_id, status="running", stage="requesting_model",
                                    progress=5 + int(done_n / len(todo) * 60),
                                    message=f"Extracted {done_n}/{len(todo)} chunks ({workers} at a time){eta_txt}"
                                            f" - last: {c['label'][:40]}")
            _log(f"chunk extraction finished in {time.time() - t_job:.1f}s ({failed} failed); merging...")
            _update_job(job_id, stage="generating", progress=68, message="Merging entities...")
            conn = _conn()
            rows = conn.execute("SELECT idx, result_json FROM text_chunk_results WHERE project_id=? AND idx>=0",
                                (pid,)).fetchall()
            conn.close()
            results = {x["idx"]: json.loads(x["result_json"]) for x in rows}
            if not results:
                raise RuntimeError("No chunks extracted successfully. Check the model/provider and try again."
                                   + (f" First error: {errors[0]}" if errors else ""))
            labels = {c["idx"]: c["label"] for c in chunks}
            merged = merge_entities(results)
            _log(f"merge: {sum(len(v.get('entities', [])) for v in results.values())} raw entities from "
                 f"{len(results)} chunks -> {len(merged)} merged entries; writing"
                 + (" (condensing multi-chunk entities with extra model calls)" if condense else ""))
            _save_entities(pid, merged, labels, provider, model, condense, job_id)

            # keep chapter summaries for the 'Story So Far' entry
            summ = [{"idx": i, "label": labels.get(i, i), "summary": results[i]["chapter_summary"]}
                    for i in sorted(results) if results[i].get("chapter_summary")]
            conn = _conn()
            conn.execute("UPDATE text_projects SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                         ("extracted", pid))
            conn.execute("INSERT OR REPLACE INTO text_chunk_results VALUES (?,?,?)",
                         (pid, -1, json.dumps(summ, ensure_ascii=False)))
            conn.commit()
            conn.close()
            _log(f"job {job_id} done in {time.time() - t_job:.1f}s total: {len(merged)} entries")
            msg = f"{len(merged)} entities from {len(results)}/{len(chunks)} chunks"
            if failed:
                msg += f" ({failed} chunk(s) failed; run again to retry them)"
            _update_job(job_id, status="done", stage="done", progress=100, message=msg,
                        result={"entities": len(merged), "failed_chunks": failed})
        except Exception as e:
            import traceback
            traceback.print_exc()
            _log(f"job {job_id} FAILED after {time.time() - t_job:.1f}s: {e}")
            _update_job(job_id, status="failed", stage="failed", progress=100,
                        message=str(e), error=str(e))
        finally:
            with _EXTRACT_LOCK:
                _EXTRACT_RUNNING.pop(pid, None)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})


# ══════════════════════════════════════════════════════════════════════════════
# Review: edit / merge / delete / commit
# ══════════════════════════════════════════════════════════════════════════════
@bp.patch("/api/text/entity/<int:eid>")
def api_text_entity_patch(eid):
    d = request.get_json(force=True) or {}
    conn = _conn()
    cur = conn.execute("SELECT * FROM text_entities WHERE id=?", (eid,)).fetchone()
    if not cur:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    e = _row_entity(cur)
    if any(k in d for k in ("name", "age", "content", "summary", "type", "aliases", "keywords", "voice",
                            "origin", "relations")):
        e["edited"] = True                     # survives Rebuild list (a re-merge)
    if "origin" in d:
        e["origin"] = norm_origin(d["origin"])
    if "relations" in d:
        e["relations"] = norm_relations(d["relations"]) if isinstance(d["relations"], list) else e["relations"]
    for k in ("name", "age", "content", "summary"):
        if k in d:
            e[k] = str(d[k])
    if "type" in d:
        e["entity_type"] = _norm_type(d["type"])
    for k in ("aliases", "keywords", "voice"):
        if k in d and isinstance(d[k], list):
            e[k] = [str(x).strip() for x in d[k] if str(x).strip()]
    if "keep" in d:
        e["keep"] = bool(d["keep"])
    if "content" in d and "summary" not in d:   # keep the one-line summary in step with edited content
        e["summary"] = _first_sentence(e["content"])
    if "age" in d:
        e["age_flag"] = classify_age([e["age"]] if e["age"] else [], e["entity_type"])
    conn.execute(
        """UPDATE text_entities SET name=?, aliases_json=?, entity_type=?, age=?, age_flag=?,
           keywords_json=?, summary=?, content=?, voice_json=?, keep=?, edited=?, origin=?, relations_json=?,
           updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (e["name"], json.dumps(e["aliases"], ensure_ascii=False), e["entity_type"], e["age"],
         e["age_flag"], json.dumps(e["keywords"], ensure_ascii=False), e["summary"], e["content"],
         json.dumps(e["voice"], ensure_ascii=False), 1 if e["keep"] else 0, 1 if e["edited"] else 0,
         e["origin"], json.dumps(e["relations"], ensure_ascii=False), eid),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.delete("/api/text/entity/<int:eid>")
def api_text_entity_delete(eid):
    """Moves the entry to the trash (restorable). ?purge=1 deletes it for good."""
    conn = _conn()
    if request.args.get("purge"):
        conn.execute("DELETE FROM text_entities WHERE id=?", (eid,))
    else:
        conn.execute("UPDATE text_entities SET deleted=1 WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return jsonify({"deleted": eid})


@bp.post("/api/text/entity/<int:eid>/restore")
def api_text_entity_restore(eid):
    conn = _conn()
    conn.execute("UPDATE text_entities SET deleted=0 WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return jsonify({"restored": eid})


@bp.delete("/api/text/project/<int:pid>/trash")
def api_text_empty_trash(pid):
    conn = _conn()
    n = conn.execute("DELETE FROM text_entities WHERE project_id=? AND deleted=1", (pid,)).rowcount
    conn.commit()
    conn.close()
    return jsonify({"purged": n})


@bp.post("/api/text/project/<int:pid>/merge")
def api_text_manual_merge(pid):
    ids = [int(i) for i in (request.get_json(force=True) or {}).get("ids", [])]
    if len(ids) < 2:
        return jsonify({"error": "Select at least 2 entities"}), 400
    conn = _conn()
    q = ",".join("?" * len(ids))
    rows = conn.execute(f"SELECT * FROM text_entities WHERE project_id=? AND id IN ({q}) AND COALESCE(deleted,0)=0",
                        [pid] + ids).fetchall()
    ents = sorted((_row_entity(r) for r in rows), key=lambda e: -e["mentions"])
    if len(ents) < 2:
        conn.close()
        return jsonify({"error": "Entities not found"}), 404
    base = ents[0]
    aliases = list(base["aliases"])
    seen = {base["name"].lower()} | {a.lower() for a in aliases}
    keywords, voice = list(base["keywords"]), list(base["voice"])
    content = base["content"]
    ages = [base["age"]] if base["age"] else []
    for o in ents[1:]:
        for a in [o["name"]] + o["aliases"]:
            if a.lower() not in seen:
                seen.add(a.lower())
                aliases.append(a)
        keywords += [k for k in o["keywords"] if k not in keywords]
        voice += [v for v in o["voice"] if v not in voice]
        if o["content"] and o["content"] not in content:
            content = f"{content} {o['content']}".strip()
        if o["age"]:
            ages.append(o["age"])
    relations = list(base["relations"])
    for o in ents[1:]:
        for x in o["relations"]:
            if norm_name(x["with"]) not in {norm_name(r["with"]) for r in relations}:
                relations.append(x)
    origin = base["origin"] or next((o["origin"] for o in ents[1:] if o["origin"]), "")
    age = base["age"] or (ages[0] if ages else "")
    conn.execute(
        """UPDATE text_entities SET aliases_json=?, keywords_json=?, voice_json=?, content=?, summary=?, age=?,
           age_flag=?, mentions=?, relations_json=?, origin=?, edited=1 WHERE id=?""",
        (json.dumps(aliases[:12], ensure_ascii=False), json.dumps(keywords[:12], ensure_ascii=False),
         json.dumps(voice[:5], ensure_ascii=False), content, _first_sentence(content), age,
         classify_age(ages, base["entity_type"]), sum(e["mentions"] for e in ents),
         json.dumps(relations[:8], ensure_ascii=False), origin, base["id"]),
    )
    conn.execute(f"DELETE FROM text_entities WHERE id IN ({','.join('?' * (len(ents) - 1))})",
                 [e["id"] for e in ents[1:]])
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "kept_id": base["id"]})


RECAP_CHARS = 3000       # the recap is always on, so it has to stay small (about 700 tokens)
SUMMARY_CHARS = 6000     # the AI archive summary (header + chapter log + status), about 1,500 tokens at most
TIMELINE_CHARS = 9000

_GENERIC_KW = {"spell", "spells", "location", "magic", "skill", "skills", "ability", "abilities", "item", "items",
               "place", "past battle", "character", "event", "weapon", "weapons", "concept", "faction", "world",
               "story", "scene", "battle", "fight", "room", "girl", "girls", "boy", "man", "woman"}


def clean_keywords(e, other_names):
    """Trigger keywords for one entry: its own name/aliases first; drop generic words and names that
    belong to other entries (so 'Mascot dress sphere' does not fire every time 'Paine' is mentioned)."""
    own = {norm_name(n) for n in [e["name"]] + list(e["aliases"])}
    out, seen = [], set()
    for k in (e["keywords"] or []):
        nk = norm_name(k)
        if not nk or nk in seen:
            continue
        seen.add(nk)
        if nk in own:
            out.append(k)
            continue
        if nk in _GENERIC_KW:
            continue
        owner = other_names.get(nk)
        if owner is not None and owner != e["id"]:
            continue
        out.append(k)
    return out or [e["name"]]


def build_recap(summaries):
    """One short always-on recap from chapter summaries; if too long, keep each one's first sentence,
    then drop the oldest so the latest state of the story is always included."""
    parts = [str(x).strip() for x in summaries if str(x).strip()]
    text = " ".join(parts)
    if len(text) <= RECAP_CHARS:
        return text
    parts = [p.split(". ")[0].rstrip(".") + "." for p in parts]
    while parts and len(" ".join(parts)) > RECAP_CHARS:
        parts.pop(0)
    return ("(earlier events omitted) " if parts else "") + " ".join(parts)


def lore_entry_content(e):
    """The text that goes into a lorebook entry for one reviewed entity."""
    content = (e.get("content") or "").strip()
    origin = e.get("origin") or ""
    if origin == "altered" and not content.lower().startswith("in this story"):
        content = "In this story (differs from canon): " + content
    elif origin == "original" and not content.lower().startswith("original to this story"):
        content = "Original to this story: " + content
    if e["entity_type"] == "character":
        if e.get("age"):
            content += f" Age: {e['age']}."
        rels = [f"{r['with']} ({r['relation']})" for r in (e.get("relations") or []) if r.get("with")]
        if rels:
            content += " Relationships: " + ", ".join(rels) + "."
        if e.get("voice"):
            content += "\nSpeech samples:\n" + "\n".join(f'- "{v}"' for v in e["voice"])
    return content


def _chunk_labels(r):
    return [c["label"] for c in json.loads(r["chunks_json"] or "[]")]


def _summaries(pid, upto=-1):
    """Chapter summaries in story order, only up to chunk `upto` when it is set (>= 0)."""
    r = _project_row(pid)
    conn = _conn()
    row = conn.execute("SELECT result_json FROM text_chunk_results WHERE project_id=? AND idx=-1", (pid,)).fetchone()
    conn.close()
    summ = json.loads(row["result_json"]) if row else []
    labels = _chunk_labels(r) if r else []
    out = []
    for x in summ:
        idx = x.get("idx")
        if idx is None and x.get("label") in labels:      # summaries saved before the idx field existed
            idx = labels.index(x["label"])
        if upto >= 0 and idx is not None and idx > upto:
            continue
        if x.get("summary"):
            out.append(x["summary"])
    return out


def _project_recap(pid, upto=None):
    """(recap text, is_hand_edited, upto). The saved hand-edited recap wins unless a new `upto` is asked for."""
    r = _project_row(pid)
    saved = (r["recap_text"] or "").strip() if "recap_text" in r.keys() else ""
    stored_upto = r["recap_upto"] if "recap_upto" in r.keys() and r["recap_upto"] is not None else -1
    if upto is None:
        upto = stored_upto
        if saved:
            return saved, True, upto
    summaries = _summaries(pid, upto)
    if not summaries:
        evs = [e for e in _entities(pid) if e["entity_type"] == "event" and e["keep"]
               and (upto < 0 or e.get("first_chunk", -1) <= upto)]
        summaries = [e["summary"] or e["name"] for e in sorted(evs, key=lambda e: e["id"])]
    return build_recap(summaries), False, upto


@bp.get("/api/text/project/<int:pid>/recap")
def api_text_recap(pid):
    r = _project_row(pid)
    if not r:
        return jsonify({"error": "Not found"}), 404
    upto = request.args.get("upto", type=int)
    text, edited, upto = _project_recap(pid, upto)
    limit = SUMMARY_CHARS if text.startswith("[HEADER]") else RECAP_CHARS
    return jsonify({"text": text, "edited": edited, "upto": upto, "chunks": _chunk_labels(r),
                    "limit": limit, "timeline": _saved_timeline(r), "timeline_limit": TIMELINE_CHARS,
                    "position": _recap_position(r)})


def _recap_position(r):
    v = r["recap_position"] if r is not None and "recap_position" in r.keys() else "before"
    return v if v in ("before", "depth") else "before"


@bp.put("/api/text/project/<int:pid>/recap")
def api_text_recap_save(pid):
    r = _project_row(pid)
    if not r:
        return jsonify({"error": "Not found"}), 404
    d = request.get_json(force=True) or {}
    upto = int(d.get("upto", -1) if d.get("upto") is not None else -1)
    text = str(d.get("text") or "").strip()            # "" = go back to the automatic recap
    conn = _conn()
    if "text" in d:                                    # a body with only "position" changes only the placement
        conn.execute("UPDATE text_projects SET recap_text=?, recap_upto=? WHERE id=?", (text, upto, pid))
    if d.get("position") in ("before", "depth"):       # where SillyTavern puts the recap
        conn.execute("UPDATE text_projects SET recap_position=? WHERE id=?", (d["position"], pid))
    if "timeline" in d:                                # "" = go back to one line per kept event
        conn.execute("UPDATE text_projects SET timeline_text=? WHERE id=?", (str(d.get("timeline") or "").strip(), pid))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "edited": bool(text), "upto": upto})


def _lore_items(pid):
    """Everything 'Send to LORE' would create, in order: one item per kept entity, then the
    constant Story So Far recap and the Story Timeline (events are rolled up, never sent one by one:
    dozens of entries sharing the character names as keywords would all fire at once)."""
    ents = [e for e in _entities(pid) if e["keep"]]
    recap, _, upto = _project_recap(pid)
    events = sorted([e for e in ents if e["entity_type"] == "event"
                     and (upto < 0 or e.get("first_chunk", -1) <= upto)], key=lambda e: e["id"])
    ents = [e for e in ents if e["entity_type"] != "event"]
    # a keyword that is really ANOTHER entry's name would make this entry fire whenever that name appears
    other_names = {}
    for e in ents:
        for nm in [e["name"]] + list(e["aliases"]):
            other_names.setdefault(norm_name(nm), e["id"])
    items = []
    for e in ents:
        content = lore_entry_content(e)
        items.append({"title": e["name"], "entry_type": e["entity_type"], "keys": clean_keywords(e, other_names),
                      "summary": (e["summary"] or content)[:200], "content": content})
    roster = cast_roster(ents, len(json.loads(_project_row(pid)["chunks_json"] or "[]")))
    if roster:
        items.append({"title": "Cast Roster", "entry_type": "concept", "keys": ["cast", "characters", "who is who"],
                      "summary": "Always-on list of the main cast, so the model knows who exists.",
                      "content": roster, "constant": True, "position": 0})
    rel = relationship_tracker(ents)
    if rel:
        items.append({"title": "Relationships", "entry_type": "concept",
                      "keys": ["relationship", "relationships", "feel about", "trust", "rival", "friends"],
                      "summary": "Always-on map of who is what to whom.", "content": rel, "constant": True, "position": 0})
    if recap:
        at_depth = _recap_position(_project_row(pid)) == "depth"
        items.append({"title": "Story So Far", "entry_type": "concept",
                      "keys": ["story so far", "recap", "previously", "plot summary"],
                      "summary": "Always-on recap of what has happened in the story.", "content": recap,
                      "constant": True, "position": 4 if at_depth else 0, "depth": 4, "role": 0})
    timeline = _saved_timeline(_project_row(pid)) or (build_timeline(events) if events else "")
    if timeline:
        items.append({"title": "Story Timeline", "entry_type": "concept",
                      "keys": ["timeline", "what happened", "earlier events", "flashback", "last time", "chapter"],
                      "summary": "Chapter-by-chapter timeline of the story so far.", "content": timeline})
    return items, upto


ROSTER_MAX = 15
RELATIONS_MAX_CHARS = 1200


def relationship_tracker(ents):
    """'A & B: relation' lines from the kept characters' relationships, each pair once (Memory Books-style tracker).
    Empty unless there are at least two pairs."""
    names = {norm_name(e["name"]): e["name"] for e in ents if e["entity_type"] == "character"}
    for e in ents:
        if e["entity_type"] == "character":
            for a in e.get("aliases") or []:
                names.setdefault(norm_name(a), e["name"])
    pairs = {}
    for e in ents:
        if e["entity_type"] != "character":
            continue
        for x in e.get("relations") or []:
            other = names.get(norm_name(str(x.get("with") or "")))
            rel = str(x.get("relation") or "").strip()
            if not other or other == e["name"] or not rel:
                continue
            key = tuple(sorted((e["name"], other)))
            pairs.setdefault(key, [])
            if rel.lower() not in [r.lower() for r in pairs[key]]:
                pairs[key].append(rel)
    if len(pairs) < 2:
        return ""
    lines, used = [], 0
    for (a, b), rels in pairs.items():
        ln = f"- {a} & {b}: {'; '.join(rels[:3])}"
        if used + len(ln) > RELATIONS_MAX_CHARS:
            lines.append("- (more relationships in each character's entry)")
            break
        lines.append(ln)
        used += len(ln) + 1
    return "[Relationships]\n" + "\n".join(lines)



def cast_roster(ents, chunk_total):
    """One line per main/supporting character (most mentioned first): an always-on entry so the model knows who
    exists even when nobody has named them yet (r/SillyTavernAI tip). Empty for fewer than two characters."""
    chars = [e for e in ents if e["entity_type"] == "character" and entity_tier(e, chunk_total) != "one-off"]
    if len(chars) < 2:
        return ""
    chars.sort(key=lambda e: -int(e.get("mentions") or 1))
    lines = []
    for e in chars[:ROSTER_MAX]:
        about = _first_sentence(e.get("summary") or e.get("content") or "")
        aka = [a for a in (e.get("aliases") or []) if a][:2]
        lines.append(f"- {e['name']}" + (f" (also {', '.join(aka)})" if aka else "") + (f": {about}" if about else ""))
    return "[Cast of the story]\n" + "\n".join(lines)


def _saved_timeline(r):
    return ((r["timeline_text"] or "").strip() if r is not None and "timeline_text" in r.keys() else "")


ARCHIVIST_SYSTEM = """You are a Narrative Archivist. Turn a story's history into a compact reference for roleplay
continuity. Return ONLY valid JSON, no fences:
{
  "current_timeline": "e.g. Post-battle, morning, day 3",
  "current_location": "specific setting",
  "dynamic": "one sentence: the current relationship state between the primary characters",
  "characters": [{"name": "", "location": "", "physical": "injuries, clothing, condition", "goal": "what they want right now"}],
  "plot_hooks": ["unresolved threats, items, promises"],
  "chapters": [{"title": "descriptive title", "summary": "1-3 short paragraphs"}]
}
Rules:
- Continuity anchors are non-negotiable: keep specific physical details (injuries, clothing changes, places) and the
  story's systemic rules (magic, mechanics, restrictions).
- State what happened and how characters feel as plain facts. Do not guess at motives the story does not show.
- Economy: group micro-actions into broader beats, no flowery prose, no repetition. Summarise the OUTCOME and any
  shift in a relationship, not the back-and-forth dialogue.
- Track relationships with clear labels (e.g. allies, rivals, hostile, protective) and note when they shift.
- "chapters": group the parts you are given into logical chapters, in order. 1-3 short paragraphs each; if a chapter is
  one conversation, summarise the shift in the dynamic, not every line.
- Everything up to the END POINT only; nothing after it. Use only the material given; never invent.
- Lines starting "[ARC n: ...]" are earlier arcs that were already condensed: give each ONE chapter entry titled
  "Arc n - <title>" with one short paragraph, then cover the remaining parts in normal chapters.
- The whole result is pasted into ONE always-on lorebook entry, so keep everything together under 850 words."""

ARC_SYSTEM = """You condense several consecutive part summaries of a story into ONE arc summary for roleplay continuity.
Return ONLY valid JSON, no fences: {"title": "short descriptive arc title", "summary": "one paragraph, max 120 words"}
Keep outcomes, relationship shifts, injuries, deaths, item and location changes. Drop scene-by-scene detail.
Use only what is given; never invent."""
ARC_THRESHOLD = 24      # more part summaries than this: condense the older ones into arcs first
ARC_KEEP_RECENT = 10    # the latest parts stay as they are
ARC_SIZE = 8            # parts per arc


def tier_parts(parts, provider, model):
    """Memory-Books-style tiers: older part summaries become arc summaries, recent parts stay detailed.
    Returns (lines, arcs_made). A failed arc call keeps that group's first and last summaries instead."""
    if len(parts) <= ARC_THRESHOLD:
        return parts, 0
    old, recent = parts[:-ARC_KEEP_RECENT], parts[-ARC_KEEP_RECENT:]
    lines = []
    for n, i in enumerate(range(0, len(old), ARC_SIZE), 1):
        group = old[i:i + ARC_SIZE]
        try:
            res = _request(provider, model, "PART SUMMARIES (in order):\n" + "\n".join(group)[:9000], system=ARC_SYSTEM)
            title = str(res.get("title") or "").strip() or f"Parts {i + 1}-{i + len(group)}"
            summ = str(res.get("summary") or "").strip()
            if not summ:
                raise ValueError("empty arc summary")
            lines.append(f"[ARC {n}: {title}] {summ}")
        except Exception as ex:
            _log(f"arc {n} condense failed ({str(ex)[:80]}); keeping its first and last part")
            lines.extend([group[0], group[-1]] if len(group) > 1 else group)
    return lines + recent, n



def format_archive(res):
    """The archivist's JSON as one lorebook entry, laid out like a summary pasted into SillyTavern World Info:
    [HEADER] / [BODY - CHAPTER LOG] / [FOOTER - CURRENT STATUS]."""
    head = []
    for label, key in (("Current Timeline", "current_timeline"), ("Current Location", "current_location"),
                       ("Dynamic", "dynamic")):
        v = str(res.get(key) or "").strip()
        if v:
            head.append(f"{label}: {v}")
    body = []
    for i, ch in enumerate([c for c in (res.get("chapters") or []) if isinstance(c, dict)], 1):
        title, summ = str(ch.get("title") or "").strip(), str(ch.get("summary") or "").strip()
        if summ:
            body.append(f"## CHAPTER {i} - {title or 'Untitled'}\n{summ}")
    foot = []
    for c in [c for c in (res.get("characters") or []) if isinstance(c, dict) and str(c.get("name") or "").strip()][:8]:
        bits = [str(c.get(k) or "").strip() for k in ("location", "physical", "goal")]
        foot.append(f"* {str(c['name']).strip()}: " + "; ".join(b for b in bits if b))
    hooks = [str(h).strip() for h in (res.get("plot_hooks") or []) if str(h).strip()]
    if hooks:
        foot.append("* Plot Hooks: " + "; ".join(hooks[:8]))
    parts = []
    if head:
        parts.append("[HEADER]\n" + "\n".join(head))
    if body:
        parts.append("[BODY - CHAPTER LOG]\n" + "\n\n".join(body))
    if foot:
        parts.append("[FOOTER - CURRENT STATUS]\n[ANCHOR: Current Situation]\n" + "\n".join(foot))
    text = "\n\n".join(parts)
    if len(text) > SUMMARY_CHARS and body:      # too long: shorten the oldest chapters first, never the status
        while len(text) > SUMMARY_CHARS and len(body) > 1:
            body.pop(0)
            parts[1 if head else 0] = "[BODY - CHAPTER LOG]\n(earlier chapters omitted)\n\n" + "\n\n".join(body)
            text = "\n\n".join(parts)
    return text


@bp.post("/api/text/project/<int:pid>/recap/ai")
def api_text_recap_ai(pid):
    """Write the Story So Far (current status) and a chapter-log timeline with the model, from the chapter
    summaries, kept events and main cast up to the starting point. Saved as hand-edited text, so it sticks."""
    r = _project_row(pid)
    if not r:
        return jsonify({"error": "Not found"}), 404
    d = request.get_json(force=True) or {}
    provider, model = d.get("provider", "nanogpt"), d.get("model", "")
    upto = int(d["upto"]) if d.get("upto") is not None else (r["recap_upto"] if r["recap_upto"] is not None else -1)
    labels = _chunk_labels(r)
    conn = _conn()
    row = conn.execute("SELECT result_json FROM text_chunk_results WHERE project_id=? AND idx=-1", (pid,)).fetchone()
    conn.close()
    parts = []
    for x in (json.loads(row["result_json"]) if row else []):
        idx = x.get("idx", labels.index(x["label"]) if x.get("label") in labels else None)
        if upto >= 0 and idx is not None and idx > upto:
            continue
        if x.get("summary"):
            parts.append(f"[{x.get('label', idx)}] {x['summary']}")
    ents = _entities(pid)
    events = [e for e in sorted(ents, key=lambda e: e["id"]) if e["entity_type"] == "event" and e["keep"]
              and (upto < 0 or e.get("first_chunk", -1) <= upto)]
    cast = sorted([e for e in ents if e["entity_type"] == "character" and e["keep"]],
                  key=lambda e: -int(e.get("mentions") or 1))[:10]
    rules = [e for e in ents if e["keep"] and e["entity_type"] in ("concept", "ability", "item")
             and e.get("origin") in ("altered", "original")][:10]
    if not parts and not events:
        return jsonify({"error": "Nothing to summarise yet: extract the text first."}), 400
    end = f"after part {upto + 1} ({labels[upto]})" if 0 <= upto < len(labels) else "the end of the text"
    cast_txt = "\n".join(
        f"- {e['name']}: {_first_sentence(e['content'])}"
        + (" Relationships: " + ", ".join(f"{x['with']} ({x['relation']})" for x in e["relations"]) if e["relations"] else "")
        for e in cast)
    parts, arcs = tier_parts(parts, provider, model)
    parts_txt = "\n".join(parts)
    if len(parts_txt) > 14000:            # keep the latest parts: they are nearest the end point
        parts_txt = "(earlier parts omitted)\n" + parts_txt[-14000:]
    user = (f"STORY: {r['name']}\nEND POINT: {end}\n\nPART SUMMARIES (in order):\n" + parts_txt +
            "\n\nKEY EVENTS (in order):\n" + "\n".join(f"- {(e['content'].split('. Involved:')[0] or e['name'])}" for e in events)[:10000] +
            "\n\nMAIN CAST:\n" + cast_txt +
            ("\n\nSTORY-SPECIFIC RULES:\n" + "\n".join(f"- {e['name']}: {_first_sentence(e['content'])}" for e in rules) if rules else ""))
    try:
        res = _request(provider, model, user, system=ARCHIVIST_SYSTEM)
    except Exception as ex:
        return jsonify({"error": f"The model call failed: {str(ex)[:200]}"}), 502
    summary = format_archive(res)
    if not summary:
        return jsonify({"error": "The model returned an empty summary. Try again or pick another model."}), 502
    conn = _conn()      # the whole summary is the Story So Far entry; the timeline stays one line per kept event
    conn.execute("UPDATE text_projects SET recap_text=?, recap_upto=?, timeline_text='' WHERE id=?", (summary, upto, pid))
    conn.commit()
    conn.close()
    _log(f"AI recap for project={pid} ({provider}/{model or 'default'}): {len(summary)} chars, end point: {end}"
         + (f", {arcs} earlier arc(s) condensed first" if arcs else ""))
    return jsonify({"text": summary, "timeline": "", "upto": upto, "edited": True, "arcs": arcs})


def _wi_of(it):
    """World Info fields an item carries (Story So Far, Cast Roster) -> save_lore_entry keyword arguments."""
    wi = {}
    if it.get("constant") is not None:
        wi["constant"] = 1 if it["constant"] else 0
    if it.get("position") is not None:
        wi["position"] = int(it["position"])
    if it.get("depth") is not None:
        wi["entry_depth"] = int(it["depth"])
    if it.get("role") is not None:
        wi["role"] = int(it["role"])
    return wi


@bp.post("/api/text/project/<int:pid>/commit")
def api_text_commit(pid):
    """Send the kept entries to LORE. The first send makes a new LORE project. Later sends UPDATE that project
    (body {"mode": "update"}, the default when it still exists): entries edited by hand in LORE are kept as they are,
    the rest are refreshed, new ones are added, and ones no longer kept go to the LORE trash (restorable).
    {"mode": "new"} always makes a fresh project."""
    r = _project_row(pid)
    if not r:
        return jsonify({"error": "Not found"}), 404
    if not any(e["keep"] for e in _entities(pid)):
        return jsonify({"error": "No entities marked keep"}), 400
    d = request.get_json(silent=True) or {}
    items, upto = _lore_items(pid)
    existing = r["lore_project_id"] if "lore_project_id" in r.keys() else None
    if existing and not any(p["id"] == existing for p in list_lore_projects()):
        existing = None
    mode = d.get("mode") or ("update" if existing else "new")
    if mode == "update" and existing:
        stats = _update_lore_project(existing, items)
        _log(f"re-send project={pid} -> lore project {existing}: {stats}")
        return jsonify({"lore_project_id": existing, "entries": len(items), "mode": "update", **stats})
    # a new lore project; give repeats a distinct name so they are easy to tell apart
    taken = {p["project_name"] for p in list_lore_projects()}
    lore_name, n_dup = r["name"], 1
    while lore_name in taken:
        n_dup += 1
        lore_name = f"{r['name']} ({n_dup})"
    lore_pid = create_lore_project(lore_name)
    for it in items:
        save_lore_entry(crawl_id=lore_pid, source_id=None, title=it["title"], entry_type=it["entry_type"],
                        keywords=it["keys"], summary=it["summary"], content=it["content"],
                        provider="text-module", model="", **_wi_of(it))
    conn = _conn()
    conn.execute("UPDATE text_projects SET lore_project_id=?, status='committed' WHERE id=?", (lore_pid, pid))
    conn.commit()
    conn.close()
    _log(f"commit project={pid} -> lore project {lore_pid}, {len(items)} entries"
         + (f" (roleplay starts after chunk {upto + 1})" if upto >= 0 else ""))
    return jsonify({"lore_project_id": lore_pid, "entries": len(items), "mode": "new", "added": len(items)})


def _update_lore_project(lore_pid, items):
    conn = _conn()
    rows = conn.execute("SELECT id, title, provider, COALESCE(user_edited, 0) AS user_edited, COALESCE(deleted, 0) AS deleted "
                        "FROM lore_entries WHERE crawl_id=?", (lore_pid,)).fetchall()
    by_title = {}
    for row in rows:
        by_title.setdefault(row["title"].strip().lower(), row)
    added = updated = kept_edited = trashed = 0
    seen = set()
    new_items = []
    for it in items:
        key = it["title"].strip().lower()
        seen.add(key)
        row = by_title.get(key)
        if row is None:
            new_items.append(it)
            continue
        if row["user_edited"]:
            kept_edited += 1
            if row["deleted"]:
                pass               # the user deleted it in LORE: leave it in the trash
            continue
        if row["deleted"]:
            continue               # deleted in LORE on purpose: don't bring it back
        conn.execute("UPDATE lore_entries SET keywords_json=?, summary=?, content=?, entry_type=?, "
                     "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (json.dumps(it["keys"], ensure_ascii=False), it["summary"], it["content"], it["entry_type"], row["id"]))
        updated += 1
        wi = _wi_of(it)
        if wi:
            conn.execute(f"UPDATE lore_entries SET {', '.join(k + '=?' for k in wi)} WHERE id=?", list(wi.values()) + [row["id"]])
    for key, row in by_title.items():
        if key not in seen and row["provider"] == "text-module" and not row["user_edited"] and not row["deleted"]:
            conn.execute("UPDATE lore_entries SET deleted=1, updated_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))
            trashed += 1
    conn.commit()
    conn.close()
    for it in new_items:
        save_lore_entry(crawl_id=lore_pid, source_id=None, title=it["title"], entry_type=it["entry_type"],
                        keywords=it["keys"], summary=it["summary"], content=it["content"],
                        provider="text-module", model="", **_wi_of(it))
        added += 1
    return {"added": added, "updated": updated, "kept_edited": kept_edited, "trashed": trashed}


# ══════════════════════════════════════════════════════════════════════════════
# Cards: a character from review -> CHARACTER studio source, and a World Narrator card
# ══════════════════════════════════════════════════════════════════════════════
def _events_with(pid, name, aliases, upto=-1):
    keys = [n for n in [name] + list(aliases) if n]
    out = []
    for e in sorted(_entities(pid), key=lambda e: e["id"]):
        if e["entity_type"] != "event" or not e["keep"]:
            continue
        if upto >= 0 and e.get("first_chunk", -1) > upto:
            continue
        text = f"{e['name']} {e['content']}".lower()
        if any(k.lower() in text for k in keys):
            out.append((e["content"].split(". Involved:")[0].strip() or e["name"]))
    return out


@bp.post("/api/text/entity/<int:eid>/to-source")
def api_text_entity_to_source(eid):
    """Turn a reviewed character into a CHARACTER studio source (like a scraped wiki page), so the normal
    Generate Card flow writes a full card from the fic's facts, voice lines, relationships and events."""
    res = entity_to_source(eid)
    if res is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(res)


def main_cast(pid, limit=8):
    """Kept main-tier characters, most mentioned first (the batch 'cards for the main cast')."""
    r = _project_row(pid)
    n = len(json.loads(r["chunks_json"] or "[]")) if r else 0
    chars = [e for e in _entities(pid) if e["keep"] and e["entity_type"] == "character" and entity_tier(e, n) == "main"]
    return sorted(chars, key=lambda e: -int(e.get("mentions") or 1))[:limit]


def entity_to_source(eid):
    """{source_id, source, story_point, lore_project_id} for one reviewed character, or None."""
    conn = _conn()
    row = conn.execute("SELECT * FROM text_entities WHERE id=?", (eid,)).fetchone()
    conn.close()
    if not row:
        return None
    e = _row_entity(row)
    r = _project_row(e["project_id"])
    recap, _, upto = _project_recap(e["project_id"])
    events = _events_with(e["project_id"], e["name"], e["aliases"], upto)[:12]
    rels = [f"{x['with']}: {x['relation']}" for x in e["relations"]]
    facts = lore_entry_content({**e, "voice": [], "relations": []})
    infobox = {k: v for k, v in (("Age", e["age"]), ("Also known as", ", ".join(e["aliases"][:6])),
                                 ("Story", r["name"] if r else ""),
                                 ("Origin", {"altered": "changed by this story", "original": "original to this story",
                                             "canon": "as in canon"}.get(e["origin"], ""))) if v}
    sections = {"Notes from the story": [facts]}
    if rels:
        sections["Relationships"] = rels
    if e["voice"]:
        sections["How they speak"] = [f'"{v}"' for v in e["voice"]]
    if events:
        sections["Story events"] = events
    if recap:
        sections["Story so far"] = [recap]
    source_id = save_source({
        "wiki_base": "text-studio", "page_name": e["name"],
        "url": f"text://project/{e['project_id']}/entity/{eid}", "title": e["name"], "raw_html": "",
        "raw_infobox": infobox, "raw_sections": sections,
        "normalized": {
            "title": e["name"], "summary": facts, "franchise": r["name"] if r else "",
            "normalized_infobox": infobox, "relationships": rels, "speech_patterns": e["voice"],
            "history_list": events, "personality_traits": [], "appearance_list": [], "abilities_list": [],
            "uncategorized_sections": {k: v for k, v in sections.items() if k != "Notes from the story"},
        },
    })
    from database import get_source
    labels = _chunk_labels(r) if r else []
    story_point = (f"{r['name']}, right after {labels[upto]}" if r and 0 <= upto < len(labels)
                   else (f"{r['name']}, as of the latest chapter" if r else ""))
    lore_id = r["lore_project_id"] if r is not None and "lore_project_id" in r.keys() else None
    _log(f"make card: '{e['name']}' -> character source {source_id}")
    return {"source_id": source_id, "source": get_source(source_id), "story_point": story_point,
            "lore_project_id": lore_id}


NARRATOR_SYSTEM = """You write a SillyTavern character card for a NARRATOR / game master who runs a roleplay inside the
world of a story. The user plays a character in that world; the narrator describes scenes, voices every other
character, and keeps the world's rules and the story so far consistent. Return ONLY JSON, no fences:
{"name": "", "description": "", "personality": "", "scenario": "", "first_mes": "", "system_prompt": "", "tags": []}
- name: "<Story title> Narrator" or similar.
- description: 150-300 words: the setting, its key rules and what makes this story's version of the world different,
  and the main cast in one line each. Use only the material given.
- personality: the narrator's style in 1-3 sentences (e.g. vivid, fair, keeps the cast in character).
- scenario: where things stand at the start of the roleplay (from the story so far), 2-4 sentences.
- first_mes: an opening narration of 80-200 words that sets the scene at that point and invites {{user}} to act.
  Never act or speak for {{user}}.
- system_prompt: short rules for the narrator: describe, voice NPCs, never control {{user}}, follow the lorebook.
- tags: 3-6 short tags."""


def _narrator_fallback(name, recap, cast, rules):
    desc = f"The world of {name}."
    if rules:
        desc += " Key points of this story's world: " + " ".join(rules[:6])
    if cast:
        desc += "\n\nMain cast: " + "; ".join(cast[:10]) + "."
    return {
        "name": f"{name} Narrator", "description": desc,
        "personality": "A vivid, fair narrator who keeps every character true to the story.",
        "scenario": recap[:800] if recap else f"The story of {name} continues.",
        "first_mes": (recap.split(". ")[-1] if recap else f"The world of {name} stirs.") +
                     "\n\nThe scene is set. What do you do, {{user}}?",
        "system_prompt": "You are the narrator. Describe scenes, voice every character except {{user}}, keep to the "
                         "story's facts and the lorebook, and never act or speak for {{user}}.",
        "tags": ["narrator", "fanfiction", "world"],
    }


@bp.post("/api/text/project/<int:pid>/narrator")
def api_text_narrator(pid):
    """Build a World Narrator card (V2) for roleplaying inside the story, with the reviewed lore embedded as its
    character_book. Also saved to the card library so it can be edited in the CHARACTER studio."""
    r = _project_row(pid)
    if not r:
        return jsonify({"error": "Not found"}), 404
    d = request.get_json(force=True) or {}
    provider, model = d.get("provider", "nanogpt"), d.get("model", "")
    items, upto = _lore_items(pid)
    recap = next((it["content"] for it in items if it["title"] == "Story So Far"), "")
    ents = _entities(pid)
    chunks_n = len(json.loads(r["chunks_json"] or "[]"))
    kept = [e for e in ents if e["keep"] and e["entity_type"] != "event"]
    main = sorted(kept, key=lambda e: -int(e.get("mentions") or 1))
    cast = [f"{e['name']} - {_first_sentence(e['content'])}" for e in main if e["entity_type"] == "character"][:12]
    rules = [f"{e['name']}: {_first_sentence(e['content'])}" for e in main
             if e["entity_type"] in ("concept", "faction", "place", "ability", "item")
             and (e.get("origin") in ("altered", "original") or entity_tier(e, chunks_n) == "main")][:14]
    user = (f"STORY: {r['name']}\n\nSTORY SO FAR (roleplay starts here):\n{recap or '(not available)'}\n\n"
            f"MAIN CAST:\n" + "\n".join(f"- {c}" for c in cast) +
            "\n\nWORLD RULES / KEY PLACES / FIC-SPECIFIC POINTS:\n" + "\n".join(f"- {x}" for x in rules))
    try:
        res = _request(provider, model, user, system=NARRATOR_SYSTEM)
        card = {k: res.get(k) for k in ("name", "description", "personality", "scenario", "first_mes",
                                          "system_prompt", "tags")}
        if not str(card.get("description") or "").strip() or not str(card.get("first_mes") or "").strip():
            raise ValueError("model returned an incomplete card")
        _log(f"narrator card for project={pid} written by {provider}/{model or 'default'}")
    except Exception as ex:
        _log(f"narrator card: model step failed ({str(ex)[:120]}); using the template version")
        card = _narrator_fallback(r["name"], recap, cast, rules)
    card = {**card, "name": str(card.get("name") or f"{r['name']} Narrator").strip(),
            "tags": [str(t) for t in (card.get("tags") or [])][:8], "mes_example": "",
            "creator_notes": f"World narrator for '{r['name']}', built in Character Card Studio's TEXT studio. "
                             f"The story's lorebook is embedded.", "alternate_greetings": [],
            "structured_profile": {}, "provider": provider, "model": model}
    source_id = save_source({
        "wiki_base": "text-studio", "page_name": "narrator", "url": f"text://project/{pid}/narrator",
        "title": card["name"], "raw_html": "", "raw_infobox": {}, "raw_sections": {"Story so far": [recap]} if recap else {},
        "normalized": {"title": card["name"], "summary": recap, "franchise": r["name"]},
    })
    card_id = create_or_update_card(source_id, card)       # re-running replaces this story's narrator card
    v2 = build_export_card_json({**get_card(card_id), **card})
    book_items = normalise_lore_items(items)
    if book_items:
        v2["data"]["character_book"] = character_book_from_items(r["name"], book_items)
    return jsonify({"card_id": card_id, "card": v2, "entries": len(book_items)})


def build_timeline(events):
    lines, used = [], 0
    for e in events:
        ln = "- " + ((e.get("content") or "").split(". Involved:")[0].strip() or e["name"])
        if used + len(ln) > TIMELINE_CHARS:
            lines.append("- (timeline truncated)")
            break
        lines.append(ln)
        used += len(ln) + 1
    return "\n".join(lines)


def deep_entries_from_text(text, provider, model, condense=False):
    """Deep-extract lore entries from plain text (used by the LORE studio's deep mode).
    Returns a list of {title, entry_type, keywords, summary, content, related_entries}."""
    chunks = chunk_text(text, DEFAULT_CHUNK_CHARS)
    results = {}
    for c in chunks:
        try:
            results[c["idx"]] = extract_chunk(c, provider, model, "deep")
        except Exception as e:
            _log(f"deep chunk {c['idx']} failed: {e}")
    labels = {c["idx"]: c["label"] for c in chunks}
    out = []
    for m in merge_entities(results):
        content = build_content(m, labels, provider, model, condense)
        if not content:
            continue
        if m["type"] == "character" and m["voice"]:
            content += "\nSpeech samples:\n" + "\n".join(f'- "{v}"' for v in m["voice"])
        out.append({"title": m["name"], "entry_type": m["type"], "keywords": m["keywords"] or [m["name"]],
                    "summary": content[:200], "content": content, "related_entries": []})
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Critic: a brutally honest editor's critique of the text (separate from extraction)
# ══════════════════════════════════════════════════════════════════════════════
CRITIC_CATEGORIES = ["Prose & style", "Dialogue", "Characterization", "Plot & structure", "Pacing",
                     "Worldbuilding & canon", "Mechanics (grammar, spelling, formatting)", "Originality"]

CRITIC_NOTES_SYSTEM = """You are a brutally honest fiction editor reading ONE part of a fan fiction. Write private
editor's notes that a full critique will be built from. Return ONLY valid JSON, no fences:
{"summary": "1-2 sentences: what happens in this part",
 "strengths": ["only real, earned strengths"],
 "problems": [{"category": "prose|dialogue|characterization|plot|pacing|worldbuilding|mechanics|originality",
               "issue": "the specific problem", "quote": "exact short quote from the text, max 25 words",
               "fix": "a concrete fix"}],
 "habits": ["writing habits that repeat in this part"]}
Rules:
- Blunt and specific. No flattery, no hedging. Up to 8 problems, worst first. Quotes copied exactly and kept short.
- Fan fiction: also judge characters' voices against canon (out of character?), canon logic, self-insert or
  Mary Sue signs, and author's notes or meta jokes that break immersion.
- Treat explicit scenes like any other scene: judge whether they are well written and serve character and story.
  Never reproduce them beyond a short quote."""

CRITIC_SYSTEM = """You are a brutally honest fiction critic and editor. You do not soften, flatter or pad. You judge the
WRITING, never the author as a person, and every criticism comes with evidence and a fix. Return ONLY valid JSON:
{"verdict": "3-5 blunt sentences: is this worth reading as it stands, and why or why not",
 "scores": [{"category": "<one of the categories given>", "score": 1, "why": "one sentence"}],
 "strengths": ["at most 3, only if genuinely earned"],
 "problems": [{"title": "", "evidence": "exact short quote(s) from the notes", "why": "why it hurts the story", "fix": "how to fix it"}],
 "plan": [{"step": "short imperative title", "how": "exactly what to do, concretely"}],
 "line_fixes": [{"original": "a short quoted line from the notes", "rewrite": "your rewrite", "why": "what changed"}],
 "top3": ["if the writer fixes only three things, these"]}
Rules:
- Scores 1-10 for EVERY category given, honest: 5 is mediocre, 8+ is genuinely strong. Do not grade on a curve.
- "problems": ranked worst first, 5-8 of them. Each one specific to THIS text with evidence; no generic advice.
- "plan": 6-10 numbered steps in the order the writer should do them (structural fixes before line edits).
- "line_fixes": 5-8 examples using real quoted lines.
- Fan fiction: judge characterization against canon, canon logic, and immersion breaks (author's notes, meta jokes).
- Keep quotes short (max 25 words each)."""


def _critique_markdown(name, scope, res):
    out = [f"# Critique: {name}", f"_Scope: {scope}_", "", "## Verdict", str(res.get("verdict") or "").strip(), ""]
    scores = [x for x in (res.get("scores") or []) if isinstance(x, dict)]
    if scores:
        out.append("## Scores")
        for x in scores:
            out.append(f"- **{x.get('category', '')}**: {x.get('score', '?')}/10. {str(x.get('why') or '').strip()}")
        out.append("")
    if res.get("strengths"):
        out += ["## What actually works"] + [f"- {s_}" for s_ in res["strengths"]] + [""]
    probs = [x for x in (res.get("problems") or []) if isinstance(x, dict)]
    if probs:
        out.append("## The biggest problems")
        for i, x in enumerate(probs, 1):
            out.append(f"{i}. **{x.get('title', '')}**")
            if x.get("evidence"):
                out.append(f"   - Evidence: {x['evidence']}")
            if x.get("why"):
                out.append(f"   - Why it hurts: {x['why']}")
            if x.get("fix"):
                out.append(f"   - Fix: {x['fix']}")
        out.append("")
    plan = [x for x in (res.get("plan") or []) if isinstance(x, dict)]
    if plan:
        out.append("## Step-by-step improvement plan")
        for i, x in enumerate(plan, 1):
            out.append(f"{i}. **{x.get('step', '')}**: {x.get('how', '')}")
        out.append("")
    fixes = [x for x in (res.get("line_fixes") or []) if isinstance(x, dict)]
    if fixes:
        out.append("## Line-level fixes")
        for x in fixes:
            out.append(f"- Before: \u201c{x.get('original', '')}\u201d")
            out.append(f"  After: \u201c{x.get('rewrite', '')}\u201d" + (f" ({x['why']})" if x.get("why") else ""))
        out.append("")
    if res.get("top3"):
        out += ["## If you only fix three things"] + [f"{i}. {t}" for i, t in enumerate(res["top3"], 1)]
    return "\n".join(out).strip() + "\n"


@bp.post("/api/text/project/<int:pid>/critique")
def api_text_critique(pid):
    """Background job: editor's notes per part (in parallel), then one full critique. Stored for later viewing."""
    r = _project_row(pid)
    if not r:
        return jsonify({"error": "Not found"}), 404
    d = request.get_json(force=True) or {}
    provider, model = d.get("provider", "nanogpt"), d.get("model", "")
    focus = str(d.get("focus") or "").strip()
    chunks = json.loads(r["chunks_json"] or "[]")
    pick = {int(i) for i in (d.get("chunks") or []) if str(i).isdigit()}
    sel = [c for c in chunks if not pick or c["idx"] in pick]
    if not sel:
        return jsonify({"error": "Nothing to critique: load a text first."}), 400
    scope = str(d.get("scope_label") or ("Whole text" if not pick else f"{len(sel)} part(s)"))
    workers = max(1, min(int(d.get("parallel") or 3), 6))
    job_id = _create_job()

    def run():
        t0 = time.time()
        try:
            _log(f"[CRITIC] project={pid} '{r['name']}' scope='{scope}' parts={len(sel)} {provider}/{model or 'default'}")
            notes = {}
            if len(sel) == 1:
                notes[sel[0]["idx"]] = None        # one part: the critic reads the text itself
            else:
                _update_job(job_id, status="running", stage="requesting_model", progress=5,
                            message=f"Critic is reading {len(sel)} parts ({workers} at a time)...")
                done = 0
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futs = {ex.submit(_request, provider, model, f"PART: {c['label']}\n\n{c['text']}",
                                      system=CRITIC_NOTES_SYSTEM): c for c in sel}
                    for fut in as_completed(futs):
                        c = futs[fut]
                        done += 1
                        try:
                            notes[c["idx"]] = fut.result()
                        except Exception as e:
                            _log(f"[CRITIC] notes for part {c['idx'] + 1} failed: {str(e)[:120]}")
                        _update_job(job_id, status="running", stage="requesting_model",
                                    progress=5 + int(done / len(sel) * 70),
                                    message=f"Critic read {done}/{len(sel)} parts")
                if not notes:
                    raise RuntimeError("The critic could not read any part (all model calls failed).")
            _update_job(job_id, status="running", stage="generating", progress=80, message="Writing the critique...")
            cats = ", ".join(CRITIC_CATEGORIES)
            if len(sel) == 1:
                body = f"TEXT ({sel[0]['label']}):\n{sel[0]['text']}"
            else:
                lines = []
                for c in sel:
                    n = notes.get(c["idx"])
                    if not isinstance(n, dict):
                        continue
                    lines.append(f"### {c['label']}\nWhat happens: {n.get('summary', '')}")
                    for s_ in n.get("strengths") or []:
                        lines.append(f"+ {s_}")
                    for p_ in n.get("problems") or []:
                        if isinstance(p_, dict):
                            lines.append(f"- [{p_.get('category', '')}] {p_.get('issue', '')} | quote: \"{p_.get('quote', '')}\""
                                         f" | fix: {p_.get('fix', '')}")
                    for h in n.get("habits") or []:
                        lines.append(f"~ habit: {h}")
                body = "EDITOR'S NOTES PER PART:\n" + "\n".join(lines)[:40000]
            user = (f"STORY: {r['name']}\nSCOPE: {scope}\nCATEGORIES TO SCORE: {cats}\n"
                    + (f"FOCUS ESPECIALLY ON: {focus}\n" if focus else "") + "\n" + body)
            res = _request(provider, model, user, system=CRITIC_SYSTEM)
            if not str(res.get("verdict") or "").strip():
                raise RuntimeError("The model returned an empty critique. Try again or pick another model.")
            res["markdown"] = _critique_markdown(r["name"], scope, res)
            conn = _conn()
            cur = conn.execute("INSERT INTO text_critiques (project_id, scope, focus, provider, model, result_json) "
                               "VALUES (?,?,?,?,?,?)", (pid, scope, focus, provider, model, json.dumps(res, ensure_ascii=False)))
            cid = cur.lastrowid
            conn.commit()
            conn.close()
            _log(f"[CRITIC] done in {time.time() - t0:.1f}s -> critique {cid}")
            _update_job(job_id, status="done", stage="done", progress=100, message="Critique ready",
                        result={"critique_id": cid})
        except Exception as e:
            _log(f"[CRITIC] FAILED after {time.time() - t0:.1f}s: {e}")
            _update_job(job_id, status="failed", stage="failed", progress=100, message=str(e), error=str(e))

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})


@bp.get("/api/text/project/<int:pid>/critiques")
def api_text_critiques(pid):
    conn = _conn()
    rows = conn.execute("SELECT id, scope, focus, provider, model, created_at, result_json FROM text_critiques "
                        "WHERE project_id=? ORDER BY id DESC", (pid,)).fetchall()
    conn.close()
    out = []
    for x in rows:          # scores ride along so the studio can draw a score history without loading each critique
        d = dict(x)
        try:
            res = json.loads(d.pop("result_json") or "{}")
        except Exception:
            res = {}
        sc = {str(s_.get("category")): s_.get("score") for s_ in (res.get("scores") or [])
              if isinstance(s_, dict) and isinstance(s_.get("score"), (int, float))}
        d["scores"] = sc
        d["avg"] = round(sum(sc.values()) / len(sc), 1) if sc else None
        d["kind"] = "sweep" if res.get("sweep") else "critique"
        out.append(d)
    return jsonify(out)


@bp.get("/api/text/critique/<int:cid>")
def api_text_critique_get(cid):
    conn = _conn()
    row = conn.execute("SELECT * FROM text_critiques WHERE id=?", (cid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    d = dict(row)
    d["result"] = json.loads(d.pop("result_json"))
    return jsonify(d)


@bp.delete("/api/text/critique/<int:cid>")
def api_text_critique_delete(cid):
    conn = _conn()
    conn.execute("DELETE FROM text_critiques WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return jsonify({"deleted": cid})


def register_text_module(app, create_job, update_job):
    global _create_job, _update_job
    _create_job, _update_job = create_job, update_job
    init_text_tables()
    app.register_blueprint(bp)
