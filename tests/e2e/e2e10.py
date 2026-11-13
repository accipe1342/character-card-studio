"""v2.5 last features in the browser: relationship map, story bible / Data Bank downloads, secrets (who knows this)."""
import os
OUT = os.environ.get("E2E_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
os.makedirs(OUT, exist_ok=True)
import io, json, re, zipfile, requests
from playwright.sync_api import sync_playwright
B = "http://127.0.0.1:5173"
R = []
def ok(c, n): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n)
texts = requests.get(B + "/api/text/projects").json()
texts = texts if isinstance(texts, list) else texts["projects"]
proj = next(p for p in texts if p.get("lore_project_id"))
pid = proj["id"]
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1600, "height": 1300}, accept_downloads=True)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    pg.goto("http://localhost:5173/"); pg.wait_for_timeout(800)
    pg.get_by_role("button", name=re.compile(r"^\s*TEXT\s*$", re.I)).first.click(); pg.wait_for_timeout(600)
    pg.locator("div", has_text=re.compile("^" + re.escape(proj["name"]) + r"\s*[\d.]+k? chars")).last.click(); pg.wait_for_timeout(1200)
    review = pg.locator("section").filter(has_text="REVIEW")
    # relationship map
    pg.get_by_role("button", name=re.compile("RELATIONSHIP MAP")).click()
    pg.wait_for_selector("[role=dialog][aria-label='Relationship map'] svg", timeout=10000); pg.wait_for_timeout(500)
    dlg = pg.locator("[role=dialog][aria-label='Relationship map']")
    ok(dlg.locator("[data-node='Corin']").count() == 1 and dlg.locator("[data-node='Ilsa']").count() == 1, "map draws the linked characters")
    dlg.locator("[data-node='Corin']").click(); pg.wait_for_timeout(300)
    ok("Corin → cousin" in dlg.inner_text(), "clicking a node lists its relations")
    box = dlg.locator("[data-node='Ilsa']").bounding_box()
    pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + 5); pg.mouse.down(); pg.mouse.move(box["x"] + 140, box["y"] + 90, steps=6); pg.mouse.up()
    box2 = dlg.locator("[data-node='Ilsa']").bounding_box()
    ok(abs(box2["x"] - box["x"]) > 50, "nodes can be dragged")
    with pg.expect_download() as dl:
        dlg.get_by_role("button", name=re.compile("SVG")).click()
    svg = open(dl.value.path(), encoding="utf-8").read()
    ok(svg.startswith("<?xml") and "Corin" in svg and "var(--" not in svg, "map downloads as a standalone SVG")
    pg.screenshot(path=OUT + "/relationship_map.png", full_page=True)
    dlg.get_by_role("button", name="OPEN IN REVIEW").click(); pg.wait_for_timeout(600)
    ok(pg.locator("[role=dialog][aria-label='Relationship map']").count() == 0, "OPEN IN REVIEW closes the map")
    # secrets on Corin (opened by the map)
    pg.get_by_role("button", name=re.compile("SECRETS · WHO KNOWS THIS")).click(); pg.wait_for_timeout(200)
    pg.get_by_role("button", name="+ ADD A SECRET").click()
    pg.get_by_label("Secret 1", exact=True).fill("She rigged the airship engine herself.")
    pg.get_by_label("Who knows secret 1").select_option("Ilsa"); pg.wait_for_timeout(1200)
    E = {e["name"]: e for e in requests.get(B + f"/api/text/project/{pid}").json()["entities"]}
    ok(E["Corin"].get("secrets") == [{"text": "She rigged the airship engine herself.", "known_by": ["Ilsa"]}], "secret saved with who knows it")
    pg.screenshot(path=OUT + "/secrets.png", full_page=True)
    # it goes to LORE as its own filtered entry (the update preview shows it as new)
    pg.get_by_role("button", name=re.compile("UPDATE \\d+ ENTRIES IN LORE")).click()
    pg.wait_for_selector("[role=dialog][aria-label='Update LORE preview']", timeout=10000); pg.wait_for_timeout(600)
    d2 = pg.locator("[role=dialog][aria-label='Update LORE preview']")
    ok("Corin — secret 1" in d2.inner_text(), "the secret shows up as a new LORE entry")
    d2.get_by_role("button", name=re.compile("APPLY")).click(); pg.wait_for_timeout(1500)
    wi = requests.get(B + f"/api/lore/export?project_id={proj['lore_project_id']}").json()
    entries = wi.get("entries", {}).values() if isinstance(wi, dict) else []
    sec = [e for e in entries if "airship engine" in e.get("content", "")]
    ok(len(sec) == 1 and sec[0]["characterFilter"]["names"] == ["Ilsa"], "World Info export carries the character filter")
    # story bible + Data Bank
    pg.get_by_role("button", name=re.compile(r"STORY BIBLE \/ DATA BANK")).click()
    pg.wait_for_selector("[role=dialog][aria-label='Story exports']", timeout=10000)
    d3 = pg.locator("[role=dialog][aria-label='Story exports']")
    with pg.expect_download() as dl:
        d3.get_by_role("link", name=re.compile("MARKDOWN")).click()
    md = open(dl.value.path(), encoding="utf-8").read()
    ok(md.startswith("# " + proj["name"]) and "## Characters" in md and "## Secrets" in md, "bible downloads as Markdown, with secrets for the author")
    with pg.expect_download() as dl:
        d3.get_by_role("link", name=re.compile("DATA BANK")).click()
    z = zipfile.ZipFile(dl.value.path())
    ok("README.txt" in z.namelist() and any(n.startswith("characters/") for n in z.namelist())
       and not any("airship engine" in z.read(n).decode() for n in z.namelist()), "Data Bank zip: notes per entry, no secrets")
    with pg.expect_popup() as pop:
        d3.get_by_role("link", name="PRINTABLE PAGE").click()
    page2 = pop.value; page2.wait_for_load_state()
    ok("Story bible" in page2.inner_text("body") and page2.locator("button", has_text="PRINT").count() == 1, "printable bible opens in a new tab")
    page2.screenshot(path=OUT + "/bible.png", full_page=True); page2.close()
    ok(not errs, f"no page errors {errs[:2]}")
    b.close()
print("FAILS:", R.count(False))
