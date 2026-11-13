"""Every API route answers bad input with a readable JSON error (never an HTML page, never a crash), a missing row is a
404, and saving settings with a partial body changes only what was sent."""
import json
import re

import app as A

SKIP = {"/api/st/test"}                    # tries the network on purpose; covered by the SillyTavern tests


def test_no_route_crashes_or_returns_html(client, H, monkeypatch, tmp_path):
    (tmp_path / "config").mkdir()
    for f in ("prompts.json", "settings.json"):
        (tmp_path / "config" / f).write_text((A.BASE_DIR / "config" / f).read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(A, "BASE_DIR", tmp_path)              # the probes must not touch the real config
    monkeypatch.setattr(A, "ENV_PATH", tmp_path / ".env")
    import admin_routes
    monkeypatch.setattr(admin_routes, "SETTINGS_PATH", tmp_path / "config" / "settings.json")
    bad = []
    for rule in A.app.url_map.iter_rules():
        if rule.endpoint == "static" or rule.rule in SKIP or not rule.rule.startswith("/api/"):
            continue
        url = re.sub(r"<[^>]+>", "999999", rule.rule)
        for m in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            for body in ([None] if m == "GET" else [None, {}, [], "not json"]):
                kw = {"headers": H}
                if body == "not json":
                    kw.update(data="{nope", content_type="application/json")
                elif body is not None:
                    kw["json"] = body
                r = getattr(client, m.lower())(url, **kw)
                if r.status_code >= 500 or "html" in r.headers.get("Content-Type", ""):
                    bad.append(f"{m} {rule.rule} body={body!r} -> {r.status_code} {r.get_data(as_text=True)[:80]}")
    assert not bad, "\n".join(bad[:20])


def test_missing_rows_are_404(client, H):
    assert client.get("/api/lore/entry/999999", headers=H).status_code == 404
    assert client.post("/api/card/999999/duplicate", headers=H, json={}).status_code == 404


def test_saving_settings_keeps_what_was_not_sent(client, H, monkeypatch, tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "prompts.json").write_text(json.dumps({
        "character_generation_template": "CHAR {source_json}", "field_regeneration_template": "FIELD",
        "lore_generation_template": "LORE"}), encoding="utf-8")
    (tmp_path / "config" / "settings.json").write_text(json.dumps({"use_templates": True, "temperature": 0.7,
                                                                    "max_tokens": 4096, "model_presets": {"x": 1}}))
    monkeypatch.setattr(A, "BASE_DIR", tmp_path)
    read = lambda f: json.loads((tmp_path / "config" / f).read_text(encoding="utf-8"))
    assert client.post("/api/config/prompts", headers=H, json={}).status_code == 200
    assert read("prompts.json")["character_generation_template"] == "CHAR {source_json}"
    assert read("settings.json") == {"use_templates": True, "temperature": 0.7, "max_tokens": 4096, "model_presets": {"x": 1}}
    client.post("/api/config/prompts", headers=H, json={"lore_generation_template": "NEW LORE", "temperature": 0.4})
    p, st = read("prompts.json"), read("settings.json")
    assert p["lore_generation_template"] == "NEW LORE" and p["field_regeneration_template"] == "FIELD"
    assert st["temperature"] == 0.4 and st["use_templates"] is True and st["model_presets"] == {"x": 1}
    r = client.post("/api/config/prompts", headers=H, json={"temperature": "warm"})
    assert r.status_code == 400 and "numbers" in r.get_json()["error"]


def test_presets_keep_tasks_not_sent(client, H, monkeypatch, tmp_path):
    import admin_routes
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"model_presets": {"critic": {"provider": "local", "model": "m1"}}}))
    monkeypatch.setattr(admin_routes, "SETTINGS_PATH", path)
    client.post("/api/config/presets", headers=H, json={"card": {"provider": "openrouter", "model": "m2"}})
    pr = json.loads(path.read_text())["model_presets"]
    assert pr["critic"] == {"provider": "local", "model": "m1"} and pr["card"] == {"provider": "openrouter", "model": "m2"}
    assert client.post("/api/config/presets", headers=H, json={"card": "nonsense"}).status_code == 400


def test_card_and_entry_saves_keep_their_shapes(client, H):
    import database as D
    sid = D.save_source({"wiki_base": "manual", "page_name": "rb", "url": "manual://rb/1", "title": "T", "raw_html": "",
                         "raw_infobox": {}, "raw_sections": {}, "normalized": {}})
    cid = D.create_or_update_card(sid, {"name": "Mara", "description": "d", "tags": ["x"], "structured_profile": {},
                                        "alternate_greetings": [], "provider": "local", "model": "m"}, force_new=True)
    card = D.get_card(cid)
    client.post(f"/api/save-card/{cid}", headers=H, json={**card, "tags": "a, b", "alternate_greetings": "Hello there, you.",
                                                          "structured_profile": {"likes": "tea, rain"}})
    c = D.get_card(cid)
    assert c["tags"] == ["a", "b"] and c["alternate_greetings"] == ["Hello there, you."] and c["structured_profile"]["likes"] == ["tea", "rain"]
    assert client.post(f"/api/save-card/{cid}", headers=H, data="nope", content_type="application/json").status_code == 400
    r = client.post("/api/export/v2", headers=H, json={"card": card, "lore_project_id": "abc"})
    assert r.status_code == 400
    # a lore entry PATCH changes only what was sent
    pid = D.create_lore_project("RB")
    lid = client.post("/api/lore/entry/new", headers=H, json={"project_id": pid, "title": "Old Harbor"}).get_json()["id"]
    client.patch(f"/api/lore/entry/{lid}", headers=H, json={"content": "Docks.", "keywords": ["harbor"]})
    client.patch(f"/api/lore/entry/{lid}", headers=H, json={"keywords": "harbor, docks"})
    e = D.get_lore_entry(lid)
    assert e["title"] == "Old Harbor" and e["content"] == "Docks." and e["keywords"] == ["harbor", "docks"]
    assert client.patch(f"/api/lore/entry/{lid}", headers=H, json={"scan_depth": "deep"}).status_code == 400
    assert client.post("/api/lore/entry/new", headers=H, json={"project_id": 999999}).status_code == 404


def test_helper_refuses_overlong_messages(client, H):
    r = client.post("/api/helper/chat", headers=H, json={"message": "x" * 7000})
    assert r.status_code == 400 and "limit is 6,000" in r.get_json()["error"]
