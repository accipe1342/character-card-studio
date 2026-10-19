"""
app.py — Flask API server
==========================
The main backend process. Serves the JSON API that the React frontend
calls via fetch(). Runs on http://localhost:5000 and is started by
start.bat / start.sh alongside the Vite dev server.

ARCHITECTURE
------------
- Flask app with no templating (the React frontend handles all UI)
- Background jobs run in daemon threads via Python's threading module
- Job state is stored in the in-memory JOBS dict (pruned hourly)
- All persistence goes through database.py
- AI generation goes through generator.py
- Web scraping goes through scraper.py

API ROUTES — CHARACTER CARDS
-----------------------------
POST   /api/scrape                  Start a scrape job for a URL
POST   /api/generate                Start a card generation job
POST   /api/generate/batch          Batch generate cards from multiple URLs
POST   /api/generate/cast           Generate a combined cast card from existing cards
GET    /api/cards                   List all saved cards (supports ?q= search)
GET    /api/card/<id>               Get a single card by ID
POST   /api/card/<id>               Save / update a card
POST   /api/card/<id>/duplicate     Duplicate a card
DELETE /api/card/<id>               Delete a card
POST   /api/card/<id>/field/regen   Regenerate a single field
GET    /api/card/<id>/export/png    Export card as a SillyTavern PNG

API ROUTES — LORE   (in lore_routes.py; simulator/graph/trash in lore_tools.py)
-----------------
POST   /api/lore/crawl              Start a single-URL lore generation job
POST   /api/lore/multi              Start a multi-URL lore crawl job
GET    /api/lore/projects           List all lore projects
POST   /api/lore/project            Create a new lore project
PATCH  /api/lore/project/<id>       Rename a project
DELETE /api/lore/project/<id>       Delete a project and its entries
GET    /api/lore/entries/<crawl_id> List entries for a project
POST   /api/lore/entry/new          Create a blank lore entry
POST   /api/lore/entry/generate     Generate a lore entry from custom text
PATCH  /api/lore/entry/<id>         Update a lore entry
PATCH  /api/lore/entry/<id>/project Move entry to a different project
DELETE /api/lore/entry/<id>         Delete a lore entry
GET    /api/lore/export[?project_id=N]  Export a lorebook (one project, or all) as SillyTavern JSON

API ROUTES — CONFIG & MODELS
-----------------------------
GET    /api/config                  Get current settings (provider, model, etc.)
POST   /api/config                  Save settings
GET    /api/models/<provider>       Fetch available models from NanoGPT or OpenRouter
GET    /api/image-proxy             Proxy an external image URL (CORS bypass)

API ROUTES — JOBS
-----------------
GET    /api/job/<job_id>            Poll job status and result

JOB SYSTEM
----------
Long-running operations (scrape, generate, crawl) run in background
threads and report progress through the JOBS dict. The frontend polls
GET /api/job/<id> every second until status is "done" or "failed".

Job lifecycle:
    create_job()           → status: "queued"
    update_job(...)        → status: "running", stage, progress, message
    update_job(done=True)  → status: "done", result: {...}
    (on exception)         → status: "failed", error: "..."

Jobs older than 1 hour are pruned from memory on each new job creation.

HOW TO EXTEND
-------------
- Add a new API route: add a @app.get/post/patch/delete decorated
  function. Follow the pattern of existing routes — return jsonify()
  and catch exceptions with a 500 response.
- Add a new background job: call create_job(), spawn a Thread that
  calls update_job() for progress and sets status="done" with a
  result dict when complete.
- Change the port: set the PORT environment variable, or edit the
  app.run() call at the bottom of the file.
- Add authentication: add a before_request hook that checks a token
  header. All routes will require it automatically.
"""

import io
import ipaddress
import json
import os
import socket
import sqlite3
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from dotenv import load_dotenv
import logging
from flask import (
    Flask,
    abort,
    jsonify,
    request,
    send_file,
)

from lore_crawler import crawl_worldbook

from database import (
    DB_PATH,
    create_or_update_card,
    get_card,
    get_source,
    init_db,
    list_cards,
    save_field_version,
    save_source,
    delete_card,
    duplicate_card,
    save_lore_entry,
    create_lore_crawl,
    update_lore_crawl_status,
    save_lore_crawl_page,
    save_job_row, load_job_row, mark_interrupted_jobs, usage_summary,
)

from generator import (
    generate_full_card,
    regenerate_single_field,
    generate_lore_entry,
    _request as _gen_request,
    _ensure_list,
    load_runtime_config,
)
from preview import (build_export_card_json, build_export_card_v3, format_structured_profile_text, normalise_lore_items,
                     character_book_from_items, world_info_book)
from scraper import scrape_url
import threading
import uuid

# Ensure UTF-8 output on Windows
import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

JOBS = {}
_JOB_MAX_AGE_SECONDS = 3600  # prune jobs older than 1 hour


def _prune_old_jobs():
    """Remove completed/failed jobs older than JOB_MAX_AGE to prevent memory leak."""
    import time as _time
    now = _time.time()
    to_delete = []
    for jid, job in JOBS.items():
        if job.get("status") in ("done", "failed"):
            ts = job.get("_created_at", now)
            if now - ts > _JOB_MAX_AGE_SECONDS:
                to_delete.append(jid)
    for jid in to_delete:
        del JOBS[jid]


def create_job():
    import time as _time
    _prune_old_jobs()
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "message": "Waiting to start...",
        "result": None,
        "error": None,
        "_created_at": _time.time(),
    }
    return job_id


def update_job(job_id, **kwargs):
    """Update a job; it is also written to SQLite (on status changes and at most every 1.5 s), so a page
    polling after a backend restart gets a clear 'interrupted' result instead of a vanished job."""
    import time as _time
    if job_id in JOBS:
        job = JOBS[job_id]
        job.update(kwargs)
        now = _time.time()
        if "status" in kwargs or now - job.get("_saved_at", 0) > 1.5:
            job["_saved_at"] = now
            try:
                save_job_row({"id": job_id, **{k: v for k, v in job.items() if not k.startswith("_")}})
            except Exception:
                pass


