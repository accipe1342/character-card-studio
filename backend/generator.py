"""
generator.py - AI card and lore generation
===========================================
Sends prompts to the configured AI provider and parses the response
into structured data. Supports three providers: NanoGPT, OpenRouter,
and any OpenAI-compatible local server (LM Studio, Ollama, KoboldCPP).

MAIN ENTRY POINTS
-----------------
generate_full_card(source, provider, model, use_config=True) -> dict
    Takes a normalised source dict from scraper.py and generates a
    complete SillyTavern V2 character card. Returns a dict with keys:
    name, description, personality, scenario, first_mes, mes_example,
    tags, structured_profile.

regenerate_single_field(source, card, field_name, provider, model, ...) -> dict
    Regenerates a single field of an existing card in context of the
    full card. Returns the new field value as a dict.

generate_lore_entry(source, provider, model, ...) -> dict
    Generates a single lore entry from a source with valid/reason
    validation. Returns dict with valid, reason, entry keys.

PROVIDER ROUTING
----------------
_request(provider, model, system, prompt) -> dict
    Internal function. Takes separate system and user messages.
    All generation functions call this.

    Provider strings:  "nanogpt" | "openrouter" | "local"

HOW TO EXTEND
-------------
- Add a new provider: add a branch in _build_request().
- Change the card format: edit CHARACTER_CARD_DEFINITION and the
  prompt in generate_full_card().
- Add a new structured field: add to DEFAULT_STRUCTURED_PROFILE in
  database.py AND add to the prompt in generate_full_card().
- Adjust retry/timeout: edit _RETRY_MAX_ATTEMPTS and TIMEOUT_SECONDS.
"""

from pathlib import Path
import json
import os
import re
import time
from typing import Any, Dict, Optional
from prompt_templates import get_prompt_templates
import requests
from dotenv import load_dotenv
from requests.exceptions import Timeout

load_dotenv()

_RESET = "\033[0m"; _BOLD = "\033[1m"
_CYAN = "\033[36m"; _GREEN = "\033[32m"
_YELLOW = "\033[33m"; _DIM = "\033[2m"
def _log_info(m):  print(f"{_CYAN}[.]{_RESET} {m}")
def _log_ok(m):    print(f"{_GREEN}[OK]{_RESET} {_BOLD}{m}{_RESET}")
def _log_warn(m):  print(f"{_YELLOW}[!]{_RESET} {m}")
def _log_dim(m):   print(f"{_DIM}{m}{_RESET}")

NANOGPT_URL      = "https://nano-gpt.com/api/v1/chat/completions"
OPENROUTER_URL   = "https://openrouter.ai/api/v1/chat/completions"
NANOGPT_MODEL    = os.getenv("NANOGPT_MODEL", "zai-org/glm-4.7:thinking")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "z-ai/glm-4.7")
OPENROUTER_ENABLE_REASONING = True
TEMPERATURE      = 0.7
LOCAL_BASE_URL   = os.getenv("LOCAL_OPENAI_BASE_URL", "http://localhost:1234/v1")
LOCAL_MODEL      = os.getenv("LOCAL_MODEL", "")
LOCAL_API_KEY    = os.getenv("LOCAL_API_KEY", "local")
TIMEOUT_SECONDS  = 180

_RETRY_MAX_ATTEMPTS   = 3
_RETRY_BACKOFF_SECONDS = [2, 4]
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

REQUIRED_KEYS = {
    "name", "structured_profile", "description",
    "personality", "scenario", "first_mes", "mes_example", "tags",
}


# -------------------------------------------------------------------------------
# DEFINITIONS  (injected as system context)
# -------------------------------------------------------------------------------

