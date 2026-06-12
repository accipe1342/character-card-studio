import json
import os
import re
import time
from typing import Any, Dict
from prompt_templates import get_prompt_templates
import requests
from dotenv import load_dotenv
from requests.exceptions import ReadTimeout, ConnectTimeout, Timeout, RequestException

# =========================
# LORE GENERATION TEMPLATES
# =========================

LOREBOOK_DEFINITION = """
Return valid JSON with these keys:
- title
- entry_type
- keywords
- summary
- content
- related_entries

Rules:
- title: short and specific
- entry_type: character, organization, faction, location, event, concept, item, world
- keywords: 1-8 strong retrieval terms
- summary: 1-3 sentences
- content: 100-400 words of dense lore
- related_entries: related concepts or entities
""".strip()


LORE_ENTRY_TEMPLATE = """
{lorebook_definition}

Task:
Create one lorebook entry from the provided source.

Purpose:
{purpose}

Criteria:
{criteria}

Extraction Notes:
{extraction_notes}

Rules:
- Focus on one core topic from the page
- Preserve relationships, affiliations, and context
- Ignore gameplay-only clutter unless relevant
- Output valid JSON only

If invalid page:
{{
  "valid": false,
  "reason": "",
  "entry": null
}}

If valid:
{{
  "valid": true,
  "reason": "",
  "entry": {{
    "title": "",
    "entry_type": "",
    "keywords": [],
    "summary": "",
    "content": "",
    "related_entries": []
  }}
}}

Source URL:
{source_url}

Source Content:
{content}
""".strip()

load_dotenv()

_RESET = "\033[0m"; _BOLD = "\033[1m"
_CYAN = "\033[36m"; _GREEN = "\033[32m"
_YELLOW = "\033[33m"; _RED = "\033[31m"; _DIM = "\033[2m"
def _log_info(m):  print(f"{_CYAN}[·]{_RESET} {m}")
def _log_ok(m):    print(f"{_GREEN}[✓]{_RESET} {_BOLD}{m}{_RESET}")
def _log_warn(m):  print(f"{_YELLOW}[!]{_RESET} {m}")
def _log_dim(m):   print(f"{_DIM}{m}{_RESET}")

NANOGPT_URL = "https://nano-gpt.com/api/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
NANOGPT_MODEL = os.getenv("NANOGPT_MODEL", "zai-org/glm-4.7:thinking")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "z-ai/glm-4.7")
OPENROUTER_ENABLE_REASONING = True
TEMPERATURE = 0.7
TIMEOUT_SECONDS = 180

REQUIRED_KEYS = {
    "name",
    "structured_profile",
    "description",
    "personality",
    "scenario",
    "first_mes",
    "mes_example",
    "tags",
}


def _normalized_source_json(source: Dict[str, Any]) -> str:
    return json.dumps(source.get("normalized", {}), ensure_ascii=False, indent=2)


def get_nanogpt_key() -> str:
    return os.getenv("NANOGPT_API_KEY", "")


def get_openrouter_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "")


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_json_object(text: str) -> Dict[str, Any]:
    text = _strip_code_fences(text)

    # 1. Try clean parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Try extracting the first {...} block then parsing
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        candidate = match.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        # 3. Try json_repair on the extracted block
        try:
            from json_repair import repair_json
            repaired = repair_json(candidate, return_objects=True)
            if isinstance(repaired, dict):
                _log_warn("JSON repaired — model returned malformed response")
                return repaired
        except Exception as repair_err:
            _log_dim(f"  repair attempt failed: {repair_err}")

    # 4. Try json_repair on the full text as last resort
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


def load_runtime_config():
    try:
        with open("config/settings.json", "r") as f:
            return json.load(f)
    except:
        return {"use_templates": False}


_RETRY_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = [2, 4]  # waits before attempt 2, then attempt 3

