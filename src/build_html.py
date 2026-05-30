#!/usr/bin/env python3
"""Inline data/charts.json into the HTML template -> dist/poker-trainer.html.

The data must be embedded (not fetched) so the single file works from a
file:// double-click, where fetch() is blocked by CORS.
"""
import json
import os

HERE = os.path.dirname(__file__)
TEMPLATE = os.path.join(HERE, "..", "template", "poker-trainer.template.html")
DATA = os.path.join(HERE, "..", "data", "charts.json")
OUT = os.path.join(HERE, "..", "dist", "poker-trainer.html")
# also written to the repo root so GitHub Pages serves it at the site root URL
OUT_INDEX = os.path.join(HERE, "..", "index.html")


def main():
    with open(TEMPLATE) as f:
        html = f.read()
    with open(DATA) as f:
        data = json.load(f)
    # drop the per-hand verification field we don't need in the app, keep it lean
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    html = html.replace("{{CHARTS_JSON}}", blob)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    for path in (OUT, OUT_INDEX):
        with open(path, "w") as f:
            f.write(html)
    kb = os.path.getsize(OUT) / 1024
    print(f"wrote {os.path.relpath(OUT)} + {os.path.relpath(OUT_INDEX)} "
          f"({kb:.0f} KB, {len(data['situations'])} charts)")


if __name__ == "__main__":
    main()
