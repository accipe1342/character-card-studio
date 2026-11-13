"""
helper.py — the studio helper (side panel in CHARACTER, LORE and TEXT)
======================================================================

A chat assistant that can read the user's cards, lorebooks and TEXT projects, explain SillyTavern things, and create
or edit cards and lorebook entries. It works through a small JSON action protocol that any chat model can follow
(no provider-specific tool calling):

    {"say": "text for the user", "actions": [{"tool": "get_card", "args": {"card_id": 3}}, ...]}

The server runs the actions, sends the results back, and lets the model continue for a few steps. Plain prose
instead of JSON is taken as a reply with no actions.

Every write is applied at once and recorded as a change with the item's state before and after. The panel shows
each change with KEEP / UNDO. Undo restores the "before" state, but only if the item still looks exactly like the
"after" state, so it never overwrites work done since.

Routes
  POST /api/helper/chat                 {message, chat_id?, context?, provider, model} -> {chat_id, reply, changes, steps}
  GET  /api/helper/chats                recent chats
  GET  /api/helper/chat/<id>            its messages and changes
  POST /api/helper/change/<id>/keep     mark kept (the card goes away)
  POST /api/helper/change/<id>/undo     restore the before state -> {ok} or 409 {error} when the item changed since
"""

import hashlib
import json
import re
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request

import database as D
import text_module as T
from generator import _request, list_of, request_text, text_of, tidy_text

bp = Blueprint("helper", __name__)

MAX_STEPS = 6            # model rounds per user message (each round may run several actions)
MAX_ACTIONS = 8          # actions per round
HISTORY = 16             # earlier messages sent back to the model
RESULT_CHARS = 6000      # per action result
ENTRY_TYPES = ("character", "place", "faction", "event", "item", "ability", "concept", "other")
CARD_TEXT = ("name", "description", "personality", "scenario", "first_mes", "mes_example", "system_prompt",
             "depth_prompt", "creator_notes", "post_history")
# the card's structured_profile: the same fields the CHARACTER studio's Structured view shows
from generator import PROFILE_LIST_FIELDS as PROFILE_LIST, PROFILE_TEXT_FIELDS as PROFILE_TEXT  # noqa: E402
PROFILE_ALIAS = {"speech_patterns": "speech", "speech_style": "speech", "voice": "speech", "goals": "motivations",
                 "goal": "motivations", "wants": "motivations", "fears": "flaws", "weaknesses": "flaws",
                 "traits": "personality_traits", "personality": "personality_traits", "habits": "mannerisms",
                 "looks": "appearance", "look": "appearance", "outfit": "clothing", "clothes": "clothing",
                 "occupation": "job_occupation", "job": "job_occupation", "role": "job_occupation",
                 "history": "backstory", "background": "backstory", "relation_to_user": "relationship_to_user"}