# HTTP status codes worth retrying (transient server-side issues or rate limits)
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _build_request(provider: str, model: str, prompt: str):
    """Return (url, headers, payload) for the given provider without sending."""
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
            "messages": [
                {"role": "system", "content": "Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": TEMPERATURE,
            "stream": False,
            "max_tokens": 4096,
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
            "messages": [
                {"role": "system", "content": "Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": TEMPERATURE,
            "max_tokens": 4096,
        }
        if OPENROUTER_ENABLE_REASONING:
            payload["reasoning"] = {"enabled": True}
        return OPENROUTER_URL, headers, payload

    else:
        raise ValueError(f"Unsupported provider: {provider}")


def _request(provider: str, model: str, prompt: str) -> Dict[str, Any]:
    import traceback

    provider = (provider or "").strip().lower()
    _log_info(f"Request  →  {provider}/{model}")

    # Build request params once — raises immediately for bad provider / missing key
    url, headers, payload = _build_request(provider, model, prompt)

    last_exception: Exception = RuntimeError("No attempts made")

    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        if attempt > 1:
            wait = _RETRY_BACKOFF_SECONDS[attempt - 2]
            print(f"[REQUEST] attempt {attempt}/{_RETRY_MAX_ATTEMPTS} — waiting {wait}s after previous failure")
            time.sleep(wait)

        try:
            _log_dim(f"  → sending (attempt {attempt})")
            response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT_SECONDS)

            _log_dim(f"  ← {response.status_code}")
            

            if response.status_code in _RETRYABLE_STATUS_CODES:
                msg = f"HTTP {response.status_code} from {provider} (attempt {attempt})"
                _log_warn(msg)
                last_exception = RuntimeError(msg)
                continue  # retry

            # Non-retryable HTTP errors (400, 401, 403, …) — surface immediately
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
            # Timeouts are retryable — keep looping

        except (ValueError, RuntimeError):
            # ValueError = bad provider, missing key, unparseable JSON — not transient
            raise

        except Exception as exc:
            traceback.print_exc()
            last_exception = exc
            # Unknown error — retry in case it was transient

    raise RuntimeError(
        f"{provider} request failed after {_RETRY_MAX_ATTEMPTS} attempts. "
        f"Last error: {last_exception}"
    ) from last_exception


def generate_full_card(
    source: Dict[str, Any], provider: str, model: str
) -> Dict[str, Any]:
    source_json = json.dumps(source["normalized"], ensure_ascii=False, indent=2)

    templates = get_prompt_templates()
    config = load_runtime_config()
    use_config = config.get("use_templates", False)

    print(f": {use_config}")

    prompt = None
    template_text = templates.get("character_generation_template", "").strip()

    if use_config and template_text:
        try:
            prompt = template_text.format(source_json=source_json)
        except Exception as e:
            print("[TEMPLATE ERROR] Falling back to default:", e)

    if not prompt:
        prompt = f"""
You are converting scraped fandom wiki data into a SillyTavern character card.

Rules:
- Do not invent facts not present in the source data.
- Keep the character canon-consistent.
- Rewrite for roleplay usefulness, not wiki style.
- Make personality behavioral, not just a list of adjectives.
- Keep first_mes short, natural, and in character.
- Do not write actions or dialogue for {{{{user}}}}.
- Output valid JSON only.
- No markdown fences.
- Fill scenario with a roleplay-ready setup grounded in canon when enough context exists.
- Scenario should describe the situation, tone, and where the interaction begins.
- Scenario should be immersive and usable for roleplay, but should not become a full story scene.
- mes_example must contain 3 to 6 example messages in this exact format:
  <START>
  {{{{char}}}}: example line here
- Put a blank line between each <START> block.
- Each mes_example entry should reflect different moods, manners, or speaking patterns of the character.
- Do not write any lines for {{{{user}}}} in mes_example.
- mes_example must be a single valid JSON string.
- Use \\n for line breaks inside mes_example.
- Do not use raw unescaped line breaks inside JSON string values.
- Fill structured_profile.age, likes, dislikes, loves, hates, speech, personality_traits, relationship_to_user, and relationship_status whenever the source gives enough direct or strongly implied support.
- Only leave a field blank if the source gives truly no grounded basis for it.
- For list fields, prefer concise but meaningful entries rather than leaving them empty.

Return exactly this JSON shape:
{{
  "name": "",
  "structured_profile": {{
    "sex": "",
    "species": "",
    "race": "",
    "job_occupation": "",
    "gender": "",
    "sexual_attraction": "",
    "pronouns": "",
    "appearance": [],
    "non_human_appearance": [],
    "personal_parts": [],
    "clothing": [],
    "accessories": [],
    "relationship_to_user": "",
    "relationship_status": "",
    "backstory": "",
    "speech": [],
    "personality_traits": [],
    "kinks": [],
    "likes": [],
    "dislikes": [],
    "loves": [],
    "hates": [],
    "height": "",
    "weight": "",
    "age": ""
  }},
  "description": "",
  "personality": "",
  "scenario": "",
  "first_mes": "",
  "mes_example": "<START>\\n{{{{char}}}}: ...\\n\\n<START>\\n{{{{char}}}}: ...\\n\\n<START>\\n{{{{char}}}}: ...",
  "tags": []
}}

Source data:
{source_json}
""".strip()

    result = _request(provider, model, prompt)
    print("[GENERATOR] result keys:", list(result.keys()))

    for key in REQUIRED_KEYS:
        if key == "tags":
            result.setdefault("tags", [])
        elif key == "structured_profile":
            result.setdefault("structured_profile", {})
        else:
            result.setdefault(key, "")

    return result


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

    compact_source = {
    "title": source["normalized"].get("title", ""),
    "summary": source["normalized"].get("summary", ""),
    "franchise": source["normalized"].get("franchise", ""),
    "appearance_list": source["normalized"].get("appearance_list", [])[:12],
    "personality_traits": source["normalized"].get("personality_traits", [])[:12],
    "abilities_list": source["normalized"].get("abilities_list", [])[:12],
    "history_list": source["normalized"].get("history_list", [])[:12],
    "normalized_infobox": source["normalized"].get("normalized_infobox", {}),
}
    source_json = json.dumps(compact_source, ensure_ascii=False, indent=2)
    card_json = json.dumps(card, ensure_ascii=False, indent=2)

    prompt = None
    template_text = templates.get("field_regeneration_template", "").strip()
    custom_instruction = custom_prompt.strip()
    structured_subfields = {
        "sex",
        "species",
        "race",
        "job_occupation",
        "gender",
        "sexual_attraction",
        "pronouns",
        "appearance",
        "non_human_appearance",
        "personal_parts",
        "clothing",
        "accessories",
        "relationship_to_user",
        "relationship_status",
        "backstory",
        "speech",
        "personality_traits",
        "kinks",
        "likes",
        "dislikes",
        "loves",
        "hates",
        "height",
        "weight",
        "age",
    }

    list_subfields = {
        "appearance",
        "non_human_appearance",
        "personal_parts",
        "clothing",
        "accessories",
        "speech",
        "personality_traits",
        "kinks",
        "likes",
        "dislikes",
        "loves",
        "hates",
    }
    if use_config and template_text:
        try:
            prompt = template_text.format(
                field_name=field_name,
                source_json=source_json,
                card_json=card_json,
                include_source=str(include_source).lower(),
                include_current_card=str(include_current_card).lower(),
                custom_prompt=custom_instruction,
            )
        except Exception as e:
            print("[TEMPLATE ERROR - REGEN] Falling back to default:", e)

    if not prompt:
        prompt_parts = [
            "You are rewriting exactly one field of a SillyTavern character card.",
            f"Target field: {field_name}",
            "",
            "Rules:",
            "- Return valid JSON only.",
            "- Only include the field being regenerated.",
            "- Do not include markdown fences.",
            "- Stay canon-consistent with the source.",
            "- Do not invent facts not supported by the source or current card.",
            "- Do not write actions or dialogue for {{user}}.",
            '- If the field is unknown, return an empty string "" or empty array [].',
        ]

        if field_name == "structured_profile":
            prompt_parts += [
                "",
                "Return this shape exactly:",
                """{
                    "structured_profile": {
                        "sex": "",
                        "species": "",
                        "race": "",
                        "job_occupation": "",
                        "gender": "",
                        "sexual_attraction": "",
                        "pronouns": "",
                        "appearance": [],
                        "non_human_appearance": [],
                        "personal_parts": [],
                        "clothing": [],
                        "accessories": [],
                        "relationship_to_user": "",
                        "relationship_status": "",
                        "backstory": "",
                        "speech": [],
                        "personality_traits": [],
                        "kinks": [],
                        "likes": [],
                        "dislikes": [],
                        "loves": [],
                        "hates": [],
                        "height": "",
                        "weight": "",
                        "age": ""
                    }
                    }""",
            ]
        elif field_name in structured_subfields:
            if field_name in list_subfields:
                prompt_parts += [
                    "",
                    "Return this shape exactly:",
                    f'{{"structured_profile": {{"{field_name}": []}}}}',
                    "",
                    f"Rules for structured_profile.{field_name}:",
                    "- Return a short list of grounded items.",
                    "- Prefer concise but meaningful entries.",
                    "- Do not invent facts beyond the source or strong implication from canon context.",
                    "- Only return an empty list if there is truly no grounded basis.",
                ]
            else:
                prompt_parts += [
                    "",
                    "Return this shape exactly:",
                    f'{{"structured_profile": {{"{field_name}": ""}}}}',
                    "",
                    f"Rules for structured_profile.{field_name}:",
                    "- Fill this field when the source directly states it or strongly implies it.",
                    "- Only leave it blank if there is truly no grounded basis.",
                ]

        elif field_name == "tags":
            prompt_parts += [
                "",
                "Return this shape exactly:",
                '{"tags": []}',
            ]
        elif field_name == "scenario":
            prompt_parts += [
                "",
                "Return this shape exactly:",
                '{"scenario": ""}',
                "",
                "Rules for scenario:",
                "- Write a roleplay-ready opening setup grounded in canon.",
                "- Describe the situation, tone, and where the interaction begins.",
                "- Keep it immersive and usable, but do not turn it into a long story scene.",
                "- Do not write actions or dialogue for {{user}}.",
                "- Only leave it blank if there is truly no grounded basis from the source or current card.",
            ]
        elif field_name == "mes_example":
            prompt_parts += [
                "",
                "Return this shape exactly:",
                """{"mes_example": "<START>\\n{{char}}: ...\\n\\n<START>\\n{{char}}: ...\\n\\n<START>\\n{{char}}: ..."}""",
                "",
                "Rules for mes_example:",
                "- Write 3 to 6 example messages.",
                "- Each example must begin with <START> on its own line.",
                "- Each example must then have {{char}}: followed by in-character dialogue.",
                "- Put a blank line between each <START> block.",
                "- Show the character's personality, mood, and mannerisms through the examples.",
                "- Do not write any lines for {{user}}.",
            ]
        else:
            prompt_parts += [
                "",
                "Return this shape exactly:",
                f'{{"{field_name}": ""}}',
            ]

        if custom_instruction:
            prompt_parts += [
                "",
                "Additional user instruction:",
                custom_instruction,
                "",
                "You must still return valid JSON only in the exact required shape.",
            ]

        if include_source:
            prompt_parts += ["", "Source data:", source_json]

        if include_current_card:
            prompt_parts += ["", "Current card:", card_json]

        prompt = "\n".join(prompt_parts)

    result = _request(provider, model, prompt)

    if field_name == "structured_profile":
        if "structured_profile" not in result:
            raise ValueError("Missing structured_profile in regeneration result")
        return {"structured_profile": result["structured_profile"]}

    if field_name in structured_subfields:
        if "structured_profile" not in result:
            raise ValueError("Missing structured_profile in regeneration result")
        if field_name not in result["structured_profile"]:
            raise ValueError(
                f"Missing structured_profile field in regeneration result: {field_name}"
            )
        return {
            "structured_profile": {field_name: result["structured_profile"][field_name]}
        }

    if field_name == "tags":
        if "tags" not in result:
            raise ValueError("Missing tags in regeneration result")
        return {"tags": result["tags"]}

    if field_name not in result:
        raise ValueError(f"Missing field in regeneration result: {field_name}")

    return {field_name: result[field_name]}


def generate_lore_entry(
    source: Dict[str, Any],
    provider: str,
    model: str,
    purpose: str = "Create a lorebook entry from this page.",
    criteria: str = "The page must contain meaningful lore about a specific subject.",
    extraction_notes: str = "Focus on relationships, affiliations, and worldbuilding context.",
) -> Dict[str, Any]:

    source_json = _normalized_source_json(source)

    prompt = LORE_ENTRY_TEMPLATE.format(
        lorebook_definition=LOREBOOK_DEFINITION,
        purpose=purpose,
        criteria=criteria,
        extraction_notes=extraction_notes,
        source_url=source.get("url", ""),
        content=source_json,
    )

    result = _request(provider, model, prompt)

    if "valid" not in result:
        raise ValueError("Lore response missing 'valid' flag")

    return result