LOREBOOK_DEFINITION = """
### WORLDINFO (LOREBOOK) DEFINITION

A Lorebook is a collection of entries that give an AI consistent, contextual
information about a fictional world during roleplay or storytelling.

**Standard Entry Structure:**
- `title`: Short, specific name for the entry (e.g. "Seraph Voss", "The Ashen Blade")
- `entry_type`: One of: character | ability | item | faction | place | event | concept
- `keywords`: 2-6 strong trigger words. Include the name + common aliases.
  Good: ["Seraph Voss", "Voss", "the Ashen Commander"]
  Bad: ["main", "character", "important"]
- `summary`: 1-2 sentence overview. Used for browsing, not injected into context.
- `content`: 100-300 word encyclopedic, in-universe summary. Use plain prose.
  Focus on: who/what it is, key relationships, why it matters to the world.
  Ignore gameplay mechanics unless they are core to the lore.

**Example entry:**
{
  "title": "The Hollow Citadel",
  "entry_type": "place",
  "keywords": ["Hollow Citadel", "the Citadel", "Voss's fortress"],
  "summary": "A ruined fortress at the edge of the Ashfields, now seat of Seraph Voss.",
  "content": "Once the seat of the old empire, the Hollow Citadel fell during the Sundering and lay abandoned for three centuries. Seraph Voss claimed it as her base of operations after her exile from the Council of Flames. Its walls are reinforced with shardite ore, rendering them impervious to conventional siege weapons. The citadel houses her elite unit, the Ashguard, and serves as the staging ground for her campaign against the eastern territories. Locals avoid the surrounding Ashfields, believing the citadel cursed."
}

**Validation:**
Before generating, check if the source page is actually a detailed article
about a single subject. Set `valid: false` for:
- List/index/category pages
- Disambiguation pages
- Pages that only mention the subject in passing
""".strip()


CHARACTER_CARD_DEFINITION = """
### CHARACTER CARD DEFINITION

A Character Card defines a fictional character for AI roleplay. Each field
serves a specific purpose - fill them with that purpose in mind.

**`name`**
The character's primary identifier. Use their most commonly known name.
Example: "Seraph Voss" not "Commander Seraph Voss of the Ashguard (formerly known as...)"

**`description`**
A snapshot combining appearance, personality, and key traits. Structure:
- Appearance: physical traits (silver-streaked hair, burn scar across jaw, worn leather pauldron)
- Personality: core demeanor (calculating, dry-humored, intensely private)
- Mannerisms: unique habits that make them feel real (drums fingers when thinking, never sits with her back to a door)
Keep it vivid and concise. Prioritise traits that affect roleplay.

**`personality`**
How the character thinks and behaves - the core of who they are. Include:
- Core traits (e.g. "commands loyalty through fear and respect in equal measure")
- Motivations and goals (reclaim her title, expose the Council's corruption)
- Flaws and contradictions (ruthless in strategy, but can't abandon soldiers she's bonded with)
- How they treat {{user}} (wary at first, tests loyalty before showing any warmth)
Write in third person, behaviorally. Avoid adjective lists.

**`scenario`**
Sets the stage for the interaction. Include:
- Where and when the scene takes place (the war tent outside Ashfield Gate, eve of the siege)
- The character's current situation or goal (needs information {{user}} carries)
- The relationship or dynamic with {{user}} (uneasy alliance, neither fully trusts the other)
Ground it in canon. Keep it immersive, not a plot summary.

**`first_mes`**
The character's opening line. It must:
- Establish their voice and speech style immediately
- Include subtle action or body language (*doesn't look up from the map*)
- End with a hook that invites the user to respond
Never use a passive opening like "Hello, how can I help you?"
Example: *Seraph doesn't look up from the map pinned across the table.* "You're late. Sit down and tell me what you saw at the eastern pass — and leave out the parts you think I want to hear."

**`mes_example`**
3-6 example exchanges showing the character's range. Format:
<START>
{{char}}: [in-character line with action + dialogue]

Show different moods: commanding, sardonic, briefly vulnerable, cold.
Never write {{user}} lines. Each block starts with <START>.

**`structured_profile`**
Factual fields extracted directly from source. Only fill fields with
clear source support - leave blank rather than invent.
List fields (appearance, clothing, etc.) use short, specific phrases.
""".strip()


# -------------------------------------------------------------------------------
# JSON helpers
# -------------------------------------------------------------------------------