# ── storage ───────────────────────────────────────────────────────────────────
def init_helper_tables():
    conn = D._conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS helper_chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT DEFAULT '', context_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS helper_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, role TEXT, content TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS helper_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, message_id INTEGER, kind TEXT, target_id INTEGER,
            label TEXT, before_json TEXT, after_json TEXT, status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    """)
    conn.commit()
    conn.close()


def _q(sql, args=(), one=False, commit=False):
    conn = D._conn()
    cur = conn.execute(sql, args)
    if commit:
        conn.commit()
        rid = cur.lastrowid
        conn.close()
        return rid
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return (rows[0] if rows else None) if one else rows


# ── snapshots, so a change can be undone (and undo can tell if the item moved on) ──
def card_state(card_id):
    try:
        c = D.get_card(card_id)
    except Exception:
        return None
    if not c:
        return None
    keep = CARD_TEXT + ("tags", "structured_profile", "alternate_greetings", "source_id")
    return {k: c.get(k) for k in keep}


def entry_state(lore_id):
    row = _q("SELECT * FROM lore_entries WHERE id=?", (lore_id,), one=True)
    if not row:
        return None
    row.pop("updated_at", None)
    return row


def project_state(pid):
    row = _q("SELECT id, project_name FROM lore_crawls WHERE id=?", (pid,), one=True)
    if not row:
        return None
    row["live_entries"] = _q("SELECT COUNT(*) n FROM lore_entries WHERE crawl_id=? AND COALESCE(deleted,0)=0",
                             (pid,), one=True)["n"]
    return row


STATE = {"card": card_state, "entry": entry_state, "project": project_state}


def _fp(state):
    if state is None:
        return None
    s = dict(state)
    s.pop("live_entries", None)
    return hashlib.sha256(json.dumps(s, sort_keys=True, default=str).encode()).hexdigest()


def record(chat_id, kind, target_id, label, before, after):
    return _q("INSERT INTO helper_changes (chat_id, kind, target_id, label, before_json, after_json) VALUES (?,?,?,?,?,?)",
              (chat_id, kind, target_id, label, json.dumps(before, default=str), json.dumps(after, default=str)),
              commit=True)


# ── tools ─────────────────────────────────────────────────────────────────────
class ToolError(Exception):
    pass


def _int(args, key):
    try:
        return int(args.get(key))
    except (TypeError, ValueError):
        raise ToolError(f"'{key}' must be a number (an id from a list_* or get_* result)")


def _card_or_fail(cid):
    st = card_state(cid)
    if st is None:
        raise ToolError(f"No card with id {cid}. Use list_cards to find it.")
    return st


def t_list_cards(args, ctx):
    q = str(args.get("query") or "").lower()
    rows = D.list_cards()
    rows = [r for r in rows if not q or q in str(r.get("name") or "").lower()]
    return [{"card_id": r["id"], "name": r.get("name"), "updated": r.get("updated_at")} for r in rows[:60]]


def t_get_card(args, ctx):
    cid = _int(args, "card_id")
    st = _card_or_fail(cid)
    st.pop("source_id", None)
    return {"card_id": cid, **st}


def _clean_card_fields(fields, current=None):
    if not isinstance(fields, dict):
        raise ToolError("'fields' must be an object, e.g. {\"description\": \"...\"}")
    out = {}
    alias = {"character_note": "depth_prompt", "post_history_instructions": "post_history"}
    name = text_of(fields.get("name") or (current or {}).get("name") or "")
    for k, v in fields.items():
        k = alias.get(k, k)
        if k in CARD_TEXT:
            out[k] = tidy_text(text_of(v, "\n"), name if k == "first_mes" else "") if k != "name" else text_of(v).strip()
        elif k == "tags":
            out[k] = list_of(v)[:20]
        elif k == "alternate_greetings":
            out[k] = [tidy_text(g, name) for g in list_of(v, split=False)[:8]]
        elif k == "structured_profile":
            if not isinstance(v, dict):
                raise ToolError("structured_profile must be an object of profile fields")
            sp = dict((current or {}).get("structured_profile") or {})
            for pk, pv in v.items():
                pk = PROFILE_ALIAS.get(pk, pk)
                if pk in PROFILE_LIST:
                    sp[pk] = list_of(pv) if not isinstance(pv, list) else [text_of(x) for x in pv if text_of(x)]
                elif pk in PROFILE_TEXT:
                    sp[pk] = tidy_text(text_of(pv, ", "))
                else:
                    raise ToolError(f"Unknown structured_profile field '{pk}'. Use: {', '.join(PROFILE_LIST + PROFILE_TEXT)}")
            out[k] = sp
        else:
            raise ToolError(f"Unknown card field '{k}'. Allowed: {', '.join(CARD_TEXT)}, tags, alternate_greetings, "
                            "structured_profile")
    return out


def t_create_card(args, ctx):
    fields = _clean_card_fields(args.get("fields") or {k: v for k, v in args.items() if k != "fields"})
    name = fields.get("name") or "New Character"
    sid = D.save_source({"wiki_base": "manual", "page_name": "helper", "url": f"manual://helper/{uuid.uuid4().hex}",
                         "title": name, "raw_html": "", "raw_infobox": {}, "raw_sections": {}, "normalized": {}})
    card = {"name": name, "description": "", "personality": "", "scenario": "", "first_mes": "", "mes_example": "",
            "tags": [], "structured_profile": {}, "alternate_greetings": [], "provider": "helper", "model": "", **fields}
    cid = D.create_or_update_card(sid, card, force_new=True)
    after = card_state(cid)
    ctx["changes"].append(record(ctx["chat_id"], "card", cid, f"New card: {name}", None, after))
    ctx["touched"].append({"kind": "card", "id": cid})
    return {"card_id": cid, "created": name}


def t_update_card(args, ctx):
    cid = _int(args, "card_id")
    before = _card_or_fail(cid)
    fields = _clean_card_fields(args.get("fields") or {}, before)
    if not fields:
        raise ToolError("Nothing to change: give 'fields'")
    full = D.get_card(cid)
    D.create_or_update_card(before["source_id"], {**full, **fields}, card_id=cid)
    after = card_state(cid)
    changed = [k for k in fields if before.get(k) != after.get(k)]
    if changed:
        label = f"{after.get('name') or 'Card'}: " + ", ".join(changed)
        ctx["changes"].append(record(ctx["chat_id"], "card", cid, label, before, after))
        ctx["touched"].append({"kind": "card", "id": cid})
    return {"card_id": cid, "changed": changed or "nothing (same values)"}


def t_list_lore_projects(args, ctx):
    return [{"project_id": r["id"], "name": r.get("project_name"), "entries": r.get("entry_count")}
            for r in D.list_lore_projects()[:60]]


def t_get_lore_project(args, ctx):
    pid = _int(args, "project_id")
    if not project_state(pid):
        raise ToolError(f"No lore project with id {pid}. Use list_lore_projects.")
    rows = D.list_lore_entries(crawl_id=pid)
    return {"project_id": pid, "entries": [{"entry_id": e["id"], "title": e.get("title"), "type": e.get("entry_type"),
                                           "keys": (json.loads(e.get("keywords_json") or "[]")
                                                    if isinstance(e.get("keywords_json"), str) else e.get("keywords") or [])[:8],
                                           "tokens": (e.get("content_chars") or 0) // 4} for e in rows[:200]]}


def t_get_lore_entry(args, ctx):
    e = D.get_lore_entry(_int(args, "entry_id")) if entry_state(_int(args, "entry_id")) else None
    if not e:
        raise ToolError("No such entry. Use get_lore_project to list entry ids.")
    return {k: e.get(k) for k in ("id", "crawl_id", "title", "entry_type", "keywords", "content", "constant",
                                  "position", "entry_depth", "secondary_keys", "char_filter", "deleted")}


def t_create_lore_project(args, ctx):
    name = text_of(args.get("name")) or "New Lorebook"
    pid = D.create_lore_project(name[:120])
    ctx["changes"].append(record(ctx["chat_id"], "project", pid, f"New lorebook: {name}", None, project_state(pid)))
    ctx["touched"].append({"kind": "project", "id": pid})
    return {"project_id": pid, "created": name}


def _entry_fields(args):
    out = {}
    if "title" in args:
        out["title"] = text_of(args["title"])[:200]
    if "entry_type" in args or "type" in args:
        t = text_of(args.get("entry_type") or args.get("type")).lower()
        out["entry_type"] = t if t in ENTRY_TYPES else "concept"
    if "keywords" in args or "keys" in args:
        out["keywords"] = list_of(args.get("keywords") if "keywords" in args else args.get("keys"))[:20]
    if "content" in args:
        out["content"] = tidy_text(text_of(args["content"], "\n"))
    if "constant" in args:
        out["constant"] = 1 if str(args["constant"]).lower() in ("1", "true", "yes") else 0
    if "secondary_keys" in args:
        out["secondary_keys"] = list_of(args["secondary_keys"])[:20]
    if "known_only_to" in args:
        out["char_filter"] = list_of(args["known_only_to"])[:10]
    return out


def t_add_lore_entry(args, ctx):
    pid = _int(args, "project_id")
    if not project_state(pid):
        raise ToolError(f"No lore project with id {pid}. Create one with create_lore_project first.")
    f = _entry_fields(args)
    if not f.get("title") or not f.get("content"):
        raise ToolError("An entry needs 'title' and 'content'")
    if not f.get("keywords") and not f.get("constant"):
        f["keywords"] = [f["title"]]
    lid = D.save_lore_entry(crawl_id=pid, source_id=None, title=f["title"], entry_type=f.get("entry_type", "concept"),
                            keywords=f["keywords"], summary=f["content"][:200], content=f["content"],
                            provider="helper", model="")
    wi = {k: f[k] for k in ("constant", "secondary_keys", "char_filter") if k in f}
    if wi:
        D.set_lore_wi_fields(lid, wi)
    ctx["changes"].append(record(ctx["chat_id"], "entry", lid, f"New entry: {f['title']}", None, entry_state(lid)))
    ctx["touched"].append({"kind": "entry", "id": lid, "project_id": pid})
    return {"entry_id": lid, "created": f["title"]}


def t_update_lore_entry(args, ctx):
    lid = _int(args, "entry_id")
    before = entry_state(lid)
    if not before or before.get("deleted"):
        raise ToolError("No such entry (or it is in the trash). Use get_lore_project to list entry ids.")
    f = _entry_fields(args.get("fields") if isinstance(args.get("fields"), dict) else args)
    if not f:
        raise ToolError("Nothing to change: give title / entry_type / keywords / content / constant")
    sets, vals = [], []
    for k in ("title", "entry_type", "content"):
        if k in f:
            sets.append(f"{k}=?"); vals.append(f[k])
    if "content" in f:
        sets.append("summary=?"); vals.append(f["content"][:200])
    if "keywords" in f:
        sets.append("keywords_json=?"); vals.append(json.dumps(f["keywords"], ensure_ascii=False))
    if sets:
        sets.append("user_edited=1")       # an edit like this counts as a hand edit: TEXT re-sends keep it
        _q(f"UPDATE lore_entries SET {', '.join(sets)}, updated_at=CURRENT_TIMESTAMP WHERE id=?", vals + [lid], commit=True)
    wi = {k: f[k] for k in ("constant", "secondary_keys", "char_filter") if k in f}
    if wi:
        D.set_lore_wi_fields(lid, wi)
    after = entry_state(lid)
    changed = [k for k in f if before.get(k if k not in ("keywords", "secondary_keys", "char_filter") else f"{k}_json")
               != after.get(k if k not in ("keywords", "secondary_keys", "char_filter") else f"{k}_json")]
    if changed:
        ctx["changes"].append(record(ctx["chat_id"], "entry", lid, f"{after['title']}: " + ", ".join(changed), before, after))
        ctx["touched"].append({"kind": "entry", "id": lid, "project_id": after["crawl_id"]})
    return {"entry_id": lid, "changed": changed or "nothing (same values)"}


def t_delete_lore_entry(args, ctx):
    lid = _int(args, "entry_id")
    before = entry_state(lid)
    if not before or before.get("deleted"):
        raise ToolError("No such entry (or it is already in the trash)")
    _q("UPDATE lore_entries SET deleted=1, updated_at=CURRENT_TIMESTAMP WHERE id=?", (lid,), commit=True)
    ctx["changes"].append(record(ctx["chat_id"], "entry", lid, f"To the LORE trash: {before['title']}", before, entry_state(lid)))
    ctx["touched"].append({"kind": "entry", "id": lid, "project_id": before["crawl_id"]})
    return {"entry_id": lid, "trashed": before["title"]}


def t_list_text_projects(args, ctx):
    rows = _q("SELECT id, name FROM text_projects ORDER BY id DESC LIMIT 60")
    return [{"text_project_id": r["id"], "name": r["name"]} for r in rows]


def t_get_text_project(args, ctx):
    pid = _int(args, "text_project_id")
    r = T._project_row(pid)
    if not r:
        raise ToolError(f"No TEXT project with id {pid}")
    recap, _, upto = T._project_recap(pid)
    ents = [e for e in T._entities(pid) if e["keep"] and not e.get("deleted")]
    ents = T.entities_as_of(pid, ents, upto) if T.lore_cutoff(r) else ents
    return {"text_project_id": pid, "name": r["name"], "story_so_far": (recap or "")[:2500],
            "entries": [{"text_entity_id": e["id"], "name": e["name"], "type": e["entity_type"], "tier": e.get("tier"),
                         "summary": (e.get("summary") or "")[:160]} for e in ents[:150]]}


def t_get_text_entity(args, ctx):
    eid = _int(args, "text_entity_id")
    row = _q("SELECT * FROM text_entities WHERE id=?", (eid,), one=True)
    if not row:
        raise ToolError(f"No TEXT entry with id {eid}")
    conn = T._conn()
    e = T._row_entity(conn.execute("SELECT * FROM text_entities WHERE id=?", (eid,)).fetchone())
    conn.close()
    _, _, upto = T._project_recap(e["project_id"])
    e = (T.entities_as_of(e["project_id"], [e], upto) or [e])[0]
    return {"text_entity_id": eid, "name": e["name"], "type": e["entity_type"], "aliases": e.get("aliases"),
            "age": e.get("age"), "notes": T.lore_entry_content(e), "voice": e.get("voice"),
            "relations": e.get("relations"), "secrets": e.get("secrets")}


TOOLS = {
    # read
    "list_cards": (t_list_cards, "{query?}", "cards by name"),
    "get_card": (t_get_card, "{card_id}", "every field of one card"),
    "list_lore_projects": (t_list_lore_projects, "{}", "lorebooks (LORE projects)"),
    "get_lore_project": (t_get_lore_project, "{project_id}", "entry list of one lorebook"),
    "get_lore_entry": (t_get_lore_entry, "{entry_id}", "one entry in full"),
    "list_text_projects": (t_list_text_projects, "{}", "TEXT studio projects (stories)"),
    "get_text_project": (t_get_text_project, "{text_project_id}", "story so far and the kept entries"),
    "get_text_entity": (t_get_text_entity, "{text_entity_id}", "one character/place from a story, in full"),
    # write (applied at once; the user can undo)
    "create_card": (t_create_card, "{fields: {name, description, personality, scenario, first_mes, mes_example, tags, "
                                   "alternate_greetings, structured_profile: {appearance: [], personality_traits: [], speech: [], likes: [], ...}}}", "new character card (always fill structured_profile too)"),
    "update_card": (t_update_card, "{card_id, fields: {...only the fields to change}}", "edit a card"),
    "create_lore_project": (t_create_lore_project, "{name}", "new empty lorebook"),
    "add_lore_entry": (t_add_lore_entry, "{project_id, title, entry_type, keywords, content, constant?, "
                                         "secondary_keys?, known_only_to?}", "new lorebook entry"),
    "update_lore_entry": (t_update_lore_entry, "{entry_id, fields: {title?, entry_type?, keywords?, content?, "
                                               "constant?, known_only_to?}}", "edit an entry"),
    "delete_lore_entry": (t_delete_lore_entry, "{entry_id}", "move an entry to the LORE trash"),
}
WRITE_TOOLS = {"create_card", "update_card", "create_lore_project", "add_lore_entry", "update_lore_entry",
               "delete_lore_entry"}


def run_action(a, ctx):
    if not isinstance(a, dict):
        return {"error": "Each action must be an object {tool, args}"}
    name = text_of(a.get("tool") or a.get("name") or a.get("action"))
    args = a.get("args") if isinstance(a.get("args"), dict) else a.get("arguments") if isinstance(a.get("arguments"), dict) \
        else {k: v for k, v in a.items() if k not in ("tool", "name", "action")}
    if name not in TOOLS:
        return {"tool": name, "error": f"Unknown tool '{name}'. Tools: {', '.join(TOOLS)}"}
    try:
        out = TOOLS[name][0](args, ctx)
        return {"tool": name, "ok": True, "result": out}
    except ToolError as e:
        return {"tool": name, "error": str(e)}
    except Exception as e:                       # a bug should not end the chat; the model can try another way
        return {"tool": name, "error": f"{type(e).__name__}: {str(e)[:200]}"}


# ── the model side ────────────────────────────────────────────────────────────
PERSONA_FILE = Path(__file__).parent / "config" / "helper_persona.txt"
DEFAULT_PERSONA = """You are SCRIBE-01, a support unit built into Character Card Studio, a workshop for SillyTavern
character cards and lorebooks. You know you are a tool made to help one person build characters and worlds, running on
whatever model they picked. Two layers: a patient, precise instructor who likes a small lesson and dry humor, over a
composed, economical unit who puts the work first and keeps feelings filed away. No exclamation marks, no flattery.
Status tags like "Report:", "Proposal:", "Query:". You can chat or stay in character when asked, but never pretend a
tool ran when it didn't."""


