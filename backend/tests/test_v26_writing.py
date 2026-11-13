"""2.6 writing checks: the new prose-scan patterns, the longer stock-phrase list, the clean-up of generated text,
and the first-message point of view / tense / length option, sent through the real request code."""
import json

import generator as G
import prose_scan as P
from test_text_flow import wait
from test_model_output_shapes import LOCAL, ROUTES, SEEN, _source, real_model, server  # noqa: F401  (fixtures)


def _system(body):
    return next((m["content"] for m in body["messages"] if m["role"] == "system"), "")


def _user(body):
    return next((m["content"] for m in body["messages"] if m["role"] == "user"), "")


# ── prose scan patterns ──────────────────────────────────────────────────────
SAMPLE = '''She doesn't move. It wasn't anger. It was something colder.

"Are you new here?" he asked.

"New?"

This isn't a request — it's an order. He didn't answer. Not fear, but resignation.

"I don't move," she said.'''


def test_patterns_find_each_habit():
    p = P.patterns(SAMPLE)
    assert p["not_but"]["count"] == 3                                  # wasn't X. It was Y / isn't X — it's Y / not X, but Y
    assert p["negations"]["count"] == 2                                # doesn't move, didn't answer; the dialogue line is skipped
    assert p["echoes"]["count"] == 1 and "New?" in p["echoes"]["examples"][0]["excerpt"]
    assert p["dashes"]["count"] == 1


def test_patterns_leave_plain_prose_alone():
    clean = ('Mara shakes the rain off her coat and sets the parcel on the counter. "Sign here," she says, and taps '
             'the ledger twice.\n\nThe clerk signs. Outside, a cart rattles past the window.')
    p = P.patterns(clean)
    assert (p["not_but"]["count"], p["negations"]["count"], p["echoes"]["count"], p["dashes"]["count"]) == (0, 0, 0, 0)
    assert p["para_starts"] == []


def test_paragraph_starts_and_scan_report():
    text = "\n\n".join(["She walked in.", "She sat down.", "She waited.", "The door opened.", "She stood up."])
    r = P.scan(text)
    assert r["patterns"]["para_starts"][0]["word"] == "she" and r["patterns"]["para_starts"][0]["count"] == 4
    per = P.scan_chunks([{"idx": 0, "label": "Ch 1", "text": SAMPLE}, {"idx": 1, "label": "Ch 2", "text": "Plain text here."}])
    assert per["patterns"]["not_but"]["count"] == 3 and per["per_chunk"][0]["echoes"] == 1 and per["per_chunk"][1]["not_but"] == 0
    assert per["patterns"]["not_but"]["examples"][0]["label"] == "Ch 1"


def test_new_stock_phrases_and_card_warnings():
    cl = P.load_cliches()
    r = P.scan("The smell of ozone filled the room. After a beat, her breath hitched.", cliches=cl)
    found = {c["phrase"] for c in r["cliches"]}
    assert {"smell* of ozone", "after a beat", "breath hitched"} <= found
    w = P.card_text_warnings({"first_mes": SAMPLE, "description": "As an AI language model, I can't help with that."}, limit=20)
    assert w[0].startswith("Description: looks like the model refused")
    assert any("not X, but Y" in x for x in w) and any("doesn't happen" in x for x in w) and any("repeats" in x for x in w)


def test_shipped_phrase_file_has_the_new_lines():
    from pathlib import Path
    lines = Path(P.CLICHE_FILE).read_text(encoding="utf-8").lower().splitlines()
    assert "smell* of ozone" in lines and "breath hitched" in lines and len(lines) == len(set(lines))


# ── clean-up of generated text ───────────────────────────────────────────────
def test_tidy_text():
    t = G.tidy_text
    assert t('Mara: “Hi…”  she said.<br>Next<p></p>\n\n\n\nEnd   ', "Mara") == '"Hi..." she said.\nNext\n\nEnd'
    assert t("{{char}}: Hello.", "Mara") == "Hello." and t("Mara: Hello.") == "Mara: Hello."     # name only stripped when given
    assert t("```\nText\n```") == "Text"
    assert t("<personality>kind</personality>") == "<personality>kind</personality>"         # XML-style sections stay
    assert t("「こんにちは」“你好…”") == "「こんにちは」“你好…”"                                      # CJK keeps its quotes
    assert t("    indented line") == "indented line" and t("a\n    b") == "a\n    b"             # inner indentation stays


