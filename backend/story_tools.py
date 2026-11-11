"""
story_tools.py — TEXT studio helpers that need no new tables (kept out of text_module.py)
=========================================================================================

GET  /api/text/entity/<eid>/chapters        what each chapter said about an entity (progressions), with the
                                            starting point marked
GET  /api/text/entity/<eid>/mentions        every line of the text that names the entity, by chapter (no model)
POST /api/text/project/<pid>/prose-scan     clichés, overused words, filler, adverbs, dialogue tags (no model)
POST /api/prose/scan                        the same for any text {"text"}, or a card {"card"} (field by field)
PUT  /api/text/entity/<eid>/secrets         {secrets: [{text, known_by: [names]}]}: facts only some characters
                                            know (each becomes a LORE entry filtered to those characters)
GET  /api/text/project/<pid>/relations      who is linked to whom, for the relationship map (as of the starting
                                            point when "only facts up to the starting point" is on)
"""

import json
import re

from flask import Blueprint, jsonify, request

import prose_scan
import text_module as T

bp = Blueprint("story_tools", __name__)

MAX_MENTIONS = 80
PER_CHUNK = 4


def _entity(eid):
    conn = T._conn()
    row = conn.execute("SELECT * FROM text_entities WHERE id=?", (eid,)).fetchone()
    conn.close()
    return T._row_entity(row) if row else None


def _chunks(pid):
    r = T._project_row(pid)
    return json.loads(r["chunks_json"] or "[]") if r else []


@bp.get("/api/text/entity/<int:eid>/chapters")
def api_entity_chapters(eid):
    e = _entity(eid)
    if e is None:
        return jsonify({"error": "Not found"}), 404
    pid = e["project_id"]
    _, _, upto = T._project_recap(pid)
    labels = [c["label"] for c in _chunks(pid)]
    sl = T.entity_slices(e, T.chunk_results(pid))
    rows = [{**x, "label": labels[x["chunk"]] if 0 <= x["chunk"] < len(labels) else f"Part {x['chunk'] + 1}",
             "after_start": upto >= 0 and x["chunk"] > upto} for x in sl]
    later = sum(1 for x in rows if x["after_start"])
    return jsonify({"name": e["name"], "upto": upto, "start_label": labels[upto] if 0 <= upto < len(labels) else "",
                    "cutoff": T.lore_cutoff(T._project_row(pid)), "chapters": rows, "later": later,
                    "edited": bool(e.get("edited"))})


def mention_patterns(e):
    """Whole-word patterns for the name and aliases. One-word names are matched with their capital letter so
    'Will' or 'Rose' don't match ordinary words; longer names ignore case."""
    out = []
    for n in sorted({x.strip() for x in [e["name"]] + list(e.get("aliases") or []) if x and x.strip()}, key=len,
                    reverse=True):
        esc = re.escape(n)
        flags = re.I if " " in n or not n[:1].isupper() else 0
        out.append(re.compile(rf"(?<![\w]){esc}(?:['’]s)?(?![\w])", flags))
    return out


def find_mentions(e, chunks, case_sensitive=None):
    pats = mention_patterns(e)
    if case_sensitive is False:
        pats = [re.compile(p.pattern, re.I) for p in pats]
    res, total = [], 0
    for c in chunks:
        sents = re.split(r"(?<=[.!?…])[\"'”’)]*\s+|\n\s*\n", c["text"])
        hits = []
        for s in sents:
            if any(p.search(s) for p in pats):
                hits.append(re.sub(r"\s+", " ", s).strip()[:300])
        if hits:
            total += len(hits)
            res.append({"chunk": c["idx"], "label": c["label"], "count": len(hits), "lines": hits[:PER_CHUNK]})
    shown = 0
    for r in res:                                 # cap the lines returned, keep every chapter's count
        room = max(0, MAX_MENTIONS - shown)
        r["lines"] = r["lines"][:room]
        shown += len(r["lines"])
    return {"total": total, "chapters": res}


@bp.get("/api/text/entity/<int:eid>/mentions")
def api_entity_mentions(eid):
    e = _entity(eid)
    if e is None:
        return jsonify({"error": "Not found"}), 404
    cs = request.args.get("any_case") not in ("1", "true")
    out = find_mentions(e, _chunks(e["project_id"]), None if cs else False)
    return jsonify({"name": e["name"], "names": [e["name"]] + list(e.get("aliases") or []), **out})


@bp.post("/api/text/project/<int:pid>/prose-scan")
def api_project_prose_scan(pid):
    chunks = _chunks(pid)
    if not chunks:
        return jsonify({"error": "Nothing to scan: load a text first."}), 400
    want = (request.get_json(silent=True) or {}).get("chunks") or []
    if want:
        want = {int(x) for x in want}
        chunks = [c for c in chunks if c["idx"] in want]
    return jsonify(prose_scan.scan_chunks(chunks))


@bp.post("/api/prose/scan")
def api_prose_scan():
    d = request.get_json(force=True) or {}
    if isinstance(d.get("card"), dict):
        return jsonify({"warnings": prose_scan.card_text_warnings(d["card"], limit=20)})
    text = str(d.get("text") or "")
    if not text.strip():
        return jsonify({"error": "No text"}), 400
    return jsonify(prose_scan.scan(text[:400000], d.get("label") or ""))


@bp.put("/api/text/entity/<int:eid>/secrets")
def api_entity_secrets(eid):
    secrets = T.norm_secrets((request.get_json(silent=True) or {}).get("secrets"))
    conn = T._conn()
    cur = conn.execute("UPDATE text_entities SET secrets_json=? WHERE id=?", (json.dumps(secrets, ensure_ascii=False), eid))
    conn.commit()
    conn.close()
    if not cur.rowcount:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"secrets": secrets})


MAP_TYPES = ("character", "faction")


def relation_graph(pid):
    r = T._project_row(pid)
    if not r:
        return None
    _, _, upto = T._project_recap(pid)
    ents = [e for e in T._entities(pid) if e["keep"] and e["entity_type"] in MAP_TYPES]
    if T.lore_cutoff(r):
        ents = T.entities_as_of(pid, ents, upto)
    by_name = {}
    for e in ents:
        for n in [e["name"]] + list(e.get("aliases") or []):
            if n and n.strip():
                by_name.setdefault(n.strip().lower(), e["id"])
    edges = {}
    for e in ents:
        for rel in e.get("relations") or []:
            other = by_name.get(str(rel.get("with") or "").strip().lower())
            label = str(rel.get("relation") or "").strip()
            if not other or other == e["id"]:
                continue
            a, b = sorted((e["id"], other))
            ed = edges.setdefault((a, b), {"a": a, "b": b, "a_to_b": "", "b_to_a": ""})
            key = "a_to_b" if e["id"] == a else "b_to_a"
            if label and label.lower() not in ed[key].lower():
                ed[key] = f"{ed[key]}; {label}" if ed[key] else label
    deg = {}
    for (a, b) in edges:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    nodes = [{"id": e["id"], "name": e["name"], "type": e["entity_type"], "tier": e.get("tier") or "",
              "image": e.get("image") or "", "degree": deg.get(e["id"], 0)} for e in ents]
    return {"nodes": nodes, "edges": list(edges.values()), "upto": upto, "cutoff": T.lore_cutoff(r)}


@bp.get("/api/text/project/<int:pid>/relations")
def api_relations(pid):
    g = relation_graph(pid)
    if g is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(g)


def register_story_tools(app):
    app.register_blueprint(bp)
