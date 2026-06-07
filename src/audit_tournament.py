#!/usr/bin/env python3
"""Automated per-cell audit of the tournament extraction. For every cell we
compare the shipped extractor (column-majority) against an INDEPENDENT method
(pixel fraction over the text-free top/bottom strips). They use different logic,
so cells where they disagree are the ones worth inspecting. Reports the worst
cells across all charts of a stack.
"""
import sys
import re
import io

import numpy as np
import fitz
from PIL import Image

import extract_tournament as ex


def strip_freq(A, i, j, vy=5, hx=1, noise=0.03):
    y0, y1 = ex.ROWB[i], ex.ROWB[i + 1]
    x0, x1 = ex.COLB[j] + hx, ex.COLB[j + 1] - hx
    h = y1 - y0
    s = max(4, int(0.30 * h))
    top = A[y0 + vy:y0 + s, x0:x1].reshape(-1, 3)
    bot = A[y1 - s:y1 - vy, x0:x1].reshape(-1, 3)
    c = ex.px_codes(np.vstack([top, bot]).astype(int))
    c = c[c >= 0]
    if len(c) == 0:
        return [1.0, 0.0, 0.0, 0.0]                  # all border/text (corner) -> fold
    tot = len(c)
    f = [int((c == k).sum()) / tot for k in range(4)]
    f = [v if v >= noise else 0.0 for v in f]
    sm = sum(f) or 1.0
    return [v / sm for v in f]


def charts_for(doc, stack):
    out = []
    cs = cse = None
    for pi in range(doc.page_count):
        page = doc[pi]
        lines = ex.page_lines(page)
        for bb, sz, txt in lines:
            t = txt.replace(" ", "")
            if 13.5 <= sz <= 14.5 and re.match(r"^\d+BB$", t):
                cs = t
            elif 12.5 <= sz <= 13.5 and txt.upper() in ex.SECTION_TAB:
                cse = txt.upper()
        if cs != stack or cse is None:
            continue
        titles = [(bb, sz, txt) for bb, sz, txt in lines
                  if 10.5 <= sz <= 11.5 and "·" in txt]
        for ib, A in ex.chart_images(page):
            t = ex.match_title(ib, titles)
            if t:
                out.append((ex.SECTION_TAB[cse], t, A))
    return out


def main():
    stack = sys.argv[1] if len(sys.argv) > 1 else "80BB"
    doc = fitz.open(ex.PDF)
    charts = charts_for(doc, stack)
    flags = []
    worst = 0.0
    for tab, title, A in charts:
        for i in range(13):
            for j in range(13):
                cf = ex.cell_freq(A, i, j)                 # shipped: column majority
                sf = ex.cell_freq_pixfrac(A, i, j)         # independent: pixel area
                tvd = 0.5 * sum(abs(cf[k] - sf[k]) for k in range(4))
                worst = max(worst, tvd)
                if tvd > 0.12:
                    flags.append((tvd, f"{tab} {title}", ex.hand_name(i, j),
                                  [round(x, 2) for x in cf], [round(x, 2) for x in sf]))
    flags.sort(reverse=True)
    print(f"{stack}: {len(charts)} charts, {len(flags)} cells disagree (TVD>0.12), "
          f"worst TVD={worst:.2f}")
    for tvd, ch, hand, cf, sf in flags[:30]:
        print(f"  {tvd:.2f}  {ch:28s} {hand:4s} col={cf} strip={sf}")


if __name__ == "__main__":
    main()
