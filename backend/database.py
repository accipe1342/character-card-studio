"""
database.py — SQLite persistence layer
=======================================
The single source of truth for all stored data. Every read and write
to the database goes through this file. No other module opens the DB
directly — they all import from here.

SCHEMA OVERVIEW
---------------
sources
    Raw scraped wiki page data. One row per URL scraped.
    Stores the original HTML, infobox dict, section text, and a
    normalised summary used by the generator.

cards
    Generated SillyTavern V2 character cards.
    Foreign-keyed to sources (one source can produce many cards).
    Stores all V2 fields: description, personality, scenario,
    first_mes, mes_example, structured_profile (JSON), tags (JSON),
    alternate_greetings (JSON), and the provider/model used.

lore_crawls
    A named project that groups lore entries together.
    Created when you start a lore generation run.

lore_entries
    Individual lorebook entries belonging to a crawl/project.
    Stores keywords (JSON), content, summary, entry_type, and
    SillyTavern-specific fields: scan_depth, insertion_order,
    entry_depth.

field_versions
    Version history for individual card fields.
    Every time a field is regenerated, the old value is saved here.
    Allows future undo/history features.

HOW TO EXTEND
-------------
- Adding a column: add it to the CREATE TABLE statement AND add an
  ALTER TABLE migration in the migrations list inside init_db().
  The migration will silently skip if the column already exists.
- Adding a table: add a CREATE TABLE IF NOT EXISTS block in init_db().
- Adding a query: write a new function that calls _conn() directly.
  Always close the connection when done — this module uses per-call
  connections rather than a persistent pool.

NOTES
-----
- WAL mode is enabled on startup for better concurrent performance.
- DB file lives at data/fandom_chars.db (relative to project root).
  Change DB_PATH to relocate it.
- All JSON fields (tags, keywords, structured_profile, etc.) are
  stored as TEXT and serialised/deserialised with json.dumps/loads.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict

DB_PATH = str(Path(__file__).resolve().parent.parent / "data" / "fandom_chars.db")

DEFAULT_STRUCTURED_PROFILE = {
    "sex": "",
    "species": "",
    "ethnicity": "",
    "race": "",
    "job_occupation": "",
    "gender": "",
    "sexual_attraction": "",
    "pronouns": "",
    "appearance": [],
    "non_human_appearance": [],
    "personal_parts": [],
    "clothing": [],
    "accessories": [],
    "relationship_to_user": "",
    "relationship_status": "",
    "backstory": "",
    "speech": [],
    "personality_traits": [],
    "kinks": [],
    "likes": [],
    "dislikes": [],
    "loves": [],
    "hates": [],
    "height": "",
    "weight": "",
    "age": "",
    "story_point": "",
    "motivations": [],
    "flaws": [],
    "mannerisms": [],
    "relationships": [],
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    # Enable WAL mode for better concurrent read/write performance
    conn = _conn()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.commit()
    conn.close()

    # Run column migrations before creating tables
    for migration in [
        "ALTER TABLE lore_crawls ADD COLUMN project_name TEXT DEFAULT 'Untitled Project'",
        "ALTER TABLE cards ADD COLUMN alternate_greetings_json TEXT DEFAULT '[]'",
        "ALTER TABLE lore_entries ADD COLUMN scan_depth INTEGER DEFAULT 2",
        "ALTER TABLE lore_entries ADD COLUMN insertion_order INTEGER DEFAULT 100",
        "ALTER TABLE lore_entries ADD COLUMN entry_depth INTEGER DEFAULT 4",
    ]:
        try:
            conn = _conn()
            conn.execute(migration)
            conn.commit()
            conn.close()
        except Exception:
            pass  # Column already exists
    conn = _conn()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wiki_base TEXT NOT NULL,
            page_name TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            title TEXT,
            raw_html TEXT,
            raw_infobox_json TEXT,
            raw_sections_json TEXT,
            normalized_source_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            name TEXT,
            structured_profile_json TEXT,
            description TEXT,
            personality TEXT,
            scenario TEXT,
            first_mes TEXT,
            mes_example TEXT,
            tags_json TEXT,
            provider TEXT,
            model TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_id) REFERENCES sources(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS field_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (card_id) REFERENCES cards(id)
        )
        """
    )
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS lore_crawls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seed_url TEXT NOT NULL,
        max_pages INTEGER NOT NULL DEFAULT 10,
        max_depth INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'queued',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """
    )

    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS lore_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        crawl_id INTEGER,
        source_id INTEGER,
        title TEXT NOT NULL,
        entry_type TEXT DEFAULT 'world',
        keywords_json TEXT DEFAULT '[]',
        summary TEXT DEFAULT '',
        content TEXT NOT NULL,
        provider TEXT DEFAULT '',
        model TEXT DEFAULT '',
        scan_depth INTEGER DEFAULT 2,
        insertion_order INTEGER DEFAULT 100,
        entry_depth INTEGER DEFAULT 4,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """
    )

    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS lore_crawl_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        crawl_id INTEGER NOT NULL,
        url TEXT NOT NULL,
        source_id INTEGER,
        depth INTEGER NOT NULL DEFAULT 0,
        page_title TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'queued',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    conn.commit()

    # Run column migrations after tables are created
    # Safe to run every startup — silently skips if column already exists
    for migration in [
        "ALTER TABLE lore_crawls ADD COLUMN project_name TEXT DEFAULT 'Untitled Project'",
        "ALTER TABLE cards ADD COLUMN alternate_greetings_json TEXT DEFAULT '[]'",
        # card fields SillyTavern uses that the editor never stored
        "ALTER TABLE cards ADD COLUMN system_prompt TEXT DEFAULT ''",
        "ALTER TABLE cards ADD COLUMN depth_prompt TEXT DEFAULT ''",        # Character's Note
        "ALTER TABLE cards ADD COLUMN creator_notes TEXT DEFAULT ''",
        "ALTER TABLE cards ADD COLUMN post_history TEXT DEFAULT ''",
        # full World Info fields per lore entry (NULL = use the type default at export)
        "ALTER TABLE lore_entries ADD COLUMN constant INTEGER",
        "ALTER TABLE lore_entries ADD COLUMN position INTEGER",
        "ALTER TABLE lore_entries ADD COLUMN role INTEGER DEFAULT 0",
        "ALTER TABLE lore_entries ADD COLUMN probability INTEGER DEFAULT 100",
        "ALTER TABLE lore_entries ADD COLUMN sticky INTEGER",
        "ALTER TABLE lore_entries ADD COLUMN cooldown INTEGER DEFAULT 0",
        "ALTER TABLE lore_entries ADD COLUMN delay INTEGER DEFAULT 0",
        "ALTER TABLE lore_entries ADD COLUMN secondary_keys_json TEXT DEFAULT '[]'",
        "ALTER TABLE lore_entries ADD COLUMN selective_logic INTEGER DEFAULT 0",
        "ALTER TABLE lore_entries ADD COLUMN char_filter_json TEXT DEFAULT '[]'",
        "ALTER TABLE lore_entries ADD COLUMN vectorized INTEGER DEFAULT 0",
        "ALTER TABLE lore_entries ADD COLUMN group_name TEXT DEFAULT ''",
        "ALTER TABLE lore_entries ADD COLUMN group_weight INTEGER DEFAULT 100",
        "ALTER TABLE lore_entries ADD COLUMN group_prioritize INTEGER DEFAULT 0",
        "ALTER TABLE lore_entries ADD COLUMN deleted INTEGER DEFAULT 0",       # trash
        "ALTER TABLE lore_entries ADD COLUMN user_edited INTEGER DEFAULT 0",   # hand-edited in LORE: re-send keeps it
        "ALTER TABLE lore_entries ADD COLUMN scan_depth INTEGER DEFAULT 2",
        "ALTER TABLE lore_entries ADD COLUMN insertion_order INTEGER DEFAULT 100",
        "ALTER TABLE lore_entries ADD COLUMN entry_depth INTEGER DEFAULT 4",
    ]:
        try:
            conn.execute(migration)
            conn.commit()
        except Exception:
            pass  # Column already exists

    # one-time: remember which entries had their order set by hand, so export can tell
    # "left at the default 100" from "chose 100" (see api_export_lorebook)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(lore_entries)")}
    conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, data_json TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS model_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT DEFAULT CURRENT_TIMESTAMP, provider TEXT, model TEXT,
        prompt_tokens INTEGER DEFAULT 0, completion_tokens INTEGER DEFAULT 0, seconds REAL DEFAULT 0)""")
    conn.commit()
    if "order_manual" not in cols:
        conn.execute("ALTER TABLE lore_entries ADD COLUMN order_manual INTEGER DEFAULT 0")
        conn.execute("UPDATE lore_entries SET order_manual = 1 WHERE insertion_order IS NOT NULL AND insertion_order != 100")
        conn.commit()

    conn.close()


def save_source(source: Dict[str, Any]) -> int:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO sources (
            wiki_base, page_name, url, title, raw_html,
            raw_infobox_json, raw_sections_json, normalized_source_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            title=excluded.title,
            raw_html=excluded.raw_html,
            raw_infobox_json=excluded.raw_infobox_json,
            raw_sections_json=excluded.raw_sections_json,
            normalized_source_json=excluded.normalized_source_json
        """,
        (
            source["wiki_base"],
            source["page_name"],
            source["url"],
            source["title"],
            source["raw_html"],
            json.dumps(source["raw_infobox"], ensure_ascii=False),
            json.dumps(source["raw_sections"], ensure_ascii=False),
            json.dumps(source["normalized"], ensure_ascii=False),
        ),
    )
    conn.commit()
    cur.execute("SELECT id FROM sources WHERE url = ?", (source["url"],))
    source_id = cur.fetchone()[0]
    conn.close()
    return source_id


