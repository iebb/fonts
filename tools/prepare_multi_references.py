#!/usr/bin/env python3
"""Prepare private four-specimen visual references from the Unicode chart.

The PDF's displayed Unicode labels identify each row. Large glyph spans are
matched to the THX, CCZ, QJZ, and DYC columns in that same row. Small radical
and source annotations are excluded. Blank source columns remain unavailable;
another column is never substituted for them. This tool renders PDF regions
for visual reference and does not extract embedded font files or outlines.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import fitz


ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ("THX", "CCZ", "QJZ", "DYC")
# Source-column centers relative to the hexadecimal row label's left edge.
# The same layout repeats in each of the chart's three large table columns.
COLUMN_CENTERS = {"THX": 46.4, "CCZ": 73.0, "QJZ": 99.7, "DYC": 126.4}
CHART_URL = "https://www.unicode.org/charts/PDF/U3D000.pdf"


def page_spans(page: fitz.Page) -> list[dict]:
    return [span for block in page.get_text("dict")["blocks"] if "lines" in block
            for line in block["lines"] for span in line["spans"]]


def index_chart(pdf: Path, start: int, count: int) -> dict:
    records = {}
    stop = start + count
    with fitz.open(pdf) as document:
        for page_number, page in enumerate(document, 1):
            spans = page_spans(page)
            labels = [span for span in spans
                      if span["font"] == "Arial"
                      and re.fullmatch(r"[0-9A-F]{5,6}", span["text"])
                      and start <= int(span["text"], 16) < stop
                      and span["bbox"][1] > 90]
            for label in labels:
                lx, ly = label["bbox"][:2]
                variants = {}
                for variant in VARIANTS:
                    cx = lx + COLUMN_CENTERS[variant]
                    candidates = [span for span in spans
                                  if span["size"] >= 18 and span["text"].strip()
                                  and abs((span["bbox"][0] + span["bbox"][2]) / 2 - cx) < 12
                                  and abs((span["bbox"][1] + span["bbox"][3]) / 2 - (ly + 10)) < 12]
                    if len(candidates) > 1:
                        raise ValueError(f"U+{label['text']} {variant}: ambiguous glyph spans")
                    if not candidates:
                        variants[variant] = {"available": False, "reason": "blank source column in chart"}
                        continue
                    span = candidates[0]
                    bbox = list(map(float, span["bbox"]))
                    annotations = [annotation for annotation in spans
                                   if annotation["font"] == "UnihanInfo"
                                   and abs((annotation["bbox"][0] + annotation["bbox"][2]) / 2 - cx) < 12]
                    current_annotations = [annotation for annotation in annotations
                                           if 20 < annotation["bbox"][1] - ly < 28]
                    previous_annotations = [annotation for annotation in annotations
                                            if 0 < ly - annotation["bbox"][1] < 12]
                    # Font metric boxes are not reliable ink bounds: CCZ ink can
                    # descend beyond its span box, whose top can include the
                    # preceding row's source-ID text. Use the displayed source
                    # column between adjacent annotation rows instead. This
                    # retains overhanging glyph ink without copying source IDs.
                    top = max((annotation["bbox"][3] + .35 for annotation in previous_annotations),
                              default=ly - 3.8)
                    bottom = min((annotation["bbox"][1] - .35 for annotation in current_annotations),
                                 default=ly + 23.6)
                    crop = [cx - 12.5, top, cx + 12.5, bottom]
                    source_labels = [annotation["text"] for annotation in current_annotations]
                    variants[variant] = {
                        "available": True,
                        "page": page_number,
                        "font": span["font"],
                        "font_size": span["size"],
                        "bbox": bbox,
                        "crop_bbox": crop,
                        "source_label": source_labels[0] if len(source_labels) == 1 else None,
                    }
                records[label["text"]] = {
                    "codepoint": f"U+{label['text']}",
                    "page": page_number,
                    "label_bbox": list(label["bbox"]),
                    "variants": variants,
                }
            if len(records) == count:
                break
    missing = [f"U+{cp:05X}" for cp in range(start, stop) if f"{cp:05X}" not in records]
    if missing:
        raise ValueError(f"Chart row labels not found: {', '.join(missing)}")
    return {
        "chart_url": CHART_URL,
        "chart_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "purpose": "Private visual reference; four chart specimens per character where available; no font outlines extracted",
        "variant_order": list(VARIANTS),
        "glyphs": records,
    }


def insert_specimen(document: fitz.Document, sheet: fitz.Page, record: dict,
                    target: fitz.Rect) -> None:
    if not record["available"]:
        baseline = target.y0 + target.height / 2
        sheet.insert_textbox(fitz.Rect(target.x0, baseline - 12, target.x1, baseline + 20),
                             "UNAVAILABLE", fontsize=16, fontname="helv", align=1,
                             color=(.55, .55, .55))
        return
    page = document[record["page"] - 1]
    raster = page.get_pixmap(matrix=fitz.Matrix(14, 14),
                             clip=fitz.Rect(record["crop_bbox"]), alpha=False)
    sheet.insert_image(target, pixmap=raster, keep_proportion=True)


def render_batch(pdf: Path, index: dict, start: int, output: Path, size: int = 2400) -> dict:
    if size < 1600:
        raise ValueError("Reference sheets need at least 1600 pixels per side")
    unit = size / 4
    records = []
    with fitz.open(pdf) as document, fitz.open() as rendered:
        sheet = rendered.new_page(width=size, height=size)
        for slot, codepoint in enumerate(range(start, start + 16)):
            record = index["glyphs"][f"{codepoint:05X}"]
            x, y = slot % 4 * unit, slot // 4 * unit
            group_rect = fitz.Rect(x + 1, y + 1, x + unit - 1, y + unit - 1)
            sheet.draw_rect(group_rect, color=(.82, .82, .82), width=.8)
            sheet.insert_text((x + unit * .04, y + unit * .062),
                              f"U+{codepoint:05X}", fontsize=unit * .043,
                              fontname="hebo", color=(.15, .15, .15))
            placement = {}
            for variant_index, variant in enumerate(VARIANTS):
                col, row = variant_index % 2, variant_index // 2
                sx, sy = x + col * unit / 2, y + row * unit * .46
                label_rect = fitz.Rect(sx + .03 * unit, sy + .095 * unit,
                                       sx + .47 * unit, sy + .165 * unit)
                sheet.insert_textbox(label_rect, variant, fontsize=unit * .032,
                                     fontname="helv", align=1, color=(.35, .35, .35))
                specimen_rect = fitz.Rect(sx + .065 * unit, sy + .175 * unit,
                                          sx + .435 * unit, sy + .475 * unit)
                insert_specimen(document, sheet, record["variants"][variant], specimen_rect)
                placement[variant] = list(specimen_rect)
            records.append({**record, "row": slot // 4, "column": slot % 4,
                            "group_bbox": list(group_rect), "specimen_sheet_bboxes": placement})
        output.parent.mkdir(parents=True, exist_ok=True)
        sheet.get_pixmap(alpha=False).save(output)
    metadata = {key: value for key, value in index.items() if key != "glyphs"}
    metadata.update({"sheet_size": [size, size],
                     "layout": "4x4 codepoint groups; each group is THX/CCZ above QJZ/DYC",
                     "glyphs": records})
    output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def render_overview(pdf: Path, index: dict, codepoint: int, output: Path) -> None:
    record = index["glyphs"][f"{codepoint:05X}"]
    with fitz.open(pdf) as document, fitz.open() as rendered:
        sheet = rendered.new_page(width=1600, height=520)
        sheet.insert_text((30, 42), f"U+{codepoint:05X} - four chart specimens", fontsize=28,
                          fontname="hebo", color=(.15, .15, .15))
        for slot, variant in enumerate(VARIANTS):
            x = slot * 400
            sheet.insert_textbox(fitz.Rect(x + 20, 65, x + 380, 108), variant,
                                 fontsize=24, align=1, color=(.35, .35, .35))
            insert_specimen(document, sheet, record["variants"][variant],
                            fitz.Rect(x + 55, 115, x + 345, 445))
            item = record["variants"][variant]
            caption = item.get("source_label") or ("blank in chart" if not item["available"] else "")
            sheet.insert_textbox(fitz.Rect(x + 20, 475, x + 380, 505), caption,
                                 fontsize=17, align=1, color=(.4, .4, .4))
        sheet.get_pixmap(alpha=False).save(output)
    output.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n")


def parse_codepoint(value: str) -> int:
    return int(value.removeprefix("U+").removeprefix("0x"), 16)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=ROOT / "reference/seal/U3D000.pdf")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reference/seal/consensus")
    parser.add_argument("--start", type=parse_codepoint, default=0x3D000)
    parser.add_argument("--count", type=int, default=64)
    parser.add_argument("--sheet-size", type=int, default=2400)
    parser.add_argument("--overview", type=parse_codepoint, default=0x3D001)
    args = parser.parse_args()
    if args.count <= 0 or args.count % 16:
        parser.error("--count must be a positive multiple of sixteen")
    index = index_chart(args.pdf, args.start, args.count)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "chart-index.json").write_text(json.dumps(index, indent=2) + "\n")
    for start in range(args.start, args.start + args.count, 16):
        output = args.output_dir / f"reference-{start:05X}-{start + 15:05X}.png"
        metadata = render_batch(args.pdf, index, start, output, args.sheet_size)
        available = sum(specimen["available"] for record in metadata["glyphs"]
                        for specimen in record["variants"].values())
        print(f"{output}: {available}/64 chart specimens available")
    if args.start <= args.overview < args.start + args.count:
        overview = args.output_dir / f"reference-{args.overview:05X}-four-sources.png"
        render_overview(args.pdf, index, args.overview, overview)
        print(overview)


if __name__ == "__main__":
    main()
