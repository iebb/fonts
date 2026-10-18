#!/usr/bin/env python3
"""Build a weight axis by varying only the radius of editable pen strokes.

Every master uses the same centerlines and flattening. Rectangle and circle
vertices move with the radius, so masters retain compatible contour topology.
No outline-offset operation is used. Dense counters still need optical review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fontTools.designspaceLib import (
    AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor,
)
from fontTools.ttLib import TTFont
from fontTools.varLib import build
from fontTools.varLib.instancer import instantiateVariableFont

from build_stroke_font import ROOT, build_font, family_basename, load_sources


MASTERS = {300: ("Light", 30.0), 400: ("Regular", 43.0), 700: ("Bold", 65.0)}
INSTANCES = {300: "Light", 400: "Regular", 500: "Medium", 700: "Bold"}


def stroke_width(weight: float) -> float:
    if not 300 <= weight <= 700:
        raise ValueError("Weight must be between 300 and 700")
    return (30 + (weight - 300) * 13 / 100 if weight <= 400
            else 43 + (weight - 400) * 22 / 300)


def set_names(font: TTFont, family: str, style: str, weight: int) -> None:
    basename = family_basename(family)
    values = {
        1: family, 2: style, 3: f"{basename};0.4;{style}",
        4: f"{family} {style}", 5: "Version 0.4; centerline width prototype",
        6: f"{basename}-{style}", 16: family, 17: style,
        10: ("Rounded uniform-width strokes. All weight masters use identical "
             "centerline trajectories. Character forms require specialist review."),
        13: "Licensed under the SIL Open Font License, Version 1.1.",
        14: "https://openfontlicense.org/",
    }
    for name_id, value in values.items():
        for platform, encoding, language in [(3, 1, 0x409), (1, 0, 0)]:
            font["name"].setName(value, name_id, platform, encoding, language)
    font["OS/2"].usWeightClass = weight
    font["OS/2"].fsSelection &= ~((1 << 5) | (1 << 6))
    font["head"].macStyle &= ~1
    if weight >= 700:
        font["OS/2"].fsSelection |= 1 << 5
        font["head"].macStyle |= 1
    elif weight == 400:
        font["OS/2"].fsSelection |= 1 << 6
    font.recalcTimestamp = False


def topology(font: TTFont) -> dict:
    return {
        name: (tuple(font["glyf"][name].endPtsOfContours),
               tuple(int(flag) & 1 for flag in font["glyf"][name].flags))
        for name in font.getGlyphOrder() if font["glyf"][name].numberOfContours > 0
    }


def build_variable(source_root: Path, output: Path,
                   family: str = "Panorama Gothic Seal Individual Variable") -> dict:
    sources = load_sources(source_root)
    output.mkdir(parents=True, exist_ok=True)
    master_dir = output / "masters"
    master_dir.mkdir(exist_ok=True)
    (master_dir / "manifest.json").write_text(json.dumps({
        "coverage_eligible": False, "status": "prototype_masters",
        "reason": "Weight masters of an experimental centerline sample.",
    }, indent=2) + "\n")
    basename = family_basename(family)
    master_paths = {}
    master_fonts = {}
    expected_topology = None
    for weight, (style, width) in MASTERS.items():
        path = master_dir / f"{basename}-{style}.ttf"
        build_font(sources, path, family, width)
        font = TTFont(path)
        set_names(font, family, style, weight)
        actual_topology = topology(font)
        if expected_topology is not None and actual_topology != expected_topology:
            raise ValueError(f"Incompatible stroke topology in {style} master")
        expected_topology = actual_topology
        master_fonts[weight], master_paths[weight] = font, path

    # Keep line metrics constant throughout the axis.
    ascent = max(font["hhea"].ascent for font in master_fonts.values())
    descent = min(font["hhea"].descent for font in master_fonts.values())
    for weight, font in master_fonts.items():
        font["hhea"].ascent, font["hhea"].descent = ascent, descent
        font["OS/2"].sTypoAscender, font["OS/2"].sTypoDescender = ascent, descent
        font["OS/2"].usWinAscent, font["OS/2"].usWinDescent = ascent, -descent
        font.save(master_paths[weight])

    document = DesignSpaceDocument()
    axis = AxisDescriptor()
    axis.name, axis.tag = "Weight", "wght"
    axis.minimum, axis.default, axis.maximum = 300, 400, 700
    document.addAxis(axis)
    for weight, path in master_paths.items():
        source = SourceDescriptor()
        source.path, source.name = str(path.resolve()), MASTERS[weight][0]
        source.familyName, source.styleName = family, MASTERS[weight][0]
        source.location = {"Weight": weight}
        if weight == 400:
            source.copyInfo = source.copyLib = source.copyFeatures = True
        document.addSource(source)
    for weight, style in INSTANCES.items():
        instance = InstanceDescriptor()
        instance.name, instance.familyName, instance.styleName = style, family, style
        instance.location = {"Weight": weight}
        document.addInstance(instance)
    designspace_path = output / f"{basename}.designspace"
    document.write(designspace_path)
    variable, _, _ = build(document)
    variable.recalcTimestamp = False
    variable_path = output / f"{basename}.ttf"
    variable.save(variable_path)
    files = [variable_path, designspace_path]
    for weight, style in INSTANCES.items():
        instance = instantiateVariableFont(variable, {"wght": weight}, inplace=False)
        set_names(instance, family, style, weight)
        path = output / f"{basename}-{style}.ttf"
        instance.save(path)
        files.append(path)
    variable.flavor = "woff"
    browser_path = variable_path.with_suffix(".woff")
    variable.save(browser_path)
    files.append(browser_path)
    report = {
        "family": family, "status": "prototype_unverified", "production_ready": False,
        "coverage_eligible": False, "glyph_count": len(sources),
        "axis": {"tag": "wght", "minimum": 300, "default": 400, "maximum": 700},
        "construction": "Same editable centerlines; only the common pen radius changes.",
        "outline_offsets_used": False, "centerline_geometry_changes_with_weight": False,
        "widths_font_units": {str(weight): stroke_width(weight) for weight in INSTANCES},
        "limitations": ["Dense counters and spacing need optical review.",
                        "Inferred paths do not establish historical writing order."],
        "sources": [{"codepoint": f"U+{s['codepoint']:05X}",
                     "centerline_file": str(s["path"].relative_to(ROOT))
                     if s["path"].is_relative_to(ROOT) else str(s["path"]),
                     "sha256": hashlib.sha256(s["path"].read_bytes()).hexdigest()}
                    for s in sources],
        "files": [{"name": p.name, "bytes": p.stat().st_size,
                   "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files],
    }
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT / "design/strokes-individual")
    parser.add_argument("--output", type=Path, default=ROOT / "fonts/seal-individual-variable")
    parser.add_argument("--family", default="Panorama Gothic Seal Individual Variable")
    args = parser.parse_args()
    report = build_variable(args.source_root, args.output, args.family)
    print(f"Built {report['glyph_count']} glyphs with a centerline width axis in {args.output}")


if __name__ == "__main__":
    main()
