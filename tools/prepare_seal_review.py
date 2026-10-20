#!/usr/bin/env python3
"""Snapshot selected candidate sources and render their actual Regular400 font.

Private proof generation never grants acceptance or modifies native drawings.
Snapshots prevent ongoing parallel generation from changing an in-flight proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from build_stroke_font import build_all
from seal_repertoire_status import codepoint, geometry_sha256

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(points: list[int], output: Path, root: Path = ROOT) -> dict:
    if not points or len(set(points)) != len(points):
        raise ValueError("Review codepoints must be nonempty and unique")
    if any(not 0x3D000 <= cp <= 0x3FC3F for cp in points):
        raise ValueError("Review codepoints must belong to the Small Seal block")
    if output.exists():
        raise ValueError("Use a new proof directory to preserve earlier review evidence")
    records = []
    # Read and verify every source before writing any proof files.
    for cp in sorted(points):
        stem = f"U{cp:05X}"
        source = root / "design/strokes-individual/candidates" / f"{stem}.json"
        native = root / "design/seal-individual" / f"{stem}.png"
        data = json.loads(source.read_text())
        native_sha = digest(native)
        if codepoint(data["codepoint"]) != cp or data["source"]["sha256"] != native_sha:
            raise ValueError(f"{stem}: candidate geometry and current native drawing differ")
        records.append((cp, source, native, data, native_sha))
    snapshot = output / "sources"
    snapshot.mkdir(parents=True)
    for cp, source, native, data, native_sha in records:
        (snapshot / source.name).write_text(json.dumps(data, indent=2) + "\n")
    font_output = output / "font"
    build_all(snapshot, font_output, family="Small Seal Review", font_stroke_width=30,
              normalization_extent=738)
    ttf = font_output / "SmallSealReview-Regular.ttf"
    font = ImageFont.truetype(str(ttf), 1024)
    report = {"schema_version": 1, "purpose": "Private Regular400 review proof; not acceptance",
              "font": str(ttf), "font_sha256": digest(ttf), "glyphs": []}
    for cp, source, native, data, native_sha in records:
        raster = output / f"U{cp:05X}-Regular400.png"
        image = Image.new("RGB", (1280, 1280), "white")
        ImageDraw.Draw(image).text((128, 1040), chr(cp), font=font, fill="black", anchor="ls")
        image.save(raster)
        report["glyphs"].append({"codepoint": f"U+{cp:05X}",
                                "source": str(source), "source_png_sha256": native_sha,
                                "geometry_sha256": geometry_sha256(data),
                                "raster": str(raster), "raster_sha256": digest(raster)})
    (output / "proof.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("codepoints", nargs="+", type=codepoint)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = prepare(args.codepoints, args.output)
    print(f"Prepared {len(report['glyphs'])} actual-font review proofs in {args.output}")


if __name__ == "__main__":
    main()
