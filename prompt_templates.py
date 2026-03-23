import json
import os

PROMPTS_PATH = os.path.join("config", "prompts.json")


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