"""
charx.py — Character Card V3 .charx export
==========================================

A .charx is a zip holding card.json (a Character Card V3) and the card's files under assets/. The portrait is the
"icon" asset named "main"; its uri uses the embeded:// prefix (RisuAI's spelling, which SillyTavern and other apps
read). A card without a portrait points at "ccdefault:" (the app's default picture). SillyTavern 1.19 imports it
through its normal character import.

POST /api/export/charx   {card, mode?, lore_project_id?, image? (data URL, for a picture not saved yet)} -> .charx
"""

import io
import json
import re
import zipfile

from flask import Blueprint, jsonify, request, send_file

import images
from lore_routes import build_character_book
from preview import build_export_card_v3

bp = Blueprint("charx", __name__)


def build_charx(card, mode="natural", lore_project_id=None, image_bytes=None):
    v3 = build_export_card_v3(card, structured=mode == "structured")
    if lore_project_id not in (None, "", 0, "0"):
        book = build_character_book(int(lore_project_id))
        if book["entries"]:
            v3["data"]["character_book"] = book
    raw, ext = (image_bytes, images.sniff(image_bytes)) if image_bytes else images.load(card.get("image"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if raw and ext:
            path = f"assets/icon/images/main.{ext}"
            v3["data"]["assets"] = [{"type": "icon", "uri": f"embeded://{path}", "name": "main", "ext": ext}]
            z.writestr(path, raw, compress_type=zipfile.ZIP_STORED)      # images are already compressed
        else:
            v3["data"]["assets"] = [{"type": "icon", "uri": "ccdefault:", "name": "main", "ext": "png"}]
        z.writestr("card.json", json.dumps(v3, ensure_ascii=False, indent=2))
    return buf.getvalue()


@bp.post("/api/export/charx")
def api_export_charx():
    d = request.get_json(force=True) or {}
    card = d.get("card") or {}
    if not isinstance(card, dict):
        return jsonify({"error": "'card' must be the card object"}), 400
    from generator import clean_card_payload
    card = clean_card_payload(card)
    try:
        d["lore_project_id"] = int(d["lore_project_id"]) if d.get("lore_project_id") not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        return jsonify({"error": "lore_project_id must be a number"}), 400
    if not str(card.get("name") or "").strip():
        return jsonify({"error": "The card needs a name first"}), 400
    raw = None
    s = str(d.get("image") or "")
    if s.startswith("data:") and "," in s:
        import base64
        try:
            raw = base64.b64decode(s.split(",", 1)[1])
        except Exception:
            raw = None
        if raw and not images.sniff(raw):
            raw = None
    data = build_charx(card, d.get("mode") or "natural", d.get("lore_project_id"), raw)
    fname = re.sub(r"[^\w\- ]+", "", card["name"]).strip().replace(" ", "_") or "card"
    return send_file(io.BytesIO(data), mimetype="application/zip", as_attachment=True, download_name=f"{fname}.charx")


def register_charx(app):
    app.register_blueprint(bp)
