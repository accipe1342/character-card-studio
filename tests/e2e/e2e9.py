"""v2.5 saved portraits: a card keeps its picture after a reload, the Library shows it, opening another card doesn't
show the wrong picture, and a TEXT character's picture follows MAKE CARD."""
import os
OUT = os.environ.get("E2E_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
os.makedirs(OUT, exist_ok=True)
import re, sys, requests
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
import png_card
from playwright.sync_api import sync_playwright
B = "http://127.0.0.1:5173"
R = []
def ok(c, n): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n)
pic = os.path.join(OUT, "portrait_test.png")
raw = png_card.placeholder("e2e portrait", 40, 60)
open(pic, "wb").write(raw)
import hashlib
PIC = hashlib.sha256(raw).hexdigest()[:20] + ".png"          # the name the app stores it under
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1600, "height": 1300}, accept_downloads=True)
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    pg.goto("http://localhost:5173/"); pg.wait_for_timeout(800)
    pg.get_by_role("button", name=re.compile(r"^\s*CHARACTER\s*$", re.I)).first.click(); pg.wait_for_timeout(500)
    pg.get_by_role("button", name=re.compile("New Card")).click(); pg.wait_for_timeout(1000)
    pg.locator("section").filter(has_text="Preview").locator("input[type=file]").first.set_input_files(pic)
    pg.wait_for_timeout(2000)
    cards = requests.get(B + "/api/cards").json()
    newest = next((c for c in cards if c.get("image") == PIC), {})
    ok(bool(newest), "uploaded portrait saved with the card")
    # another blank card: no picture
    pg.get_by_role("button", name=re.compile("New Card")).click(); pg.wait_for_timeout(1000)
    ok(pg.locator("text=No image uploaded yet").count() == 1, "a new card starts without the last picture")
    # reload, open the first card from the Library: its picture comes back
    pg.reload(); pg.wait_for_timeout(1000)
    pg.get_by_role("button", name=re.compile(r"^\s*LIBRARY\s*$")).first.click(); pg.wait_for_timeout(800)
    ok(pg.locator(f"img[src='/api/images/{newest['image']}']").count() >= 1, "Library shows the thumbnail")
    pg.locator(".signal-library-item").filter(has=pg.locator(f"img[src='/api/images/{newest['image']}']")).first.evaluate("e => e.click()")
    pg.wait_for_timeout(1200)
    shown = pg.locator("section").filter(has_text="Preview").locator("img").first.get_attribute("src") or ""
    ok(shown == f"/api/images/{newest['image']}", f"reopened card shows its saved portrait ({shown})")
    import io, json, zipfile
    with pg.expect_download() as dl:
        pg.get_by_role("button", name="CHARX", exact=True).click()
    z = zipfile.ZipFile(dl.value.path())
    v3 = json.loads(z.read("card.json"))
    ok(dl.value.suggested_filename.endswith(".charx") and z.read("assets/icon/images/main.png") == raw
       and v3["data"]["assets"][0]["uri"] == "embeded://assets/icon/images/main.png", "CHARX download holds the card and its portrait")
    # opening a card without a picture clears it
    plain = next((c for c in cards if not c.get("image")), None)
    if plain:
        pg.get_by_role("button", name=re.compile(r"^\s*LIBRARY\s*$")).first.click(); pg.wait_for_timeout(600)
        pg.locator(".signal-library-item").filter(has_text=plain["name"] or "Unnamed").first.evaluate("e => e.click()"); pg.wait_for_timeout(1000)
        ok(pg.locator("text=No image uploaded yet").count() == 1, "a card without a portrait doesn't show the previous one")
    pg.screenshot(path=OUT + "/portrait_card.png", full_page=True)
    # TEXT: picture on a character, then MAKE CARD
    texts = requests.get(B + "/api/text/projects").json()
    texts = texts if isinstance(texts, list) else texts["projects"]
    proj = next(p for p in texts if p.get("lore_project_id"))
    pg.get_by_role("button", name=re.compile(r"^\s*TEXT\s*$", re.I)).first.click(); pg.wait_for_timeout(600)
    pg.locator("div", has_text=re.compile("^" + re.escape(proj["name"]) + r"\s*[\d.]+k? chars")).last.click(); pg.wait_for_timeout(1200)
    pg.locator("section").filter(has_text="REVIEW").locator("div", has_text=re.compile(r"^Rikku$")).first.click(); pg.wait_for_timeout(500)
    pg.get_by_label("Character picture").set_input_files(pic); pg.wait_for_timeout(1500)
    ok(pg.locator("img[alt=Portrait]").count() == 1, "TEXT character shows its picture")
    E = {e["name"]: e for e in requests.get(B + f"/api/text/project/{proj['id']}").json()["entities"]}
    ok(bool(E["Rikku"].get("image")), "TEXT picture saved")
    mk = pg.get_by_role("button", name=re.compile(r"MAKE CARD")).first
    mk.scroll_into_view_if_needed(); mk.evaluate("b => b.click()"); pg.wait_for_timeout(2000)
    shown = pg.locator("section").filter(has_text="Preview").locator("img").first.get_attribute("src") or ""
    ok(shown == f"/api/images/{E['Rikku']['image']}", "MAKE CARD brings the picture to the CHARACTER studio")
    ok(not errs, f"no page errors {errs[:2]}")
    b.close()
print("FAILS:", R.count(False))
