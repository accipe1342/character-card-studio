import json
import os
import re
from typing import Any, Dict
from prompt_templates import get_prompt_templates
import requests
from dotenv import load_dotenv

load_dotenv()

NANOGPT_URL = "https://nano-gpt.com/api/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
NANOGPT_MODEL = os.getenv("NANOGPT_MODEL", "zai-org/glm-4.7:thinking")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "z-ai/glm-4.7")
LOCAL_DEFAULT_BASE_URL = "http://127.0.0.1:1234"
LOCAL_DEFAULT_MODEL = "Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q6_K"
OPENROUTER_ENABLE_REASONING = True
TEMPERATURE = 0.7
TIMEOUT_SECONDS = 120

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


def get_nanogpt_key() -> str:
    return os.getenv("NANOGPT_API_KEY", "")


def get_openrouter_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "")


def get_local_key() -> str:
    return os.getenv("LOCAL_API_KEY", "")


def get_local_base_url() -> str:
    return os.getenv("LOCAL_OPENAI_BASE_URL", LOCAL_DEFAULT_BASE_URL)


def get_local_model() -> str:
    return os.getenv("LOCAL_MODEL", LOCAL_DEFAULT_MODEL)


def _build_local_chat_completions_url(base_url: str) -> str:
    base = (base_url or LOCAL_DEFAULT_BASE_URL).strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


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
    if not match:
        raise ValueError(
            f"Model response did not contain a JSON object. Raw: {text[:1200]}"
        )
    return json.loads(match.group(0))
def load_runtime_config():
    try:
        with open("config/settings.json", "r") as f:
            return json.load(f)
    except:
        return {"use_templates": False}

KNOWN_PROVIDERS = {"nanogpt", "openrouter", "local", "lmstudio", "openai_local"}