def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = _strip_code_fences(text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        candidate = match.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        try:
            from json_repair import repair_json
            repaired = repair_json(candidate, return_objects=True)
            if isinstance(repaired, dict):
                _log_warn("JSON repaired - model returned malformed response")
                return repaired
        except Exception as repair_err:
            _log_dim(f"  repair attempt failed: {repair_err}")

    try:
        from json_repair import repair_json
        repaired = repair_json(text, return_objects=True)
        if isinstance(repaired, dict):
            _log_warn("JSON repaired (full text fallback)")
            return repaired
    except Exception:
        pass

    raise ValueError(
        f"Model response could not be parsed as JSON even after repair attempt. "
        f"Raw: {text[:1200]}"
    )


def _ensure_list(value: Any) -> list:
    """Normalise a value to a list - handles JSON strings, None, scalars."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        return [value] if value.strip() else []
    return []


def load_runtime_config():
    try:
        with open(Path(__file__).resolve().parent / "config" / "settings.json", "r") as f:
            return json.load(f)
    except Exception:
        return {"use_templates": False, "temperature": 0.7, "max_tokens": 4096}


# -------------------------------------------------------------------------------
# Provider layer  (now accepts separate system + user messages)
# -------------------------------------------------------------------------------

def get_nanogpt_key() -> str:
    return os.getenv("NANOGPT_API_KEY", "")


def get_openrouter_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "")


def _build_messages(system: str, user: str) -> list:
    """Build the messages array from separate system and user strings."""
    return [
        {"role": "system", "content": system.strip()},
        {"role": "user",   "content": user.strip()},
    ]


def _build_request(
    provider: str, model: str, system: str, user: str,
    temperature: float = TEMPERATURE, max_tokens: int = 4096
):
    """Return (url, headers, payload) for the given provider."""
    messages = _build_messages(system, user)

    if provider == "nanogpt":
        api_key = get_nanogpt_key()
        if not api_key:
            raise ValueError("Missing NANOGPT_API_KEY environment variable.")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or NANOGPT_MODEL,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
            "max_tokens": max_tokens,
        }
        return NANOGPT_URL, headers, payload

    elif provider == "openrouter":
        api_key = get_openrouter_key()
        if not api_key:
            raise ValueError("Missing OPENROUTER_API_KEY environment variable.")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "Character Card Studio",
        }
        payload = {
            "model": model or OPENROUTER_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if OPENROUTER_ENABLE_REASONING:
            payload["reasoning"] = {"enabled": True}
        return OPENROUTER_URL, headers, payload

    elif provider == "local":
        base_url = LOCAL_BASE_URL.rstrip("/")
        headers = {
            "Authorization": f"Bearer {LOCAL_API_KEY or 'local'}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or LOCAL_MODEL or "local-model",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        return f"{base_url}/chat/completions", headers, payload

    else:
        _log_warn(f"Unknown provider '{provider}', treating as local OpenAI-compatible")
        base_url = LOCAL_BASE_URL.rstrip("/")
        headers = {
            "Authorization": f"Bearer {LOCAL_API_KEY or 'local'}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or LOCAL_MODEL or provider,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        return f"{base_url}/chat/completions", headers, payload


def _request(
    provider: str,
    model: str,
    prompt: str,
    system: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a request to the provider. Accepts either:
      - _request(provider, model, prompt)              - legacy single-message
      - _request(provider, model, prompt, system=...)  - system + user split
    """
    import traceback

    provider = (provider or "").strip().lower()
    _log_info(f"Request  ->  {provider}/{model or '(default)'}")

    # If no explicit system message, use the old single-message style
    effective_system = system if system is not None else "Return only valid JSON. No markdown fences."

    # Read temperature and max_tokens from settings.json
    cfg = load_runtime_config()
    cfg_temperature = float(cfg.get("temperature", TEMPERATURE))
    cfg_max_tokens = int(cfg.get("max_tokens", 4096))

    url, headers, payload = _build_request(
        provider, model, effective_system, prompt,
        temperature=cfg_temperature, max_tokens=cfg_max_tokens,
    )

    last_exception: Exception = RuntimeError("No attempts made")

    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        if attempt > 1:
            wait = _RETRY_BACKOFF_SECONDS[attempt - 2]
            _log_warn(f"attempt {attempt}/{_RETRY_MAX_ATTEMPTS} - waiting {wait}s")
            time.sleep(wait)

        try:
            _log_dim(f"  -> sending (attempt {attempt})")
            response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT_SECONDS)
            _log_dim(f"  <- {response.status_code}")

            if response.status_code in _RETRYABLE_STATUS_CODES:
                msg = f"HTTP {response.status_code} from {provider} (attempt {attempt})"
                _log_warn(msg)
                last_exception = RuntimeError(msg)
                continue

            response.raise_for_status()

            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return _extract_json_object(content)

        except Timeout:
            msg = (
                f"{provider} request timed out on attempt {attempt}. "
                "Try a faster model, or a smaller prompt."
            )
            _log_warn(msg)
            last_exception = RuntimeError(msg)

        except (ValueError, RuntimeError):
            raise

        except Exception as exc:
            traceback.print_exc()
            last_exception = exc

    raise RuntimeError(
        f"{provider} request failed after {_RETRY_MAX_ATTEMPTS} attempts. "
        f"Last error: {last_exception}"
    ) from last_exception


