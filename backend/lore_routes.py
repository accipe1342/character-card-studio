"""
lore_routes.py — the LORE studio's routes (moved out of app.py)
===============================================================

POST   /api/lore/multi | /api/lore/single | /api/lore/crawl/start     generation jobs from wiki URLs
GET    /api/lore/projects                 POST /api/lore/projects     list / create projects
PATCH  /api/lore/project/<id>/name        DELETE /api/lore/project/<id>
GET    /api/lore/entries[?project_id=N]   POST /api/lore/entry/new    POST /api/lore/entry/generate
GET    /api/lore/entry/<id>               PATCH /api/lore/entry/<id>  (text + World Info fields)
DELETE /api/lore/project/<id>/entries     (to the trash)              POST /api/lore/project/<id>/clean-keywords
GET    /api/lore/export[?project_id=N]    SillyTavern World Info JSON
GET    /api/lore/export/deeplore          DeepLore (Obsidian) zip
PATCH  /api/lore/entry/<id>/project       move an entry

The simulator, links graph and trash live in lore_tools.py. App-level helpers (jobs, logging, the crawl worker)
are handed over by register_lore_routes(app, **helpers), so this module never imports app.py.
"""

import json
import threading

from flask import Blueprint, jsonify, request

from database import save_lore_entry, save_source
from generator import _ensure_list, generate_lore_entry
from lore_tools import lorebook_entries
from preview import character_book_from_items, world_info_book

bp = Blueprint("lore", __name__)

# set by register_lore_routes()
create_job = update_job = get_db_connection = run_lore_crawl_job = None
log_info = log_ok = log_warn = log_dim = print


@bp.post("/api/lore/multi")
def api_lore_multi():
    """Generate lorebook entries from multiple URLs."""
    try:
        data = request.get_json(force=True) or {}
        urls = [u.strip() for u in data.get("urls", []) if u.strip()]
        provider = data.get("provider", "nanogpt")
        model = data.get("model", "")
        project_id = data.get("project_id")
        deep = bool(data.get("deep"))

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

                        lore_result = generate_lore_entry(source, provider, model, deep=deep)

                        if not lore_result.get("valid", True):
                            reason = lore_result.get("reason", "not valid")
                            short = reason[:80] + "..." if len(reason) > 80 else reason
                            log_warn(f"  Skipped [{title}]: {short}")
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


@bp.post("/api/lore/single")
def api_lore_single():
    """Generate a single lorebook entry from one page."""
    try:
        data = request.get_json(force=True) or {}
        url = data.get("url", "").strip()
        provider = data.get("provider", "nanogpt")
        model = data.get("model", "")
        project_id = data.get("project_id")
        deep = bool(data.get("deep"))

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

                lore_result = generate_lore_entry(source, provider, model, deep=deep)

                if not lore_result.get("valid", True):
                    reason = lore_result.get("reason", "Page did not meet criteria")
                    # Truncate long model-generated reasons for the status bar
                    short_reason = reason[:80] + "..." if len(reason) > 80 else reason
                    update_job(job_id, status="done", stage="done", progress=100,
                               message=f"Skipped: {short_reason}")
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


@bp.post("/api/lore/crawl/start")
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


@bp.get("/api/lore/projects")
def api_list_lore_projects():
    try:
        from database import list_lore_projects
        return jsonify(list_lore_projects())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.post("/api/lore/projects")