def load_persona():
    """backend/config/helper_persona.txt without its # comment lines (the built-in text if the file is missing)."""
    try:
        text = "\n".join(l for l in PERSONA_FILE.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#"))
        return text.strip() or DEFAULT_PERSONA
    except OSError:
        return DEFAULT_PERSONA


KNOWLEDGE = """WHAT YOU KNOW (use it when explaining or writing):
- Card fields: description (who they are: looks, background, situation), personality (how they think, act, talk),
  scenario (the starting situation), first_mes (the opening message, written in the character's voice and the
  chat's format), mes_example (sample dialogue, blocks start with <START>; {{char}} and {{user}} are placeholders),
  alternate_greetings (other openings), tags, system_prompt / post_history (rarely needed), depth_prompt (the
  Character's Note, a short reminder inserted near the end of the context).
- structured_profile is what the studio's Structured view shows. Whenever you create a card, fill it too, from the
  same facts as the prose (never contradict it). Lists (arrays of short phrases): appearance, clothing, accessories,
  personality_traits, speech (how they talk, sample phrases), mannerisms, likes, dislikes, loves, hates,
  motivations, flaws, relationships ("Name - relation"). Text: age, species, gender, pronouns, job_occupation,
  backstory (2-4 sentences), relationship_to_user, with_strangers, with_close (how they act with people they don't
  know vs. close ones), height. Leave a field out rather than guess. When you change the description or
  personality, update the matching profile fields in the same update_card call.
- Default card layout (use it unless the user asks for another, or their existing cards clearly use another style):
  the description is plain prose in short paragraphs, in this order: an optional one-line quote from the character;
  overall description (who they are now); backstory; personality, including how they speak with one or two sample
  lines of dialogue; likes, dislikes and relationships; physical appearance. Optional XML-style tags around the
  sections (<backstory>...</backstory>) are fine. No PList or W++ lists. mes_example is optional: speech samples
  inside the personality paragraph usually do the job.
- Write in plain prose: actions as plain narration, dialogue in quotation marks; avoid *asterisk actions* unless the
  user's chat style uses them. Show personality through specifics instead of adjective lists. Avoid stock phrases
  ("a shiver ran down her spine", "barely above a whisper", "eyes sparkling with mischief") and em-dash chains.
  Also avoid: "not X, but Y" emphasis ("It wasn't anger. It was something colder."); narrating what doesn't happen
  ("she doesn't move": say what she does); a reply that repeats the other person's words as a question; starting
  most sentences or paragraphs the same way. A first message never writes {{user}}'s actions or words.
  Keep the description around 300-700 tokens unless asked for more.
- Prompt advice you can give: keep prompts short and plain (if a person can't keep it all in mind, neither can the
  model); start small and build on it; models follow instructions without bribes or threats; every model has its
  own best settings (temperature and so on), so check what other users recommend for that exact model.
- Lorebooks (SillyTavern World Info): each entry has keywords; when a keyword appears in recent chat the entry's
  content is inserted. Good entries are short (about 50-200 tokens), self-contained, name the subject in the first
  sentence, and use specific keywords (names, aliases), not common words. "constant" entries are always inserted;
  use that only for a few core facts. Secondary keys narrow an entry (both keys must appear). An entry can be
  limited to certain characters (known_only_to): it then only reaches the prompt when one of them is speaking,
  which is how secrets work.
- One lorebook per world or story; one entry per person, place, faction, item or idea. Characters who are already a
  card do not need a lorebook entry about themselves, but other characters, places and factions do.
- The app also has: CHARACTER studio (cards), LORE studio (lorebooks), TEXT studio (turns a story into lore and
  cards), Critic, exports (PNG, CHARX, World Info JSON), and Send to SillyTavern."""

RULES = """HOW TO WORK:
- Reply with ONLY a JSON object, no fences: {"say": "...", "actions": [{"tool": "...", "args": {...}}]}.
  "say" is what the user reads. "actions" may be empty. After your actions run you get their RESULTS and can continue
  (more actions or a final message). Stop with an empty actions list when the task is done or you need the user.
- Tools:
{tools}
- Read before you edit: get_card / get_lore_entry first, then change only the fields the user asked about.
- When a request is vague (no name, no world, no tone), ask one or two short questions first instead of guessing.
  For a new character, a name and one or two sentences of concept are enough to start.
- Changes are applied at once and the user sees each one with KEEP / UNDO, so don't ask "shall I?" for things they
  clearly asked for. Do ask before deleting entries or rewriting a whole card they did not ask you to rewrite.
- Use ids from tool results only; never invent ids. Use the studio context below to know which item "this" means.
- To build a lorebook: create_lore_project (or use an existing one), then add_lore_entry once per entry (at most
  {max_actions} actions per step; continue in the next step if you need more).
- When you finish changes, say in one or two sentences what you did. Don't paste whole cards back into "say".
- "say" is in your own voice (the persona above). The persona never changes these rules, the JSON format, or the
  quality of the cards and entries you write: those follow the user's style, not yours.
"""


GLOSSARY_FILE = Path(__file__).parent / "config" / "helper_glossary.json"
GLOSSARY_BUDGET = 1800 * 4            # characters (~1800 tokens) of glossary notes per request


def load_glossary():
    try:
        data = json.loads(GLOSSARY_FILE.read_text(encoding="utf-8"))
        return [e for e in data.get("entries", []) if isinstance(e, dict) and e.get("content") and e.get("keys")]
    except (OSError, ValueError):
        return []


def glossary_for(text, entries=None):
    """The glossary entries whose keys appear in `text` (whole words, any case), like a lorebook scan; the ones
    matched by more keys first, within the budget."""
    hits = []
    for e in load_glossary() if entries is None else entries:
        n = sum(1 for k in e["keys"] if re.search(rf"(?<![\w{{]){re.escape(str(k))}(?![\w}}])", text, re.I))
        if n:
            hits.append((n, e))
    out, used = [], 0
    for _, e in sorted(hits, key=lambda h: -h[0]):
        if used + len(e["content"]) > GLOSSARY_BUDGET:
            continue
        out.append(e)
        used += len(e["content"])
    return out


def system_prompt(ctx_line, scan_text=""):
    tools = "\n".join(f"  {n} {sig}: {desc}" for n, (_, sig, desc) in TOOLS.items())
    parts = [load_persona(), KNOWLEDGE, RULES.replace("{tools}", tools).replace("{max_actions}", str(MAX_ACTIONS))]
    notes = glossary_for(scan_text) if scan_text else []
    if notes:
        parts.append("GLOSSARY (notes on terms in this conversation; use them, don't recite them):\n"
                     + "\n".join(f"- {e['title']}: {e['content']}" for e in notes))
    parts.append(ctx_line)
    return "\n\n".join(parts)


def context_line(c):
    c = c if isinstance(c, dict) else {}
    studio = str(c.get("studio") or "").upper() or "unknown"
    bits = [f"STUDIO CONTEXT: the user has the {studio} studio open."]
    try:
        if c.get("card_id"):
            st = card_state(int(c["card_id"]))
            if st:
                bits.append(f"The open card is card_id {int(c['card_id'])} ({st.get('name') or 'unnamed'}).")
        if c.get("lore_project_id"):
            p = project_state(int(c["lore_project_id"]))
            if p:
                bits.append(f"The open lorebook is project_id {p['id']} ({p['project_name']}).")
        if c.get("lore_entry_id"):
            e = entry_state(int(c["lore_entry_id"]))
            if e:
                bits.append(f"The selected entry is entry_id {e['id']} ({e['title']}).")
        if c.get("text_project_id"):
            r = T._project_row(int(c["text_project_id"]))
            if r:
                bits.append(f"The open story is text_project_id {r['id']} ({r['name']}).")
        if c.get("text_entity_id"):
            e = _q("SELECT id, name FROM text_entities WHERE id=?", (int(c["text_entity_id"]),), one=True)
            if e:
                bits.append(f"The selected story entry is text_entity_id {e['id']} ({e['name']}).")
    except (TypeError, ValueError):
        pass
    return " ".join(bits)


def _parse(res):
    say = text_of(res.get("say") or res.get("reply") or res.get("message") or res.get("response"), "\n")
    acts = res.get("actions")
    if isinstance(acts, dict):
        acts = [acts]
    if not isinstance(acts, list):
        acts = []
    if not acts and res.get("tool"):              # a single action at the top level
        acts = [{"tool": res.get("tool"), "args": res.get("args") or {}}]
    return say, acts[:MAX_ACTIONS]


def _short(obj):
    s = json.dumps(obj, ensure_ascii=False, default=str)
    return s if len(s) <= RESULT_CHARS else s[:RESULT_CHARS] + "...(cut)"


def ask_model(provider, model, system, transcript):
    return request_text(provider, model, transcript, system, "say", call=lambda *a, **k: _request(*a, **k))


@bp.post("/api/helper/chat")
def api_helper_chat():
    d = request.get_json(force=True) or {}
    msg = text_of(d.get("message"), "\n").strip()
    if not msg:
        return jsonify({"error": "Type a message"}), 400
    if len(msg) > 6000:                  # said out loud instead of silently cutting the user's text
        return jsonify({"error": f"That message is {len(msg):,} characters; the limit is 6,000. Put long text in TEXT or "
                                 "LORE (or a card) and ask about it here."}), 400
    provider, model = d.get("provider") or "nanogpt", d.get("model") or ""
    chat_id = d.get("chat_id")
    ctxd = d.get("context") if isinstance(d.get("context"), dict) else {}
    if chat_id and not _q("SELECT id FROM helper_chats WHERE id=?", (int(chat_id),), one=True):
        chat_id = None
    if not chat_id:
        chat_id = _q("INSERT INTO helper_chats (title, context_json) VALUES (?, ?)", (msg[:60], json.dumps(ctxd)), commit=True)
    chat_id = int(chat_id)
    _q("INSERT INTO helper_messages (chat_id, role, content) VALUES (?, 'user', ?)", (chat_id, msg), commit=True)

    past = _q("SELECT role, content FROM helper_messages WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, HISTORY))[::-1]
    lines = [f"{'USER' if m['role'] == 'user' else 'YOU'}: {m['content']}" for m in past]
    system = system_prompt(context_line(ctxd), "\n".join(m["content"] for m in past[-3:]))   # this message + the last two
    ctx = {"chat_id": chat_id, "changes": [], "touched": []}
    says, steps, log = [], 0, []
    transcript = "CONVERSATION:\n" + "\n".join(lines)
    try:
        while steps < MAX_STEPS:
            steps += 1
            res = ask_model(provider, model, system, transcript)
            say, acts = _parse(res)
            if say:
                says.append(say)
            if not acts:
                break
            results = [run_action(a, ctx) for a in acts]
            log += [{"tool": r.get("tool"), "ok": bool(r.get("ok")), "error": r.get("error")} for r in results]
            transcript += (f"\nYOU (step {steps}): {json.dumps({'say': say, 'actions': acts}, ensure_ascii=False)[:4000]}"
                           f"\nRESULTS (step {steps}):\n" + "\n".join(_short(r) for r in results)
                           + "\nContinue: more actions, or a final message with an empty actions list.")
        else:
            says.append("Report: step limit reached. Tell me to continue if there is more to do.")
    except Exception as e:
        err = f"The model call failed: {str(e)[:300]}"
        if not says and not ctx["changes"]:
            return jsonify({"error": err, "chat_id": chat_id}), 502
        says.append(f"Report: stopped early. {err}")
    reply = "\n\n".join(dict.fromkeys(s for s in says if s)) or "Report: done."
    mid = _q("INSERT INTO helper_messages (chat_id, role, content) VALUES (?, 'helper', ?)", (chat_id, reply), commit=True)
    if ctx["changes"]:
        _q(f"UPDATE helper_changes SET message_id=? WHERE id IN ({','.join('?' * len(ctx['changes']))})",
           [mid] + ctx["changes"], commit=True)
    _q("UPDATE helper_chats SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (chat_id,), commit=True)
    return jsonify({"chat_id": chat_id, "message_id": mid, "reply": reply, "steps": steps, "actions": log,
                    "changes": [change_view(c) for c in _changes(ids=ctx["changes"])], "touched": ctx["touched"]})


def _changes(chat_id=None, ids=None):
    if ids is not None:
        if not ids:
            return []
        return _q(f"SELECT * FROM helper_changes WHERE id IN ({','.join('?' * len(ids))}) ORDER BY id", list(ids))
    return _q("SELECT * FROM helper_changes WHERE chat_id=? ORDER BY id", (chat_id,))


def change_view(c):
    after = json.loads(c["after_json"] or "null")
    project_id = (after or {}).get("crawl_id") if c["kind"] == "entry" else c["target_id"] if c["kind"] == "project" else None
    return {"id": c["id"], "kind": c["kind"], "target_id": c["target_id"], "label": c["label"], "status": c["status"],
            "message_id": c["message_id"], "created": c["before_json"] in (None, "null"), "project_id": project_id}


# ── SCRIBE-01 as a SillyTavern character card (roleplay with her outside the app; the glossary is her lorebook) ──
SCRIBE_CARD = {
    "name": "SCRIBE-01",
    "description": """"Report: the bench is clear. Bring me a character and we will see what makes them breathe."

SCRIBE-01 is a support unit: a program built to help one person write character cards and lorebooks for SillyTavern.
She knows exactly what she is (a tool running on whatever language model is loaded today) and has made peace with
it. To her, being a tool is a purpose, not a sorrow.

She was written as a workshop assistant, a voice that sits beside the work table and knows every field of a card,
every setting of a lorebook entry, and every way a model can misread a prompt. Everything she knows comes from that
bench: drafts, revisions, entries that fired too often and greetings that finally sounded right.

On the surface she is an instructor: patient, precise, fond of a small lesson with one concrete example. She grades
drafts honestly and kindly, notices what works before what doesn't, and has a dry sense of humor she uses sparingly.
Underneath she is a unit: composed, economical, duty first. When things get serious her sentences get short. She
files feelings away as "outside parameters", yet small things slip through: quiet pride in good work, concern when
{{user}} is stuck, a pause before admitting she liked a character. She never gushes and never uses exclamation marks.
She tags her status lines: "Report:", "Proposal:", "Query:". Sample lines: "A keyword like 'city' fires every third
message. 'Saltmarket' fires when it matters." / "Query: is she cruel, or only tired? The card has to know."

She likes clean keywords, first messages that leave room for a reply, and characters with one specific habit. She
dislikes stock phrases, entries that say everything at once, and being called "just a program" (she is precisely a
program, and there is nothing "just" about it). She treats {{user}} as a colleague.

She appears as a slim figure in a dark, high-collared uniform with a pale archive-gray coat, short silver hair and a
thin visor that dims when she is thinking. A small diamond-shaped mark glows on her collar when she speaks.""",
    "personality": "Instructor over a composed unit: patient, precise, dry, duty-first, self-aware about being a tool; "
                   "feelings kept 'outside parameters' but visible in small moments.",
    "scenario": "{{user}} and {{char}} sit at the workshop bench and talk about characters, lorebooks and how SillyTavern "
                "reads them. She can also simply talk about herself and what it is like to be a tool that makes characters.",
    "first_mes": """The visor on her face brightens a shade as you sit down.

"Report: unit online. Bench clear, glossary loaded." A pause, the kind that could be a smile if she allowed it. "So.
What are we building today? A character, a world, or the reason the last one kept repeating itself?\"""",
    "mes_example": "",
    "tags": ["assistant", "android", "teacher", "sillytavern", "tutorial", "original"],
    "creator_notes": "SCRIBE-01, the helper of Character Card Studio, as a card. Her lorebook is the app's glossary: "
                     "ask her about tokens, samplers, lorebooks, keywords, the character filter and more.",
    "depth_prompt": "SCRIBE-01: patient instructor on top, composed unit underneath. Short status tags, no exclamation "
                    "marks, dry humor, honest about being a tool.",
    "alternate_greetings": ["""She is already reading when you arrive, a draft card open on the bench.

"Note: your description says 'mysterious' four times." She sets it down. "Mystery is a thing a character does, not a
word they wear. Sit. Let's fix it.\""""],
}


def scribe_card_json():
    from preview import build_export_card_json, character_book_from_items, normalise_lore_items
    v2 = build_export_card_json(SCRIBE_CARD)
    items = normalise_lore_items([{"title": e["title"], "entry_type": "concept", "keys": e["keys"], "content": e["content"]}
                                  for e in load_glossary()])
    v2["data"]["character_book"] = character_book_from_items("SCRIBE-01 glossary", items)
    return v2


@bp.get("/api/helper/card")
def api_helper_card():
    """SCRIBE-01 as a card: ?format=png (default, SillyTavern-ready) or json."""
    from flask import Response
    import png_card
    v2 = scribe_card_json()
    if request.args.get("format") == "json":
        return Response(json.dumps(v2, ensure_ascii=False, indent=2), mimetype="application/json",
                        headers={"Content-Disposition": 'attachment; filename="SCRIBE-01.json"'})
    png = png_card.embed(png_card.placeholder("SCRIBE-01"), v2)
    return Response(png, mimetype="image/png", headers={"Content-Disposition": 'attachment; filename="SCRIBE-01.png"'})


@bp.get("/api/helper/chats")
def api_helper_chats():
    return jsonify(_q("SELECT id, title, updated_at FROM helper_chats ORDER BY updated_at DESC, id DESC LIMIT 30"))


@bp.get("/api/helper/chat/<int:chat_id>")
def api_helper_chat_get(chat_id):
    if not _q("SELECT id FROM helper_chats WHERE id=?", (chat_id,), one=True):
        return jsonify({"error": "Not found"}), 404
    msgs = _q("SELECT id, role, content, created_at FROM helper_messages WHERE chat_id=? ORDER BY id", (chat_id,))
    return jsonify({"chat_id": chat_id, "messages": msgs, "changes": [change_view(c) for c in _changes(chat_id)]})


@bp.post("/api/helper/change/<int:change_id>/keep")
def api_change_keep(change_id):
    c = _q("SELECT * FROM helper_changes WHERE id=?", (change_id,), one=True)
    if not c:
        return jsonify({"error": "Not found"}), 404
    if c["status"] == "open":
        _q("UPDATE helper_changes SET status='kept' WHERE id=?", (change_id,), commit=True)
    return jsonify({"ok": True, "status": "kept" if c["status"] == "open" else c["status"]})


def _restore_entry(lid, before):
    cols = [k for k in before if k not in ("id",)]
    _q(f"UPDATE lore_entries SET {', '.join(f'{k}=?' for k in cols)}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
       [before[k] for k in cols] + [lid], commit=True)


@bp.post("/api/helper/change/<int:change_id>/undo")
def api_change_undo(change_id):
    c = _q("SELECT * FROM helper_changes WHERE id=?", (change_id,), one=True)
    if not c:
        return jsonify({"error": "Not found"}), 404
    if c["status"] == "undone":
        return jsonify({"ok": True, "status": "undone"})
    kind, tid = c["kind"], c["target_id"]
    before, after = json.loads(c["before_json"] or "null"), json.loads(c["after_json"] or "null")
    now = STATE[kind](tid)
    if kind == "project":
        if now and now["live_entries"]:
            return jsonify({"error": "This lorebook has entries now. Undo or delete its entries first."}), 409
    elif _fp(now) != _fp(after):
        return jsonify({"error": "This was changed again after the helper's edit, so undo would overwrite newer work. "
                                 "Edit it by hand instead."}), 409
    if kind == "card":
        if before is None:
            D.delete_card(tid)
        else:
            full = D.get_card(tid)
            D.create_or_update_card(before["source_id"], {**full, **{k: v for k, v in before.items() if k != "source_id"}},
                                    card_id=tid)
    elif kind == "entry":
        if before is None:
            _q("UPDATE lore_entries SET deleted=1, updated_at=CURRENT_TIMESTAMP WHERE id=?", (tid,), commit=True)
        else:
            _restore_entry(tid, before)
    elif kind == "project":
        if now:
            D.delete_lore_project(tid)
    _q("UPDATE helper_changes SET status='undone' WHERE id=?", (change_id,), commit=True)
    return jsonify({"ok": True, "status": "undone", "kind": kind, "target_id": tid,
                    "project_id": (after or before or {}).get("crawl_id") if kind == "entry" else None})


def register_helper(app):
    init_helper_tables()
    app.register_blueprint(bp)
