"""Every feature that calls a model, run through the REAL request code (generator._request) against a small
OpenAI-compatible server that answers the way real models often do instead of the way the prompt asks:
plain prose instead of JSON, JSON in code fences or after a sentence, a string where a list was asked for, a list
where text was asked for, scores as "7/10", a list of objects without the wrapper, other key names.

Each test checks that what reaches the user is clean: text is text, lists are lists of whole words (never letter
by letter, never "['a', 'b']"), and failures come back as readable JSON errors."""
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import assist_tools as A
import critic_tools as C
import generator
import text_module as T
from test_text_flow import wait

REAL_EXTRACT = T.extract_chunk          # other test files swap in fakes while they run; keep the real one
ROUTES = []                             # [(substring of the system prompt, reply or callable(body) -> reply)]
SEEN = []
LOCK = threading.Lock()


def answer(body):
    system = next((m["content"] for m in body["messages"] if m["role"] == "system"), "")
    user = next((m["content"] for m in body["messages"] if m["role"] == "user"), "")
    for key, reply in ROUTES:
        if key in system or key in user:
            return reply(body) if callable(reply) else reply
    return '{"note": "no route"}'


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with LOCK:
            SEEN.append(body)
        reply = answer(body)
        status, content = reply if isinstance(reply, tuple) else (200, reply)
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
    for mod in (A, T, generator):
        monkeypatch.setattr(mod, "_request", generator._request)
    import app as APP                                   # other test files leave fakes on these too
    for name in ("generate_full_card", "regenerate_single_field", "generate_lore_entry"):
        monkeypatch.setattr(APP, name, getattr(generator, name))
    monkeypatch.setattr(APP, "_gen_request", generator._request)
    monkeypatch.setattr(T, "extract_chunk", REAL_EXTRACT)
    monkeypatch.setenv("LOCAL_OPENAI_BASE_URL", server)
    monkeypatch.setattr(generator, "_RETRY_BACKOFF_SECONDS", [0, 0])
    ROUTES.clear(); SEEN.clear()


def no_letters(lst):
    """True when a list holds whole items, not the letters of one string."""
    return isinstance(lst, list) and not (len(lst) > 2 and all(len(x) == 1 for x in lst))


def no_python_repr(s):
    return isinstance(s, str) and "['" not in s and "{'" not in s


LOCAL = {"provider": "local", "model": "m"}


# ── the helpers themselves ───────────────────────────────────────────────────
def test_helpers():
    assert generator.list_of("Mar, Mara") == ["Mar", "Mara"] and generator.list_of("one line, with a comma", split=False) == ["one line, with a comma"]
    assert generator.list_of(["a", "", {"name": "B"}]) == ["a", "B"] and generator.list_of('["x", "y"]') == ["x", "y"]
    assert generator.list_of(None) == [] and generator.list_of(True) == []
    assert generator.text_of(["a", "b"]) == "a b" and generator.text_of({"k": ["x", "y"]}) == "k: x, y" and generator.text_of(None) == ""
    assert generator.number_of("7/10") == 7 and generator.number_of("8.5 out of 10") == 8.5 and generator.number_of("n/a") is None
    with pytest.raises(generator.NotJSONError) as e:
        generator._extract_json_object("Just prose, no JSON at all. " * 80)
    assert len(e.value.raw) > 1200                                    # the whole answer is kept, not 1200 chars
    assert generator._extract_json_object('[{"title": "A"}]')["entries"] == [{"title": "A"}]
    with pytest.raises(generator.NotJSONError):
        generator._extract_json_object('"a bare string"')


# ── CHARACTER studio ─────────────────────────────────────────────────────────
def _source():
    from database import save_source
    return save_source({"wiki_base": "manual", "page_name": f"shape{time.time()}", "url": f"manual://shape/{time.time()}",
                        "title": "Mara", "raw_html": "", "raw_infobox": {},
                        "raw_sections": {"Bio": ["Mara is a courier."]}, "normalized": {"title": "Mara", "summary": "Courier."}})


