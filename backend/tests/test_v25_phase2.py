"""v2.5 phase 2: re-send preview with skip list, "often here" on places, trim, character interview."""
import pytest

import assist_tools as A
import text_module as T
from test_text_flow import wait


def fake(chunk, provider, model, mode):
    i = chunk["idx"]
    ents = [{"name": "Mara", "aliases": [], "type": "character", "age": "", "facts": f"Mara fact {i}.", "voice": [],
             "keywords": ["Mara"], "origin": "", "relations": []},
            {"name": "Tomas", "aliases": [], "type": "character", "age": "", "facts": f"Tomas fact {i}.", "voice": [],
             "keywords": ["Tomas"], "origin": "", "relations": []},
            {"name": "Old Harbor", "aliases": ["the harbor"], "type": "place", "age": "", "facts": f"Docks {i}.",
             "voice": [], "keywords": ["harbor"], "origin": "", "relations": []}]
    if i == 0:
        ents.append({"name": "Ivo", "aliases": [], "type": "character", "age": "", "facts": "Seen once.", "voice": [],
                     "keywords": ["Ivo"], "origin": "", "relations": []})
    beats = [{"title": f"Meeting {i}", "what_happened": "They meet at the docks.", "participants": ["Mara"],
              "place": "Old Harbor", "marker": "", "flashback": False, "order": "", "state_changes": [],
              "evidence": "", "confidence": "high"}]
    return {"chapter_summary": f"Summary {i}.", "entities": ents, "beats": beats, "stats": {}}


@pytest.fixture(scope="module")
def proj(client, H):
    T.extract_chunk = fake
    text = "\n\n".join(f"Chapter {n}\n\n" + " ".join(f"w{n}x{k}" for k in range(400)) for n in range(1, 5))
    pid = client.post("/api/text/ingest", json={"name": "Phase2 Fic", "text": text, "chunk_chars": 2000}, headers=H).get_json()["id"]
    wait(client, H, client.post(f"/api/text/project/{pid}/extract", json={"mode": "deep", "parallel": 2, "condense": False},
                                headers=H).get_json()["job_id"])
    return pid


def ents(client, H, pid):
    return {e["name"]: e for e in client.get(f"/api/text/project/{pid}", headers=H).get_json()["entities"]}


def lore_list(client, H, lore):
    d = client.get(f"/api/lore/entries?project_id={lore}", headers=H).get_json()
    return d if isinstance(d, list) else d.get("entries", [])


def test_often_here(client, H, proj):
    E = ents(client, H, proj)
    by = {i["title"]: i for i in T._lore_items(proj)[0]}
    line = [l for l in by["Old Harbor"]["content"].splitlines() if l.startswith("Often here:")]
    assert line and line[0].startswith("Often here: Mara")       # in every event at the place, so first
    assert "Tomas" in line[0] and "Ivo" not in line[0]           # Ivo is there only once
    r = client.get(f"/api/text/project/{proj}/recap", headers=H).get_json()
    assert r["often_here"] is True
    client.put(f"/api/text/project/{proj}/recap", json={"often_here": False}, headers=H)
    by = {i["title"]: i for i in T._lore_items(proj)[0]}
    assert "Often here" not in by["Old Harbor"]["content"]
    client.put(f"/api/text/project/{proj}/recap", json={"often_here": True}, headers=H)
    assert E["Mara"]["entity_type"] == "character"


