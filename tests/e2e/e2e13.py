"""Drop-downs must be clickable wherever they are opened.

In 2.8.0 the menu was `position: absolute`, so any ancestor with overflow hidden or auto cropped it:
the first-run panel collapses itself with overflow:hidden and the studio panels scroll, and the
provider list came out with two of its three options outside the panel and unclickable.

Visibility proves nothing here - Playwright reports a cropped element as visible - so every item is
hit-tested with elementFromPoint, which is what a real click resolves against."""
import os
import sys

from playwright.sync_api import sync_playwright
from ui import open_menu  # noqa: F401  (kept for parity with the other scripts)

OUT = os.environ.get("E2E_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
os.makedirs(OUT, exist_ok=True)
B = "http://127.0.0.1:5173"
R = []
def ok(c, n): R.append(bool(c)); print(("PASS " if c else "FAIL ") + n)

HIT = """() => {
  const items = [...document.querySelectorAll('.sui-menu:not([hidden]) [role=menuitem]')];
  if (!items.length) return null;
  const bad = items.filter(it => {
    const r = it.getBoundingClientRect();
    if (!r.width || !r.height) return false;
    const hit = document.elementFromPoint(Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2));
    return !(hit && hit.closest('[role=menuitem]') === it);
  });
  return {total: items.length, bad: bad.length,
          text: bad.slice(0, 3).map(b => b.innerText.trim().split('\\n')[0])};
}"""

with sync_playwright() as pw:
    br = pw.chromium.launch()
    pg = br.new_page(viewport={"width": 1440, "height": 900})
    pg.goto(B, wait_until="networkidle")
    pg.wait_for_timeout(700)

    # --- the first-run panel, which collapses itself with overflow:hidden -------------------------
    gate = pg.get_by_role("button", name="Provider")
    if gate.count():
        gate.first.click()
        pg.wait_for_timeout(300)
        r = pg.evaluate(HIT)
        ok(r is not None and r["total"] == 3, f"the first-run provider menu lists all three providers ({r and r['total']})")
        ok(r is not None and r["bad"] == 0, f"every provider is clickable, not cropped by the panel {r and r['text']}")
        pg.screenshot(path=os.path.join(OUT, "e2e13-first-run-menu.png"))
        # and picking the last one has to actually land
        pg.locator('[role="menuitem"]').last.click()
        pg.wait_for_timeout(300)
        ok(pg.locator('input[aria-label="Local server address"]').count() > 0,
           "picking the last provider switched the panel to the local address field")
        pg.keyboard.press("Escape")
        skip = pg.get_by_text("Skip for now")
        if skip.count():
            skip.first.click()
            pg.wait_for_timeout(400)
    else:
        ok(True, "no first-run panel on this run (a provider is already configured)")

    # --- every other menu we can reach, across the studios ---------------------------------------
    opened = broken = items = 0
    for tab in ["CHARACTER", "LORE", "TEXT"]:
        t = pg.get_by_role("button", name=tab, exact=True)
        if t.count():
            try:
                t.first.click()
                pg.wait_for_timeout(500)
            except Exception:
                pass
        btns = pg.locator('button[aria-haspopup="menu"]')
        for i in range(btns.count()):
            btn = btns.nth(i)
            try:
                if not btn.is_visible() or btn.is_disabled():
                    continue
                btn.click(timeout=2500)
                pg.wait_for_timeout(200)
            except Exception:
                continue
            r = pg.evaluate(HIT)
            if r:
                opened += 1
                items += r["total"]
                if r["bad"]:
                    broken += 1
                    print(f"       {tab}: {r['bad']}/{r['total']} unreachable {r['text']}")
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(120)

    ok(opened >= 5, f"opened enough menus to be meaningful ({opened} menus, {items} items)")
    ok(broken == 0, f"no menu has unreachable items ({broken} broken)")

    br.close()

print(f"\n{sum(R)}/{len(R)} passed")
sys.exit(0 if all(R) else 1)