# -------------------------------------------------------------------------------
# Character card generation
# -------------------------------------------------------------------------------

def generate_full_card(
    source: Dict[str, Any], provider: str, model: str
) -> Dict[str, Any]:
    """
    Generate a complete SillyTavern V2 character card from a scraped source.
    Uses system/user message split: definitions in system, source in user.
    """
    # Trim source to key fields - avoid sending huge normalized blobs
    normalized = source.get("normalized", {})
    # Pull ability-related uncategorized sections (e.g. "Soulcalibur VI", "Fighting Style")
    uncategorized = normalized.get("uncategorized_sections") or source.get("uncategorized_sections", {})
    ability_keywords = {"attack", "moveset", "move", "skill", "power", "ability", "technique",
                        "magic", "spell", "art", "fighting", "combat", "gameplay", "weapon"}
    extra_abilities_card = {
        k: v[:3] for k, v in (uncategorized.items() if isinstance(uncategorized, dict) else {}.items())
        if any(kw in k.lower() for kw in ability_keywords)
    }

    compact_source = {
        "title":             normalized.get("title", ""),
        "summary":           normalized.get("summary", ""),
        "franchise":         normalized.get("franchise", ""),
        "normalized_infobox": normalized.get("normalized_infobox", {}),
        "appearance_list":   normalized.get("appearance_list", [])[:15],
        "personality_traits": normalized.get("personality_traits", [])[:15],
        "abilities_list":    normalized.get("abilities_list", [])[:15],
        "history_list":      normalized.get("history_list", [])[:12],
        "relationships":     normalized.get("relationships", [])[:10],
        "speech_patterns":   normalized.get("speech_patterns", [])[:8],
    }
    if extra_abilities_card:
        compact_source["extra_ability_sections"] = extra_abilities_card

    # If personality/appearance/abilities are sparse, pull from uncategorized sections
    # This handles wikis where all content is in event/game-named sections (e.g. Resident Evil)
    personality_sparse = not normalized.get("personality_traits") and not normalized.get("personality")
    appearance_sparse = len(normalized.get("appearance_list", [])) <= 2
    if personality_sparse or appearance_sparse:
        # Include a trimmed selection of uncategorized sections for context
        uncategorized_trimmed = {}
        char_limit = 0
        for section_name, paragraphs in (uncategorized.items() if isinstance(uncategorized, dict) else {}.items()):
            if section_name.lower() in {"bibliography", "sources", "references", "notes", "gallery"}:
                continue
            # Take first 2 paragraphs per section, cap total at ~3000 chars
            trimmed = paragraphs[:2]
            for p in trimmed:
                char_limit += len(p)
            if char_limit > 3000:
                break
            uncategorized_trimmed[section_name] = trimmed
        if uncategorized_trimmed:
            compact_source["story_sections"] = uncategorized_trimmed
    source_json = json.dumps(compact_source, ensure_ascii=False, indent=2)

    templates = get_prompt_templates()
    config = load_runtime_config()
    use_config = config.get("use_templates", False)
    template_text = templates.get("character_generation_template", "").strip()

    # System message: definitions + task rules
    system = f"""{CHARACTER_CARD_DEFINITION}

---

You are converting scraped wiki data into a SillyTavern V2 character card.
Return ONLY valid JSON. No markdown fences. No extra commentary.

RULES:
- Do not invent facts not present in the source.
- Stay canon-consistent. Rewrite for roleplay, not wiki style.
- Make personality behavioral - not a list of adjectives.
- first_mes must be short, natural, and in character.
- Do not write actions or dialogue for {{{{user}}}}.
- mes_example must contain 3-6 examples. Exact format as a JSON string:
  "<START>\\n{{{{char}}}}: line one\\n\\n<START>\\n{{{{char}}}}: line two"
  Critical: TWO newlines (\\n\\n) between each block. Never place <START>
  immediately after dialogue on the same line as the previous entry.
  Use \\n for line breaks inside the JSON string.
- scenario: roleplay-ready setup grounded in canon. Describe the situation
  and where the interaction begins. Do not write a full story scene.
- structured_profile: only fill fields the source directly supports.
  For list fields, use short specific phrases. Leave blank if no basis.
- If `story_sections` is present in the source, read through the narrative carefully
  to infer personality, speech patterns, likes/dislikes/loves/hates, and appearance
  details that are shown through action rather than stated directly.
- Fill age, likes, dislikes, personality_traits, speech, relationship_to_user
  whenever the source gives clear OR implied support. Be proactive:
  - `speech`: infer from any quoted dialogue, described mannerisms, or narrative tone.
    Even a single quote is enough to capture their voice pattern.
  - `likes` / `dislikes` / `loves` / `hates`: infer from story actions, stated goals,
    relationships, and emotional reactions. Apply intensity based on context:
    "likes" for preferences, "loves" for deep passions or obsessions,
    "dislikes" for mild aversions, "hates" for strong contempt or fear.
    Examples: a character obsessed with alchemy -> loves alchemy;
    one who destroys cursed artifacts on sight -> hates cursed items;
    one who is shown to enjoy solitude -> likes solitude, dislikes crowds.
    Never leave all four blank if the source has any behavioral or emotional content.
  - `personality_traits`: extract from behavioral descriptions, not just explicit trait lists.
  - `relationship_to_user`: default to a reasonable canon-consistent framing if not stated
    (e.g. "a stranger who crossed paths with her" or "a potential ally she is testing").

Return this exact JSON shape:
{{
  "name": "",
  "structured_profile": {{
    "sex": "", "ethnicity": "", "race": "", "job_occupation": "",
    "gender": "", "sexual_attraction": "", "pronouns": "",
    "appearance": [], "non_human_appearance": [], "personal_parts": [],
    "clothing": [], "accessories": [],
    "relationship_to_user": "", "relationship_status": "",
    "backstory": "", "speech": [], "personality_traits": [],
    "kinks": [], "likes": [], "dislikes": [],
    "loves": [], "hates": [],
    "height": "", "weight": "", "age": ""
  }},
  "description": "",
  "personality": "",
  "scenario": "",
  "first_mes": "",
  "mes_example": "<START>\\n{{{{char}}}}: ...\\n\\n<START>\\n{{{{char}}}}: ...\\n\\n<START>\\n{{{{char}}}}: ...",
  "tags": []
}}"""

    # User message: source data (or custom template)
    if use_config and template_text:
        try:
            user = template_text.format(source_json=source_json)
        except Exception as e:
            _log_warn(f"Template error, falling back to default: {e}")
            user = f"SOURCE DATA:\n{source_json}"
    else:
        user = f"SOURCE DATA:\n{source_json}"

    result = _request(provider, model, user, system=system)

    _log_dim(f"  card keys: {list(result.keys())}")

    for key in REQUIRED_KEYS:
        if key == "tags":
            result.setdefault("tags", [])
        elif key == "structured_profile":
            result.setdefault("structured_profile", {})
        else:
            result.setdefault(key, "")

    # Normalise list fields that may come back as strings
    sp = result.get("structured_profile", {})
    list_fields = [
        "appearance", "non_human_appearance", "personal_parts",
        "clothing", "accessories", "speech", "personality_traits",
        "kinks", "likes", "dislikes", "loves", "hates",
    ]
    for lf in list_fields:
        if lf in sp:
            sp[lf] = _ensure_list(sp[lf])
    result["tags"] = _ensure_list(result.get("tags", []))

    return result


