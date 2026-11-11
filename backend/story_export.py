"""
story_export.py — a story bible to read or print, and a Data Bank pack for SillyTavern
=====================================================================================

Both are built from the same entries that go to LORE (so they follow the starting point, hand edits and the
"Often here" setting), grouped and ordered for reading: Story So Far, Timeline, characters (main first), factions,
places, items, then everything else.

GET /api/text/project/<pid>/bible?format=md|html     Markdown, or a printable HTML page (portraits embedded)
GET /api/text/project/<pid>/databank                  .zip of one Markdown file per entry, for SillyTavern's Data Bank
GET /api/lore/project/<pid>/bible?format=md|html      the same for a LORE project
GET /api/lore/project/<pid>/databank
"""

import base64
import html
import io
import re
import zipfile
from datetime import date

from flask import Blueprint, Response, jsonify, request, send_file

import images
import text_module as T
from lore_tools import lorebook_entries

bp = Blueprint("story_export", __name__)

GROUPS = [("character", "Characters"), ("faction", "Factions"), ("place", "Places"), ("item", "Items"),
          ("ability", "Abilities"), ("concept", "Concepts"), ("event", "Events")]
SPECIAL = ("Story So Far", "Story Timeline", "Relationships")
SKIP = ("Cast Roster",)                       # the Characters section already lists everyone
TIER_RANK = {"main": 0, "supporting": 1, "minor": 2, "one-off": 3}
MAX_EMBED = 12 * 1024 * 1024                  # portraits embedded in the HTML bible, in total


def _slug(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\- ]+", "", s or "")).strip()[:80] or "entry"


def text_bible(pid):
    r = T._project_row(pid)
    if not r:
        return None
    items, upto = T._lore_items(pid)
    ents = {e["name"]: e for e in T._entities(pid)}
    labels = [c["label"] for c in T.json.loads(r["chunks_json"] or "[]")] if "chunks_json" in r.keys() else []
    note = ""
    if upto is not None and upto >= 0 and T.lore_cutoff(r):
        where = labels[upto] if 0 <= upto < len(labels) else f"part {upto + 1}"
        note = f"As of the roleplay starting point: after {where}."
    for it in items:
        e = ents.get(it["title"]) or {}
        it["tier"] = e.get("tier") or ""
        it["image"] = e.get("image") or ""
        it["aliases"] = e.get("aliases") or []
    return r["name"], note, items


def lore_bible(pid):
    name, items = lorebook_entries(pid)
    if not items:
        return None
    return name, "", [{**it, "tier": "", "image": "", "aliases": []} for it in items]


def sections(items):
    special = [it for t in SPECIAL for it in items if it["title"] == t]
    secrets = [it for it in items if it.get("secret")]
    rest = [it for it in items if it["title"] not in SPECIAL + SKIP and not it.get("secret")]
    out = [{"heading": it["title"], "entries": [it], "special": True} for it in special]
    known = {k for k, _ in GROUPS}
    for key, heading in GROUPS:
        group = [it for it in rest if (it.get("entry_type") or "concept") == key]
        if key == "concept":
            group += [it for it in rest if (it.get("entry_type") or "concept") not in known]
        group.sort(key=lambda it: (TIER_RANK.get(it.get("tier"), 2), it["title"].lower()))
        if group:
            out.append({"heading": heading, "entries": group, "special": False})
    if secrets:
        out.append({"heading": "Secrets", "entries": [{**it, "tier": "", "aliases": [], "image": "",
                                                        "meta": "known only to " + ", ".join(it["char_filter"])}
                                                       for it in secrets], "special": False, "secret": True})
    return out


def _meta(it):
    if it.get("meta"):
        return it["meta"]
    bits = []
    if it.get("tier"):
        bits.append(it["tier"])
    if it.get("aliases"):
        bits.append("also " + ", ".join(it["aliases"]))
    return " · ".join(bits)