def test_card_generation_with_wrong_types(client, H):
    ROUTES.append(("", "Here is the card you asked for:\n```json\n" + json.dumps({
        "name": "Mara", "description": ["Mara is a courier.", "She is never late."], "personality": {"core": "dry", "flaw": "proud"},
        "scenario": "A rainy port.", "first_mes": "*Mara shakes off the rain.* \"You're late.\"",
        "mes_example": "<START>\n{{char}}: Keep up.", "tags": "courier, rain, port",
        "alternate_greetings": "\"Again?\" she sighs.",
        "structured_profile": json.dumps({"likes": "tea, rain", "with_close": ["teasing", "warm"], "age": 24}),
    }) + "\n```\nLet me know if you want changes!"))
    r = client.post("/api/generate-card", json={"source_id": _source(), **LOCAL}, headers=H)
    assert r.status_code == 200, r.get_json()
    card = r.get_json()["card"]
    assert card["description"] == "Mara is a courier.\nShe is never late."
    assert card["personality"] == "core: dry; flaw: proud" and no_python_repr(card["personality"])
    assert card["tags"] == ["courier", "rain", "port"]
    assert card["alternate_greetings"] == ['"Again?" she sighs.']
    sp = card["structured_profile"]
    assert sp["likes"] == ["tea", "rain"] and sp["with_close"] == "teasing, warm" and sp["age"] == "24"


def test_card_generation_plain_prose_is_a_readable_error(client, H):
    ROUTES.append(("", "Mara is a courier who hates being late."))
    r = client.post("/api/generate-card", json={"source_id": _source(), **LOCAL}, headers=H)
    assert r.status_code == 500 and "could not be parsed as JSON" in r.get_json()["error"]


@pytest.fixture
def card_id(client, H):
    from database import create_or_update_card
    return create_or_update_card(_source(), {"name": "Mara", "description": "Old.", "personality": "Dry.", "scenario": "Port.",
                                             "first_mes": "Hi.", "mes_example": "", "tags": ["a"], "provider": "local", "model": "m",
                                             "structured_profile": {"likes": ["tea"], "with_close": ""},
                                             "alternate_greetings": []}, force_new=True)


def regen(client, H, cid, field):
    return client.post(f"/api/generate/field/{cid}", data={"field_name": field, "custom_prompt": ""}, headers=H,
                       content_type="application/x-www-form-urlencoded")


def test_field_regenerate_shapes(client, H, card_id):
    ROUTES[:] = [("", "Mara is a courier who knows every alley.")]                 # plain prose for a text field
    d = regen(client, H, card_id, "description").get_json()
    assert d["new_value"] == "Mara is a courier who knows every alley."
    ROUTES[:] = [("", '{"likes": "tea, rain, quiet docks"}')]                      # sub-field at the top level, as a string
    regen(client, H, card_id, "likes")
    from database import get_card
    assert get_card(card_id)["structured_profile"]["likes"] == ["tea", "rain", "quiet docks"]
    ROUTES[:] = [("", '{"structured_profile": {"with_close": ["teasing", "blunt"]}}')]
    regen(client, H, card_id, "with_close")
    assert get_card(card_id)["structured_profile"]["with_close"] == "teasing, blunt"
    ROUTES[:] = [("", '{"tags": "courier; rain; port"}')]
    assert regen(client, H, card_id, "tags").get_json()["new_value"] == ["courier", "rain", "port"]
    ROUTES[:] = [("", '{"likes": "", "note": "nothing"}')]                          # nothing usable: readable error
    r = regen(client, H, card_id, "likes")
    assert r.status_code == 502 and "returned nothing for likes" in r.get_json()["error"]


