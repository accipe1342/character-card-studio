"""v2.5 phase 1: lore as of the starting point, chapters per entity, mentions, prose scan, personality layers."""
import pytest

import prose_scan as P
import text_module as T
from generator import validate_card
from preview import format_structured_profile_text
from test_text_flow import wait


def fake(chunk, provider, model, mode):
    i = chunk["idx"]
    ents = [{"name": "Mara", "aliases": ["Mar"], "type": "character", "age": "20" if i < 3 else "21",
             "facts": f"Mara fact {i}.", "voice": [f"Line {i}"], "keywords": ["Mara"], "origin": "",
             "relations": [{"with": "Tomas", "relation": "friend" if i < 3 else "enemy"}]},
            {"name": "Tomas", "aliases": [], "type": "character", "age": "", "facts": f"Tomas fact {i}.", "voice": [],
             "keywords": ["Tomas"], "origin": "", "relations": []}]
    if i >= 3:
        ents.append({"name": "Late Arrival", "aliases": [], "type": "character", "age": "", "facts": "Shows up late.",
                     "voice": [], "keywords": ["Late"], "origin": "", "relations": []})
    return {"chapter_summary": f"Summary {i}.", "entities": ents, "beats": [], "stats": {}}


def chapter(n):
    body = (f"Mara walked in. Tomas waved. Her voice was barely above a whisper. Will power alone kept her going. "
            f"\"Go,\" she whispered. ") * 6
    return f"Chapter {n}\n\n" + body + " ".join(f"pad{n}x{k}" for k in range(250))


@pytest.fixture(scope="module")
def proj(client, H):
    T.extract_chunk = fake
    text = "\n\n".join(chapter(n) for n in range(1, 6))
    pid = client.post("/api/text/ingest", json={"name": "Phase1 Fic", "text": text, "chunk_chars": 2500}, headers=H).get_json()["id"]
    wait(client, H, client.post(f"/api/text/project/{pid}/extract", json={"mode": "quick", "parallel": 2, "condense": False},
                                headers=H).get_json()["job_id"])
    return pid


def ents(client, H, pid):
    return {e["name"]: e for e in client.get(f"/api/text/project/{pid}", headers=H).get_json()["entities"]}


def test_lore_as_of_the_starting_point(client, H, proj):
    E = ents(client, H, proj)
    assert "Mara fact 4" in E["Mara"]["content"]
    client.put(f"/api/text/project/{proj}/recap", json={"text": "", "upto": 1}, headers=H)
    r = client.get(f"/api/text/project/{proj}/recap", headers=H).get_json()
    assert r["upto"] == 1 and r["cutoff"] is True
    items, upto = T._lore_items(proj)
    by = {i["title"]: i for i in items}
    assert upto == 1
    assert "Mara fact 0" in by["Mara"]["content"] and "Mara fact 1" in by["Mara"]["content"]
    assert "Mara fact 2" not in by["Mara"]["content"] and "Line 3" not in by["Mara"]["content"]
    assert "Age: 20" in by["Mara"]["content"] and "friend" in by["Mara"]["content"] and "enemy" not in by["Mara"]["content"]
    assert "Late Arrival" not in by                                  # appears after the starting point
    # a card made from TEXT gets the same view
    src = client.post(f"/api/text/entity/{E['Mara']['id']}/to-source", headers=H).get_json()["source"]
    assert "Mara fact 4" not in str(src["normalized"]) and "Mara fact 1" in str(src["normalized"])
    # switching the cutoff off sends everything again
    client.put(f"/api/text/project/{proj}/recap", json={"cutoff": False}, headers=H)
    by = {i["title"]: i for i in T._lore_items(proj)[0]}
    assert "Mara fact 4" in by["Mara"]["content"] and "Late Arrival" in by
    client.put(f"/api/text/project/{proj}/recap", json={"cutoff": True}, headers=H)


def test_hand_edits_win_over_the_cutoff(client, H, proj):
    E = ents(client, H, proj)
    client.patch(f"/api/text/entity/{E['Tomas']['id']}", json={"content": "My own Tomas text."}, headers=H)
    by = {i["title"]: i for i in T._lore_items(proj)[0]}
    assert by["Tomas"]["content"].startswith("My own Tomas text.")