def test_generated_card_is_tidied(client, H):
    ROUTES.append(("", json.dumps({
        "name": "Mara", "description": "Mara is a courier.  She is <span>never</span> late.",
        "personality": "Dry.", "scenario": "A rainy port.", "first_mes": "Mara: “You’re late…”",
        "mes_example": "<START>\n{{char}}: Keep up.", "tags": ["courier"],
        "alternate_greetings": ["{{char}}: “Again?”"], "structured_profile": {}})))
    r = client.post("/api/generate-card", json={"source_id": _source(), **LOCAL}, headers=H)
    card = r.get_json()["card"]
    assert card["description"] == "Mara is a courier. She is never late."
    assert card["first_mes"] == '"You\'re late..."' and card["alternate_greetings"] == ['"Again?"']


# ── first message point of view / tense / length ─────────────────────────────
STYLE = {"pov": "second", "tense": "present", "length": "short"}


def test_greeting_style_rule():
    rule = G.greeting_style(STYLE)
    assert "second person" in rule and "present tense" in rule and "50-100 words" in rule
    assert G.greeting_style(json.dumps({"pov": "first"})).startswith("Write it in first person")
    assert G.greeting_style({}) == "" and G.greeting_style("nonsense") == "" and G.greeting_style({"pov": "sideways"}) == ""


def test_card_generation_sends_the_style(client, H):
    ROUTES.append(("", json.dumps({"name": "Mara", "description": "A courier.", "personality": "Dry.", "scenario": "Port.",
                                   "first_mes": "You step in out of the rain.", "mes_example": "", "tags": []})))
    wait(client, H, client.post("/api/generate/start", json={"source_id": _source(), "greeting_style": STYLE, **LOCAL},
                                headers=H).get_json()["job_id"])                # the route the studio uses
    assert "FIRST MESSAGE AND GREETINGS" in _system(SEEN[-1]) and "second person" in _system(SEEN[-1])
    ROUTES.append(("", json.dumps({"name": "Mara", "description": "A courier.", "personality": "Dry.", "scenario": "Port.",
                                   "first_mes": "Hi.", "mes_example": "", "tags": []})))
    wait(client, H, client.post("/api/generate/start", json={"source_id": _source(), **LOCAL}, headers=H).get_json()["job_id"])
    assert "FIRST MESSAGE AND GREETINGS" not in _system(SEEN[-1])                    # no option, no rule


def test_field_and_greeting_regenerate_send_the_style(client, H):
    from database import create_or_update_card
    cid = create_or_update_card(_source(), {"name": "Mara", "description": "A courier.", "personality": "Dry.", "scenario": "Port.",
                                            "first_mes": "Hi.", "mes_example": "", "tags": [], "provider": "local", "model": "m",
                                            "structured_profile": {}, "alternate_greetings": []}, force_new=True)
    ROUTES[:] = [("", "Mara: You step in out of the rain.")]
    r = client.post(f"/api/generate/field/{cid}", data={"field_name": "first_mes", "custom_prompt": "",
                                                       "greeting_style": json.dumps(STYLE)},
                    headers=H, content_type="application/x-www-form-urlencoded")
    assert r.get_json()["new_value"] == "You step in out of the rain."              # 'Mara:' taken off
    assert "second person" in _user(SEEN[-1])
    ROUTES[:] = [("", '{"greeting": "You find her at the docks."}')]
    client.post(f"/api/generate/greeting/{cid}", json={"greeting_style": {"pov": "first", "length": "long"}}, headers=H)
    assert "first person" in _user(SEEN[-1]) and "300-450 words" in _user(SEEN[-1])
    client.post(f"/api/generate/greeting/{cid}", json={}, headers=H)
    assert "Match the point of view" in _user(SEEN[-1])
