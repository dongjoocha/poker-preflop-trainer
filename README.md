# Preflop Charts Trainer

A flashcard trainer for memorising the **PokerCoaching full preflop charts**
(RFI / Facing RFI / RFI vs 3-bet). Pick a tab, get dealt a random
position + hand, and answer with the correct action — value 3-bet vs bluff
3-bet vs call vs fold, etc. Tracks weak spots and drills them harder.

The deliverable is a single self-contained file: **`dist/poker-trainer.html`**.
Double-click it to open in any browser (works from `file://`, no server) or host
it on GitHub Pages.

## Features
- **3 tabs** — RFI, Facing RFI, RFI vs 3-bet.
- **Quiz** — random position+hand from the selected filter; full-granularity
  answers (e.g. *3-bet for Value* vs *3-bet as a Bluff*); instant feedback;
  keyboard 1–4 to answer, Space for next.
- **약점 집중 (SRS)** — unseen and previously-wrong hands are served more often.
- **통계** — overall accuracy + weakest spots, persisted in `localStorage`.
- **차트 열람** — view any full 13×13 chart with the original combo-count legend.

## Project layout
```
data/charts.json   # extracted chart data — the editable single source of truth
src/extract_charts.py   # PDF -> charts.json (renders each chart JPEG, samples cells)
src/verify_charts.py    # renders side-by-side verification sheets into verify/
src/build_html.py       # inlines charts.json into the template -> dist/
template/poker-trainer.template.html   # the app (HTML/CSS/vanilla JS)
dist/poker-trainer.html # built single-file app  <-- open this
```

## Rebuilding from the PDF
Needs Python with `pymupdf`, `numpy`, `pillow`. The source PDF is expected at
`~/Downloads/full-preflop-charts.pdf`.

```bash
python src/extract_charts.py   # -> data/charts.json
python src/build_html.py       # -> dist/poker-trainer.html
# optional: visual QA sheets (needs the PDF)
python src/verify_charts.py    # -> verify/page_NN.png
```

If you ever spot a wrong cell, just edit `data/charts.json` (it is the source of
truth) and re-run `build_html.py` — no need to re-extract.

## How the data was extracted & verified
Each chart in the PDF is an embedded ~600px JPEG (a 13×13 hand matrix + a legend
printing exact combo counts per action). `extract_charts.py`:
1. matches each chart image to its title by position → `(tab, hero, villain)`,
2. finds the 13×13 lattice via a non-white projection bounding box,
3. classifies each cell by **pixel voting** over its interior (majority tinted
   hue → value/bluff/call; otherwise fold) — robust to the white hand-label
   glyph and the thick border on "notable" cells.

Verification: a second independent classifier (nearest-swatch on cell mean
colour) agrees with the voting classifier on **every coloured cell** across all
11,492 cells; the only differences are neutral-grey fold cells (correctly folded
by voting). Every chart's combo counts sum to 1326 and match the printed legend
on the spot-checked charts. Use **차트 열람** mode to eyeball any chart against
the original PDF.

> Charts assume 100bb effective with an ante (≈50bb+). They are a sound default,
> not a substitute for situational adjustment.
