"""TEXT studio end to end with a fake model: extract -> review -> re-merge -> recap -> LORE -> cards/exports."""
import io
import time
import zipfile

import pytest

import text_module as T

calls = []


def fake_extract(chunk, provider, model, mode):
    calls.append(chunk["idx"])
    i = chunk["idx"]
    ents = [
        {"name": "Ilsa", "aliases": [], "type": "character", "age": "19", "facts": f"Ilsa fact {i}.", "voice": [],
         "keywords": ["Ilsa"], "origin": "canon" if i == 0 else "altered",
         "relations": [{"with": "Corin", "relation": "cousin"}]},
        {"name": "Corin", "aliases": [], "type": "character", "age": "", "facts": f"Corin fact {i}.", "voice": [],
         "keywords": ["Corin"], "origin": "canon", "relations": []},
        {"name": f"Trinket{i}", "aliases": [], "type": "item", "age": "", "facts": "A trinket.", "voice": [],
         "keywords": [f"Trinket{i}"], "origin": "original", "relations": []},
    ]
    beats = [{"title": f"Event in chunk {i}", "what_happened": f"Something happens in chunk {i}.",
              "participants": ["Ilsa"], "place": "", "marker": "", "flashback": False, "order": "",
              "state_changes": [], "evidence": "", "confidence": "high"}]
    return {"chapter_summary": f"Summary of chunk {i}.", "entities": ents, "beats": beats, "stats": {}}


@pytest.fixture(scope="module")
def project(client, H):
    T.extract_chunk = fake_extract
    text = "\n\n".join(f"Chapter {n}\n\n" + " ".join(f"w{n}x{k}" for k in range(400)) for n in range(1, 6))
    pid = client.post("/api/text/ingest", json={"name": "Fic", "text": text, "chunk_chars": 2000}, headers=H).get_json()["id"]
    job = client.post(f"/api/text/project/{pid}/extract", json={"mode": "deep", "parallel": 2, "condense": False},
                      headers=H).get_json()["job_id"]
    wait(client, H, job)
    return pid


def wait(client, H, job):
    for _ in range(200):
        j = client.get(f"/api/job/{job}", headers=H).get_json()
        if j.get("status") in ("done", "failed"):
            assert j["status"] == "done", j
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def ents(client, H, pid):
    p = client.get(f"/api/text/project/{pid}", headers=H).get_json()
    return {e["name"]: e for e in p["entities"]}, p


def test_extraction_merges_origin_relations_tiers(client, H, project):
    E, p = ents(client, H, project)
    assert E["Ilsa"]["origin"] == "altered"
    assert E["Ilsa"]["relations"][0]["with"] == "Corin"
    assert E["Ilsa"]["tier"] == "main" and E["Trinket0"]["tier"] == "one-off"
    assert E["Trinket0"]["keep"] is False            # one-off items start skipped
    assert E["Event in chunk 0"]["first_chunk"] == 0


def test_review_work_survives_remerge(client, H, project):
    E, _ = ents(client, H, project)
    client.patch(f"/api/text/entity/{E['Ilsa']['id']}", json={"content": "Hand-written Ilsa."}, headers=H)
    client.delete(f"/api/text/entity/{E['Corin']['id']}", headers=H)
    client.patch(f"/api/text/entity/{E['Trinket1']['id']}", json={"keep": True}, headers=H)
    wait(client, H, client.post(f"/api/text/project/{project}/extract", json={"merge_only": True, "condense": False},
                                headers=H).get_json()["job_id"])
    E, p = ents(client, H, project)
    assert E["Ilsa"]["content"] == "Hand-written Ilsa." and E["Ilsa"]["edited"]
    assert "Corin" not in E and [t["name"] for t in p["trash"]] == ["Corin"]
    assert E["Trinket1"]["keep"] is True


def test_trash_restore_and_empty(client, H, project):
    _, p = ents(client, H, project)
    rid = p["trash"][0]["id"]
    client.post(f"/api/text/entity/{rid}/restore", headers=H)
    E, p = ents(client, H, project)
    assert "Corin" in E and not p["trash"]
    client.delete(f"/api/text/entity/{rid}", headers=H)
    client.delete(f"/api/text/project/{project}/trash", headers=H)
    E, p = ents(client, H, project)
    assert "Corin" not in E and not p["trash"]