def test_chapters_view(client, H, proj):
    E = ents(client, H, proj)
    d = client.get(f"/api/text/entity/{E['Mara']['id']}/chapters", headers=H).get_json()
    assert [c["chunk"] for c in d["chapters"]] == [0, 1, 2, 3, 4]
    assert [c["after_start"] for c in d["chapters"]] == [False, False, True, True, True]
    assert d["later"] == 3 and d["start_label"] and d["chapters"][0]["voice"] == ["Line 0"]
    assert client.get("/api/text/entity/999999/chapters", headers=H).status_code == 404


def test_mentions(client, H, proj):
    E = ents(client, H, proj)
    d = client.get(f"/api/text/entity/{E['Mara']['id']}/mentions", headers=H).get_json()
    assert d["total"] >= 5 and len(d["chapters"]) == 5 and all(len(c["lines"]) <= 4 for c in d["chapters"])
    assert all("Mara" in line for c in d["chapters"] for line in c["lines"])
    # one-word names keep their capital: "Will" the name would not match "will"
    e = {"name": "Will", "aliases": []}
    from story_tools import find_mentions
    chunks = [{"idx": 0, "label": "A", "text": "Will left. The will was read. Free will."}]
    assert find_mentions(e, chunks)["total"] == 1
    assert find_mentions(e, chunks, case_sensitive=False)["total"] == 3


def test_prose_scan(client, H, proj):
    r = client.post(f"/api/text/project/{proj}/prose-scan", json={}, headers=H).get_json()
    assert r["words"] > 100 and any(c["phrase"] == "barely above a whisper" for c in r["cliches"])
    assert len(r["per_chunk"]) == 5 and r["tags"]["fancy"] >= 5
    assert r["cliches"][0]["examples"][0]["label"]
    one = client.post(f"/api/text/project/{proj}/prose-scan", json={"chunks": [0]}, headers=H).get_json()
    assert len(one["per_chunk"]) == 1
    t = P.scan("She ran. She hid. She waited. A shiver ran down her spine. It was very, very quiet.")
    assert t["repeated_starts"][0]["run"] == 3 and t["filler"]["very"] == 2
    assert any("spine" in c["phrase"] for c in t["cliches"])
    w = client.post("/api/prose/scan", json={"card": {"first_mes": "Her voice was barely above a whisper."}}, headers=H).get_json()
    assert w["warnings"] and "First message" in w["warnings"][0]
    assert client.post("/api/prose/scan", json={"text": " "}, headers=H).status_code == 400


def test_personality_layers_and_cliche_warnings():
    card = {"name": "Mara", "description": "Mara is a courier.", "personality": "Calm.", "scenario": "A street.",
            "first_mes": "Her voice was barely above a whisper.", "mes_example": "<START>\n{{char}}: Hi.",
            "tags": [f"t{i}" for i in range(10)],
            "structured_profile": {"with_strangers": "Guarded and polite.", "with_close": "Teasing and blunt."}}
    fixed, warns = validate_card(card, {})
    assert any("Stock phrases" in w for w in warns)
    txt = format_structured_profile_text("Mara", fixed["structured_profile"])
    assert 'With Strangers ("Guarded and polite.")' in txt and 'With People Close To Them ("Teasing and blunt.")' in txt
    assert "With Strangers" not in format_structured_profile_text("X", {})     # old cards export exactly as before


def test_relation_graph(client, H, proj):
    g = client.get(f"/api/text/project/{proj}/relations", headers=H).get_json()
    names = {n["id"]: n["name"] for n in g["nodes"]}
    assert "Mara" in names.values() and "Tomas" in names.values() and "Late Arrival" not in names.values()  # cutoff on
    [ed] = g["edges"]
    labels = ed["a_to_b"] + ed["b_to_a"]
    assert {names[ed["a"]], names[ed["b"]]} == {"Mara", "Tomas"} and "friend" in labels and "enemy" not in labels
    assert next(n for n in g["nodes"] if n["name"] == "Mara")["degree"] == 1
    client.put(f"/api/text/project/{proj}/recap", json={"cutoff": False}, headers=H)
    g = client.get(f"/api/text/project/{proj}/relations", headers=H).get_json()
    assert "Late Arrival" in {n["name"] for n in g["nodes"]}
    client.put(f"/api/text/project/{proj}/recap", json={"cutoff": True}, headers=H)
    assert client.get("/api/text/project/999999/relations", headers=H).status_code == 404