def run_scrape_job(job_id: str, url: str):
    try:
        log_info(f"Scrape started  →  {url}")

        update_job(
            job_id,
            status="running",
            stage="fetching_page",
            progress=10,
            message="Fetching wiki page...",
        )

        log_dim("  fetching page...")
        source = scrape_url(url)
        log_dim("  page fetched")

        update_job(
            job_id,
            stage="saving_source",
            progress=80,
            message="Source scraped and saved.",
        )

        log_dim("  saving source...")
        source_id = save_source(source)
        log_dim(f"  source saved  id={source_id}")

        update_job(
            job_id,
            status="done",
            stage="done",
            progress=100,
            message="Wiki page scraped successfully.",
            result={
                "source_id": source_id,
                "source": source,
            },
        )
        log_ok(f"Scrape complete  →  {url}")
    except Exception as e:
        import traceback
        traceback.print_exc()

        update_job(
            job_id,
            status="failed",
            stage="failed",
            progress=100,
            message=str(e),
            error=str(e),
        )


def run_generate_job(job_id: str, source_id: int, provider: str, model: str, as_new: bool = False,
                     options: dict | None = None):
    try:
        log_info(f"Generate started  →  source={source_id}  {provider}/{model}")

        update_job(
            job_id,
            status="running",
            stage="loading_source",
            progress=10,
            message="Loading scraped source data...",
        )

        source = get_source(source_id)
        log_dim("  source loaded")

        update_job(
            job_id,
            stage="building_prompt",
            progress=25,
            message="Preparing character generation prompt...",
        )

        log_dim("  sending to model...")
        update_job(
            job_id,
            stage="requesting_model",
            progress=60,
            message=f"Sending to {provider}/{model or 'default'}...",
        )

        options = dict(options or {})
        options["progress"] = lambda msg: update_job(job_id, stage="requesting_model", progress=60, message=msg)
        generated = generate_full_card(source, provider, model, options)
        log_dim("  model responded")
        warnings = generated.pop("_warnings", [])
        for w in warnings:
            log_warn(f"  card check: {w}")

        generated["provider"] = provider
        generated["model"] = model

        update_job(
            job_id,
            stage="saving_card",
            progress=90,
            message="Parsing and saving character card...",
        )

        # as_new: a card from this source already exists (maybe hand-edited) — keep it and save a new one
        card_id = create_or_update_card(source_id, generated, force_new=as_new)
        log_dim(f"  card saved  id={card_id}" + ("  (new card; the earlier one is kept)" if as_new else ""))

        update_job(
            job_id,
            status="done",
            stage="done",
            progress=100,
            message="Character card ready." + (f" {len(warnings)} thing(s) to check." if warnings else ""),
            result={
                "card_id": card_id,
                "card": get_card(card_id),      # as stored (includes the Character's Note, system prompt...)
                "warnings": warnings,
            },
        )

    except Exception as e:
        import traceback
        traceback.print_exc()

        log_error(f"Job failed: {e}")
        update_job(
            job_id,
            status="failed",
            stage="failed",
            progress=100,
            message=str(e),
            error=str(e),
        )


