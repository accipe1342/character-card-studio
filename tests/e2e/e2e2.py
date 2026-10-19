import os
OUT = os.environ.get("E2E_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
os.makedirs(OUT, exist_ok=True)
import re
from playwright.sync_api import sync_playwright
R = []
def ok(c, n): R.append(c); print(("PASS " if c else "FAIL ") + n)
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1600, "height": 1300})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto("http://localhost:5173/"); pg.wait_for_timeout(800)
    pg.get_by_role("button", name=re.compile(r"^\s*TEXT\s*$", re.I)).first.click(); pg.wait_for_timeout(400)
    text = "\n\n".join(f"Chapter {n}: Part {n}\n\n" + " ".join(f"Sentence {k} of part {n}." for k in range(250)) for n in range(1, 6))
    pg.get_by_placeholder("Fic title").fill("Gamerz"); pg.locator("textarea").first.fill(text)
    pg.get_by_role("button", name=re.compile("LOAD TEXT")).click(); pg.wait_for_timeout(1000)
    pg.get_by_role("button", name=re.compile("EXTRACT")).first.click()
    for _ in range(60):
        pg.wait_for_timeout(500)
        if pg.locator("text=/SEND \\d+ ENTRIES TO LORE/").count(): break
    ok(pg.locator("text=/Battle \\d/").count() == 0, "events not in the main list")
    ok(pg.locator("text=/TIMELINE · \\d+ EVENTS · \\d+ KEPT/").count() == 1, "collapsed TIMELINE section")
    pg.locator("text=/TIMELINE · \\d+ EVENTS/").click(); pg.wait_for_timeout(400)
    rows = [r.split(" · ")[0] for r in pg.locator("text=/^Battle \\d/").all_inner_texts()]
    ok(rows[:3] == ["Battle 0", "Battle 1", "Battle 2"], f"timeline in story order: {rows[:4]}")
    ok(pg.locator("text=/· part 1/").count() >= 1, "timeline rows show their part")
    pg.get_by_role("button", name=re.compile("WRITE RECAP WITH AI")).click(); pg.wait_for_timeout(1500)
    ok(pg.locator("textarea", has_text="Current timeline: Night, day 2").count() == 1, "AI status in the recap box")
    ok(pg.locator("textarea", has_text="## CHAPTER 1 - The Trap").count() == 1, "AI chapter log in the timeline box")
    pg.screenshot(path=OUT + "/recap_ai.png", full_page=True)
    ok(not errs, f"no page errors {errs[:2]}")
    b.close()
print("FAILS:", R.count(False))
