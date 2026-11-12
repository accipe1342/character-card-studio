"""
lore_extract.py — Deep (multi-pass) entity + event extraction
==============================================================
A single "list everything important" call stalls at a handful of entries:
the model self-limits, the output hits max_tokens, and one truncated JSON
loses the whole chunk. This module avoids that with small, separate calls:

  1. INVENTORY   names + types only (tiny output, can't truncate, no cap)
                 -> entities[] and beats[] (beat = distinct event/scene)
  2. GLEAN       "what did you miss?" up to N rounds, until nothing new
  3. NAME CHECK  plain code (no model): recurring capitalised names in the
                 text that the inventory never mentioned are sent back for
                 confirmation
  4. DETAIL      entities in batches of 5: facts / age / voice for each.
                 A failed batch is split in half and retried.
  5. BEATS       one call turning the beat list into full event records:
                 participants, place, time + flashback flag, state changes,
                 short evidence quote, confidence.

extract_chunk_deep() returns the same shape text_module's quick mode does,
plus `beats` and `stats`, so both modes share merge / review / commit.

Used by: text_module.extract_chunk(mode="deep") and, through
text_module.deep_entries_from_text(), generator.generate_lore_entry(deep=True)
which is what the LORE studio's "Deep extraction" option calls.
"""

import re
import sys
import threading
import time

from generator import _request, load_runtime_config, list_of, text_of

DEEP_MAX_TOKENS = 8000  # fallback; the real value is Config -> 'Deep extraction max tokens'
DETAIL_BATCH = 5
MAX_GLEAN_ROUNDS = 2

ENTITY_TYPES = {"character", "place", "faction", "item", "ability", "concept"}
_TYPE_ALIASES = {
    "rule": "concept", "world": "concept", "organization": "faction", "organisation": "faction",
    "group": "faction", "location": "place", "setting": "place", "object": "item",
    "artifact": "item", "power": "ability", "magic": "ability", "person": "character",
    "npc": "character", "event": "concept",
}

_MINOR_RULE = ("If a character is or appears to be under 18, record their age but do NOT include any "
               "romantic or sexual details about them.")

INVENTORY_SYSTEM = """You inventory a story or wiki text for a lorebook. Return ONLY valid JSON, no fences.
{
  "entities": [{"name": "", "type": "character|place|faction|item|ability|concept", "aliases": []}],
  "beats":    [{"title": "short verb phrase, e.g. 'Elias abandons the clinic'"}]
}
Rules:
- List every named character, place, faction/group, and every distinct item, ability, creature type or world
  rule/concept that matters to the setting, even if mentioned once.
- A recurring character with no name gets a short descriptor as the name (e.g. "the red-scarfed courier"), type character.
- Do NOT list: body parts or bodily fluids ("Mara's hand", "his tail"), sexual or violent acts, emotions or
  feelings, generic furniture or scenery ("floor", "wall", "room", "corner"), clothing worn by one person once,
  pronoun-like nouns ("the girls", "little kid"), or the story's own title. If it is not something a reader
  would look up in a wiki for this world, leave it out.
- Do not list events under entities. Events go in beats.
- A beat is one plot-significant event or scene, NOT every action, gesture or line of dialogue. A change of
  time, place or participants starts a new beat. A flashback is its own beat. The same event retold counts once.
  Expect roughly 3-12 beats per 8,000 characters.
- Names only: no descriptions, no summaries.

"""

GLEAN_SYSTEM = INVENTORY_SYSTEM + """
You are now checking a previous inventory. Return ONLY items from the text that are NOT already in the lists
provided. If nothing is missing return {"entities": [], "beats": []}."""

DETAIL_SYSTEM = """You write lorebook notes. Return ONLY valid JSON, no fences.
{"entities": [{"name": "exactly as given in TARGETS", "aliases": [], "age": "", "facts": "", "voice": [], "keywords": [],
               "origin": "canon|altered|original|", "relations": [{"with": "other character", "relation": "e.g. cousin; teammate"}]}]}
Rules:
- One object per target, in the same order, using the name exactly as given.
- facts: 30-120 words using ONLY what the text says about that target. If the text barely mentions it, one short
  sentence is fine. Never invent.
- age: stated or clearly implied age; empty string if the text gives no basis.
- voice: up to 3 short verbatim dialogue lines (max 25 words each) for characters; [] otherwise.
- keywords: 3-6 trigger words.
- origin: if this text is fan fiction of a known work, "canon" = exists in the original work and is shown as it is
  there; "altered" = exists in the original work but this story changes it (role, powers, history, personality,
  relationships); "original" = invented by this story. Use "" if the text is not fan fiction or you are unsure.
- relations: for characters, up to 5 relationships to other named characters that the text shows; [] otherwise.
- Do not copy long passages. """ + _MINOR_RULE

