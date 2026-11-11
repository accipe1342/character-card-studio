"""v2.5: portraits saved with cards and TEXT characters."""
import base64
import io

import png_card
from test_text_flow import wait


def png():
    return png_card.placeholder("x", 4, 4)


def test_upload_get_and_attach(client, H):
    raw = png()
    r = client.post("/api/images", data={"file": (io.BytesIO(raw), "p.png")}, headers=H, content_type="multipart/form-data").get_json()
    name = r["image"]
    assert name.endswith(".png") and r["url"] == f"/api/images/{name}"
    g = client.get(r["url"], headers=H)
    assert g.status_code == 200 and g.data == raw and g.headers["Content-Type"] == "image/png"
    # same bytes = same file; data URLs work too
    again = client.post("/api/images", json={"data_url": "data:image/png;base64," + base64.b64encode(raw).decode()}, headers=H).get_json()
    assert again["image"] == name
    # refuse non-images and odd names
    assert client.post("/api/images", data={"file": (io.BytesIO(b"<svg/>"), "x.svg")}, headers=H, content_type="multipart/form-data").status_code == 400
    assert client.get("/api/images/..%2f..%2fetc.png", headers=H).status_code == 404
    assert client.get("/api/images/0000000000000000000a.png", headers=H).status_code == 404
    # attach to a card; the library list and the card both carry it; card edits keep it
    from database import create_or_update_card, get_card, save_source
    sid = save_source({"wiki_base": "manual", "page_name": "p", "url": "manual://p", "title": "P", "raw_html": "",
                       "raw_infobox": {}, "raw_sections": {}, "normalized": {}})
    cid = create_or_update_card(sid, {"name": "Pic", "description": "d"}, force_new=True)
    assert client.put(f"/api/card/{cid}/image", json={"image": name}, headers=H).get_json() == {"image": name}
    create_or_update_card(sid, {**get_card(cid), "description": "changed"}, card_id=cid)
    assert get_card(cid)["image"] == name
    assert any(c["id"] == cid and c["image"] == name for c in client.get("/api/cards", headers=H).get_json())
    assert client.put(f"/api/card/{cid}/image", json={"image": "nope.png"}, headers=H).status_code == 400
    assert client.put("/api/card/999999/image", json={"image": name}, headers=H).status_code == 404
    assert client.put(f"/api/card/{cid}/image", json={"image": ""}, headers=H).get_json() == {"image": ""}


def test_entity_image_travels_to_the_card_source(client, H):
    import text_module as T
    T.extract_chunk = lambda chunk, provider, model, mode: {"chapter_summary": "s", "beats": [], "stats": {}, "entities": [
        {"name": "Mara", "aliases": [], "type": "character", "age": "", "facts": "f", "voice": [], "keywords": ["Mara"],
         "origin": "", "relations": []}]}
    pid = client.post("/api/text/ingest", json={"name": "Img Fic", "text": "Chapter 1\n\n" + "word " * 400}, headers=H).get_json()["id"]
    wait(client, H, client.post(f"/api/text/project/{pid}/extract", json={"mode": "quick", "condense": False}, headers=H).get_json()["job_id"])
    e = client.get(f"/api/text/project/{pid}", headers=H).get_json()["entities"][0]
    name = client.post("/api/images", json={"data_url": "data:image/png;base64," + base64.b64encode(png()).decode()}, headers=H).get_json()["image"]
    client.put(f"/api/text/entity/{e['id']}/image", json={"image": name}, headers=H)
    e = client.get(f"/api/text/project/{pid}", headers=H).get_json()["entities"][0]
    assert e["image"] == name
    assert client.post(f"/api/text/entity/{e['id']}/to-source", headers=H).get_json()["image"] == name


def test_bundle_carries_portraits(client, H, tmp_path):
    import zipfile
    import images
    from database import create_or_update_card, get_card, save_source
    raw = png_card.placeholder("bundle", 6, 6)
    name = client.post("/api/images", data={"file": (io.BytesIO(raw), "p.png")}, headers=H, content_type="multipart/form-data").get_json()["image"]
    sid = save_source({"wiki_base": "manual", "page_name": "b", "url": "manual://bundle-pic", "title": "B", "raw_html": "",
                       "raw_infobox": {}, "raw_sections": {}, "normalized": {}})
    cid = create_or_update_card(sid, {"name": "Bundled", "description": "d"}, force_new=True)
    client.put(f"/api/card/{cid}/image", json={"image": name}, headers=H)
    O = {"Origin": "http://localhost:5173"}
    r = client.post("/api/bundle/export", json={"card_ids": [cid]}, headers={**H, **O})
    z = zipfile.ZipFile(io.BytesIO(r.data))
    assert z.read(f"images/{name}") == raw
    pngs = [n for n in z.namelist() if n.startswith("cards/") and n.endswith(".png")]
    assert pngs and png_card.read(z.read(pngs[0]))["chara"]["data"]["name"] == "Bundled"
    (images.images_dir() / name).unlink()               # as if on another computer
    res = client.post("/api/bundle/import", data={"file": (io.BytesIO(r.data), "b.zip")}, headers={**H, **O},
                      content_type="multipart/form-data").get_json()
    assert res["images"] == 1 and (images.images_dir() / name).exists()
    assert get_card(res["ids"]["cards"][0])["image"] == name