def to_markdown(title, note, secs):
    out = [f"# {title}", "", f"*Story bible, {date.today().isoformat()}.{(' ' + note) if note else ''}*", ""]
    toc = [f"- [{s['heading']}](#{_slug(s['heading']).lower().replace(' ', '-')})" for s in secs]
    out += ["## Contents", "", *toc, ""]
    for s in secs:
        out += [f"## {s['heading']}", ""]
        if s["special"]:
            out += [s["entries"][0]["content"].strip(), ""]
            continue
        for it in s["entries"]:
            out += [f"### {it['title']}", ""]
            if _meta(it):
                out += [f"*{_meta(it)}*", ""]
            out += [it["content"].strip(), ""]
    return "\n".join(out).rstrip() + "\n"


CSS = """
:root { --ink: #2b2a26; --dim: #6d6a60; --line: #b9b39f; --paper: #f4f0e4; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.6 Georgia, "Times New Roman", serif; }
main { max-width: 780px; margin: 0 auto; padding: 48px 28px 80px; }
h1 { font: 700 30px/1.2 "Helvetica Neue", Arial, sans-serif; letter-spacing: .12em; text-transform: uppercase; margin: 0 0 6px; }
.sub { color: var(--dim); font-style: italic; margin-bottom: 28px; }
h2 { font: 700 13px/1 "Helvetica Neue", Arial, sans-serif; letter-spacing: .22em; text-transform: uppercase;
     border-top: 2px solid var(--ink); padding-top: 12px; margin: 40px 0 16px; }
h3 { font: 700 17px/1.3 "Helvetica Neue", Arial, sans-serif; letter-spacing: .04em; margin: 0 0 2px; }
nav ol { columns: 2; padding-left: 18px; font-family: "Helvetica Neue", Arial, sans-serif; font-size: 13px; }
nav a { color: var(--ink); }
.entry { display: flex; gap: 16px; padding: 14px 0; border-bottom: 1px solid var(--line); break-inside: avoid; }
.entry img { width: 92px; height: 120px; object-fit: cover; border: 1px solid var(--line); flex: 0 0 auto; }
.meta { color: var(--dim); font-size: 13px; font-style: italic; margin-bottom: 4px; }
.body { white-space: pre-wrap; }
.special .body { border-left: 3px solid var(--line); padding-left: 14px; }
.print { position: fixed; top: 14px; right: 14px; font: 700 12px Arial, sans-serif; letter-spacing: .1em; padding: 8px 12px;
         border: 1px solid var(--ink); background: var(--paper); color: var(--ink); cursor: pointer; }
@media print {
  body { background: #fff; font-size: 11pt; } main { max-width: none; padding: 0; } .print { display: none; }
  h2, h3 { break-after: avoid; } .entry { break-inside: avoid; }
  a { color: inherit; text-decoration: none; }
}
"""


def to_html(title, note, secs):
    e = html.escape
    budget = [MAX_EMBED]

    def portrait(name):
        raw, ext = images.load(name)
        if not raw or len(raw) > budget[0]:
            return ""
        budget[0] -= len(raw)
        mime = images.MIME[ext]
        return f'<img src="data:{mime};base64,{base64.b64encode(raw).decode()}" alt="">'

    parts = [f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
             f"content=\"width=device-width, initial-scale=1\"><title>{e(title)} · Story bible</title><style>{CSS}</style>"
             f"</head><body><button class=\"print\" onclick=\"window.print()\">PRINT / SAVE AS PDF</button><main>",
             f"<h1>{e(title)}</h1><div class=\"sub\">Story bible, {date.today().isoformat()}.{(' ' + e(note)) if note else ''}</div>",
             "<nav><ol>" + "".join(f"<li><a href=\"#s{i}\">{e(s['heading'])}</a></li>" for i, s in enumerate(secs)) + "</ol></nav>"]
    for i, s in enumerate(secs):
        parts.append(f"<section id=\"s{i}\" class=\"{'special' if s['special'] else ''}\"><h2>{e(s['heading'])}</h2>")
        for it in s["entries"]:
            img = portrait(it.get("image")) if it.get("image") else ""
            head = "" if s["special"] else f"<h3>{e(it['title'])}</h3>" + (f"<div class=\"meta\">{e(_meta(it))}</div>" if _meta(it) else "")
            parts.append(f"<div class=\"entry\">{img}<div>{head}<div class=\"body\">{e(it['content'].strip())}</div></div></div>")
        parts.append("</section>")
    parts.append("</main></body></html>")
    return "".join(parts)