def run_lore_crawl_job(
    job_id,
    seed_url,
    max_pages,
    max_depth,
    provider,
    model,
    purpose,
    criteria,
    extraction_notes,
):
    try:
        update_job(
            job_id,
            status="running",
            stage="starting",
            progress=5,
            message="Starting crawl...",
        )

        crawl_id = create_lore_crawl(seed_url, max_pages, max_depth, "running")

        update_job(
            job_id,
            stage="crawling",
            progress=10,
            message="Crawling pages...",
        )

        crawled_pages = crawl_worldbook(
            seed_url=seed_url,
            max_pages=max_pages,
            max_depth=max_depth,
        )

        total = max(len(crawled_pages), 1)
        results = []

        for i, item in enumerate(crawled_pages, start=1):
            url = item["url"]
            depth = item["depth"]
            source = item["source"]

            source_id = save_source(source)

            save_lore_crawl_page(
                crawl_id=crawl_id,
                url=url,
                source_id=source_id,
                depth=depth,
                page_title="",
                status="processing",
            )

            lore_result = generate_lore_entry(
                source,
                provider=provider,
                model=model,
                purpose=purpose,
                criteria=criteria,
                extraction_notes=extraction_notes,
            )

            if not isinstance(lore_result, dict):
                print(f"[LORE ERROR] Invalid response type for {url}")
                continue

            if not lore_result.get("valid"):
                print(f"[LORE SKIP] {url} → {lore_result.get('reason', 'invalid')}")
                continue

            entry = lore_result.get("entry")

            if not entry:
                print(f"[LORE ERROR] Missing entry for {url}")
                continue

            lore_id = save_lore_entry(
                crawl_id=crawl_id,
                source_id=source_id,
                title=entry["title"],
                entry_type=entry.get("entry_type", "world"),
                keywords=entry.get("keywords", []),
                summary=entry.get("summary", ""),
                content=entry.get("content", ""),
                provider=provider,
                model=model,
            )

            save_lore_crawl_page(
                crawl_id=crawl_id,
                url=url,
                source_id=source_id,
                depth=depth,
                page_title=entry["title"],
                status="done",
            )

            results.append(
                {
                    "lore_id": lore_id,
                    "title": entry["title"],
                    "url": url,
                }
            )

            progress = 10 + int((i / total) * 85)

            update_job(
                job_id,
                stage="generating",
                progress=progress,
                message=f"{len(results)} entries saved / {i} pages processed",
            )

            if len(results) >= max_pages:
                break

        update_lore_crawl_status(crawl_id, "done")

        update_job(
            job_id,
            status="done",
            stage="done",
            progress=100,
            message="Lore crawl complete.",
            result={"entries": results},
        )

    except Exception as e:
        import traceback
        traceback.print_exc()

        update_job(
            job_id,
            status="failed",
            stage="failed",
            progress=100,
            message=str(e),
            error=str(e),
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        update_job(
            job_id,
            status="failed",
            stage="failed",
            progress=100,
            message=str(e),
            error=str(e),
        )


def load_config():
    if not CONFIG_PATH.exists():
        return {"use_templates": False}

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(data):
    CONFIG_PATH.parent.mkdir(exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


BASE_DIR = Path(__file__).resolve().parent          # backend/
ROOT_DIR = BASE_DIR.parent                             # project root
DATA_DIR = ROOT_DIR / "data"                           # data/
DATA_DIR.mkdir(exist_ok=True)
ENV_PATH = ROOT_DIR / ".env"
CONFIG_PATH = BASE_DIR / "config" / "settings.json"

load_dotenv(ENV_PATH, override=True)

app = Flask(__name__)
init_db()
try:
    _n_interrupted = mark_interrupted_jobs()
    if _n_interrupted:
        print(f"[!] {_n_interrupted} job(s) were interrupted by the last restart", flush=True)
except Exception:
    pass

# ── Local-only request guard ──────────────────────────────────────────────────
# This server has no login, so it must only answer the app you are using:
#  * Host check   - blocks DNS-rebinding (a website re-pointing its name at 127.0.0.1)
#  * Origin check - blocks other websites from sending POST/PATCH/DELETE to it
# Requests with no Origin header (curl, scripts) are allowed. Escape hatches:
#   CCS_STRICT_ORIGIN=0          turn the guard off
#   CCS_ALLOWED_ORIGINS=a,b      extra allowed origins, e.g. http://192.168.1.5:5173
_SAFE_HOSTS = {"localhost", "127.0.0.1", "::1"}
_SAFE_PORTS = {5000, 5173, 4173, int(os.getenv("PORT", 5000) or 5000)}
_EXTRA_ORIGINS = {o.strip().rstrip("/").lower() for o in os.getenv("CCS_ALLOWED_ORIGINS", "").split(",") if o.strip()}


def _origin_allowed(origin: str) -> bool:
    if origin.rstrip("/").lower() in _EXTRA_ORIGINS:
        return True
    try:
        u = urlsplit(origin)
        return u.scheme in ("http", "https") and u.hostname in _SAFE_HOSTS and u.port in _SAFE_PORTS
    except ValueError:
        return False


@app.before_request
def _local_only_guard():
    if os.getenv("CCS_STRICT_ORIGIN", "1") == "0":
        return None
    try:
        host = urlsplit("//" + (request.host or "")).hostname
    except ValueError:
        host = None
    if host not in _SAFE_HOSTS and (request.host or "").lower() not in _EXTRA_ORIGINS \
            and ("http://" + (request.host or "").lower()) not in _EXTRA_ORIGINS:
        return jsonify({"error": "Blocked: unexpected Host header"}), 403
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("Origin")
        if origin is not None and not _origin_allowed(origin):
            return jsonify({"error": "Blocked: cross-site request"}), 403
    return None


@app.errorhandler(ValueError)
def _value_error(e):
    """get_card / get_source raise ValueError for a missing id: answer 404 instead of a 500 page."""
    msg = str(e)
    return jsonify({"error": msg}), (404 if "not found" in msg.lower() else 400)

# TEXT studio (fanfiction / long-form text -> lorebook)
from text_module import register_text_module
register_text_module(app, create_job, update_job)
from admin_routes import register_admin_routes      # backups, model presets, usage
register_admin_routes(app)
from lore_tools import register_lore_tools   # simulator, graph, trash
register_lore_tools(app)
from critic_tools import register_critic_tools   # chapter sweep, rewrite a passage
register_critic_tools(app)
from bundle_routes import register_bundle_routes   # project bundles (.zip export / import)
register_bundle_routes(app)
from search_routes import register_search_routes   # one search box across cards, lore and TEXT
register_search_routes(app)
# (lore_routes is registered further down, once the job and logging helpers exist)

# ── Custom logging setup ──────────────────────────────────────────────────────

class _SuppressJobPolling(logging.Filter):
    """Hide the high-frequency /api/job polling lines from the access log."""
    def filter(self, record):
        msg = record.getMessage()
        return "/api/job/" not in msg

# Apply filter to Werkzeug access log
_wz_log = logging.getLogger("werkzeug")
_wz_log.addFilter(_SuppressJobPolling())

# Coloured print helpers for generator progress
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_CYAN   = "\033[36m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_DIM    = "\033[2m"

def log_info(msg):   print(f"{_CYAN}[.]{_RESET} {msg}")
def log_ok(msg):     print(f"{_GREEN}[OK]{_RESET} {_BOLD}{msg}{_RESET}")
def log_warn(msg):   print(f"{_YELLOW}[!]{_RESET} {msg}")
def log_error(msg):  print(f"{_RED}[ERR]{_RESET} {_BOLD}{msg}{_RESET}")
def log_dim(msg):    print(f"{_DIM}{msg}{_RESET}")


# ---------- DB helpers ----------
def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_table_names() -> list[str]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    )
    rows = [r["name"] for r in cur.fetchall()]
    conn.close()
    return rows


def get_table_rows(
    table_name: str, limit: int = 100
) -> tuple[list[str], list[sqlite3.Row]]:
    allowed = {"sources", "cards", "field_versions"}
    if table_name not in allowed:
        abort(404)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]
    conn.close()
    return columns, rows


def get_table_count(table_name: str) -> int:
    allowed = {"sources", "cards", "field_versions"}
    if table_name not in allowed:
        return 0

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) AS count FROM {table_name}")
    count = cur.fetchone()["count"]
    conn.close()
    return count


# ---------- Main pages ----------
from prompt_templates import get_prompt_templates


from prompt_templates import save_prompt_templates


