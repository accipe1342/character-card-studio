import os
OUT = os.environ.get("E2E_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
os.makedirs(OUT, exist_ok=True)
import re, json, requests
from playwright.sync_api import sync_playwright
B = "http://127.0.0.1:5173"
R = []
def ok(c, n): R.append(c); print(("PASS " if c else "FAIL ") + n)
H = {"Content-Type": "application/json", "Origin": "http://localhost:5173"}
p = requests.post(B + "/api/lore/projects", json={"name": "Spira Lore"}, headers=H).json()
pid = p["id"]
for t_, kw in (("Paine", ["Paine"]), ("Mascot dress sphere", ["Mascot dress sphere", "spell", "Paine"]), ("Empty one", [])):
    e = requests.post(B + "/api/lore/entry/new", json={"project_id": pid, "title": t_}, headers=H).json()
    requests.patch(B + f"/api/lore/entry/{e['id']}", json={"title": t_, "keywords": kw, "content": "Some content here." if kw else "", "entry_type": "concept"}, headers=H)
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1600, "height": 1200})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto("http://localhost:5173/"); pg.wait_for_timeout(800)
    pg.get_by_role("button", name=re.compile(r"^\s*LORE\s*$", re.I)).first.click(); pg.wait_for_timeout(600)
    pg.locator("div", has_text=re.compile(r"^Spira Lore$")).first.click(); pg.wait_for_timeout(700)
    ok(pg.locator("span", has_text=re.compile(r"^NO KEYS$")).count() == 1 and pg.locator("span", has_text=re.compile(r"^EMPTY$")).count() == 1, "LORE list problem badges")
    pg.locator("div", has_text=re.compile(r"^Paine$")).first.click(); pg.wait_for_timeout(500)
    pg.get_by_role("button", name=re.compile(r"^character$", re.I)).last.click()
    pg.locator("textarea").last.fill("Paine is a stoic warrior.")
    pg.wait_for_timeout(2000)
    ok(pg.locator("text=✓ saved").count() >= 1, "LORE autosave indicator")
    eid = [e for e in requests.get(B + f"/api/lore/entries?project_id={pid}").json() if e["title"] == "Paine"][0]["id"]
    full = requests.get(B + f"/api/lore/entry/{eid}").json()
    ok(full["content"] == "Paine is a stoic warrior." and full["entry_type"] == "character", "LORE autosave + type change persisted")
    pg.get_by_role("button", name=re.compile("Clean Keywords")).click(); pg.wait_for_timeout(1200)
    m = [e for e in requests.get(B + f"/api/lore/entries?project_id={pid}").json() if e["title"] == "Mascot dress sphere"][0]
    ok(m["keywords"] == ["Mascot dress sphere"], f"Clean Keywords applied: {m['keywords']}")
    pg.get_by_role("button", name=re.compile("Trash all entries")).click(); pg.wait_for_timeout(800)
    ok(any(x["id"] == pid for x in requests.get(B + "/api/lore/projects").json()), "Trash all entries keeps the project id")
    # CHARACTER autosave
    pg.get_by_role("button", name=re.compile(r"^\s*CHARACTER\s*$", re.I)).first.click(); pg.wait_for_timeout(600)
    pg.get_by_role("button", name=re.compile("New Card")).click(); pg.wait_for_timeout(1000)
    ta = pg.locator("textarea").first
    ta.fill("A brand new description typed by hand.")
    pg.wait_for_timeout(2400)
    cards = requests.get(B + "/api/cards").json()
    newest = max(cards, key=lambda c: c["id"])
    full = requests.get(B + f"/api/card/{newest['id']}").json()
    card = full.get("card", full)
    ok("brand new description" in json.dumps(card), "CHARACTER autosave persisted")
    ok(pg.locator("text=✓ saved").count() >= 1, "CHARACTER saved indicator")
    pg.screenshot(path=OUT + "/character2.png")
    ok(not errs, f"no page errors {errs[:2]}")
    b.close()
print("FAILS:", R.count(False))
