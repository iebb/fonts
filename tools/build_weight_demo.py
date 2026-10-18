#!/usr/bin/env python3
"""Build a topology-compatible weight-axis study from the 64-glyph seal sample.

This is an experimental outline-weight study, not a finished typeface design.
The existing image-generation-derived Regular outlines are the default master.
All other masters preserve their contour, point and on/off-curve topology, using
small normal displacements. No bitmap source image is modified or regenerated.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import shutil
from pathlib import Path

import numpy as np
from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.varLib import build
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import label


ROOT = Path(__file__).resolve().parents[1]
FAMILY = "Panorama Gothic Seal Variable"
STYLES = {300: "Light", 400: "Regular", 500: "Medium", 700: "Bold"}
OFFSETS = {300: -4.5, 400: 0.0, 500: 3.0, 700: 8.0}


def _unit(vector):
    length = math.hypot(*vector)
    return (vector[0] / length, vector[1] / length) if length else (0.0, 0.0)


def _walk(points, index, direction, distance=4.0):
    """Find a nearby point by arc distance, avoiding tiny-segment tangent noise."""
    current = points[index]
    remaining = distance
    for step in range(1, len(points) + 1):
        following = points[(index + step * direction) % len(points)]
        length = math.dist(current, following)
        if length >= remaining and length:
            fraction = remaining / length
            return tuple(a + (b - a) * fraction for a, b in zip(current, following))
        remaining -= length
        current = following
    return current


def contour_normals(points):
    """Left-side normal offsets: TrueType filled material is on the right.

    The bounded miter keeps corners coherent without very long spikes. The
    original control points remain untouched at the default axis location.
    """
    result = []
    for index, point in enumerate(points):
        before, after = _walk(points, index, -1), _walk(points, index, 1)
        incoming = _unit((point[0] - before[0], point[1] - before[1]))
        outgoing = _unit((after[0] - point[0], after[1] - point[1]))
        first, second = (-incoming[1], incoming[0]), (-outgoing[1], outgoing[0])
        normal = _unit((first[0] + second[0], first[1] + second[1]))
        if normal == (0.0, 0.0):
            normal = first
        projection = abs(normal[0] * first[0] + normal[1] * first[1])
        miter = min(1.35, 1.0 / max(projection, 0.001))
        result.append((normal[0] * miter, normal[1] * miter))
    return result


def offset_glyph(glyph, amount):
    if not amount or glyph.numberOfContours <= 0:
        return
    points = list(glyph.coordinates)
    start = 0
    adjusted = []
    for end in glyph.endPtsOfContours:
        contour = points[start:end + 1]
        normals = contour_normals(contour)
        adjusted.extend((round(x + amount * nx), round(y + amount * ny))
                        for (x, y), (nx, ny) in zip(contour, normals))
        start = end + 1
    glyph.coordinates = GlyphCoordinates(adjusted)


def set_names(font, style, weight):
    names = font["name"]
    for name_id, value in {
        1: FAMILY,
        2: style,
        3: f"PanoramaGothicSealVariable;0.2;{style}",
        4: f"{FAMILY} {style}",
        5: "Version 0.2; experimental weight-axis prototype",
        6: f"PanoramaGothicSealVariable-{style}",
        10: "Experimental Small Seal outline-weight prototype. Glyph identities and script forms require specialist review.",
        16: FAMILY,
        17: style,
    }.items():
        for platform, encoding, language in [(3, 1, 0x409), (1, 0, 0)]:
            names.setName(value, name_id, platform, encoding, language)
    font["OS/2"].usWeightClass = weight
    font["OS/2"].fsSelection &= ~(1 << 5 | 1 << 6)
    font["head"].macStyle &= ~1
    if weight == 700:
        font["OS/2"].fsSelection |= 1 << 5
        font["head"].macStyle |= 1
    elif weight == 400:
        font["OS/2"].fsSelection |= 1 << 6


def topology(font_path, codepoints):
    """Count connected ink regions and counters at 2 px per font unit."""
    font = ImageFont.truetype(str(font_path), 2048)
    result = {}
    for codepoint in codepoints:
        image = Image.new("L", (2304, 2304))
        ImageDraw.Draw(image).text((128, 1920), chr(codepoint), fill=255, font=font, anchor="ls")
        mask = np.asarray(image) >= 128
        components = label(mask)[1]
        counters = label(~mask)[1] - 1
        result[codepoint] = (int(components), int(counters), int(mask.sum()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "fonts/seal-example/PanoramaGothicSealExample-Regular.ttf")
    parser.add_argument("--output", type=Path, default=ROOT / "fonts/seal-variable")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    masters = args.output / "masters"
    masters.mkdir(exist_ok=True)
    (masters / "manifest.json").write_text(json.dumps({
        "coverage_eligible": False, "status": "experimental weight masters",
    }, indent=2) + "\n")
    source = TTFont(args.source)
    codepoints = sorted(source.getBestCmap())
    assert codepoints == list(range(0x3D000, 0x3D040)), "Expected the complete 64-glyph example"
    cmap = source.getBestCmap()
    source_metrics = dict(source["hmtx"].metrics)
    source_coordinates = {name: list(source["glyf"][name].coordinates)
                          for name in cmap.values()}

    master_paths = {}
    for weight, style in STYLES.items():
        font = copy.deepcopy(source)
        set_names(font, style, weight)
        for name in cmap.values():
            glyph = font["glyf"][name]
            offset_glyph(glyph, OFFSETS[weight])
            glyph.recalcBounds(font["glyf"])
            # Advance widths remain fixed; bearings track the modified outlines.
            if weight != 400:
                font["hmtx"].metrics[name] = (source_metrics[name][0], glyph.xMin)
        path = masters / f"PanoramaGothicSealVariable-{style}.ttf"
        font.save(path)
        master_paths[weight] = path

    document = DesignSpaceDocument()
    axis = AxisDescriptor()
    axis.name, axis.tag = "Weight", "wght"
    axis.minimum, axis.default, axis.maximum = 300, 400, 700
    document.addAxis(axis)
    for weight, path in master_paths.items():
        descriptor = SourceDescriptor()
        descriptor.path = str(path)
        descriptor.name = STYLES[weight]
        descriptor.familyName, descriptor.styleName = FAMILY, STYLES[weight]
        descriptor.location = {"Weight": weight}
        if weight == 400:
            descriptor.copyInfo = descriptor.copyLib = descriptor.copyFeatures = True
        document.addSource(descriptor)
    for weight, style in STYLES.items():
        instance = InstanceDescriptor()
        instance.name = style
        instance.familyName, instance.styleName = FAMILY, style
        instance.location = {"Weight": weight}
        document.addInstance(instance)
    designspace_path = args.output / "PanoramaGothicSealVariable.designspace"
    document.write(designspace_path)
    variable, _, _ = build(document)
    variable_path = args.output / "PanoramaGothicSealVariable.ttf"
    variable.save(variable_path)

    outputs = {}
    for weight, style in STYLES.items():
        instance = instantiateVariableFont(variable, {"wght": weight}, inplace=False)
        set_names(instance, style, weight)
        path = args.output / f"PanoramaGothicSealVariable-{style}.ttf"
        instance.save(path)
        outputs[weight] = path
        reopened = TTFont(path)
        assert reopened.getBestCmap() == cmap
        assert all(reopened["hmtx"].metrics[name][0] == source_metrics[name][0] for name in cmap.values())
        assert all([flag & 1 for flag in reopened["glyf"][name].flags] ==
                   [flag & 1 for flag in source["glyf"][name].flags] and
                   reopened["glyf"][name].endPtsOfContours == source["glyf"][name].endPtsOfContours
                   for name in cmap.values())
        if weight == 400:
            assert reopened["hmtx"].metrics == source_metrics
            assert all(list(reopened["glyf"][name].coordinates) == source_coordinates[name] for name in cmap.values())

    reference = topology(outputs[400], codepoints)
    checked = {400: reference}
    for weight in (300, 500, 700):
        checked[weight] = topology(outputs[weight], codepoints)
    changes = {str(weight): [f"U+{cp:05X}" for cp in codepoints
                             if checked[weight][cp][:2] != reference[cp][:2]]
               for weight in (300, 500, 700)}
    if any(changes.values()):
        # Keep these findings explicit. Outline point compatibility does not
        # guarantee design topology or prove script-specific glyph correctness.
        print("Raster topology changes requiring design review:", changes)
    ink = {str(weight): sum(value[2] for value in checked[weight].values())
           for weight in STYLES}
    assert ink["300"] < ink["400"] < ink["500"] < ink["700"]
    reopened_variable = TTFont(variable_path)
    assert [(a.axisTag, a.minValue, a.defaultValue, a.maxValue) for a in reopened_variable["fvar"].axes] == [("wght", 300, 400, 700)]
    assert reopened_variable.getBestCmap() == cmap
    for filename in ("LICENSE-OFL.txt", "OFL-1.1.txt"):
        if (args.source.parent / filename).exists():
            shutil.copy2(args.source.parent / filename, args.output / filename)
    manifest = {
        "coverage_eligible": False,
        "status": "experimental outline-weight prototype; not a completed script font",
        "source": str(args.source.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "glyph_range": "U+3D000–U+3D03F",
        "mapped_codepoints": 64,
        "axis": {"tag": "wght", "minimum": 300, "default": 400, "maximum": 700},
        "font": variable_path.name,
        "statics": {str(weight): path.name for weight, path in outputs.items()},
        "normal_offset_font_units": {str(key): value for key, value in OFFSETS.items()},
        "units_per_em": source["head"].unitsPerEm,
        "validation": {
            "default_coordinates_and_metrics_match_source": True,
            "all_advances_and_cmaps_preserved": True,
            "all_masters_have_matching_point_topology": True,
            "raster_topology_changes_vs_regular": changes,
            "raster_ink_area_at_2x_upm": ink,
        },
        "limitations": "Normal offsets are a design preview. Weight balance, joins, counters and script identities need manual review. This demo adds no new Unicode coverage.",
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (args.output / "README.txt").write_text(
        "Panorama Gothic Seal Variable — 64-glyph weight study\n\n"
        "Experimental wght axis: 300 Light, 400 Regular, 500 Medium, 700 Bold.\n"
        "Install PanoramaGothicSealVariable.ttf or use the included static fonts.\n"
        "U+3D000–U+3D03F; existing generated drawing identities are preserved.\n"
        "Regular400 uses exactly the original outlines and metrics. All advances\n"
        "remain 1024 units. Other weights use compatible normal-offset outlines.\n"
        "This is a weight visualization prototype, not a finished script design.\n"
        "See manifest.json for measured checks and limitations. OFL 1.1.\n"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
