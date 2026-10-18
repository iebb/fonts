#!/usr/bin/env python3
"""Prepare private raster references for an ImageGen redraw, never font outlines.

The Unicode chart is not redistributed by this project. Each indexed record
points to a representative drawing on the chart; Unicode values come from the
chart's labels, not the PDF's legacy font encodings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def index_chart(pdf: Path) -> dict:
    import fitz

    records = {}
    with fitz.open(pdf) as document:
        for page_number, page in enumerate(document):
            spans = [s for b in page.get_text("dict")["blocks"] if "lines" in b
                     for line in b["lines"] for s in line["spans"]]
            labels = [s for s in spans if re.fullmatch(r"3[D-F][0-9A-F]{3}", s["text"])
                      and s["font"] == "Arial" and s["bbox"][1] > 90
                      and 0x3D000 <= int(s["text"], 16) <= 0x3FC3F]
            for label in labels:
                lx, ly = label["bbox"][:2]
                candidates = [s for s in spans
                              if lx + 33 < s["bbox"][0] < lx + 140
                              and abs(s["bbox"][1] - (ly - 1.73)) < 8
                              and s["size"] >= 18 and s["text"].strip()]
                candidates.sort(key=lambda s: (s["font"] != "CMEXShuowenSeal", s["bbox"][0]))
                if not candidates:
                    continue
                span = candidates[0]
                bbox = list(span["bbox"])
                bbox[0] -= .5
                bbox[2] += .5
                bbox[1] += 1
                bbox[3] -= 1
                records[label["text"]] = {"page": page_number + 1,
                                          "bbox": bbox, "reference_column": span["font"]}
    return {"chart_url": "https://www.unicode.org/charts/PDF/U3D000.pdf",
            "chart_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
            "purpose": "Private visual reference; no embedded font outlines extracted",
            "glyphs": records}


def render_batch(pdf: Path, index: dict, start: int, count: int, output: Path) -> None:
    import fitz

    if count != 16:
        raise ValueError("This redraw workflow uses exactly sixteen cells (4 by 4).")
    records = []
    with fitz.open(pdf) as document, fitz.open() as rendered:
        sheet = rendered.new_page(width=1200, height=1200)
        for slot, cp in enumerate(range(start, start + count)):
            record = index["glyphs"][f"{cp:05X}"]
            page = document[record["page"] - 1]
            raster = page.get_pixmap(matrix=fitz.Matrix(12, 12), clip=fitz.Rect(record["bbox"]), alpha=False)
            x, y = slot % 4 * 300, slot // 4 * 300
            sheet.insert_image(fitz.Rect(x + 46, y + 20, x + 254, y + 248), pixmap=raster, keep_proportion=True)
            sheet.insert_text((x + 98, y + 280), f"U+{cp:05X}", fontsize=18, color=(.25, .25, .25))
            records.append({"codepoint": f"U+{cp:05X}", "row": slot // 4, "column": slot % 4, **record})
        output.parent.mkdir(parents=True, exist_ok=True)
        sheet.get_pixmap().save(output)
    output.with_suffix(".json").write_text(json.dumps({"chart_url": index["chart_url"], "glyphs": records}, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=Path("reference/seal/U3D000.pdf"))
    parser.add_argument("--index", type=Path, default=Path("reference/seal/chart-index.json"))
    parser.add_argument("--start", type=lambda value: int(value.removeprefix("U+"), 16))
    parser.add_argument("--count", type=int, default=16)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.index.exists():
        index = json.loads(args.index.read_text())
    else:
        index = index_chart(args.pdf)
        args.index.parent.mkdir(parents=True, exist_ok=True)
        args.index.write_text(json.dumps(index, indent=2) + "\n")
    if args.start is not None:
        dest = args.output or args.index.parent / f"reference-{args.start:05X}-{args.start + args.count - 1:05X}.png"
        render_batch(args.pdf, index, args.start, args.count, dest)
        print(dest)
    print(f"Indexed {len(index['glyphs']):,} chart glyphs.")


if __name__ == "__main__":
    main()
