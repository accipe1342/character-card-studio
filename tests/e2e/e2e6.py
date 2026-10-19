"""Batches 4-8 in the browser: recap placement, add text, cast cards, sweep + rewrite, score history, search,
bundles, narrow layout, leave warning."""
import os
OUT = os.environ.get("E2E_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
os.makedirs(OUT, exist_ok=True)
import re, json, requests
from playwright.sync_api import sync_playwright
B = "http://127.0.0.1:5173"
R = []
def ok(c, n): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n)
H = {"Content-Type": "application/json", "Origin": "http://localhost:5173"}
texts = requests.get(B + "/api/text/projects").json()
proj = texts[-1] if isinstance(texts, list) else texts["projects"][-1]
pid = proj["id"]
cards_before = len(requests.get(B + "/api/cards").json())
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1600, "height": 1300}, accept_downloads=True)
    errs = []; dialogs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    def on_dialog(d):
        dialogs.append(d.type)
        try:
            d.accept()
        except Exception:      # the page is already closing (the beforeunload check)
            pass
    pg.on("dialog", on_dialog)
    pg.goto("http://localhost:5173/"); pg.wait_for_timeout(800)
    pg.get_by_role("button", name=re.compile(r"^\s*TEXT\s*$", re.I)).first.click(); pg.wait_for_timeout(600)
    pg.locator("div", has_text=re.compile("^" + re.escape(proj["name"]))).first.click(); pg.wait_for_timeout(1200)
    # recap placement
    pg.get_by_label("Where SillyTavern inserts the recap").select_option("depth"); pg.wait_for_timeout(500)
    ok(requests.get(B + f"/api/text/project/{pid}/recap").json()["position"] == "depth", "recap placement saved")
    # add text
    n_chunks = len(requests.get(B + f"/api/text/project/{pid}").json()["chunks"])
    pg.get_by_role("button", name=re.compile(r"\+ ADD TEXT")).click()
    pg.get_by_label("Text to add").fill("Chapter 9: Later\n\n" + "Yuna and Rikku chase Trema through the ruins. " * 12)
    pg.get_by_role("button", name="ADD", exact=True).click(); pg.wait_for_timeout(1200)
    n2 = len(requests.get(B + f"/api/text/project/{pid}").json()["chunks"])
    ok(n2 == n_chunks + 1, f"add text appended a chunk ({n_chunks} -> {n2})")
    ok(pg.locator("text=EXTRACT REMAINING").count() >= 1, "extract button offers the remaining chunk")
    # cast cards
    pg.get_by_role("button", name=re.compile("CARDS FOR MAIN CAST")).click()
    for _ in range(40):
        pg.wait_for_timeout(500)
        if len(requests.get(B + "/api/cards").json()) > cards_before + 1: break
    pg.wait_for_timeout(2000)
    cards = requests.get(B + "/api/cards").json()
    names = [c["name"] for c in cards]
    ok(len(cards) >= cards_before + 3 and "Gullwings Cast" in names, f"cast cards + group card made ({len(cards) - cards_before} new)")
    # sweep + rewrite
    pg.get_by_role("button", name=re.compile("CHAPTER SWEEP")).click()
    pg.wait_for_selector("[role=dialog][aria-label=Critique]", timeout=30000)
    dlg = pg.locator("[role=dialog][aria-label=Critique]")
    ok("PART BY PART" in dlg.inner_text() and "CHAPTER SWEEP" in dlg.inner_text(), "sweep result opens")
    dlg.get_by_role("button", name="WEAKEST FIRST").click()
    dlg.get_by_role("button", name=re.compile("REWRITE THE PASSAGE")).first.click(); pg.wait_for_timeout(1200)
    ok("squared her shoulders" in dlg.inner_text(), "rewrite shown under the problem")
    dlg.get_by_role("button", name="CLOSE", exact=True).click(); pg.wait_for_timeout(300)
    if pg.locator("[aria-label='Score history']").count() == 0:      # a fresh database: one more sweep for a history
        pg.get_by_role("button", name=re.compile("CHAPTER SWEEP")).click()
        pg.wait_for_selector("[role=dialog][aria-label=Critique]", timeout=30000)
        pg.locator("[role=dialog][aria-label=Critique]").get_by_role("button", name="CLOSE", exact=True).click(); pg.wait_for_timeout(300)
    ok(pg.locator("[aria-label='Score history']").count() == 1, "score history drawn")
    pg.screenshot(path=OUT + "/text_v24.png", full_page=True)
    # search -> LORE entry
    pg.keyboard.press("Control+k"); pg.wait_for_timeout(300)
    pg.keyboard.type("Wakka"); pg.wait_for_timeout(800)
    ok(pg.locator("[role=option]").count() >= 1, "search finds Wakka")
    pg.keyboard.press("Enter"); pg.wait_for_timeout(1500)
    title = pg.locator("section.signal-screen-panel input").first.input_value() if pg.locator("section.signal-screen-panel input").count() else ""
    ok(title == "Wakka" and pg.locator("text=📁 Besaid Lore").count() == 1, f"search opened the LORE entry ({title})")
    # search -> TEXT entity
    pg.locator("button[aria-label='Search everything']").click(); pg.wait_for_timeout(300)
    pg.keyboard.type("Trema"); pg.wait_for_timeout(800)
    pg.locator("[role=option]", has_text="character").first.click(); pg.wait_for_timeout(1800)
    ok(pg.locator("input[value='Trema']").count() >= 1, "search opened the TEXT entity in review")
    # narrow LORE
    pg.set_viewport_size({"width": 900, "height": 1200})
    pg.get_by_role("button", name=re.compile(r"^\s*LORE\s*$", re.I)).first.click(); pg.wait_for_timeout(700)
    sw = pg.evaluate("document.documentElement.scrollWidth")
    ok(sw <= 905, f"LORE has no sideways scroll at 900px ({sw})")
    pg.screenshot(path=OUT + "/lore_narrow.png", full_page=True)
    pg.set_viewport_size({"width": 1600, "height": 1300})
    # bundles
    pg.get_by_role("button", name=re.compile(r"^\s*CONFIG\s*$", re.I)).first.click(); pg.wait_for_timeout(900)
    sec = pg.locator("section", has_text="Project bundles")
    sec.locator("label", has_text=proj["name"]).first.locator("input").check()
    with pg.expect_download() as dl:
        sec.get_by_role("button", name=re.compile("EXPORT SELECTED")).click()
    path = dl.value.path()
    before = len(requests.get(B + "/api/text/projects").json())
    sec.locator("input[type=file]").set_input_files(path); pg.wait_for_timeout(1500)
    after = len(requests.get(B + "/api/text/projects").json())
    ok(after == before + 1, f"bundle exported and imported ({before} -> {after})")
    # leave warning while an edit is unsaved
    pg.get_by_role("button", name=re.compile(r"^\s*LORE\s*$", re.I)).first.click(); pg.wait_for_timeout(700)
    pg.locator("div", has_text=re.compile(r"^Besaid Lore$")).first.click(); pg.wait_for_timeout(500)
    pg.locator("div", has_text=re.compile(r"^Wakka$")).first.click(); pg.wait_for_timeout(500)
    pg.locator("textarea").last.click(); pg.keyboard.type(" more")
    pg.wait_for_timeout(100)
    ok(pg.locator("text=editing (autosaves)").count() >= 1, "edit is pending")
    ok(not errs, f"no page errors {errs[:2]}")
    pg.close(run_before_unload=True); pg.wait_for_timeout(500) if False else None
    import time; time.sleep(0.5)
    ok("beforeunload" in dialogs, f"leaving with an unsaved edit asks first ({dialogs})")
    b.close()
print("FAILS:", R.count(False))
