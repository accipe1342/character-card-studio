"""
search_routes.py — one search box across the whole app
======================================================

GET /api/search?q=text[&limit=8]
    -> {"cards": [...], "lore": [...], "texts": [...], "entities": [...]}
Cards match on name/description, lore entries on title/keywords/content, TEXT projects on name, reviewed TEXT
entities on name/aliases/content. Case-insensitive; trashed rows are left out. Each hit has a short snippet.
"""

import re

from flask import Blueprint, jsonify, request

import database

bp = Blueprint("search", __name__)


def _snippet(text, q, width=90):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    i = text.lower().find(q.lower())
    if i < 0:
        return text[:width] + ("…" if len(text) > width else "")
    start = max(0, i - width // 3)
    out = text[start:start + width]
    return ("…" if start else "") + out + ("…" if start + width < len(text) else "")


def _has_table(conn, name):
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


@bp.get("/api/search")
def api_search():
    q = (request.args.get("q") or "").strip()
    limit = max(1, min(request.args.get("limit", default=8, type=int), 50))
    empty = {"cards": [], "lore": [], "texts": [], "entities": []}
    if len(q) < 2:
        return jsonify({**empty, "q": q})
    like = f"%{q.replace('%', '').replace('_', '')}%"
    conn = database._conn()
    out = dict(empty)
    try:
        rows = conn.execute("SELECT id, name, description FROM cards WHERE name LIKE ? OR description LIKE ? "
                            "ORDER BY (name LIKE ?) DESC, id DESC LIMIT ?", (like, like, like, limit)).fetchall()
        out["cards"] = [{"id": r["id"], "name": r["name"] or "Unnamed",
                         "snippet": _snippet(r["description"], q)} for r in rows]
        rows = conn.execute(
            "SELECT le.id, le.crawl_id, le.title, le.entry_type, le.content, lc.project_name FROM lore_entries le "
            "LEFT JOIN lore_crawls lc ON lc.id = le.crawl_id WHERE COALESCE(le.deleted, 0) = 0 AND "
            "(le.title LIKE ? OR le.keywords_json LIKE ? OR le.content LIKE ?) "
            "ORDER BY (le.title LIKE ?) DESC, le.id DESC LIMIT ?", (like, like, like, like, limit)).fetchall()
        out["lore"] = [{"id": r["id"], "project_id": r["crawl_id"], "project": r["project_name"] or "",
                        "title": r["title"], "entry_type": r["entry_type"], "snippet": _snippet(r["content"], q)} for r in rows]
        if _has_table(conn, "text_projects"):
            rows = conn.execute("SELECT id, name FROM text_projects WHERE name LIKE ? ORDER BY id DESC LIMIT ?",
                                (like, limit)).fetchall()
            out["texts"] = [{"id": r["id"], "name": r["name"]} for r in rows]
        if _has_table(conn, "text_entities"):
            rows = conn.execute(
                "SELECT e.id, e.project_id, e.name, e.entity_type, e.content, p.name AS project FROM text_entities e "
                "JOIN text_projects p ON p.id = e.project_id WHERE COALESCE(e.deleted, 0) = 0 AND "
                "(e.name LIKE ? OR e.aliases_json LIKE ? OR e.content LIKE ?) "
                "ORDER BY (e.name LIKE ?) DESC, e.id DESC LIMIT ?", (like, like, like, like, limit)).fetchall()
            out["entities"] = [{"id": r["id"], "project_id": r["project_id"], "project": r["project"],
                                "name": r["name"], "entity_type": r["entity_type"],
                                "snippet": _snippet(r["content"], q)} for r in rows]
    finally:
        conn.close()
    return jsonify({**out, "q": q})


def register_search_routes(app):
    app.register_blueprint(bp)
