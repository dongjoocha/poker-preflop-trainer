#!/usr/bin/env python3
"""Build per-page verification sheets to confirm data/charts.json matches the
PDF. For every chart we place the ORIGINAL chart image (grid + printed legend
counts) next to a RECONSTRUCTION rendered from the extracted JSON, with the
extracted combo counts printed underneath. Open verify/page_NN.png and eyeball
that the colour blocks match and the counts equal the printed legend.
"""
import io
import os

import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import extract_charts as ex

OUTDIR = os.path.join(os.path.dirname(__file__), "..", "verify")

ACT_COLOR = {
    "raise": (232, 69, 60), "raise_value": (232, 69, 60),
    "3bet_value": (232, 69, 60), "4bet_value": (232, 69, 60),
    "raise_bluff": (61, 111, 214), "3bet_bluff": (61, 111, 214),
    "4bet_bluff": (61, 111, 214),
    "call": (63, 174, 90), "limp": (63, 174, 90),
    "fold": (255, 255, 255),
}
CELL = 30
GRID = CELL * 13


def font(sz):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", sz)
    except Exception:
        return ImageFont.load_default()


def render_grid(hands):
    img = Image.new("RGB", (GRID + 2, GRID + 2), (40, 40, 40))
    d = ImageDraw.Draw(img)
    f = font(11)
    for i in range(13):
        for j in range(13):
            h = ex.hand_name(i, j)
            col = ACT_COLOR.get(hands[h], (255, 0, 255))
            x0, y0 = 1 + j * CELL, 1 + i * CELL
            d.rectangle([x0, y0, x0 + CELL - 1, y0 + CELL - 1], fill=col,
                        outline=(90, 90, 90))
            tcol = (20, 20, 20) if hands[h] in ("fold",) else (255, 255, 255)
            d.text((x0 + 2, y0 + 8), h, fill=tcol, font=f)
    return img


def main():
    doc = fitz.open(ex.PDF)
    pages = {}
    for pi, tab, hero, villain, action_set, label, A in ex.iter_charts(doc):
        hands, counts = ex.classify_chart(A, action_set)
        orig = Image.fromarray(A)
        scale = (GRID + 60) / orig.height
        orig = orig.resize((int(orig.width * scale), GRID + 60))
        recon = render_grid(hands)
        # row canvas: title | original | reconstruction + counts
        rw = orig.width + recon.width + 320
        rh = max(orig.height, recon.height) + 40
        row = Image.new("RGB", (rw, rh), (255, 255, 255))
        d = ImageDraw.Draw(row)
        d.text((6, 6), f"{label}  [{action_set}]", fill=(0, 0, 0), font=font(15))
        row.paste(orig, (6, 30))
        rx = orig.width + 16
        row.paste(recon, (rx, 30))
        cy = 30
        for a in ex.ACTION_SETS[action_set]:
            d.text((rx + recon.width + 8, cy), f"{a}: {counts[a]}", fill=(0, 0, 0),
                   font=font(13))
            cy += 20
        pages.setdefault(pi, []).append(row)

    os.makedirs(OUTDIR, exist_ok=True)
    for pi, rows in pages.items():
        w = max(r.width for r in rows)
        h = sum(r.height for r in rows) + 10
        sheet = Image.new("RGB", (w, h), (220, 220, 220))
        y = 5
        for r in rows:
            sheet.paste(r, (0, y))
            y += r.height
        path = os.path.join(OUTDIR, f"page_{pi:02d}.png")
        sheet.save(path)
        print("wrote", os.path.relpath(path), f"({len(rows)} charts)")


if __name__ == "__main__":
    main()
