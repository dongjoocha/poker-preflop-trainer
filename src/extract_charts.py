#!/usr/bin/env python3
"""Extract PokerCoaching preflop charts from the PDF into data/charts.json.

Each sub-chart is an embedded JPEG (~600px wide) containing a 13x13 hand
matrix plus an Action/Hands legend below it. We:
  1. locate each chart image and match it to its 16pt title (by x-center,
     title sits just above the image) -> (tab, hero, villain, actionSet),
  2. detect the 13x13 lattice via a non-white projection bounding box,
  3. sample each cell center colour and classify it into a semantic code
     (value / bluff / call|limp / fold), then map that to the action code
     for the chart's actionSet.

charts.json is the editable single source of truth; rerun verify_charts.py
after any manual correction.
"""
import io
import json
import os
import sys

import fitz  # PyMuPDF
import numpy as np
from PIL import Image

PDF = os.path.expanduser("~/Downloads/full-preflop-charts.pdf")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "charts.json")

RANKS = "AKQJT98765432"  # high -> low; index 0 = Ace

# --- hand naming -----------------------------------------------------------
def hand_name(i, j):
    """Grid cell (row i, col j) -> hand string. i<j suited, i>j offsuit."""
    if i == j:
        return RANKS[i] * 2
    if i < j:
        return RANKS[i] + RANKS[j] + "s"
    return RANKS[j] + RANKS[i] + "o"

def combos(hand):
    if len(hand) == 2:
        return 6           # pair
    return 4 if hand.endswith("s") else 12

HANDS = [hand_name(i, j) for i in range(13) for j in range(13)]

# --- situation metadata ----------------------------------------------------
SECTION_TAB = {
    "Raise First In": "rfi",
    "Facing RFI": "facing",
    "RFI vs 3bet": "vs3bet",
}

POS_NORMALIZE = {
    "Lojack": "LJ", "Hijack": "HJ", "Cutoff": "CO", "Button": "BTN",
    "Small Blind": "SB", "Big Blind": "BB",
}
QUALIFIERS = {"3bet", "RFI", "Limp", "Raise"}

ACTION_SETS = {
    "rfi": ["raise", "fold"],
    "rfi_sb": ["raise_value", "raise_bluff", "limp", "fold"],
    "facing": ["3bet_value", "3bet_bluff", "call", "fold"],
    "vs3bet": ["4bet_value", "4bet_bluff", "call", "fold"],
    "sb_limp_vs_bb": ["3bet_value", "3bet_bluff", "call", "fold"],
}
ACTION_LABELS = {
    "raise": "Raise", "fold": "Fold",
    "raise_value": "Raise for Value", "raise_bluff": "Raise as a Bluff", "limp": "Limp",
    "3bet_value": "3-bet for Value", "3bet_bluff": "3-bet as a Bluff", "call": "Call",
    "4bet_value": "4-bet for Value", "4bet_bluff": "4-bet as a Bluff",
}
# semantic colour code -> action code, per actionSet
SEM_TO_ACTION = {
    "rfi":           {"V": "raise", "B": "raise", "C": "raise", "F": "fold"},
    "rfi_sb":        {"V": "raise_value", "B": "raise_bluff", "C": "limp", "F": "fold"},
    "facing":        {"V": "3bet_value", "B": "3bet_bluff", "C": "call", "F": "fold"},
    "vs3bet":        {"V": "4bet_value", "B": "4bet_bluff", "C": "call", "F": "fold"},
    "sb_limp_vs_bb": {"V": "3bet_value", "B": "3bet_bluff", "C": "call", "F": "fold"},
}


def normalize_pos(token):
    token = token.strip()
    return POS_NORMALIZE.get(token, token)


def strip_quals(part):
    """'SB RFI' -> 'SB'; 'BB 3bet' -> 'BB'; 'UTG/UTG+1' kept."""
    words = [w for w in part.split() if w not in QUALIFIERS]
    return " ".join(words).strip()


def parse_title(tab, title):
    """Return (hero, villain, actionSet, label)."""
    if " vs " not in title:                       # RFI: title is the hero position
        hero = normalize_pos(title)
        action_set = "rfi_sb" if hero == "SB" else "rfi"
        return hero, None, action_set, hero
    left, right = title.split(" vs ", 1)
    is_limp = "Limp" in left or "Limp" in right
    hero = normalize_pos(strip_quals(left))
    villain_raw = strip_quals(right)
    villain = "/".join(normalize_pos(v) for v in villain_raw.split("/"))
    if is_limp:
        return hero, villain, "sb_limp_vs_bb", "SB Limp vs BB Raise"
    label = f"{hero} vs {villain}"
    return hero, villain, tab, label


# --- image / lattice -------------------------------------------------------
def page_section_tab(page):
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            size = max(s["size"] for s in ln["spans"])
            txt = "".join(s["text"] for s in ln["spans"]).strip()
            if size > 24:                          # the big section header
                for key, tab in SECTION_TAB.items():
                    if key in txt:
                        return tab
    return None