def test_resend_preview_and_skip(client, H, proj):
    assert client.post(f"/api/text/project/{proj}/commit/preview", headers=H).get_json() == {"mode": "new", "actions": []}
    lore = client.post(f"/api/text/project/{proj}/commit", headers=H).get_json()["lore_project_id"]
    p = client.post(f"/api/text/project/{proj}/commit/preview", headers=H).get_json()
    assert p["mode"] == "update" and p["lore_project_id"] == lore
    assert {x["action"] for x in p["actions"]} == {"same"}
    # hand edit one entry in LORE, change two in TEXT, drop one
    lore_entries = {e["title"]: e for e in lore_list(client, H, lore)}
    tomas = client.get(f"/api/lore/entry/{lore_entries['Tomas']['id']}", headers=H).get_json()
    tomas = tomas.get("entry", tomas)
    client.patch(f"/api/lore/entry/{tomas['id']}", json={**tomas, "keywords": tomas.get("keywords") or ["Tomas"],
                                                        "content": "LORE hand edit."}, headers=H)
    E = ents(client, H, proj)
    client.patch(f"/api/text/entity/{E['Mara']['id']}", json={"content": "New Mara text."}, headers=H)
    client.patch(f"/api/text/entity/{E['Tomas']['id']}", json={"content": "New Tomas text."}, headers=H)
    client.patch(f"/api/text/entity/{E['Ivo']['id']}", json={"keep": False}, headers=H)
    p = client.post(f"/api/text/project/{proj}/commit/preview", headers=H).get_json()
    act = {x["title"]: x for x in p["actions"]}
    assert act["Mara"]["action"] == "refresh" and act["Mara"]["old_content"] != act["Mara"]["new_content"]
    assert act["Mara"]["new_content"].startswith("New Mara text.")
    assert act["Tomas"]["action"] == "keep_edited"
    assert act["Ivo"]["action"] == "trash"
    assert "item" not in act["Mara"] and p["counts"]["refresh"] >= 1
    # nothing was written by the preview
    after = {e["title"]: e for e in lore_list(client, H, lore)}
    assert "New Mara" not in (after["Mara"].get("content") or "")
    # untick Ivo: it stays as it is; Mara is refreshed
    res = client.post(f"/api/text/project/{proj}/commit", json={"mode": "update", "skip": ["Ivo"]}, headers=H).get_json()
    assert res["skipped"] == 1 and res["updated"] >= 1 and res["trashed"] == 0 and res["kept_edited"] == 1
    after = {e["title"]: e for e in lore_list(client, H, lore)}
    assert "Ivo" in after
    mara = client.get(f"/api/lore/entry/{after['Mara']['id']}", headers=H).get_json()
    assert "New Mara text." in str(mara)
    res = client.post(f"/api/text/project/{proj}/commit", json={"mode": "update"}, headers=H).get_json()
    assert res["trashed"] == 1


def test_trim(client, H, monkeypatch):
    seen = {}

    def fake_req(provider, model, prompt, system=None, max_tokens=None):
        seen["system"], seen["prompt"] = system, prompt
        return {"text": "Short version."}
    monkeypatch.setattr(A, "_request", fake_req)
    long = "Mara is a courier who knows every alley. " * 40
    r = client.post("/api/trim", json={"text": long, "target_tokens": 60, "name": "Mara"}, headers=H).get_json()
    assert r["text"] == "Short version." and r["tokens_before"] > 60 and r["tokens_after"] < 10
    assert "about 60 tokens" in seen["system"] and "lorebook entry" in seen["system"] and "Mara" in seen["prompt"]
    r = client.post("/api/trim", json={"text": "Tiny.", "target_tokens": 60}, headers=H).get_json()
    assert r["unchanged"] and r["text"] == "Tiny."
    assert client.post("/api/trim", json={"text": ""}, headers=H).status_code == 400
    monkeypatch.setattr(A, "_request", lambda *a, **k: {"text": ""})
    assert client.post("/api/trim", json={"text": long}, headers=H).status_code == 502


