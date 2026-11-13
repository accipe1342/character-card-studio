"""
card_import.py — bring an existing character card into the library
==================================================================

POST /api/card/import   multipart "file": a card PNG (V2 "chara" / V3 "ccv3" chunk), a card .json (V1, V2 or V3),
                        or a .charx (zip with card.json and its images)
                        -> {card_id, name, lore_project_id?, entries?, image?, warnings}

The card is added as a NEW card (nothing is overwritten). Its embedded lorebook (character_book), if any, becomes a
new LORE project with the same entries and settings. The PNG itself, or the CHARX's main image, becomes the portrait.
Cards exported from this app come back with their structured profile and Character's Note.
"""

import io
import json
import re
import uuid
import zipfile

from flask import Blueprint, jsonify, request

import database as D
import images as IMG
import png_card

bp = Blueprint("card_import", __name__)
MAX_BYTES = 30 * 1024 * 1024

TEXT_FIELDS = ("name", "description", "personality", "scenario", "first_mes", "mes_example", "creator_notes",
               "system_prompt", "creator", "character_version")
POSITIONS = {"before_char": 0, "after_char": 1}
ENTRY_TYPES = ("character", "place", "faction", "event", "item", "ability", "concept", "other")


class ImportError_(ValueError):
    pass


def _s(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "\n".join(_s(x) for x in v if _s(x))
    return str(v)


def _list(v):
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return []


def card_data(obj):
    """Any card JSON (V1 flat, V2, V3) -> the 'data' dict with V2 field names."""
    if not isinstance(obj, dict):
        raise ImportError_("This file has no character card in it.")
    data = obj.get("data") if isinstance(obj.get("data"), dict) else obj
    if "char_name" in data and not data.get("name"):           # very old V1 names
        data = {**data, "name": data.get("char_name"), "personality": data.get("char_persona", data.get("personality")),
                "first_mes": data.get("char_greeting", data.get("first_mes")),
                "scenario": data.get("world_scenario", data.get("scenario")), "mes_example": data.get("example_dialogue", "")}
    if not any(data.get(k) for k in ("name", "description", "first_mes", "personality")):
        if data.get("entries") is not None:
            raise ImportError_("This is a lorebook (World Info) file, not a character card. Import it in LORE.")
        raise ImportError_("This file has no character card in it (no name, description or first message).")
    return data


def read_file(name, raw):
    """-> (card JSON object, image bytes or None)"""
    low = (name or "").lower()
    if raw.startswith(png_card.SIG):
        try:
            chunks = png_card.read(raw)
        except Exception:
            raise ImportError_("This PNG could not be read.")
        obj = chunks.get("ccv3") or chunks.get("chara")
        if not obj:
            raise ImportError_("This PNG has no character card inside it. Only card PNGs (with card data) can be imported.")
        return obj, raw
    if raw[:2] == b"PK" or low.endswith(".charx"):
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile:
            raise ImportError_("This .charx file is damaged.")
        if "card.json" not in z.namelist():
            raise ImportError_("This zip has no card.json, so it is not a CHARX card.")
        if sum(i.file_size for i in z.infolist()) > 200 * 1024 * 1024 or z.getinfo("card.json").file_size > 20 * 1024 * 1024:
            raise ImportError_("This .charx unpacks to more than 200 MB; it can't be imported.")
        obj = json.loads(z.read("card.json").decode("utf-8"))
        image = None
        assets = ((obj.get("data") or {}).get("assets") or []) if isinstance(obj, dict) else []
        want = [a.get("uri", "") for a in assets if isinstance(a, dict) and a.get("type") in ("icon", "main")]
        names = [w.split("embeded://", 1)[-1].split("embedded://", 1)[-1] for w in want]
        names += [n for n in z.namelist() if re.search(r"\.(png|jpe?g|webp|gif)$", n, re.I)]
        for n in names:
            if n in z.namelist():
                image = z.read(n)
                break
        return obj, image
    try:
        return json.loads(raw.decode("utf-8-sig")), None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ImportError_("Unsupported file. Import a card PNG, a card .json or a .charx.")


def to_card(data):
    ext = data.get("extensions") if isinstance(data.get("extensions"), dict) else {}
    card = {k: _s(data.get(k)) for k in TEXT_FIELDS}
    card["name"] = card["name"].strip() or "Imported character"
    card["post_history"] = _s(data.get("post_history_instructions"))
    card["alternate_greetings"] = [_s(g) for g in (data.get("alternate_greetings") or []) if _s(g).strip()]
    card["tags"] = _list(data.get("tags"))
    dp = ext.get("depth_prompt")
    card["depth_prompt"] = _s(dp.get("prompt")) if isinstance(dp, dict) else _s(dp)
    sp = ext.get("structured_profile")
    card["structured_profile"] = sp if isinstance(sp, dict) else {}
    if card["creator_notes"] == "Generated and edited in local Character Card Studio.":
        card["creator_notes"] = ""
    return card


def _entry_title(e, i):
    for k in ("name", "comment"):
        t = _s(e.get(k)).strip()
        if t:
            return re.sub(r"\s+-\s+(" + "|".join(ENTRY_TYPES) + r")$", "", t)[:200]
    keys = _list(e.get("keys"))
    return keys[0] if keys else f"Entry {i + 1}"


def import_book(book, card_name):
    """character_book -> a new LORE project. Returns (project_id, entry count)."""
    entries = book.get("entries") if isinstance(book, dict) else None
    if isinstance(entries, dict):
        entries = list(entries.values())
    entries = [e for e in (entries or []) if isinstance(e, dict) and _s(e.get("content")).strip()]
    if not entries:
        return None, 0
    pid = D.create_lore_project((_s(book.get("name")).strip() or f"{card_name} lorebook")[:120])
    for i, e in enumerate(entries):
        ex = e.get("extensions") if isinstance(e.get("extensions"), dict) else {}
        title = _entry_title(e, i)
        m = re.search(r"\s+-\s+(" + "|".join(ENTRY_TYPES) + r")$", _s(e.get("comment")))
        etype = m.group(1) if m else "concept"
        content = _s(e.get("content")).strip()
        lid = D.save_lore_entry(crawl_id=pid, source_id=None, title=title, entry_type=etype,
                                keywords=_list(e.get("keys") or e.get("key")), summary=content[:200], content=content,
                                provider="import", model="")
        wi = {"constant": 1 if e.get("constant") else 0, "secondary_keys": _list(e.get("secondary_keys") or e.get("keysecondary"))}
        pos = ex.get("position", POSITIONS.get(e.get("position"), None))
        if isinstance(pos, int):
            wi["position"] = pos
        for src, dst in (("depth", "entry_depth"), ("probability", "probability"), ("sticky", "sticky"),
                         ("cooldown", "cooldown"), ("delay", "delay"), ("selectiveLogic", "selective_logic"),
                         ("scan_depth", "scan_depth"), ("group", "group_name"), ("group_weight", "group_weight")):
            if ex.get(src) not in (None, ""):
                wi[dst] = ex[src]
        if isinstance(ex.get("role"), int):
            wi["role"] = ex["role"]
        order = e.get("insertion_order", e.get("priority"))
        if isinstance(order, int):
            wi["insertion_order"] = order
            wi["order_manual"] = 1
        cf = ex.get("character_filter")
        if isinstance(cf, dict) and cf.get("names") and not cf.get("isExclude"):
            wi["char_filter"] = _list(cf.get("names"))
        D.set_lore_wi_fields(lid, wi)
    return pid, len(entries)


@bp.post("/api/card/import")
def api_card_import():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file: choose a card PNG, .json or .charx"}), 400
    raw = f.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        return jsonify({"error": "That file is too large (30 MB max)."}), 400
    try:
        obj, image = read_file(f.filename, raw)
        data = card_data(obj)
    except ImportError_ as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:                                    # a damaged file: a readable message, not a crash
        return jsonify({"error": f"This file could not be read as a card ({str(e)[:120]})."}), 400
    card = to_card(data)
    warnings = []
    sid = D.save_source({"wiki_base": "manual", "page_name": "import", "url": f"manual://import/{uuid.uuid4().hex}",
                         "title": card["name"], "raw_html": "", "raw_infobox": {}, "raw_sections": {}, "normalized": {}})
    cid = D.create_or_update_card(sid, {**card, "provider": "import", "model": ""}, force_new=True)
    out = {"card_id": cid, "name": card["name"]}
    if image:
        try:
            name = IMG.store(image)
            conn = D._conn()
            conn.execute("UPDATE cards SET image=? WHERE id=?", (name, cid))
            conn.commit()
            conn.close()
            out["image"] = name
        except ValueError:
            warnings.append("The picture could not be kept (unsupported image type).")
    pid, n = import_book(data.get("character_book"), card["name"])
    if pid:
        out.update(lore_project_id=pid, entries=n)
    out["warnings"] = warnings
    return jsonify(out)


def register_card_import(app):
    app.register_blueprint(bp)
