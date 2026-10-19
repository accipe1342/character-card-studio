"""SillyTavern World Info fields, the activation simulator, the lore graph, the LORE trash and re-sending from TEXT."""
import json
import re
import pytest

import database as db
import text_module as T
from lore_tools import lore_graph, simulate
from preview import normalise_lore_items
from test_text_flow import fake_extract, wait

O = {"Origin": "http://localhost:5173"}


@pytest.fixture(scope="module")
def tproject(client, H):
    T.extract_chunk = fake_extract
    text = "\n\n".join(f"Chapter {n}\n\n" + " ".join(f"w{n}x{k}" for k in range(400)) for n in range(1, 6))
    pid = client.post("/api/text/ingest", json={"name": "WI Fic", "text": text, "chunk_chars": 2000}, headers=H).get_json()["id"]
    job = client.post(f"/api/text/project/{pid}/extract", json={"mode": "deep", "parallel": 2, "condense": False},
                      headers=H).get_json()["job_id"]
    wait(client, H, job)
    return pid


def item(title, et="character", keys=(), content="", **kw):
    return {"title": title, "entry_type": et, "keys": list(keys), "content": content, **kw}


def test_defaults_sticky_characters_and_always_on_entries():
    its = normalise_lore_items([item("Yuna", keys=["Yuna"]), item("Sword", "item"),
                                item("Cast Roster", "concept"), item("Story So Far", "concept")])
    by = {i["title"]: i for i in its}
    assert by["Yuna"]["sticky"] == 2 and by["Sword"]["sticky"] == 0
    assert by["Cast Roster"]["constant"] and by["Story So Far"]["constant"] and by["Story So Far"]["order"] == 999
    # stored values beat the defaults; 0 is a real value, not "unset"
    its = normalise_lore_items([item("Yuna", sticky=0, position=4, role=1, probability=0, constant=1,
                                     secondary_keys=["sad"], selective_logic=3, group_name="g", vectorized=1)])
    y = its[0]
    assert (y["sticky"], y["position"], y["role"], y["probability"], y["constant"]) == (0, 4, 1, 0, True)
    assert y["secondaryKeys"] == ["sad"] and y["selectiveLogic"] == 3 and y["group"] == "g" and y["vectorized"]


def test_patch_saves_wi_fields_marks_edits_and_exports(client, H):
    pid = db.create_lore_project("WI export")
    lid = db.save_lore_entry(pid, None, "Yuna", "character", ["Yuna"], "s", "Yuna is a summoner.")
    full = client.get(f"/api/lore/entry/{lid}", headers=H).get_json()
    assert not full["user_edited"]
    body = {**full, "position": 4, "role": 2, "sticky": 3, "cooldown": 1, "delay": 2, "probability": 50,
            "secondary_keys": ["temple", " "], "selective_logic": 2, "group_name": "summoners", "group_weight": 70,
            "group_prioritize": True, "vectorized": True, "char_filter": ["Tidus"], "constant": None}
    assert client.patch(f"/api/lore/entry/{lid}", json=body, headers={**H, **O}).status_code == 200
    full = client.get(f"/api/lore/entry/{lid}", headers=H).get_json()
    assert not full["user_edited"]                      # settings only: the text was not touched
    client.patch(f"/api/lore/entry/{lid}", json={**full, "content": "Yuna, edited by hand."}, headers={**H, **O})
    assert client.get(f"/api/lore/entry/{lid}", headers=H).get_json()["user_edited"] == 1
    e = list(client.get(f"/api/lore/export?project_id={pid}", headers=H).get_json()["entries"].values())[0]
    assert (e["position"], e["role"], e["sticky"], e["cooldown"], e["delay"], e["probability"]) == (4, 2, 3, 1, 2, 50)
    assert e["keysecondary"] == ["temple"] and e["selective"] and e["selectiveLogic"] == 2
    assert e["group"] == "summoners" and e["groupWeight"] == 70 and e["groupOverride"] and e["vectorized"]
    assert e["characterFilter"]["names"] == ["Tidus"]
    book = client.post("/api/export/v2", json={"card": {"name": "Yuna"}, "lore_project_id": pid}, headers=H).get_json()
    be = book["data"]["character_book"]["entries"][0]
    assert be["secondary_keys"] == ["temple"] and be["extensions"]["sticky"] == 3 and be["extensions"]["role"] == 2
    assert client.patch("/api/lore/entry/999999", json={"title": "x"}, headers={**H, **O}).status_code == 404