def test_redo_single_chunk(client, H, project):
    calls.clear()
    wait(client, H, client.post(f"/api/text/project/{project}/extract", json={"only": [1], "condense": False},
                                headers=H).get_json()["job_id"])
    assert calls == [1]


def test_degraded_chunk_is_retried(client, H, project):
    conn = T._conn()
    conn.execute("UPDATE text_chunk_results SET result_json=? WHERE project_id=? AND idx=2",
                 ('{"chapter_summary": "", "entities": [], "beats": [], "stats": {"degraded": true}}', project))
    conn.commit()
    conn.close()
    calls.clear()
    wait(client, H, client.post(f"/api/text/project/{project}/extract", json={"condense": False}, headers=H).get_json()["job_id"])
    assert calls == [2]


def test_recap_starting_point_and_commit(client, H, project):
    r = client.get(f"/api/text/project/{project}/recap?upto=0", headers=H).get_json()
    assert r["text"] == "Summary of chunk 0."
    client.put(f"/api/text/project/{project}/recap", json={"text": "My own recap.", "upto": 0}, headers=H)
    res = client.post(f"/api/text/project/{project}/commit", headers=H).get_json()
    ex = client.get(f"/api/lore/export?project_id={res['lore_project_id']}", headers=H).get_json()
    by = {e["comment"].rsplit(" - ", 1)[0]: e for e in ex["entries"].values()}
    assert by["Story So Far"]["content"] == "My own recap." and by["Story So Far"]["constant"] is True
    assert "chunk 0" in by["Story Timeline"]["content"] and "chunk 1" not in by["Story Timeline"]["content"]
    assert by["Ilsa"]["content"].startswith("In this story (differs from canon): Hand-written Ilsa.")  # hand edit wins
    assert by["Corin"]["content"].startswith("Corin fact 0.") and "Corin fact 1" not in by["Corin"]["content"]
    assert "Trinket1" not in by          # first appears after the starting point (only facts up to it are used)
    assert "Relationships: Corin (cousin)" in by["Ilsa"]["content"]
    pytest.lore_id = res["lore_project_id"]


def test_make_card_source(client, H, project):
    E, _ = ents(client, H, project)
    src = client.post(f"/api/text/entity/{E['Ilsa']['id']}/to-source", headers=H).get_json()
    assert src["source"]["normalized"]["title"] == "Ilsa"
    assert "Story so far" in src["source"]["raw_sections"]


def test_narrator_card(client, H, project):
    T._request = lambda provider, model, user, system=None, **k: {
        "name": "Fic Narrator", "description": "World.", "personality": "Vivid.", "scenario": "Start.",
        "first_mes": "The scene opens.", "system_prompt": "Narrate.", "tags": ["x"]}
    d = client.post(f"/api/text/project/{project}/narrator", json={}, headers=H).get_json()["card"]["data"]
    assert d["first_mes"] == "The scene opens." and d["system_prompt"] == "Narrate."
    assert any(e["name"] == "Story So Far" and e["constant"] for e in d["character_book"]["entries"])

    def down(*a, **k):
        raise RuntimeError("model down")
    T._request = down
    d = client.post(f"/api/text/project/{project}/narrator", json={}, headers=H).get_json()["card"]["data"]
    assert d["first_mes"] and d["name"].endswith("Narrator")


def test_card_export_embeds_lorebook_and_deeplore(client, H):
    lid = pytest.lore_id
    v2 = client.post("/api/export/v2", json={"card": {"name": "Ilsa"}, "lore_project_id": lid}, headers=H).get_json()
    assert v2["data"]["character_book"]["entries"]
    plain = client.post("/api/export/v2", json={"card": {"name": "Ilsa"}}, headers=H).get_json()
    assert "character_book" not in plain["data"]
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/lore/export/deeplore?project_id={lid}", headers=H).data))
    recap = next(n for n in z.namelist() if n.endswith("Story So Far.md"))
    assert z.read(recap).decode().startswith("---\ntags:")