BEATS_SYSTEM = """You turn a list of beats (events/scenes) into full records. Return ONLY valid JSON, no fences.
{
  "chapter_summary": "1-2 sentences",
  "beats": [{
    "title": "as given",
    "what_happened": "1-3 sentences: action and outcome",
    "participants": ["names"],
    "place": "",
    "when": {"marker": "e.g. 'that night', 'three years earlier'", "flashback": false, "order": "relative to other beats, e.g. 'after <title>' or ''"},
    "state_changes": [{"entity": "name", "change": "what is different after this beat"}],
    "evidence": "a quote of at most 15 words from the text supporting this beat",
    "confidence": "high|medium|low"
  }]
}
Rules:
- One record per beat given, same titles. Use only what the text says.
- If the writing is unclear about who/where/when, leave that field empty and use confidence "low".
- state_changes only for real changes (dies, learns a secret, joins/leaves a group, changes allegiance, is injured, etc.).
- Do not include romantic or sexual details about anyone who is or appears under 18."""

_STOP_CAPS = {
    "The", "A", "An", "He", "She", "They", "It", "I", "We", "You", "His", "Her", "Their", "Its", "Our", "My",
    "But", "And", "Or", "So", "Then", "When", "While", "As", "If", "In", "On", "At", "To", "For", "Of", "With",
    "That", "This", "These", "Those", "There", "Here", "What", "Who", "Where", "Why", "How", "Not", "No", "Yes",
    "After", "Before", "Once", "Now", "Just", "Still", "Even", "Maybe", "Chapter", "Part", "Mr", "Mrs", "Ms", "Dr",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "OK", "Okay", "Oh", "Well",
}
_CAP_RE = re.compile(r"\b[A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+){0,2}")


def _norm(s):
    return re.sub(r"[^\w\s'-]", " ", (s or "").lower()).strip()


def _ntype(t):
    t = _TYPE_ALIASES.get((t or "").strip().lower(), (t or "").strip().lower())
    return t if t in ENTITY_TYPES else "concept"


def _extract_max_tokens():
    try:
        return max(1024, min(int(load_runtime_config().get("extract_max_tokens", DEEP_MAX_TOKENS)), 32768))
    except Exception:
        return DEEP_MAX_TOKENS


_ctx = threading.local()  # which chunk this worker thread is on, for log lines


def _dlog(msg):
    sys.stdout.write(f"[DEEP] {time.strftime('%H:%M:%S')} [{getattr(_ctx, 'label', '')[:40]}] {msg}\n")
    sys.stdout.flush()


def _purpose(system):
    for name, const in (("inventory", "INVENTORY_SYSTEM"), ("glean/check", "GLEAN_SYSTEM"),
                        ("detail", "DETAIL_SYSTEM"), ("beats", "BEATS_SYSTEM")):
        if system is globals().get(const):
            return name
    return "call"


def _call(provider, model, system, user):
    # read each call so changing the Config slider takes effect without a restart
    t0 = time.time()
    what = _purpose(system)
    try:
        res = _request(provider, model, user, system=system, max_tokens=_extract_max_tokens())
    except Exception as e:
        _dlog(f"  {what}: FAILED after {time.time() - t0:.1f}s: {str(e)[:160]}")
        raise
    _dlog(f"  {what}: ok in {time.time() - t0:.1f}s")
    return res


_BODY = (r"cock|dick|penis|pussy|vagina|clit|clitoris|erection|boner|precum|cum|semen|balls|breasts?|tits?|boobs?|nipples?|"
         r"ass|butt|mouth|lips?|tongue|hands?|fists?|fingers?|arms?|legs?|feet|foot|face|eyes?|hair|ponytail|skin|tears?|"
         r"tail|claws?|teeth|neck|chest|back|body|cheeks?|thighs?|waist|hips?")
_ACTS = {"sex", "rape", "blowjob", "handjob", "orgasm", "naked", "nudity", "boredom", "fear", "anger", "joy",
         "sadness", "embarrassment", "arousal", "lust", "pain", "pleasure"}
_SCENERY = {"floor", "wall", "walls", "room", "corner", "ceiling", "door", "window", "pockets", "pocket", "items",
            "item", "weapon", "weapons", "transformation", "ground", "air", "light", "darkness", "silence"}
