"""
images.py — portraits saved with cards and TEXT characters
=========================================================

Images live next to the database in data/images/, named by a hash of their bytes (the same picture is stored once).
Cards and TEXT entities keep only the file name in their `image` column.

POST /api/images                    multipart "file", or JSON {"data_url"} -> {image, url}. PNG, JPEG, WebP or GIF, 15 MB max.
GET  /api/images/<name>             the file
PUT  /api/card/<id>/image           {image: name | ""}   ("" removes the portrait from the card; the file stays)
PUT  /api/text/entity/<id>/image    {image: name | ""}
"""

import base64
import hashlib
import re
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

import database

bp = Blueprint("images", __name__)

MAX_BYTES = 15 * 1024 * 1024
NAME_RE = re.compile(r"^[0-9a-f]{20}\.(png|jpg|webp|gif)$")
MIME = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}


def images_dir():
    d = Path(database.DB_PATH).resolve().parent / "images"      # follows the database (tests use a temp one)
    d.mkdir(parents=True, exist_ok=True)
    return d


def sniff(raw):
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw[:3] == b"\xff\xd8\xff":
        return "jpg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def store(raw):
    """Save bytes, return the file name. Raises ValueError for anything that isn't a supported image."""
    if not raw:
        raise ValueError("Empty file")
    if len(raw) > MAX_BYTES:
        raise ValueError("Image is larger than 15 MB")
    ext = sniff(raw)
    if not ext:
        raise ValueError("Not a PNG, JPEG, WebP or GIF image")
    name = f"{hashlib.sha256(raw).hexdigest()[:20]}.{ext}"
    path = images_dir() / name
    if not path.exists():
        path.write_bytes(raw)
    return name


def load(name):
    """(bytes, ext) for a stored image, or (None, None)."""
    if not name or not NAME_RE.match(name):
        return None, None
    p = images_dir() / name
    return (p.read_bytes(), name.rsplit(".", 1)[1]) if p.exists() else (None, None)


def _set(table, row_id, name):
    if name and not NAME_RE.match(name):
        return jsonify({"error": "Unknown image"}), 400
    if name and not (images_dir() / name).exists():
        return jsonify({"error": "Image not found"}), 404
    conn = database._conn()
    cur = conn.execute(f"UPDATE {table} SET image=? WHERE id=?", (name or "", row_id))
    conn.commit()
    conn.close()
    if not cur.rowcount:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"image": name or ""})


@bp.post("/api/images")
def api_upload_image():
    raw = None
    if "file" in request.files:
        raw = request.files["file"].read(MAX_BYTES + 1)
    else:
        d = request.get_json(silent=True) or {}
        s = str(d.get("data_url") or "")
        if s.startswith("data:") and "," in s:
            try:
                raw = base64.b64decode(s.split(",", 1)[1])
            except Exception:
                raw = None
    try:
        name = store(raw)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"image": name, "url": f"/api/images/{name}"})


@bp.get("/api/images/<name>")
def api_get_image(name):
    if not NAME_RE.match(name):
        return jsonify({"error": "Not found"}), 404
    resp = send_from_directory(images_dir(), name, mimetype=MIME[name.rsplit(".", 1)[1]], max_age=31536000)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@bp.put("/api/card/<int:card_id>/image")
def api_card_image(card_id):
    return _set("cards", card_id, str((request.get_json(silent=True) or {}).get("image") or ""))


@bp.put("/api/text/entity/<int:eid>/image")
def api_entity_image(eid):
    return _set("text_entities", eid, str((request.get_json(silent=True) or {}).get("image") or ""))


def register_images(app):
    app.register_blueprint(bp)
