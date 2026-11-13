"""Text cleaning, chunking and the extraction filters (no model calls)."""
import lore_extract as L
import text_module as T


def test_replacement_chars_repaired():
    out = T.fix_replacement_chars("I don�t know. �Hello,� she said. Wait�what?")
    assert "�" not in out
    assert "don’t" in out
    assert "“Hello," in out


def test_boilerplate_and_chapter_dropdown_removed():
    raw = ("Previous\nNext\nChapter 1\nChapter 2\nChapter 3\nWrite a Review\n\n"
           "Chapter 1: The Start\n\nShe walked in. " + "Story text. " * 60)
    out = T.clean_text(raw)
    assert "Write a Review" not in out
    assert "Chapter 1: The Start" in out


def test_chunks_have_no_duplicates_and_reasonable_sizes():
    text = "\n\n".join(f"Chapter {n}\n\n" + " ".join(f"Sentence {k} of chapter {n} goes here." for k in range(250))
                         for n in range(1, 5))
    text += "\n\n" + text.split("\n\nChapter 4")[0][-3000:]          # a repeated page
    chunks = T.chunk_text(T.clean_text(text), 4000)
    bodies = [c["text"] for c in chunks]
    assert len(bodies) == len(set(bodies))
    assert all(len(b) <= 4000 * 1.6 for b in bodies), [len(b) for b in bodies]


def test_junk_entities_filtered():
    for bad in ["Ilsa's mouth", "behemoth's tail", "floor", "rape", "boredom"]:
        assert L._junk_entity(bad), bad
    for good in ["Ilsa", "mask rack", "Endless Stair", "Iron Warden", "the room where the girls met Calder"]:
        assert not L._junk_entity(good), good


def test_name_check_ignores_sentence_starters_and_contractions():
    text = ("“I’ll go,” she said. Anyway, we met Ilsa’s friend Corin at Fennmoor. "
            "Later Corin and Garrick spoke; Garrick nodded. Yeah. I’m sure Corin left Fennmoor.")
    missing = L.name_check(text, {"entities": [], "beats": []})
    assert "Corin" in missing and "Fennmoor" in missing
    assert not {"I’ll", "Anyway", "Yeah", "I’m"} & set(missing)


def test_keyword_cleaner():
    e = {"id": 1, "name": "Mascot spirit mask", "aliases": [], "keywords": ["Mascot spirit mask", "spell", "Vessa", "vessa", "mascot"]}
    assert T.clean_keywords(e, {"vessa": 2}) == ["Mascot spirit mask", "mascot"]


def test_recap_keeps_latest_events_when_too_long():
    recap = T.build_recap([f"Chapter {i} happened. More detail." for i in range(1000)])
    assert len(recap) <= T.RECAP_CHARS + 40
    assert "Chapter 999 happened." in recap


def test_wiki_urls_use_the_mediawiki_api(monkeypatch):
    import text_module as T
    assert T.wiki_api_candidates("https://archiveofourown.org/works/1") == []
    assert T.wiki_api_candidates("https://examplesaga.fandom.com/wiki/Category:Characters") == []
    c = T.wiki_api_candidates("https://examplesaga.fandom.com/fr/wiki/Ilsa_(Sample_Saga)")
    assert c[0][0] == "https://examplesaga.fandom.com/fr/api.php" and c[0][1]["page"] == "Ilsa (Sample Saga)"
    html = ('<aside class="portable-infobox"><div class="pi-data"><h3 class="pi-data-label">Age</h3>'
            '<div class="pi-data-value">17</div></div></aside><p>Ilsa is a summoner<sup class="reference">[1]</sup>.</p>'
            '<h2>Story<span class="mw-editsection">[edit]</span></h2><p>' + "She travels across Aldmere. " * 12 + '</p>'
            '<ul><li>White magic</li></ul><h2>References</h2><div class="reflist"><p>junk</p></div>'
            '<table class="navbox"><tr><td>nav junk</td></tr></table>')
    calls = []

    class Resp:
        status_code = 200
        def json(self):
            return {"parse": {"title": "Ilsa", "displaytitle": "<i>Ilsa</i>", "text": html}}
    monkeypatch.setattr(T.requests, "get", lambda url, params=None, **k: calls.append(url) or Resp())
    title, text, nxt = T.fetch_page("https://examplesaga.fandom.com/wiki/Ilsa")
    assert title == "Ilsa" and nxt is None and calls == ["https://examplesaga.fandom.com/api.php"]
    assert "Age: 17" in text and "## Story" in text and "- White magic" in text and "Ilsa is a summoner." in text
    assert "[edit]" not in text and "junk" not in text and "References" not in text
