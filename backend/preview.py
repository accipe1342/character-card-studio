"""
preview.py — Structured profile text formatter
===============================================
Converts a card's structured_profile dict into a formatted plain-text
string used in the "include fields in image" export feature and as
context when regenerating individual fields.

MAIN ENTRY POINT
----------------
format_structured_profile_text(name, profile) -> str
    Takes the card name and a structured_profile dict and returns a
    human-readable multi-line string. Each field is formatted as:
        FieldName ("value")
    List fields (appearance, clothing, abilities, etc.) are formatted as:
        FieldName ("item1" + "item2" + "item3")

USAGE
-----
from preview import format_structured_profile_text

text = format_structured_profile_text(card["name"], card["structured_profile"])

HOW TO EXTEND
-------------
- Add a new field: add a line in format_structured_profile_text()
  following the same pattern as existing fields. Make sure the key
  matches what's in DEFAULT_STRUCTURED_PROFILE in database.py.
- Change the format: edit the f-string patterns in q() and join_items().
  The output format should remain parseable by the AI — avoid markdown.
"""

from typing import Any, Dict


def format_structured_profile_text(name: str, profile: Dict[str, Any]) -> str:
    def q(value: str) -> str:
        return (value or "").replace('"', '\\"')

    def join_items(items: list[str]) -> str:
        if not items:
            return '""'
        return " + ".join(f'"{item}"' for item in items)

    lines = [
        f'Name ("{q(name)}")',
        f'Sex ("{q(profile.get("sex", ""))}")',
        f'Species ("{q(profile.get("species", "") or profile.get("ethnicity", ""))}")',
        f'Ethnicity ("{q(profile.get("ethnicity", ""))}")',
        f'Race ("{q(profile.get("race", ""))}")',
        f'Job/Occupation ("{q(profile.get("job_occupation", ""))}")',
        f'Gender ("{q(profile.get("gender", ""))}")',
        f'Sexual Attraction ("{q(profile.get("sexual_attraction", ""))}")',
        f'Pronouns ("{q(profile.get("pronouns", ""))}")',
        f'Appearance ({join_items(profile.get("appearance", []))})',
        f'Non Human Appearances ({join_items(profile.get("non_human_appearance", []))})',
        f'Personal Parts ({join_items(profile.get("personal_parts", []))})',
        f'Clothing ({join_items(profile.get("clothing", []))})',
        f'Accessories ({join_items(profile.get("accessories", []))})',
        f'Description of Relationship to {{{{User}}}} ("{q(profile.get("relationship_to_user", ""))}")',
        f'Relationship Status ("{q(profile.get("relationship_status", ""))}")',
        f'Backstory ("{q(profile.get("backstory", ""))}")',
        f'Speech ({join_items(profile.get("speech", []))})',
        f'Personality ({join_items(profile.get("personality_traits", []))})',
        f'Kinks ({join_items(profile.get("kinks", []))})',
        f'Likes ({join_items(profile.get("likes", []))})',
        f'Dislikes ({join_items(profile.get("dislikes", []))})',
        f'Loves ({join_items(profile.get("loves", []))})',
        f'Hates ({join_items(profile.get("hates", []))})',
        f'Height ("{q(profile.get("height", ""))}")',
        f'Weight ("{q(profile.get("weight", ""))}")',
        f'Age ("{q(profile.get("age", ""))}")',
    ]
    # newer profile fields: only printed when filled, so older cards export exactly as before
    for label, key in (("Motivations", "motivations"), ("Flaws", "flaws"), ("Mannerisms", "mannerisms"),
                       ("Relationships", "relationships")):
        if profile.get(key):
            lines.append(f'{label} ({join_items(profile.get(key, []))})')
    if profile.get("story_point"):
        lines.append(f'Story Point ("{q(profile.get("story_point", ""))}")')
    return "\n".join(lines)


def _s(value: Any) -> str:
    """Coerce to a plain string (None -> '')."""
    return "" if value is None else str(value)


def _str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [v for v in value.split(",")]
    if not isinstance(value, (list, tuple)):
        return []
    return [_s(v).strip() for v in value if _s(v).strip()]


