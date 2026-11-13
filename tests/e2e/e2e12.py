"""2.6 layout: NieR-style header with what is open, the SCRIBE-01 console (hide to a bar, Ctrl+/, float, drag,
resize, dock), toolbar menus (Escape closes), LORE entry tabs, importing a card PNG and a card JSON with a lorebook,
and no sideways scrolling on a phone."""
import json
import os
import re
import sys
import tempfile

import requests
from playwright.sync_api import sync_playwright
from ui import menu, open_menu

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
import png_card  # noqa: E402
from preview import build_export_card_json, character_book_from_items, normalise_lore_items  # noqa: E402

OUT = os.environ.get("E2E_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
os.makedirs(OUT, exist_ok=True)
B = "http://127.0.0.1:5173"
R = []
def ok(c, n): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n)

tmp = tempfile.mkdtemp()
card = {"name": "Ines Varga", "description": "A harbor clerk who stamps every crate.", "personality": "Precise.",
        "scenario": "The customs house.", "first_mes": "Next.", "tags": ["clerk"], "structured_profile": {"likes": ["order"]}}
png_path = os.path.join(tmp, "ines.png")
open(png_path, "wb").write(png_card.embed(png_card.placeholder("Ines"), build_export_card_json(card)))
v2 = build_export_card_json({**card, "name": "Oskar Brandt", "description": "A ferryman."})
v2["data"]["character_book"] = character_book_from_items("Ferry Lines", normalise_lore_items([
    {"title": "North Ferry", "entry_type": "place", "keys": ["north ferry"], "content": "Runs at dawn."},
    {"title": "Toll Book", "entry_type": "item", "keys": ["toll book"], "content": "Every fare, written down."}]))
json_path = os.path.join(tmp, "oskar.json")
open(json_path, "w").write(json.dumps(v2))