def test_simulator_rules():
    its = normalise_lore_items([
        item("Recap", "concept", content="R" * 40, constant=1),
        item("Yuna", keys=["Yuna"], content="Yuna carries the Staff of Light."),
        item("Staff of Light", "item", keys=["Staff of Light"], content="A holy staff."),
        item("Temple", "place", keys=["temple"], content="x", secondary_keys=["night"], selective_logic=0),
        item("Big", "concept", keys=["Yuna"], content="B" * 8000),
        item("A1", "concept", keys=["dragon"], content="a", group_name="g", group_weight=10),
        item("A2", "concept", keys=["dragon"], content="b", group_name="g", group_weight=90),
    ])
    r = simulate(its, "Yuna walks into the temple with a dragon.", budget=600)
    kept = {a["title"]: a for a in r["activated"]}
    dropped = {d["title"]: d for d in r["dropped"]}
    assert kept["Recap"]["why"].startswith("constant")
    assert "Yuna" in kept and "recursion" in kept["Staff of Light"]["why"]
    assert "Temple" not in kept and any(b["title"] == "Temple" for b in r["blocked"])     # needs "night" too
    assert "budget" in dropped["Big"]["dropped"]
    assert "A2" in kept and "inclusion group" in dropped["A1"]["dropped"]
    assert r["activated"][0]["title"] == "Recap"                                          # constants first
    assert simulate(its, "yuna at the temple at night", whole_words=True)["activated"][1]["title"] in ("Yuna", "Temple", "Big")


def test_graph_orphans_and_loops():
    its = normalise_lore_items([item("A", keys=["alpha"], content="knows beta"), item("B", keys=["beta"], content="knows alpha"),
                                item("C", keys=["gamma"], content="alone"), item("D", content="no keys")])
    for n, it in enumerate(its):
        it["lore_id"] = n
    g = lore_graph(its)
    assert {(e["from"], e["to"]) for e in g["edges"]} == {(0, 1), (1, 0)}
    assert g["loops"] == [["A", "B"]] and "C" in g["orphans"] and g["no_keys"] == ["D"]


def test_simulate_and_graph_routes(client, H):
    pid = db.create_lore_project("Sim")
    db.save_lore_entry(pid, None, "Yuna", "character", ["Yuna"], "", "Yuna.")
    r = client.post("/api/lore/simulate", json={"project_id": pid, "text": "Hi Yuna"}, headers={**H, **O}).get_json()
    assert [a["title"] for a in r["activated"]] == ["Yuna"] and r["budget"] == 2048
    assert client.post("/api/lore/simulate", json={"project_id": pid, "text": " "}, headers={**H, **O}).status_code == 400
    assert client.get(f"/api/lore/project/{pid}/graph", headers=H).get_json()["nodes"][0]["title"] == "Yuna"


def test_lore_trash(client, H):
    pid = db.create_lore_project("Trash")
    lid = db.save_lore_entry(pid, None, "Gone", "concept", [], "", "x")
    client.delete(f"/api/lore/entry/{lid}", headers={**H, **O})
    assert all(e["id"] != lid for e in client.get("/api/lore/entries", headers=H).get_json())
    assert [e["id"] for e in db.list_lore_entries(crawl_id=pid)] == []
    assert [e["id"] for e in client.get(f"/api/lore/trash?project_id={pid}", headers=H).get_json()["entries"]] == [lid]
    assert next(p for p in db.list_lore_projects() if p["id"] == pid)["entry_count"] == 0
    client.post(f"/api/lore/entry/{lid}/restore", headers={**H, **O})
    assert [e["id"] for e in db.list_lore_entries(crawl_id=pid)] == [lid]
    client.delete(f"/api/lore/entry/{lid}", headers={**H, **O})
    assert client.delete(f"/api/lore/trash?project_id={pid}", headers={**H, **O}).get_json()["purged"] == 1
    assert client.post(f"/api/lore/entry/{lid}/restore", headers={**H, **O}).status_code == 404