def create_or_update_card(
    source_id: int, card_data: Dict[str, Any], card_id: int | None = None, force_new: bool = False
) -> int:
    """Update card_id (or the latest card made from this source); force_new always inserts a new card."""
    conn = _conn()
    cur = conn.cursor()

    structured_profile = card_data.get("structured_profile", DEFAULT_STRUCTURED_PROFILE)
    tags = card_data.get("tags", [])

    if card_id is None and not force_new:
        cur.execute(
            "SELECT id FROM cards WHERE source_id = ? ORDER BY id DESC LIMIT 1",
            (source_id,),
        )
        row = cur.fetchone()
        if row:
            card_id = row[0]

    if card_id is None:
        alternate_greetings = card_data.get("alternate_greetings", [])
        cur.execute(
            """
            INSERT INTO cards (
                source_id, name, structured_profile_json, description, personality,
                scenario, first_mes, mes_example, tags_json, provider, model,
                alternate_greetings_json, system_prompt, depth_prompt, creator_notes, post_history
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                card_data.get("name", ""),
                json.dumps(structured_profile, ensure_ascii=False),
                card_data.get("description", ""),
                card_data.get("personality", ""),
                card_data.get("scenario", ""),
                card_data.get("first_mes", ""),
                card_data.get("mes_example", ""),
                json.dumps(tags, ensure_ascii=False),
                card_data.get("provider", "nanogpt"),
                card_data.get("model", ""),
                json.dumps(alternate_greetings, ensure_ascii=False),
                card_data.get("system_prompt", "") or "",
                card_data.get("depth_prompt", card_data.get("character_note", "")) or "",
                card_data.get("creator_notes", "") or "",
                card_data.get("post_history", card_data.get("post_history_instructions", "")) or "",
            ),
        )
        conn.commit()
        card_id = cur.lastrowid
    else:
        alternate_greetings = card_data.get("alternate_greetings", [])
        cur.execute(
            """
            UPDATE cards SET
                name = ?,
                structured_profile_json = ?,
                description = ?,
                personality = ?,
                scenario = ?,
                first_mes = ?,
                mes_example = ?,
                tags_json = ?,
                provider = ?,
                model = ?,
                alternate_greetings_json = ?,
                system_prompt = COALESCE(?, system_prompt),
                depth_prompt = COALESCE(?, depth_prompt),
                creator_notes = COALESCE(?, creator_notes),
                post_history = COALESCE(?, post_history),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                card_data.get("name", ""),
                json.dumps(structured_profile, ensure_ascii=False),
                card_data.get("description", ""),
                card_data.get("personality", ""),
                card_data.get("scenario", ""),
                card_data.get("first_mes", ""),
                card_data.get("mes_example", ""),
                json.dumps(tags, ensure_ascii=False),
                card_data.get("provider", "nanogpt"),
                card_data.get("model", ""),
                json.dumps(alternate_greetings, ensure_ascii=False),
                card_data.get("system_prompt"),          # None = keep what is stored
                card_data.get("depth_prompt", card_data.get("character_note")),
                card_data.get("creator_notes"),
                card_data.get("post_history", card_data.get("post_history_instructions")),
                card_id,
            ),
        )
        conn.commit()

    conn.close()
    return card_id