# ---------- Scrape Job ----------
@app.post("/api/scrape/start")
def api_scrape_start():
    try:
        data = request.get_json(force=True) or {}
        url = data.get("url", "").strip()

        if not url:
            return jsonify({"error": "Missing URL"}), 400

        job_id = create_job()
        threading.Thread(target=run_scrape_job, args=(job_id, url), daemon=True).start()

        return jsonify({"job_id": job_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/generate/start")
def api_generate_start():
    try:
        data = request.get_json(force=True) or {}

        source_id = data.get("source_id")
        provider = data.get("provider", "nanogpt")
        model = data.get("model") or os.getenv("NANOGPT_MODEL", "deepseek/deepseek-v4.1-flash")

        if not source_id:
            return jsonify({"error": "Missing source_id"}), 400

        options = {k: data.get(k) for k in ("story_point", "user_role", "token_target", "style", "deep")
                   if data.get(k) not in (None, "")}
        if data.get("lore_project_id"):
            options["lore_aware"] = True
        job_id = create_job()
        threading.Thread(
            target=run_generate_job,
            args=(job_id, source_id, provider, model, bool(data.get("as_new")), options),
            daemon=True,
        ).start()

        return jsonify({"job_id": job_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/generate/batch")
def api_generate_batch():
    """Scrape + generate character cards for multiple URLs in one job."""
    try:
        data = request.get_json(force=True) or {}
        urls = [u.strip() for u in data.get("urls", []) if u.strip()]
        provider = data.get("provider", "nanogpt")
        model = data.get("model", "")

        if not urls:
            return jsonify({"error": "No URLs provided"}), 400
        if len(urls) > 10:
            return jsonify({"error": "Maximum 10 URLs per batch"}), 400

        job_id = create_job()

        def run():
            results = []
            errors = []
            for i, url in enumerate(urls):
                pct = int((i / len(urls)) * 90)
                update_job(job_id, status="running", stage="scraping",
                           progress=pct,
                           message=f"[{i+1}/{len(urls)}] Scraping {url.split('/')[-1]}...")
                try:
                    source = scrape_url(url)
                    source_id = save_source(source)

                    update_job(job_id, status="running", stage="generating",
                               progress=pct + 5,
                               message=f"[{i+1}/{len(urls)}] Generating {source.get('title', url.split('/')[-1])}...")

                    generated = generate_full_card(source, provider, model); generated.pop("_warnings", None)
                    generated["provider"] = provider
                    generated["model"] = model
                    # Merge sex -> gender if needed
                    if generated.get("structured_profile") and                        not generated["structured_profile"].get("gender") and                        generated["structured_profile"].get("sex"):
                        generated["structured_profile"]["gender"] = generated["structured_profile"]["sex"]

                    card_id = create_or_update_card(source_id, generated)
                    results.append({"card_id": card_id, "name": generated.get("name", ""), "url": url})
                    log_ok(f"Batch [{i+1}/{len(urls)}] generated: {generated.get('name', url)}")
                except Exception as e:
                    log_warn(f"Batch [{i+1}/{len(urls)}] failed for {url}: {e}")
                    errors.append({"url": url, "error": str(e)})

            update_job(job_id, status="done", stage="done", progress=100,
                       message=f"{len(results)} cards generated, {len(errors)} failed.",
                       result={"cards": results, "errors": errors})

        threading.Thread(target=run, daemon=True).start()
        return jsonify({"job_id": job_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# LORE studio routes live in lore_routes.py
from lore_routes import build_character_book, register_lore_routes   # noqa: E402
register_lore_routes(app, create_job=create_job, update_job=update_job, get_db_connection=get_db_connection,
                     run_lore_crawl_job=run_lore_crawl_job, log_info=log_info, log_ok=log_ok, log_warn=log_warn,
                     log_dim=log_dim)


@app.get("/")
def api_root():
    """The UI is the React app (http://localhost:5173 in development). The old Flask template pages are gone."""
    return ("<!doctype html><title>Character Card Studio API</title><body style='font-family:system-ui;padding:24px'>"
            "<h2>Character Card Studio backend is running</h2><p>Open the app at "
            "<a href='http://localhost:5173'>http://localhost:5173</a>.</p></body>")


@app.get("/api/job/<job_id>")
def api_job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        job = load_job_row(job_id)     # finished before a restart, or cut off by one
    if not job:
        return jsonify({"error": "Job not found. The backend may have restarted; run it again.", "status": "failed",
                        "message": "Job not found. The backend may have restarted; run it again."}), 404
    return jsonify({k: v for k, v in job.items() if not k.startswith("_")})


# ---------- Scrape / cards ----------
# ---------- React Scrap ----------
@app.get("/api/test")
def api_test():
    return jsonify({"ok": True})




@app.post("/api/scrape")
def api_scrape():
    try:
        data = request.get_json(force=True) or {}
        url = data.get("url", "").strip()

        if not url:
            return jsonify({"error": "Missing URL"}), 400

        source = scrape_url(url)
        source_id = save_source(source)

        return jsonify({"source_id": source_id, "source": source})
    except Exception as e:
        print("SCRAPE ERROR:", repr(e))
        return jsonify({"error": str(e)}), 500


@app.post("/api/generate-card")
def api_generate_card():
    try:
        data = request.get_json(force=True)

        source_id = data.get("source_id")
        provider = data.get("provider", "nanogpt")
        model = data.get("model", "")

        if not source_id:
            return jsonify({"error": "Missing source_id"}), 400

        source = get_source(source_id)

        generated = generate_full_card(source, provider, model); generated.pop("_warnings", None)
        generated["provider"] = provider
        generated["model"] = model

        card_id = create_or_update_card(source_id, generated)

        return jsonify({"card_id": card_id, "card": generated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/models/<provider>")
def api_list_models(provider):
    import requests as req
    try:
        if provider == "nanogpt":
            api_key = os.getenv("NANOGPT_API_KEY", "")
            if not api_key:
                return jsonify({"error": "No NanoGPT API key configured"}), 400
            r = req.get(
                "https://nano-gpt.com/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                params={"sort": "mostused"},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            # Filter to text models only and return id + name
            models = [
                {"id": m["id"], "name": m.get("name") or m["id"]}
                for m in data.get("data", [])
                if m.get("object") == "model"
            ]
            return jsonify({"models": models})

        elif provider == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY", "")
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            r = req.get(
                "https://openrouter.ai/api/v1/models",
                headers=headers,
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            # Filter to text-generation models only, exclude image/audio/embedding
            excluded = ("stable-diffusion", "dall-e", "whisper", "embedding",
                        "tts", "vision", "image", "audio", "moderation")
            models = []
            for m in data.get("data", []):
                mid = m.get("id", "")
                arch = (m.get("architecture") or {})
                modality = arch.get("modality", "") or ""
                # Skip non-text modalities
                if "image" in modality and "text" not in modality:
                    continue
                if any(x in mid.lower() for x in excluded):
                    continue
                models.append({
                    "id": mid,
                    "name": m.get("name") or mid,
                    "context": m.get("context_length"),
                    "per_token": (m.get("pricing") or {}).get("prompt"),
                })
            # Sort alphabetically by name
            models.sort(key=lambda m: m["name"].lower())
            return jsonify({"models": models})

        else:
            return jsonify({"error": "Unknown provider"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/card/<int:card_id>/duplicate")
def api_duplicate_card(card_id):
    try:
        new_id = duplicate_card(card_id)
        new_card = get_card(new_id)
        log_ok(f"Card duplicated  {card_id} → {new_id}")
        return jsonify({"card": new_card, "id": new_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.delete("/api/card/<int:card_id>")
def api_delete_card(card_id):
    try:
        delete_card(card_id)
        log_ok(f"Card deleted  id={card_id}")
        return jsonify({"deleted": card_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/card/new")
def api_new_blank_card():
    """Create a blank card with no source (manual mode)."""
    try:
        data = request.get_json(force=True) or {}
        name = data.get("name", "New Character").strip() or "New Character"

        # Create a placeholder manual source
        source_id = save_source({
            "wiki_base": "manual",
            "page_name": "manual",
            "url": f"manual://card/{name.lower().replace(' ', '-')}",
            "title": name,
            "raw_html": "",
            "raw_infobox": {},
            "raw_sections": {},
            "normalized": {},
            "infobox_image": "",
        })

        blank = {
            "name": name,
            "description": "",
            "personality": "",
            "scenario": "",
            "first_mes": "",
            "mes_example": "",
            "tags": [],
            "structured_profile": {},
            "alternate_greetings": [],
            "provider": "manual",
            "model": "",
        }

        card_id = create_or_update_card(source_id, blank)
        card = get_card(card_id)
        log_ok(f"Blank card created: {name} id={card_id}")
        return jsonify({"card": card, "card_id": card_id, "source_id": source_id})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.get("/api/cards")
def api_list_cards():
    try:
        q = request.args.get("q", "").strip().lower()
        cards = list_cards()
        if q:
            cards = [c for c in cards if q in (c.get("name") or "").lower()
                     or q in (c.get("url") or "").lower()
                     or q in (c.get("title") or "").lower()]
        return jsonify(cards)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.patch("/api/card/<int:card_id>/name")
def api_rename_card(card_id):
    try:
        data = request.get_json(force=True) or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Name cannot be empty"}), 400
        card = get_card(card_id)
        card["name"] = name
        create_or_update_card(card["source_id"], card, card_id=card_id)
        return jsonify({"name": name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/card/<int:card_id>")
def api_get_card(card_id):
    card = get_card(card_id)
    source = get_source(card["source_id"])
    return jsonify({"card": card, "source": source})


@app.post("/api/save-card/<int:card_id>")
def api_save_card(card_id):
    payload = request.get_json(force=True)

    card = get_card(card_id)
    payload["provider"] = card["provider"]
    payload["model"] = card["model"]

    create_or_update_card(card["source_id"], payload, card_id=card_id)

    return jsonify({"status": "ok"})


@app.post("/api/generate/full/<int:card_id>")
def api_generate_full(card_id: int):
    try:
        card = get_card(card_id)
        source = get_source(card["source_id"])

        generated = generate_full_card(source, card["provider"], card["model"]); generated.pop("_warnings", None)
        generated["provider"] = card["provider"]
        generated["model"] = card["model"]

        create_or_update_card(card["source_id"], generated, card_id=card_id)

        return jsonify(
            {
                "status": "ok",
                "card_id": card_id,
                "card": generated,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/generate/greeting/<int:card_id>")
def api_generate_greeting(card_id: int):
    """Regenerate one alternate greeting by index, or generate a new one."""
    try:
        data = request.get_json(force=True) or {}
        idx = data.get("idx", None)  # None = generate brand new
        custom_prompt = data.get("custom_prompt", "").strip()

        card = get_card(card_id)
        greetings = card.get("alternate_greetings") or []

        existing = greetings[idx] if idx is not None and idx < len(greetings) else ""
        existing_first = card.get("first_mes", "")
        name = card.get("name", "Character")

        prompt = f"""You are writing a SillyTavern character card field.

Task: Write ONE alternate first message (opening greeting) for the character "{name}".
- Write in character, first person, in-character voice
- Make it distinct from the existing first message
- Keep it concise and roleplay-ready (1-4 sentences)
- Do not write actions or dialogue for {{{{user}}}}
- Output valid JSON only: {{"greeting": "..."}}

Existing first message (for reference, make this one different):
{existing_first}

{"Existing greeting to improve:" + chr(10) + existing if existing else "Generate a fresh alternate greeting."}

{"Additional instruction: " + custom_prompt if custom_prompt else ""}

Character card context:
{json.dumps({"name": name, "personality": card.get("personality",""), "scenario": card.get("scenario","")}, ensure_ascii=False)}"""

        result = _gen_request(card["provider"], card["model"], prompt)

        if "greeting" not in result:
            return jsonify({"error": "Generator did not return greeting"}), 500

        # Update card
        if idx is not None and idx < len(greetings):
            greetings[idx] = result["greeting"]
        else:
            greetings.append(result["greeting"])

        card["alternate_greetings"] = greetings
        create_or_update_card(card["source_id"], card, card_id=card_id)

        return jsonify({"greeting": result["greeting"], "idx": idx if idx is not None else len(greetings) - 1})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.post("/api/generate/compile/<int:card_id>")
def api_generate_compile(card_id: int):
    """Compile structured profile fields into description or personality prose."""
    try:
        data = request.get_json(force=True) or {}
        target = data.get("target", "description")  # "description" or "personality"

        card = get_card(card_id)
        sp = card.get("structured_profile") or {}

        if target == "description":
            prompt = f"""You are writing a SillyTavern character card field.

Task: Write a rich, roleplay-ready "description" field for the character "{card.get('name', 'Unknown')}".
Compile it from the structured profile below. Write in third person, present tense.
Focus on physical appearance, clothing, and notable visual traits.
Do not invent facts not present in the profile. Be vivid and concise (150-300 words).
Output valid JSON only: {{"description": "..."}}

Structured profile:
{json.dumps(sp, ensure_ascii=False, indent=2)}

Current description (may be empty or outdated):
{card.get('description', '')}"""

        elif target == "personality":
            prompt = f"""You are writing a SillyTavern character card field.

Task: Write a "personality" summary field for the character "{card.get('name', 'Unknown')}".
Compile it from the structured profile below. Write in third person, present tense.
Focus on personality traits, speech patterns, likes, dislikes, loves, hates.
Make it behavioral and specific — not just a list of adjectives.
Do not invent facts not present in the profile. Be vivid and concise (100-200 words).
Output valid JSON only: {{"personality": "..."}}

Structured profile:
{json.dumps(sp, ensure_ascii=False, indent=2)}

Current personality (may be empty or outdated):
{card.get('personality', '')}"""
        else:
            return jsonify({"error": f"Unknown target: {target}"}), 400

        result = _gen_request(card["provider"], card["model"], prompt)

        if target not in result:
            return jsonify({"error": f"Generator did not return '{target}'"}), 500

        # Save to card
        card[target] = result[target]
        create_or_update_card(card["source_id"], card, card_id=card_id)

        return jsonify({"field": target, "value": result[target]})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.post("/api/generate/field/<int:card_id>")
def regenerate_field(card_id: int):
    # Accept both JSON and form data
    if request.is_json:
        data = request.get_json(force=True) or {}
    else:
        data = request.form

    field_name = data.get("field_name", "")
    custom_prompt = data.get("custom_prompt", "").strip() if hasattr(data, "get") else ""
    include_current_card = str(data.get("include_current_card", "true")).lower() == "true"
    include_source = str(data.get("include_source", "true")).lower() == "true"

    card = get_card(card_id)
    source = get_source(card["source_id"])

    result = regenerate_single_field(
        source=source,
        card=card,
        field_name=field_name,
        provider=card["provider"],
        model=card["model"],
        custom_prompt=custom_prompt,
        include_current_card=include_current_card,
        include_source=include_source,
    )

    # Fields that live at card top-level (not structured_profile)
    NATURAL_FIELDS = {"name", "description", "personality", "scenario",
                      "first_mes", "mes_example", "tags", "depth_prompt", "system_prompt"}

    # All structured profile subfields — accepted as plain names or sp_-prefixed
    SP_SUBFIELDS = {
        "backstory", "appearance", "non_human_appearance", "personal_parts",
        "clothing", "accessories", "speech", "personality_traits", "kinks",
        "likes", "dislikes", "loves", "hates",
        "sex", "ethnicity", "race", "job_occupation", "gender", "sexual_attraction",
        "pronouns", "relationship_to_user", "relationship_status",
        "height", "weight", "age",
        "species", "story_point", "motivations", "flaws", "mannerisms", "relationships",
    }

    # Strip sp_ prefix if present
    resolved_field = field_name[3:] if field_name.startswith("sp_") else field_name
    is_sp = resolved_field in SP_SUBFIELDS

    if field_name in NATURAL_FIELDS or field_name == "structured_profile":
        return jsonify({
            "preview_only": True,
            "field_name": field_name,
            "result": result,
            "current_value": card.get(field_name) if field_name != "structured_profile" else card.get("structured_profile"),
            "new_value": result.get(field_name) if field_name != "structured_profile" else result.get("structured_profile"),
        })

    updated = dict(card)

    if is_sp:
        old_value = json.dumps(card["structured_profile"].get(resolved_field), ensure_ascii=False)
        new_piece = result.get("structured_profile", {}).get(resolved_field)
        if new_piece is None:
            new_piece = result.get(resolved_field)
        if new_piece is None:
            return jsonify({"error": f"Generator did not return a value for '{resolved_field}'"}), 500

        new_value = json.dumps(new_piece, ensure_ascii=False)
        updated_profile = dict(card["structured_profile"])
        updated_profile[resolved_field] = new_piece
        updated["structured_profile"] = updated_profile

        save_field_version(card_id, resolved_field, old_value, new_value)
        create_or_update_card(card["source_id"], updated, card_id=card_id)
        return jsonify({"preview_only": False, "field_name": resolved_field, "result": result})

    if field_name not in result:
        return jsonify({"error": f"Generator did not return a value for '{field_name}'"}), 500

    old_value = card.get(field_name)
    new_value = result[field_name]
    updated.update(result)

    save_field_version(card_id, field_name, old_value, new_value)
    create_or_update_card(card["source_id"], updated, card_id=card_id)
    return jsonify({"preview_only": False, "field_name": field_name, "result": result})


@app.post("/api/export/v2")
def api_export_v2():
    """Build a Character Card V2 object from the card currently in the editor.
    Body: {"card": {...}, "mode": "natural" | "structured"}
    Used by both the JSON download and the PNG chara-chunk embed."""
    try:
        data = request.get_json(force=True) or {}
        card = data.get("card") or {}
        structured = data.get("mode") == "structured"
        out = (build_export_card_v3(card, structured=structured) if data.get("spec") == "v3"
               else build_export_card_json(card, structured=structured))
        lore_id = data.get("lore_project_id")
        if lore_id not in (None, "", 0, "0"):
            book = build_character_book(int(lore_id))
            if book["entries"]:
                out["data"]["character_book"] = book
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- DB viewer ----------
# ---------- React Config API ----------
@app.get("/api/config/prompts")
def api_get_prompts():
    from prompt_templates import get_prompt_templates
    templates = get_prompt_templates()
    config = load_runtime_config()
    # Also load lore template from prompts.json
    templates_path = str(BASE_DIR / "config" / "prompts.json")
    lore_tpl = ""
    if os.path.exists(templates_path):
        try:
            with open(templates_path, "r", encoding="utf-8") as f:
                lore_tpl = json.load(f).get("lore_generation_template", "")
        except Exception:
            pass
    return jsonify({
        **templates,
        "lore_generation_template": lore_tpl,
        "use_templates": config.get("use_templates", False),
        "temperature": config.get("temperature", 0.7),
        "max_tokens": config.get("max_tokens", 4096),
        "extract_max_tokens": config.get("extract_max_tokens", 8000),
    })


@app.post("/api/config/prompts")
def api_save_prompts():
    try:
        data = request.get_json(force=True) or {}
        from prompt_templates import save_prompt_templates
        save_prompt_templates(
            data.get("character_generation_template", ""),
            data.get("field_regeneration_template", ""),
        )
        # Save lore template to prompts.json
        lore_tpl = data.get("lore_generation_template", "")
        templates_path = str(BASE_DIR / "config" / "prompts.json")
        os.makedirs("config", exist_ok=True)
        existing = {}
        if os.path.exists(templates_path):
            try:
                with open(templates_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass
        existing["lore_generation_template"] = lore_tpl
        with open(templates_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        # Save use_templates to settings.json (where generator reads it)
        settings_path = str(BASE_DIR / "config" / "settings.json")
        settings = {}
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
            except Exception:
                pass
        settings["use_templates"] = data.get("use_templates", False)
        settings["temperature"] = float(data.get("temperature", 0.7))
        settings["max_tokens"] = int(data.get("max_tokens", 4096))
        settings["extract_max_tokens"] = max(1024, min(int(data.get("extract_max_tokens", 8000)), 32768))
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


ENV_WRITABLE = (
    "NANOGPT_API_KEY", "OPENROUTER_API_KEY", "NANOGPT_MODEL", "OPENROUTER_MODEL",
    "LOCAL_OPENAI_BASE_URL", "LOCAL_MODEL", "LOCAL_API_KEY",
)


MASK = "\u2022\u2022\u2022\u2022"   # "••••": a saved secret the page never gets back in full


def _is_secret(key):
    return key.endswith("_KEY") or "TOKEN" in key or "SECRET" in key


@app.get("/api/config/env")
def api_get_env():
    """Settings for the Config page. API keys come back masked (last 4 characters), never in full."""
    out = {}
    for key in ENV_WRITABLE:
        val = os.getenv(key, "")
        out[key] = (MASK + val[-4:] if len(val) > 8 else (MASK if val else "")) if _is_secret(key) else val
    return jsonify(out)


@app.post("/api/config/env")
def api_save_env():
    """Update known settings in .env. Only ENV_WRITABLE names are accepted, values can't
    contain line breaks, and comments / other lines in the file are left as they are."""
    try:
        data = request.get_json(force=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Expected a JSON object"}), 400
        updates = {}
        for key, val in data.items():
            if key not in ENV_WRITABLE:
                return jsonify({"error": f"Unknown setting: {key}"}), 400
            val = "" if val is None else str(val)
            if val.startswith(MASK):
                continue                      # the masked placeholder came back unchanged: keep the saved key
            if "\n" in val or "\r" in val or len(val) > 500:
                return jsonify({"error": f"Invalid value for {key}"}), 400
            updates[key] = val.strip()

        lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
        out, seen = [], set()
        for line in lines:
            k = line.partition("=")[0].strip() if ("=" in line and not line.lstrip().startswith("#")) else None
            if k in updates:
                seen.add(k)
                if updates[k]:
                    out.append(f"{k}={updates[k]}")  # empty value -> line dropped
            else:
                out.append(line)
        for k, v in updates.items():
            if k not in seen and v:
                out.append(f"{k}={v}")
        ENV_PATH.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
        load_dotenv(ENV_PATH, override=True)
        for k, v in updates.items():
            if not v:
                os.environ.pop(k, None)
        log_ok("ENV saved and reloaded")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- .env editor ----------
# ── Multi-character cast card ─────────────────────────────────────────────────
def build_cast_card(card_ids, cast_name, provider, model):
    """One card that plays several characters. Saved as a NEW card (it used to overwrite the first member's card)."""
    cards = [get_card(cid) for cid in card_ids]
        # Build a combined prompt
    sep = "=" * 40
    chars_summary = []
    for c in cards:
        sp = c.get("structured_profile", {})
        chars_summary.append(
            f"Name: {c.get('name', 'Unknown')}\n"
            f"Personality: {c.get('personality', '')[:300]}\n"
            f"Description: {c.get('description', '')[:300]}\n"
            f"Scenario: {c.get('scenario', '')[:200]}\n"
            f"Traits: {', '.join(sp.get('personality_traits', [])[:6])}"
        )
    chars_block = f"\n{sep}\n".join(chars_summary)

    prompt = (
        f"You are creating a SillyTavern character card for a CAST of multiple characters.\n"
        f"The AI will play ALL characters in this cast during the same roleplay session.\n\n"
        f"Cast name: {cast_name}\n"
        f"Number of characters: {len(cards)}\n\n"
        f"Characters:\n{sep}\n{chars_block}\n\n"
        f"Write a unified character card where:\n"
        f'- name: the cast name (e.g. "{cast_name}")\n'
        f"- description: introduces each character in third person, their appearance and role\n"
        f"- personality: describes how each character behaves and interacts with each other and {{{{user}}}}\n"
        f"- scenario: a roleplay-ready setup featuring all characters together\n"
        f'- first_mes: an opening message where all characters are present (write each character\'s line as "CharName: ...")\n'
        f"- mes_example: 3 example exchanges showing how the characters interact differently\n"
        f"- tags: tags for the whole cast\n\n"
        f"Output valid JSON only with these keys: name, description, personality, scenario, first_mes, mes_example, tags\n"
    )
    result = _gen_request(provider, model, prompt)

    # Get a source_id from one of the cards
    source_id = cards[0]["source_id"]
    result["provider"] = provider
    result["model"] = model
    result.setdefault("structured_profile", {})
    result.setdefault("tags", [])
    card_id = create_or_update_card(source_id, result, force_new=True)

    return card_id, result


def _card_exists_for_source(source_id):
    conn = get_db_connection()
    row = conn.execute("SELECT 1 FROM cards WHERE source_id = ? LIMIT 1", (source_id,)).fetchone()
    conn.close()
    return row is not None


def run_cast_cards_job(job_id, pid, eids, provider, model, options, group):
    """Cards for several reviewed TEXT characters, one after another, then (optionally) one group card."""
    import text_module as TM
    try:
        made, failed = [], []
        for i, eid in enumerate(eids):
            src = TM.entity_to_source(eid)
            if src is None:
                failed.append({"id": eid, "error": "character not found"})
                continue
            name = src["source"].get("title") or f"#{eid}"
            update_job(job_id, status="running", stage="requesting_model", progress=int(5 + 85 * i / max(1, len(eids))),
                       message=f"Card {i + 1}/{len(eids)}: {name}...")
            try:
                opts = {**options, "story_point": options.get("story_point") or src["story_point"]}
                if src.get("lore_project_id"):
                    opts["lore_aware"] = True
                generated = generate_full_card(src["source"], provider, model, opts)
                generated.pop("_warnings", None)
                generated["provider"], generated["model"] = provider, model
                # a card made earlier for this character (maybe hand-edited) is kept: save a new one beside it
                cid = create_or_update_card(src["source_id"], generated,
                                            force_new=_card_exists_for_source(src["source_id"]))
                made.append({"card_id": cid, "name": generated.get("name") or name})
                log_ok(f"cast cards: {name} -> card {cid}")
            except Exception as ex:
                failed.append({"id": eid, "name": name, "error": str(ex)[:200]})
                log_warn(f"cast cards: {name} failed: {ex}")
        group_id = None
        if group and len(made) >= 2:
            update_job(job_id, stage="requesting_model", progress=92, message="Writing the group card...")
            r = TM._project_row(pid)
            try:
                group_id, _ = build_cast_card([m["card_id"] for m in made[:6]], f"{r['name']} Cast" if r else "Cast",
                                              provider, model)
            except Exception as ex:
                failed.append({"name": "group card", "error": str(ex)[:200]})
        update_job(job_id, status="done", stage="done", progress=100,
                   message=f"{len(made)} card(s) made" + (", plus a group card" if group_id else "")
                           + (f"; {len(failed)} failed" if failed else ""),
                   result={"cards": made, "group_card_id": group_id, "failed": failed})
    except Exception as e:
        update_job(job_id, status="failed", stage="failed", error=str(e), message=str(e))


@app.post("/api/text/project/<int:pid>/cast-cards")
def api_text_cast_cards(pid):
    """Body: {provider, model, ids?: [entity ids] (default: the kept MAIN characters, up to 8), group?: bool,
    token_target?, style?, user_role?, deep?}. Starts a job; poll /api/job/<id>."""
    import text_module as TM
    if TM._project_row(pid) is None:
        return jsonify({"error": "Not found"}), 404
    data = request.get_json(force=True) or {}
    eids = [int(x) for x in (data.get("ids") or [e["id"] for e in TM.main_cast(pid)])][:8]
    if not eids:
        return jsonify({"error": "No kept main characters. Keep some characters (main tier) or pick them."}), 400
    provider = data.get("provider") or "nanogpt"
    model = data.get("model") or ""
    options = {k: data.get(k) for k in ("user_role", "token_target", "style", "deep", "story_point") if data.get(k)}
    job_id = create_job()
    threading.Thread(target=run_cast_cards_job,
                     args=(job_id, pid, eids, provider, model, options, bool(data.get("group"))), daemon=True).start()
    return jsonify({"job_id": job_id, "count": len(eids)})


@app.post("/api/generate/cast")
def api_generate_cast():
    """Generate a single combined card with multiple characters as a cast."""
    try:
        data = request.get_json(force=True) or {}
        card_ids = data.get("card_ids", [])
        cast_name = data.get("cast_name", "Cast Card").strip()
        provider = data.get("provider", "nanogpt")
        model = data.get("model", "")

        if not card_ids or len(card_ids) < 2:
            return jsonify({"error": "Select at least 2 cards"}), 400
        if len(card_ids) > 6:
            return jsonify({"error": "Maximum 6 characters per cast card"}), 400

        card_id, result = build_cast_card(card_ids, cast_name, provider, model)
        log_ok(f"Cast card generated: {cast_name} ({len(card_ids)} chars) → id={card_id}")
        return jsonify({"card_id": card_id, "card": result})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Image proxy ──────────────────────────────────────────────────────────────
def _is_public_host(host: str) -> bool:
    """True only if every address the name resolves to is a normal public one."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False
    return bool(infos)


@app.get("/api/image-proxy")
def api_image_proxy():
    """Proxy an external image so the frontend can load cross-origin images.
    Public http(s) hosts only (no localhost / LAN / metadata addresses), images only, 10 MB max."""
    import requests as req
    img_url = request.args.get("url", "").strip()
    try:
        for _hop in range(4):  # follow redirects by hand so every hop is re-checked
            u = urlsplit(img_url)
            if u.scheme not in ("http", "https") or not u.hostname or not _is_public_host(u.hostname):
                return jsonify({"error": "URL not allowed"}), 400
            r = req.get(img_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"},
                        stream=True, allow_redirects=False)
            if r.is_redirect and r.headers.get("Location"):
                img_url = urljoin(img_url, r.headers["Location"])
                r.close()
                continue
            break
        else:
            return jsonify({"error": "Too many redirects"}), 400
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if not content_type.startswith("image/"):
            return jsonify({"error": "Not an image"}), 400
        body, size = [], 0
        for chunk in r.iter_content(65536):
            size += len(chunk)
            if size > 10 * 1024 * 1024:
                return jsonify({"error": "Image too large"}), 400
            body.append(chunk)
        resp = send_file(io.BytesIO(b"".join(body)), mimetype=content_type)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
        return resp
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import logging
    port = int(os.getenv("PORT", 5000))
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.WARNING)
    print(f"[OK] Flask running on http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
