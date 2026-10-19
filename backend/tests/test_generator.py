"""Character generator: prompt options, validation/repair, minor rule, in-depth passes, V3 export, jobs, usage."""

import database as db
import generator as G
import preview as P


def test_fic_source_prompt_says_fic_wins_and_story_point():
    src = {"wiki_base": "text-studio", "normalized": {"title": "Yuna"}}
    sp = G.card_system_prompt(src, {"story_point": "after chapter 2", "user_role": "a recruit", "lore_aware": True,
                                    "token_target": "lean", "style": "plist"})
    assert "FAN FICTION" in sp and "fan fiction is the truth" in sp
    assert "after chapter 2" in sp and "a recruit" in sp and "LOREBOOK" in sp and "LEAN CARD" in sp and "PList" in sp
    wiki = G.card_system_prompt({"wiki_base": "fandom"}, {})
    assert "canon-consistent" in wiki and "FAN FICTION" not in wiki
    assert '"species"' in wiki and '"alternate_greetings"' in wiki and '"character_note"' in wiki


def test_validate_repairs_examples_tags_and_flags_user():
    card = {"name": "Rikku", "description": "d" * 50, "personality": "p", "scenario": "s",
            "first_mes": "{{user}}: hi\nRikku waves.", "mes_example": "{{char}}: one<START>{{char}}: two",
            "tags": ["#Al Bhed", "al bhed", "thief"], "structured_profile": {"ethnicity": "Al Bhed", "age": "16",
            "kinks": ["x"], "personal_parts": ["y"], "sexual_attraction": "z"}}
    out, warn = G.validate_card(card, {})
    assert out["mes_example"].startswith("<START>\n{{char}}: one\n\n<START>\n{{char}}: two")
    assert out["tags"] == ["al bhed", "thief"]
    assert out["structured_profile"]["species"] == "Al Bhed"
    sp = out["structured_profile"]
    assert sp["kinks"] == [] and sp["personal_parts"] == [] and sp["sexual_attraction"] == ""
    joined = " ".join(warn)
    assert "speak or act for {{user}}" in joined and "tags" in joined and "under 18" in joined


def test_adult_profile_keeps_fields():
    out, warn = G.validate_card({"structured_profile": {"age": "19", "kinks": ["x"]}, "tags": []}, {})
    assert out["structured_profile"]["kinks"] == ["x"]


def test_deep_mode_runs_bible_card_check(monkeypatch):
    calls = []

    def fake(provider, model, prompt, system=None, max_tokens=None):
        if system and system.startswith("You build a CHARACTER BIBLE"):
            calls.append("bible")
            return {"name": "Yuna", "age": "19"}
        if system and system.startswith("You check a SillyTavern"):
            calls.append("check")
            return {"fixes": {"scenario": "Fixed scenario.", "structured_profile.age": "19"}, "issues": ["scenario contradicted"]}
        calls.append("card")
        assert "CHARACTER BIBLE" in prompt
        return {"name": "Yuna", "description": "desc", "personality": "p", "scenario": "wrong", "first_mes": "Hi.",
                "mes_example": "<START>\n{{char}}: hi", "tags": ["a"] * 1, "structured_profile": {"age": "12"}}
    monkeypatch.setattr(G, "_request", fake)
    card = G.generate_full_card({"wiki_base": "fandom", "normalized": {"title": "Yuna"}}, "nanogpt", "m", {"deep": True})
    assert calls == ["bible", "card", "check"]
    assert card["scenario"] == "Fixed scenario." and card["structured_profile"]["age"] == "19"
    assert any("scenario contradicted" in w for w in card["_warnings"])


def test_card_note_and_system_prompt_saved_and_exported():
    sid = db.save_source({"wiki_base": "manual", "page_name": "x", "url": "manual://note-test", "title": "X",
                          "raw_html": "", "raw_infobox": {}, "raw_sections": {}, "normalized": {}})
    cid = db.create_or_update_card(sid, {"name": "X", "character_note": "Keeps calm.", "system_prompt": "Be X."})
    card = db.get_card(cid)
    assert card["depth_prompt"] == "Keeps calm." and card["system_prompt"] == "Be X."
    v2 = P.build_export_card_json(card)
    assert v2["data"]["extensions"]["depth_prompt"]["prompt"] == "Keeps calm." and v2["data"]["system_prompt"] == "Be X."
    v3 = P.build_export_card_v3(card)
    assert v3["spec"] == "chara_card_v3" and v3["data"]["name"] == "X" and "assets" in v3["data"]
    db.create_or_update_card(sid, {"name": "X"}, card_id=cid)       # update without the fields keeps them
    assert db.get_card(cid)["depth_prompt"] == "Keeps calm."


def test_structured_export_prints_species_and_ethnicity():
    txt = P.format_structured_profile_text("Rikku", {"species": "Human", "ethnicity": "Al Bhed", "motivations": ["find Brother"]})
    assert 'Species ("Human")' in txt and 'Ethnicity ("Al Bhed")' in txt and 'Motivations ("find Brother")' in txt


def test_retry_after_parsing():
    assert G._parse_retry_after("7") == 7
    assert G._parse_retry_after(None) is None
    assert G._parse_retry_after("garbage") is None


def test_job_persisted_and_interrupted(client, H):
    db.save_job_row({"id": "jx", "status": "running", "message": "half way"})
    assert db.mark_interrupted_jobs() >= 1
    j = client.get("/api/job/jx", headers=H).get_json()
    assert j["status"] == "failed" and "restart" in j["message"].lower()
    r = client.get("/api/job/never-existed", headers=H)
    assert r.status_code == 404 and "restart" in r.get_json()["error"]


def test_usage_recorded_and_summarised():
    db.record_usage("nanogpt", "m1", 100, 20, 1.5)
    db.record_usage("nanogpt", "m1", 50, 10, 0.5)
    rows = [r for r in db.usage_summary(30) if r["model"] == "m1"]
    assert rows and rows[0]["calls"] == 2 and rows[0]["prompt_tokens"] == 150