def test_alternate_greeting_and_compile(client, H, card_id):
    ROUTES[:] = [("", '*Mara looks up.* "You again."')]
    r = client.post(f"/api/generate/greeting/{card_id}", json={}, headers=H).get_json()
    assert r["greeting"] == '*Mara looks up.* "You again."'
    ROUTES[:] = [("", '"Rain again," she mutters.')]                              # bare JSON-ish string
    assert client.post(f"/api/generate/greeting/{card_id}", json={}, headers=H).get_json()["greeting"] == '"Rain again," she mutters.'
    ROUTES[:] = [("", '{"response": "*She nods.*"}')]                              # another key name
    assert client.post(f"/api/generate/greeting/{card_id}", json={}, headers=H).get_json()["greeting"] == "*She nods.*"
    ROUTES[:] = [("", "Mara is a courier in a rainy port, dry and quick.")]
    r = client.post(f"/api/generate/compile/{card_id}", json={"target": "personality"}, headers=H).get_json()
    assert r["value"] == "Mara is a courier in a rainy port, dry and quick."
    ROUTES[:] = [("", '{"greeting": ""}')]
    assert client.post(f"/api/generate/greeting/{card_id}", json={}, headers=H).status_code == 502


def test_cast_card(client, H, card_id):
    from database import create_or_update_card, get_card
    other = create_or_update_card(get_card(card_id)["source_id"], {**get_card(card_id), "name": "Tomas"}, force_new=True)
    ROUTES[:] = [("", json.dumps({"name": "Port Crew", "description": ["Mara runs.", "Tomas fixes."], "personality": "Loud.",
                                  "scenario": "Docks.", "first_mes": "Mara: Hi.\nTomas: Yo.", "mes_example": "", "tags": "crew, port"}))]
    r = client.post("/api/generate/cast", json={"card_ids": [card_id, other], "cast_name": "Port Crew", **LOCAL}, headers=H).get_json()
    assert r["card"]["description"] == "Mara runs.\nTomas fixes." and r["card"]["tags"] == ["crew", "port"]


def test_lore_entry_generation_shapes():
    src = {"url": "manual://x", "title": "Old Harbor", "raw_sections": {"A": ["Docks."]}, "normalized": {"title": "Old Harbor"}}
    ROUTES[:] = [("", '[{"title": "Old Harbor", "entry_type": "place", "keywords": "harbor, docks", "summary": "Docks.", "content": ["Busy.", "Wet."]}]')]
    r = generator.generate_lore_entry(src, "local", "m")
    assert r["valid"] and r["entries"][0]["keywords"] == ["harbor", "docks"] and r["entries"][0]["content"] == "Busy.\nWet."
    ROUTES[:] = [("", '{"valid": "true", "entries": {"title": "Old Harbor", "keywords": ["harbor"], "content": "Busy."}}')]
    assert generator.generate_lore_entry(src, "local", "m")["entries"][0]["title"] == "Old Harbor"
    ROUTES[:] = [("", '{"valid": false, "reason": ["Not a lore page"]}')]
    r = generator.generate_lore_entry(src, "local", "m")
    assert r == {"valid": False, "reason": "Not a lore page", "entries": []}


# ── TEXT studio ──────────────────────────────────────────────────────────────
MESSY_EXTRACT = json.dumps({
    "chapter_summary": ["Mara meets Tomas.", "They argue."],
    "entities": [
        {"name": "Mara", "aliases": "Mar, Mara V", "type": "Character", "age": 24, "facts": ["Courier.", "Hates being late."],
         "voice": "Keep up, will you?", "keywords": "Mara", "origin": "Canon",
         "relations": {"Tomas": "friend", "Sela": ["sister", "rival"]}},
        {"name": "Tomas", "aliases": [], "type": "character", "facts": "Mechanic.",
         "relations": ["Mara - friend", "Jean-Luc — boss"]},
        {"name": "Old Harbor", "type": "location", "facts": "Docks.", "keywords": ["harbor", "docks"]},
    ]})


@pytest.fixture
def text_project(client, H):
    text = "\n\n".join(f"Chapter {n}\n\n" + " ".join(f"Mara and Tomas talk at the harbor, day {n} hour {k}." for k in range(120)) for n in range(1, 4))
    pid = client.post("/api/text/ingest", json={"name": "Shapes Fic", "text": text, "chunk_chars": 3000}, headers=H).get_json()["id"]
    assert len(json.loads(T._project_row(pid)["chunks_json"])) >= 2
    return pid