def test_ai_recap_is_one_archive_entry(client, H, project):
    T._request = lambda provider, model, user, system=None, **k: {
        "current_timeline": "Night, day 2", "current_location": "Endless Stair, floor 100",
        "dynamic": "Ilsa and Corin are wary allies.",
        "characters": [{"name": "Ilsa", "location": "cage", "physical": "bruised", "goal": "escape"}],
        "plot_hooks": ["Calder's orb"],
        "chapters": [{"title": "The Trap", "summary": "The girls are caged."}, {"title": "Escape", "summary": "They break out."}]}
    r = client.post(f"/api/text/project/{project}/recap/ai", json={"upto": 1}, headers=H).get_json()
    t = r["text"]
    assert t.startswith("[HEADER]\nCurrent Timeline: Night, day 2\nCurrent Location: Endless Stair, floor 100")
    assert "[BODY - CHAPTER LOG]\n## CHAPTER 1 - The Trap\nThe girls are caged.\n\n## CHAPTER 2 - Escape" in t
    assert t.endswith("[FOOTER - CURRENT STATUS]\n[ANCHOR: Current Situation]\n* Ilsa: cage; bruised; escape\n* Plot Hooks: Calder's orb")
    saved = client.get(f"/api/text/project/{project}/recap", headers=H).get_json()
    assert saved["edited"] and saved["upto"] == 1 and saved["limit"] == T.SUMMARY_CHARS
    res = client.post(f"/api/text/project/{project}/commit", headers=H).get_json()
    ex = client.get(f"/api/lore/export?project_id={res['lore_project_id']}", headers=H).get_json()
    by = {e["comment"].rsplit(" - ", 1)[0]: e for e in ex["entries"].values()}
    assert by["Story So Far"]["content"] == t and by["Story So Far"]["constant"] is True
    assert by["Story Timeline"]["content"].startswith("- Something happens in chunk 0")


def test_archive_too_long_drops_oldest_chapters_not_status():
    res = {"current_timeline": "now", "characters": [{"name": "Ilsa", "location": "here", "physical": "ok", "goal": "win"}],
           "chapters": [{"title": f"C{i}", "summary": "x" * 900} for i in range(20)]}
    t = T.format_archive(res)
    assert len(t) <= T.SUMMARY_CHARS + 100 and "(earlier chapters omitted)" in t and t.endswith("* Ilsa: here; ok; win")


def test_ai_recap_model_failure_is_reported(client, H, project):
    def down(*a, **k):
        raise RuntimeError("model down")
    T._request = down
    r = client.post(f"/api/text/project/{project}/recap/ai", json={}, headers=H)
    assert r.status_code == 502 and "model call failed" in r.get_json()["error"]


def test_critic_job_and_history(client, H, project):
    seen = []

    def fake(provider, model, user, system=None, **k):
        seen.append("notes" if system == T.CRITIC_NOTES_SYSTEM else "final")
        if system == T.CRITIC_NOTES_SYSTEM:
            return {"summary": "Stuff happens.", "strengths": ["Brisk"], "habits": ["adverbs"],
                    "problems": [{"category": "prose", "issue": "Telling", "quote": "w1x1 w1x2", "fix": "Show it"}]}
        assert "EDITOR'S NOTES PER PART" in user and "Telling" in user
        return {"verdict": "Not ready.", "scores": [{"category": c, "score": 4, "why": "meh"} for c in T.CRITIC_CATEGORIES],
                "strengths": ["Brisk"], "problems": [{"title": "Telling", "evidence": "w1x1", "why": "flat", "fix": "show"}],
                "plan": [{"step": "Cut adverbs", "how": "Delete most -ly words"}],
                "line_fixes": [{"original": "w1x1", "rewrite": "better", "why": "punch"}], "top3": ["show", "cut", "vary"]}
    T._request = fake
    job = client.post(f"/api/text/project/{project}/critique", json={"focus": "dialogue"}, headers=H).get_json()["job_id"]
    j = wait(client, H, job)
    cid = j["result"]["critique_id"]
    assert seen.count("final") == 1 and seen.count("notes") >= 2
    c = client.get(f"/api/text/critique/{cid}", headers=H).get_json()
    md = c["result"]["markdown"]
    assert md.startswith("# Critique: Fic") and "## Step-by-step improvement plan" in md and "4/10" in md
    hist = client.get(f"/api/text/project/{project}/critiques", headers=H).get_json()
    assert hist[0]["id"] == cid and hist[0]["focus"] == "dialogue"
    # one part: the critic reads the text directly (no notes pass)
    seen.clear()
    T._request = lambda provider, model, user, system=None, **k: (seen.append(user[:5]) or
        {"verdict": "Short.", "scores": [], "problems": [], "plan": [], "line_fixes": [], "top3": []})
    j = wait(client, H, client.post(f"/api/text/project/{project}/critique", json={"chunks": [0], "scope_label": "Part 1"},
                                    headers=H).get_json()["job_id"])
    assert seen == ["STORY"] and j["status"] == "done"
    client.delete(f"/api/text/critique/{cid}", headers=H)
    assert all(x["id"] != cid for x in client.get(f"/api/text/project/{project}/critiques", headers=H).get_json())


