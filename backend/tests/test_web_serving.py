"""Flask serving the built UI, which is what lets the portable build run without Node."""
import json

import app as app_module          # the same module object conftest built the client from


def _app_with_web(tmp_path, monkeypatch):
    """The app, pointed at a throwaway built UI in web/."""
    A = app_module
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><title>Character Card Studio</title><div id=root>", "utf-8")
    (web / "assets").mkdir()
    (web / "assets" / "index-abc.js").write_text("console.log('ui')", "utf-8")
    monkeypatch.setattr(A, "WEB_DIR", web)
    return A.app.test_client(), A


def test_root_serves_the_built_ui(tmp_path, monkeypatch):
    c, _ = _app_with_web(tmp_path, monkeypatch)
    r = c.get("/")
    assert r.status_code == 200
    assert b"id=root" in r.data              # the app shell, not the "backend is running" signpost


def test_assets_are_served(tmp_path, monkeypatch):
    c, _ = _app_with_web(tmp_path, monkeypatch)
    r = c.get("/assets/index-abc.js")
    assert r.status_code == 200 and b"console.log" in r.data


def test_an_unknown_path_falls_back_to_the_app_shell(tmp_path, monkeypatch):
    """The single-page app routes its own paths, so a deep link must not 404."""
    c, _ = _app_with_web(tmp_path, monkeypatch)
    r = c.get("/lore/some/deep/link")
    assert r.status_code == 200 and b"id=root" in r.data


def test_an_unknown_api_path_stays_a_json_404(tmp_path, monkeypatch):
    """The catch-all must not swallow /api: a bad API call still answers JSON, not the UI."""
    c, _ = _app_with_web(tmp_path, monkeypatch)
    r = c.get("/api/not/a/real/route")
    assert r.status_code == 404
    assert "error" in json.loads(r.data)
    assert b"id=root" not in r.data


def test_no_build_still_points_at_the_dev_server(monkeypatch):
    monkeypatch.setattr(app_module, "WEB_DIR", None)
    c = app_module.app.test_client()
    assert c.get("/").status_code == 200
    assert b"5173" in c.get("/").data
    assert c.get("/assets/index-abc.js").status_code == 404


def test_the_ui_cannot_be_used_to_read_outside_its_folder(tmp_path, monkeypatch):
    c, _ = _app_with_web(tmp_path, monkeypatch)
    for probe in ("../.env", "..%2f.env", "....//.env"):
        assert c.get(f"/{probe}").status_code in (200, 400, 404)   # never the file itself
        assert b"API_KEY" not in c.get(f"/{probe}").data
