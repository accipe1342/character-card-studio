"""The helper side panel (SCRIBE-01) in the browser: open it, edit the open card, undo, build a lorebook, open an
entry from a change card, edit the selected entry, undo-all, the "changed since" refusal, and it survives a reload."""
import os
OUT = os.environ.get("E2E_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
os.makedirs(OUT, exist_ok=True)
import re, requests
from playwright.sync_api import sync_playwright
B = "http://127.0.0.1:5173"
R = []
def ok(c, n): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n)
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1600, "height": 1200})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    pg.goto("http://localhost:5173/"); pg.wait_for_timeout(800)
    pg.evaluate("() => { try { localStorage.removeItem('ccs.helper.open'); localStorage.removeItem('ccs.helper.chat'); } catch (e) {} }")
    pg.reload(); pg.wait_for_timeout(800)
    pg.get_by_role("button", name=re.compile(r"^\s*CHARACTER\s*$", re.I)).first.click(); pg.wait_for_timeout(400)
    pg.get_by_role("button", name=re.compile("New Card")).click(); pg.wait_for_timeout(1000)
    desc = pg.locator("textarea:not([aria-label='Message to the helper'])").first                        # the card editor, not the helper's message box
    desc.fill("Old description."); pg.wait_for_timeout(300)        # not autosaved yet: the panel must save it first
    pg.get_by_role("button", name="Open the helper").click(); pg.wait_for_timeout(300)
    panel = pg.locator("aside[aria-label=Helper]")
    ok(panel.count() == 1 and "SCRIBE-01" in panel.inner_text() and "CHARACTER" in panel.inner_text(), "panel opens with the studio context")
    ok(panel.get_by_role("button", name="Tighten this card's description").count() == 1, "starter suggestions for this studio")
    # 1. edit the open card's description
    panel.get_by_label("Message to the helper").fill("Rewrite the description please")
    panel.get_by_role("button", name="SEND").click()
    pg.wait_for_selector("text=Report: description rewritten.", timeout=15000); pg.wait_for_timeout(800)
    ok(panel.locator("text=/: description$/").count() == 1, "the change is listed with KEEP / UNDO")
    ok(desc.input_value() == "A courier who knows every alley of the rainy port.", f"the open card reloaded ({desc.input_value()[:40]})")
    pg.screenshot(path=OUT + "/helper_card.png", full_page=False)
    panel.get_by_role("button", name="UNDO").first.click(); pg.wait_for_timeout(1200)
    ok(desc.input_value() == "Old description.", "UNDO put back the description the user had (saved before the helper read it)")
    ok(panel.locator("text=↶ undone").count() == 1, "the change shows as undone")
    # 2. the "changed since" refusal
    panel.get_by_label("Message to the helper").fill("Rewrite the description again")
    panel.get_by_role("button", name="SEND").click()
    pg.wait_for_selector("text=Report: description rewritten. >> nth=1", timeout=15000); pg.wait_for_timeout(800)
    desc.fill("My own text after the helper."); pg.wait_for_timeout(2500)   # autosaved
    panel.get_by_role("button", name="UNDO").first.click(); pg.wait_for_timeout(1000)
    ok(panel.locator("text=/overwrite newer work/").count() == 1 and desc.input_value() == "My own text after the helper.",
       "UNDO refuses when the card was edited since, and nothing is lost")
    # 3. a lorebook with entries, OPEN an entry in LORE
    panel.get_by_label("Message to the helper").fill("Make a lorebook for this card's world")
    panel.get_by_role("button", name="SEND").click()
    pg.wait_for_selector("text=Report: lorebook ready with 2 entries.", timeout=15000); pg.wait_for_timeout(500)
    labels = panel.inner_text()
    ok("New lorebook: Helper Port" in labels and "New entry: Old Harbor" in labels and "New entry: Grey Watch" in labels,
       "lorebook and both entries listed")
    ok(panel.get_by_role("button", name="UNDO ALL").count() == 1, "UNDO ALL / KEEP ALL for a multi-change reply")
    proj = next(p for p in requests.get(B + "/api/lore/projects").json() if p["project_name"] == "Helper Port")
    ok(proj["entry_count"] == 2, "saved on the server")
    pg.screenshot(path=OUT + "/helper_lorebook.png", full_page=False)
    panel.get_by_role("group", name="Change: New entry: Old Harbor").get_by_role("button", name="OPEN").click()
    pg.wait_for_timeout(1500)
    vals = pg.eval_on_selector_all("textarea:not([aria-label='Message to the helper']), input", "els => els.map(e => e.value)")
    ok("Old Harbor" in vals and "Docks that never sleep." in vals, f"OPEN shows the entry in the LORE editor")
    panel = pg.locator("aside[aria-label=Helper]")
    ok("LORE" in panel.inner_text() and "Old Harbor" in panel.inner_text(), "the panel follows to LORE with the entry as context")
    # 4. edit the selected entry; the editor reloads
    panel.get_by_label("Message to the helper").fill("Tighten this entry")
    panel.get_by_role("button", name="SEND").click()
    pg.wait_for_selector("text=Report: entry tightened.", timeout=15000); pg.wait_for_timeout(1000)
    vals = pg.eval_on_selector_all("textarea:not([aria-label='Message to the helper'])", "els => els.map(e => e.value)")
    ok("Docks. Busy all night." in vals, "the open entry reloaded in the LORE editor")
    # 5. undo all of the lorebook (entries first, then the lorebook)
    panel.get_by_role("button", name="UNDO").last.click(); pg.wait_for_timeout(800)      # undo the tighten edit first
    panel.get_by_role("button", name="UNDO ALL").first.click(); pg.wait_for_timeout(2000)
    ok(not any(p["project_name"] == "Helper Port" for p in requests.get(B + "/api/lore/projects").json()),
       "UNDO ALL removed the entries and then the lorebook")
    # 6. a reload keeps the panel open with the same chat
    pg.reload(); pg.wait_for_timeout(1500)
    panel = pg.locator("aside[aria-label=Helper]")
    ok(panel.count() == 1 and "Make a lorebook for this card's world" in panel.inner_text(), "after a reload the panel and chat are back")
    panel.get_by_role("button", name="Close the helper").click(); pg.wait_for_timeout(300)
    ok(pg.get_by_role("button", name="Open the helper").count() == 1, "closes to the edge tab")
    ok(not errs, f"no page errors {errs[:2]}")
    b.close()
print("FAILS:", R.count(False))
