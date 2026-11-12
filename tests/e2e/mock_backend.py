"""Mock backend for the browser tests: the real Flask app on a throwaway database, with every model call faked."""
import os, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
import database
database.DB_PATH = os.path.join(tempfile.mkdtemp(), "e2e.db")
import app as A, text_module as T
from pathlib import Path
A.ENV_PATH = Path(tempfile.mkdtemp()) / ".env"     # Config saves go to a scratch .env, never the real one
def fake(chunk, provider, model, mode):
    time.sleep(0.6)
    i = chunk["idx"]
    ents = [{"name": "Yuna", "aliases": ["Yunie"], "type": "character", "age": "19", "facts": f"Yuna leads the Gullwings (chunk {i}).",
             "voice": ["Let's go!"], "keywords": ["Yuna"], "origin": "altered" if i else "canon",
             "relations": [{"with": "Rikku", "relation": "cousin"}]},
            {"name": "Rikku", "aliases": [], "type": "character", "age": "18", "facts": f"Rikku is an Al Bhed thief (chunk {i}).",
             "voice": [], "keywords": ["Rikku"], "origin": "canon", "relations": [{"with": "Yuna", "relation": "cousin"}]},
            {"name": "Trema", "aliases": [], "type": "character", "age": "", "facts": "A mysterious magician.", "voice": [],
             "keywords": ["Trema"], "origin": "original", "relations": []},
            {"name": f"Odd trinket {i}", "aliases": [], "type": "item", "age": "", "facts": "A trinket seen once.", "voice": [],
             "keywords": [], "origin": "", "relations": []},
            {"name": "Yuna's mouth", "aliases": [], "type": "item", "age": "", "facts": "x", "voice": [], "keywords": ["mouth"], "origin": "", "relations": []}]
    beats = [{"title": f"Battle {i}", "what_happened": f"The girls fight in chunk {i}.", "participants": ["Yuna", "Rikku"],
              "place": f"Floor {i}", "marker": "", "flashback": False, "order": "", "state_changes": [], "evidence": "", "confidence": "high"}]
    return {"chapter_summary": f"In part {i + 1} the Gullwings press on.", "entities": ents, "beats": beats, "stats": {}}
T.extract_chunk = fake
def _req(provider, model, user, system=None, **k):
    if system == T.CRITIC_NOTES_SYSTEM:
        time.sleep(0.3)
        return {"summary": "The girls fight.", "strengths": ["Energetic action"], "habits": ["exclamation marks"],
                "problems": [{"category": "prose", "issue": "Telling emotions", "quote": "She was very sad.", "fix": "Show it"}]}
    if system == T.CRITIC_SYSTEM:
        return {"verdict": "Energetic but sloppy. It reads like a first draft with game jargon doing the heavy lifting.",
                "scores": [{"category": c, "score": s_, "why": "x"} for c, s_ in zip(T.CRITIC_CATEGORIES, [4, 5, 6, 3, 4, 7, 2, 5])],
                "strengths": ["Energetic action"], "problems": [{"title": "Telling, not showing", "evidence": "She was very sad.", "why": "Flat.", "fix": "Use action."}],
                "plan": [{"step": "Fix the structure", "how": "Outline each chapter's turn."}, {"step": "Cut filler", "how": "Delete recaps of game mechanics."}],
                "line_fixes": [{"original": "She was very sad.", "rewrite": "She turned away before they could see her face.", "why": "shows"}],
                "top3": ["Show emotions", "Cut jargon", "Proofread"]}
    import critic_tools as CT
    if system == CT.SWEEP_SYSTEM:
        time.sleep(0.2)
        n = 3 + (len(user) % 6)
        return {"score": n, "scores": {"prose": n, "dialogue": 5}, "summary": "The girls fight.", "worst": "Telling not showing",
                "quote": "Yuna leads the Gullwings", "fix": "Show it through action", "best": "Energy"}
    if system == CT.REWRITE_SYSTEM:
        return {"rewrite": "Yuna squared her shoulders and led the Gullwings on.", "notes": "Shows leadership through action."}
    if system == T.ARC_SYSTEM:
        return {"title": "Early arc", "summary": "They set out."}
    if system and "Narrative Archivist" in system:
        return {"current_timeline": "Night, day 2", "current_location": "Via Infinito", "dynamic": "Wary allies.",
                "characters": [{"name": "Yuna", "location": "cage", "physical": "bruised", "goal": "escape"}],
                "plot_hooks": ["Trema's orb"], "chapters": [{"title": "The Trap", "summary": "The girls are caged."}]}
    return NARR