def _request(provider: str, model: str, prompt: str) -> Dict[str, Any]:
    provider = (provider or "").strip().lower()

    if provider not in KNOWN_PROVIDERS:
        print(f"[GENERATOR] Unknown provider '{provider}', falling back to local.")
        provider = "local"

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
        }
        response = requests.post(
            NANOGPT_URL, headers=headers, json=payload, timeout=TIMEOUT_SECONDS
        )
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
        }
        if OPENROUTER_ENABLE_REASONING:
            payload["reasoning"] = {"enabled": True}
        response = requests.post(
            OPENROUTER_URL, headers=headers, json=payload, timeout=TIMEOUT_SECONDS
        )
    elif provider in {"local", "lmstudio", "openai_local"}:
        local_api_key = get_local_key()
        headers = {
            "Content-Type": "application/json",
        }
        if local_api_key:
            headers["Authorization"] = f"Bearer {local_api_key}"

        payload = {
            "model": model or get_local_model(),
            "messages": [
                {"role": "system", "content": "Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": TEMPERATURE,
            "stream": False,
        }
        response = requests.post(
            _build_local_chat_completions_url(get_local_base_url()),
            headers=headers,
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
    else:
        # Alias catch-all — should never reach here after the normalisation above
        print(f"[GENERATOR] Unhandled provider '{provider}', routing to local.")
        provider = "local"
        local_api_key = get_local_key()
        headers = {"Content-Type": "application/json"}
        if local_api_key:
            headers["Authorization"] = f"Bearer {local_api_key}"
        payload = {
            "model": model or get_local_model(),
            "messages": [
                {"role": "system", "content": "Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "temperature": TEMPERATURE,
            "stream": False,
        }
        response = requests.post(
            _build_local_chat_completions_url(get_local_base_url()),
            headers=headers,
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )

    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return _extract_json_object(content)


def generate_full_card(
    source: Dict[str, Any], provider: str, model: str
) -> Dict[str, Any]:
    source_json = json.dumps(source["normalized"], ensure_ascii=False, indent=2)

    templates = get_prompt_templates()
    config = load_runtime_config()
    use_config = config.get("use_templates", False)
    has_template = bool(templates.get("character_generation_template", "").strip())

    print(f"[GENERATOR] Using config templates (full): {use_config}")

    if use_config and not has_template:
        use_config = False

    if use_config:
        try:
            prompt = templates["character_generation_template"].format(
                source_json=source_json
            )
        except Exception as e:
            print("[TEMPLATE ERROR] Falling back to default:", e)
            use_config = False

    if not use_config:
        prompt = f"""
You are converting scraped fandom wiki data into a SillyTavern character card.

Rules:
- Do not invent facts not present in the source data.
- Keep the character canon-consistent.
- Rewrite for roleplay usefulness, not wiki style.
- Make personality behavioral, not just a list of adjectives.
- Keep first_mes short, natural, and in character.
- Do not write actions or dialogue for {{{{user}}}}.
- If a field is unknown, use an empty string "" or an empty array [].
- Output valid JSON only.
- No markdown fences.

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
  "mes_example": "",
  "tags": []
}}

Source data:
{source_json}
""".strip()

    result = _request(provider, model, prompt)

    # Fill any keys the model omitted with safe defaults instead of crashing
    defaults = {
        "name": "",
        "structured_profile": {},
        "description": "",
        "personality": "",
        "scenario": "",
        "first_mes": "",
        "mes_example": "",
        "tags": [],
    }
    for key, default in defaults.items():
        if key not in result:
            print(f"[GENERATOR] Model omitted '{key}', using default.")
            result[key] = default

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

    current_card = {
        "name": card["name"],
        "structured_profile": card["structured_profile"],
        "description": card["description"],
        "personality": card["personality"],
        "scenario": card["scenario"],
        "first_mes": card["first_mes"],
        "mes_example": card["mes_example"],
        "tags": card["tags"],
    }

    if field_name == "structured_profile":
        shape = {"structured_profile": card["structured_profile"]}
        target_instruction = "Regenerate the full structured_profile."
    else:
        shape = {field_name: [] if field_name == "tags" else ""}
        target_instruction = f"Regenerate ONLY the field '{field_name}'."

    templates = get_prompt_templates()
    config = load_runtime_config()
    use_config = config.get("use_templates", False)
    has_template = bool(templates.get("field_regeneration_template", "").strip())

    print(f"[GENERATOR] Using config templates (regen): {use_config}")

    if use_config and not has_template:
        use_config = False

    if use_config:
        try:
            custom_prompt_block = (
                f"Additional user instruction: {custom_prompt}"
                if custom_prompt
                else "No additional user instruction."
            )

            source_json = "{}"
            if include_source:
                source_json = json.dumps(
                    source["normalized"], ensure_ascii=False, indent=2
                )

            current_card_json = "{}"
            if include_current_card:
                current_card_json = json.dumps(
                    current_card, ensure_ascii=False, indent=2
                )

            prompt = templates["field_regeneration_template"].format(
                field_name_instruction=target_instruction,
                custom_prompt_block=custom_prompt_block,
                shape_json=json.dumps(shape, ensure_ascii=False, indent=2),
                source_json=source_json,
                current_card_json=current_card_json,
            )

        except Exception as e:
            print("[TEMPLATE ERROR - REGEN] Falling back to default:", e)
            use_config = False

    if not use_config:
        prompt_parts = [
            target_instruction,
            "Return valid JSON only.",
            "Do not change any other field.",
            "Do not invent facts not present in the provided context.",
        ]

        if custom_prompt:
            prompt_parts.append(f"Additional user instruction: {custom_prompt}")

        prompt_parts.append("\nReturn exactly this JSON shape:")
        prompt_parts.append(json.dumps(shape, ensure_ascii=False, indent=2))

        if include_source:
            prompt_parts.append("\nSource data:")
            prompt_parts.append(
                json.dumps(source["normalized"], ensure_ascii=False, indent=2)
            )

        if include_current_card:
            prompt_parts.append("\nCurrent card draft:")
            prompt_parts.append(json.dumps(current_card, ensure_ascii=False, indent=2))

        prompt = "\n".join(prompt_parts).strip()

    return _request(provider, model, prompt)