def get_card(card_id: int) -> Dict[str, Any]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cards WHERE id = ?", (card_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        raise ValueError("Card not found")
    card = dict(row)
    card["structured_profile"] = json.loads(card["structured_profile_json"] or "{}")
    card["tags"] = json.loads(card["tags_json"] or "[]")
    card["alternate_greetings"] = json.loads(card.get("alternate_greetings_json") or "[]")
    return card


def get_source(source_id: int) -> Dict[str, Any]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sources WHERE id = ?", (source_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        raise ValueError("Source not found")
    source = dict(row)
    source["raw_infobox"] = json.loads(source["raw_infobox_json"] or "{}")
    source["raw_sections"] = json.loads(source["raw_sections_json"] or "{}")
    source["normalized"] = json.loads(source["normalized_source_json"] or "{}")
    return source


def save_field_version(
    card_id: int, field_name: str, old_value: str | None, new_value: str | None
) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO field_versions (card_id, field_name, old_value, new_value) VALUES (?, ?, ?, ?)",
        (card_id, field_name, old_value, new_value),
    )
    conn.commit()
    conn.close()


def list_cards() -> list[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            c.id,
            c.name,
            c.provider,
            c.model,
            c.updated_at,
            s.title,
            s.url
        FROM cards c
        JOIN sources s ON s.id = c.source_id
        ORDER BY c.updated_at DESC, c.id DESC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def delete_card(card_id: int) -> None:
    conn = _conn()
    conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    conn.commit()
    conn.close()


def duplicate_card(card_id: int) -> int:
    card = get_card(card_id)
    card["name"] = card.get("name", "Unnamed") + " (Copy)"
    return create_or_update_card(card["source_id"], card, card_id=None)


def rename_card(card_id: int, name: str) -> None:
    conn = _conn()
    conn.execute("UPDATE cards SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (name, card_id))
    conn.commit()
    conn.close()


def list_lore_projects() -> list[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT lc.id, lc.project_name, lc.seed_url, lc.created_at,
               COUNT(le.id) as entry_count
        FROM lore_crawls lc
        LEFT JOIN lore_entries le ON le.crawl_id = lc.id AND COALESCE(le.deleted, 0) = 0
        GROUP BY lc.id
        ORDER BY lc.created_at DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def rename_lore_project(crawl_id: int, name: str) -> None:
    conn = _conn()
    conn.execute("UPDATE lore_crawls SET project_name = ? WHERE id = ?", (name, crawl_id))
    conn.commit()
    conn.close()


def delete_lore_project(crawl_id: int) -> None:
    conn = _conn()
    conn.execute("DELETE FROM lore_entries WHERE crawl_id = ?", (crawl_id,))
    conn.execute("DELETE FROM lore_crawls WHERE id = ?", (crawl_id,))
    conn.commit()
    conn.close()


def create_lore_project(name: str) -> int:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO lore_crawls (seed_url, max_pages, max_depth, status, project_name) VALUES (?, ?, ?, ?, ?)",
        ("", 0, 0, "project", name)
    )
    conn.commit()
    project_id = cur.lastrowid
    conn.close()
    return project_id


def save_lore_entry(
    crawl_id: int | None,
    source_id: int | None,
    title: str,
    entry_type: str,
    keywords: list[str],
    summary: str,
    content: str,
    provider: str = "",
    model: str = "",
    **wi,
) -> int:
    """wi: optional World Info fields (constant, position, role, sticky, ...) — see set_lore_wi_fields."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO lore_entries (
            crawl_id,
            source_id,
            title,
            entry_type,
            keywords_json,
            summary,
            content,
            provider,
            model
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            crawl_id,
            source_id,
            title,
            entry_type,
            json.dumps(keywords, ensure_ascii=False),
            summary,
            content,
            provider,
            model,
        ),
    )
    conn.commit()
    lore_id = cur.lastrowid
    conn.close()
    if wi:
        set_lore_wi_fields(lore_id, wi)
    return lore_id


WI_FIELDS = {"constant", "position", "role", "probability", "sticky", "cooldown", "delay", "selective_logic",
             "vectorized", "group_name", "group_weight", "group_prioritize", "secondary_keys", "char_filter",
             "scan_depth", "entry_depth", "insertion_order", "order_manual", "user_edited"}


def set_lore_wi_fields(lore_id: int, fields: Dict[str, Any]) -> None:
    sets, vals = [], []
    for k, v in fields.items():
        if k not in WI_FIELDS:
            continue
        if k in ("secondary_keys", "char_filter"):
            sets.append(f"{k if k != 'secondary_keys' else 'secondary_keys'}_json = ?")
            vals.append(json.dumps([str(x).strip() for x in (v or []) if str(x).strip()], ensure_ascii=False))
        else:
            sets.append(f"{k} = ?")
            vals.append(v)
    if not sets:
        return
    conn = _conn()
    conn.execute(f"UPDATE lore_entries SET {', '.join(sets)} WHERE id = ?", vals + [lore_id])
    conn.commit()
    conn.close()


def get_lore_entry(lore_id: int) -> Dict[str, Any]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM lore_entries WHERE id = ?", (lore_id,))
    row = cur.fetchone()
    conn.close()

    if row is None:
        raise ValueError("Lore entry not found")

    entry = dict(row)
    entry["keywords"] = json.loads(entry.get("keywords_json") or "[]")
    for k in ("secondary_keys", "char_filter"):
        try:
            entry[k] = json.loads(entry.get(f"{k}_json") or "[]")
        except Exception:
            entry[k] = []
    entry.setdefault("scan_depth", 2)
    entry.setdefault("insertion_order", 100)
    entry.setdefault("order_manual", 0)
    entry.setdefault("entry_depth", 4)
    return entry


def list_lore_entries(crawl_id: int | None = None, deleted: bool = False) -> list[Dict[str, Any]]:
    """All lore entries, or only those of one project when crawl_id is given. deleted=True lists the trash."""
    sql = """
        SELECT
            le.id,
            le.crawl_id,
            le.title,
            le.entry_type,
            le.summary,
            le.keywords_json,
            LENGTH(COALESCE(le.content, '')) AS content_chars,
            le.constant,
            le.user_edited,
            le.provider,
            le.model,
            le.updated_at,
            le.created_at,
            s.title AS source_title,
            s.url AS source_url
        FROM lore_entries le
        LEFT JOIN sources s ON s.id = le.source_id
    """
    sql += " WHERE COALESCE(le.deleted, 0) = ?"
    params: tuple = (1 if deleted else 0,)
    if crawl_id is not None:
        sql += " AND le.crawl_id = ?"
        params = params + (crawl_id,)
    sql += " ORDER BY le.updated_at DESC, le.id DESC"
    conn = _conn()
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    for row in rows:
        try:
            row["keywords"] = json.loads(row.get("keywords_json") or "[]")
        except Exception:
            row["keywords"] = []

    return rows


def create_lore_crawl(
    seed_url: str, max_pages: int = 10, max_depth: int = 1, status: str = "queued"
) -> int:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO lore_crawls (seed_url, max_pages, max_depth, status)
        VALUES (?, ?, ?, ?)
        """,
        (seed_url, max_pages, max_depth, status),
    )
    conn.commit()
    crawl_id = cur.lastrowid
    conn.close()
    return crawl_id


def update_lore_crawl_status(crawl_id: int, status: str) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE lore_crawls
        SET status = ?
        WHERE id = ?
        """,
        (status, crawl_id),
    )
    conn.commit()
    conn.close()


def save_lore_crawl_page(
    crawl_id: int,
    url: str,
    source_id: int | None = None,
    depth: int = 0,
    page_title: str = "",
    status: str = "queued",
) -> int:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO lore_crawl_pages (
            crawl_id,
            url,
            source_id,
            depth,
            page_title,
            status
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (crawl_id, url, source_id, depth, page_title, status),
    )
    conn.commit()
    page_id = cur.lastrowid
    conn.close()
    return page_id


# ---------------------------------------------------------------------------
# Jobs (persisted so progress survives a restart) and model usage
# ---------------------------------------------------------------------------
def save_job_row(job: Dict[str, Any]) -> None:
    conn = _conn()
    conn.execute("INSERT OR REPLACE INTO jobs (id, data_json, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                 (job["id"], json.dumps(job, ensure_ascii=False, default=str)))
    conn.commit()
    conn.close()


def load_job_row(job_id: str) -> Dict[str, Any] | None:
    conn = _conn()
    row = conn.execute("SELECT data_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return json.loads(row[0]) if row else None


def mark_interrupted_jobs() -> int:
    """At start-up: jobs still 'running'/'queued' were cut off by a restart."""
    conn = _conn()
    rows = conn.execute("SELECT id, data_json FROM jobs").fetchall()
    n = 0
    for jid, data in rows:
        try:
            job = json.loads(data)
        except Exception:
            continue
        if job.get("status") in ("queued", "running"):
            job.update(status="failed", stage="failed", progress=100,
                       message="Interrupted: the backend restarted while this was running. Run it again.",
                       error="Interrupted by a backend restart. Run it again.")
            conn.execute("UPDATE jobs SET data_json = ? WHERE id = ?", (json.dumps(job, ensure_ascii=False, default=str), jid))
            n += 1
    conn.execute("DELETE FROM jobs WHERE updated_at < datetime('now', '-14 days')")
    conn.commit()
    conn.close()
    return n


def record_usage(provider: str, model: str, prompt_tokens: int, completion_tokens: int, seconds: float) -> None:
    try:
        conn = _conn()
        conn.execute("INSERT INTO model_usage (provider, model, prompt_tokens, completion_tokens, seconds) VALUES (?,?,?,?,?)",
                     (provider, model, int(prompt_tokens or 0), int(completion_tokens or 0), float(seconds or 0)))
        conn.commit()
        conn.close()
    except Exception:
        pass   # usage logging must never break a generation


def usage_summary(days: int = 30) -> list[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        """SELECT provider, model, COUNT(*) AS calls, SUM(prompt_tokens) AS prompt_tokens,
                  SUM(completion_tokens) AS completion_tokens, ROUND(SUM(seconds), 1) AS seconds,
                  MAX(ts) AS last_used
           FROM model_usage WHERE ts >= datetime('now', ?) GROUP BY provider, model ORDER BY calls DESC""",
        (f"-{int(days)} days",)).fetchall()
    conn.close()
    return [dict(zip(("provider", "model", "calls", "prompt_tokens", "completion_tokens", "seconds", "last_used"), r)) for r in rows]