def chart_titles(page):
    """16pt title lines as (cx, top, text)."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            size = max(s["size"] for s in ln["spans"])
            txt = "".join(s["text"] for s in ln["spans"]).strip()
            if 15.0 <= size <= 20.0 and txt:
                x0, y0, x1, y1 = ln["bbox"]
                out.append(((x0 + x1) / 2, y0, txt))
    return out


def match_title(img_bbox, titles):
    """Nearest title above the image by x-center."""
    icx = (img_bbox[0] + img_bbox[2]) / 2
    itop = img_bbox[1]
    best, bestd = None, 1e9
    for cx, top, txt in titles:
        if top > itop:                             # title must be above image
            continue
        d = abs(cx - icx) + 0.05 * (itop - top)
        if d < bestd:
            bestd, best = d, txt
    return best


def detect_lattice(A):
    H, W, _ = A.shape
    gray = A.mean(axis=2)
    nonwhite = gray < 235
    grid_h = min(W, H)                             # grid is a square at the top
    colp = nonwhite[:grid_h].sum(axis=0)
    rowp = nonwhite[:grid_h].sum(axis=1)

    def span(proj, thr):
        idx = np.where(proj > thr)[0]
        return int(idx[0]), int(idx[-1])

    cx0, cx1 = span(colp, grid_h * 0.15)
    ry0, ry1 = span(rowp, W * 0.15)

    def centers(a, b):
        pitch = (b - a) / 13
        return [int(round(a + pitch * (k + 0.5))) for k in range(13)]

    return centers(cx0, cx1), centers(ry0, ry1)


def classify_cell(A, y, x, r=15):
    """Pixel-vote a cell into V/B/C/F.

    Median-sampling a single patch is fooled by the white hand-label glyph at
    the cell centre and by the thick dark border of "notable" cells (which
    desaturates the fill). Instead we count clearly-tinted pixels across the
    cell interior and take the majority hue, ignoring near-white text and
    near-black border pixels.
    """
    patch = A[y - r:y + r, x - r:x + r].reshape(-1, 3).astype(int)
    R, G, B = patch[:, 0], patch[:, 1], patch[:, 2]
    mx = patch.max(1)
    notdark = mx > 60                              # drop border pixels
    red = notdark & (R >= G) & (R >= B) & (R - np.maximum(G, B) > 15)
    blue = notdark & (B >= R) & (B >= G) & (B - np.maximum(R, G) > 15)
    green = notdark & (G >= R) & (G >= B) & (G - np.maximum(R, B) > 15)
    cnt = {"V": int(red.sum()), "B": int(blue.sum()), "C": int(green.sum())}
    best = max(cnt, key=cnt.get)
    return best if cnt[best] > patch.shape[0] * 0.06 else "F"


def iter_charts(doc):
    """Yield (page_index, hero, villain, action_set, label, image_array) for
    every chart in the PDF. Shared by extraction and verification."""
    for pi in range(doc.page_count):
        page = doc[pi]
        tab = page_section_tab(page)
        if tab is None:
            continue
        titles = chart_titles(page)
        blocks = [b for b in page.get_text("dict")["blocks"] if b["type"] == 1]
        blocks.sort(key=lambda b: (round(b["bbox"][1] / 50), b["bbox"][0]))
        for b in blocks:
            title = match_title(b["bbox"], titles)
            if not title:
                print(f"  WARN p{pi}: no title for image {b['bbox']}", file=sys.stderr)
                continue
            hero, villain, action_set, label = parse_title(tab, title)
            A = np.asarray(Image.open(io.BytesIO(b["image"])).convert("RGB"))
            yield pi, tab, hero, villain, action_set, label, A


def classify_chart(A, action_set):
    """Return (hands dict, comboCounts) for one chart image."""
    xs, ys = detect_lattice(A)
    sem2act = SEM_TO_ACTION[action_set]
    hands, counts = {}, {a: 0 for a in ACTION_SETS[action_set]}
    for i in range(13):
        for j in range(13):
            h = hand_name(i, j)
            act = sem2act[classify_cell(A, ys[i], xs[j])]
            hands[h] = act
            counts[act] += combos(h)
    return hands, counts


def extract():
    doc = fitz.open(PDF)
    situations = []
    for pi, tab, hero, villain, action_set, label, A in iter_charts(doc):
        hands, counts = classify_chart(A, action_set)
        situations.append({
            "tab": tab, "hero": hero, "villain": villain,
            "actionSet": action_set, "label": label,
            "hands": hands, "comboCounts": counts,
        })
        print(f"p{pi} {label:24s} {action_set:14s} {counts}")
    return situations


def main():
    situations = extract()
    out = {
        "meta": {
            "source": "PokerCoaching full-preflop-charts.pdf",
            "assumptions": ("100bb eff, ante; IP 2.5bb open / 3bet x3 / 4bet x2.5; "
                            "OOP 3.5bb open / 3bet x3.5 / 4bet x2.75; applies ~50bb+"),
        },
        "ranks": list(RANKS),
        "hands": HANDS,
        "actionSets": ACTION_SETS,
        "actionLabels": ACTION_LABELS,
        "situations": situations,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\nwrote {len(situations)} situations -> {os.path.relpath(OUT)}")


if __name__ == "__main__":
    main()
