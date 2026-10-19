"""
bundle_routes.py — move projects between installs (or keep them safe) as one .zip
=================================================================================

GET  /api/bundle/contents      what can go in a bundle: TEXT projects, LORE projects, cards
POST /api/bundle/export        {"text_ids": [], "lore_ids": [], "card_ids": [], "include_linked": true} -> .zip
                               include_linked adds a TEXT project's LORE project and the cards made from it
POST /api/bundle/import        multipart "file": a bundle .zip. Everything is added as NEW rows (nothing is
                               overwritten); links between them (TEXT -> LORE, card -> source) are kept.
                               A backup of the database is made first.

The zip holds data.json (the rows, for importing) plus ready-to-use copies: lorebooks/*.json (SillyTavern World Info)
and cards/*.json (Character Card V2), so a bundle is useful even without this app.
"""

import io
import json
import re
import zipfile
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file

import database

bp = Blueprint("bundle", __name__)

BUNDLE_VERSION = 1
TABLES = ("sources", "lore_crawls", "lore_entries", "text_projects", "text_entities", "text_chunk_results",
          "text_critiques", "cards")
MAX_BUNDLE_BYTES = 200 * 1024 * 1024


def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _cols(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def _in(ids):
    return ",".join("?" * len(ids))


def _safe(name):
    return re.sub(r"[^\w\- ]+", "", str(name or "")).strip()[:60] or "untitled"


def collect(text_ids, lore_ids, card_ids, include_linked=True):
    conn = database._conn()
    try:
        text_ids, lore_ids, card_ids = {int(x) for x in text_ids}, {int(x) for x in lore_ids}, {int(x) for x in card_ids}
        tables = {t: [] for t in TABLES}
        if text_ids:
            tables["text_projects"] = _rows(conn, f"SELECT * FROM text_projects WHERE id IN ({_in(text_ids)})", tuple(text_ids))
            ids = tuple(p["id"] for p in tables["text_projects"])
            if ids:
                for t in ("text_entities", "text_chunk_results", "text_critiques"):
                    tables[t] = _rows(conn, f"SELECT * FROM {t} WHERE project_id IN ({_in(ids)})", ids)
                if include_linked:
                    lore_ids |= {p["lore_project_id"] for p in tables["text_projects"] if p.get("lore_project_id")}
                    for pid in ids:
                        card_ids |= {r["id"] for r in _rows(
                            conn, "SELECT c.id FROM cards c JOIN sources s ON s.id = c.source_id WHERE s.url LIKE ?",
                            (f"text://project/{pid}/%",))}
        if lore_ids:
            tables["lore_crawls"] = _rows(conn, f"SELECT * FROM lore_crawls WHERE id IN ({_in(lore_ids)})", tuple(lore_ids))
            tables["lore_entries"] = _rows(conn, f"SELECT * FROM lore_entries WHERE crawl_id IN ({_in(lore_ids)}) "
                                                 "AND COALESCE(deleted, 0) = 0", tuple(lore_ids))
        if card_ids:
            tables["cards"] = _rows(conn, f"SELECT * FROM cards WHERE id IN ({_in(card_ids)})", tuple(card_ids))
        src_ids = {c["source_id"] for c in tables["cards"] if c.get("source_id")} | \
                  {e["source_id"] for e in tables["lore_entries"] if e.get("source_id")}
        if src_ids:
            tables["sources"] = _rows(conn, f"SELECT * FROM sources WHERE id IN ({_in(src_ids)})", tuple(src_ids))
        return tables
    finally:
        conn.close()


def build_zip(tables):
    from lore_tools import lorebook_entries
    from preview import build_export_card_json, world_info_book
    buf = io.BytesIO()
    counts = {t: len(v) for t, v in tables.items()}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps({"app": "Character Card Studio", "bundle_version": BUNDLE_VERSION,
                                                "created": datetime.now().isoformat(timespec="seconds"),
                                                "counts": counts}, indent=2))
        z.writestr("data.json", json.dumps({"bundle_version": BUNDLE_VERSION, "tables": tables}, ensure_ascii=False))
        for lc in tables["lore_crawls"]:
            name, items = lorebook_entries(lc["id"])
            z.writestr(f"lorebooks/{_safe(name)}-{lc['id']}.json", json.dumps(world_info_book(name, items), ensure_ascii=False, indent=2))
        for c in tables["cards"]:
            try:
                card = database.get_card(c["id"])
                z.writestr(f"cards/{_safe(card.get('name'))}-{c['id']}.json",
                           json.dumps(build_export_card_json(card), ensure_ascii=False, indent=2))
            except Exception:
                pass
    buf.seek(0)
    return buf, counts