T._request = _req
import assist_tools as AT
def _assist(provider, model, user, system=None, **k):
    if system and system.startswith("You shorten text"):
        return {"text": "A trimmed entry that keeps the names."}
    if system and "check an interview" in system:
        return {"issues": ["Claims to dislike her cousin."], "verdict": "Mostly in character."}
    return {"reply": "Ask quick, I have places to be."}
AT._request = _assist
import helper as HLP, json as _json, re as _re
def _helper(provider, model, user, system=None, **k):
    """A scripted SCRIBE-01 for the browser tests: edits the open card, builds a small lorebook, edits an entry."""
    step = user.count("RESULTS (step")
    last_user = [l for l in user.splitlines() if l.startswith("USER: ")][-1][6:].lower()
    m_card = _re.search(r"open card is card_id (\d+)", system or "")
    m_entry = _re.search(r"selected entry is entry_id (\d+)", system or "")
    def result(tool):
        for line in reversed(user.splitlines()):
            if line.startswith("{") and f'"tool": "{tool}"' in line:
                return _json.loads(line)["result"]
    if "description" in last_user and m_card:
        if step == 0:
            return {"say": "", "actions": [{"tool": "get_card", "args": {"card_id": int(m_card.group(1))}}]}
        if step == 1:
            return {"say": "", "actions": [{"tool": "update_card", "args": {"card_id": int(m_card.group(1)),
                    "fields": {"description": "A courier who knows every alley of the rainy port."}}}]}
        return {"say": "Report: description rewritten.", "actions": []}
    if "lorebook" in last_user:
        if step == 0:
            return {"say": "Proposal: a small lorebook.", "actions": [{"tool": "create_lore_project", "args": {"name": "Helper Port"}}]}
        if step == 1:
            pid = result("create_lore_project")["project_id"]
            return {"say": "", "actions": [
                {"tool": "add_lore_entry", "args": {"project_id": pid, "title": "Old Harbor", "entry_type": "place",
                                                    "keywords": "harbor, docks", "content": "Docks that never sleep."}},
                {"tool": "add_lore_entry", "args": {"project_id": pid, "title": "Grey Watch", "entry_type": "faction",
                                                    "keywords": "watch", "content": "The city guard."}}]}
        return {"say": "Report: lorebook ready with 2 entries.", "actions": []}
    if "tighten" in last_user and m_entry:
        if step == 0:
            return {"say": "", "actions": [{"tool": "update_lore_entry", "args": {"entry_id": int(m_entry.group(1)),
                    "fields": {"content": "Docks. Busy all night."}}}]}
        return {"say": "Report: entry tightened.", "actions": []}
    return {"say": "Report: a keyword is the word that makes a lorebook entry appear.", "actions": []}
HLP._request = _helper
NARR = {"name": "Gamerz Narrator", "description": "The Spira of this story.",
    "personality": "Vivid.", "scenario": "After the trap.", "first_mes": "Pyreflies drift past you.", "system_prompt": "Narrate.", "tags": ["ffx2"]}
A.generate_full_card = lambda source, provider, model, options=None: {"name": source["title"], "description": "Generated from the fic: " + (source["normalized"].get("summary") or "")[:200],
    "personality": "Cheerful.", "scenario": "", "first_mes": "Hi!", "mes_example": "", "tags": ["fic"], "structured_profile": {}, "alternate_greetings": []}
A._gen_request = lambda provider, model, prompt: {"name": "Gullwings Cast", "description": "Yuna and Rikku together.",
    "personality": "Bubbly.", "scenario": "On the airship.", "first_mes": "Yuna: Ready? Rikku: Always!", "mes_example": "", "tags": ["cast"]}
A.app.run(host="127.0.0.1", port=5000, threaded=True, use_reloader=False)
