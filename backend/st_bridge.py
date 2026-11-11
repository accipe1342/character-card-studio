"""
st_bridge.py — send cards, lorebooks and Quick Reply sets straight into a running SillyTavern
============================================================================================

SillyTavern has no public API: these are the same calls its own web page makes. Each call first fetches a CSRF token
(GET /csrf-token, tied to a session cookie) and sends it as X-CSRF-Token. Basic auth is used when a user name is set
(SillyTavern's basicAuthMode). Checked against SillyTavern 1.19.

Settings live in .env (Config page): ST_URL (default http://127.0.0.1:8000), ST_USER, ST_PASSWORD.

POST /api/st/test                    {url?, user?, password?}  -> {ok, version} (unsaved values from the form win)
POST /api/st/push/card               {card, mode?, lore_project_id?, image?, file_name?} -> {file_name}
                                     image: a PNG data URL (the portrait). file_name: the name SillyTavern gave last
                                     time, so a re-send replaces that character instead of adding a copy.
POST /api/st/push/lore               {project_id, name?} -> {name}   (World Info; same name = replaced)
POST /api/st/push/quick-replies      {set} -> {name}                  (a Quick Reply set; same name = replaced)
"""

import json
import os

import requests
from flask import Blueprint, jsonify, request

import png_card
from lore_routes import build_character_book
from lore_tools import lorebook_entries
from preview import build_export_card_json, build_export_card_v3, world_info_book

bp = Blueprint("st_bridge", __name__)

MASK = "••••"
TIMEOUT = 20


class STError(Exception):
    pass


def settings(over=None):
    over = over or {}
    url = (over.get("url") or os.getenv("ST_URL") or "http://127.0.0.1:8000").strip().rstrip("/")
    user = over.get("user") if over.get("user") is not None else os.getenv("ST_USER", "")
    pw = over.get("password")
    if pw is None or str(pw).startswith(MASK):
        pw = os.getenv("ST_PASSWORD", "")
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url, (user or "").strip(), pw or ""


class STClient:
    def __init__(self, url, user="", password=""):
        self.url = url
        self.s = requests.Session()
        if user:
            self.s.auth = (user, password)
        self.token = None

    def _check(self, r, what):
        if r.status_code == 401:
            raise STError("SillyTavern asked for a login: check the user name and password (Config → SillyTavern).")
        if r.status_code == 403:
            body = r.text[:300].lower()
            if "whitelist" in body:
                raise STError("SillyTavern refused this computer (its whitelist). Add this machine's IP to the "
                              "whitelist in SillyTavern's config.yaml, or run both on the same computer.")
            raise STError(f"SillyTavern refused the request ({what}): {r.text[:160].strip() or 'forbidden'}")
        if r.status_code >= 400:
            raise STError(f"SillyTavern returned {r.status_code} for {what}: {r.text[:160].strip()}")
        return r

    def _req(self, method, path, what, **kw):
        try:
            r = self.s.request(method, self.url + path, timeout=TIMEOUT, **kw)
        except requests.exceptions.ConnectionError:
            raise STError(f"Can't reach SillyTavern at {self.url}. Is it running, and is the address right?")
        except requests.exceptions.Timeout:
            raise STError(f"SillyTavern at {self.url} did not answer in {TIMEOUT} s.")
        return self._check(r, what)

    def csrf(self):
        if self.token is None:
            r = self._req("GET", "/csrf-token", "the security token")
            try:
                self.token = r.json().get("token") or ""
            except ValueError:
                raise STError(f"{self.url} answered, but it does not look like SillyTavern.")
        return self.token

    def post(self, path, what, **kw):
        headers = {"X-CSRF-Token": self.csrf()}
        return self._req("POST", path, what, headers=headers, **kw)

    def version(self):
        try:
            v = self._req("GET", "/version", "the version").json()
        except ValueError:
            v = {}
        self.post("/api/ping", "a test call")          # proves login + CSRF work, not just that the page is up
        return v.get("pkgVersion") or v.get("agent") or "unknown"


def client(over=None):
    return STClient(*settings(over))


def _err(e):
    return jsonify({"error": str(e)}), 502


@bp.post("/api/st/test")
def api_st_test():
    d = request.get_json(silent=True) or {}
    try:
        c = client(d)
        return jsonify({"ok": True, "version": c.version(), "url": c.url})
    except STError as e:
        return _err(e)


def card_png(card, mode="natural", lore_project_id=None, image=None):
    structured = mode == "structured"
    v2 = build_export_card_json(card, structured=structured)
    v3 = build_export_card_v3(card, structured=structured)
    if lore_project_id not in (None, "", 0, "0"):
        book = build_character_book(int(lore_project_id))
        if book["entries"]:
            v2["data"]["character_book"] = book
            v3["data"]["character_book"] = book
    png = png_card.decode_data_url(image) if image else None
    return png_card.embed(png or png_card.placeholder(card.get("name", "")), v2, v3), png is not None