def test_interview(client, H, proj, monkeypatch):
    seen = []

    def fake_req(provider, model, prompt, system=None, max_tokens=None):
        seen.append((system, prompt))
        if "check an interview" in (system or ""):
            return {"issues": ["Says she hates the docks."], "verdict": "One slip."}
        return {"reply": "Ask quick, I have a delivery."}
    monkeypatch.setattr(A, "_request", fake_req)
    E = ents(client, H, proj)
    msgs = [{"role": "user", "content": "Who are you?"}]
    r = client.post("/api/interview", json={"entity_id": E["Mara"]["id"], "messages": msgs}, headers=H).get_json()
    assert r["reply"].startswith("Ask quick") and r["name"] == "Mara"
    assert "You are Mara" in seen[-1][0] and "New Mara text." in seen[-1][0] and "Who are you?" in seen[-1][1]
    msgs += [{"role": "char", "content": r["reply"]}]
    c = client.post("/api/interview", json={"entity_id": E["Mara"]["id"], "messages": msgs, "check": True}, headers=H).get_json()
    assert c["issues"] == ["Says she hates the docks."] and c["verdict"]
    card = {"name": "Kel", "description": "A smith.", "structured_profile": {"with_close": "Warm."}}
    client.post("/api/interview", json={"card": card, "messages": [{"role": "user", "content": "Hi"}]}, headers=H)
    assert "You are Kel" in seen[-1][0] and "A smith." in seen[-1][0] and "Warm." in seen[-1][0]
    assert client.post("/api/interview", json={"card": card, "messages": msgs[:0]}, headers=H).status_code == 400
    assert client.post("/api/interview", json={"entity_id": 999999, "messages": msgs}, headers=H).status_code == 404
    assert client.post("/api/interview", json={"messages": msgs}, headers=H).status_code == 400


def test_story_bible_and_databank(client, H, proj):
    import io, zipfile
    md = client.get(f"/api/text/project/{proj}/bible", headers=H)
    t = md.get_data(as_text=True)
    assert md.status_code == 200 and t.startswith("# Phase2 Fic") and "attachment" in md.headers["Content-Disposition"]
    assert "## Characters" in t and "## Places" in t and "### Mara" in t and "Often here:" in t
    assert t.index("## Characters") < t.index("## Places") and "Cast Roster" not in t
    h = client.get(f"/api/text/project/{proj}/bible?format=html", headers=H).get_data(as_text=True)
    assert h.startswith("<!doctype html>") and "<h3>Mara</h3>" in h and "window.print()" in h and "@media print" in h
    assert "<script" not in h.lower()                               # nothing from the story can run as code
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/text/project/{proj}/databank", headers=H).data))
    names = z.namelist()
    assert "README.txt" in names and "characters/Mara.md" in names and "places/Old Harbor.md" in names
    assert z.read("characters/Mara.md").decode().startswith("# Mara\n\nStory: Phase2 Fic.")
    assert client.get("/api/text/project/999999/bible", headers=H).status_code == 404


def test_bible_escapes_html(client, H):
    from story_export import to_html, sections
    h = to_html("<T>", "", sections([{"title": "X<img src=x onerror=alert(1)>", "entry_type": "character",
                                     "content": "<script>alert(1)</script>", "tier": "", "image": "", "aliases": []}]))
    assert "<script>alert" not in h and "&lt;script&gt;" in h and "<img src=x" not in h


