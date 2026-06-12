import json
import sqlite3
from pathlib import Path
from typing import Any, Dict

DB_PATH = str(Path(__file__).resolve().parent / "fandom_chars.db")

DEFAULT_STRUCTURED_PROFILE = {
    "sex": "",
    "species": "",
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
}


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    # Run column migrations before creating tables
    try:
        conn = _conn()
        conn.execute("ALTER TABLE lore_crawls ADD COLUMN project_name TEXT DEFAULT 'Untitled Project'")
        conn.commit()
        conn.close()
    except Exception:
        pass  # Column already exists

    try:
        conn = _conn()
        conn.execute("ALTER TABLE cards ADD COLUMN alternate_greetings_json TEXT DEFAULT '[]'")
        conn.commit()
        conn.close()
    except Exception:
        pass
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
    source_id: int, card_data: Dict[str, Any], card_id: int | None = None
) -> int:
    conn = _conn()
    cur = conn.cursor()

    structured_profile = card_data.get("structured_profile", DEFAULT_STRUCTURED_PROFILE)
    tags = card_data.get("tags", [])

    if card_id is None:
        cur.execute(
            "SELECT id FROM cards WHERE source_id = ? ORDER BY id DESC LIMIT 1",
            (source_id,),
        )
        row = cur.fetchone()
        if row:
            card_id = row[0]

    if card_id is None:
        cur.execute(
            """
            INSERT INTO cards (
                source_id, name, structured_profile_json, description, personality,
                scenario, first_mes, mes_example, tags_json, provider, model
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        conn.commit()
        card_id = cur.lastrowid
    else:
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
        LEFT JOIN lore_entries le ON le.crawl_id = lc.id
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
) -> int:
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
    return lore_id


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
    return entry


def list_lore_entries() -> list[Dict[str, Any]]:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            le.id,
            le.crawl_id,
            le.title,
            le.entry_type,
            le.summary,
            le.provider,
            le.model,
            le.updated_at,
            le.created_at,
            s.title AS source_title,
            s.url AS source_url
        FROM lore_entries le
        LEFT JOIN sources s ON s.id = le.source_id
        ORDER BY le.updated_at DESC, le.id DESC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    for row in rows:
        row["keywords"] = json.loads(row.get("keywords_json") or "[]")

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