DATABANK_README = """{title} — Data Bank pack
================================

One Markdown file per entry, made by Character Card Studio ({today}).

How to use it in SillyTavern:
1. Open the magic wand menu next to the chat box and choose "Data Bank" (Open Data Bank).
2. Under Character Attachments (or Chat / Global), use "Add" and pick the .md files from this folder.
3. Turn on Vector Storage (Extensions) and enable it for files, so the right notes are found and inserted when they
   are relevant.

Unlike a lorebook, this does not need keywords: SillyTavern looks up whichever notes are closest in meaning to the
chat. It works well for long background notes; use the lorebook for things that must always fire on a name.
"""


def databank_zip(title, note, secs):
    buf = io.BytesIO()
    used = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", DATABANK_README.format(title=title, today=date.today().isoformat()))
        n = 0
        for s in secs:
            if s.get("secret"):        # the Data Bank has no character filter: a secret there would reach everyone
                continue
            folder = "" if s["special"] else _slug(s["heading"]).lower() + "/"
            for it in s["entries"]:
                n += 1
                base = f"{n:02d} {_slug(it['title'])}" if s["special"] else _slug(it["title"])
                path = f"{folder}{base}.md"
                while path in used:
                    base += "_"
                    path = f"{folder}{base}.md"
                used.add(path)
                head = [f"# {it['title']}", "", f"Story: {title}." + (f" {note}" if note else "")]
                if _meta(it):
                    head.append(_meta(it).capitalize() + ".")
                z.writestr(path, "\n".join(head) + "\n\n" + it["content"].strip() + "\n")
    return buf.getvalue()


def _respond(found, kind):
    if found is None:
        return jsonify({"error": "Nothing to export" if kind == "lore" else "Not found"}), 404
    title, note, items = found
    secs = sections(items)
    if not secs:
        return jsonify({"error": "Nothing to export yet: keep some entries first"}), 400
    slug = _slug(title).replace(" ", "-")
    if request.endpoint.endswith("databank"):
        return send_file(io.BytesIO(databank_zip(title, note, secs)), mimetype="application/zip", as_attachment=True,
                         download_name=f"{slug}-databank.zip")
    if (request.args.get("format") or "md") == "html":
        resp = Response(to_html(title, note, secs), mimetype="text/html")
        if request.args.get("download"):
            resp.headers["Content-Disposition"] = f'attachment; filename="{slug}-bible.html"'
        return resp
    resp = Response(to_markdown(title, note, secs), mimetype="text/markdown")
    resp.headers["Content-Disposition"] = f'attachment; filename="{slug}-bible.md"'
    return resp


@bp.get("/api/text/project/<int:pid>/bible")
def api_text_bible(pid):
    return _respond(text_bible(pid), "text")


@bp.get("/api/text/project/<int:pid>/databank")
def api_text_databank(pid):
    return _respond(text_bible(pid), "text")


@bp.get("/api/lore/project/<int:pid>/bible")
def api_lore_bible(pid):
    return _respond(lore_bible(pid), "lore")


@bp.get("/api/lore/project/<int:pid>/databank")
def api_lore_databank(pid):
    return _respond(lore_bible(pid), "lore")


def register_story_export(app):
    app.register_blueprint(bp)