_BODY_RE = re.compile(r"^(?:(?:the|his|her|their|its|[\w-]+['\u2019]s)\s+)?(?:[\w-]+\s+)?(?:" + _BODY + r")$", re.I)


def _junk_entity(name):
    """True for names that are body parts, acts, feelings or generic scenery, never lorebook entries."""
    n = _norm(name)
    if not n:
        return True
    if n in _ACTS or n in _SCENERY:
        return True
    if _BODY_RE.match(name.strip()):
        return True
    return False


def _merge_inventory(inv, new):
    """Add new entities/beats into inv (dedupe by normalised name/title). Returns count added."""
    known = {_norm(e["name"]) for e in inv["entities"]}
    for e in inv["entities"]:
        known |= {_norm(a) for a in e.get("aliases", [])}
    known_beats = {_norm(b["title"]) for b in inv["beats"]}
    added = 0
    ents = new.get("entities")
    for e in (ents if isinstance(ents, list) else [ents] if isinstance(ents, dict) else list_of(ents)):
        if isinstance(e, str):                   # a bare list of names
            e = {"name": e}
        if not isinstance(e, dict) or not text_of(e.get("name")):
            continue
        e = {**e, "name": text_of(e["name"])}
        n = _norm(e["name"])
        if _junk_entity(str(e["name"])):
            continue
        if n and n not in known:
            known.add(n)
            inv["entities"].append({
                "name": str(e["name"]).strip(), "type": _ntype(e.get("type")),
                "aliases": list_of(e.get("aliases")),
            })
            added += 1
    beats_in = new.get("beats")
    for b in (beats_in if isinstance(beats_in, list) else [beats_in] if beats_in else []):
        title = text_of(b.get("title", "") if isinstance(b, dict) else b)
        if title and _norm(title) not in known_beats:
            known_beats.add(_norm(title))
            inv["beats"].append({"title": title})
            added += 1
    return added


_EXTRA_STOP = {"I", "It", "Its", "Is", "Was", "What", "Whats", "Don", "Doesn", "Didn", "Can", "Won", "Isn", "Aren",
               "Anyway", "Please", "Yeah", "Yes", "No", "Stupid", "Okay", "Ok", "Well", "Oh", "Hey", "We", "You",
               "He", "She", "They", "That", "This", "There", "Here", "But", "And", "So", "Then", "Thanks", "Sorry"}


def name_check(text, inv):
    """Recurring capitalised names in `text` that the inventory never mentions (no model call)."""
    known = set()
    for e in inv["entities"]:
        for n in [e["name"]] + e.get("aliases", []):
            known.add(_norm(n))
            known |= set(_norm(n).split())
    counts = {}
    for m in _CAP_RE.finditer(text):
        # a capital at the start of a sentence/quote proves nothing; only count mid-sentence uses
        before = text[:m.start()].rstrip(" \t")
        if not before or before[-1] in ".!?\u2026:\n\u201c\u201d\"'\u2018\u2019(-\u2014\u2013*":
            continue
        cand = m.group(0).strip()
        # drop possessive / contraction endings (Mara's -> Mara, I'll -> I)
        cand = re.sub(r"[\u2019']\s*(?:s|ll|m|re|ve|d|t)\b", "", cand).strip()
        cand = re.sub(r"\bn$", "", cand).strip()
        words = [w for w in cand.split() if w not in _STOP_CAPS and w not in _EXTRA_STOP]
        if not words:
            continue
        cand = " ".join(words)
        counts[cand] = counts.get(cand, 0) + 1
    missing = []
    for cand, c in sorted(counts.items(), key=lambda x: -x[1]):
        if c < 2:
            continue
        n = _norm(cand)
        if n in known or all(w in known for w in n.split()):
            continue
        missing.append(cand)
    return missing[:25]


def norm_origin(v):
    v = str(v or "").strip().lower()
    return v if v in ("canon", "altered", "original") else ""


_REL_SPLIT = re.compile(r"\s*(?:\u2014|\u2013|=>|->|:|\()\s*|\s+--?\s+")   # a plain hyphen only with spaces (Jean-Luc stays whole)


