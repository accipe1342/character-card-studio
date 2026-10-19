"""
lore_tools.py — lorebook helpers for the LORE studio
====================================================

POST   /api/lore/simulate                       {"project_id", "text", "budget"?, "whole_words"?}
                                                 which entries SillyTavern would activate for this chat text
GET    /api/lore/project/<id>/graph              which entries mention which (recursion links), orphans, loops
GET    /api/lore/trash[?project_id=N]            deleted entries
POST   /api/lore/entry/<id>/restore              take an entry out of the trash
DELETE /api/lore/entry/<id>[?purge=1]            move to the trash (purge=1: delete for good)
DELETE /api/lore/trash[?project_id=N]            empty the trash

The simulator follows SillyTavern's World Info rules as documented: constant entries always fire; otherwise a primary
key must appear in the scanned text, then the secondary-key logic is applied; activated entries' content is scanned
again for other entries' keys (recursion) unless they prevent it; one entry per inclusion group; then entries are kept
in budget order: constants first, then higher Order first. Token counts are estimates (about 4 characters per token).
Probability, delay, cooldown, sticky and character filters depend on the live chat, so they are reported as notes.
"""

import json
import math
import re

from flask import Blueprint, jsonify, request

import database
from preview import normalise_lore_items

bp = Blueprint("lore_tools", __name__)

LORE_WI_EXPORT = ("constant", "position", "role", "probability", "sticky", "cooldown", "delay", "secondary_keys",
                  "selective_logic", "group_name", "group_weight", "group_prioritize", "vectorized", "char_filter")
LOGIC_NAMES = {0: "AND ANY", 1: "NOT ALL", 2: "NOT ANY", 3: "AND ALL"}


def est_tokens(text: str) -> int:
    return math.ceil(len(text or "") / 4)


def lorebook_entries(project_id=None):
    """(lorebook name, [normalised entries]) for one LORE project (None = every entry), oldest first so edits don't
    reshuffle the order numbers on every export. Shared by the World Info export, the character_book embedded in
    cards, the DeepLore export and the simulator. Each item also carries its lore_id."""
    entries = sorted(database.list_lore_entries(crawl_id=project_id), key=lambda e: e["id"])
    project_name = "Character Card Studio Lorebook"
    if project_id is not None:
        conn = database._conn()
        row = conn.execute("SELECT project_name FROM lore_crawls WHERE id = ?", (project_id,)).fetchone()
        conn.close()
        if row and row[0]:
            project_name = row[0]
    raw = []
    for e in entries:
        full = database.get_lore_entry(e["id"])
        keywords = full.get("keywords", [])
        if isinstance(keywords, str):
            try:
                keywords = json.loads(keywords)
            except Exception:
                keywords = [keywords]
        raw.append({"title": full.get("title", ""), "entry_type": full.get("entry_type", "character"),
                    "keys": keywords, "content": full.get("content", ""), "summary": full.get("summary", ""),
                    "order": full.get("insertion_order") if full.get("order_manual") else None,
                    "depth": full.get("entry_depth", 4), "scan_depth": full.get("scan_depth", 4),
                    **{k: full.get(k) for k in LORE_WI_EXPORT}, "lore_id": full["id"]})
    out = normalise_lore_items(raw)
    for it, r in zip(out, raw):
        it["lore_id"] = r["lore_id"]
    return project_name, out


# ── key matching ─────────────────────────────────────────────────────────────
_REGEX_KEY = re.compile(r"^/(.+)/([a-z]*)$", re.S)


def key_pattern(key: str, whole_words: bool):
    """A compiled pattern for one key, or None. Keys written as /regex/flags are regexes, as in SillyTavern."""
    key = (key or "").strip()
    if not key:
        return None
    m = _REGEX_KEY.match(key)
    if m:
        flags = re.I if "i" in m.group(2) else 0
        try:
            return re.compile(m.group(1), flags)
        except re.error:
            return None
    esc = re.escape(key)
    if whole_words and re.match(r"^\w.*\w$|^\w$", key):
        esc = rf"(?<!\w){esc}(?!\w)"
    return re.compile(esc, re.I)


def first_match(keys, text, whole_words):
    for k in keys:
        p = key_pattern(k, whole_words)
        if p and p.search(text):
            return k
    return None


