#!/usr/bin/env python3
"""Visual verification for the tournament extraction: for selected charts, place
the ORIGINAL chart image next to a mix-banded RECONSTRUCTION rendered from the
extracted frequencies. Eyeball that the colour layout matches. -> verify/tournament/
"""
import io
import os
import sys

import fitz
import numpy as np
from PIL import Image, ImageDraw

import extract_tournament as ex

OUTDIR = os.path.join(os.path.dirname(__file__), "..", "verify", "tournament")
COL = {0: (60, 118, 176), 1: (70, 170, 95), 2: (225, 60, 55), 3: (120, 22, 22)}


def recon(hands):
    H, W = 425, 659
    img = Image.new("RGB", (W, H - 48), (20, 20, 20))
    d = ImageDraw.Draw(img)
    for i in range(13):
        for j in range(13):
            f = hands[ex.hand_name(i, j)]
            y0, y1 = ex.ROWB[i] - 48, ex.ROWB[i + 1] - 48
            x0, x1 = ex.COLB[j], ex.COLB[j + 1]
            xo = x0
            for k in (2, 3, 1, 0):
                w = int(round(f[k] * (x1 - x0)))
                if w:
                    d.rectangle([xo, y0, min(xo + w, x1), y1], fill=COL[k])
                    xo += w
            if xo < x1:
                d.rectangle([xo, y0, x1, y1], fill=COL[0])
    # per-cell grid so the reconstruction is readable cell-by-cell
    for b in ex.ROWB:
        d.line([(0, b - 48), (659, b - 48)], fill=(15, 15, 15), width=1)
    for b in ex.COLB:
        d.line([(b, 0), (b, 425 - 48)], fill=(15, 15, 15), width=1)
    return img


def main():
    stack = sys.argv[1] if len(sys.argv) > 1 else "80BB"
    doc = fitz.open(ex.PDF)
    # rebuild the chart list with original images kept, for this stack
    charts = []
    cur_stack = cur_sect = None
    import re
    for pi in range(doc.page_count):
        page = doc[pi]
        lines = ex.page_lines(page)
        for bb, sz, txt in lines:
            t = txt.replace(" ", "")
            if 13.5 <= sz <= 14.5 and re.match(r"^\d+BB$", t):
                cur_stack = t
            elif 12.5 <= sz <= 13.5 and txt.upper() in ex.SECTION_TAB:
                cur_sect = txt.upper()
        if cur_stack != stack or cur_sect is None:
            continue
        titles = [(bb, sz, txt) for bb, sz, txt in lines
                  if 10.5 <= sz <= 11.5 and "·" in txt]
        for img_bbox, A in ex.chart_images(page):
            title = ex.match_title(img_bbox, titles)
            if not title:
                continue
            hero, villain, scenario = ex.parse_title(ex.SECTION_TAB[cur_sect], title)
            hands, _ = ex.extract_chart(A)
            sc = f" · {scenario}" if scenario else ""
            charts.append((f"{ex.SECTION_TAB[cur_sect]} {hero} vs {villain}{sc}", A, hands))

    os.makedirs(OUTDIR, exist_ok=True)
    # one sheet: each row = original | reconstruction, ~8 charts per sheet
    per = 8
    for s in range(0, len(charts), per):
        rows = charts[s:s + per]
        W = 659 * 2 + 30
        rh = 377 + 16
        sheet = Image.new("RGB", (W, rh * len(rows)), (255, 255, 255))
        dd = ImageDraw.Draw(sheet)
        for r, (lbl, A, hands) in enumerate(rows):
            y = r * rh
            sheet.paste(Image.fromarray(A[48:]), (0, y + 16))
            sheet.paste(recon(hands), (659 + 30, y + 16))
            dd.text((4, y + 2), lbl, fill=(0, 0, 0))
        p = os.path.join(OUTDIR, f"{stack}_{s//per:02d}.png")
        sheet.save(p)
        print("wrote", os.path.relpath(p), f"({len(rows)} charts)")


if __name__ == "__main__":
    main()