with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1440, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://localhost:5173/"); pg.wait_for_timeout(800)
    pg.evaluate("() => { try { ['ccs.helper.open','ccs.helper.mode','ccs.helper.pos','ccs.helper.h'].forEach(k => localStorage.removeItem(k)); } catch (e) {} }")
    pg.reload(); pg.wait_for_timeout(1000)
    pg.get_by_role("button", name=re.compile(r"^\s*CHARACTER\s*$")).first.click(); pg.wait_for_timeout(500)
    ok(pg.locator("h1.nier-title").inner_text().strip() == "CHARACTER", "NieR header shows the studio name")

    # import a card PNG
    with pg.expect_file_chooser() as fc:
        menu(pg, "NEW", "Import card")
    fc.value.set_files(png_path); pg.wait_for_timeout(1500)
    vals = pg.eval_on_selector_all("input, textarea", "els => els.map(e => e.value)")
    ok("Ines Varga" in vals and "A harbor clerk who stamps every crate." in vals, "imported PNG card opens in the editor")
    ok("ines varga" in pg.locator(".nier-ctx").first.inner_text().lower(), "the header names the open card")
    ok(pg.locator("img[src^='/api/images/']").count() >= 1, "the PNG became the portrait")
    # import a JSON card with a lorebook
    with pg.expect_file_chooser() as fc:
        menu(pg, "NEW", "Import card")
    fc.value.set_files(json_path); pg.wait_for_timeout(1500)
    vals = pg.eval_on_selector_all("input, textarea", "els => els.map(e => e.value)")
    ok("Oskar Brandt" in vals, "imported JSON card opens")
    proj = next((p for p in requests.get(B + "/api/lore/projects").json() if p["project_name"] == "Ferry Lines"), None)
    ok(proj and proj["entry_count"] == 2, "its lorebook became a LORE project")
    m = open_menu(pg, "EXPORT")
    ok(pg.get_by_label("Embedded lorebook").input_value() == str(proj["id"]), "and is attached to the card for export")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    ok(not m.is_visible(), "Escape closes a menu")

    # the console: hidden bar, Ctrl+/, float, drag, dock
    bar = pg.get_by_role("button", name="Open the helper")
    ok(bar.count() == 1 and "SCRIBE-01" in bar.inner_text(), "SCRIBE-01 waits as a bar at the bottom")
    pg.keyboard.press("Control+/"); pg.wait_for_timeout(400)
    panel = pg.locator("aside[aria-label=Helper]")
    ok(panel.count() == 1, "Ctrl+/ opens the console")
    box = panel.bounding_box()
    ok(box["y"] + box["height"] > 880 and box["width"] > 1300, f"docked along the bottom ({box})")
    pad = pg.evaluate("parseInt(getComputedStyle(document.body).paddingBottom)")
    ok(pad >= box["height"], "the page leaves room so nothing hides under it")
    edge = panel.locator("[title='Drag to resize']").first.bounding_box()
    pg.mouse.move(edge["x"] + edge["width"] / 2, edge["y"] + 3); pg.mouse.down(); pg.mouse.move(edge["x"] + edge["width"] / 2, edge["y"] - 100); pg.mouse.up()
    pg.wait_for_timeout(200)
    ok(panel.bounding_box()["height"] > box["height"] + 60, "dragging the top edge makes it taller")
    panel.get_by_role("button", name="Float as a window").click(); pg.wait_for_timeout(300)
    fb = panel.bounding_box()
    ok(fb["width"] < 900, f"FLOAT turns it into a window ({fb})")
    head = panel.locator("div").nth(0)
    hx, hy = fb["x"] + 300, fb["y"] + 12
    pg.mouse.move(hx, hy); pg.mouse.down(); pg.mouse.move(hx - 400, hy - 200, steps=5); pg.mouse.up(); pg.wait_for_timeout(200)
    nb = panel.bounding_box()
    ok(nb["x"] < fb["x"] - 300 and nb["y"] < fb["y"] - 150, f"the window can be dragged ({nb})")
    pg.screenshot(path=OUT + "/console_float.png")
    pg.reload(); pg.wait_for_timeout(1200)
    rb = pg.locator("aside[aria-label=Helper]").bounding_box()
    ok(rb and abs(rb["x"] - nb["x"]) < 4, "it stays where you left it after a reload")
    pg.locator("aside[aria-label=Helper]").get_by_role("button", name="Dock at the bottom").click(); pg.wait_for_timeout(300)
    pg.locator("aside[aria-label=Helper]").get_by_role("button", name="Close the helper").click(); pg.wait_for_timeout(300)
    pg.locator("footer button", has_text="SCRIBE-01").click(); pg.wait_for_timeout(300)
    ok(pg.locator("aside[aria-label=Helper]").count() == 1, "the footer hint opens it too")
    pg.keyboard.press("Control+/"); pg.wait_for_timeout(300)

    # LORE: tabs in the entry editor
    pg.get_by_role("button", name=re.compile(r"^\s*LORE\s*$")).first.click(); pg.wait_for_timeout(700)
    pg.locator("div", has_text=re.compile(r"^Ferry Lines$")).first.click(); pg.wait_for_timeout(600)
    pg.locator("div", has_text=re.compile(r"^North Ferry$")).first.click(); pg.wait_for_timeout(700)
    ok(pg.get_by_role("tab", name="CONTENT").get_attribute("aria-selected") == "true", "an entry opens on the CONTENT tab")
    ok(pg.get_by_role("tab", name=re.compile(r"KEYS · 1")).count() == 1, "the KEYS tab shows how many keys there are")
    pg.get_by_role("tab", name=re.compile("KEYS")).click(); pg.wait_for_timeout(200)
    ok(pg.locator("text=north ferry").first.is_visible(), "KEYS shows the keywords")
    pg.screenshot(path=OUT + "/lore_nier.png")

    # phone width: nothing scrolls sideways
    pg.set_viewport_size({"width": 390, "height": 800}); pg.wait_for_timeout(600)
    sw = pg.evaluate("document.documentElement.scrollWidth")
    ok(sw <= 392, f"no sideways scrolling on a phone ({sw}px)")
    ok(not errs, f"no page errors {errs[:2]}")
    b.close()
print("FAILS:", R.count(False))
