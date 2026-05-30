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
ICON = os.path.join(HERE, "..", "assets", "icon.png")
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


def main():
    with open(TEMPLATE) as f:
        html = f.read()
    with open(DATA) as f:
        data = json.load(f)
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    html = html.replace("{{CHARTS_JSON}}", blob)
    html = html.replace("{{FAVICON}}", favicon_datauri())
    write_apple_icons()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    for path in (OUT, OUT_INDEX):
        with open(path, "w") as f:
            f.write(html)
    kb = os.path.getsize(OUT) / 1024
    print(f"wrote {os.path.relpath(OUT)} + {os.path.relpath(OUT_INDEX)} "
          f"+ apple-touch-icon.png ({kb:.0f} KB, {len(data['situations'])} charts)")


if __name__ == "__main__":
    main()