def secondary_ok(it, text, whole_words):
    sec = it.get("secondaryKeys") or []
    if not sec:
        return True, ""
    hits = [k for k in sec if (p := key_pattern(k, whole_words)) and p.search(text)]
    logic = it.get("selectiveLogic") or 0
    ok = {0: bool(hits), 1: len(hits) < len(sec), 2: not hits, 3: len(hits) == len(sec)}.get(logic, True)
    return ok, f"{LOGIC_NAMES.get(logic, 'AND ANY')} {', '.join(sec)}" + (f" (found: {', '.join(hits)})" if hits else "")


def simulate(items, text, budget=2048, whole_words=False, recursion=True):
    active, reasons = {}, {}
    for it in items:
        if it["constant"]:
            active[it["uid"]] = it
            reasons[it["uid"]] = {"why": "constant (always on)", "matched": ""}
    # pass 0 scans the chat; later passes scan the content of what was activated in the previous pass (recursion)
    scan_sources = [("chat", text)]
    for step in range(10):
        new = []
        for it in items:
            if it["uid"] in active or not it["keys"]:
                continue
            if step > 0 and it["excludeRecursion"]:
                continue
            for src_name, src_text in scan_sources:
                k = first_match(it["keys"], src_text, whole_words)
                if not k:
                    continue
                ok, sec_note = secondary_ok(it, src_text, whole_words)
                if not ok:
                    reasons.setdefault(("blocked", it["uid"]), {"why": f"key '{k}' found but secondary keys failed: {sec_note}"})
                    continue
                new.append(it)
                reasons[it["uid"]] = {"why": (f"key '{k}' in the chat" if src_name == "chat"
                                              else f"key '{k}' in the content of '{src_name}' (recursion)"),
                                      "matched": k, "secondary": sec_note}
                break
        for it in new:
            active[it["uid"]] = it
        if not new or not recursion:
            break
        scan_sources = [(it["title"], it["content"]) for it in new if not it["preventRecursion"]]
        if not scan_sources:
            break
    # inclusion groups: only one entry per group goes in
    group_losers = {}
    by_group = {}
    for it in active.values():
        if it["group"]:
            by_group.setdefault(it["group"], []).append(it)
    for g, members in by_group.items():
        if len(members) < 2:
            continue
        prio = [m for m in members if m["groupOverride"]]
        pool = prio or members
        winner = max(pool, key=lambda m: (m["order"], m["groupWeight"]) if prio else (m["groupWeight"], m["order"]))
        for m in members:
            if m is not winner:
                group_losers[m["uid"]] = (f"lost the '{g}' inclusion group to '{winner['title']}'"
                                          + ("" if prio else " (SillyTavern picks by weight at random; the heaviest is shown)"))
    ordered = sorted([it for it in active.values() if it["uid"] not in group_losers],
                     key=lambda it: (0 if it["constant"] else 1, -it["order"]))
    kept, dropped, used = [], [], 0
    for it in ordered:
        tok = est_tokens(it["content"])
        row = _row(it, reasons.get(it["uid"], {}), tok)
        if used + tok > budget:
            row["dropped"] = f"over the {budget}-token budget"
            dropped.append(row)
            continue
        used += tok
        kept.append(row)
    for uid, why in group_losers.items():
        row = _row(active[uid], reasons.get(uid, {}), est_tokens(active[uid]["content"]))
        row["dropped"] = why
        dropped.append(row)
    blocked = [{"title": next(i["title"] for i in items if i["uid"] == k[1]), "why": v["why"]}
               for k, v in reasons.items() if isinstance(k, tuple) and k[1] not in active]
    return {"activated": kept, "dropped": dropped, "blocked": blocked, "tokens": used, "budget": budget,
            "inactive": len(items) - len(active)}


def _row(it, reason, tok):
    notes = []
    if it["probability"] < 100:
        notes.append(f"fires {it['probability']}% of the time")
    if it["delay"]:
        notes.append(f"only after {it['delay']} messages in the chat")
    if it["cooldown"]:
        notes.append(f"cooldown {it['cooldown']} messages after it fires")
    if it["sticky"]:
        notes.append(f"stays {it['sticky']} messages after it fires")
    if it["characterFilter"]:
        notes.append("only for: " + ", ".join(it["characterFilter"]))
    if it["vectorized"]:
        notes.append("vectorized: may also fire by meaning (needs the Vector Storage extension)")
    return {"lore_id": it.get("lore_id"), "title": it["title"], "entry_type": it["entry_type"], "why": reason.get("why", ""),
            "tokens": tok, "order": it["order"], "position": it["position"], "constant": it["constant"], "notes": notes}


