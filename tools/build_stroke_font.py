#!/usr/bin/env python3
"""Build a font by expanding editable centerlines with one constant radius.

Input is design/strokes/*.json, with hand-reviewed files taking precedence over
design/strokes/auto/*.json. No existing font outline, bitmap contour, or brush
silhouette is read. A stroke is the union of segment rectangles and round disks
along an adaptively flattened Bezier centerline. All primitives use the same
clockwise winding, so crossings add ink instead of cutting holes.

The JSON and exported SVG remain the editable source; TrueType necessarily
stores filled outlines, rather than SVG stroke attributes. Weight changes need
an optical spacing and curvature review and are outside this prototype.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import re
import shutil
from typing import Iterable

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.basePen import BasePen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import flagOverlapSimple


ROOT = Path(__file__).resolve().parents[1]
FAMILY = "Panorama Gothic Seal Strokes"
UNITS_PER_EM = 1024
BASELINE = 832
NORMALIZED_CENTERLINE_EXTENT = 738.0  # 768 units of ink at Regular's 30-unit pen.
FLATTEN_TOLERANCE = 0.10  # In source drawing units; independent of weight.
Point = tuple[float, float]


def point_segment_distance(point: Point, start: Point, end: Point) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if not length_squared:
        return math.dist(point, start)
    fraction = max(0.0, min(1.0, ((point[0] - start[0]) * dx
                                 + (point[1] - start[1]) * dy) / length_squared))
    return math.dist(point, (start[0] + fraction * dx, start[1] + fraction * dy))


def _midpoint(first: Point, second: Point) -> Point:
    return ((first[0] + second[0]) / 2, (first[1] + second[1]) / 2)


def flatten_cubic(start: Point, first: Point, second: Point, end: Point,
                  tolerance: float = FLATTEN_TOLERANCE, depth: int = 0) -> list[Point]:
    """Subdivide until the entire cubic control hull is close to its chord."""
    error = max(point_segment_distance(first, start, end),
                point_segment_distance(second, start, end))
    if error <= tolerance:
        return [end]
    if depth >= 24:
        raise ValueError("Bezier flattening did not converge within 24 subdivisions")
    a, b, c = _midpoint(start, first), _midpoint(first, second), _midpoint(second, end)
    d, e = _midpoint(a, b), _midpoint(b, c)
    middle = _midpoint(d, e)
    return (flatten_cubic(start, a, d, middle, tolerance, depth + 1)
            + flatten_cubic(middle, e, c, end, tolerance, depth + 1))


class CenterlinePen(BasePen):
    def __init__(self, tolerance: float = FLATTEN_TOLERANCE):
        super().__init__(None)
        self.tolerance = tolerance
        self.subpaths: list[tuple[list[Point], bool]] = []
        self.points: list[Point] = []

    def _moveTo(self, point):
        if self.points:
            raise ValueError("Each stroke must have exactly one continuous subpath")
        self.points = [tuple(point)]

    def _lineTo(self, point):
        point = tuple(point)
        if point != self.points[-1]:
            self.points.append(point)

    def _curveToOne(self, first, second, end):
        self.points.extend(flatten_cubic(self.points[-1], tuple(first), tuple(second),
                                         tuple(end), self.tolerance))

    def _qCurveToOne(self, control, end):
        start = self.points[-1]
        first = tuple(start[axis] + 2 / 3 * (control[axis] - start[axis]) for axis in (0, 1))
        second = tuple(end[axis] + 2 / 3 * (control[axis] - end[axis]) for axis in (0, 1))
        self._curveToOne(first, second, end)

    def _closePath(self):
        self.subpaths.append((self.points, True))
        self.points = []

    def _endPath(self):
        self.subpaths.append((self.points, False))
        self.points = []


def flatten_path(path: str, closed: bool | None = None,
                 tolerance: float = FLATTEN_TOLERANCE) -> tuple[list[Point], bool]:
    pen = CenterlinePen(tolerance)
    parse_path(path, pen)
    if pen.points:
        pen._endPath()
    if len(pen.subpaths) != 1:
        raise ValueError("Each stroke path must contain one continuous subpath")
    points, path_closed = pen.subpaths[0]
    if len(points) < 2:
        raise ValueError("Each stroke must contain at least one nonzero segment")
    if closed is not None and not closed and path_closed:
        raise ValueError("A closed SVG path must not declare closed=false")
    return points, bool(closed or path_closed)


def _clockwise_rectangle(pen: TTGlyphPen, start: Point, end: Point, radius: float):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return
    nx, ny = -dy / length * radius, dx / length * radius
    pen.moveTo((start[0] + nx, start[1] + ny))
    pen.lineTo((end[0] + nx, end[1] + ny))
    pen.lineTo((end[0] - nx, end[1] - ny))
    pen.lineTo((start[0] - nx, start[1] - ny))
    pen.closePath()


def _clockwise_disk(pen: TTGlyphPen, center: Point, radius: float):
    """Sixteen tangent-matched quadratic arcs approximate a constant-radius disk.

    At each tangent control point the radius is r/cos(pi/16). The maximum radial
    error is below 0.00019*r, in addition to final TrueType coordinate rounding.
    """
    cx, cy = center
    pen.moveTo((cx + radius, cy))
    control_radius = radius / math.cos(math.pi / 16)
    for index in range(16):
        middle = -(index + 0.5) * math.pi / 8
        end = -(index + 1) * math.pi / 8
        # Close at the identical first point. sin(-2*pi)'s floating residual
        # otherwise makes TTGlyphPen remove the duplicate at some radii but
        # retain it at others, breaking compatible variable-font masters.
        endpoint = ((cx + radius, cy) if index == 15 else
                    (cx + radius * math.cos(end), cy + radius * math.sin(end)))
        pen.qCurveTo((cx + control_radius * math.cos(middle),
                      cy + control_radius * math.sin(middle)), endpoint)
    pen.closePath()


def expand_polylines(strokes: Iterable[tuple[list[Point], bool]], radius: float):
    """Return the nonzero-winding union of constant-radius stroke primitives."""
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("Stroke radius must be finite and positive")
    pen = TTGlyphPen(None)
    counts = {"segment_rectangles": 0, "round_disks": 0}
    for points, closed in strokes:
        segments = list(zip(points, points[1:]))
        if closed and points[-1] != points[0]:
            segments.append((points[-1], points[0]))
        for start, end in segments:
            if math.dist(start, end) > 1e-9:
                _clockwise_rectangle(pen, start, end, radius)
                counts["segment_rectangles"] += 1
        disk_points = points[:-1] if closed and points[0] == points[-1] else points
        for point in disk_points:
            _clockwise_disk(pen, point, radius)
            counts["round_disks"] += 1
    glyph = pen.glyph()
    if glyph.numberOfContours and len(glyph.coordinates) > 65535:
        raise ValueError(f"Glyph has {len(glyph.coordinates)} points; TrueType limit is 65535")
    if glyph.numberOfContours:
        glyph.flags[0] |= flagOverlapSimple
    return glyph, counts


def codepoint_number(value) -> int:
    if isinstance(value, int):
        number = value
    else:
        number = int(value.removeprefix("U+").removeprefix("0x"), 16)
    if not 0 <= number <= 0x10FFFF or 0xD800 <= number <= 0xDFFF:
        raise ValueError(f"Invalid Unicode scalar value: {value!r}")
    return number


def source_transform(view_box: list[float]):
    if len(view_box) != 4:
        raise ValueError("viewBox must contain x, y, width, height")
    left, top, width, height = map(float, view_box)
    if width <= 0 or height <= 0:
        raise ValueError("viewBox width and height must be positive")
    scale = UNITS_PER_EM / max(width, height)
    x_margin = (UNITS_PER_EM - width * scale) / 2
    y_margin = (UNITS_PER_EM - height * scale) / 2

    def transform(point):
        return ((point[0] - left) * scale + x_margin,
                BASELINE - (point[1] - top) * scale - y_margin)

    return transform, scale


def normalize_sources(sources: list[dict], extent: float = NORMALIZED_CENTERLINE_EXTENT) -> list[dict]:
    """Fit each complete glyph proportionally; never scale its pen width.

    One affine transform is applied to every stroke of a character. The same
    transformed paths are reused at every weight. Reviewed input JSON stays
    immutable, including the nominal width used during its original review.
    """
    if not math.isfinite(extent) or not 0 < extent < UNITS_PER_EM:
        raise ValueError("Normalized extent must be positive and smaller than one em")
    result = []
    center = (UNITS_PER_EM / 2, BASELINE - UNITS_PER_EM / 2)
    for source in sources:
        points = [point for stroke, _ in source["strokes"] for point in stroke]
        bounds = (min(p[0] for p in points), min(p[1] for p in points),
                  max(p[0] for p in points), max(p[1] for p in points))
        longest = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
        if longest <= 0:
            raise ValueError(f"U+{source['codepoint']:05X}: cannot normalize an empty trajectory")
        factor = extent / longest
        offset = (center[0] - factor * (bounds[0] + bounds[2]) / 2,
                  center[1] - factor * (bounds[1] + bounds[3]) / 2)
        normalized = dict(source)
        normalized["strokes"] = [
            ([(factor*x + offset[0], factor*y + offset[1]) for x, y in stroke], closed)
            for stroke, closed in source["strokes"]
        ]
        normalized["normalization"] = {
            "preserve_aspect_ratio": True, "pen_width_scaled": False,
            "target_centerline_extent": extent,
            "matrix_font_units": [factor, 0, 0, factor, *offset],
            "original_centerline_bounds_font_units": list(bounds),
            "center_font_units": list(center),
        }
        result.append(normalized)
    return result


def load_sources(source_root: Path, require_visual_match: bool = False,
                 normalization_extent: float | None = None) -> list[dict]:
    sources = {}
    # The later manual source is the explicit override, never a silent merge.
    for directory in (source_root / "auto", source_root):
        for path in sorted(directory.glob("*.json")):
            data = json.loads(path.read_text())
            if "codepoint" not in data or "strokes" not in data:
                continue
            codepoint = codepoint_number(data["codepoint"])
            if data.get("linecap", "round") != "round" or data.get("linejoin", "round") != "round":
                raise ValueError(f"{path}: only round stroke caps and joins are supported")
            width = float(data.get("stroke_width", 13))
            if not math.isfinite(width) or width <= 0:
                raise ValueError(f"{path}: stroke_width must be positive")
            transform, scale = source_transform(data["viewBox"])
            strokes = []
            for stroke in data["strokes"]:
                points, closed = flatten_path(stroke["path"], stroke.get("closed"))
                strokes.append(([transform(point) for point in points], closed))
            if not strokes:
                raise ValueError(f"{path}: glyph has no strokes")
            sources[codepoint] = {"codepoint": codepoint, "path": path,
                                  "data": data, "strokes": strokes,
                                  "scale": scale, "width": width * scale}
    if not sources:
        raise ValueError(f"No centerline JSON sources found in {source_root}")
    if require_visual_match:
        pending = [f"U+{codepoint:05X}" for codepoint, source in sorted(sources.items())
                   if source["data"].get("visual_reference_match_reviewed") is not True]
        if pending:
            raise ValueError("Sources lack a matching-hash accepted visual reference review: "
                             + ", ".join(pending))
        for codepoint, source in sources.items():
            review = source["data"].get("source", {}).get("geometry_reference_review")
            if review:
                geometry = {key: source["data"][key] for key in ("viewBox", "stroke_width", "strokes")}
                digest = hashlib.sha256(json.dumps(geometry, sort_keys=True,
                                                  separators=(",", ":")).encode()).hexdigest()
                if review.get("verdict") != "match" or review.get("geometry_sha256") != digest:
                    raise ValueError(f"U+{codepoint:05X}: manual geometry review is stale or not a match")
    ordered = [sources[codepoint] for codepoint in sorted(sources)]
    return normalize_sources(ordered, normalization_extent) if normalization_extent is not None else ordered


def write_centerline_svg(source: dict, target: Path, font_stroke_width: float | None = None):
    data = source["data"]
    normalization = source.get("normalization")
    if normalization:
        from fontTools.pens.svgPathPen import SVGPathPen
        from fontTools.pens.transformPen import TransformPen
        left, top, view_width, view_height = data["viewBox"]
        scale = source["scale"]
        x_margin = (UNITS_PER_EM - view_width * scale) / 2
        y_margin = (UNITS_PER_EM - view_height * scale) / 2
        factor, _, _, _, tx, ty = normalization["matrix_font_units"]
        matrix = (factor*scale, 0, 0, factor*scale,
                  factor*(x_margin - left*scale) + tx,
                  BASELINE - factor*(BASELINE + top*scale - y_margin) - ty)
        width = source["width"] if font_stroke_width is None else font_stroke_width
        lines = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">',
                 f'  <g fill="none" stroke="black" stroke-width="{width:.9g}" '
                 'stroke-linecap="round" stroke-linejoin="round">']
        for index, stroke in enumerate(data["strokes"]):
            pen = SVGPathPen(None)
            path = stroke["path"]
            if stroke.get("closed") and not path.rstrip().lower().endswith("z"):
                path += " Z"
            parse_path(path, TransformPen(pen, matrix))
            label = html.escape(stroke.get("id", f"stroke-{index + 1}"), quote=True)
            lines.append(f'    <path id="{label}" d="{html.escape(pen.getCommands(), quote=True)}"/>')
        target.write_text("\n".join([*lines, "  </g>", "</svg>", ""]))
        return
    width = (font_stroke_width / source["scale"] if font_stroke_width is not None
             else float(data.get("stroke_width", 13)))
    view_box = " ".join(str(value) for value in data["viewBox"])
    content = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}">',
               f'  <g fill="none" stroke="black" stroke-width="{width:.9g}" '
               'stroke-linecap="round" stroke-linejoin="round">']
    for index, stroke in enumerate(data["strokes"]):
        stroke_id = html.escape(stroke.get("id", f"stroke-{index + 1}"), quote=True)
        path = stroke["path"]
        if stroke.get("closed") and not path.rstrip().lower().endswith("z"):
            path += " Z"
        content.append(f'    <path id="{stroke_id}" d="{html.escape(path, quote=True)}"/>')
    content.extend(["  </g>", "</svg>", ""])
    target.write_text("\n".join(content))


def family_basename(family: str) -> str:
    basename = re.sub(r"[^A-Za-z0-9]", "", family)
    if not basename:
        raise ValueError("Family name must include at least one ASCII letter or number")
    return basename


def build_font(sources: list[dict], target: Path, family: str = FAMILY,
               font_stroke_width: float | None = None) -> dict:
    basename = family_basename(family)
    if font_stroke_width is not None and (not math.isfinite(font_stroke_width) or font_stroke_width <= 0):
        raise ValueError("font_stroke_width must be finite and positive")
    glyph_names = [f"u{source['codepoint']:05X}" for source in sources]
    glyph_order = [".notdef", *glyph_names]
    glyphs, metrics, reports = {}, {}, {}
    notdef, _ = expand_polylines([([(160, 0), (160, 640), (640, 640), (640, 0)], True)], 16)
    glyphs[".notdef"], metrics[".notdef"] = notdef, (UNITS_PER_EM, 144)
    for name, source in zip(glyph_names, sources):
        width = source["width"] if font_stroke_width is None else font_stroke_width
        glyph, counts = expand_polylines(source["strokes"], width / 2)
        glyph.recalcBounds(None)
        glyphs[name], metrics[name] = glyph, (UNITS_PER_EM, glyph.xMin)
        reports[f"U+{source['codepoint']:05X}"] = {"stroke_width_font_units": width,
                                                "contours": glyph.numberOfContours,
                                                "points": len(glyph.coordinates), **counts}
    fb = FontBuilder(UNITS_PER_EM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({source["codepoint"]: name for name, source in zip(glyph_names, sources)})
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    ascent = max(896, max(glyph.yMax for glyph in glyphs.values()))
    descent = min(-192, min(glyph.yMin for glyph in glyphs.values()))
    fb.setupHorizontalHeader(ascent=ascent, descent=descent, lineGap=0)
    style = "Regular"
    fb.setupNameTable({
        "copyright": "Panorama Gothic contributors, 2026. Generated glyph drawings.",
        "familyName": family, "styleName": style,
        "uniqueFontIdentifier": f"{basename};0.6;{style}",
        "fullName": f"{family} {style}",
        "psName": f"{basename}-{style.replace(' ', '')}",
        "version": "Version 0.6; normalized centerline stroke prototype",
        "description": ("Constant-width centerline expansion. Manual and automatic geometry are "
                        "identified separately in the accompanying manifest; script review is pending."),
        "licenseDescription": "This Font Software is licensed under the SIL Open Font License, Version 1.1.",
        "licenseInfoURL": "https://openfontlicense.org/",
        "typographicFamily": family, "typographicSubfamily": style,
    })
    fb.setupOS2(sTypoAscender=ascent, sTypoDescender=descent, sTypoLineGap=0,
                usWinAscent=ascent, usWinDescent=-descent, usWeightClass=400,
                fsSelection=1 << 6, sxHeight=512, sCapHeight=704)
    fb.setupPost(keepGlyphNames=True)
    fb.setupMaxp()
    # A fixed timestamp makes repeated builds bit-for-bit reproducible.
    fb.font["head"].created = fb.font["head"].modified = 3875126400
    fb.font["head"].fontRevision = 0.6
    fb.font.recalcTimestamp = False
    fb.save(target)
    return reports


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_all(source_root: Path, output: Path, family: str = FAMILY,
              font_stroke_width: float | None = None,
              require_visual_match: bool = False,
              normalization_extent: float | None = None,
              additional_source_root: Path | None = None) -> dict:
    family_basename(family)
    if font_stroke_width is not None and (not math.isfinite(font_stroke_width) or font_stroke_width <= 0):
        raise ValueError("font_stroke_width must be finite and positive")
    sources = load_sources(source_root, require_visual_match, normalization_extent)
    if additional_source_root is not None:
        additional = load_sources(additional_source_root, require_visual_match, normalization_extent)
        duplicates = {source["codepoint"] for source in sources} & {source["codepoint"] for source in additional}
        if duplicates:
            raise ValueError("Additional sources cannot override existing glyphs: "
                             + ", ".join(f"U+{cp:05X}" for cp in sorted(duplicates)))
        sources = sorted(sources + additional, key=lambda source: source["codepoint"])
    output.mkdir(parents=True, exist_ok=True)
    svg_dir = output / "centerlines"
    svg_dir.mkdir(exist_ok=True)
    for source in sources:
        write_centerline_svg(source, svg_dir / f"U{source['codepoint']:05X}.svg", font_stroke_width)
    regular_path = output / f"{family_basename(family)}-Regular.ttf"
    regular_reports = build_font(sources, regular_path, family, font_stroke_width)
    woff_path = regular_path.with_suffix(".woff")
    font = TTFont(regular_path)
    font.recalcTimestamp = False
    font.flavor = "woff"
    font.save(woff_path)
    files = [regular_path, woff_path]
    for name in ("LICENSE-OFL.txt", "OFL-1.1.txt"):
        license_source = ROOT / "fonts/seal-example" / name
        license_target = output / name
        shutil.copyfile(license_source, license_target)
        files.append(license_target)
    glyph_records = []
    for source in sources:
        codepoint = f"U+{source['codepoint']:05X}"
        glyph_records.append({
            "codepoint": codepoint,
            "status": source["data"].get("status", "automatic_unreviewed"),
            "coverage_eligible": bool(source["data"].get("coverage_eligible", False)),
            "character_identity_verified": bool(source["data"].get("character_identity_verified", False)),
            "historical_stroke_order_verified": bool(source["data"].get("historical_stroke_order_verified", False)),
            "visual_reference_match_reviewed": bool(source["data"].get("visual_reference_match_reviewed", False)),
            "structural_corrections": source["data"].get("structural_corrections", []),
            "source": source["data"].get("source", {}),
            "centerline_file": str(source["path"].relative_to(ROOT)) if source["path"].is_relative_to(ROOT) else str(source["path"]),
            "centerline_sha256": sha256(source["path"]),
            "strokes": len(source["strokes"]),
            "closed_strokes": sum(closed for _, closed in source["strokes"]),
            "source_stroke_width_source_units": float(source["data"].get("stroke_width", 13)),
            "normalization": source.get("normalization"),
            "actual_stroke_width_source_units": regular_reports[codepoint]["stroke_width_font_units"] / (
                source["scale"] * (source.get("normalization", {}).get("matrix_font_units", [1])[0])),
            **regular_reports[codepoint],
        })
    manifest = {
        "family": family, "glyph_count": len(sources),
        "status": "prototype_unverified", "production_ready": False,
        "coverage_eligible": False,
        "visual_reference_match_required": require_visual_match,
        "license": "OFL-1.1", "license_url": "https://openfontlicense.org/",
        "construction": "constant-radius union of centerline segment rectangles and round disks",
        "outline_sources_read": False,
        "flatten_tolerance_source_units": FLATTEN_TOLERANCE,
        "circle_relative_radial_error_bound": 0.00019,
        "quantization_error_font_units_per_coordinate": 0.5,
        "round_caps": True, "round_joins": True,
        "font_stroke_width_override": font_stroke_width,
        "normalization": {"enabled": normalization_extent is not None,
                          "target_centerline_extent": normalization_extent,
                          "preserve_aspect_ratio": True, "pen_width_scaled": False},
        "fill_rule": "nonzero; all primitive contours clockwise; OVERLAP_SIMPLE set",
        "weight_axis": None,
        "glyphs": glyph_records,
        "files": [{"name": path.name, "bytes": path.stat().st_size,
                   "sha256": sha256(path)} for path in files],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT / "design/strokes-individual")
    parser.add_argument("--additional-source-root", type=Path,
                        help="Explicitly include separate candidate sources; duplicate codepoints are rejected")
    parser.add_argument("--output", type=Path, default=ROOT / "fonts/seal-individual")
    parser.add_argument("--family", default="Panorama Gothic Seal Individual", help="Font family; also determines the output filename")
    parser.add_argument("--font-stroke-width", type=float,
                        help="Use this identical width in font units for every glyph")
    parser.add_argument("--require-visual-match", action="store_true",
                        help="Refuse sources without an accepted visual reference match review")
    parser.add_argument("--normalize-glyphs", action="store_true",
                        help="Fit glyphs proportionally to the shared em envelope, without scaling the pen")
    args = parser.parse_args()
    manifest = build_all(args.source_root, args.output, args.family, args.font_stroke_width,
                         args.require_visual_match,
                         NORMALIZED_CENTERLINE_EXTENT if args.normalize_glyphs else None,
                         args.additional_source_root)
    reviewed = sum(glyph["status"] == "manual_geometry_reviewed" for glyph in manifest["glyphs"])
    print(f"Built {manifest['glyph_count']} centerline glyphs ({reviewed} manual geometry reviewed) in {args.output}")


if __name__ == "__main__":
    main()
