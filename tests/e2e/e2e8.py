"""v2.5 phase 3 in the browser, against a REAL SillyTavern with basic auth (skipped if none is running):
Config → SillyTavern (test + save), card push from CHARACTER, lorebook push + Quick Replies from LORE and TEXT.
Start one with listen: true, basicAuthMode: true, user tester / pw-123 on port 8123, or set ST_TEST_URL etc."""
import os
OUT = os.environ.get("E2E_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
os.makedirs(OUT, exist_ok=True)
import re, requests
from playwright.sync_api import sync_playwright
from ui import menu, open_menu
B = "http://127.0.0.1:5173"
ST = os.getenv("ST_TEST_URL", "http://127.0.0.1:8123")
USER, PW = os.getenv("ST_TEST_USER", "tester"), os.getenv("ST_TEST_PASSWORD", "pw-123")
R = []
def ok(c, n): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n)
try:
    up = requests.get(ST + "/version", timeout=2).status_code in (200, 401)
except Exception:
    up = False
if not up:
    print("SKIP no SillyTavern at " + ST); print("FAILS: 0"); raise SystemExit(0)
st = requests.Session(); st.auth = (USER, PW)
st.headers["X-CSRF-Token"] = st.get(ST + "/csrf-token").json()["token"]
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1600, "height": 1300}, accept_downloads=True)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    pg.goto("http://localhost:5173/"); pg.wait_for_timeout(800)
    # Config: wrong password first, then the right one, then save
    pg.get_by_role("button", name=re.compile(r"^\s*CONFIG\s*$", re.I)).first.click(); pg.wait_for_timeout(600)
    pg.get_by_label("SillyTavern address").fill(ST)
    pg.get_by_label("User name (basic auth)").fill(USER)
    pg.get_by_label("Password (basic auth)").fill("wrong")
    pg.get_by_role("button", name="TEST CONNECTION").click(); pg.wait_for_timeout(1500)
    ok("user name and password" in pg.get_by_role("status").first.inner_text(), "wrong password explained in plain words")
    pg.get_by_label("Password (basic auth)").fill(PW)
    pg.get_by_role("button", name="TEST CONNECTION").click(); pg.wait_for_timeout(1500)
    ok("Connected to SillyTavern 1." in pg.get_by_role("status").first.inner_text(), "test connection reaches SillyTavern")
    pg.screenshot(path=OUT + "/config_st.png", full_page=True)
    pg.get_by_role("button", name="SAVE", exact=True).click(); pg.wait_for_timeout(800)
    env = requests.get(B + "/api/config/env").json()
    ok(env.get("ST_URL") == ST and env.get("ST_PASSWORD", "").startswith("•") and PW not in str(env), "saved; password comes back masked")
    # LORE: send the lorebook, then the Quick Replies
    lp = next(p for p in requests.get(B + "/api/lore/projects").json() if (p.get("entry_count") or 0) > 0 or True)
    pg.get_by_role("button", name=re.compile(r"^\s*LORE\s*$", re.I)).first.click(); pg.wait_for_timeout(800)
    pg.locator("div", has_text=re.compile("^" + re.escape(lp["project_name"]) + "$")).first.click(); pg.wait_for_timeout(800)
    menu(pg, "EXPORT", "Send to SillyTavern"); pg.wait_for_timeout(1500)
    wi = st.post(ST + "/api/worldinfo/get", json={"name": lp["project_name"]}).json()
    ok(len(wi.get("entries") or {}) > 0, "lorebook arrived in SillyTavern's World Info")
    menu(pg, "EXPORT", "Quick Replies")
    pg.wait_for_selector("[role=dialog][aria-label='Quick Replies']", timeout=10000); pg.wait_for_timeout(500)
    dlg = pg.locator("[role=dialog][aria-label='Quick Replies']")
    ok("Recap" in dlg.inner_text(), "Quick Reply preview lists the buttons")
    with pg.expect_download() as dl:
        dlg.get_by_role("button", name=re.compile("DOWNLOAD")).click()
    import json
    qrs = json.load(open(dl.value.path()))
    ok(qrs["version"] == 2 and qrs["qrList"], "Quick Reply .json downloads in SillyTavern's format")
    dlg.get_by_role("button", name=re.compile("SEND TO SILLYTAVERN")).click(); pg.wait_for_timeout(1500)
    sets = st.post(ST + "/api/settings/get", json={}).json().get("quickReplyPresets") or []
    ok(any(x.get("name") == qrs["name"] for x in sets), "Quick Reply set saved in SillyTavern")
    pg.screenshot(path=OUT + "/lore_qr.png", full_page=True)
    dlg.get_by_role("button", name="CLOSE").click(); pg.wait_for_timeout(300)
    # CHARACTER: new card, name it, send twice (the second replaces the first)
    pg.get_by_role("button", name=re.compile(r"^\s*CHARACTER\s*$", re.I)).first.click(); pg.wait_for_timeout(600)
    menu(pg, "NEW", "New Card"); pg.wait_for_timeout(1000)
    before = len(st.post(ST + "/api/characters/all", json={}).json())
    name_box = pg.get_by_label(re.compile("^Name$", re.I)).first
    if name_box.count():
        name_box.fill("Pushed Courier")
    pg.locator("textarea").first.fill("A courier who knows every alley.")
    pg.wait_for_timeout(800)
    pg.get_by_role("button", name=re.compile("SEND TO SILLYTAVERN")).click(); pg.wait_for_timeout(2500)
    status = pg.get_by_role("status").last.inner_text()
    ok("Sent to SillyTavern as" in status, f"card sent ({status[:80]})")
    pg.get_by_role("button", name=re.compile("SEND TO SILLYTAVERN")).click(); pg.wait_for_timeout(2500)
    after = len(st.post(ST + "/api/characters/all", json={}).json())
    ok(after == before + 1, f"second send replaced the card ({before} -> {after})")
    pg.screenshot(path=OUT + "/card_st.png", full_page=True)
    ok(not errs, f"no page errors {errs[:2]}")
    b.close()
print("FAILS:", R.count(False))