def test_quick_extraction_with_messy_output(client, H, text_project):
    ROUTES[:] = [("You extract world-building data", "Sure! Here's the data:\n" + MESSY_EXTRACT)]
    wait(client, H, client.post(f"/api/text/project/{text_project}/extract", json={**LOCAL, "mode": "quick", "condense": False},
                                headers=H).get_json()["job_id"])
    E = {e["name"]: e for e in client.get(f"/api/text/project/{text_project}", headers=H).get_json()["entities"]}
    m = E["Mara"]
    assert set(m["aliases"]) >= {"Mar", "Mara V"} and no_letters(m["aliases"])
    assert m["voice"] == ["Keep up, will you?"] and m["age"] == "24" and m["origin"] == "canon"
    assert "Courier." in m["content"] and "Hates being late." in m["content"] and no_python_repr(m["content"])
    rel = {r["with"]: r["relation"] for r in m["relations"]}
    assert rel["Tomas"] == "friend" and set(re.split(r"[;,]\s*", rel["Sela"])) == {"sister", "rival"}
    assert {r["with"] for r in E["Tomas"]["relations"]} == {"Mara", "Jean-Luc"}
    assert E["Old Harbor"]["entity_type"] == "place"
    T._project_row(text_project)
    rs = T.chunk_results(text_project)
    assert all(no_python_repr(x.get("chapter_summary", "")) for x in rs.values())


def test_deep_extraction_with_messy_output(client, H, text_project):
    ROUTES[:] = [
        ("Add each one that is a real entity", '{"entities": [], "beats": []}'),
        ("You inventory a story", lambda b: '{"entities": [{"name": "Mara", "type": "character", "aliases": "Mar"}, "Tomas"], "beats": "The argument"}'
         if "ENTITIES FOUND" not in b["messages"][1]["content"] else '{"entities": [], "beats": []}'),
        ("You write lorebook notes", '{"entities": [{"name": "Mara Vell", "facts": ["Courier."], "voice": "Keep up.", "keywords": "Mara, Mar",'
                                     ' "relations": [{"name": "Tomas", "relationship": "friend"}]}, {"name": "Tomas", "facts": "Mechanic."}]}'),
        ("You turn a list of beats", '{"chapter_summary": "They argue.", "beats": {"title": "The argument", "participants": "Mara, Tomas",'
                                     ' "place": "Old Harbor", "what_happened": ["Mara yells.", "Tomas leaves."], "confidence": "High"}}'),
    ]
    out = T.extract_chunk_deep({"label": "Chapter 1", "text": "Mara and Tomas argue at the harbor. " * 30}, "local", "m", glean_rounds=1)
    E = {e["name"]: e for e in out["entities"]}
    assert E["Mara"]["facts"] == "Courier."                         # "Mara Vell" matched to "Mara"
    assert E["Mara"]["voice"] == ["Keep up."] and E["Mara"]["relations"] == [{"with": "Tomas", "relation": "friend"}]
    assert E["Tomas"]["facts"] == "Mechanic." and E["Mara"]["aliases"] == ["Mar"]
    [b] = out["beats"]
    assert b["participants"] == ["Mara", "Tomas"] and b["what_happened"] == "Mara yells. Tomas leaves." and b["confidence"] == "high"


def test_recap_and_narrator(client, H, text_project):
    ROUTES[:] = [("You extract world-building data", MESSY_EXTRACT)]
    wait(client, H, client.post(f"/api/text/project/{text_project}/extract", json={**LOCAL, "mode": "quick", "condense": False},
                                headers=H).get_json()["job_id"])
    ROUTES[:] = [("Narrative Archivist", json.dumps({"current_timeline": ["Day 2", "evening"], "current_location": "Old Harbor",
                                                    "chapters": {"title": "Arrival", "summary": "Mara arrives."},
                                                    "characters": [{"name": "Mara", "location": "Docks", "goal": ["deliver", "rest"]}],
                                                    "plot_hooks": "Who sent the parcel?"}))]
    r = client.post(f"/api/text/project/{text_project}/recap/ai", json=LOCAL, headers=H).get_json()
    t = r["text"]
    assert "Current Timeline: Day 2 evening" in t and "## CHAPTER 1 - Arrival\nMara arrives." in t
    assert "* Mara: Docks; deliver rest" in t and "* Plot Hooks: Who sent the parcel?" in t and no_python_repr(t)
    ROUTES[:] = [("NARRATOR / game master", json.dumps({"name": "Port Narrator", "description": ["You narrate.", "Keep it tense."],
                                                       "personality": "Calm.", "scenario": "The port.", "first_mes": "Rain falls.",
                                                       "system_prompt": "Narrate.", "tags": "narrator, port"}))]
    r = client.post(f"/api/text/project/{text_project}/narrator", json=LOCAL, headers=H)
    assert r.status_code == 200, r.get_json()
    from database import get_card
    card = get_card(r.get_json()["card_id"])
    assert card["description"].startswith("You narrate.") and card["tags"][:2] == ["narrator", "port"]