def norm_relations(v):
    """[{with, relation}] from whatever shape the model used: the asked-for list of objects, other key names
    (name/character/target, relationship/type/role), {"Tomas": "friend"}, or lines like "Tomas - friend"."""
    if isinstance(v, str):
        v = list_of(v)
    if isinstance(v, dict):
        if any(k in v for k in ("with", "name", "character")):
            v = [v]
        else:
            v = [{"with": k, "relation": text_of(x, ", ")} for k, x in v.items()]
    out = []
    for r in v if isinstance(v, list) else []:
        if isinstance(r, str):
            bits = _REL_SPLIT.split(r.strip().rstrip(")"), maxsplit=1)
            r = {"with": bits[0], "relation": bits[1] if len(bits) > 1 else ""}
        if isinstance(r, dict):
            w = text_of(r.get("with") or r.get("name") or r.get("character") or r.get("target") or r.get("who"))
            rel = text_of(r.get("relation") or r.get("relationship") or r.get("type") or r.get("role") or r.get("bond"), ", ")
            if w and rel:
                out.append({"with": w[:80], "relation": rel[:80]})
    return out[:5]


def _inv_text(inv):
    ents = "; ".join(f"{e['name']} ({e['type']})" for e in inv["entities"]) or "(none)"
    beats = "; ".join(b["title"] for b in inv["beats"]) or "(none)"
    return f"ENTITIES FOUND: {ents}\nBEATS FOUND: {beats}"


def _detail_batch(targets, text, label, provider, model):
    names = [t["name"] for t in targets]
    user = (f"TEXT ({label}):\n{text}\n\nTARGETS:\n" +
            "\n".join(f"- {t['name']} ({t['type']})" for t in targets))
    try:
        res = _call(provider, model, DETAIL_SYSTEM, user)
        raw = res.get("entities")
        out = [r for r in (raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []) if isinstance(r, dict)]
        return [(t, match_detail(t, out, i, len(targets)) or {"name": t["name"], "facts": ""})
                for i, t in enumerate(targets)]
    except Exception as e:
        print(f"[DEEP] detail batch failed ({names}): {e}", flush=True)
        if len(targets) > 1:
            mid = len(targets) // 2
            return (_detail_batch(targets[:mid], text, label, provider, model) +
                    _detail_batch(targets[mid:], text, label, provider, model))
        return [(targets[0], {"name": targets[0]["name"], "facts": ""})]


def match_detail(t, out, i, n):
    """The model's detail answer for target t: same name, one of t's aliases, a fuller or shorter form of the name
    ("Mara" / "Mara Vell"), or, when it answered exactly as many as were asked, the one in the same position."""
    names = {_norm(t["name"])} | {_norm(a) for a in t.get("aliases") or []}
    by = {_norm(text_of(r.get("name"))): r for r in out}
    for k in names:
        if k in by:
            return by[k]
    tn = _norm(t["name"])
    for k, r in by.items():
        if k and tn and (k.startswith(tn + " ") or tn.startswith(k + " ") or k.endswith(" " + tn)):
            return r
    if len(out) == n and i < n and not text_of(out[i].get("name")):
        return out[i]
    if len(out) == n == 1:
        return out[0]
    return None


