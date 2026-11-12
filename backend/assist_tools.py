"""
assist_tools.py — small model-assisted helpers
==============================================

POST /api/trim         {text, target_tokens?, kind?: lore|card_field, name?, field?, provider, model}
                       -> {text, tokens_before, tokens_after}. Shortens one lore entry or card field to a target size,
                       keeping names, facts and voice. Nothing is saved: the studio shows it next to the original.
POST /api/interview    {provider, model, messages: [{role: user|char, content}], entity_id? | card?, check?}
                       -> {reply} in character, or with check: true -> {issues: [...]} (answers that contradict the
                       source). Test chats are not saved.
"""


import re

from flask import Blueprint, jsonify, request

import text_module as T
from generator import _request
from preview import format_structured_profile_text

bp = Blueprint("assist_tools", __name__)

MAX_TURNS = 12
MAX_MSG = 2000

TRIM_SYSTEM = """You shorten text for a SillyTavern {kind}. Return ONLY valid JSON, no fences: {{"text": "..."}}
Rewrite the TEXT to about {target} tokens (roughly {words} words). Keep: every name, the facts that matter most for
roleplay, distinctive voice or quirks, and the original meaning. Drop: repetition, filler, generic adjectives, stock
phrases, and anything the rest of the card or lorebook would already say. Keep the same language and point of view.
Never add facts. Plain text only, no headings or bullet lists unless the original used them."""

INTERVIEW_SYSTEM = """You are {name}. Stay fully in character and answer the interviewer's questions the way {name}
would, in their own voice and speech habits, using ONLY what the CHARACTER NOTES support. If asked something the notes
do not cover, answer in character with something plausible and modest, or deflect the way {name} would; never invent
major facts. Speak only as {name}: no narration of the interviewer, no out-of-character notes.
Reply length: 1-6 sentences. Return ONLY valid JSON, no fences: {{"reply": "..."}}

CHARACTER NOTES:
{notes}"""

CHECK_SYSTEM = """You check an interview with a fictional character against that character's notes. Return ONLY valid
JSON, no fences: {"issues": ["short description of each answer that contradicts the notes or sounds out of character,
quoting the answer"], "verdict": "one sentence"}. Use only the notes as the truth. If nothing is wrong, return
{"issues": [], "verdict": "Consistent with the notes."}"""


REPLY_KEYS = ("reply", "response", "answer", "text", "content", "message")


def _ask(provider, model, prompt, system, key):
    """Model call that also copes with models that ignore the JSON instruction: a plain-text answer (common with
    roleplay models) comes back as {key: text}, and a JSON value that isn't an object is wrapped the same way."""
    try:
        res = _request(provider, model, prompt, system=system)
    except ValueError as e:                    # generator gives up on JSON and keeps the raw answer in the message
        msg = str(e)
        if "Raw: " not in msg:
            raise
        return {key: msg.split("Raw: ", 1)[1].strip(), "plain": True}
    if isinstance(res, dict):
        if not str(res.get(key) or "").strip():
            alt = next((res[k] for k in REPLY_KEYS if isinstance(res.get(k), str) and res[k].strip()), None)
            if alt:
                res = {**res, key: alt}
        return res
    if isinstance(res, str):
        return {key: res, "plain": True}
    return {}


def clean_reply(text, name):
    """Strip what models add around a spoken answer: a leading 'Name:' label and wrapping quotes."""
    t = str(text or "").strip()
    t = re.sub(rf"^\s*\**\s*{re.escape(name)}\s*\**\s*:\s*\**\s*", "", t, flags=re.I)   # Mara: / **Mara:** / **Mara**:
    if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'“”":
        t = t[1:-1].strip()
    if t.startswith("“") and t.endswith("”"):
        t = t[1:-1].strip()
    return t


def _tok(text):
    return max(1, round(len(text or "") / 4))


