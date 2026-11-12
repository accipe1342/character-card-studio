"""The studio helper (SCRIBE-01), through the REAL model request code against a scripted OpenAI-compatible server:
multi-step work, reading before editing, Keep / Undo with conflict protection, messy model output, and errors."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import app as APP
import database as D
import generator
import helper as HLP
import text_module as T
from test_text_flow import wait

SCRIPT, SEEN = [], []


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(body)
        item = SCRIPT.pop(0) if SCRIPT else '{"say": "Report: nothing scripted.", "actions": []}'
        status, content = item if isinstance(item, tuple) else (200, item if isinstance(item, str) else json.dumps(item))
        out = json.dumps({"choices": [{"message": {"content": content}}], "usage": {}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


@pytest.fixture(scope="module")
def server():
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


@pytest.fixture(autouse=True)
def real_model(server, monkeypatch):
    monkeypatch.setattr(HLP, "_request", generator._request)
    monkeypatch.setenv("LOCAL_OPENAI_BASE_URL", server)
    monkeypatch.setattr(generator, "_RETRY_BACKOFF_SECONDS", [0, 0])
    SCRIPT.clear(); SEEN.clear()


def chat(client, H, message, **kw):
    return client.post("/api/helper/chat", json={"message": message, "provider": "local", "model": "m", **kw}, headers=H)


def sys_of(i=-1):
    return SEEN[i]["messages"][0]["content"]


def user_of(i=-1):
    return SEEN[i]["messages"][1]["content"]


def test_builds_a_character_and_a_lorebook(client, H):
    SCRIPT[:] = [
        {"say": "Proposal: a courier card and a small lorebook.", "actions": [
            {"tool": "create_card", "args": {"fields": {"name": "Mara Vell", "description": "Mara is a courier in a rainy port.",
                                                        "personality": "Dry and quick.", "first_mes": "*Mara shakes off the rain.*",
                                                        "tags": "courier, port", "structured_profile": {"likes": "tea, rain"}}}},
            {"tool": "create_lore_project", "args": {"name": "Rain Port"}}]},
        lambda: {"say": "", "actions": [
            {"tool": "add_lore_entry", "args": {"project_id": last_result("create_lore_project")["project_id"], "title": "Old Harbor",
                                                "entry_type": "place", "keywords": "harbor, docks", "content": "Docks that never sleep."}},
            {"tool": "add_lore_entry", "args": {"project_id": last_result("create_lore_project")["project_id"], "title": "The Ledger",
                                                "entry_type": "item", "keywords": ["ledger"], "content": "Mara took it.",
                                                "known_only_to": ["Tomas"]}}]},
        {"say": "Report: card and lorebook ready.", "actions": []},
    ]
    r = chat(client, H, "Make me a courier named Mara and a lorebook for her port", context={"studio": "character"})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()
    assert d["steps"] == 3 and d["reply"].startswith("Proposal: a courier card") and "Report: card and lorebook ready." in d["reply"]
    assert [c["label"] for c in d["changes"]] == ["New card: Mara Vell", "New lorebook: Rain Port", "New entry: Old Harbor", "New entry: The Ledger"]
    card = D.get_card(d["changes"][0]["target_id"])
    assert card["description"] == "Mara is a courier in a rainy port." and card["tags"] == ["courier", "port"]
    assert card["structured_profile"]["likes"] == ["tea", "rain"]
    pid = d["changes"][1]["target_id"]
    ents = {e["title"]: D.get_lore_entry(e["id"]) for e in D.list_lore_entries(crawl_id=pid)}
    assert ents["Old Harbor"]["keywords"] == ["harbor", "docks"] and ents["Old Harbor"]["entry_type"] == "place"
    assert ents["The Ledger"]["char_filter"] == ["Tomas"]
    # the model saw each step's results
    assert '"created": "Mara Vell"' in user_of(1) and "RESULTS (step 1)" in user_of(1)
    assert "SCRIBE-01" in sys_of(0) and "add_lore_entry" in sys_of(0) and "CHARACTER studio" in sys_of(0)


def last_result(tool):
    """The newest result of `tool` the server sent back to the model (read from the transcript it received)."""
    text = user_of()
    for line in reversed(text.splitlines()):
        if line.startswith("{") and f'"tool": "{tool}"' in line:
            return json.loads(line)["result"]
    raise AssertionError(f"no {tool} result in transcript")


# the fake server calls items lazily so a later step can use an id from an earlier one
_orig_do_post = Fake.do_POST


def _do_post(self):
    if SCRIPT and callable(SCRIPT[0]):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(body)
        content = json.dumps(SCRIPT.pop(0)())
        out = json.dumps({"choices": [{"message": {"content": content}}], "usage": {}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)
        return
    _orig_do_post(self)


Fake.do_POST = _do_post


@pytest.fixture
def mara(client, H):
    sid = D.save_source({"wiki_base": "manual", "page_name": "h", "url": "manual://helper-test/mara", "title": "Mara",
                         "raw_html": "", "raw_infobox": {}, "raw_sections": {}, "normalized": {}})
    return D.create_or_update_card(sid, {"name": "Mara", "description": "Old text.", "personality": "Dry.", "scenario": "",
                                         "first_mes": "Hi.", "mes_example": "", "tags": ["a"], "structured_profile": {},
                                         "alternate_greetings": []}, force_new=True)


def test_reads_before_editing_and_undo(client, H, mara):
    SCRIPT[:] = [
        {"say": "", "actions": [{"tool": "get_card", "args": {"card_id": mara}}]},
        {"say": "", "actions": [{"tool": "update_card", "args": {"card_id": mara, "fields": {"description": "Mara runs parcels at night."}}}]},
        {"say": "Report: description rewritten.", "actions": []},
    ]
    d = chat(client, H, "Rewrite this card's description", context={"studio": "character", "card_id": mara}).get_json()
    assert "The open card is card_id %d (Mara)" % mara in sys_of(0)
    assert '"description": "Old text."' in user_of(1)                      # it was shown the card before editing
    [ch] = d["changes"]
    assert ch["label"] == "Mara: description" and ch["status"] == "open" and not ch["created"]
    assert D.get_card(mara)["description"] == "Mara runs parcels at night." and D.get_card(mara)["personality"] == "Dry."
    assert d["touched"] == [{"kind": "card", "id": mara}]
    u = client.post(f"/api/helper/change/{ch['id']}/undo", headers=H).get_json()
    assert u["ok"] and D.get_card(mara)["description"] == "Old text."
    assert client.post(f"/api/helper/change/{ch['id']}/undo", headers=H).get_json()["status"] == "undone"   # twice is fine


def test_undo_is_blocked_when_the_item_changed_since(client, H, mara):
    SCRIPT[:] = [{"say": "", "actions": [{"tool": "update_card", "args": {"card_id": mara, "fields": {"scenario": "A rainy port."}}}]},
                 {"say": "Done.", "actions": []}]
    [ch] = chat(client, H, "Set the scenario").get_json()["changes"]
    card = D.get_card(mara)
    D.create_or_update_card(card["source_id"], {**card, "scenario": "My own scenario."}, card_id=mara)   # the user edits it
    r = client.post(f"/api/helper/change/{ch['id']}/undo", headers=H)
    assert r.status_code == 409 and "overwrite newer work" in r.get_json()["error"]
    assert D.get_card(mara)["scenario"] == "My own scenario."
    assert client.post(f"/api/helper/change/{ch['id']}/keep", headers=H).get_json()["status"] == "kept"


def test_undo_creations_and_trash(client, H):
    SCRIPT[:] = [{"say": "", "actions": [{"tool": "create_lore_project", "args": {"name": "Undo Book"}}]},
                 lambda: {"say": "", "actions": [{"tool": "add_lore_entry", "args": {
                     "project_id": last_result("create_lore_project")["project_id"], "title": "Gate", "content": "A gate."}}]},
                 {"say": "Done.", "actions": []}]
    proj_ch, entry_ch = chat(client, H, "Make a lorebook").get_json()["changes"]
    pid, lid = proj_ch["target_id"], entry_ch["target_id"]
    assert D.get_lore_entry(lid)["keywords"] == ["Gate"]                   # no keywords given: the title is used
    r = client.post(f"/api/helper/change/{proj_ch['id']}/undo", headers=H)
    assert r.status_code == 409 and "has entries" in r.get_json()["error"]
    assert client.post(f"/api/helper/change/{entry_ch['id']}/undo", headers=H).get_json()["ok"]
    assert D.get_lore_entry(lid)["deleted"] == 1                           # a created entry goes to the trash
    assert client.post(f"/api/helper/change/{proj_ch['id']}/undo", headers=H).get_json()["ok"]
    assert HLP.project_state(pid) is None
    # delete -> trash, undo -> back
    keep = D.create_lore_project("Keep Book")
    lid2 = D.save_lore_entry(crawl_id=keep, source_id=None, title="Tower", entry_type="place", keywords=["tower"],
                             summary="", content="Tall.")
    SCRIPT[:] = [{"say": "", "actions": [{"tool": "delete_lore_entry", "args": {"entry_id": lid2}}]}, {"say": "Trashed.", "actions": []}]
    [ch] = chat(client, H, "Delete the tower entry").get_json()["changes"]
    assert D.get_lore_entry(lid2)["deleted"] == 1 and ch["label"] == "To the LORE trash: Tower"
    client.post(f"/api/helper/change/{ch['id']}/undo", headers=H)
    assert D.get_lore_entry(lid2)["deleted"] == 0 and D.get_lore_entry(lid2)["content"] == "Tall."
    # an edit by the helper counts as a hand edit (TEXT re-sends keep it); undo restores that flag too
    SCRIPT[:] = [{"say": "", "actions": [{"tool": "update_lore_entry", "args": {"entry_id": lid2, "fields": {"content": "Very tall.", "keywords": "tower, spire"}}}]},
                 {"say": "Done.", "actions": []}]
    [ch] = chat(client, H, "Edit the tower").get_json()["changes"]
    e = D.get_lore_entry(lid2)
    assert e["content"] == "Very tall." and e["keywords"] == ["tower", "spire"] and e["user_edited"] == 1
    client.post(f"/api/helper/change/{ch['id']}/undo", headers=H)
    e = D.get_lore_entry(lid2)
    assert e["content"] == "Tall." and e["keywords"] == ["tower"] and not e["user_edited"]


def test_messy_models_and_mistakes(client, H, mara):
    SCRIPT[:] = ["Report: a lorebook keyword is the word that makes an entry appear."]          # plain prose
    d = chat(client, H, "What is a keyword?").get_json()
    assert d["reply"] == "Report: a lorebook keyword is the word that makes an entry appear." and d["changes"] == [] and d["steps"] == 1
    SCRIPT[:] = ['Sure.\n```json\n{"tool": "get_card", "args": {"card_id": %d}}\n```' % mara,  # one action at the top level
                 '{"say": "Query: which tone?", "actions": []}']
    d = chat(client, H, "Look at my card").get_json()
    assert d["actions"] == [{"tool": "get_card", "ok": True, "error": None}] and d["reply"] == "Query: which tone?"
    SCRIPT[:] = [{"say": "", "actions": [{"tool": "make_magic", "args": {}}, {"tool": "get_card", "args": {"card_id": 999999}},
                                         {"tool": "update_card", "args": {"card_id": "abc"}}]},
                 {"say": "Report: corrected.", "actions": []}]
    d = chat(client, H, "Do it").get_json()
    errs = [a["error"] for a in d["actions"]]
    assert "Unknown tool 'make_magic'" in errs[0] and "No card with id 999999" in errs[1] and "must be a number" in errs[2]
    assert "Unknown tool 'make_magic'" in user_of()                              # the model was told
    SCRIPT[:] = [{"say": "", "actions": [{"tool": "list_cards", "args": {}}]}] * 7
    d = chat(client, H, "Loop forever").get_json()
    assert d["steps"] == HLP.MAX_STEPS and "step limit reached" in d["reply"]
    SCRIPT[:] = [(503, "{}")] * 3
    r = chat(client, H, "Hello")
    assert r.status_code == 502 and "model call failed" in r.get_json()["error"].lower()
    SCRIPT[:] = [{"say": "", "actions": [{"tool": "update_card", "args": {"card_id": mara, "fields": {"favorite_color": "red"}}}]},
                 {"say": "Sorry.", "actions": []}]
    assert "Unknown card field 'favorite_color'" in chat(client, H, "x").get_json()["actions"][0]["error"]


def test_history_and_chat_list(client, H):
    SCRIPT[:] = ['{"say": "Query: what world is she from?", "actions": []}']
    d1 = chat(client, H, "Make a knight").get_json()
    SCRIPT[:] = ['{"say": "Noted.", "actions": []}']
    chat(client, H, "A desert kingdom", chat_id=d1["chat_id"])
    assert "USER: Make a knight\nYOU: Query: what world is she from?\nUSER: A desert kingdom" in user_of()
    g = client.get(f"/api/helper/chat/{d1['chat_id']}", headers=H).get_json()
    assert [m["role"] for m in g["messages"]] == ["user", "helper", "user", "helper"]
    assert any(c["id"] == d1["chat_id"] for c in client.get("/api/helper/chats", headers=H).get_json())
    assert client.get("/api/helper/chat/999999", headers=H).status_code == 404
    assert client.post("/api/helper/chat", json={"message": " "}, headers=H).status_code == 400


def test_reads_text_projects(client, H, monkeypatch):
    monkeypatch.setattr(T, "extract_chunk", lambda chunk, provider, model, mode: {
        "chapter_summary": "s", "beats": [], "stats": {},
        "entities": [{"name": "Sela", "aliases": [], "type": "character", "age": "", "facts": "A smuggler.", "voice": ["Pay first."],
                      "keywords": ["Sela"], "origin": "", "relations": []}]})
    pid = client.post("/api/text/ingest", json={"name": "Helper Story", "text": "Chapter 1\n\n" + "Sela waits. " * 300}, headers=H).get_json()["id"]
    wait(client, H, client.post(f"/api/text/project/{pid}/extract", json={"mode": "quick", "condense": False}, headers=H).get_json()["job_id"])
    eid = client.get(f"/api/text/project/{pid}", headers=H).get_json()["entities"][0]["id"]
    SCRIPT[:] = [{"say": "", "actions": [{"tool": "get_text_project", "args": {"text_project_id": pid}},
                                         {"tool": "get_text_entity", "args": {"text_entity_id": eid}}]},
                 {"say": "Report: read.", "actions": []}]
    chat(client, H, "Make a card from Sela", context={"studio": "text", "text_project_id": pid, "text_entity_id": eid})
    assert f"The open story is text_project_id {pid} (Helper Story)" in sys_of(0) and f"text_entity_id {eid} (Sela)" in sys_of(0)
    res = user_of()
    assert '"name": "Sela"' in res and "A smuggler." in res and "Pay first." in res


def test_glossary_notes_follow_the_conversation(client, H):
    SCRIPT[:] = ['{"say": "Report: World Info button, then Import World Info.", "actions": []}']
    chat(client, H, "How do I import a lorebook into SillyTavern?")
    s = sys_of()
    assert "GLOSSARY" in s and "press Import World Info" in s and "Temperature" not in s.split("GLOSSARY")[1]
    SCRIPT[:] = ['{"say": "Hi.", "actions": []}']
    chat(client, H, "hello there")
    assert "GLOSSARY" not in sys_of()
    import json as J
    data = J.load(open(HLP.GLOSSARY_FILE, encoding="utf-8"))
    assert len(data["entries"]) >= 30 and all(e["keys"] and e["content"] for e in data["entries"])
