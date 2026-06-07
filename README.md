# Preflop Charts Trainer

A flashcard trainer for memorising preflop charts. Pick an **effective stack**, a
**situation tab**, get dealt a random position + hand, and answer with the correct
action. Tracks weak spots and drills them harder.

Two chart sources, switched by the **stack dropdown**:
- **100BB · 캐시** — the verified [PokerCoaching full preflop charts](https://poker-coaching.s3.amazonaws.com/tools/preflop-charts/full-preflop-charts.pdf)
  (RFI / Facing RFI / RFI vs 3-bet). One action per hand, full-granularity answers
  (value 3-bet vs bluff 3-bet vs call vs fold).
- **80 / 50 / 30 / 20 / 12BB · 토너먼트** — the
  [PokerCoaching Ultimate Tournament Preflop Guide](https://www.pokercoaching.com)
  (RFI / Facing RFI / RFI vs 3-Bet / **RFI vs 4-Bet**). These are *mixed-frequency*
  GTO-Wizard-style charts: each hand is a blend (e.g. *3-Bet 55% / Call 45%*), so
  the quiz reveals the full mix and scores you on picking the most-frequent action.

The deliverable is a single self-contained file: **`dist/poker-trainer.html`**.
Double-click it to open in any browser (works from `file://`, no server) or host
it on GitHub Pages.

## Features
- **Stack dropdown** — 100BB cash + five tournament effective stacks, unified.
- **Tabs** — RFI, Facing RFI, RFI vs 3-bet, and (tournament only) RFI vs 4-bet.
- **Quiz** — random position+hand from the selected filter; instant feedback;
  keyboard 1–4 to answer, Space for next. Cash: full-granularity single answer.
  Tournament: pick an action, then see the **mixed-frequency** breakdown (best
  action starred; *정답/차선/오답* by the chosen action's frequency).
- **Scenarios** — tournament matchups that differ by scenario are kept distinct in
  the matchup dropdown: *BB vs SB · RFI* vs *· Limp*, *X vs Y · 4-Bet* vs
  *· 4-Bet All-In*.
- **약점 집중 (SRS)** — unseen and previously-wrong hands are served more often.
- **통계** — overall accuracy + weakest spots, persisted in `localStorage`.
- **차트 열람** — view any full 13×13 chart. Cash shows the combo-count legend;
  tournament renders each cell as proportional action-frequency colour bands.

## Project layout
```
data/charts.json        # cash (100BB) chart data — editable source of truth
data/tournament.json    # tournament charts (5 stacks) — full-precision source of truth
src/extract_charts.py       # cash PDF -> charts.json (renders each chart JPEG, samples cells)
src/extract_tournament.py   # tournament PDF -> tournament.json (mixed-freq cell bands)
src/verify_charts.py        # cash side-by-side verification sheets into verify/
src/verify_tournament.py    # tournament original|reconstruction sheets into verify/tournament/
src/audit_tournament.py     # per-cell cross-method audit of the tournament extraction
src/build_html.py           # inlines + COMPACTS the data into the template -> dist/
template/poker-trainer.template.html   # the app (HTML/CSS/vanilla JS)
dist/poker-trainer.html # built single-file app  <-- open this
```

## Rebuilding from the PDFs
Needs Python with `pymupdf`, `numpy`, `pillow`. The source PDFs are expected at
`~/Downloads/full-preflop-charts.pdf` (cash) and
`~/Downloads/personal/poker/preflop-charts.pdf` (tournament).

```bash
python src/extract_charts.py       # -> data/charts.json
python src/extract_tournament.py   # -> data/tournament.json  (all 5 stacks)
python src/build_html.py           # -> dist/poker-trainer.html
# optional: visual QA sheets (needs the PDFs)
python src/verify_charts.py        # -> verify/page_NN.png
python src/verify_tournament.py 80BB   # -> verify/tournament/80BB_NN.png
```

If you ever spot a wrong cash cell, just edit `data/charts.json` (it is the source
of truth) and re-run `build_html.py` — no need to re-extract.

### Tournament data compaction
`data/tournament.json` is ~2 MB at full precision. Inlining that into the single
HTML file would bloat it, so `build_html.py` compacts it at build time: each cell's
`[fold, call, raise, allin]` frequency is quantised to 5% units (the raster
estimates are already approximate), and since only ~370 distinct vectors occur
across all 507 charts, every cell is stored as a fixed-width base36 index into a
global palette. Result: ~2 MB → ~220 KB. The template carries the matching decoder.

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

The **tournament** charts are harder: each cell is split into colour bands
proportional to action frequency (red=raise, green=call, dark maroon=all-in,
blue/near-black=fold). `extract_tournament.py` classifies every cell pixel by hue
and recovers a `[fold, call, raise, allin]` vector per hand (per-column majority,
with edge/gridline cleanup). Two independent extraction methods (column-majority
vs pixel-area) are cross-checked per cell by `audit_tournament.py`; remaining
disagreements are legitimately mixed/horizontal cells. Reconstruction sheets
(`verify_tournament.py`) place the original chart next to a re-rendered mix for
eyeballing. The frequencies are **approximate estimates** (the raster doesn't
invert cleanly to the printed legend %), and the app labels them as such.

> Cash charts assume 100bb effective with an ante (≈50bb+). Tournament charts are
> for the labelled effective stack with an ante. Both are sound defaults, not a
> substitute for situational/ICM adjustment.
