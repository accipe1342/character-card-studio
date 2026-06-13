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
        f'Species ("{q(profile.get("species", ""))}")',
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
    return "\n".join(lines)


def build_export_card_json(card: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": card["name"],
            "description": card["description"],
            "personality": card["personality"],
            "scenario": card["scenario"],
            "first_mes": card["first_mes"],
            "mes_example": card["mes_example"],
            "creator_notes": "Generated and edited in local Character Card Studio.",
            "system_prompt": (
                "You are roleplaying as {{char}}. Remain canon-consistent with the card. "
                "Do not speak for {{user}}."
            ),
            "post_history_instructions": "Stay in character.",
            "tags": card["tags"],
            "creator": "Andy",
            "character_version": "1.0",
            "extensions": {"structured_profile": card["structured_profile"]},
        },
    }