# ── graph ────────────────────────────────────────────────────────────────────
def lore_graph(items, whole_words=True):
    """Edges A -> B when A's content contains one of B's keys (B fires by recursion when A is in context)."""
    nodes, edges = [], []
    for a in items:
        nodes.append({"lore_id": a.get("lore_id"), "title": a["title"], "entry_type": a["entry_type"],
                      "constant": a["constant"], "keys": len(a["keys"])})
    for a in items:
        for b in items:
            if a is b or not b["keys"]:
                continue
            k = first_match(b["keys"], a["content"], whole_words)
            if k:
                edges.append({"from": a.get("lore_id"), "to": b.get("lore_id"), "key": k,
                              "live": not a["preventRecursion"] and not b["excludeRecursion"]})
    linked = {e["from"] for e in edges} | {e["to"] for e in edges}
    pairs = {(e["from"], e["to"]) for e in edges}
    mutual = sorted({tuple(sorted((f, t))) for f, t in pairs if (t, f) in pairs})
    title = {it.get("lore_id"): it["title"] for it in items}
    return {
        "nodes": nodes, "edges": edges,
        "orphans": [n["title"] for n in nodes if n["lore_id"] not in linked and not n["constant"]],
        "no_keys": [it["title"] for it in items if not it["keys"] and not it["constant"]],
        "loops": [[title[a], title[b]] for a, b in mutual],
    }


# ── routes ───────────────────────────────────────────────────────────────────
@bp.post("/api/lore/simulate")
def api_simulate():
    d = request.get_json(force=True) or {}
    pid = d.get("project_id")
    text = str(d.get("text") or "")
    if not text.strip():
        return jsonify({"error": "Paste some chat text to test"}), 400
    try:
        budget = max(100, min(int(d.get("budget") or 2048), 200000))
    except (TypeError, ValueError):
        budget = 2048
    _, items = lorebook_entries(int(pid) if pid not in (None, "") else None)
    return jsonify(simulate(items, text, budget, bool(d.get("whole_words")), d.get("recursion", True) is not False))


@bp.get("/api/lore/project/<int:project_id>/graph")
def api_graph(project_id):
    _, items = lorebook_entries(project_id)
    return jsonify(lore_graph(items))


@bp.get("/api/lore/trash")
def api_trash():
    pid = request.args.get("project_id", type=int)
    return jsonify({"entries": database.list_lore_entries(crawl_id=pid, deleted=True)})


@bp.post("/api/lore/entry/<int:lore_id>/restore")
def api_restore(lore_id):
    conn = database._conn()
    n = conn.execute("UPDATE lore_entries SET deleted = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (lore_id,)).rowcount
    conn.commit()
    conn.close()
    return (jsonify({"restored": lore_id}) if n else (jsonify({"error": "Lore entry not found"}), 404))


@bp.delete("/api/lore/entry/<int:lore_id>")
def api_delete(lore_id):
    purge = request.args.get("purge") in ("1", "true")
    conn = database._conn()
    if purge:
        n = conn.execute("DELETE FROM lore_entries WHERE id = ?", (lore_id,)).rowcount
    else:
        n = conn.execute("UPDATE lore_entries SET deleted = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                         (lore_id,)).rowcount
    conn.commit()
    conn.close()
    if not n:
        return jsonify({"error": "Lore entry not found"}), 404
    return jsonify({"deleted": lore_id, "trash": not purge})


@bp.delete("/api/lore/trash")
def api_empty_trash():
    pid = request.args.get("project_id", type=int)
    conn = database._conn()
    if pid is None:
        n = conn.execute("DELETE FROM lore_entries WHERE COALESCE(deleted, 0) = 1").rowcount
    else:
        n = conn.execute("DELETE FROM lore_entries WHERE COALESCE(deleted, 0) = 1 AND crawl_id = ?", (pid,)).rowcount
    conn.commit()
    conn.close()
    return jsonify({"purged": n})


def register_lore_tools(app):
    app.register_blueprint(bp)