@bp.post("/api/st/push/card")
def api_st_push_card():
    d = request.get_json(force=True) or {}
    card = d.get("card") or {}
    if not str(card.get("name") or "").strip():
        return jsonify({"error": "The card needs a name first"}), 400
    png, had_image = card_png(card, d.get("mode") or "natural", d.get("lore_project_id"), d.get("image"))
    form = {"file_type": "png"}
    if d.get("file_name"):
        form["preserved_name"] = str(d["file_name"])
    try:
        r = client().post("/api/characters/import", "the character import",
                          files={"avatar": (f"{card['name']}.png", png, "image/png")}, data=form)
        res = r.json()
    except STError as e:
        return _err(e)
    except ValueError:
        return jsonify({"error": "SillyTavern accepted the upload but its answer was unreadable"}), 502
    if res.get("error") or not res.get("file_name"):
        return jsonify({"error": "SillyTavern could not read the card"}), 502
    return jsonify({"file_name": res["file_name"], "image": had_image})


@bp.post("/api/st/push/lore")
def api_st_push_lore():
    d = request.get_json(force=True) or {}
    pid = d.get("project_id")
    if pid in (None, ""):
        return jsonify({"error": "Pick a lore project"}), 400
    project_name, items = lorebook_entries(int(pid))
    if not items:
        return jsonify({"error": "This project has no entries to send"}), 400
    name = str(d.get("name") or project_name or "Lorebook").strip()[:120]
    book = world_info_book(name, items)
    try:
        client().post("/api/worldinfo/edit", "the World Info save", json={"name": name, "data": book})
    except STError as e:
        return _err(e)
    return jsonify({"name": name, "entries": len(book.get("entries", {}))})


@bp.post("/api/st/push/quick-replies")
def api_st_push_qr():
    d = request.get_json(force=True) or {}
    qrs = d.get("set") or {}
    if not qrs.get("name") or not isinstance(qrs.get("qrList"), list):
        return jsonify({"error": "Not a Quick Reply set"}), 400
    try:
        client().post("/api/quick-replies/save", "the Quick Reply save", json=qrs)
    except STError as e:
        return _err(e)
    return jsonify({"name": qrs["name"], "count": len(qrs["qrList"])})


# ── Quick Reply sets ──────────────────────────────────────────────────────────
QR_MAX = 12          # per group: a row of more buttons than this is hard to use


def _qr_text(s):
    return str(s).replace("|", "\\|").replace("{{", "{ {").strip()


def _qr(i, label, message, title=""):
    return {"id": i, "icon": "", "showLabel": False, "label": label[:40], "title": title, "message": message,
            "contextList": [], "preventAutoExecute": True, "isHidden": False, "executeOnStartup": False,
            "executeOnUser": False, "executeOnAi": False, "executeOnChatChange": False,
            "executeOnGroupMemberDraft": False, "executeOnNewChat": False, "executeBeforeGeneration": False,
            "automationId": ""}


def quick_reply_set(name, characters, places):
    """A SillyTavern Quick Reply set (format version 2, as its own Export button writes it): a button per place
    (moves the scene), a button per character (brings them in), and a few story helpers. Scene buttons post a
    narrator line with /sys; the helpers send an out-of-character request to the model."""
    rows = []
    for p in places[:QR_MAX]:
        rows.append((f"→ {p}", f"/sys The scene moves to {_qr_text(p)}.", f"Narrator line: the scene moves to {p}"))
    for c in characters[:QR_MAX]:
        rows.append((f"+ {c}", f"/sys {_qr_text(c)} enters the scene.", f"Narrator line: {c} arrives"))
    rows += [
        ("Time skip", "/sys Some time passes.", "Narrator line: a short time skip"),
        ("Recap", "(OOC: In two or three sentences, recap what has happened so far in this story, then continue.)",
         "Ask the model for a short recap"),
        ("Who's here?", "(OOC: Briefly list who is in the current scene, where we are, and what each person wants right now.)",
         "Ask the model to restate the scene"),
    ]
    qr = [_qr(i + 1, *r) for i, r in enumerate(rows)]
    return {"version": 2, "name": str(name)[:60] or "Story", "disableSend": False, "placeBeforeInput": False,
            "injectInput": False, "color": "transparent", "onlyBorderColor": False, "qrList": qr, "idIndex": len(qr)}


@bp.get("/api/text/project/<int:pid>/quick-replies")
def api_text_quick_replies(pid):
    import text_module as T
    r = T._project_row(pid)
    if not r:
        return jsonify({"error": "Not found"}), 404
    _, _, upto = T._project_recap(pid)
    ents = [e for e in T._entities(pid) if e["keep"] and not e.get("deleted")]
    ents = T.entities_as_of(pid, ents, upto) if T.lore_cutoff(r) else ents
    rank = {"main": 0, "supporting": 1}
    chars = sorted((e for e in ents if e["entity_type"] == "character" and e.get("tier") != "one-off"),
                   key=lambda e: (rank.get(e.get("tier") or "", 2), e["id"]))
    places = sorted((e for e in ents if e["entity_type"] == "place"), key=lambda e: e["id"])
    return jsonify(quick_reply_set(r["name"], [e["name"] for e in chars], [e["name"] for e in places]))


@bp.get("/api/lore/project/<int:pid>/quick-replies")
def api_lore_quick_replies(pid):
    project_name, items = lorebook_entries(pid)
    if not items:
        return jsonify({"error": "This project has no entries"}), 400
    by = lambda t: [it["title"] for it in items if (it.get("entry_type") or "").lower() == t]
    return jsonify(quick_reply_set(project_name or "Lore", by("character"), by("place")))


def register_st_bridge(app):
    app.register_blueprint(bp)
