"""Small helpers for the browser tests: the toolbars keep most actions in menus (NEW / TOOLS / EXPORT /
GENERATE), so a test opens the menu and then picks the item."""
import re


def open_menu(pg, label):
    pg.get_by_role("button", name=re.compile(rf"{re.escape(label)} ▾$")).first.click()
    pg.wait_for_timeout(150)
    return pg.locator(f"[role=menu][aria-label$='{label}']").first


def menu(pg, label, item):
    """Open the menu called `label` and click the item matching `item` (a regex)."""
    m = open_menu(pg, label)
    m.locator("button", has_text=re.compile(item)).first.click()

def pick(pg, label, item, wait=200):
    """Choose an option in a SelectMenu (the app's drop-downs are menus now, not native selects).

    `label` is the control's name (its aria-label), `item` a regex for the option's text.
    """
    pg.get_by_role("button", name=re.compile(rf"^{re.escape(label)}$", re.I)).first.click()
    pg.wait_for_timeout(150)
    pg.locator("[role=menu]").last.locator("[role=menuitem]").filter(has_text=re.compile(item, re.I)).first.click()
    pg.wait_for_timeout(wait)
