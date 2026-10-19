"""LORE and CHARACTER studio fixes: entry type saved, clear keeps the project, keyword cleanup, generate never overwrites."""
import time

import app as app_module
import database as db


def test_lore_entry_type_is_saved(client, H):
    pid = db.create_lore_project("Types")
    eid = db.save_lore_entry(pid, None, "Spira", "concept", ["Spira"], "s", "The world.")
    client.patch(f"/api/lore/entry/{eid}", json={"title": "Spira", "entry_type": "place", "keywords": ["Spira"],
                                                "content": "The world.", "summary": "s"}, headers=H)
    assert client.get(f"/api/lore/entry/{eid}", headers=H).get_json()["entry_type"] == "place"


def test_clear_entries_keeps_project_id(client, H):
    pid = db.create_lore_project("Keep me")
    db.save_lore_entry(pid, None, "A", "concept", ["A"], "s", "c")
    r = client.delete(f"/api/lore/project/{pid}/entries", headers=H).get_json()
    assert r["deleted"] == 1
    assert any(p["id"] == pid for p in db.list_lore_projects())
    assert db.list_lore_entries(crawl_id=pid) == []


def test_clean_keywords_preview_then_apply(client, H):
    pid = db.create_lore_project("Clean")
    db.save_lore_entry(pid, None, "Paine", "character", ["Paine"], "s", "Warrior.")
    mid = db.save_lore_entry(pid, None, "Mascot dress sphere", "item", ["Mascot dress sphere", "spell", "Paine", "mascot"], "s", "A sphere.")
    prev = client.post(f"/api/lore/project/{pid}/clean-keywords", json={}, headers=H).get_json()
    assert prev["changed"] == 1 and not prev["applied"]
    client.post(f"/api/lore/project/{pid}/clean-keywords", json={"apply": True}, headers=H)
    kw = client.get(f"/api/lore/entry/{mid}", headers=H).get_json()["keywords"]
    if isinstance(kw, str):
        import json
        kw = json.loads(kw)
    assert kw == ["Mascot dress sphere", "mascot"]


def test_lore_list_has_content_size(client, H):
    pid = db.create_lore_project("Sizes")
    db.save_lore_entry(pid, None, "Big", "concept", ["Big"], "s", "x" * 400)
    rows = client.get(f"/api/lore/entries?project_id={pid}", headers=H).get_json()
    assert rows[0]["content_chars"] == 400


def test_generate_as_new_keeps_the_existing_card(client, H):
    app_module.generate_full_card = lambda source, provider, model, options=None: {
        "name": "Rikku", "description": "d", "personality": "", "scenario": "", "first_mes": "hi", "mes_example": "",
        "tags": [], "structured_profile": {}, "alternate_greetings": []}
    sid = db.save_source({"wiki_base": "manual", "page_name": "rikku", "url": "manual://rikku-test", "title": "Rikku",
                          "raw_html": "", "raw_infobox": {}, "raw_sections": {}, "normalized": {"title": "Rikku"}})

    def gen(as_new):
        job = client.post("/api/generate/start", json={"source_id": sid, "as_new": as_new}, headers=H).get_json()["job_id"]
        for _ in range(100):
            j = client.get(f"/api/job/{job}", headers=H).get_json()
            if j.get("status") in ("done", "failed"):
                assert j["status"] == "done", j
                return j["result"]["card_id"]
            time.sleep(0.05)
    first = gen(False)
    second = gen(True)
    assert first != second
    third = gen(False)            # the old behaviour still updates the latest card when asked to
    assert third == second


def test_env_keys_are_masked_and_mask_never_overwrites(client, H, monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("NANOGPT_API_KEY=sk-secret-123456789\nNANOGPT_MODEL=m1\n", encoding="utf-8")
    monkeypatch.setattr(app_module, "ENV_PATH", env)
    monkeypatch.setenv("NANOGPT_API_KEY", "sk-secret-123456789")
    monkeypatch.setenv("NANOGPT_MODEL", "m1")
    got = client.get("/api/config/env", headers=H).get_json()
    assert got["NANOGPT_API_KEY"].endswith("6789") and "secret" not in got["NANOGPT_API_KEY"]
    assert got["NANOGPT_MODEL"] == "m1"
    r = client.post("/api/config/env", json={"NANOGPT_API_KEY": got["NANOGPT_API_KEY"], "NANOGPT_MODEL": "m2"},
                    headers={**H, "Origin": "http://localhost:5173"})
    assert r.status_code == 200
    text = env.read_text(encoding="utf-8")
    assert "NANOGPT_API_KEY=sk-secret-123456789" in text and "NANOGPT_MODEL=m2" in text


def test_legacy_env_page_is_gone(client, H):
    assert client.get("/env", headers=H).status_code == 404
    assert client.post("/env", data={"env_content": "X=1"}, headers={**H, "Origin": "http://localhost:5173"}).status_code in (404, 405)


def test_backups_presets_usage(client, H):
    import admin_routes as A
    r = client.post("/api/backups", headers={**H, "Origin": "http://localhost:5173"}).get_json()
    assert r["name"].startswith("fandom_chars-")
    names = [b["name"] for b in client.get("/api/backups", headers=H).get_json()["backups"]]
    assert r["name"] in names
    pid = db.create_lore_project("After backup")
    res = client.post("/api/backups/restore", json={"name": r["name"]}, headers={**H, "Origin": "http://localhost:5173"}).get_json()
    assert res["restored"] == r["name"] and res["safety_backup"]
    assert all(p["id"] != pid for p in db.list_lore_projects())         # the project made after the backup is gone
    bad = client.post("/api/backups/restore", json={"name": "../../etc/passwd"}, headers={**H, "Origin": "http://localhost:5173"})
    assert bad.status_code == 400
    old_settings = A.SETTINGS_PATH
    A.SETTINGS_PATH = A.Path(A.__file__).resolve().parent / "tests" / "_settings_test.json"
    try:
        client.post("/api/config/presets", json={"extract": {"provider": "nanogpt", "model": "fast"}}, headers={**H, "Origin": "http://localhost:5173"})
        assert client.get("/api/config/presets", headers=H).get_json()["extract"]["model"] == "fast"
        assert client.post("/api/config/presets", json={"card": {"provider": "evil"}}, headers={**H, "Origin": "http://localhost:5173"}).status_code == 400
    finally:
        A.SETTINGS_PATH.unlink(missing_ok=True)
        A.SETTINGS_PATH = old_settings
    u = client.get("/api/usage?days=7", headers=H).get_json()
    assert "rows" in u and "total" in u
