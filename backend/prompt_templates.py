"""
prompt_templates.py — Custom prompt template loader
====================================================
Loads user-configured prompt templates from backend/config/prompts.json.
These templates are prepended to AI generation prompts when the user
has set a custom system prompt in the Config tab.

USAGE
-----
from prompt_templates import get_prompt_templates

templates = get_prompt_templates()
system_prompt = templates.get("character_generation_template", "")

TEMPLATE KEYS
-------------
character_generation_template
    Prepended to the full card generation prompt. Use this to set a
    persona, writing style, or output format preference.

field_regeneration_template
    Prepended to individual field regeneration prompts.

lore_generation_template
    Prepended to lore entry generation prompts.

HOW TO EXTEND
-------------
- Add a new template key: add it to the default dict returned when
  the file is missing, and handle it in generator.py where you want
  it applied.
- Change the config path: edit PROMPTS_PATH at the top of this file.
- The JSON file is managed by the Config tab in the UI — users don't
  need to edit it directly.
"""

from pathlib import Path
import json
import os

PROMPTS_PATH = str(Path(__file__).resolve().parent / "config" / "prompts.json")


def get_prompt_templates():
    if not os.path.exists(PROMPTS_PATH):
        return {
            "character_generation_template": "",
            "field_regeneration_template": "",
        }

    try:
        with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {
            "character_generation_template": "",
            "field_regeneration_template": "",
        }


def save_prompt_templates(character_template, regen_template):
    os.makedirs("config", exist_ok=True)

    data = {
        "character_generation_template": character_template,
        "field_regeneration_template": regen_template,
    }

    with open(PROMPTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)