"""Batch 2 in the browser: budget meter, advanced ST settings, activation test, links, trash + keyboard, V3 export."""
import os
OUT = os.environ.get("E2E_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
os.makedirs(OUT, exist_ok=True)
import re, json, requests
from playwright.sync_api import sync_playwright
B = "http://127.0.0.1:5173"
R = []
def ok(c, n): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n)
H = {"Content-Type": "application/json", "Origin": "http://localhost:5173"}
pid = requests.post(B + "/api/lore/projects", json={"name": "Besaid Lore"}, headers=H).json()["id"]
ids = {}
for t_, kw, body, et in (("Wakka", ["Wakka"], "Wakka captains the Besaid Aurochs and fears machina.", "character"),
                         ("Besaid Aurochs", ["Aurochs"], "A blitzball team that always loses.", "faction"),
                         ("Story So Far", [], "Long recap. " * 40, "concept"),
                         ("Lonely rock", ["rock"], "Just a rock.", "item")):
    e = requests.post(B + "/api/lore/entry/new", json={"project_id": pid, "title": t_}, headers=H).json()
    requests.patch(B + f"/api/lore/entry/{e['id']}", json={"title": t_, "keywords": kw, "content": body, "entry_type": et}, headers=H)
    ids[t_] = e["id"]
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1600, "height": 1300}, accept_downloads=True)
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto("http://localhost:5173/"); pg.wait_for_timeout(800)
    pg.get_by_role("button", name=re.compile(r"^\s*LORE\s*$", re.I)).first.click(); pg.wait_for_timeout(600)
    pg.locator("div", has_text=re.compile(r"^Besaid Lore$")).first.click(); pg.wait_for_timeout(700)
    ok(pg.locator("text=/ALWAYS ON 1 ·/").count() == 1, "budget meter counts the always-on recap")
    # advanced settings
    pg.locator("div", has_text=re.compile(r"^Wakka$")).first.click(); pg.wait_for_timeout(500)
    pg.get_by_role("button", name=re.compile("ADVANCED SILLYTAVERN SETTINGS")).click()
    pg.locator("label", has_text="POSITION").locator("select").select_option("4")
    pg.locator("label", has_text="ROLE (AT DEPTH)").locator("select").select_option("2")
    pg.locator("label", has_text="STICKY").locator("input").fill("3")
    sec = pg.locator("label", has_text="SECONDARY KEYS").locator("input")
    sec.fill("blitzball, machina"); sec.blur()
    pg.locator("label", has_text="INCLUSION GROUP").locator("input").fill("besaid")
    pg.wait_for_timeout(2200)
    full = requests.get(B + f"/api/lore/entry/{ids['Wakka']}").json()
    ok((full["position"], full["role"], full["sticky"], full["group_name"]) == (4, 2, 3, "besaid")
       and full["secondary_keys"] == ["blitzball", "machina"], f"advanced settings autosaved {full['position'], full['role'], full['sticky'], full['secondary_keys']}")
    ex = requests.get(B + f"/api/lore/export?project_id={pid}").json()
    w = [e for e in ex["entries"].values() if e["comment"].startswith("Wakka")][0]
    ok(w["position"] == 4 and w["role"] == 2 and w["keysecondary"] == ["blitzball", "machina"] and w["selective"], "exported to ST JSON")
    # activation test
    pg.get_by_role("button", name=re.compile("Test Activation")).click(); pg.wait_for_timeout(300)
    pg.get_by_label("Chat text to test").fill("Wakka grumbles about blitzball and the Aurochs.")
    pg.get_by_role("button", name=re.compile("RUN TEST")).click(); pg.wait_for_timeout(800)
    sim = pg.locator("section[aria-label='Activation test']").inner_text()
    ok("3 inserted" in sim and "constant" in sim and "key 'Wakka'" in sim and "Lonely rock" not in sim, "activation test result")
    pg.get_by_role("button", name="Close activation test").click()
    # links
    pg.get_by_role("button", name=re.compile(r"Links")).click(); pg.wait_for_timeout(800)
    links = pg.locator("section[aria-label='Entry links']").inner_text()
    ok("Besaid Aurochs" in links and "Lonely rock" in links, "links panel: Wakka -> Aurochs, rock unlinked")
    pg.get_by_role("button", name="Close links").click()
    # keyboard: J moves, X X deletes, U restores
    pg.locator("body").click(position={"x": 5, "y": 5}); pg.wait_for_timeout(200)
    sel_before = pg.locator("input").filter(has_text="").nth(0)
    pg.keyboard.press("k"); pg.wait_for_timeout(500)
    title_now = pg.locator("section.signal-screen-panel input").first.input_value()
    ok(title_now and title_now != "Wakka", f"K selects the previous entry ({title_now})")
    pg.keyboard.press("x"); pg.keyboard.press("x"); pg.wait_for_timeout(900)
    left = [e["title"] for e in requests.get(B + f"/api/lore/entries?project_id={pid}").json()]
    ok(title_now not in left and len(left) == 3, f"X X moves it to the trash ({left})")
    pg.keyboard.press("u"); pg.wait_for_timeout(900)
    left = [e["title"] for e in requests.get(B + f"/api/lore/entries?project_id={pid}").json()]
    ok(title_now in left, "U restores it")
    # trash panel
    requests.delete(B + f"/api/lore/entry/{ids['Lonely rock']}", headers=H)
    pg.get_by_role("button", name=re.compile(r"Trash")).first.click(); pg.wait_for_timeout(700)
    tr = pg.locator("section[aria-label='Trash']")
    ok("Lonely rock" in tr.inner_text(), "trash lists the deleted entry")
    tr.get_by_role("button", name="RESTORE").click(); pg.wait_for_timeout(800)
    ok(any(e["title"] == "Lonely rock" for e in requests.get(B + f"/api/lore/entries?project_id={pid}").json()), "restored from the trash panel")
    pg.screenshot(path=OUT + "/lore_tools.png", full_page=True)
    # CHARACTER: V3 JSON export
    pg.get_by_role("button", name=re.compile(r"^\s*CHARACTER\s*$", re.I)).first.click(); pg.wait_for_timeout(600)
    pg.get_by_role("button", name=re.compile("New Card")).click(); pg.wait_for_timeout(1000)
    with pg.expect_download() as dl:
        pg.get_by_role("button", name=re.compile(r"^V3 JSON$")).click()
    data = json.loads(open(dl.value.path()).read())
    ok(data["spec"] == "chara_card_v3" and dl.value.suggested_filename.endswith("_v3.json"), "V3 JSON export")
    ok(not errs, f"no page errors {errs[:2]}")
    b.close()
print("FAILS:", R.count(False))