# -------------------------------------------------------------------------------
# Single field regeneration
# -------------------------------------------------------------------------------

def regenerate_single_field(
    source: Dict[str, Any],
    card: Dict[str, Any],
    field_name: str,
    provider: str,
    model: str,
    custom_prompt: str = "",
    include_current_card: bool = True,
    include_source: bool = True,
) -> Dict[str, Any]:
    templates = get_prompt_templates()
    config = load_runtime_config()
    use_config = config.get("use_templates", False)

    normalized = source.get("normalized", {})
    compact_source = {
        "title":              normalized.get("title", ""),
        "summary":            normalized.get("summary", ""),
        "franchise":          normalized.get("franchise", ""),
        "appearance_list":    normalized.get("appearance_list", [])[:12],
        "personality_traits": normalized.get("personality_traits", [])[:12],
        "abilities_list":     normalized.get("abilities_list", [])[:12],
        "history_list":       normalized.get("history_list", [])[:12],
        "normalized_infobox": normalized.get("normalized_infobox", {}),
    }
    source_json = json.dumps(compact_source, ensure_ascii=False, indent=2)

    structured_subfields = {
        "sex", "ethnicity", "race", "job_occupation", "gender",
        "sexual_attraction", "pronouns", "appearance", "non_human_appearance",
        "personal_parts", "clothing", "accessories", "relationship_to_user",
        "relationship_status", "backstory", "speech", "personality_traits",
        "kinks", "likes", "dislikes", "loves", "hates", "height", "weight", "age",
    }
    list_subfields = {
        "appearance", "non_human_appearance", "personal_parts", "clothing",
        "accessories", "speech", "personality_traits", "kinks",
        "likes", "dislikes", "loves", "hates",
    }

    # Trim the card to only what's relevant for this field — full card is too many tokens
    sp = card.get("structured_profile", {})
    if field_name in structured_subfields:
        # Structured field: only needs name + description + personality for context
        compact_card = {
            "name": card.get("name", ""),
            "description": card.get("description", "")[:500],
            "personality": card.get("personality", "")[:500],
            "structured_profile": sp,
        }
    elif field_name == "description":
        compact_card = {
            "name": card.get("name", ""),
            "personality": card.get("personality", "")[:400],
            "structured_profile": {k: sp.get(k) for k in
                ["appearance", "clothing", "accessories", "ethnicity", "race", "height", "age"] if sp.get(k)},
        }
    elif field_name == "personality":
        compact_card = {
            "name": card.get("name", ""),
            "description": card.get("description", "")[:400],
            "structured_profile": {k: sp.get(k) for k in
                ["personality_traits", "speech", "likes", "dislikes", "loves", "hates", "relationship_to_user"] if sp.get(k)},
        }
    elif field_name in ("first_mes", "mes_example"):
        compact_card = {
            "name": card.get("name", ""),
            "personality": card.get("personality", "")[:400],
            "scenario": card.get("scenario", "")[:300],
            "first_mes": card.get("first_mes", "") if field_name == "mes_example" else "",
        }
    elif field_name == "scenario":
        compact_card = {
            "name": card.get("name", ""),
            "description": card.get("description", "")[:400],
            "personality": card.get("personality", "")[:300],
        }
    else:
        compact_card = {
            "name": card.get("name", ""),
            "description": card.get("description", "")[:300],
            "personality": card.get("personality", "")[:300],
        }
    card_json = json.dumps(compact_card, ensure_ascii=False, indent=2)

    # System: definitions + task framing
    system = f"""{CHARACTER_CARD_DEFINITION}

---

You are rewriting exactly ONE field of a SillyTavern character card.
Return ONLY valid JSON in the exact shape specified. No markdown fences.
Stay canon-consistent. Do not invent facts beyond the source or current card.
Do not write actions or dialogue for {{{{user}}}}."""

    # User: build the task
    template_text = templates.get("field_regeneration_template", "").strip()
    custom_instruction = custom_prompt.strip()

    if use_config and template_text:
        try:
            user = template_text.format(
                field_name=field_name,
                source_json=source_json,
                card_json=card_json,
                custom_prompt=custom_instruction,
            )
        except Exception as e:
            _log_warn(f"Template error, falling back to default: {e}")
            user = None
    else:
        user = None

    if not user:
        parts = [f"Target field: {field_name}", ""]

        if field_name == "structured_profile":
            parts += [
                'Return this shape exactly:',
                '{"structured_profile": {"sex":"","ethnicity":"","race":"","job_occupation":"","gender":"","sexual_attraction":"","pronouns":"","appearance":[],"non_human_appearance":[],"personal_parts":[],"clothing":[],"accessories":[],"relationship_to_user":"","relationship_status":"","backstory":"","speech":[],"personality_traits":[],"kinks":[],"likes":[],"dislikes":[],"loves":[],"hates":[],"height":"","weight":"","age":""}}',
            ]
        elif field_name in structured_subfields:
            if field_name in list_subfields:
                parts += [
                    "Return this shape exactly:",
                    f'{{"structured_profile": {{"{field_name}": []}}}}',
                    f"Rules: short specific phrases only. Leave empty if no source basis.",
                ]
            else:
                parts += [
                    "Return this shape exactly:",
                    f'{{"structured_profile": {{"{field_name}": ""}}}}',
                    f"Rules: fill only if source directly states or strongly implies it.",
                ]
        elif field_name == "tags":
            parts += ["Return this shape: {\"tags\": []}"]
        elif field_name == "scenario":
            parts += [
                'Return this shape: {"scenario": ""}',
                "Rules: roleplay-ready setup grounded in canon. Do not write {{user}} lines.",
            ]
        elif field_name == "mes_example":
            parts += [
                'Return this shape: {"mes_example": "<START>\\n{{char}}: ...\\n\\n<START>\\n{{char}}: ..."}',
                "Rules: 3-6 examples. Format: <START>\\n{{char}}: line\\n\\n<START>\\n{{char}}: line — TWO newlines (\\n\\n) between blocks. Never run <START> onto same line as previous dialogue. Show different moods. No {{user}} lines.",
            ]
        else:
            parts += [f'Return this shape: {{"{field_name}": ""}}']

        if custom_instruction:
            parts += ["", f"Additional instruction: {custom_instruction}"]

        if include_source:
            parts += ["", "SOURCE DATA:", source_json]

        if include_current_card:
            parts += ["", "CURRENT CARD:", card_json]

        user = "\n".join(parts)

    result = _request(provider, model, user, system=system)

    if field_name == "structured_profile":
        if "structured_profile" not in result:
            raise ValueError("Missing structured_profile in regeneration result")
        return {"structured_profile": result["structured_profile"]}

    if field_name in structured_subfields:
        if "structured_profile" not in result:
            raise ValueError("Missing structured_profile in regeneration result")
        if field_name not in result["structured_profile"]:
            raise ValueError(f"Missing structured_profile.{field_name} in regeneration result")
        val = result["structured_profile"][field_name]
        if field_name in list_subfields:
            val = _ensure_list(val)
        return {"structured_profile": {field_name: val}}

    if field_name == "tags":
        if "tags" not in result:
            raise ValueError("Missing tags in regeneration result")
        return {"tags": _ensure_list(result["tags"])}

    if field_name not in result:
        raise ValueError(f"Missing field in regeneration result: {field_name}")

    return {field_name: result[field_name]}