def build_export_card_json(card: Dict[str, Any], structured: bool = False) -> Dict[str, Any]:
    """
    Build a Character Card V2 object (spec: chara_card_v2) that imports on
    SillyTavern, Chub, and other V2-validating sites.

    structured=True puts the formatted structured profile text in
    `description` (the structured fields are the card's source of truth in
    that view). The raw structured_profile is always kept in extensions.

    Used by: GET /export/<id>, POST /api/export/v2 (JSON download and the
    PNG `chara` chunk both call this, so they can never diverge).
    """
    profile = card.get("structured_profile") or {}
    name = _s(card.get("name")).strip() or "Unnamed"
    description = _s(card.get("description"))
    if structured and profile:
        description = format_structured_profile_text(name, profile)

    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": name,
            "description": description,
            "personality": _s(card.get("personality")),
            "scenario": _s(card.get("scenario")),
            "first_mes": _s(card.get("first_mes")),
            "mes_example": _s(card.get("mes_example")),
            "creator_notes": _s(card.get("creator_notes")) or "Generated and edited in local Character Card Studio.",
            "system_prompt": _s(card.get("system_prompt")),
            "post_history_instructions": _s(card.get("post_history_instructions") or card.get("post_history")),
            "alternate_greetings": _str_list(card.get("alternate_greetings")),
            "tags": _str_list(card.get("tags")),
            "creator": _s(card.get("creator")),
            "character_version": _s(card.get("character_version")) or "1.0",
            "extensions": {
                "talkativeness": "0.5",
                "fav": False,
                "world": "",
                # Character's Note: injected at depth 4 to keep the character consistent in long chats
                "depth_prompt": {"prompt": _s(card.get("depth_prompt") or card.get("character_note")), "depth": 4, "role": "system"},
                "structured_profile": profile,
            },
        },
    }


# ---------------------------------------------------------------------------
# Lorebook helpers shared by the World Info export, embedded character_book and the narrator card
# ---------------------------------------------------------------------------
def layer_defaults(entry_type: str, idx: int) -> Dict[str, Any]:
    """Insertion defaults by entry type: concepts (world rules) first, then factions, characters, the rest."""
    if entry_type == "concept":
        return {"order": max(1, 950 - idx), "position": 0,
                "preventRecursion": True, "excludeRecursion": False, "constant": False}
    if entry_type == "faction":
        return {"order": max(1, 800 - idx), "position": 0,
                "preventRecursion": False, "excludeRecursion": False, "constant": False}
    if entry_type == "character":
        return {"order": max(1, 500 - idx), "position": 1,
                "preventRecursion": False, "excludeRecursion": False, "constant": False}
    return {"order": max(1, 200 - idx), "position": 1,
            "preventRecursion": True, "excludeRecursion": False, "constant": False}


ALWAYS_ON_TITLES = ("Story So Far", "Cast Roster", "Relationships")
POSITION_NAMES = {0: "before_char", 1: "after_char", 2: "an_top", 3: "an_bottom", 4: "at_depth",
                  5: "em_top", 6: "em_bottom", 7: "outlet"}
CHARACTER_STICKY = 2     # r/SillyTavernAI tip: keep a character's entry in context for a couple of messages


def _opt_int(v, lo=None, hi=None):
    """int or None (None = 'use the default for this entry type')."""
    if v is None or v == "":
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def normalise_lore_items(raw):
    """raw: [{title, entry_type, keys, content, summary?, order?(manual), + optional World Info fields}] in id order
    -> items with defaults. WI fields left as None get the default for the entry type."""
    out, layer_count = [], {}
    for i, r in enumerate(raw):
        et = r.get("entry_type") or "concept"
        layer = et if et in ("concept", "faction", "character") else "other"
        li = layer_count.get(layer, 0)
        layer_count[layer] = li + 1
        d = layer_defaults(et, li)
        d["sticky"] = CHARACTER_STICKY if et == "character" else 0
        title = r.get("title", "")
        if title in ALWAYS_ON_TITLES:   # the recap and the cast list must always be in context
            d = {**d, "constant": True, "order": {"Story So Far": 999, "Cast Roster": 998}.get(title, 997), "position": 0,
                 "preventRecursion": True, "sticky": 0}
        constant = r.get("constant")
        position = _opt_int(r.get("position"), 0, 7)
        sticky = _opt_int(r.get("sticky"), 0, 1000)
        sec = [str(k).strip() for k in (r.get("secondary_keys") or []) if str(k).strip()]
        out.append({
            "uid": i, "title": title, "entry_type": et, "keys": list(r.get("keys") or []),
            "content": r.get("content", ""), "summary": r.get("summary", "") or "",
            "constant": bool(constant) if constant is not None else d["constant"],
            "order": int(r["order"]) if r.get("order") is not None else d["order"],
            "position": position if position is not None else d["position"],
            "preventRecursion": d["preventRecursion"], "excludeRecursion": d["excludeRecursion"],
            "depth": int(r.get("depth") if r.get("depth") is not None else 4),
            "scanDepth": int(r.get("scan_depth") or 4),
            "role": _opt_int(r.get("role"), 0, 2) or 0,
            "probability": _opt_int(r.get("probability"), 0, 100) if r.get("probability") is not None else 100,
            "sticky": sticky if sticky is not None else d["sticky"],
            "cooldown": _opt_int(r.get("cooldown"), 0, 1000) or 0,
            "delay": _opt_int(r.get("delay"), 0, 1000) or 0,
            "secondaryKeys": sec,
            "selectiveLogic": _opt_int(r.get("selective_logic"), 0, 3) or 0,
            "group": str(r.get("group_name") or "").strip(),
            "groupWeight": _opt_int(r.get("group_weight"), 1, 1000) or 100,
            "groupOverride": bool(r.get("group_prioritize")),
            "vectorized": bool(r.get("vectorized")),
            "characterFilter": [str(n).strip() for n in (r.get("char_filter") or []) if str(n).strip()],
        })
    return out


