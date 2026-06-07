#!/usr/bin/env python3
"""Extract the PokerCoaching "Ultimate Tournament Preflop Guide" PDF into
data/tournament.json.

Unlike the original cash charts (one solid action per cell), these are
MIXED-FREQUENCY charts: each 13x13 cell is split into colour bands proportional
to action frequency (like GTO Wizard). We recover a per-hand frequency vector
[fold, call, raise, allin] by classifying every cell pixel by hue and taking the
proportions.

Layout (every chart image is a fixed 659x425 raster; the page tiles up to 6 of
them in a 2x3 grid):
  - page text gives the stack header ("80BB"), the section ("VS 3-BET"), and a
    per-chart title ("HJ vs CO · 3-Bet"); we carry stack/section across pages.
  - the grid sits below a colour legend bar; canonical gridline coords (below)
    were calibrated from clean RFI charts and apply to every image.

Colour -> action: bright red=raise, dark red=all-in, green=call, blue OR
dark/near-black=fold. Frequencies are *approximate* (the raster doesn't invert
cleanly to the printed legend %), so the app labels them as estimates and we
verify visually via verify_tournament.py reconstruction sheets.
"""
import io
import json
import os
import re
import sys

import fitz
import numpy as np
from PIL import Image

PDF = os.path.expanduser("~/Downloads/personal/poker/preflop-charts.pdf")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "tournament.json")

RANKS = "AKQJT98765432"
ACTIONS = ["fold", "call", "raise", "allin"]
# canonical 13x13 grid boundaries within a 659x425 chart image
ROWB = [48, 79, 108, 137, 166, 194, 225, 253, 282, 310, 339, 368, 397, 425]
COLB = [0, 49, 100, 151, 202, 252, 302, 353, 405, 456, 507, 558, 609, 659]

SECTION_TAB = {"RAISE FIRST IN": "rfi", "VS RFI": "facing",
               "VS 3-BET": "vs3bet", "VS 4-BET": "vs4bet"}


def hand_name(i, j):
    if i == j:
        return RANKS[i] * 2
    return RANKS[i] + RANKS[j] + "s" if i < j else RANKS[j] + RANKS[i] + "o"


def combos(h):
    return 6 if h[0] == h[1] else (4 if h.endswith("s") else 12)


def px_codes(p):
    """Classify each RGB pixel -> action code (0 fold,1 call,2 raise,3 allin,-1 drop)."""
    R, G, B = p[:, 0], p[:, 1], p[:, 2]
    mx = p.max(1)
    mn = p.min(1)
    code = np.full(len(p), -1)
    # Only DROP white/grey text + its halo (low saturation AND bright). Everything
    # else is real: dark pixels are FOLD (rendered anywhere from ~36,36,36 down to
    # near-black; gridlines are dark too but thin, cleaned by the noise floor).
    # NB: do NOT drop on brightness alone — a saturated bright red (246,59,67) has
    # mx>238 but is a raise pixel, not white text.
    drop = (mx - mn < 28) & (mx >= 95)
    nd = (mx - mn < 28) & ~drop                                      # dark = fold
    sat = (mx - mn >= 28) & ~drop
    red = sat & (R > G + 14) & (R > B + 14)
    grn = sat & (G > R + 4) & (G > B - 6) & ~red
    blu = sat & ~red & ~grn                                          # blue = fold
    code[nd] = 0
    code[blu] = 0
    code[grn] = 1
    # raise (red, e.g. 233,60,58) vs all-in (pure DARK maroon, e.g. 80,10,12).
    # Maroon is dark (max channel <110); even saturated raise reds stay bright
    # (R~150-234) regardless of their low G,B, so darkness is the discriminator.
    allin = red & (mx < 110) & (G < 50) & (B < 55)
    code[red & ~allin] = 2
    code[allin] = 3
    return code


NOISE = 0.03            # drop boundary/anti-alias artifacts; keeps real bands


def cell_freq(A, i, j, vy=3):
    """Frequencies for one cell via PER-COLUMN MAJORITY. Cells are split into
    vertical colour bands (width proportional to frequency) with a white label
    across the middle; each column is one band's colour (text only crosses a few
    rows, so the column's majority non-text pixel is the band colour). Frequency
    = fraction of columns per action.

    Why column-majority (not raw pixel area): it's immune to (a) the white text's
    dark outline and thin gridline pixels — scattered darks never win a column,
    so solid raise cells stay 100% raise instead of showing a spurious fold
    sliver; and (b) horizontally-split cells (a source-rendering quirk) collapse
    to their dominant colour, as intended. Real >=1-column bands are kept."""
    y0, y1 = ROWB[i] + vy, ROWB[i + 1] - vy
    cell = A[y0:y1, COLB[j]:COLB[j + 1]].astype(int)
    h, w, _ = cell.shape
    code = px_codes(cell.reshape(-1, 3)).reshape(h, w)
    counts = np.stack([(code == k).sum(0) for k in range(4)])  # [4, w]
    valid = (code >= 0).sum(0) >= 0.30 * h
    seq = [int(counts[:, x].argmax()) for x in range(w) if valid[x]]  # L->R band colours
    # A cell's outer few columns pick up the 1-2px inter-cell gridline and the
    # anti-alias where a bright band fades into it — rendered DARK, so misread as
    # fold (neutral dark) or all-in (dark red), sometimes behind a 1px bright
    # bleed from the neighbour. Drop DARK (fold/all-in) columns in the outer 3px
    # of each edge that aren't the cell's dominant action. Real fold/all-in bands
    # (dominant, or reaching past the 3px edge zone) and bright bands survive.
    if seq:
        dom = max(set(seq), key=seq.count)
        n = len(seq)
        seq = [c for idx, c in enumerate(seq)
               if not ((idx < 3 or idx >= n - 3) and c != dom and c in (0, 3))]
    tot = len(seq) or 1
    f = [seq.count(k) / tot for k in range(4)]
    f = [v if v >= NOISE else 0.0 for v in f]
    s = sum(f) or 1.0
    return [round(v / s, 3) for v in f]