def _epub(chapters):
    """A minimal but real epub: container.xml -> content.opf -> one xhtml per chapter."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        items = refs = ""
        for i, (heading, line) in enumerate(chapters, 1):
            body = "".join(f"<p>{line} Paragraph {n}.</p>" for n in range(90))
            z.writestr(f"ch{i}.xhtml", f"<html><body><h1>{heading}</h1>{body}</body></html>")
            items += f'<item id="c{i}" href="ch{i}.xhtml" media-type="application/xhtml+xml"/>'
            refs += f'<itemref idref="c{i}"/>'
        z.writestr("content.opf",
                   '<package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                   f'<dc:title>Test Fic</dc:title></metadata><manifest>{items}</manifest><spine>{refs}</spine></package>')
    return buf.getvalue()


def test_epub_keeps_chapter_headings():
    """A chapter heading that already reads "Chapter N: ..." must survive ingest: the chunker splits on it,
    and "roleplay starts after chapter N" has nothing to anchor to without it."""
    title, text = T.epub_to_text(_epub([("Chapter 1: The Harbor", "Mara walked the docks."),
                                        ("Chapter 2: The Lantern Steps", "The Grey Watch lit the stair."),
                                        ("A Note From the Author", "Thanks for reading.")]))
    assert title == "Test Fic"
    assert "Chapter 1: The Harbor" in text and "Chapter 2: The Lantern Steps" in text
    assert "Chapter: A Note From the Author" in text          # an odd heading still becomes a section
    labels = [c["label"] for c in T.chunk_text(text)]
    # a long chapter may be split into "(part 1/2)" pieces, but every chunk is still named for its chapter
    assert labels[0] == "Chapter 1: The Harbor", labels
    assert any(l.startswith("Chapter 2: The Lantern Steps") for l in labels), labels
    assert all(l.startswith("Chapter") for l in labels), labels


AO3_CHAPTER = """<html><body><h2 class="title heading">Saltmere Nights</h2>
<div id="chapters"><div class="chapter" id="chapter-1"><h3 class="title"><a>Chapter 1</a>: The Harbor</h3>
<div class="userstuff" role="article"><h3 class="landmark">Chapter Text</h3><p>Mara walked the docks.</p></div>
</div></div><ul class="work navigation actions">
<li class="chapter next"><a href="/works/555/chapters/2">Next Chapter &rarr;</a></li>
<li><a href="/works/556">Next Work &rarr;</a></li></ul></body></html>"""


def test_ao3_chapter_heading_is_not_doubled():
    """AO3's own h3.title already reads "Chapter 1: ..." - prefixing another one gives
    "Chapter 1: Chapter 1 : The Harbor" in every chunk label."""
    _, text = T.html_to_text(AO3_CHAPTER)
    assert text.startswith("Chapter 1: The Harbor"), text[:60]
    assert "Chapter Text" not in text                      # AO3's landmark heading is junk


def test_next_chapter_link_survives_an_arrow(monkeypatch):
    """The next link is rendered "Next Chapter ->" on AO3; an exact-match rule stops after page one.
    "Next Work" is a different link on the same page and must not be followed."""
    import text_module

    class R:
        status_code = 200
        content = AO3_CHAPTER.encode()
        def raise_for_status(self): pass

    monkeypatch.setattr(text_module.requests, "get", lambda *a, **k: R())
    _, _, nxt = text_module.fetch_page("https://archiveofourown.org/works/555/chapters/1")
    assert nxt and nxt.endswith("/works/555/chapters/2"), nxt
