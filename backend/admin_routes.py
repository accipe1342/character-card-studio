"""
admin_routes.py — database backups, per-task model presets and model usage
==========================================================================

GET  /api/backups                 list backups (newest first)
POST /api/backups                 make a backup now
POST /api/backups/restore         {"name": "..."}: restore one (a safety backup of the current DB is made first)
GET  /api/config/presets          model presets per task
POST /api/config/presets          save them
GET  /api/usage?days=30           calls and tokens per provider/model

Backups use SQLite's online backup API, so they are consistent even while the app is writing.
A backup is also made when the backend starts (at most once an hour); the newest KEEP_BACKUPS are kept.
"""

import json
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

import database

bp = Blueprint("admin", __name__)

KEEP_BACKUPS = 12
_NAME_RE = re.compile(r"^fandom_chars-\d{8}-\d{6}(?:-[a-z-]+)?\.db$")
PRESET_TASKS = ("extract", "critic", "card", "lore")
SETTINGS_PATH = Path(__file__).resolve().parent / "config" / "settings.json"


def _backup_dir() -> Path:
    d = Path(database.DB_PATH).resolve().parent / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_backups():
    out = []
    for p in sorted(_backup_dir().glob("fandom_chars-*.db"), reverse=True):
        if _NAME_RE.match(p.name):
            st = p.stat()
            out.append({"name": p.name, "bytes": st.st_size,
                        "created": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")})
    return out


def make_backup(reason: str = "") -> str:
    db_path = Path(database.DB_PATH)
    if not db_path.exists():
        raise FileNotFoundError("No database yet")
    tag = re.sub(r"[^a-z-]+", "", reason.lower())[:20]

    def _name():
        return f"fandom_chars-{datetime.now().strftime('%Y%m%d-%H%M%S')}{('-' + tag) if tag else ''}.db"
    name = _name()
    for _ in range(3):                 # two backups in the same second: wait for the next one
        if not (_backup_dir() / name).exists():
            break
        time.sleep(1)
        name = _name()
    target = _backup_dir() / name
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    for old in list_backups()[KEEP_BACKUPS:]:
        try:
            (_backup_dir() / old["name"]).unlink()
        except OSError:
            pass
    return name


def restore_backup(name: str) -> str:
    if not _NAME_RE.match(name or ""):
        raise ValueError("Unknown backup")
    src_path = _backup_dir() / name
    if not src_path.exists():
        raise ValueError("Backup not found")
    safety = make_backup("before-restore")
    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(str(database.DB_PATH))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return safety


def startup_backup():
    """One backup per start, but not more than once an hour."""
    try:
        latest = list_backups()[:1]
        if latest:
            age = time.time() - (_backup_dir() / latest[0]["name"]).stat().st_mtime
            if age < 3600:
                return None
        return make_backup("startup")
    except Exception as e:      # a failed backup must never stop the app
        print(f"[!] startup backup skipped: {e}", flush=True)
        return None


def _load_settings():
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_presets():
    raw = _load_settings().get("model_presets") or {}
    out = {}
    for task in PRESET_TASKS:
        v = raw.get(task) or {}
        out[task] = {"provider": str(v.get("provider") or ""), "model": str(v.get("model") or "")}
    return out


# ── routes ───────────────────────────────────────────────────────────────────
@bp.get("/api/backups")
def api_list_backups():
    return jsonify({"backups": list_backups(), "keep": KEEP_BACKUPS})


@bp.post("/api/backups")
def api_make_backup():
    try:
        return jsonify({"name": make_backup("manual")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.post("/api/backups/restore")
def api_restore_backup():
    try:
        name = (request.get_json(force=True) or {}).get("name", "")
        safety = restore_backup(name)
        return jsonify({"restored": name, "safety_backup": safety})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.get("/api/config/presets")
def api_get_presets():
    return jsonify(load_presets())


@bp.post("/api/config/presets")
def api_save_presets():
    data = request.get_json(force=True) or {}
    presets = {}
    for task in PRESET_TASKS:
        v = data.get(task) or {}
        prov = str(v.get("provider") or "").strip().lower()
        if prov and prov not in ("nanogpt", "openrouter", "local"):
            return jsonify({"error": f"Unknown provider for {task}: {prov}"}), 400
        model = str(v.get("model") or "").strip()
        if len(model) > 200 or "\n" in model:
            return jsonify({"error": f"Invalid model for {task}"}), 400
        presets[task] = {"provider": prov, "model": model}
    settings = _load_settings()
    settings["model_presets"] = presets
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "presets": presets})


@bp.get("/api/usage")
def api_usage():
    days = max(1, min(request.args.get("days", default=30, type=int), 365))
    rows = database.usage_summary(days)
    total = {"calls": sum(r["calls"] or 0 for r in rows),
             "prompt_tokens": sum(r["prompt_tokens"] or 0 for r in rows),
             "completion_tokens": sum(r["completion_tokens"] or 0 for r in rows)}
    return jsonify({"days": days, "rows": rows, "total": total})


def register_admin_routes(app):
    app.register_blueprint(bp)
    startup_backup()