@bp.post("/api/trim")
def api_trim():
    d = request.get_json(force=True) or {}
    text = str(d.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Nothing to trim"}), 400
    try:
        target = max(30, min(int(d.get("target_tokens") or 150), 2000))
    except (TypeError, ValueError):
        target = 150
    before = _tok(text)
    if before <= target:
        return jsonify({"text": text, "tokens_before": before, "tokens_after": before, "unchanged": True})
    kind = "character card field" if d.get("kind") == "card_field" else "lorebook entry"
    what = f"{kind} '{d.get('field') or ''}' of {d.get('name') or 'a character'}".strip()
    try:
        res = _ask(d.get("provider") or "nanogpt", d.get("model") or "",
                   f"WHAT THIS IS: {what}\n\nTEXT:\n{text[:12000]}",
                   TRIM_SYSTEM.format(kind=kind, target=target, words=int(target * 0.75)), "text")
    except Exception as e:
        return jsonify({"error": f"The model call failed: {str(e)[:200]}"}), 502
    out = str(res.get("text") or "").strip()
    if not out:
        return jsonify({"error": "The model returned nothing. Try again or pick another model."}), 502
    return jsonify({"text": out, "tokens_before": before, "tokens_after": _tok(out)})


def entity_notes(eid):
    """(name, notes) for a reviewed TEXT character, as of the project's starting point."""
    conn = T._conn()
    row = conn.execute("SELECT * FROM text_entities WHERE id=?", (eid,)).fetchone()
    conn.close()
    if not row:
        return None, None
    e = T._row_entity(row)
    _, _, upto = T._project_recap(e["project_id"])
    e = (T.entities_as_of(e["project_id"], [e], upto) or [e])[0]
    notes = T.lore_entry_content(e)
    known = []
    for o in T._entities(e["project_id"]):
        for it in T.secret_items(o, []):
            if any(n.lower() == e["name"].lower() for n in it["char_filter"]):
                known.append(it["content"])
    if known:
        notes += "\n\nSecrets you know (keep them unless there is a good reason to tell):\n" + "\n".join(f"- {k}" for k in known)
    return e["name"], notes


def card_notes(card):
    name = str(card.get("name") or "the character")
    parts = []
    for key, label in (("description", "Description"), ("personality", "Personality"), ("scenario", "Scenario"),
                       ("depth_prompt", "Character's note"), ("mes_example", "Example messages")):
        v = str(card.get(key) or "").strip()
        if v:
            parts.append(f"{label}: {v}")
    sp = card.get("structured_profile")
    if isinstance(sp, dict) and any(sp.values()):
        parts.append("Profile:\n" + format_structured_profile_text(name, sp))
    return name, "\n\n".join(parts)


@bp.post("/api/interview")
def api_interview():
    d = request.get_json(force=True) or {}
    if d.get("entity_id"):
        name, notes = entity_notes(int(d["entity_id"]))
        if name is None:
            return jsonify({"error": "Character not found"}), 404
    elif isinstance(d.get("card"), dict):
        name, notes = card_notes(d["card"])
    else:
        return jsonify({"error": "Give entity_id or card"}), 400
    msgs = [m for m in (d.get("messages") or []) if isinstance(m, dict) and str(m.get("content") or "").strip()]
    msgs = msgs[-MAX_TURNS:]
    transcript = "\n".join(f"{'INTERVIEWER' if m.get('role') == 'user' else name.upper()}: {str(m['content'])[:MAX_MSG]}"
                           for m in msgs)
    provider, model = d.get("provider") or "nanogpt", d.get("model") or ""
    try:
        if d.get("check"):
            if not msgs:
                return jsonify({"error": "Ask a few questions first"}), 400
            res = _ask(provider, model, f"CHARACTER: {name}\n\nNOTES:\n{notes[:9000]}\n\nINTERVIEW:\n{transcript}",
                       CHECK_SYSTEM, "verdict")
            raw = res.get("issues")
            issues = [str(x) for x in (raw if isinstance(raw, list) else [raw] if raw else []) if str(x).strip()][:10]
            return jsonify({"issues": issues, "verdict": str(res.get("verdict") or "").strip()[:600]})
        if not msgs or msgs[-1].get("role") != "user":
            return jsonify({"error": "Ask a question"}), 400
        res = _ask(provider, model, f"INTERVIEW SO FAR:\n{transcript}\n\nAnswer the last question as {name}.",
                   INTERVIEW_SYSTEM.format(name=name, notes=notes[:9000]), "reply")
    except Exception as e:
        return jsonify({"error": f"The model call failed: {str(e)[:200]}"}), 502
    reply = clean_reply(res.get("reply"), name)
    if not reply:
        return jsonify({"error": "The model returned no reply. Try again."}), 502
    return jsonify({"reply": reply, "name": name})


def register_assist_tools(app):
    app.register_blueprint(bp)
