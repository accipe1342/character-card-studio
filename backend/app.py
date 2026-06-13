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

API ROUTES — LORE
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
GET    /api/lore/export/<crawl_id>  Export lorebook as SillyTavern JSON

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
import json
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
import logging
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
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
    list_lore_projects,
    rename_lore_project,
    delete_lore_project,
    create_lore_project,
    # 👇 ADD THESE
    save_lore_entry,
    create_lore_crawl,
    update_lore_crawl_status,
    save_lore_crawl_page,
)

from generator import (
    generate_full_card,
    regenerate_single_field,
    generate_lore_entry,
    _request as _gen_request,
    _ensure_list,
    load_runtime_config,
)
from preview import build_export_card_json, format_structured_profile_text
from scraper import scrape_url
import threading
import uuid

# Ensure UTF-8 output on Windows
import sys, io
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
    if job_id in JOBS:
        JOBS[job_id].update(kwargs)


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


def run_generate_job(job_id: str, source_id: int, provider: str, model: str):
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

        generated = generate_full_card(source, provider, model)
        log_dim("  model responded")

        generated["provider"] = provider
        generated["model"] = model

        update_job(
            job_id,
            stage="saving_card",
            progress=90,
            message="Parsing and saving character card...",
        )

        card_id = create_or_update_card(source_id, generated)
        log_dim(f"  card saved  id={card_id}")

        update_job(
            job_id,
            status="done",
            stage="done",
            progress=100,
            message="Character card ready.",
            result={
                "card_id": card_id,
                "card": generated,
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
@app.get("/")
def index():
    cards = list_cards()
    return render_template("index.html", cards=cards)


@app.get("/library")
def library():
    cards = list_cards()
    return render_template("library.html", cards=cards)


from prompt_templates import get_prompt_templates


@app.get("/config")
def config_page():
    config = load_config()
    prompts = get_prompt_templates()
    return render_template("config.html", config=config, prompts=prompts)


from prompt_templates import save_prompt_templates


@app.post("/config")
def save_config_route():
    use_templates = request.form.get("use_templates") == "true"

    character_generation_template = request.form.get(
        "character_generation_template", ""
    ).strip()
    field_regeneration_template = request.form.get(
        "field_regeneration_template", ""
    ).strip()

    # save toggle
    config = {"use_templates": use_templates}
    save_config(config)

    # save templates
    save_prompt_templates(character_generation_template, field_regeneration_template)

    return redirect(url_for("config_page"))


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
        model = data.get("model") or os.getenv("NANOGPT_MODEL", "zai-org/glm-4.7:thinking")

        if not source_id:
            return jsonify({"error": "Missing source_id"}), 400

        job_id = create_job()
        threading.Thread(
            target=run_generate_job,
            args=(job_id, source_id, provider, model),
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

                    generated = generate_full_card(source, provider, model)
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


@app.post("/api/lore/multi")
def api_lore_multi():
    """Generate lorebook entries from multiple URLs."""
    try:
        data = request.get_json(force=True) or {}
        urls = [u.strip() for u in data.get("urls", []) if u.strip()]
        provider = data.get("provider", "nanogpt")
        model = data.get("model", "")
        project_id = data.get("project_id")

        if not urls:
            return jsonify({"error": "No URLs provided"}), 400

        job_id = create_job()

        def run():
            try:
                total_saved = 0
                for i, url in enumerate(urls):
                    pct = int((i / len(urls)) * 85)
                    update_job(job_id, status="running", stage="fetching_page", progress=pct,
                               message=f"Processing {i+1}/{len(urls)}: {url.split('/')[-1]}...")

                    try:
                        from scraper import scrape_url
                        source = scrape_url(url)
                        source_id = save_source(source)
                        raw_text = source.get("raw_text") or source.get("content") or ""
                        title = source.get("title") or url

                        update_job(job_id, status="running", stage="requesting_model", progress=pct + 5,
                                   message=f"Generating entries for: {title}...")

                        lore_result = generate_lore_entry(source, provider, model)

                        if not lore_result.get("valid", True):
                            log_warn(f"  Skipped: {lore_result.get('reason', 'not valid')}")
                            continue

                        entries_data = lore_result.get("entries", [])
                        for entry in entries_data:
                            if not isinstance(entry, dict): continue
                            save_lore_entry(
                                crawl_id=project_id,
                                source_id=source_id,
                                title=entry.get("title", title),
                                entry_type=entry.get("entry_type", "concept"),
                                keywords=entry.get("keywords", []),
                                summary=entry.get("summary", entry.get("content", ""))[:200],
                                content=entry.get("content", ""),
                                provider=provider,
                                model=model,
                            )
                            total_saved += 1
                            log_dim(f"  [{total_saved}] {entry.get('entry_type','?').upper():10} {entry.get('title','')}")

                        log_ok(f"Page {i+1}/{len(urls)}: {len(entries_data)} entries from {title}")

                    except Exception as page_err:
                        log_warn(f"Failed to process {url}: {page_err}")

                update_job(job_id, status="done", stage="done", progress=100,
                           message=f"{total_saved} entries from {len(urls)} pages!")
                log_ok(f"Multi-page lore complete: {total_saved} entries from {len(urls)} pages")

            except Exception as e:
                import traceback; traceback.print_exc()
                update_job(job_id, status="failed", stage="failed", progress=100, message=str(e), error=str(e))

        import threading
        threading.Thread(target=run, daemon=True).start()
        return jsonify({"job_id": job_id})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/lore/single")
def api_lore_single():
    """Generate a single lorebook entry from one page."""
    try:
        data = request.get_json(force=True) or {}
        url = data.get("url", "").strip()
        provider = data.get("provider", "nanogpt")
        model = data.get("model", "")
        project_id = data.get("project_id")

        if not url:
            return jsonify({"error": "Missing url"}), 400

        job_id = create_job()

        def run():
            try:
                update_job(job_id, status="running", stage="fetching_page", progress=10, message="Fetching wiki page...")
                from scraper import scrape_url
                source = scrape_url(url)
                source_id = save_source(source)
                title = source.get("title") or url

                update_job(job_id, status="running", stage="building_prompt", progress=40, message=f"Preparing lore generation for: {title}...")
                raw_text = source.get("raw_text") or source.get("content") or ""

                from database import save_lore_entry

                update_job(job_id, status="running", stage="requesting_model", progress=50, message=f"Generating lore entries via {provider}/{model or 'default'}...")

                lore_result = generate_lore_entry(source, provider, model)

                if not lore_result.get("valid", True):
                    reason = lore_result.get("reason", "Page did not meet criteria")
                    update_job(job_id, status="done", stage="done", progress=100,
                               message=f"Skipped: {reason}")
                    log_warn(f"Single page lore skipped: {reason}")
                    return

                entries_data = lore_result.get("entries", [])
                log_info(f"Model returned {len(entries_data)} entries for '{title}'")

                update_job(job_id, status="running", stage="saving_card", progress=90,
                           message=f"Saving {len(entries_data)} entries...")
                saved = 0
                for entry in entries_data:
                    if not isinstance(entry, dict): continue
                    save_lore_entry(
                        crawl_id=project_id,
                        source_id=source_id,
                        title=entry.get("title", title),
                        entry_type=entry.get("entry_type", "concept"),
                        keywords=entry.get("keywords", []),
                        summary=entry.get("summary", entry.get("content", ""))[:200],
                        content=entry.get("content", ""),
                        provider=provider,
                        model=model,
                    )
                    saved += 1
                    log_dim(f"  [{saved}] {entry.get('entry_type','?').upper():10} {entry.get('title','')}")

                update_job(job_id, status="done", stage="done", progress=100,
                           message=f"{saved} entries created!")
                log_ok(f"Single page lore  {saved} entries  source={title}")

            except Exception as e:
                import traceback; traceback.print_exc()
                update_job(job_id, status="failed", stage="failed", progress=100, message=str(e), error=str(e))

        import threading
        threading.Thread(target=run, daemon=True).start()
        return jsonify({"job_id": job_id})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/lore/crawl/start")
def api_lore_crawl_start():
    try:
        data = request.get_json(force=True) or {}

        seed_url = data.get("seed_url", "").strip()
        max_pages = int(data.get("max_pages", 10))
        max_depth = int(data.get("max_depth", 1))
        provider = data.get("provider", "nanogpt")
        model = data.get("model", "")
        purpose = data.get("purpose", "Create a general lorebook")
        criteria = data.get("criteria", "Must be a meaningful lore page")
        extraction_notes = data.get(
            "extraction_notes",
            "Focus on relationships and worldbuilding context",
        )
        if not seed_url:
            return jsonify({"error": "Missing seed_url"}), 400

        job_id = create_job()

        threading.Thread(
            target=run_lore_crawl_job,
            args=(
                job_id,
                seed_url,
                max_pages,
                max_depth,
                provider,
                model,
                purpose,
                criteria,
                extraction_notes,
            ),
            daemon=True,
        ).start()

        return jsonify({"job_id": job_id})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/lore/projects")
def api_list_lore_projects():
    try:
        from database import list_lore_projects
        return jsonify(list_lore_projects())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/lore/projects")
def api_create_lore_project():
    try:
        data = request.get_json(force=True) or {}
        name = data.get("name", "Untitled Project").strip()
        from database import create_lore_project
        pid = create_lore_project(name)
        return jsonify({"id": pid, "project_name": name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.patch("/api/lore/project/<int:project_id>/name")
def api_rename_lore_project(project_id):
    try:
        data = request.get_json(force=True) or {}
        from database import rename_lore_project
        rename_lore_project(project_id, data.get("name", "Untitled Project"))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.delete("/api/lore/project/<int:project_id>")
def api_delete_lore_project(project_id):
    try:
        from database import delete_lore_project
        delete_lore_project(project_id)
        log_ok(f"Lore project deleted id={project_id}")
        return jsonify({"deleted": project_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/lore/entries")
def api_list_lore_entries():
    try:
        from database import list_lore_entries
        project_id = request.args.get("project_id", type=int)
        entries = list_lore_entries()
        if project_id is not None:
            entries = [e for e in entries if e.get("crawl_id") == project_id]
        return jsonify(entries)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/lore/entry/new")
def api_new_lore_entry():
    try:
        data = request.get_json(force=True) or {}
        project_id = data.get("project_id")
        title = data.get("title", "New Entry").strip()

        # Get any existing source_id, or create a placeholder source
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM sources LIMIT 1")
        row = cur.fetchone()
        source_id = row[0] if row else None
        conn.close()

        if not source_id:
            # Create a minimal placeholder source so we can save the entry
            from database import save_source
            source_id = save_source({
                "wiki_base": "manual",
                "page_name": "manual",
                "url": f"manual://entry/{title}",
                "title": title,
                "raw_html": "",
                "raw_infobox": {},
                "raw_sections": {},
                "normalized": {},
            })

        lore_id = save_lore_entry(
            crawl_id=project_id,
            source_id=source_id,
            title=title,
            entry_type="concept",
            keywords=[],
            summary="",
            content="",
            provider="nanogpt",
            model="",
        )
        return jsonify({"id": lore_id, "title": title})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/api/lore/entry/generate")
def api_generate_lore_entry():
    """Generate a single lore entry from a prompt/text snippet."""
    try:
        data = request.get_json(force=True) or {}
        prompt_text = data.get("prompt", "").strip()
        title = data.get("title", "").strip()
        entry_type = data.get("entry_type", "concept")
        provider = data.get("provider", "nanogpt")
        model = data.get("model", "")
        project_id = data.get("project_id")

        if not prompt_text:
            return jsonify({"error": "No prompt provided"}), 400

        # Build a minimal source dict for the unified generator
        manual_source = {
            "url": f"manual://prompt/{title or 'entry'}",
            "title": title or "Manual Entry",
            "normalized": {
                "title": title or "",
                "summary": prompt_text[:500],
            },
            "raw_text": prompt_text,
        }
        lore_result = generate_lore_entry(
            manual_source, provider, model,
            purpose=f"Generate a lorebook entry about: {title or 'the described subject'}",
            criteria=f"The content must describe a {entry_type} in enough detail to create a useful lorebook entry.",
            extraction_notes="Extract core facts, relationships, and key attributes.",
        )
        entries = lore_result.get("entries", [])
        result = entries[0] if entries else {"title": title or "New Entry", "entry_type": entry_type, "keywords": [], "content": prompt_text[:300]}
        result["keywords"] = _ensure_list(result.get("keywords", []))

        # Optionally save it
        if project_id is not None or data.get("save"):
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT id FROM sources LIMIT 1")
            row = cur.fetchone()
            source_id = row[0] if row else None
            conn.close()

            if source_id:
                lore_id = save_lore_entry(
                    crawl_id=project_id,
                    source_id=source_id,
                    title=result.get("title", title or "New Entry"),
                    entry_type=result.get("entry_type", entry_type),
                    keywords=result.get("keywords", []),
                    summary=result.get("content", "")[:200],
                    content=result.get("content", ""),
                    provider=provider,
                    model=model,
                )
                result["id"] = lore_id

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/lore/entry/<int:lore_id>")
def api_get_lore_entry(lore_id):
    try:
        from database import get_lore_entry
        return jsonify(get_lore_entry(lore_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.patch("/api/lore/entry/<int:lore_id>")
def api_update_lore_entry(lore_id):
    try:
        data = request.get_json(force=True) or {}
        conn = get_db_connection()
        conn.execute(
            """UPDATE lore_entries SET
               title = ?, keywords_json = ?, content = ?, summary = ?,
               scan_depth = ?, insertion_order = ?, entry_depth = ?,
               updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (
                data.get("title", ""),
                json.dumps(data.get("keywords", []), ensure_ascii=False),
                data.get("content", ""),
                data.get("summary", ""),
                int(data.get("scan_depth", 2)),
                int(data.get("insertion_order", 100)),
                int(data.get("entry_depth", 4)),
                lore_id,
            )
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.delete("/api/lore/entry/<int:lore_id>")
def api_delete_lore_entry(lore_id):
    try:
        conn = get_db_connection()
        conn.execute("DELETE FROM lore_entries WHERE id = ?", (lore_id,))
        conn.commit()
        conn.close()
        return jsonify({"deleted": lore_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/lore/export")
def api_export_lorebook():
    try:
        from database import list_lore_entries, get_lore_entry
        entries = list_lore_entries()
        # Build SillyTavern V2 lorebook format
        lorebook = {
            "spec": "lorebook_v2",
            "spec_version": "2",
            "entries": {}
        }
        for i, e in enumerate(entries):
            full = get_lore_entry(e["id"])
            lorebook["entries"][str(i)] = {
                "id": i,
                "keys": full.get("keywords", []),
                "secondary_keys": [],
                "comment": full.get("title", ""),
                "content": full.get("content", ""),
                "constant": False,
                "selective": False,
                "insertion_order": int(full.get("insertion_order", 100)),
                "enabled": True,
                "position": "after_char",
                "use_regex": False,
                "scan_depth": int(full.get("scan_depth", 2)),
                "depth": int(full.get("entry_depth", 4)),
                "extensions": {
                    "source_title": e.get("source_title", ""),
                    "entry_type": e.get("entry_type", ""),
                }
            }
        return jsonify(lorebook)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.patch("/api/lore/entry/<int:lore_id>/project")
def api_move_lore_entry(lore_id):
    """Move a lore entry to a different project (or unassign)."""
    try:
        data = request.get_json(force=True) or {}
        project_id = data.get("project_id")  # None = unassign
        conn = get_db_connection()
        conn.execute(
            "UPDATE lore_entries SET crawl_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (project_id, lore_id)
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "project_id": project_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/job/<job_id>")
def api_job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


# ---------- Scrape / cards ----------
@app.post("/scrape")
def scrape():
    wiki_base = request.form["wiki_base"].strip().rstrip("/")
    page_name = request.form["page_name"].strip()
    provider = request.form.get("provider", "nanogpt").strip() or "nanogpt"
    model = request.form.get("model", "").strip() or os.getenv(
        "NANOGPT_MODEL", "zai-org/glm-4.7:thinking"
    )

    source = scrape_url(f"{wiki_base}/{page_name}")
    source_id = save_source(source)
    card_id = create_or_update_card(
        source_id,
        {
            "name": source["title"],
            "provider": provider,
            "model": model,
        },
    )
    return redirect(url_for("editor", card_id=card_id))


# ---------- React Scrap ----------
@app.get("/api/test")
def api_test():
    return jsonify({"ok": True})


from urllib.parse import unquote


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

        generated = generate_full_card(source, provider, model)
        generated["provider"] = provider
        generated["model"] = model

        card_id = create_or_update_card(source_id, generated)

        return jsonify({"card_id": card_id, "card": generated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/card/<int:card_id>")
def editor(card_id: int):
    card = get_card(card_id)
    source = get_source(card["source_id"])
    preview_text = format_structured_profile_text(
        card["name"], card["structured_profile"]
    )
    export_json = build_export_card_json(card)
    return render_template(
        "editor.html",
        card=card,
        source=source,
        preview_text=preview_text,
        export_json=json.dumps(export_json, ensure_ascii=False, indent=2),
    )


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


@app.post("/generate/full/<int:card_id>")
def generate_full(card_id: int):
    card = get_card(card_id)
    source = get_source(card["source_id"])
    generated = generate_full_card(source, card["provider"], card["model"])
    generated["provider"] = card["provider"]
    generated["model"] = card["model"]
    create_or_update_card(card["source_id"], generated, card_id=card_id)
    return redirect(url_for("editor", card_id=card_id))


@app.post("/api/generate/full/<int:card_id>")
def api_generate_full(card_id: int):
    try:
        card = get_card(card_id)
        source = get_source(card["source_id"])

        generated = generate_full_card(source, card["provider"], card["model"])
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
                      "first_mes", "mes_example", "tags"}

    # All structured profile subfields — accepted as plain names or sp_-prefixed
    SP_SUBFIELDS = {
        "backstory", "appearance", "non_human_appearance", "personal_parts",
        "clothing", "accessories", "speech", "personality_traits", "kinks",
        "likes", "dislikes", "loves", "hates",
        "sex", "ethnicity", "race", "job_occupation", "gender", "sexual_attraction",
        "pronouns", "relationship_to_user", "relationship_status",
        "height", "weight", "age",
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


@app.post("/apply-preview/<int:card_id>")
def apply_preview(card_id: int):
    payload = request.get_json(force=True)
    field_name = payload["field_name"]
    result = payload["result"]

    card = get_card(card_id)
    updated = dict(card)

    if field_name == "structured_profile":
        old_value = json.dumps(card.get("structured_profile"), ensure_ascii=False)
        new_value = json.dumps(result["structured_profile"], ensure_ascii=False)
        updated["structured_profile"] = result["structured_profile"]
    else:
        old_value = card.get(field_name)
        new_value = result[field_name]
        updated.update(result)

    save_field_version(card_id, field_name, old_value, new_value)
    create_or_update_card(card["source_id"], updated, card_id=card_id)

    return jsonify({"status": "ok"})


@app.post("/save/<int:card_id>")
def save_card(card_id: int):
    payload = request.get_json(force=True)
    card = get_card(card_id)
    payload["provider"] = card["provider"]
    payload["model"] = card["model"]
    create_or_update_card(card["source_id"], payload, card_id=card_id)
    return jsonify({"status": "ok"})


@app.get("/export/<int:card_id>")
def export(card_id: int):
    card = get_card(card_id)
    export_json = build_export_card_json(card)
    bio = io.BytesIO(
        json.dumps(export_json, ensure_ascii=False, indent=2).encode("utf-8")
    )
    filename = f"{card['name']}.card.json".replace("/", "-")
    return send_file(
        bio, mimetype="application/json", as_attachment=True, download_name=filename
    )


# ---------- DB viewer ----------
@app.get("/db")
def db_home():
    tables = [
        {"name": name, "count": get_table_count(name)} for name in get_table_names()
    ]
    return render_template("db/home.html", tables=tables)


@app.get("/db/<table_name>")
def db_table(table_name: str):
    columns, rows = get_table_rows(table_name)
    return render_template(
        "db/table.html", table_name=table_name, columns=columns, rows=rows
    )


@app.get("/db/card/<int:card_id>")
def db_card_detail(card_id: int):
    card = get_card(card_id)
    return render_template("db/card_detail.html", card=card)


@app.get("/db/source/<int:source_id>")
def db_source_detail(source_id: int):
    source = get_source(source_id)
    return render_template("db/source_detail.html", source=source)


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
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/config/env")
def api_get_env():
    keys = {}
    for key in ["NANOGPT_API_KEY", "OPENROUTER_API_KEY", "NANOGPT_MODEL", "OPENROUTER_MODEL"]:
        val = os.getenv(key, "")
        keys[key] = val
    return jsonify(keys)


@app.post("/api/config/env")
def api_save_env():
    try:
        data = request.get_json(force=True) or {}
        # Read existing .env
        env_lines = {}
        if ENV_PATH.exists():
            for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    env_lines[k.strip()] = v.strip()
        # Update with new values
        for key, val in data.items():
            if val:
                env_lines[key] = val
            elif key in env_lines:
                del env_lines[key]
        # Write back
        new_content = "\n".join(f"{k}={v}" for k, v in env_lines.items()) + "\n"
        ENV_PATH.write_text(new_content, encoding="utf-8")
        load_dotenv(ENV_PATH, override=True)
        log_ok("ENV saved and reloaded")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- .env editor ----------
@app.get("/env")
def env_editor():
    env_data = ""
    if ENV_PATH.exists():
        env_data = ENV_PATH.read_text(encoding="utf-8")
    return render_template("env_editor.html", env_data=env_data)


@app.post("/env")
def save_env():
    content = request.form.get("env_content", "")
    ENV_PATH.write_text(content.strip() + "\n", encoding="utf-8")
    load_dotenv(ENV_PATH, override=True)
    return redirect(url_for("env_editor"))




# ── Multi-character cast card ─────────────────────────────────────────────────
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
        card_id = create_or_update_card(source_id, result)

        log_ok(f"Cast card generated: {cast_name} ({len(cards)} chars) → id={card_id}")
        return jsonify({"card_id": card_id, "card": result})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ── Image proxy ──────────────────────────────────────────────────────────────
@app.get("/api/image-proxy")
def api_image_proxy():
    """Proxy an external image URL so the frontend can load cross-origin images."""
    import requests as req
    img_url = request.args.get("url", "").strip()
    if not img_url or not img_url.startswith("http"):
        return jsonify({"error": "Invalid URL"}), 400
    try:
        r = req.get(img_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
        r.raise_for_status()
        content_type = r.headers.get("Content-Type", "image/jpeg")
        return send_file(
            io.BytesIO(r.content),
            mimetype=content_type,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import logging
    port = int(os.getenv("PORT", 5000))
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.WARNING)
    print(f"[OK] Flask running on http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
