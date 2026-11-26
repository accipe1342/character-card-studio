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


ST_BOOK = {
    "name": "Saltmere",
    "entries": {
        "0": {"uid": 0, "comment": "Cursed Energy", "key": ["Cursed Energy", "Juryoku"],
              "keysecondary": ["Usage"], "content": "A power source aligned with negative emotion.",
              "order": 10, "insertion_order": 10, "position": 0, "depth": 4, "probability": 100,
              "constant": False, "selective": True, "disable": False, "enabled": True},
        "1": {"uid": 1, "comment": "Old Harbor", "key": ["Old Harbor"], "content": "Docks that never sleep.",
              "order": 25, "position": 1, "depth": 2, "probability": 90, "constant": True, "disable": True},
        "2": {"uid": 2, "comment": "Empty one", "key": ["nothing"], "content": "   "},
    },
}


def _post_book(client, H, book, name="book.json"):
    return client.post("/api/lore/import", headers=H, content_type="multipart/form-data",
                       data={"file": (io.BytesIO(json.dumps(book).encode()), name)})


def test_standalone_lorebook_imports_with_its_settings(client, H):
    """A World Info file exported from SillyTavern is the same shape as an embedded character_book.
    Keys, order, position, depth and probability must survive, and empty entries are skipped."""
    r = _post_book(client, H, ST_BOOK)
    assert r.status_code == 200, r.get_json()
    out = r.get_json()
    assert out["name"] == "Saltmere" and out["entries"] == 2          # the blank one is dropped
    assert any("empty" in n and "skipped" in n for n in out["notes"])
    assert any("switched off" in n for n in out["notes"])             # one was disabled in SillyTavern

    rows = client.get(f"/api/lore/entries?project_id={out['project_id']}", headers=H).get_json()
    rows = rows if isinstance(rows, list) else rows.get("entries", [])
    assert len(rows) == 2
    full = [client.get(f"/api/lore/entry/{e['id']}", headers=H).get_json() for e in rows]
    ce = next(e for e in full if "Cursed Energy" in (e.get("title") or ""))
    assert sorted(ce["keywords"]) == ["Cursed Energy", "Juryoku"]
    assert ce["insertion_order"] == 10 and ce["position"] == 0
    assert ce["entry_depth"] == 4 and ce["probability"] == 100


def test_lorebook_round_trip_keeps_entry_names(client, H):
    """Exporting what we imported must not rename anything: the type suffix is for entries we typed,
    not for someone else's lorebook arriving as the default 'concept'."""
    out = _post_book(client, H, ST_BOOK).get_json()
    back = client.get(f"/api/lore/export?project_id={out['project_id']}", headers=H).get_json()
    entries = back["entries"]
    entries = list(entries.values()) if isinstance(entries, dict) else entries
    names = {e["comment"] for e in entries}
    assert names == {"Cursed Energy", "Old Harbor"}, names
    ce = next(e for e in entries if e["comment"] == "Cursed Energy")
    assert ce["order"] == 10 and sorted(ce["key"]) == ["Cursed Energy", "Juryoku"]


def test_a_card_file_sent_to_the_lore_importer_still_works(client, H):
    """People will drop a card here by mistake: take its lorebook rather than refusing."""
    card = {"spec": "chara_card_v2", "data": {"name": "Mara", "description": "x",
                                              "character_book": ST_BOOK}}
    r = _post_book(client, H, card, "mara.json")
    assert r.status_code == 200 and r.get_json()["entries"] == 2


def test_a_file_with_no_lorebook_says_so(client, H):
    r = _post_book(client, H, {"name": "nothing here"})
    assert r.status_code == 400 and "No lorebook" in r.get_json()["error"]


def test_lore_import_names_project_after_the_file_when_the_book_has_no_name(client, H):
    """A book with no "name" takes the file's name - once, not "x lorebook lorebook"."""
    book = {"entries": [{"comment": "Old Harbor", "content": "A port town.", "keys": ["harbor"]}]}
    r = _post_book(client, H, book, "my_lorebook.json")
    assert r.status_code == 200, r.get_json()
    pid = r.get_json()["project_id"]
    assert r.get_json()["name"] == "my lorebook"
    row = next(p for p in client.get("/api/lore/projects").get_json() if p["id"] == pid)
    assert row["project_name"] == "my lorebook"      # the list and the toast agree


def test_lore_import_counts_an_empty_switched_off_entry_once(client, H):
    """Empty entries are skipped, so they are not also reported as switched off."""
    book = {"name": "B", "entries": [
        {"comment": "Real", "content": "text", "keys": ["a"]},
        {"comment": "Dead", "content": "", "keys": ["b"], "disable": True},
    ]}
    notes = _post_book(client, H, book, "b.json").get_json()["notes"]
    assert notes == ["1 empty entry skipped"]