def extract_chunk_deep(chunk, provider, model, glean_rounds=MAX_GLEAN_ROUNDS):
    """chunk: {label, text}. Returns {chapter_summary, entities[], beats[], stats{}}."""
    text, label = chunk["text"], chunk["label"]
    _ctx.label = label
    t_start = time.time()
    _dlog(f"deep extract start ({len(text):,} chars)")
    stats = {"inventory": 0, "glean_added": 0, "check_added": 0, "detail_calls": 0}
    user = f"TEXT ({label}):\n{text}"

    # 1. inventory
    inv = {"entities": [], "beats": []}
    _merge_inventory(inv, _call(provider, model, INVENTORY_SYSTEM, user))
    stats["inventory"] = len(inv["entities"]) + len(inv["beats"])
    _dlog(f"inventory: {len(inv['entities'])} entities, {len(inv['beats'])} events")

    # 2. gleaning
    for _ in range(max(0, glean_rounds)):
        try:
            res = _call(provider, model, GLEAN_SYSTEM, f"{_inv_text(inv)}\n\n{user}")
        except Exception as e:
            print(f"[DEEP] glean failed: {e}", flush=True)
            break
        added = _merge_inventory(inv, res)
        stats["glean_added"] += added
        _dlog(f"gleaning: +{added} (now {len(inv['entities'])} entities, {len(inv['beats'])} events)")
        if not added:
            break

    # 3. deterministic name check
    missing = name_check(text, inv)
    if missing:
        _dlog(f"name check: {len(missing)} capitalised names not in the lists: {', '.join(missing[:8])}")
        try:
            res = _call(provider, model, GLEAN_SYSTEM,
                        f"{_inv_text(inv)}\n\nThese capitalised names recur in the text but are not in the "
                        f"lists. Add each one that is a real entity (and any beats they imply); ignore "
                        f"false positives: {', '.join(missing)}\n\n{user}")
            stats["check_added"] = _merge_inventory(inv, res)
            _dlog(f"name check added {stats['check_added']}")
        except Exception as e:
            print(f"[DEEP] name-check call failed: {e}", flush=True)

    # 4. details in batches
    entities = []
    for i in range(0, len(inv["entities"]), DETAIL_BATCH):
        batch = inv["entities"][i:i + DETAIL_BATCH]
        stats["detail_calls"] += 1
        _dlog(f"detail batch {stats['detail_calls']}/{-(-len(inv['entities']) // DETAIL_BATCH)}: "
              + ", ".join(e["name"] for e in batch))
        for t, r in _detail_batch(batch, text, label, provider, model):
            entities.append({
                "name": t["name"],
                "aliases": list(dict.fromkeys(t.get("aliases", []) + list_of(r.get("aliases")))),
                "type": t["type"],
                "age": text_of(r.get("age")),
                "facts": text_of(r.get("facts")) or f"Mentioned in {label}.",
                "voice": list_of(r.get("voice"), split=False)[:3],
                "keywords": list_of(r.get("keywords")),
                "origin": norm_origin(r.get("origin")),
                "relations": norm_relations(r.get("relations")),
            })

    # 5. beats
    beats, summary = [], ""
    if inv["beats"]:
        try:
            res = _call(provider, model, BEATS_SYSTEM,
                        f"TEXT ({label}):\n{text}\n\nBEATS:\n" + "\n".join(f"- {b['title']}" for b in inv["beats"]))
            summary = text_of(res.get("chapter_summary"))
            raw_beats = res.get("beats")
            for b in (raw_beats if isinstance(raw_beats, list) else [raw_beats] if isinstance(raw_beats, dict) else []):
                if not isinstance(b, dict) or not text_of(b.get("title")):
                    continue
                when = b.get("when") if isinstance(b.get("when"), dict) else {}
                beats.append({
                    "title": text_of(b["title"]),
                    "what_happened": text_of(b.get("what_happened")),
                    "participants": list_of(b.get("participants")),
                    "place": text_of(b.get("place")),
                    "marker": text_of(when.get("marker") or b.get("marker")),
                    "flashback": bool(when.get("flashback")),
                    "order": text_of(when.get("order")),
                    "state_changes": [
                        {"entity": text_of(s.get("entity")), "change": text_of(s.get("change"))}
                        for s in (b.get("state_changes") if isinstance(b.get("state_changes"), list) else [])
                        if isinstance(s, dict) and text_of(s.get("entity")) and text_of(s.get("change"))
                    ],
                    "evidence": text_of(b.get("evidence"))[:200],
                    "confidence": text_of(b.get("confidence")).lower() or "medium",
                })
        except Exception as e:
            print(f"[DEEP] beats call failed: {e}", flush=True)
            _dlog("beats failed - keeping the event titles from the inventory (title only) so nothing is lost")
            stats["degraded"] = True
            for b in inv["beats"]:
                beats.append({"title": b["title"], "what_happened": "", "participants": [], "place": "",
                              "marker": "", "flashback": False, "order": "", "state_changes": [],
                              "evidence": "", "confidence": "low"})
    if not summary and beats:
        summary = " ".join(b["what_happened"] for b in beats[:3] if b["what_happened"])[:300]

    stats["entities"], stats["beats"] = len(entities), len(beats)
    _dlog(f"deep extract done in {time.time() - t_start:.1f}s: {len(entities)} entities, {len(beats)} events, "
          f"{stats['detail_calls']} detail call(s)")
    return {"chapter_summary": summary, "entities": entities, "beats": beats, "stats": stats}


def source_to_text(source):
    """Flatten a scraped wiki/page source dict into plain text for deep extraction."""
    parts = []
    norm = source.get("normalized") or {}
    title = source.get("title") or norm.get("title") or ""
    if title:
        parts.append(f"Chapter: {title}")
    if norm.get("summary"):
        parts.append(norm["summary"])
    ib = norm.get("normalized_infobox") or source.get("raw_infobox") or {}
    if ib:
        parts.append("\n".join(f"{k}: {v}" for k, v in ib.items()))
    secs = source.get("raw_sections") or norm.get("raw_sections") or {}
    for heading, paras in secs.items():
        body = "\n\n".join(paras) if isinstance(paras, list) else str(paras)
        if body.strip():
            parts.append(f"{heading}\n\n{body}")
    text = "\n\n".join(p for p in parts if p and p.strip())
    return text or str(source.get("raw_text") or source.get("content") or "")
