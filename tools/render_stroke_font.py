#!/usr/bin/env python3
"""Render a specimen using the actual built centerline font, not source images."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]


def render(font_path: Path, output: Path, sample_codepoint: int = 0x3D001) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    font = TTFont(font_path)
    codepoints = sorted(font.getBestCmap())
    family = font["name"].getDebugName(1)
    units = font["head"].unitsPerEm
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    widths = sorted({glyph["stroke_width_font_units"] for glyph in manifest.get("glyphs", [])})
    manual_count = sum(glyph["status"] == "manual_geometry_reviewed" for glyph in manifest.get("glyphs", []))
    label_path = ROOT / "fonts/noto/PanoramaGothic-Regular.ttf"
    label = ImageFont.truetype(str(label_path), 21)
    title = ImageFont.truetype(str(label_path), 43)
    subtitle = ImageFont.truetype(str(label_path), 25)
    columns, cell, margin, header, footer = 8, 270, 40, 170, 100
    rows = math.ceil(len(codepoints) / columns)
    image = Image.new("RGB", (columns * cell + 2*margin, header + rows*cell + footer), "white")
    draw = ImageDraw.Draw(image)
    draw.text((margin, 35), family, fill="#171717", font=title)
    width_note = f" · {widths[0]:g}-unit strokes" if len(widths) == 1 else ""
    draw.text((margin, 100), f"{len(codepoints)} glyphs · Rounded centerline construction{width_note}",
              fill="#666666", font=subtitle)
    em_size = 248
    specimen = ImageFont.truetype(str(font_path), em_size)
    for index, codepoint in enumerate(codepoints):
        left = margin + index % columns * cell
        top = header + index // columns * cell
        baseline = top + 7 + 832 / units * em_size
        draw.text((left + (cell-em_size)/2, baseline), chr(codepoint),
                  fill="#101010", font=specimen, anchor="ls")
        draw.text((left + cell/2, top + cell - 14), f"U+{codepoint:05X}",
                  fill="#666666", font=label, anchor="ms")
    note = (f"Prototype: {manual_count} manual corrections, "
            f"{len(codepoints)-manual_count} automatic traces. "
            "Proportionally normalized; historical writing order is not encoded.")
    draw.text((margin, header + rows*cell + 30), note, fill="#666666", font=label)
    preview = output / "preview-64.png"
    image.save(preview, dpi=(200, 200))

    files = [preview]
    if sample_codepoint in codepoints:
        sample = Image.new("RGB", (1104, 1104), "white")
        sample_font = ImageFont.truetype(str(font_path), 1024)
        ImageDraw.Draw(sample).text((40, 40 + 832), chr(sample_codepoint), fill="#101010",
                                   font=sample_font, anchor="ls")
        sample_path = output / f"U{sample_codepoint:05X}.png"
        sample.save(sample_path, dpi=(200, 200))
        files.append(sample_path)
        source_svg = output / "centerlines" / f"U{sample_codepoint:05X}.svg"
        if source_svg.exists():
            sample_svg = output / f"U{sample_codepoint:05X}.svg"
            shutil.copyfile(source_svg, sample_svg)
            files.append(sample_svg)

    report = {
        "family": family, "glyph_count": len(codepoints),
        "coverage_eligible": False,
        "rendered_from": str(font_path.relative_to(ROOT)) if font_path.is_relative_to(ROOT) else str(font_path),
        "font_sha256": hashlib.sha256(font_path.read_bytes()).hexdigest(),
        "rasterizer": "Pillow / FreeType; actual TTF cmap glyphs",
        "source_images_used_for_rendering": False,
        "files": [{"name": path.name, "bytes": path.stat().st_size,
                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in files],
    }
    (output / "preview-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(preview)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path,
                        default=ROOT / "fonts/seal-individual/PanoramaGothicSealIndividual-Regular.ttf")
    parser.add_argument("--output", type=Path, default=ROOT / "fonts/seal-individual")
    parser.add_argument("--sample-codepoint", type=lambda value: int(value.removeprefix("U+"), 16),
                        default=0x3D001)
    args = parser.parse_args()
    render(args.font, args.output, args.sample_codepoint)


if __name__ == "__main__":
    main()
