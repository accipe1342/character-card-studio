"""Importing cards: our own PNG export round-trips (profile, Character's Note, lorebook, picture), other apps' V2 / V3
JSON, old V1 JSON, CHARX, and readable errors for files that are not cards."""
import io
import json
import zipfile

import database as D
import png_card
from preview import build_export_card_json, build_export_card_v3, character_book_from_items, normalise_lore_items

CARD = {"name": "Mara Vell", "description": "A courier.", "personality": "Dry.", "scenario": "A rainy port.",
        "first_mes": "You find her at the docks.", "mes_example": "<START>\n{{char}}: Keep up.", "tags": ["courier", "port"],
        "alternate_greetings": ["Again?"], "depth_prompt": "Mara is dry and proud.", "system_prompt": "",
        "structured_profile": {"likes": ["tea"], "age": "24"}}
ITEMS = normalise_lore_items([
    {"title": "Old Harbor", "entry_type": "place", "keys": ["harbor", "docks"], "content": "Docks that never sleep."},
    {"title": "The Ledger", "entry_type": "item", "keys": ["ledger"], "content": "Mara took it.", "char_filter": ["Mara Vell"]},
    {"title": "Port Premise", "entry_type": "concept", "keys": [], "content": "Guilds keep order.", "constant": True},
])


def post(client, H, name, raw):
    return client.post("/api/card/import", data={"file": (io.BytesIO(raw), name)}, headers=H, content_type="multipart/form-data")


def entries(pid):
    return {e["title"]: D.get_lore_entry(e["id"]) for e in D.list_lore_entries(crawl_id=pid)}


def test_our_png_export_round_trips(client, H):
    v2 = build_export_card_json(CARD)
    v2["data"]["character_book"] = character_book_from_items("Rain Port", ITEMS)
    png = png_card.embed(png_card.placeholder("Mara"), v2, build_export_card_v3({**CARD}))
    r = post(client, H, "mara.png", png)
    assert r.status_code == 200, r.get_json()
    d = r.get_json()
    card = D.get_card(d["card_id"])
    assert card["name"] == "Mara Vell" and card["first_mes"] == "You find her at the docks."
    assert card["tags"] == ["courier", "port"] and card["alternate_greetings"] == ["Again?"]
    assert card["structured_profile"]["likes"] == ["tea"] and card["depth_prompt"] == "Mara is dry and proud."
    assert card["image"] and d["image"] == card["image"]                                      # the PNG is the portrait
    assert d.get("lore_project_id") is None                                                   # V3 chunk wins, no book in it


def test_v2_json_with_a_lorebook(client, H):
    v2 = build_export_card_json(CARD)
    v2["data"]["character_book"] = character_book_from_items("Rain Port", ITEMS)
    d = post(client, H, "mara.json", json.dumps(v2).encode()).get_json()
    assert d["entries"] == 3
    ents = entries(d["lore_project_id"])
    assert ents["Old Harbor"]["keywords"] == ["harbor", "docks"] and ents["Old Harbor"]["entry_type"] == "place"
    assert ents["The Ledger"]["char_filter"] == ["Mara Vell"] and ents["Port Premise"]["constant"] == 1
    assert D.get_card(d["card_id"])["creator_notes"] == ""                                   # our default note is not copied


def test_other_apps_and_old_formats(client, H):
    v3 = {"spec": "chara_card_v3", "spec_version": "3.0", "data": {
        "name": "Tomas", "description": "A smuggler.", "first_mes": "Hm?", "tags": "smuggler, port",
        "extensions": {"depth_prompt": {"prompt": "Tomas lies.", "depth": 4}},
        "character_book": {"name": "Docks", "entries": [{"keys": ["tide guild"], "content": "Smugglers.", "comment": "Tide Guild"}]}}}
    d = post(client, H, "tomas.json", json.dumps(v3).encode()).get_json()
    c = D.get_card(d["card_id"])
    assert c["tags"] == ["smuggler", "port"] and c["depth_prompt"] == "Tomas lies."
    assert list(entries(d["lore_project_id"])) == ["Tide Guild"]
    v1 = {"char_name": "Old Card", "char_persona": "Grumpy.", "char_greeting": "Go away.", "world_scenario": "A shop."}
    c = D.get_card(post(client, H, "old.json", json.dumps(v1).encode()).get_json()["card_id"])
    assert (c["name"], c["personality"], c["first_mes"], c["scenario"]) == ("Old Card", "Grumpy.", "Go away.", "A shop.")


def test_charx(client, H):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("card.json", json.dumps({"spec": "chara_card_v3", "data": {
            "name": "Ines", "description": "A clerk.", "first_mes": "Next.",
            "assets": [{"type": "icon", "uri": "embeded://assets/icon/main.png", "name": "main", "ext": "png"}]}}))
        z.writestr("assets/icon/main.png", png_card.placeholder("Ines"))
    d = post(client, H, "ines.charx", buf.getvalue()).get_json()
    assert D.get_card(d["card_id"])["name"] == "Ines" and d["image"]


def test_not_a_card(client, H):
    r = post(client, H, "plain.png", png_card.placeholder("x"))
    assert r.status_code == 400 and "no character card inside" in r.get_json()["error"]
    r = post(client, H, "world.json", json.dumps({"entries": {"0": {"content": "x"}}}).encode())
    assert r.status_code == 400 and "lorebook" in r.get_json()["error"]
    r = post(client, H, "notes.txt", b"\x00\x01 not json")
    assert r.status_code == 400 and "Unsupported file" in r.get_json()["error"]
    r = client.post("/api/card/import", data={}, headers=H, content_type="multipart/form-data")
    assert r.status_code == 400