def test_cast_roster_recap_position_and_resend(client, H, tproject):
    client.put(f"/api/text/project/{tproject}/recap", json={"text": "Recap v1.", "upto": -1, "position": "depth"}, headers=H)
    assert client.get(f"/api/text/project/{tproject}/recap", headers=H).get_json()["position"] == "depth"
    first = client.post(f"/api/text/project/{tproject}/commit", headers=H).get_json()
    lid = first["lore_project_id"]
    assert first["mode"] == "new"
    ex = client.get(f"/api/lore/export?project_id={lid}", headers=H).get_json()
    by = {e["comment"].rsplit(" - ", 1)[0]: e for e in ex["entries"].values()}
    assert by["Cast Roster"]["constant"] and "- Yuna" in by["Cast Roster"]["content"] and "- Rikku" in by["Cast Roster"]["content"]
    assert by["Story So Far"]["position"] == 4 and by["Story So Far"]["depth"] == 4 and by["Story So Far"]["role"] == 0
    assert by["Yuna"]["sticky"] == 2
    # hand-edit Yuna in LORE, delete Rikku there, then change the recap and re-send
    rows = {e["title"]: e for e in db.list_lore_entries(crawl_id=lid)}
    yuna = client.get(f"/api/lore/entry/{rows['Yuna']['id']}", headers=H).get_json()
    client.patch(f"/api/lore/entry/{yuna['id']}", json={**yuna, "content": "My Yuna."}, headers={**H, **O})
    client.delete(f"/api/lore/entry/{rows['Story Timeline']['id']}", headers={**H, **O})
    client.put(f"/api/text/project/{tproject}/recap", json={"text": "Recap v2.", "upto": -1, "position": "before"}, headers=H)
    E = {e["name"]: e for e in client.get(f"/api/text/project/{tproject}", headers=H).get_json()["entities"]}
    client.patch(f"/api/text/entity/{E['Rikku']['id']}", json={"keep": False}, headers=H)
    again = client.post(f"/api/text/project/{tproject}/commit", headers=H).get_json()
    assert again["mode"] == "update" and again["lore_project_id"] == lid
    assert again["kept_edited"] == 1 and again["trashed"] == 2      # Rikku, and the roster (one character left)
    rows = {e["title"]: e for e in db.list_lore_entries(crawl_id=lid)}
    assert "Story Timeline" not in rows and "Rikku" not in rows             # deleted in LORE / no longer kept
    assert any(e["title"] == "Rikku" for e in db.list_lore_entries(crawl_id=lid, deleted=True))   # restorable
    assert db.get_lore_entry(rows["Yuna"]["id"])["content"] == "My Yuna."     # hand edit kept
    recap = db.get_lore_entry(rows["Story So Far"]["id"])
    assert recap["content"] == "Recap v2." and recap["position"] == 0
    fresh = client.post(f"/api/text/project/{tproject}/commit", json={"mode": "new"}, headers=H).get_json()
    assert fresh["lore_project_id"] != lid


def test_narrator_card_keeps_system_prompt(client, H, tproject):
    T._request = lambda provider, model, user, system=None, **k: {
        "name": "WI Narrator", "description": "World.", "personality": "", "scenario": "",
        "first_mes": "Opening.", "system_prompt": "Narrate only.", "tags": []}
    r = client.post(f"/api/text/project/{tproject}/narrator", json={}, headers=H).get_json()
    card = db.get_card(r["card_id"])
    assert card["system_prompt"] == "Narrate only." and "Narrator rules" not in card["description"]


def test_recap_position_alone_keeps_the_recap(client, H, tproject):
    client.put(f"/api/text/project/{tproject}/recap", json={"text": "Keep me.", "upto": -1}, headers=H)
    client.put(f"/api/text/project/{tproject}/recap", json={"position": "depth"}, headers=H)
    r = client.get(f"/api/text/project/{tproject}/recap", headers=H).get_json()
    assert r["text"] == "Keep me." and r["position"] == "depth"


def test_cards_for_main_cast_and_group_card(client, H, tproject, monkeypatch):
    import app as A
    seen = []

    def fake_card(source, provider, model, options=None):
        seen.append((source["title"], dict(options or {})))
        return {"name": source["title"], "description": f"{source['title']} card.", "personality": "", "scenario": "",
                "first_mes": "Hi.", "mes_example": "", "tags": [], "structured_profile": {}}
    monkeypatch.setattr(A, "generate_full_card", fake_card)
    monkeypatch.setattr(A, "_gen_request", lambda p, m, prompt: {"name": "WI Fic Cast", "description": "Both.",
                                                                    "personality": "", "scenario": "", "first_mes": "Yo.",
                                                                    "mes_example": "", "tags": []})
    E = {e["name"]: e for e in client.get(f"/api/text/project/{tproject}", headers=H).get_json()["entities"]}
    client.patch(f"/api/text/entity/{E['Rikku']['id']}", json={"keep": True}, headers=H)
    r = client.post(f"/api/text/project/{tproject}/cast-cards", json={"group": True, "token_target": "lean"}, headers=H).get_json()
    assert r["count"] == 2
    j = wait(client, H, r["job_id"])["result"]
    names = sorted(c["name"] for c in j["cards"])
    assert names == ["Rikku", "Yuna"] and j["group_card_id"] and not j["failed"]
    assert all(o["token_target"] == "lean" and o["story_point"] and o.get("lore_aware") for _, o in seen)
    member = db.get_card(j["cards"][0]["card_id"])
    assert member["name"] in ("Rikku", "Yuna")                      # the group card did not overwrite a member
    assert db.get_card(j["group_card_id"])["name"] == "WI Fic Cast"
    # running it again keeps the earlier cards and makes new ones
    j2 = wait(client, H, client.post(f"/api/text/project/{tproject}/cast-cards", json={}, headers=H).get_json()["job_id"])["result"]
    assert {c["card_id"] for c in j2["cards"]}.isdisjoint({c["card_id"] for c in j["cards"]})