def world_info_entry(it) -> Dict[str, Any]:
    """One entry of a SillyTavern World Info JSON file (the 'entries' object)."""
    i = it["uid"]
    return {
        "uid": i, "key": it["keys"], "keysecondary": it["secondaryKeys"],
        "comment": f"{it['title']} - {it['entry_type']}", "content": it["content"],
        "constant": it["constant"], "vectorized": it["vectorized"],
        "selective": bool(it["secondaryKeys"]), "selectiveLogic": it["selectiveLogic"], "addMemo": True,
        "order": it["order"], "position": it["position"], "disable": False,
        "excludeRecursion": it["excludeRecursion"], "preventRecursion": it["preventRecursion"],
        "delayUntilRecursion": False,
        "probability": it["probability"], "useProbability": True,
        "depth": it["depth"], "role": it["role"] if it["position"] == 4 else None,
        # a shared group makes SillyTavern inject only one entry of that group (the inclusion-group lottery)
        "group": it["group"], "groupOverride": it["groupOverride"], "groupWeight": it["groupWeight"],
        "useGroupScoring": None,
        "scanDepth": it["scanDepth"], "caseSensitive": None, "matchWholeWords": None,
        "automationId": "", "displayIndex": i,
        "sticky": it["sticky"], "cooldown": it["cooldown"], "delay": it["delay"],
        "characterFilter": {"isExclude": False, "names": it["characterFilter"], "tags": []},
    }


def world_info_book(name: str, items) -> Dict[str, Any]:
    return {"name": name, "scan_depth": 4, "token_budget": 2048, "recursive_scanning": True,
            "entries": {str(it["uid"]): world_info_entry(it) for it in items}}


def character_book_from_items(name: str, items) -> Dict[str, Any]:
    """V2 card data.character_book built from normalised lore items (SillyTavern reads the extensions back)."""
    return {
        "name": name, "description": "", "scan_depth": 4, "token_budget": 2048,
        "recursive_scanning": True, "extensions": {},
        "entries": [{
            "id": it["uid"], "keys": it["keys"], "secondary_keys": it["secondaryKeys"],
            "comment": f"{it['title']} - {it['entry_type']}",
            "name": it["title"], "content": it["content"], "constant": it["constant"],
            "selective": bool(it["secondaryKeys"]),
            "enabled": True, "insertion_order": it["order"], "priority": it["order"], "case_sensitive": False,
            "position": "before_char" if it["position"] == 0 else "after_char",
            "extensions": {"position": it["position"], "depth": it["depth"], "scan_depth": it["scanDepth"],
                           "role": it["role"], "selectiveLogic": it["selectiveLogic"],
                           "prevent_recursion": it["preventRecursion"], "exclude_recursion": it["excludeRecursion"],
                           "delay_until_recursion": False, "display_index": it["uid"],
                           "probability": it["probability"], "useProbability": True,
                           "group": it["group"], "group_override": it["groupOverride"],
                           "group_weight": it["groupWeight"], "use_group_scoring": None,
                           "sticky": it["sticky"], "cooldown": it["cooldown"], "delay": it["delay"],
                           "vectorized": it["vectorized"], "match_whole_words": None, "case_sensitive": None,
                           "automation_id": "",
                           "character_filter": {"isExclude": False, "names": it["characterFilter"], "tags": []}},
        } for it in items],
    }


def build_export_card_v3(card: Dict[str, Any], structured: bool = False) -> Dict[str, Any]:
    """Character Card V3 (chara_card_v3): the V2 data plus V3 fields. SillyTavern reads the V2 `chara` PNG chunk;
    V3-aware sites read `ccv3`, so PNG exports carry both."""
    import time as _time
    v2 = build_export_card_json(card, structured=structured)
    data = dict(v2["data"])
    now = int(_time.time())
    data.update({
        "nickname": _s(card.get("nickname")),
        "group_only_greetings": _str_list(card.get("group_only_greetings")),
        "creation_date": int(card.get("creation_date") or now),
        "modification_date": now,
        "source": [],
        "assets": [{"type": "icon", "uri": "ccdefault:", "name": "main", "ext": "png"}],
    })
    return {"spec": "chara_card_v3", "spec_version": "3.0", "data": data}
