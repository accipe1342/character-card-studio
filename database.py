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


def create_or_update_card(source_id: int, card_data: Dict[str, Any], card_id: int | None = None) -> int:
    conn = _conn()
    cur = conn.cursor()

    structured_profile = card_data.get("structured_profile", DEFAULT_STRUCTURED_PROFILE)
    tags = card_data.get("tags", [])

    if card_id is None:
        cur.execute("SELECT id FROM cards WHERE source_id = ? ORDER BY id DESC LIMIT 1", (source_id,))
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


def save_field_version(card_id: int, field_name: str, old_value: str | None, new_value: str | None) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO field_versions (card_id, field_name, old_value, new_value) VALUES (?, ?, ?, ?)",
        (card_id, field_name, old_value, new_value),
    )
    conn.commit()
    conn.close()


def delete_card(card_id: int) -> None:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM field_versions WHERE card_id = ?", (card_id,))
    cur.execute("DELETE FROM cards WHERE id = ?", (card_id,))
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