ST_CHAT = "\n".join(json.dumps(x) for x in (
    {"user_name": "You", "character_name": "Yuna", "create_date": "2026-10-01", "chat_metadata": {}},
    *[{"name": "Yuna" if i % 2 else "You", "is_user": not i % 2, "is_system": False, "mes": f"Message {i}. " + "Words here. " * 20}
      for i in range(50)],
    {"name": "System", "is_user": False, "is_system": True, "mes": "hidden note"},
))


def test_st_chat_import_and_append(client, H, tproject):
    import io
    title, text = T.stchat_to_text(ST_CHAT.encode())
    assert title == "Chat with Yuna" and "Yuna: Message 1." in text and "hidden note" not in text
    assert "Part 1: messages 1-40" in text and "Part 2: messages 41-50" in text
    r = client.post("/api/text/ingest", data={"file": (io.BytesIO(ST_CHAT.encode()), "chat.jsonl"), "chunk_chars": "2000"},
                    headers=H, content_type="multipart/form-data").get_json()
    assert r["name"] == "Chat with Yuna" and r["chunks"] >= 2
    a = client.post(f"/api/text/project/{tproject}/append", data={"file": (io.BytesIO(ST_CHAT.encode()), "more.jsonl")},
                    headers=H, content_type="multipart/form-data").get_json()
    assert a["new_chunks"] >= 2 and a["chunks"] == 5 + a["new_chunks"]
    # only the new chunks are extracted
    T.calls_before = len(__import__("test_text_flow").calls)
    job = client.post(f"/api/text/project/{tproject}/extract", json={"mode": "deep", "parallel": 2}, headers=H).get_json()["job_id"]
    wait(client, H, job)
    import test_text_flow
    new_calls = test_text_flow.calls[T.calls_before:]
    assert set(new_calls) == set(range(5, 5 + a["new_chunks"])), new_calls     # the first 5 chunks are not redone
    assert client.post(f"/api/text/project/{tproject}/append", json={"text": "short"}, headers=H).status_code == 400


def test_relationship_tracker_and_arcs(monkeypatch):
    ents = [{"name": "Yuna", "entity_type": "character", "aliases": ["Yunie"],
             "relations": [{"with": "Rikku", "relation": "cousin"}, {"with": "Tidus", "relation": "lover"}]},
            {"name": "Rikku", "entity_type": "character", "aliases": [], "relations": [{"with": "yunie", "relation": "Cousin"}]},
            {"name": "Tidus", "entity_type": "character", "aliases": [], "relations": []}]
    t = T.relationship_tracker(ents)
    assert t.count("Yuna & Rikku") + t.count("Rikku & Yuna") == 1 and "cousin" in t and "lover" in t
    assert T.relationship_tracker(ents[:1] + [ents[2]]) == ""          # one pair only: no entry
    parts = [f"[Part {i}] thing {i}" for i in range(30)]
    monkeypatch.setattr(T, "_request", lambda p, m, u, system=None, **k: {"title": "Arc", "summary": "Condensed."})
    lines, arcs = T.tier_parts(parts, "x", "y")
    assert arcs == 3 and lines[0].startswith("[ARC 1: Arc]") and lines[-1] == "[Part 29] thing 29" and len(lines) == 13
    assert T.tier_parts(parts[:10], "x", "y") == (parts[:10], 0)


