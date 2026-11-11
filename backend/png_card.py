"""
png_card.py — character card PNGs without an image library
==========================================================

embed(png, v2, v3=None)   put the card into a PNG as tEXt chunks: "chara" (base64 V2 JSON, what SillyTavern reads)
                          and "ccv3" (base64 V3 JSON, for V3-aware sites). Old card chunks are replaced.
read(png)                 {keyword: decoded text} for the card chunks in a PNG
placeholder(name)         a plain 400x600 portrait PNG for cards that have no image yet
decode_data_url(s)        bytes from "data:image/png;base64,..." (or bare base64); None when it isn't a PNG
"""

import base64
import json
import struct
import zlib

SIG = b"\x89PNG\r\n\x1a\n"
CARD_KEYS = (b"chara", b"ccv3")


def _chunks(png):
    if not png.startswith(SIG):
        raise ValueError("Not a PNG file")
    pos = len(SIG)
    while pos + 8 <= len(png):
        length, = struct.unpack(">I", png[pos:pos + 4])
        ctype = png[pos + 4:pos + 8]
        data = png[pos + 8:pos + 8 + length]
        yield ctype, data, png[pos:pos + 12 + length]
        pos += 12 + length
        if ctype == b"IEND":
            break


def _chunk(ctype, data):
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


def _b64(obj):
    return base64.b64encode(json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def embed(png, v2, v3=None):
    out, extra = [SIG], [_chunk(b"tEXt", b"chara\x00" + _b64(v2))]
    if v3 is not None:
        extra.append(_chunk(b"tEXt", b"ccv3\x00" + _b64(v3)))
    for ctype, data, raw in _chunks(png):
        if ctype == b"tEXt" and data.split(b"\x00", 1)[0] in CARD_KEYS:
            continue
        if ctype == b"IEND":
            out.extend(extra)
        out.append(raw)
    return b"".join(out)


def read(png):
    res = {}
    for ctype, data, _ in _chunks(png):
        if ctype == b"tEXt":
            key, _, val = data.partition(b"\x00")
            if key in CARD_KEYS:
                res[key.decode()] = json.loads(base64.b64decode(val).decode("utf-8"))
    return res


def placeholder(name="", w=400, h=600):
    """Muted parchment portrait with a darker band, in the app's palette. No text (no font rendering here)."""
    seed = sum(ord(c) for c in name or "x")
    band = (60 + seed % 40, 56 + seed % 30, 48 + seed % 20)
    bg = (232, 227, 211)
    rows = []
    for y in range(h):
        col = band if h * 0.62 < y < h * 0.72 else bg
        rows.append(b"\x00" + bytes(col) * w)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return SIG + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + _chunk(b"IEND", b"")


def decode_data_url(s):
    if not s or not isinstance(s, str):
        return None
    if s.startswith("data:"):
        head, _, s = s.partition(",")
        if "base64" not in head:
            return None
    try:
        raw = base64.b64decode(s, validate=False)
    except Exception:
        return None
    return raw if raw.startswith(SIG) else None