# -------------------------------------------------------------------------------
# Lore entry generation  (unified - used by single, multi, and crawl paths)
# -------------------------------------------------------------------------------

def generate_lore_entry(
    source: Dict[str, Any],
    provider: str,
    model: str,
    purpose: str = "Create lorebook entries from this wiki page.",
    criteria: str = "The page must be a detailed article about a specific subject, not a list or category page.",
    extraction_notes: str = "Focus on relationships, affiliations, and worldbuilding context. Ignore gameplay mechanics.",
) -> Dict[str, Any]:
    """
    Generate one or more lore entries from a source page.

    Returns a dict:
      {
        "valid": bool,
        "reason": str | None,       # why skipped if not valid
        "entries": [ { title, entry_type, keywords, summary, content }, ... ]
      }

    The valid/reason pattern lets the model
    explicitly skip bad pages rather than generating garbage entries.
    """
    # Build source content - prefer structured normalized data, fall back to raw text
    normalized = source.get("normalized", {})
    title = source.get("title") or normalized.get("title") or source.get("url", "")

    # Include raw abilities/attacks text even when structured data exists
    # because ability section names vary widely ("Attacks", "Moveset", etc.)
    # and may land in uncategorized_sections rather than abilities_list
    raw_abilities = normalized.get("abilities", "").strip()
    # uncategorized_sections lives in normalized (from parse_page) for Fandom pages
    uncategorized = normalized.get("uncategorized_sections") or source.get("uncategorized_sections", {})
    # Pull any section that looks ability-related from uncategorized
    ability_keywords = {"attack", "moveset", "move", "skill", "power", "ability", "technique", "magic", "spell", "art"}
    extra_abilities = {}
    for section_name, paragraphs in (uncategorized.items() if isinstance(uncategorized, dict) else {}.items()):
        if any(kw in section_name.lower() for kw in ability_keywords):
            extra_abilities[section_name] = paragraphs[:5]

    structured = {
        "title":              normalized.get("title", ""),
        "summary":            normalized.get("summary", ""),
        "franchise":          normalized.get("franchise", ""),
        "normalized_infobox": normalized.get("normalized_infobox", {}),
        "personality_traits": normalized.get("personality_traits", [])[:10],
        "abilities_list":     normalized.get("abilities_list", [])[:15],
        "history_list":       normalized.get("history_list", [])[:8],
        "relationships":      normalized.get("relationships", [])[:8],
    }
    # Always append raw abilities text and extra sections if present
    if raw_abilities:
        structured["abilities_raw"] = raw_abilities[:3000]
    if extra_abilities:
        structured["extra_ability_sections"] = extra_abilities

    has_structured = any(
        structured[k] for k in ["summary", "normalized_infobox", "personality_traits", "history_list",
                                  "abilities_list", "abilities_raw", "extra_ability_sections"]
    )
    if has_structured:
        content_block = json.dumps(structured, ensure_ascii=False, indent=2)
    else:
        raw = source.get("raw_text") or source.get("content") or ""
        content_block = raw[:8000] if raw else json.dumps(structured, ensure_ascii=False)

    # System: lorebook definition + task framing
    system = f"""{LOREBOOK_DEFINITION}

---

You are generating SillyTavern lorebook entries from a wiki page.
Return ONLY valid JSON. No markdown fences.

TASK:
Purpose: {purpose}
Criteria: {criteria}
Extraction notes: {extraction_notes}

STEP 1 - VALIDATE:
Check if this page meets the criteria above.
- If NOT valid: set "valid": false, explain in "reason", set "entries": []
- If valid: set "valid": true, "reason": null, fill "entries"

STEP 2 - GENERATE (only if valid):
Create one entry per distinct entity on the page.
Include the main subject PLUS:
- Each named ability, attack, move, or technique as its OWN separate entry
- Named items, weapons, or equipment
- Factions, locations, or events mentioned in detail

If abilities_list, abilities_raw, or extra_ability_sections are present in
the source data, create individual entries for EACH named ability/attack.
Do not group all abilities into one entry.
Aim for 3-10 entries per page depending on how much content is available.

Return this exact JSON shape:
{{
  "valid": true,
  "reason": null,
  "entries": [
    {{
      "title": "",
      "entry_type": "character|ability|item|faction|place|event|concept",
      "keywords": [],
      "summary": "",
      "content": ""
    }}
  ]
}}"""

    user = f"SOURCE URL: {source.get('url', '')}\n\nSOURCE CONTENT:\n{content_block}"

    result = _request(provider, model, user, system=system)

    # Normalise the response
    if "valid" not in result:
        # Model returned entries directly without the wrapper - treat as valid
        if "entries" in result:
            return {"valid": True, "reason": None, "entries": result["entries"]}
        if "title" in result:
            return {"valid": True, "reason": None, "entries": [result]}
        return {"valid": False, "reason": "Model returned unexpected structure", "entries": []}

    entries = result.get("entries", [])
    # Normalise keywords in every entry
    for entry in entries:
        if isinstance(entry, dict):
            entry["keywords"] = _ensure_list(entry.get("keywords", []))

    return {
        "valid":   bool(result.get("valid", True)),
        "reason":  result.get("reason"),
        "entries": entries,
    }