def import_tables(tables):
    """Insert the bundle's rows as new rows, remapping ids. Returns counts per table and the new ids."""
    conn = database._conn()
    maps = {t: {} for t in TABLES}
    added = {t: 0 for t in TABLES}
    try:
        cols = {t: set(_cols(conn, t)) for t in TABLES}

        def insert(table, row, overrides):
            data = {k: v for k, v in {**row, **overrides}.items() if k in cols[table] and k != "id"}
            if not data:
                return None
            keys = list(data)
            cur = conn.execute(f"INSERT INTO {table} ({','.join(keys)}) VALUES ({_in(keys)})", [data[k] for k in keys])
            added[table] += 1
            return cur.lastrowid

        for s in tables.get("sources") or []:          # same URL already here: reuse it, never overwrite it
            got = conn.execute("SELECT id FROM sources WHERE url = ?", (s.get("url"),)).fetchone()
            maps["sources"][s["id"]] = got[0] if got else insert("sources", s, {})
        taken = {r[0] for r in conn.execute("SELECT project_name FROM lore_crawls")}
        for lc in tables.get("lore_crawls") or []:
            name = lc.get("project_name") or "Imported lore"
            if name in taken:
                name = f"{name} (imported)"
            taken.add(name)
            maps["lore_crawls"][lc["id"]] = insert("lore_crawls", lc, {"project_name": name})
        for e in tables.get("lore_entries") or []:
            insert("lore_entries", e, {"crawl_id": maps["lore_crawls"].get(e.get("crawl_id")),
                                       "source_id": maps["sources"].get(e.get("source_id"))})
        tnames = {r[0] for r in conn.execute("SELECT name FROM text_projects")}
        for p in tables.get("text_projects") or []:
            name = p.get("name") or "Imported text"
            if name in tnames:
                name = f"{name} (imported)"
            tnames.add(name)
            maps["text_projects"][p["id"]] = insert("text_projects", p, {
                "name": name, "lore_project_id": maps["lore_crawls"].get(p.get("lore_project_id"))})
        for t in ("text_entities", "text_chunk_results", "text_critiques"):
            for row in tables.get(t) or []:
                new_pid = maps["text_projects"].get(row.get("project_id"))
                if new_pid:
                    insert(t, row, {"project_id": new_pid})
        for c in tables.get("cards") or []:
            sid = maps["sources"].get(c.get("source_id"))
            if sid:
                maps["cards"][c["id"]] = insert("cards", c, {"source_id": sid})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return added, {t: list(m.values()) for t, m in maps.items() if m}


@bp.get("/api/bundle/contents")
def api_contents():
    conn = database._conn()
    try:
        texts = _rows(conn, "SELECT id, name, lore_project_id, created_at FROM text_projects ORDER BY id DESC")
        cards = _rows(conn, "SELECT c.id, c.name, s.url FROM cards c LEFT JOIN sources s ON s.id = c.source_id ORDER BY c.id DESC")
    finally:
        conn.close()
    lores = database.list_lore_projects()
    return jsonify({"text_projects": texts, "lore_projects": [{"id": p["id"], "name": p["project_name"],
                                                               "entries": p["entry_count"]} for p in lores],
                    "cards": [{"id": c["id"], "name": c["name"],
                               "from_text": (c.get("url") or "").startswith("text://")} for c in cards]})


@bp.post("/api/bundle/export")
def api_export():
    d = request.get_json(force=True) or {}
    tables = collect(d.get("text_ids") or [], d.get("lore_ids") or [], d.get("card_ids") or [],
                     d.get("include_linked", True) is not False)
    if not any(tables.values()):
        return jsonify({"error": "Pick at least one project or card"}), 400
    buf, counts = build_zip(tables)
    name = f"card-studio-bundle-{datetime.now().strftime('%Y%m%d-%H%M')}.zip"
    resp = send_file(buf, mimetype="application/zip", as_attachment=True, download_name=name)
    resp.headers["X-Bundle-Counts"] = json.dumps(counts)
    return resp


@bp.post("/api/bundle/import")
def api_import():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file"}), 400
    data = f.read(MAX_BUNDLE_BYTES + 1)
    if len(data) > MAX_BUNDLE_BYTES:
        return jsonify({"error": "Bundle too large"}), 400
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        payload = json.loads(z.read("data.json").decode("utf-8"))
    except Exception:
        return jsonify({"error": "Not a Card Studio bundle (.zip with data.json)"}), 400
    if int(payload.get("bundle_version") or 0) > BUNDLE_VERSION:
        return jsonify({"error": "This bundle was made by a newer version of the app"}), 400
    tables = payload.get("tables") or {}
    if not isinstance(tables, dict) or not any(isinstance(v, list) and v for v in tables.values()):
        return jsonify({"error": "The bundle is empty"}), 400
    try:
        from admin_routes import make_backup
        backup = make_backup("before-import")
    except Exception:
        backup = None
    try:
        added, ids = import_tables({t: v for t, v in tables.items() if t in TABLES and isinstance(v, list)})
    except Exception as e:
        return jsonify({"error": f"Import failed, nothing was changed: {e}"}), 500
    return jsonify({"added": added, "ids": ids, "backup": backup})


def register_bundle_routes(app):
    app.register_blueprint(bp)