def cell_freq_pixfrac(A, i, j, vy=3, hx=2):
    """Independent pixel-area estimate (audit cross-check only). Picks up scattered
    text-outline/gridline darks, so not used for extraction."""
    y0, y1 = ROWB[i] + vy, ROWB[i + 1] - vy
    c = px_codes(A[y0:y1, COLB[j] + hx:COLB[j + 1] - hx].reshape(-1, 3).astype(int))
    c = c[c >= 0]
    tot = len(c) or 1
    f = [v if (v := int((c == k).sum()) / tot) >= NOISE else 0.0 for k in range(4)]
    s = sum(f) or 1.0
    return [round(v / s, 3) for v in f]


def extract_chart(A):
    """Return {hand: [fold,call,raise,allin]} and the present-action set."""
    hands = {}
    agg = [0.0, 0.0, 0.0, 0.0]
    for i in range(13):
        for j in range(13):
            h = hand_name(i, j)
            f = cell_freq(A, i, j)
            hands[h] = f
            for k in range(4):
                agg[k] += f[k] * combos(h)
    tot = sum(agg) or 1
    present = [ACTIONS[k] for k in range(4) if agg[k] / tot > 0.01]
    return hands, present


# --- page parsing ----------------------------------------------------------
def page_lines(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            sz = max(s["size"] for s in ln["spans"])
            txt = "".join(s["text"] for s in ln["spans"]).strip()
            if txt:
                out.append((ln["bbox"], sz, txt))
    return out


def parse_title(tab, title):
    """'HJ vs CO · 3-Bet' -> (hero, villain, scenario). 'UTG · RFI' -> (UTG, None, RFI).

    The text after '·' is a SCENARIO qualifier that distinguishes otherwise-identical
    matchups: e.g. 'BB vs SB · RFI' vs '· Limp' (SB raised vs limped), and
    'X vs Y · 4-Bet' vs '· 4-Bet All-In' (facing a normal 4-bet vs a 4-bet jam).
    Without it, ~90 distinct charts collide on (stack, tab, hero, villain)."""
    parts = title.split("·")
    left = parts[0].strip()
    scenario = parts[1].strip() if len(parts) > 1 else ""
    if " vs " in left:
        hero, villain = [s.strip() for s in left.split(" vs ", 1)]
        return hero, villain, scenario
    return left, None, scenario


def chart_images(page):
    """(bbox, ndarray) for each 659x425 chart raster on the page."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 1:
            continue
        im = Image.open(io.BytesIO(b["image"])).convert("RGB")
        if im.size == (659, 425):
            out.append((b["bbox"], np.asarray(im)))
    return out


def match_title(img_bbox, titles):
    """The title for an image is the one in the SAME COLUMN (left edges align —
    NOT x-centre, which shifts with title text width) that sits DIRECTLY above it
    (smallest vertical gap). Matching by x-centre mismatches rows on 2x3 pages."""
    ix0 = img_bbox[0]
    itop = img_bbox[1]
    best, best_gap = None, 1e9
    for (bb, sz, txt) in titles:
        if bb[1] >= itop:                      # title must be above the image
            continue
        if abs(bb[0] - ix0) > 130:             # different column
            continue
        gap = itop - bb[1]
        if gap < best_gap:
            best_gap, best = gap, txt
    return best


def main():
    doc = fitz.open(PDF)
    only = sys.argv[1] if len(sys.argv) > 1 else None     # e.g. "80BB"
    situations = []
    cur_stack = cur_sect = None
    for pi in range(doc.page_count):
        page = doc[pi]
        lines = page_lines(page)
        for bb, sz, txt in lines:
            t = txt.replace(" ", "")
            if 13.5 <= sz <= 14.5 and re.match(r"^\d+BB$", t):
                cur_stack = t
            elif 12.5 <= sz <= 13.5 and txt.upper() in SECTION_TAB:
                cur_sect = txt.upper()
        if cur_stack is None or cur_sect is None:
            continue
        if only and cur_stack != only:
            continue
        titles = [(bb, sz, txt) for bb, sz, txt in lines
                  if 10.5 <= sz <= 11.5 and "·" in txt]
        for img_bbox, A in chart_images(page):
            title = match_title(img_bbox, titles)
            if not title:
                continue
            tab = SECTION_TAB[cur_sect]
            hero, villain, scenario = parse_title(tab, title)
            hands, present = extract_chart(A)
            label = hero if villain is None else f"{hero} vs {villain}"
            situations.append({
                "stack": cur_stack, "tab": tab, "hero": hero, "villain": villain,
                "scenario": scenario, "label": label,
                "actions": present, "hands": hands,
            })
        print(f"p{pi} {cur_stack} {cur_sect}: {len([s for s in situations])} total",
              file=sys.stderr)

    out = {
        "meta": {"source": "PokerCoaching Ultimate Tournament Preflop Guide",
                 "note": "mixed-frequency (approximate, extracted from chart "
                         "images); freqs are estimates, verify visually"},
        "ranks": list(RANKS), "actions": ACTIONS,
        "situations": situations,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    from collections import Counter
    by = Counter((s["stack"], s["tab"]) for s in situations)
    print(f"\nwrote {os.path.relpath(OUT)}: {len(situations)} charts")
    for k in sorted(by):
        print(f"  {k[0]:6s} {k[1]:8s} {by[k]}")


if __name__ == "__main__":
    main()
