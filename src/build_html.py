#!/usr/bin/env python3
"""Inline data/charts.json into the HTML template -> dist/poker-trainer.html.

The data must be embedded (not fetched) so the single file works from a
file:// double-click, where fetch() is blocked by CORS. The favicon is
embedded the same way (small data URI); the larger apple-touch-icon (iOS
home screen) is emitted as a sibling PNG file.
"""
import base64
import io
import json
import os

from PIL import Image

HERE = os.path.dirname(__file__)
TEMPLATE = os.path.join(HERE, "..", "template", "poker-trainer.template.html")
DATA = os.path.join(HERE, "..", "data", "charts.json")
TOURNEY = os.path.join(HERE, "..", "data", "tournament.json")
ICON = os.path.join(HERE, "..", "assets", "icon.png")
DIG = "0123456789abcdefghijklmnopqrstuvwxyz"
OUT = os.path.join(HERE, "..", "dist", "poker-trainer.html")
# also written to the repo root so GitHub Pages serves it at the site root URL
OUT_INDEX = os.path.join(HERE, "..", "index.html")
# apple-touch-icon written next to each HTML entry point
APPLE_OUT = [os.path.join(HERE, "..", "apple-touch-icon.png"),
             os.path.join(HERE, "..", "dist", "apple-touch-icon.png")]


def favicon_datauri():
    im = Image.open(ICON).convert("RGB").resize((48, 48), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def write_apple_icons():
    im = Image.open(ICON).convert("RGB").resize((180, 180), Image.LANCZOS)
    for p in APPLE_OUT:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        im.save(p, "PNG", optimize=True)


# --- tournament data: full-precision tournament.json (~2 MB) is the editable
# source of truth; here we COMPACT it for inlining. Each cell is a
# [fold,call,raise,allin] frequency vector quantised to 5% units (these freqs
# are already approximate raster estimates, so 5% is lossless in practice).
# Across all 507 charts only ~430 distinct vectors occur, so we build a global
# palette and reference each of the 169 cells by a fixed-width base36 index.
# Result: ~2 MB -> ~200 KB. The JS template carries the matching decoder.
def quantize(vec):
    """[f,c,r,a] floats summing ~1 -> 4 ints in 5% units (0..20) summing to 20."""
    s = sum(vec) or 1.0
    raw = [max(0.0, v) / s * 20 for v in vec]
    u = [int(x) for x in raw]                       # floor
    rem = 20 - sum(u)                               # 0..3 units to hand out
    for i in sorted(range(4), key=lambda k: raw[k] - u[k], reverse=True)[:rem]:
        u[i] += 1
    return tuple(u)


def compact_tournament(tj):
    ranks = tj["ranks"]
    cells = [(i, j) for i in range(13) for j in range(13)]   # canonical order

    def hand_name(i, j):
        if i == j:
            return ranks[i] * 2
        return ranks[i] + ranks[j] + "s" if i < j else ranks[j] + ranks[i] + "o"

    pal_index, pal = {}, []
    rows = []                                        # (situation, [palette idx ...])
    for s in tj["situations"]:
        idxs = []
        for i, j in cells:
            q = quantize(s["hands"][hand_name(i, j)])
            if q not in pal_index:
                pal_index[q] = len(pal)
                pal.append(q)
            idxs.append(pal_index[q])
        rows.append((s, idxs))

    w = 2                                            # base36 digits per cell index
    while 36 ** w <= len(pal) - 1:
        w += 1

    def b36(n):
        out = DIG[n % 36] if n else "0"
        n //= 36
        while n:
            out = DIG[n % 36] + out
            n //= 36
        return out.rjust(w, "0")

    stacks = sorted({s["stack"] for s in tj["situations"]}, key=lambda x: -int(x[:-2]))
    sits = [{"k": s["stack"], "t": s["tab"], "h": s["hero"], "v": s["villain"],
             "g": s.get("scenario", ""), "l": s["label"], "a": s["actions"],
             "c": "".join(b36(x) for x in idxs)}
            for s, idxs in rows]
    return {"meta": tj["meta"], "stacks": stacks, "actions": tj["actions"],
            "ranks": ranks, "w": w,
            "pal": ["".join(DIG[x] for x in q) for q in pal], "sits": sits}


def main():
    with open(TEMPLATE) as f:
        html = f.read()
    with open(DATA) as f:
        data = json.load(f)
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    html = html.replace("{{CHARTS_JSON}}", blob)
    # tournament charts (compacted; empty if not yet extracted)
    tblob, tcount = '{"stacks":[],"sits":[],"pal":[],"ranks":[],"w":2,"actions":[]}', 0
    if os.path.exists(TOURNEY):
        with open(TOURNEY) as f:
            tj = json.load(f)
        compact = compact_tournament(tj)
        tblob = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        tcount = len(tj["situations"])
    html = html.replace("{{TOURNAMENT_JSON}}", tblob)
    html = html.replace("{{FAVICON}}", favicon_datauri())
    write_apple_icons()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    for path in (OUT, OUT_INDEX):
        with open(path, "w") as f:
            f.write(html)
    kb = os.path.getsize(OUT) / 1024
    print(f"wrote {os.path.relpath(OUT)} + {os.path.relpath(OUT_INDEX)} "
          f"+ apple-touch-icon.png ({kb:.0f} KB, {len(data['situations'])} cash + "
          f"{tcount} tournament charts; tournament blob {len(tblob)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
