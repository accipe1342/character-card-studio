"""
critic_tools.py — more of the TEXT studio's critic (kept out of text_module.py)
==============================================================================

POST /api/text/project/<pid>/critique/sweep   {provider, model, parallel?}  job: score EVERY part on its own, so
                                               the weakest chapters stand out. Saved as a critique (scope "Chapter sweep").
POST /api/text/project/<pid>/rewrite           {quote, fix, provider, model}: find the quoted line in the text and
                                               rewrite its paragraph with the fix applied (the text itself is not changed).

The critique list (GET /api/text/project/<pid>/critiques) carries each critique's average and per-category scores,
which the studio draws as a score history.
"""

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Blueprint, jsonify, request

import text_module as T

bp = Blueprint("critic_tools", __name__)

SWEEP_SYSTEM = """You are a brutally honest fiction editor scoring ONE part of a fan fiction on its own.
Return ONLY valid JSON, no fences:
{"score": 1, "scores": {"prose": 1, "dialogue": 1, "characterization": 1, "pacing": 1},
 "summary": "one sentence: what happens", "worst": "the single biggest problem in this part, specific",
 "quote": "exact short quote showing it, max 25 words", "fix": "a concrete fix", "best": "the best thing in it, or ''"}
Scores 1-10, honest: 5 is mediocre, 8+ is genuinely strong. No flattery. Judge the writing, not the author."""

REWRITE_SYSTEM = """You are a fiction line editor. Rewrite the PASSAGE so the given problem is fixed. Keep the author's
voice, point of view, tense, names and events; change only what the fix needs; keep about the same length (never
more than 30% longer). Return ONLY valid JSON, no fences: {"rewrite": "the rewritten passage", "notes": "one sentence: what changed"}"""


def _clamp(v, lo=1, hi=10):
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return None


def _sweep_markdown(name, rows):
    out = [f"# Chapter sweep: {name}", ""]
    scored = [r for r in rows if r.get("score")]
    if scored:
        avg = sum(r["score"] for r in scored) / len(scored)
        out += [f"Average {avg:.1f}/10 over {len(scored)} part(s).", ""]
    for r in rows:
        out.append(f"## {r['label']} - {r.get('score') or '?'}/10")
        if r.get("summary"):
            out.append(r["summary"])
        if r.get("worst"):
            out.append(f"- Worst: {r['worst']}" + (f" (“{r['quote']}”)" if r.get("quote") else ""))
        if r.get("fix"):
            out.append(f"- Fix: {r['fix']}")
        if r.get("best"):
            out.append(f"- Best: {r['best']}")
        out.append("")
    return "\n".join(out).strip() + "\n"