def test_secrets_reach_only_who_knows(client, H, proj, monkeypatch):
    import io, json as J, zipfile
    E = ents(client, H, proj)
    r = client.put(f"/api/text/entity/{E['Mara']['id']}/secrets", json={"secrets": [
        {"text": "She took the  ledger.", "known_by": ["Tomas", "tomas", " "]},
        {"text": "Afraid of deep water."}, {"text": "  "}, "junk"]}, headers=H).get_json()
    assert r["secrets"] == [{"text": "She took the ledger.", "known_by": ["Tomas"]}, {"text": "Afraid of deep water.", "known_by": []}]
    by = {i["title"]: i for i in T._lore_items(proj)[0]}
    s1, s2 = by["Mara — secret 1"], by["Mara — secret 2"]
    assert s1["char_filter"] == ["Tomas"] and "known only to Tomas" in s1["content"] and "Mara" in s1["keys"]
    assert s2["char_filter"] == ["Mara"]                                  # nobody listed: only Mara herself
    assert "ledger" not in by["Mara"]["content"]                          # never in the main entry
    # through LORE into SillyTavern World Info, with the character filter
    lore = client.post(f"/api/text/project/{proj}/commit", json={"mode": "update"}, headers=H).get_json()["lore_project_id"]
    from lore_tools import lorebook_entries
    from preview import world_info_book
    name, items = lorebook_entries(lore)
    wi = world_info_book(name, items)["entries"]
    sec = [e for e in wi.values() if "ledger" in e["content"]]
    assert len(sec) == 1 and sec[0]["characterFilter"] == {"isExclude": False, "names": ["Tomas"], "tags": []}
    plain = [e for e in wi.values() if e["comment"].startswith("Mara - ")]
    assert plain and plain[0]["characterFilter"]["names"] == []
    # changing who knows it refreshes the entry on the next send
    client.put(f"/api/text/entity/{E['Mara']['id']}/secrets", json={"secrets": [{"text": "She took the ledger.", "known_by": ["Tomas", "Ivo"]}]}, headers=H)
    res = client.post(f"/api/text/project/{proj}/commit", json={"mode": "update"}, headers=H).get_json()
    assert res["updated"] >= 1 and res["trashed"] >= 1                    # secret 2 removed -> trash
    wi = world_info_book(*lorebook_entries(lore))["entries"]
    assert [e["characterFilter"]["names"] for e in wi.values() if "ledger" in e["content"]] == [["Tomas", "Ivo"]]
    # story bible lists it; the Data Bank never carries it (no character filter there)
    t = client.get(f"/api/text/project/{proj}/bible", headers=H).get_data(as_text=True)
    assert "## Secrets" in t and "known only to Tomas, Ivo" in t
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/text/project/{proj}/databank", headers=H).data))
    assert not any("ledger" in z.read(n).decode() for n in z.namelist())
    # the interview: Tomas knows it, Mara (not listed) doesn't
    seen = []
    monkeypatch.setattr(A, "_request", lambda p, m, prompt, system=None, **k: seen.append(system) or {"reply": "Hm."})
    client.post("/api/interview", json={"entity_id": E["Tomas"]["id"], "messages": [{"role": "user", "content": "Hi"}]}, headers=H)
    client.post("/api/interview", json={"entity_id": E["Mara"]["id"], "messages": [{"role": "user", "content": "Hi"}]}, headers=H)
    assert "ledger" in seen[0] and "ledger" not in seen[1]
    # secrets and pictures survive Rebuild list
    client.put(f"/api/text/entity/{E['Old Harbor']['id']}/image", json={"image": ""}, headers=H)
    wait(client, H, client.post(f"/api/text/project/{proj}/extract", json={"merge_only": True, "condense": False}, headers=H).get_json()["job_id"])
    E2 = ents(client, H, proj)
    assert E2["Mara"]["secrets"] == [{"text": "She took the ledger.", "known_by": ["Tomas", "Ivo"]}]
    assert client.put("/api/text/entity/999999/secrets", json={"secrets": []}, headers=H).status_code == 404


def test_rebuild_keeps_pictures(client, H, proj):
    import base64, png_card
    E = ents(client, H, proj)
    name = client.post("/api/images", json={"data_url": "data:image/png;base64," + base64.b64encode(png_card.placeholder("h", 3, 3)).decode()},
                       headers=H).get_json()["image"]
    client.put(f"/api/text/entity/{E['Old Harbor']['id']}/image", json={"image": name}, headers=H)
    wait(client, H, client.post(f"/api/text/project/{proj}/extract", json={"merge_only": True, "condense": False}, headers=H).get_json()["job_id"])
    assert ents(client, H, proj)["Old Harbor"]["image"] == name
