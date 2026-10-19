import os
OUT = os.environ.get("E2E_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
os.makedirs(OUT, exist_ok=True)
import re
from playwright.sync_api import sync_playwright
R = []
def ok(c, n): R.append(c); print(("PASS " if c else "FAIL ") + n)
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1600, "height": 1400}, accept_downloads=True); pg = ctx.new_page()
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto("http://localhost:5173/"); pg.wait_for_timeout(800)
    pg.get_by_role("button", name=re.compile(r"^\s*TEXT\s*$", re.I)).first.click(); pg.wait_for_timeout(400)
    ok(pg.locator("text=Pick a text above to have it torn apart").count() == 1, "critic panel under Text Sources (empty state)")
    text = "\n\n".join(f"Chapter {n}: Part {n}\n\n" + " ".join(f"Sentence {k} of part {n}." for k in range(250)) for n in range(1, 4))
    pg.get_by_placeholder("Fic title").fill("Gamerz"); pg.locator("textarea").first.fill(text)
    pg.get_by_role("button", name=re.compile("LOAD TEXT")).click(); pg.wait_for_timeout(1000)
    # critic runs on its own, before any extraction
    pg.get_by_role("button", name=re.compile("RUN CRITIQUE")).click()
    pg.wait_for_timeout(600)
    ok(pg.locator("text=/Critic read|Critic is reading|Writing the critique|Starting the critic/").count() >= 1, "critic progress shown")
    for _ in range(40):
        pg.wait_for_timeout(400)
        if pg.locator("text=CRITIQUE · Gamerz").count(): break
    ok(pg.locator("text=CRITIQUE · Gamerz").count() == 1, "full critique opens when done")
    ok(pg.locator("text=STEP-BY-STEP IMPROVEMENT PLAN").count() == 1 and pg.locator("text=She turned away before they could see her face.").count() == 1, "plan + line fixes rendered")
    pg.screenshot(path=OUT + "/critique_full.png", full_page=False)
    with pg.expect_download() as dl:
        pg.get_by_role("button", name="↓ DOWNLOAD .MD").click()
    md = open(dl.value.path()).read()
    ok(md.startswith("# Critique: Gamerz") and "## The biggest problems" in md, "markdown download")
    pg.get_by_role("button", name="CLOSE", exact=True).click(); pg.wait_for_timeout(300)
    ok(pg.locator("text=LATEST VERDICT").count() == 1 and pg.locator("text=/average \\d/").count() == 1, "latest verdict + scores in panel")
    ok(pg.locator("text=/\\d SEND/").count() == 0 and pg.locator("text=/SEND \\d+ ENTRIES/").count() == 0, "critic did not extract anything")
    # extraction + AI archive recap + toolbars
    pg.get_by_role("button", name=re.compile("EXTRACT")).first.click()
    for _ in range(60):
        pg.wait_for_timeout(500)
        if pg.locator("text=/SEND \\d+ ENTRIES TO LORE/").count(): break
    pg.get_by_role("button", name=re.compile("WRITE RECAP WITH AI")).click(); pg.wait_for_timeout(1500)
    ta = pg.locator("textarea").filter(has_text="[HEADER]").first
    v = ta.input_value()
    ok(v.startswith("[HEADER]\nCurrent Timeline:") and "[BODY - CHAPTER LOG]\n## CHAPTER 1" in v and "[FOOTER - CURRENT STATUS]\n[ANCHOR: Current Situation]" in v, "archive-format Story So Far")
    pg.screenshot(path=OUT + "/text_full.png", full_page=True)
    ok(not errs, f"no page errors {errs[:2]}")
    b.close()
print("FAILS:", R.count(False))