def test_sweep_history_and_rewrite(client, H, tproject, monkeypatch):
    import critic_tools as C

    def fake(provider, model, user, system=None, **k):
        if system == C.SWEEP_SYSTEM:
            n = int(re.search(r"w(\d)x", user).group(1)) if re.search(r"w(\d)x", user) else 5
            if "Chapter 3" in user:
                raise RuntimeError("model hiccup")
            return {"score": n + 3, "scores": {"prose": n + 2, "dialogue": 4}, "summary": "Stuff.", "worst": "Flat prose",
                    "quote": "w1x3 w1x4", "fix": "Vary it", "best": ""}
        if system == C.REWRITE_SYSTEM:
            assert "w1x3" in user
            return {"rewrite": "A better line.", "notes": "Varied the rhythm."}
        raise AssertionError(system)
    monkeypatch.setattr(T, "_request", fake)
    j = wait(client, H, client.post(f"/api/text/project/{tproject}/critique/sweep", json={}, headers=H).get_json()["job_id"])
    c = client.get(f"/api/text/critique/{j['result']['critique_id']}", headers=H).get_json()["result"]
    rows = {x["label"]: x for x in c["sweep"]}
    assert rows["Chapter 1"]["score"] == 4 and "error" in rows["Chapter 3"] and "Weakest: Chapter 1 (4)" in c["verdict"]
    assert "## Chapter 2 - 5/10" in c["markdown"]
    hist = client.get(f"/api/text/project/{tproject}/critiques", headers=H).get_json()
    assert hist[0]["kind"] == "sweep" and hist[0]["avg"] and "Prose" in hist[0]["scores"]
    r = client.post(f"/api/text/project/{tproject}/rewrite", json={"quote": "W1X3  w1x4", "fix": "Vary it"}, headers=H).get_json()
    assert r["found"] and r["label"] == "Chapter 1" and r["rewrite"] == "A better line." and "w1x0" in r["original"]
    nf = client.post(f"/api/text/project/{tproject}/rewrite", json={"quote": "w1x3 nowhere in text", "fix": ""}, headers=H).get_json()
    assert nf["found"] is False and nf["original"] == "w1x3 nowhere in text"
    assert client.post(f"/api/text/project/{tproject}/rewrite", json={}, headers=H).status_code == 400


def test_bundle_export_import_roundtrip(client, H, tproject):
    import io, zipfile
    lid = client.get(f"/api/text/project/{tproject}", headers=H).get_json()["lore_project_id"]
    assert lid
    c = client.get("/api/bundle/contents", headers=H).get_json()
    assert any(p["id"] == tproject for p in c["text_projects"]) and any(p["id"] == lid for p in c["lore_projects"])
    r = client.post("/api/bundle/export", json={"text_ids": [tproject]}, headers={**H, **O})
    assert r.status_code == 200 and r.mimetype == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.data))
    names = z.namelist()
    assert "data.json" in names and any(n.startswith("lorebooks/") for n in names) and any(n.startswith("cards/") for n in names)
    data = json.loads(z.read("data.json"))
    n_ents = len(data["tables"]["text_entities"])
    n_lore = len(data["tables"]["lore_entries"])
    res = client.post("/api/bundle/import", data={"file": (io.BytesIO(r.data), "b.zip")}, headers={**H, **O},
                      content_type="multipart/form-data").get_json()
    assert res["added"]["text_projects"] == 1 and res["added"]["text_entities"] == n_ents
    assert res["added"]["lore_entries"] == n_lore and res["added"]["cards"] >= 1 and res["backup"]
    new_pid = res["ids"]["text_projects"][0]
    newp = client.get(f"/api/text/project/{new_pid}", headers=H).get_json()
    assert newp["name"].endswith("(imported)") and newp["lore_project_id"] == res["ids"]["lore_crawls"][0]
    assert len(db.list_lore_entries(crawl_id=newp["lore_project_id"])) == n_lore
    assert client.post("/api/bundle/import", data={"file": (io.BytesIO(b"nope"), "x.zip")}, headers={**H, **O},
                       content_type="multipart/form-data").status_code == 400
    assert client.post("/api/bundle/export", json={}, headers={**H, **O}).status_code == 400


def test_global_search(client, H, tproject):
    r = client.get("/api/search?q=Yuna", headers=H).get_json()
    assert r["entities"] and r["entities"][0]["name"] == "Yuna" and r["entities"][0]["project_id"]
    assert any(x["title"] == "Yuna" for x in r["lore"]) and any(c["name"] == "Yuna" for c in r["cards"])
    assert client.get("/api/search?q=WI Fic", headers=H).get_json()["texts"]
    assert client.get("/api/search?q=y", headers=H).get_json()["cards"] == []
    assert client.get("/api/search?q=%25%25", headers=H).status_code == 200
