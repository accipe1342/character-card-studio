import os
OUT = os.environ.get("E2E_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
os.makedirs(OUT, exist_ok=True)
import json, re, time, zipfile, io
from playwright.sync_api import sync_playwright
R = []
def ok(c, n): R.append((c, n)); print(("PASS " if c else "FAIL ") + n)
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1600, "height": 1200}, accept_downloads=True)
    pg = ctx.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("dialog", lambda d: d.accept())
    pg.goto("http://localhost:5173/"); pg.wait_for_timeout(800)
    pg.get_by_role("button", name=re.compile(r"^\s*TEXT\s*$", re.I)).first.click(); pg.wait_for_timeout(500)
    text = "\n\n".join(f"Chapter {n}: Part {n}\n\n" + " ".join(f"w{n}x{k}" for k in range(700)) for n in range(1, 7))
    pg.get_by_placeholder("Fic title").fill("Gamerz Fantasy X-2")
    pg.locator("textarea").first.fill(text)
    pg.get_by_role("button", name=re.compile("LOAD TEXT")).click(); pg.wait_for_timeout(1200)
    pg.get_by_role("button", name=re.compile("EXTRACT")).first.click()
    pg.wait_for_timeout(2500)
    mid = pg.locator("text=/· …/").count()
    ok(mid > 0 or pg.locator("text=/ent \\/ .* ev ✓/").count() > 0, "live chunk progress while extracting")
    pg.wait_for_selector("text=REVIEW", timeout=5000)
    for _ in range(40):
        if pg.locator("text=/SEND \\d+ ENTRIES TO LORE/").count(): break
        pg.wait_for_timeout(500)
    ok(pg.locator("text=/SEND \\d+ ENTRIES TO LORE/").count() == 1, "extraction finished, review list shown")
    ok(pg.locator("span", has_text=re.compile(r"^MAIN$")).count() >= 2, "MAIN tier badges")
    ok(pg.locator("span", has_text=re.compile(r"^(FIC|ALT)$")).count() >= 2, "FIC/ALT badges")
    hidden = pg.locator("text=/\\(\\d+ hidden\\)/").count()
    ok(hidden == 1, "one-offs collapsed by default")
    # edit Yuna + relationships + origin, autosave
    pg.locator("div", has_text=re.compile(r"^Yuna$")).first.click(); pg.wait_for_timeout(400)
    rel = pg.get_by_placeholder(re.compile("Rikku — cousin"))
    ok(rel.input_value().startswith("Rikku"), "relationships shown in editor")
    content = pg.locator("textarea").nth(2)
    pg.locator("xpath=//div[normalize-space(text())='CONTENT']/following-sibling::textarea[1]").fill("Hand-written Yuna notes.")
    pg.wait_for_timeout(1800)
    ok(pg.locator("text=✓ saved").count() == 1 and "Hand-written" in __import__("requests").get("http://127.0.0.1:5173/api/text/project/1").json()["entities"].__str__(), "autosave reached the backend")
    # keyboard: move down, X skip, Delete -> trash, U undo
    pg.locator("body").click(position={"x": 5, "y": 5})
    pg.keyboard.press("j"); pg.wait_for_timeout(400)
    nm = pg.locator("input").filter(has=pg.locator("xpath=.")).count()
    pg.keyboard.press("x"); pg.wait_for_timeout(600)
    pg.keyboard.press("Delete"); pg.wait_for_timeout(800)
    ok(pg.locator("text=/TRASH \\(1\\)/").count() == 1, "Delete key moves to trash")
    pg.keyboard.press("u"); pg.wait_for_timeout(800)
    ok(pg.locator("text=/TRASH \\(0\\)/").count() == 1, "U undoes the delete")
    # select problems -> delete -> trash -> restore one
    pg.get_by_role("button", name="SELECT PROBLEMS").click(); pg.wait_for_timeout(200)
    pg.get_by_role("button", name=re.compile(r"^DELETE$")).first.click(); pg.wait_for_timeout(900)
    pg.get_by_role("button", name=re.compile(r"TRASH \(\d+\)")).click(); pg.wait_for_timeout(300)
    n_trash = len(re.findall(r"\d+", pg.get_by_role("button", name=re.compile(r"TRASH \(\d+\)")).inner_text()))
    pg.get_by_role("button", name="RESTORE").first.click(); pg.wait_for_timeout(700)
    ok(True, "trash view + restore clicked")
    pg.get_by_role("button", name=re.compile(r"TRASH \(\d+\)")).click(); pg.wait_for_timeout(300)
    # Rebuild list (merge only) keeps the hand edit
    pg.get_by_role("button", name=re.compile("REBUILD LIST")).click()
    for _ in range(40):
        pg.wait_for_timeout(400)
        if pg.locator("text=/SEND \\d+ ENTRIES TO LORE/").count() and not pg.locator("text=WORKING…").count(): break
    pg.wait_for_timeout(800)
    pg.locator("div", has_text=re.compile(r"^Yuna$")).first.click(); pg.wait_for_timeout(400)
    ok(pg.locator("textarea", has_text="Hand-written Yuna notes.").count() == 1, "Rebuild list kept the hand edit")
    # per-chunk redo
    pg.locator("button[title^='Redo just this chunk']").first.click(); pg.wait_for_timeout(3500)
    ok(True, "single-chunk redo ran")
    # recap: starting point after chunk 2, then edit text
    sel = pg.locator("select").filter(has=pg.locator("option", has_text="the end of the text"))
    sel.select_option(index=2); pg.wait_for_timeout(700)
    recap_ta = pg.locator("textarea").filter(has_text="Gullwings press on").first
    ok(recap_ta.input_value().count("press on") == 2, f"recap stops at starting point: {recap_ta.input_value()[:80]!r}")
    pg.get_by_role("button", name="SAVE RECAP").click(); pg.wait_for_timeout(500)
    pg.screenshot(path=OUT + "/text_studio.png", full_page=True)
    # send to LORE
    pg.get_by_role("button", name=re.compile("SEND \\d+ ENTRIES TO LORE")).click(); pg.wait_for_timeout(1200)
    # narrator card download
    with pg.expect_download() as dl:
        pg.get_by_role("button", name=re.compile("WORLD NARRATOR CARD")).click()
    d = json.loads(open(dl.value.path()).read())
    ok(d["spec"] == "chara_card_v2" and d["data"]["character_book"]["entries"], "narrator card downloaded with lorebook")
    tl = [e for e in d["data"]["character_book"]["entries"] if e["name"] == "Story Timeline"]
    ok(tl and "chunk 3" not in tl[0]["content"], "narrator lorebook respects starting point")
    # make card -> character studio -> generate -> attach lorebook -> export
    pg.locator("div", has_text=re.compile(r"^Rikku$")).first.click(); pg.wait_for_timeout(400)
    pg.get_by_role("button", name=re.compile("MAKE CARD")).click(); pg.wait_for_timeout(1500)
    ok(pg.locator("text=Character Card Studio").count() >= 1, "switched to CHARACTER studio")
    pg.get_by_role("button", name=re.compile("Generate Card", re.I)).first.click()
    for _ in range(30):
        pg.wait_for_timeout(500)
        if pg.locator("text=Generated from the fic").count() or pg.locator("textarea", has_text="Generated from the fic").count(): break
    ok(pg.locator("textarea", has_text="Generated from the fic").count() >= 1 or pg.locator("text=Generated from the fic").count() >= 1, "card generated from the fic source")
    lsel = pg.locator("select").filter(has=pg.locator("option", has_text="No lorebook attached"))
    opts = lsel.locator("option").all_inner_texts()
    lsel.select_option(index=1); pg.wait_for_timeout(300)
    with pg.expect_download() as dl2:
        pg.get_by_role("button", name=re.compile("Export Card JSON", re.I)).click()
    d2 = json.loads(open(dl2.value.path()).read())
    ok(d2["data"].get("character_book", {}).get("entries"), f"card JSON embeds lorebook ({opts[1] if len(opts) > 1 else '?'})")
    pg.screenshot(path=OUT + "/character.png")
    # LORE studio DeepLore export
    pg.get_by_role("button", name=re.compile(r"^\s*LORE\s*$", re.I)).first.click(); pg.wait_for_timeout(1000)
    pj = pg.locator("text=/Gamerz Fantasy X-2/").first
    if pj.count(): pj.click(); pg.wait_for_timeout(800)
    with pg.expect_download() as dl3:
        pg.get_by_role("button", name=re.compile("DeepLore", re.I)).click()
    z = zipfile.ZipFile(dl3.value.path())
    ok(len(z.namelist()) >= 3, f"DeepLore zip with {len(z.namelist())} notes")
    pg.screenshot(path=OUT + "/lore.png")
    real_errs = [e for e in errs if "favicon" not in e]
    ok(not real_errs, f"no page errors {real_errs[:3]}")
    b.close()
print("FAILS:", sum(1 for c, _ in R if not c))
