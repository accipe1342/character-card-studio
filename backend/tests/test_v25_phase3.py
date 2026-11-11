"""v2.5 phase 3: card PNGs, Quick Reply sets, and sending to a real SillyTavern.

The live tests need a SillyTavern running with basic auth. Point them at it with
    ST_TEST_URL=http://127.0.0.1:8123 ST_TEST_USER=tester ST_TEST_PASSWORD=pw-123
They are skipped when it isn't reachable.
"""
import os

import pytest
import requests

import png_card
import st_bridge as S

ST_URL = os.getenv("ST_TEST_URL", "http://127.0.0.1:8123")
ST_USER = os.getenv("ST_TEST_USER", "tester")
ST_PW = os.getenv("ST_TEST_PASSWORD", "pw-123")


def st_up():
    try:
        return requests.get(ST_URL + "/version", timeout=2).status_code in (200, 401)
    except Exception:
        return False


live = pytest.mark.skipif(not st_up(), reason="no SillyTavern to test against")
CARD = {"name": "Mara Vell", "description": "Mara is a courier who knows every alley.", "personality": "Dry, quick.",
        "scenario": "A rainy port.", "first_mes": "*Mara shakes rain off her coat.* \"You're late.\"",
        "mes_example": "<START>\n{{char}}: Keep up.", "tags": ["courier"], "structured_profile": {}}


def test_png_embed_and_read():
    png = png_card.placeholder("Mara")
    assert png.startswith(png_card.SIG)
    out = png_card.embed(png, {"spec": "chara_card_v2", "data": {"name": "Mara"}}, {"spec": "chara_card_v3"})
    got = png_card.read(out)
    assert got["chara"]["data"]["name"] == "Mara" and got["ccv3"]["spec"] == "chara_card_v3"
    again = png_card.embed(out, {"spec": "chara_card_v2", "data": {"name": "Mara 2"}})      # replaces, no duplicates
    assert png_card.read(again) == {"chara": {"spec": "chara_card_v2", "data": {"name": "Mara 2"}}}
    assert again.count(b"tEXtchara") == 1
    import base64
    assert png_card.decode_data_url("data:image/png;base64," + base64.b64encode(png).decode()) == png
    assert png_card.decode_data_url("data:image/jpeg;base64,/9j/4AAQ") is None
    with pytest.raises(ValueError):
        png_card.embed(b"nope", {})


def test_quick_reply_set_shape():
    s = S.quick_reply_set("Port Story", ["Mara", "Tomas"], ["Old Harbor", "A | B"])
    assert s["version"] == 2 and s["name"] == "Port Story" and s["idIndex"] == len(s["qrList"])
    labels = [q["label"] for q in s["qrList"]]
    assert labels[:4] == ["→ Old Harbor", "→ A | B", "+ Mara", "+ Tomas"] and "Recap" in labels
    assert s["qrList"][1]["message"] == "/sys The scene moves to A \\| B."      # a pipe would split the STscript
    assert [q["id"] for q in s["qrList"]] == list(range(1, len(labels) + 1))
    keys = set(s["qrList"][0])
    assert {"label", "message", "contextList", "executeOnStartup", "automationId"} <= keys


def test_text_project_quick_replies(client, H):
    import text_module as T
    from test_text_flow import wait
    T.extract_chunk = lambda chunk, provider, model, mode: {
        "chapter_summary": "s", "beats": [], "stats": {},
        "entities": [{"name": "Mara", "aliases": [], "type": "character", "age": "", "facts": "f", "voice": [],
                      "keywords": ["Mara"], "origin": "", "relations": []},
                     {"name": "Old Harbor", "aliases": [], "type": "place", "age": "", "facts": "f", "voice": [],
                      "keywords": ["harbor"], "origin": "", "relations": []}]}
    text = "\n\n".join(f"Chapter {n}\n\n" + " ".join(f"w{k}" for k in range(300)) for n in range(1, 3))
    pid = client.post("/api/text/ingest", json={"name": "QR Fic", "text": text, "chunk_chars": 2000}, headers=H).get_json()["id"]
    wait(client, H, client.post(f"/api/text/project/{pid}/extract", json={"mode": "quick", "condense": False},
                                headers=H).get_json()["job_id"])
    s = client.get(f"/api/text/project/{pid}/quick-replies", headers=H).get_json()
    labels = [q["label"] for q in s["qrList"]]
    assert s["name"] == "QR Fic" and "+ Mara" in labels and "→ Old Harbor" in labels
    assert client.get("/api/text/project/999999/quick-replies", headers=H).status_code == 404


def test_errors_are_plain_words(client, H, monkeypatch):
    monkeypatch.setenv("ST_URL", "http://127.0.0.1:9")            # nothing listens there
    r = client.post("/api/st/test", json={}, headers=H)
    assert r.status_code == 502 and "Can't reach SillyTavern" in r.get_json()["error"]
    assert client.post("/api/st/push/card", json={"card": {}}, headers=H).status_code == 400
    assert client.post("/api/st/push/quick-replies", json={"set": {"name": "x"}}, headers=H).status_code == 400


@live
def test_live_login_and_csrf(client, H, monkeypatch):
    bad = client.post("/api/st/test", json={"url": ST_URL, "user": ST_USER, "password": "wrong"}, headers=H)
    assert bad.status_code == 502 and "user name and password" in bad.get_json()["error"]
    good = client.post("/api/st/test", json={"url": ST_URL, "user": ST_USER, "password": ST_PW}, headers=H).get_json()
    assert good["ok"] and good["version"]
    # saved password comes back masked; the masked value from the form means "use the saved one"
    monkeypatch.setenv("ST_URL", ST_URL); monkeypatch.setenv("ST_USER", ST_USER); monkeypatch.setenv("ST_PASSWORD", ST_PW)
    assert client.post("/api/st/test", json={"password": S.MASK + "-123"}, headers=H).get_json()["ok"]