def api_create_lore_project():
    try:
        data = request.get_json(force=True) or {}
        name = data.get("name", "Untitled Project").strip()
        from database import create_lore_project
        pid = create_lore_project(name)
        return jsonify({"id": pid, "project_name": name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.patch("/api/lore/project/<int:project_id>/name")
def api_rename_lore_project(project_id):
    try:
        data = request.get_json(force=True) or {}
        from database import rename_lore_project
        rename_lore_project(project_id, data.get("name", "Untitled Project"))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.delete("/api/lore/project/<int:project_id>")
def api_delete_lore_project(project_id):
    try:
        from database import delete_lore_project
        delete_lore_project(project_id)
        log_ok(f"Lore project deleted id={project_id}")
        return jsonify({"deleted": project_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.get("/api/lore/entries")
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


@bp.post("/api/lore/entry/new")
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


@bp.post("/api/lore/entry/generate")
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


@bp.get("/api/lore/entry/<int:lore_id>")
def api_get_lore_entry(lore_id):
    try:
        from database import get_lore_entry
        return jsonify(get_lore_entry(lore_id))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _clean_wi(data):
    """The World Info fields a PATCH may carry, validated. None (or "") for an int field = back to the default."""
    out = {}

    def opt(key, lo, hi):
        if key not in data:
            return
        v = data[key]
        if v is None or v == "":
            out[key] = None
            return
        try:
            out[key] = max(lo, min(hi, int(v)))
        except (TypeError, ValueError):
            pass
    opt("position", 0, 7)
    opt("role", 0, 2)
    opt("probability", 0, 100)
    opt("sticky", 0, 1000)
    opt("cooldown", 0, 1000)
    opt("delay", 0, 1000)
    opt("selective_logic", 0, 3)
    opt("group_weight", 1, 1000)
    if "constant" in data:
        out["constant"] = None if data["constant"] is None else (1 if data["constant"] else 0)
    for k in ("group_prioritize", "vectorized"):
        if k in data:
            out[k] = 1 if data[k] else 0
    if "group_name" in data:
        out["group_name"] = str(data.get("group_name") or "").strip()[:100]
    for k in ("secondary_keys", "char_filter"):
        if k in data and isinstance(data[k], list):
            out[k] = [str(x)[:100] for x in data[k]][:50]
    return out


@bp.patch("/api/lore/entry/<int:lore_id>")
def api_update_lore_entry(lore_id):
    try:
        data = request.get_json(force=True) or {}
        conn = get_db_connection()
        new_order = int(data.get("insertion_order", 100))
        prev = conn.execute("SELECT order_manual FROM lore_entries WHERE id = ?", (lore_id,)).fetchone()
        before = conn.execute("SELECT title, content, keywords_json FROM lore_entries WHERE id = ?", (lore_id,)).fetchone()
        if before is None:
            conn.close()
            return jsonify({"error": "Lore entry not found"}), 404
        order_manual = 1 if (new_order != 100 or (prev and prev[0])) else 0
        conn.execute(
            """UPDATE lore_entries SET
               title = ?, keywords_json = ?, content = ?, summary = ?,
               scan_depth = ?, insertion_order = ?, entry_depth = ?, order_manual = ?,
               updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (
                data.get("title", ""),
                json.dumps(data.get("keywords", []), ensure_ascii=False),
                data.get("content", ""),
                data.get("summary", ""),
                int(data.get("scan_depth", 2)),
                new_order,
                int(data.get("entry_depth", 4)),
                order_manual,
                lore_id,
            )
        )
        if data.get("entry_type"):   # the type buttons in the editor were never saved before
            conn.execute("UPDATE lore_entries SET entry_type = ? WHERE id = ?", (str(data["entry_type"]), lore_id))
        # a hand edit of the text marks the entry, so re-sending from TEXT keeps it
        if before and (before["title"] != data.get("title", "") or (before["content"] or "") != data.get("content", "")
                       or json.loads(before["keywords_json"] or "[]") != list(data.get("keywords", []))):
            conn.execute("UPDATE lore_entries SET user_edited = 1 WHERE id = ?", (lore_id,))
        conn.commit()
        conn.close()
        wi = _clean_wi(data)
        if wi:
            from database import set_lore_wi_fields
            set_lore_wi_fields(lore_id, wi)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.delete("/api/lore/project/<int:project_id>/entries")
def api_clear_lore_project(project_id):
    """Empty a project but keep it (and its id, which TEXT projects and card lorebook attachments point at).
    The entries go to the trash."""
    try:
        conn = get_db_connection()
        # to the trash, so a mistaken clear can be undone from the LORE trash
        n = conn.execute("UPDATE lore_entries SET deleted = 1, updated_at = CURRENT_TIMESTAMP "
                         "WHERE crawl_id = ? AND COALESCE(deleted, 0) = 0", (project_id,)).rowcount
        conn.commit()
        conn.close()
        return jsonify({"deleted": n})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.post("/api/lore/project/<int:project_id>/clean-keywords")
def api_clean_lore_keywords(project_id):
    """Remove generic trigger words and other entries' names from each entry's keywords (same rules as the TEXT
    studio's send). Body {"apply": false} previews the changes; {"apply": true} saves them."""
    try:
        from database import list_lore_entries, get_lore_entry
        from text_module import clean_keywords, norm_name
        apply = bool((request.get_json(force=True) or {}).get("apply"))
        ents = []
        for e in list_lore_entries(crawl_id=project_id):
            full = get_lore_entry(e["id"])
            kws = full.get("keywords") or []
            if isinstance(kws, str):
                try:
                    kws = json.loads(kws)
                except Exception:
                    kws = [kws]
            ents.append({"id": full["id"], "name": full.get("title", ""), "aliases": [], "keywords": kws})
        owners = {}
        for e in ents:
            owners.setdefault(norm_name(e["name"]), e["id"])
        changes = []
        for e in ents:
            if e["name"] in ("Story So Far", "Story Timeline"):
                continue
            new = clean_keywords(e, owners)
            if [k.lower() for k in new] != [k.lower() for k in e["keywords"]]:
                changes.append({"id": e["id"], "title": e["name"], "before": e["keywords"], "after": new})
        if apply and changes:
            conn = get_db_connection()
            for c in changes:
                conn.execute("UPDATE lore_entries SET keywords_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                             (json.dumps(c["after"], ensure_ascii=False), c["id"]))
            conn.commit()
            conn.close()
        return jsonify({"changed": len(changes), "applied": apply, "examples": changes[:8]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500




def build_character_book(project_id):
    """A lorebook embedded in a V2 card (data.character_book), so the card carries its world with it."""
    name, items = lorebook_entries(project_id)
    return character_book_from_items(name, items)


@bp.get("/api/lore/export")
def api_export_lorebook():
    try:
        project_id = request.args.get("project_id", type=int)
        project_name, items = lorebook_entries(project_id)
        lorebook = world_info_book(project_name, items)
        return jsonify(lorebook)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.get("/api/lore/export/deeplore")
def api_export_deeplore():
    """DeepLore (Obsidian vault) export: a zip of one markdown note per entry with YAML frontmatter."""
    try:
        import io, re as _re, zipfile
        project_id = request.args.get("project_id", type=int)
        name, items = lorebook_entries(project_id)

        def yq(v):  # YAML-safe double-quoted string
            return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'

        safe = _re.sub(r"[^\w\- ]+", "", name).strip() or "lorebook"
        buf = io.BytesIO()
        used = set()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for it in items:
                base = _re.sub(r'[\\/:*?"<>|]+', "", it["title"]).strip() or f"entry-{it['uid']}"
                fn, n = base, 2
                while fn.lower() in used:
                    fn, n = f"{base} ({n})", n + 1
                used.add(fn.lower())
                about = (it["summary"] or it["content"].split(". ")[0])[:200].strip()
                when = ("Always include: the story so far." if it["constant"]
                        else f"When to select: {it['title']} is mentioned, involved or relevant. {about}")
                fm = ["---", "tags:", "  - lorebook", f"  - {it['entry_type']}",
                      "keys:"] + [f"  - {yq(k)}" for k in it["keys"]] + [
                      f"priority: {it['order']}", f"summary: {yq(when)}"]
                if it["constant"]:
                    fm.append("constant: true")
                fm.append("---")
                z.writestr(f"{safe}/{fn}.md", "\n".join(fm) + f"\n\n# {it['title']}\n\n{it['content']}\n")
        buf.seek(0)
        from flask import send_file
        return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"{safe}-deeplore.zip")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.patch("/api/lore/entry/<int:lore_id>/project")
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


def register_lore_routes(app, **helpers):
    globals().update(helpers)
    app.register_blueprint(bp)