def test_critic_sweep_and_rewrite(client, H, text_project):
    ROUTES[:] = [
        ("reading ONE part", "This part is fine but the dialogue drags."),                  # prose notes
        ("fiction critic and editor", json.dumps({"verdict": ["Solid start.", "Dialogue drags."],
                                                  "scores": {"Pacing": "6/10", "Dialogue": {"score": "5 out of 10", "why": "Drags."}},
                                                  "strengths": "Clear setting", "top3": "Cut filler",
                                                  "problems": {"title": "Slow middle", "fix": "Cut."}})),
    ]
    j = client.post(f"/api/text/project/{text_project}/critique", json=LOCAL, headers=H).get_json()["job_id"]
    wait(client, H, j)
    [crit] = client.get(f"/api/text/project/{text_project}/critiques", headers=H).get_json()[:1]
    assert crit["scores"] == {"Pacing": 6, "Dialogue": 5}
    full = json.loads(T._conn().execute("SELECT result_json FROM text_critiques WHERE id=?", (crit["id"],)).fetchone()[0])
    assert full["verdict"] == "Solid start.\nDialogue drags." and full["strengths"] == ["Clear setting"] and full["top3"] == ["Cut filler"]
    assert full["problems"][0]["title"] == "Slow middle" and "- **Dialogue**: 5" in full["markdown"]
    notes_prompt = [b for b in SEEN if "fiction critic and editor" in b["messages"][0]["content"]][-1]["messages"][1]["content"]
    assert "This part is fine but the dialogue drags." in notes_prompt                     # prose notes were used
    ROUTES[:] = [("scoring ONE part", '{"score": "7/10", "scores": [{"category": "Pacing", "score": "8"}], "summary": ["Talk."], "worst": "Drags"}')]
    wait(client, H, client.post(f"/api/text/project/{text_project}/critique/sweep", json=LOCAL, headers=H).get_json()["job_id"])
    sweep = json.loads(T._conn().execute("SELECT result_json FROM text_critiques WHERE project_id=? ORDER BY id DESC LIMIT 1",
                                         (text_project,)).fetchone()[0])
    assert all(x["score"] == 7 and x["scores"] == {"Pacing": 8} and x["summary"] == "Talk." for x in sweep["sweep"])
    ROUTES[:] = [("line editor", "Mara and Tomas argued at the harbor, voices low.")]
    r = client.post(f"/api/text/project/{text_project}/rewrite", json={"quote": "Mara and Tomas talk at the harbor, day 2 hour 5.", **LOCAL}, headers=H).get_json()
    assert r["found"] and r["rewrite"] == "Mara and Tomas argued at the harbor, voices low."


def test_condense_and_arcs():
    ROUTES[:] = [("You consolidate notes", "Mara is a courier who hates being late and trusts Tomas.")]   # prose
    m = {"name": "Mara", "type": "character", "fragments": [(i, "Mara does something important in this chapter. " * 12) for i in range(3)]}
    assert T.build_content(m, {}, "local", "m", True) == "Mara is a courier who hates being late and trusts Tomas."
    ROUTES[:] = [("You condense several consecutive", '{"title": ["Arrival"], "summary": ["Mara arrives.", "Rain."]}')]
    parts = [f"[Part {i}] thing {i}" for i in range(40)]
    lines, n = T.tier_parts(parts, "local", "m")
    assert n >= 1 and lines[0] == "[ARC 1: Arrival] Mara arrives. Rain."
