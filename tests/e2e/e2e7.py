"""v2.5 phases 1-2 in the browser: BY CHAPTER / MENTIONS / INTERVIEW tabs, prose scan, re-send preview,
trim compare in LORE, interview + personality layers in CHARACTER."""
import os
OUT = os.environ.get("E2E_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
os.makedirs(OUT, exist_ok=True)
import re, requests
from playwright.sync_api import sync_playwright
from ui import menu, open_menu
B = "http://127.0.0.1:5173"
R = []
def ok(c, n): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n)
texts = requests.get(B + "/api/text/projects").json()
texts = texts if isinstance(texts, list) else texts["projects"]
proj = next(p for p in texts if p.get("lore_project_id"))
pid, lore_pid = proj["id"], proj["lore_project_id"]
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1600, "height": 1300}, accept_downloads=True)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    pg.goto("http://localhost:5173/"); pg.wait_for_timeout(800)
    pg.get_by_role("button", name=re.compile(r"^\s*TEXT\s*$", re.I)).first.click(); pg.wait_for_timeout(600)
    pg.locator("div", has_text=re.compile("^" + re.escape(proj["name"]) + r"\s*[\d.]+k? chars")).last.click(); pg.wait_for_timeout(1200)
    # entity tabs
    pg.locator("div", has_text=re.compile(r"^Rikku$")).first.click(); pg.wait_for_timeout(500)
    pg.get_by_role("tab", name="BY CHAPTER").click(); pg.wait_for_timeout(800)
    ok(pg.locator("text=/Rikku is an Al Bhed thief \\(chunk 0\\)/").count() >= 1, "BY CHAPTER lists what each chapter said")
    pg.get_by_role("tab", name="MENTIONS").click(); pg.wait_for_timeout(800)
    ok(pg.locator("text=/line\\(s\\) in \\d+ chapter\\(s\\)/").count() == 1, "MENTIONS searched the text")
    pg.get_by_role("tab", name="INTERVIEW").click(); pg.wait_for_timeout(300)
    pg.get_by_role("button", name="Who are you, in your own words?").click(); pg.wait_for_timeout(1000)
    ok(pg.locator("text=Ask quick, I have places to be.").count() == 1, "INTERVIEW answers in character")
    pg.get_by_label("Question").fill("Do you like your cousin?"); pg.keyboard.press("Enter"); pg.wait_for_timeout(1000)
    pg.get_by_role("button", name=re.compile("CHECK AGAINST NOTES")).click(); pg.wait_for_timeout(1000)
    ok(pg.locator("text=Claims to dislike her cousin.").count() == 1, "interview check lists a slip")
    pg.screenshot(path=OUT + "/text_interview.png", full_page=True)
    pg.get_by_role("tab", name="EDIT").click(); pg.wait_for_timeout(300)
    # prose scan from the critic
    pg.get_by_role("button", name=re.compile("PROSE SCAN")).click()
    pg.wait_for_selector("[role=dialog][aria-label='Prose scan']", timeout=10000)
    dlg = pg.locator("[role=dialog][aria-label='Prose scan']")
    ok("STOCK PHRASES" in dlg.inner_text() and "words" in dlg.inner_text(), "prose scan opens")
    dlg.get_by_role("button", name="CLOSE", exact=True).click(); pg.wait_for_timeout(300)
    # re-send preview: change an entry, then update with it unticked, then ticked
    E = {e["name"]: e for e in requests.get(B + f"/api/text/project/{pid}").json()["entities"]}
    requests.patch(B + f"/api/text/entity/{E['Rikku']['id']}", json={"content": "Rikku, changed for the preview test."},
                   headers={"Origin": "http://localhost:5173"})
    pg.reload(); pg.wait_for_timeout(800)
    pg.get_by_role("button", name=re.compile(r"^\s*TEXT\s*$", re.I)).first.click(); pg.wait_for_timeout(600)
    pg.locator("div", has_text=re.compile("^" + re.escape(proj["name"]) + r"\s*[\d.]+k? chars")).last.click(); pg.wait_for_timeout(1200)
    pg.get_by_role("button", name=re.compile("UPDATE \\d+ ENTRIES IN LORE")).click()
    pg.wait_for_selector("[role=dialog][aria-label='Update LORE preview']", timeout=10000)
    dlg = pg.locator("[role=dialog][aria-label='Update LORE preview']")
    pg.wait_for_timeout(600)
    ok("REFRESHED" in dlg.inner_text() and "Rikku" in dlg.inner_text(), "preview lists the refreshed entry")
    dlg.get_by_role("button", name=re.compile("Rikku")).first.click(); pg.wait_for_timeout(200)
    ok(dlg.locator("ins", has_text="changed").count() >= 1, "preview shows the before/after diff")
    pg.screenshot(path=OUT + "/resend_preview.png", full_page=True)
    dlg.get_by_label("Apply Rikku").uncheck()
    dlg.get_by_role("button", name=re.compile("APPLY")).click(); pg.wait_for_timeout(1200)
    lore = {e["title"]: e for e in requests.get(B + f"/api/lore/entries?project_id={lore_pid}").json()}
    ok("changed for the preview" not in (lore["Rikku"].get("content") or ""), "unticked entry left as it was")
    pg.get_by_role("button", name=re.compile("UPDATE \\d+ ENTRIES IN LORE")).click()
    pg.wait_for_selector("[role=dialog][aria-label='Update LORE preview']", timeout=10000); pg.wait_for_timeout(600)
    pg.locator("[role=dialog][aria-label='Update LORE preview']").get_by_role("button", name=re.compile("APPLY")).click(); pg.wait_for_timeout(1200)
    full = requests.get(B + f"/api/lore/entry/{lore['Rikku']['id']}").json()
    ok("changed for the preview" in str(full), "ticked entry refreshed")
    # LORE trim compare
    long = "Rikku knows every ruin and every shortcut through them. " * 30
    requests.patch(B + f"/api/lore/entry/{lore['Rikku']['id']}", json={**full.get("entry", full), "content": long},
                   headers={"Origin": "http://localhost:5173"})
    pg.get_by_role("button", name=re.compile(r"^\s*LORE\s*$", re.I)).first.click(); pg.wait_for_timeout(800)
    lname = next(p["project_name"] for p in requests.get(B + "/api/lore/projects").json() if p["id"] == lore_pid)
    pg.locator("div", has_text=re.compile("^" + re.escape(lname) + "$")).first.click(); pg.wait_for_timeout(600)
    pg.locator("div", has_text=re.compile(r"^Rikku$")).first.click(); pg.wait_for_timeout(600)
    pg.get_by_role("button", name=re.compile("TRIM TO ~150")).click()
    pg.wait_for_selector("[role=dialog][aria-label='Trim compare']", timeout=10000)
    ok("A trimmed entry that keeps the names." in pg.locator("[role=dialog][aria-label='Trim compare']").inner_text(), "trim shows the shorter version next to the original")
    pg.wait_for_timeout(700)
    pg.screenshot(path=OUT + "/lore_trim.png", full_page=True)
    pg.get_by_role("button", name="USE TRIMMED").click(); pg.wait_for_timeout(2500)
    full = requests.get(B + f"/api/lore/entry/{lore['Rikku']['id']}").json()
    ok("A trimmed entry that keeps the names." in str(full), "trimmed text accepted and autosaved")
    # CHARACTER: personality layers + interview
    pg.get_by_role("button", name=re.compile(r"^\s*CHARACTER\s*$", re.I)).first.click(); pg.wait_for_timeout(600)
    menu(pg, "NEW", "New Card"); pg.wait_for_timeout(1000)
    pg.locator("textarea").first.fill("Kel is a smith in a mountain town.")
    menu(pg, "TOOLS", "Interview"); pg.wait_for_timeout(300)
    ok(pg.locator("[role=dialog][aria-label=Interview]").count() == 1, "CHARACTER interview opens")
    pg.get_by_label("Question").fill("What do you make?"); pg.keyboard.press("Enter"); pg.wait_for_timeout(1000)
    ok(pg.locator("text=Ask quick, I have places to be.").count() == 1, "CHARACTER interview replies")
    pg.get_by_role("button", name="Close interview").click(); pg.wait_for_timeout(300)
    menu(pg, "TOOLS", "Audit"); pg.wait_for_timeout(1200)
    ok(pg.locator("text=/with strangers \\/ with people close to them/").count() >= 1, "audit suggests the personality layers")
    ok(not errs, f"no page errors {errs[:2]}")
    b.close()
print("FAILS:", R.count(False))