def _st_session():
    s = requests.Session(); s.auth = (ST_USER, ST_PW)
    tok = s.get(ST_URL + "/csrf-token").json()["token"]
    s.headers["X-CSRF-Token"] = tok
    return s


@live
def test_live_push_card_lore_and_quick_replies(client, H, monkeypatch):
    monkeypatch.setenv("ST_URL", ST_URL); monkeypatch.setenv("ST_USER", ST_USER); monkeypatch.setenv("ST_PASSWORD", ST_PW)
    # a lore project to embed and to send as World Info
    lore = client.post("/api/lore/projects", json={"name": "Port Lore"}, headers=H).get_json()
    lore_id = lore.get("id") or lore.get("project_id")
    eid = client.post("/api/lore/entry/new", json={"project_id": lore_id, "title": "Old Harbor"}, headers=H).get_json()["id"]
    full = client.get(f"/api/lore/entry/{eid}", headers=H).get_json()
    full = full.get("entry", full)
    client.patch(f"/api/lore/entry/{eid}", json={**full, "entry_type": "place", "keywords": ["harbor"],
                                                 "content": "Docks that never sleep."}, headers=H)
    r = client.post("/api/st/push/card", json={"card": CARD, "lore_project_id": lore_id}, headers=H).get_json()
    assert r.get("file_name"), r
    fname = r["file_name"]
    st = _st_session()
    got = st.post(ST_URL + "/api/characters/get", json={"avatar_url": f"{fname}.png"}).json()
    assert got["name"] == "Mara Vell" and "courier" in got["description"]
    assert got["data"]["character_book"]["entries"][0]["content"] == "Docks that never sleep."
    # re-sending with the returned name replaces it instead of adding a copy
    before = len(st.post(ST_URL + "/api/characters/all", json={}).json())
    r2 = client.post("/api/st/push/card", json={"card": {**CARD, "personality": "Changed."}, "file_name": fname},
                     headers=H).get_json()
    assert r2["file_name"] == fname
    assert len(st.post(ST_URL + "/api/characters/all", json={}).json()) == before
    got = st.post(ST_URL + "/api/characters/get", json={"avatar_url": f"{fname}.png"}).json()
    assert got["personality"] == "Changed."
    # World Info
    w = client.post("/api/st/push/lore", json={"project_id": lore_id}, headers=H).get_json()
    assert w["name"] == "Port Lore" and w["entries"] == 1
    wi = st.post(ST_URL + "/api/worldinfo/get", json={"name": "Port Lore"}).json()
    assert any(e["content"] == "Docks that never sleep." for e in wi["entries"].values())
    # Quick Replies: SillyTavern lists the saved set in its settings
    qr = S.quick_reply_set("Port Story", ["Mara"], ["Old Harbor"])
    assert client.post("/api/st/push/quick-replies", json={"set": qr}, headers=H).get_json()["count"] == len(qr["qrList"])
    sets = st.post(ST_URL + "/api/settings/get", json={}).json().get("quickReplyPresets") or []
    assert any(x.get("name") == "Port Story" and x["qrList"][0]["label"] == "→ Old Harbor" for x in sets)


def test_charx_shape(client, H):
    import io, json, zipfile
    from charx import build_charx
    z = zipfile.ZipFile(io.BytesIO(build_charx(CARD)))
    v3 = json.loads(z.read("card.json"))
    assert v3["spec"] == "chara_card_v3" and v3["data"]["name"] == "Mara Vell"
    assert v3["data"]["assets"] == [{"type": "icon", "uri": "ccdefault:", "name": "main", "ext": "png"}]
    pic = png_card.placeholder("m", 8, 8)
    z = zipfile.ZipFile(io.BytesIO(build_charx(CARD, image_bytes=pic)))
    v3 = json.loads(z.read("card.json"))
    a = v3["data"]["assets"][0]
    assert a["uri"] == "embeded://assets/icon/images/main.png" and z.read("assets/icon/images/main.png") == pic
    import base64
    r = client.post("/api/export/charx", json={"card": CARD, "image": "data:image/png;base64," + base64.b64encode(pic).decode()}, headers=H)
    assert r.status_code == 200 and r.headers["Content-Disposition"].endswith('Mara_Vell.charx')
    assert zipfile.ZipFile(io.BytesIO(r.data)).read("assets/icon/images/main.png") == pic
    assert client.post("/api/export/charx", json={"card": {}}, headers=H).status_code == 400


@live
def test_live_charx_imports_into_sillytavern():
    from charx import build_charx
    pic = png_card.placeholder("charx portrait", 32, 48)
    data = build_charx({**CARD, "name": "Charx Courier"}, image_bytes=pic)
    st = _st_session()
    r = st.post(ST_URL + "/api/characters/import", files={"avatar": ("Charx_Courier.charx", data, "application/zip")},
                data={"file_type": "charx"}).json()
    assert r.get("file_name"), r
    got = st.post(ST_URL + "/api/characters/get", json={"avatar_url": r["file_name"] + ".png"}).json()
    assert got["name"] == "Charx Courier" and "courier" in got["description"]
    # the portrait became the avatar: SillyTavern serves a thumbnail of it
    th = st.get(ST_URL + "/thumbnail", params={"type": "avatar", "file": r["file_name"] + ".png"})
    assert th.status_code == 200 and th.headers["Content-Type"].startswith("image/")