@bp.post("/api/text/project/<int:pid>/critique/sweep")
def api_sweep(pid):
    r = T._project_row(pid)
    if not r:
        return jsonify({"error": "Not found"}), 404
    d = request.get_json(force=True) or {}
    provider, model = d.get("provider", "nanogpt"), d.get("model", "")
    chunks = json.loads(r["chunks_json"] or "[]")
    if not chunks:
        return jsonify({"error": "Nothing to score: load a text first."}), 400
    workers = max(1, min(int(d.get("parallel") or 3), 6))
    job_id = T._create_job()

    def run():
        t0 = time.time()
        try:
            rows, done = {}, 0
            T._update_job(job_id, status="running", stage="requesting_model", progress=3,
                          message=f"Scoring {len(chunks)} parts ({workers} at a time)...")
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(T._request, provider, model, f"PART: {c['label']}\n\n{c['text']}", system=SWEEP_SYSTEM): c
                        for c in chunks}
                for fut in as_completed(futs):
                    c = futs[fut]
                    done += 1
                    row = {"idx": c["idx"], "label": c["label"]}
                    try:
                        res = fut.result()
                        row.update({
                            "score": _clamp(res.get("score")),
                            "scores": {k: _clamp(v) for k, v in (res.get("scores") or {}).items() if _clamp(v)},
                            **{k: str(res.get(k) or "").strip()[:400] for k in ("summary", "worst", "quote", "fix", "best")},
                        })
                    except Exception as e:
                        row["error"] = str(e)[:160]
                    rows[c["idx"]] = row
                    T._update_job(job_id, status="running", stage="requesting_model",
                                  progress=3 + int(done / len(chunks) * 92), message=f"Scored {done}/{len(chunks)} parts")
            ordered = [rows[c["idx"]] for c in chunks if c["idx"] in rows]
            scored = [x for x in ordered if x.get("score")]
            if not scored:
                raise RuntimeError("No part could be scored (all model calls failed).")
            avg = round(sum(x["score"] for x in scored) / len(scored), 1)
            weakest = sorted(scored, key=lambda x: x["score"])[:3]
            verdict = (f"Average {avg}/10 across {len(scored)} part(s). Weakest: "
                       + ", ".join(f"{x['label']} ({x['score']})" for x in weakest) + ".")
            cat_avg = {}
            for x in scored:
                for k, v in (x.get("scores") or {}).items():
                    cat_avg.setdefault(k, []).append(v)
            res = {"sweep": ordered, "verdict": verdict,
                   "scores": [{"category": k.capitalize(), "score": round(sum(v) / len(v)), "why": "average over the parts"}
                              for k, v in cat_avg.items()]}
            res["markdown"] = _sweep_markdown(r["name"], ordered)
            conn = T._conn()
            cur = conn.execute("INSERT INTO text_critiques (project_id, scope, focus, provider, model, result_json) "
                               "VALUES (?,?,?,?,?,?)", (pid, "Chapter sweep", "", provider, model, json.dumps(res, ensure_ascii=False)))
            cid = cur.lastrowid
            conn.commit()
            conn.close()
            T._log(f"[CRITIC] sweep project={pid}: {len(scored)}/{len(chunks)} parts scored, avg {avg}, "
                   f"{time.time() - t0:.1f}s -> critique {cid}")
            T._update_job(job_id, status="done", stage="done", progress=100, message="Sweep ready", result={"critique_id": cid})
        except Exception as e:
            T._update_job(job_id, status="failed", stage="failed", progress=100, message=str(e), error=str(e))

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})


_Q = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "..."})


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").translate(_Q)).strip().lower()


def find_passage(chunks, quote):
    """(chunk label, paragraph) of the paragraph containing the quote, or (None, None).
    Matching ignores case, spacing and curly quotes; a long quote may match on its first 60 characters."""
    q = _norm(quote).strip(" \"'")
    if len(q) < 8:
        return None, None
    probes = [q] + ([q[:60]] if len(q) > 60 else [])
    for probe in probes:
        for c in chunks:
            for para in re.split(r"\n\s*\n", c["text"]):
                if probe in _norm(para):
                    return c["label"], para.strip()
    return None, None


@bp.post("/api/text/project/<int:pid>/rewrite")
def api_rewrite(pid):
    r = T._project_row(pid)
    if not r:
        return jsonify({"error": "Not found"}), 404
    d = request.get_json(force=True) or {}
    quote, fix = str(d.get("quote") or "").strip(), str(d.get("fix") or "").strip()
    if not quote:
        return jsonify({"error": "No line to rewrite"}), 400
    label, para = find_passage(json.loads(r["chunks_json"] or "[]"), quote)
    found = para is not None
    passage = para if found else quote
    if len(passage) > 4000:                   # a giant paragraph: keep the sentences around the quote
        i = _norm(passage).find(_norm(quote)[:40])
        passage = passage[max(0, i - 1500): i + 2500]
    user = (f"PROBLEM AND FIX: {fix or 'Improve this passage as a strict editor would.'}\n"
            f"LINE IT IS ABOUT: {quote}\n\nPASSAGE:\n{passage}")
    try:
        res = T._request(d.get("provider", "nanogpt"), d.get("model", ""), user, system=REWRITE_SYSTEM)
    except Exception as e:
        return jsonify({"error": f"The model call failed: {str(e)[:200]}"}), 502
    rewrite = str(res.get("rewrite") or "").strip()
    if not rewrite:
        return jsonify({"error": "The model returned no rewrite. Try again or pick another model."}), 502
    return jsonify({"found": found, "label": label, "original": passage, "rewrite": rewrite,
                    "notes": str(res.get("notes") or "").strip()})


def register_critic_tools(app):
    app.register_blueprint(bp)
