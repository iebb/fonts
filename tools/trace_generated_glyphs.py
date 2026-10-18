#!/usr/bin/env python3
"""Trace an immutable alpha glyph sheet into an explicitly experimental font.

The source PNG is read and retained byte-for-byte. Only vector contours are
derived: alpha threshold 128, tiny contour rejection and 0.5 source-pixel polygon
simplification. These glyphs require visual comparison with the draft reference
before they are eligible for a coverage claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import numpy as np
from scipy.interpolate import splprep, splev
from scipy.spatial import cKDTree
from fontTools.fontBuilder import FontBuilder
from fontTools.merge import Merger
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont


Point = tuple[int, int]
UPM = 1024
BASELINE = 832


def signed_area(points: list[Point]) -> float:
    return sum(x * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * y
               for i, (x, y) in enumerate(points)) / 2


def trace_boundaries(mask: list[list[bool]]) -> list[list[Point]]:
    """Trace oriented unit-pixel boundaries, including opposite-wound holes.

    Filled pixels lie to the right of each edge in image coordinates. At a
    diagonal vertex, turning right first keeps touching components separate.
    """
    height, width = len(mask), len(mask[0]) if mask else 0
    edges: dict[Point, set[Point]] = {}

    def add(start: Point, end: Point) -> None:
        edges.setdefault(start, set()).add(end)

    def filled(x: int, y: int) -> bool:
        return 0 <= x < width and 0 <= y < height and mask[y][x]

    for y, row in enumerate(mask):
        if len(row) != width:
            raise ValueError("mask rows must have a consistent width")
        for x, value in enumerate(row):
            if not value:
                continue
            if not filled(x, y - 1):
                add((x, y), (x + 1, y))
            if not filled(x + 1, y):
                add((x + 1, y), (x + 1, y + 1))
            if not filled(x, y + 1):
                add((x + 1, y + 1), (x, y + 1))
            if not filled(x - 1, y):
                add((x, y + 1), (x, y))
    directions = {(1, 0): 0, (0, 1): 1, (-1, 0): 2, (0, -1): 3}
    turn_priority = {1: 0, 0: 1, 3: 2, 2: 3}
    contours: list[list[Point]] = []
    while edges:
        start = min(edges)
        previous = start
        current = min(edges[start])
        edges[start].remove(current)
        if not edges[start]:
            del edges[start]
        contour = [start]
        while current != start:
            contour.append(current)
            candidates = edges.get(current)
            if not candidates:
                raise ValueError("pixel boundary did not close")
            incoming = directions[(current[0] - previous[0], current[1] - previous[1])]

            def priority(end: Point):
                outgoing = directions[(end[0] - current[0], end[1] - current[1])]
                return turn_priority[(outgoing - incoming) % 4]

            following = min(candidates, key=priority)
            candidates.remove(following)
            if not candidates:
                del edges[current]
            previous, current = current, following
        contours.append(contour)
    return contours


def _simplify_open(points: list[Point], tolerance: float) -> list[Point]:
    keep = {0, len(points) - 1}
    pending = [(0, len(points) - 1)]
    while pending:
        first, last = pending.pop()
        ax, ay = points[first]
        bx, by = points[last]
        dx, dy = bx - ax, by - ay
        denominator = dx * dx + dy * dy
        farthest, distance_squared = None, tolerance * tolerance
        for index in range(first + 1, last):
            px, py = points[index]
            fraction = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / denominator)) if denominator else 0
            distance = (px - ax - fraction * dx) ** 2 + (py - ay - fraction * dy) ** 2
            if distance > distance_squared:
                farthest, distance_squared = index, distance
        if farthest is not None:
            keep.add(farthest)
            pending.extend(((first, farthest), (farthest, last)))
    return [points[index] for index in sorted(keep)]


def simplify_contour(points: list[Point], tolerance: float = 0.5) -> list[Point]:
    """Simplify a closed contour without changing its winding direction."""
    if len(points) <= 3:
        return points
    start_index = min(range(len(points)), key=lambda i: points[i])
    ring = points[start_index:] + points[:start_index]
    opposite = max(range(1, len(ring)), key=lambda i: (ring[i][0] - ring[0][0]) ** 2 + (ring[i][1] - ring[0][1]) ** 2)
    result = _simplify_open(ring[:opposite + 1], tolerance)[:-1]
    result += _simplify_open(ring[opposite:] + [ring[0]], tolerance)[:-1]
    return result if len(result) >= 3 and signed_area(result) * signed_area(points) > 0 else points


def _dense_closed(points, step=0.125):
    dense = []
    for index, first in enumerate(points):
        last = points[(index + 1) % len(points)]
        count = max(1, math.ceil(math.dist(first, last) / step))
        if len(dense) + count > 250000:
            raise ValueError("spline candidate has excessive perimeter")
        dense.extend((first[0] + (last[0] - first[0]) * i / count,
                      first[1] + (last[1] - first[1]) * i / count) for i in range(count))
    return np.asarray(dense, dtype=float)


def _distance_to_polyline(queries, points):
    # Densification keeps all segments local to their nearest vertices.
    tree = cKDTree(points)
    maximum = 0.0
    for offset in range(0, len(queries), 4096):
        batch = queries[offset:offset + 4096]
        _, indexes = tree.query(batch, k=min(4, len(points)))
        if indexes.ndim == 1:
            indexes = indexes[:, None]
        starts = np.concatenate((indexes, (indexes - 1) % len(points)), axis=1)
        first, last = points[starts], points[(starts + 1) % len(points)]
        delta = last - first
        relative = batch[:, None, :] - first
        denominator = np.sum(delta * delta, axis=2)
        fractions = np.divide(np.sum(relative * delta, axis=2), denominator,
                              out=np.zeros_like(denominator), where=denominator > 0)
        projections = first + np.clip(fractions, 0, 1)[:, :, None] * delta
        maximum = max(maximum, float(np.sqrt(np.min(np.sum((batch[:, None, :] - projections) ** 2, axis=2), axis=1)).max()))
    return maximum


def _flatten_cubic(first, control1, control2, last, tolerance=0.025):
    def distance(point):
        dx, dy = last[0] - first[0], last[1] - first[1]
        length = math.hypot(dx, dy)
        return abs(dx * (point[1] - first[1]) - dy * (point[0] - first[0])) / length if length else math.dist(point, first)
    if max(distance(control1), distance(control2)) <= tolerance:
        return [last]
    midpoint = lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    a, b, c = midpoint(first, control1), midpoint(control1, control2), midpoint(control2, last)
    d, e = midpoint(a, b), midpoint(b, c)
    middle = midpoint(d, e)
    return _flatten_cubic(first, a, d, middle, tolerance) + _flatten_cubic(middle, e, c, last, tolerance)


def _spline_commands(points, smoothing, periodic):
    array = np.asarray(points, dtype=float)
    degree = min(3, len(points) - 1)
    tck, _ = splprep(array.T, s=smoothing, per=periodic, k=degree)
    if not periodic:
        # Open pieces meet exactly at genuine corners, without rounding them.
        tck[1][0][0], tck[1][1][0] = array[0]
        tck[1][0][-1], tck[1][1][-1] = array[-1]
    knots = sorted({float(value) for value in tck[0] if 0 <= value <= 1})
    commands = []
    flattened = [tuple(splev(0, tck))]
    for first_t, last_t in zip(knots, knots[1:]):
        if last_t <= first_t:
            continue
        first = np.asarray(splev(first_t, tck))
        last = np.asarray(splev(last_t, tck))
        control1 = first + np.asarray(splev(first_t, tck, der=1)) * (last_t - first_t) / 3
        control2 = last - np.asarray(splev(last_t, tck, der=1)) * (last_t - first_t) / 3
        margin = max(float(np.ptp(array, axis=0).max()), 1) * 4
        controls = np.asarray([first, control1, control2, last])
        if not np.isfinite(controls).all() or np.any(controls < array.min(axis=0) - margin) or np.any(controls > array.max(axis=0) + margin):
            raise ValueError("unstable spline candidate")
        commands.append((tuple(control1), tuple(control2), tuple(last)))
        flattened.extend(_flatten_cubic(tuple(first), tuple(control1), tuple(control2), tuple(last)))
    return tuple(splev(0, tck)), commands, flattened


def smooth_contour(points: list[Point], original: list[Point], max_error=0.60):
    """Fit cubic splines with corner anchors and densely checked geometry."""
    corners = []
    for index, point in enumerate(points):
        previous, following = points[index - 1], points[(index + 1) % len(points)]
        incoming = (point[0] - previous[0], point[1] - previous[1])
        outgoing = (following[0] - point[0], following[1] - point[1])
        lengths = math.hypot(*incoming), math.hypot(*outgoing)
        if min(lengths) >= 4 and sum(a * b for a, b in zip(incoming, outgoing)) / (lengths[0] * lengths[1]) <= 0.5:
            corners.append(index)
    if corners:
        pieces = []
        # Spline samples must stay evenly spaced. Feeding sparse RDP vertices
        # directly causes severe overshoot across long straight strokes.
        anchors = sorted(original.index(points[index]) for index in corners)
        for index, first in enumerate(anchors):
            last = anchors[(index + 1) % len(anchors)]
            piece = original[first:last + 1] if last > first else original[first:] + original[:last + 1]
            pieces.append((piece, False))
    else:
        pieces = [(original + [original[0]], True)]
    reference = _dense_closed(original)
    for multiplier in (1, 0.5, 0.25, 0.125, 0.0625, 0.03125, 0):
        commands, flattened, start = [], [], None
        try:
            for piece, periodic in pieces:
                if len(piece) == 2:
                    piece_start, piece_commands, piece_flat = piece[0], [(piece[1],)], piece
                else:
                    piece_start, piece_commands, piece_flat = _spline_commands(piece, 0.3 * len(piece) * multiplier, periodic)
                start = start or piece_start
                commands.extend(piece_commands)
                flattened.extend(piece_flat[:-1])
            fitted = _dense_closed(flattened)
        except ValueError:
            continue
        error = max(_distance_to_polyline(reference, fitted), _distance_to_polyline(fitted, reference))
        if error <= max_error and signed_area(flattened) * signed_area(original) > 0:
            return {"start": start, "commands": commands, "measured_error": error, "corner_count": len(corners), "smoothed": True}
    # A difficult tiny contour remains an honest bounded polygon.
    fitted = _dense_closed(points)
    error = max(_distance_to_polyline(reference, fitted), _distance_to_polyline(fitted, reference))
    return {"start": points[0], "commands": [(point,) for point in points[1:]] + [(points[0],)],
            "measured_error": error, "corner_count": len(corners), "smoothed": False}


def _font_glyph(contours: list[dict], width: int, height: int):
    target = TTGlyphPen(None)
    pen = Cu2QuPen(target, max_err=0.05 * UPM / max(width, height), all_quadratic=True)
    def transform(point):
        x, y = point
        return x * UPM / width, BASELINE - y * UPM / height
    for contour in contours:
        pen.moveTo(transform(contour["start"]))
        for command in contour["commands"]:
            if len(command) == 1:
                pen.lineTo(transform(command[0]))
            else:
                pen.curveTo(*(transform(point) for point in command))
        pen.closePath()
    return target.glyph()


def _write_specimen(font_path: Path, output: Path, start: int, columns: int, rows: int, review_status: str) -> None:
    cell_width, cell_height = 320, 350
    page = Image.new("RGB", (columns * cell_width + 80, rows * cell_height + 170), "white")
    draw = ImageDraw.Draw(page)
    label_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    label = ImageFont.truetype(str(label_path), 18) if label_path.exists() else ImageFont.load_default()
    title = ImageFont.truetype(str(label_path), 27) if label_path.exists() else label
    glyph_font = ImageFont.truetype(str(font_path), 256)
    draw.text((40, 24), "Panorama Gothic Seal Draft - experimental", font=title, fill="#111111")
    review_text = "visually compared; experimental" if review_status == "experimental_visually_compared" else "visual review pending"
    draw.text((40, 67), f"Generated drawings; {review_text}. Rendered from the TTF.", font=label, fill="#555555")
    for index in range(columns * rows):
        column, row = index % columns, index // columns
        x, y = 40 + column * cell_width, 125 + row * cell_height
        draw.rectangle((x, y, x + cell_width, y + cell_height), outline="#dddddd", width=1)
        draw.text((x + 14, y + 10), f"U+{start + index:05X}", font=label, fill="#555555")
        draw.text((x + 32, y + 55 + 208), chr(start + index), font=glyph_font, fill="black", anchor="ls")
    page.save(output)


def trace_generated_glyphs(source: Path, output: Path, retained_source: Path, start: int = 0x3D000,
                          columns: int = 4, rows: int = 4, threshold: int = 128,
                          min_area: float = 8, tolerance: float = 0.5,
                          review_status: str = "experimental_unreviewed") -> dict:
    """Build an experimental font while preserving the image source unchanged."""
    if not 0 <= threshold <= 255 or columns < 1 or rows < 1 or min_area < 0 or tolerance < 0:
        raise ValueError("invalid tracing parameters")
    image = Image.open(source)
    if image.mode != "RGBA":
        raise ValueError("the immutable source must be an RGBA image")
    if start < 0 or start + columns * rows > 0x110000 or start <= 0xDFFF and start + columns * rows > 0xD800:
        raise ValueError("codepoint range must contain only Unicode scalar values")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    retained_source.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != retained_source.resolve():
        shutil.copyfile(source, retained_source)
    if hashlib.sha256(retained_source.read_bytes()).hexdigest() != source_hash:
        raise ValueError("retained source is not byte-for-byte identical")
    alpha = image.getchannel("A")
    glyphs, metrics, cmap, records = {}, {}, {}, []
    notdef_pen = TTGlyphPen(None)
    for rectangle in (((96, -96), (96, 736), (928, 736), (928, -96)), ((160, -32), (864, -32), (864, 672), (160, 672))):
        notdef_pen.moveTo(rectangle[0])
        for point in rectangle[1:]:
            notdef_pen.lineTo(point)
        notdef_pen.closePath()
    glyphs[".notdef"] = notdef_pen.glyph()
    metrics[".notdef"] = (UPM, 96)
    for index in range(columns * rows):
        row, column = divmod(index, columns)
        left, right = column * image.width // columns, (column + 1) * image.width // columns
        top, bottom = row * image.height // rows, (row + 1) * image.height // rows
        cell_alpha = alpha.crop((left, top, right, bottom))
        width, height = cell_alpha.size
        pixels = cell_alpha.load()
        mask = [[pixels[x, y] >= threshold for x in range(width)] for y in range(height)]
        original_contours = trace_boundaries(mask)
        retained = [contour for contour in original_contours if abs(signed_area(contour)) >= min_area]
        contours = [simplify_contour(contour, tolerance) for contour in retained]
        if not contours:
            raise ValueError(f"cell {index + 1} has no retained glyph contours")
        cp, name = start + index, f"u{start + index:05X}"
        smoothed = [smooth_contour(contour, original) for contour, original in zip(contours, retained)]
        glyphs[name] = _font_glyph(smoothed, width, height)
        glyphs[name].recalcBounds(None)
        lsb = glyphs[name].xMin
        metrics[name] = (UPM, lsb)
        cmap[cp] = name
        def format_point(point):
            return f"{point[0]:.5f},{point[1]:.5f}"
        paths = []
        for contour in smoothed:
            commands = ["M " + format_point(contour["start"])]
            for command in contour["commands"]:
                commands.append(("L " if len(command) == 1 else "C ") + " ".join(map(format_point, command)))
            paths.append(" ".join(commands) + " Z")
        path_data = " ".join(paths)
        svg_file = f"U{cp:05X}.svg"
        (output / svg_file).write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"><title>U+{cp:05X} experimental drawing</title>'
            f'<path d="{path_data}" fill="black" fill-rule="nonzero"/></svg>\n', encoding="utf-8")
        records.append({
            "codepoint": f"U+{cp:05X}", "glyph": name, "svg": svg_file,
            "source_cell": [left, top, right, bottom],
            "foreground_pixels": sum(sum(row) for row in mask),
            "contours": len(contours), "holes": sum(signed_area(contour) < 0 for contour in contours),
            "removed_tiny_contours": len(original_contours) - len(retained),
            "points_before_simplification": sum(map(len, retained)), "points_after_simplification": sum(map(len, contours)),
            "smoothed_contours": sum(contour["smoothed"] for contour in smoothed),
            "polygon_fallback_contours": sum(not contour["smoothed"] for contour in smoothed),
            "maximum_measured_fit_error_source_pixels": max(contour["measured_error"] for contour in smoothed),
            "preserved_corner_count": sum(contour["corner_count"] for contour in smoothed),
        })
    builder = FontBuilder(UPM, isTTF=True)
    builder.setupGlyphOrder(list(glyphs))
    builder.setupCharacterMap(cmap)
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=BASELINE, descent=BASELINE - UPM, lineGap=0)
    builder.setupNameTable({
        "familyName": "Panorama Gothic Seal Draft", "styleName": "Regular",
        "fullName": "Panorama Gothic Seal Draft Regular", "psName": "PanoramaGothicSealDraft-Regular",
        "uniqueFontIdentifier": f"PanoramaGothicSealDraft;{source_hash[:16]};alpha{threshold}",
        "version": "Version 0.1; experimental Unicode 19 draft drawings",
        "copyright": "Panorama Gothic contributors, 2026. Generated glyph drawings.",
        "description": f"Experimental generated drawings traced from an immutable ImageGen sheet. Status: {review_status}; excluded from verified coverage.",
        "licenseDescription": "This Font Software is licensed under the SIL Open Font License, Version 1.1.",
        "licenseInfoURL": "https://openfontlicense.org/",
    })
    builder.setupOS2(sTypoAscender=BASELINE, sTypoDescender=BASELINE - UPM, usWinAscent=BASELINE,
                     usWinDescent=UPM - BASELINE, fsType=0, usWeightClass=400, usWidthClass=5, fsSelection=0x40)
    builder.setupPost(isFixedPitch=1)
    builder.setupMaxp()
    builder.font["head"].created = builder.font["head"].modified = 2082844800
    builder.font.recalcTimestamp = False
    ttf_path = output / "PanoramaGothicSealDraft-Regular.ttf"
    builder.save(ttf_path)
    builder.font.flavor = "woff"
    woff_path = ttf_path.with_suffix(".woff")
    builder.save(woff_path)
    _write_specimen(ttf_path, output / "specimen.png", start, columns, rows, review_status)
    provenance = {
        "schema_version": 1, "family": "Panorama Gothic Seal Draft", "license": "OFL-1.1",
        "status": review_status, "coverage_eligible": False,
        "source_generation": {"tool": "image_gen.imagegen", "source_file": str(source),
                              "retained_source": str(retained_source), "sha256": source_hash,
                              "reference": "reference/seal/U3D000.pdf", "source_pixels_modified": False},
        "tracing": {"alpha_threshold": threshold, "grid": [columns, rows], "minimum_contour_area_source_pixels": min_area,
                    "simplification_tolerance_source_pixels": tolerance,
                    "algorithm": "oriented pixel edges; RDP; corner-anchored cubic B-splines; Cu2Qu quadratic conversion",
                    "maximum_measured_spline_fit_error_source_pixels": 0.6,
                    "distance_validation_spacing_source_pixels": 0.125,
                    "cubic_flattening_validation_tolerance_source_pixels": 0.025,
                    "quadratic_conversion_tolerance_source_pixels": 0.05,
                    "normalization": "each full source cell maps to 1024x1024 units; baseline832; no individual glyph fitting"},
        "font": {"file": ttf_path.name, "woff": woff_path.name, "codepoint_count": len(cmap),
                 "codepoints": [f"U+{cp:05X}" for cp in cmap], "sha256": hashlib.sha256(ttf_path.read_bytes()).hexdigest(),
                 "woff_sha256": hashlib.sha256(woff_path.read_bytes()).hexdigest()},
        "glyphs": records,
        "notes": "Review status applies only to these drawings; no full-script certification is claimed. Generated drawings remain excluded from the verified coverage set.",
    }
    (output / "manifest.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    (output / "README.txt").write_text(
        f"EXPERIMENTAL: {review_status}\nGenerated glyph drawings traced into an original font.\n"
        "These experimental cmap entries are excluded from verified coverage.\n"
        "The original PNG is retained byte-for-byte; manifest.json records all tracing parameters.\n"
        "Font license: SIL Open Font License, Version 1.1 (OFL-1.1).\n", encoding="utf-8")
    license_source = Path(__file__).resolve().parents[1] / "sources/supplemental/plangothic/LICENSE-OFL.txt"
    if license_source.is_file():
        (output / "LICENSE-OFL.txt").write_text(
            "Panorama Gothic Seal Draft\nPanorama Gothic contributors, 2026. Generated glyph drawings.\n\n"
            + license_source.read_text(encoding="utf-8"), encoding="utf-8")
    return provenance


def _write_example_proofs(font_path: Path, output: Path, codepoints: list[int]) -> None:
    """Render the aggregate TrueType as a readable PNG and vector PDF proof."""
    columns, rows = 8, math.ceil(len(codepoints) / 8)
    width, margin, tile_width, tile_height, gap = 1800, 74, 196, 222, 12
    height = 186 + rows * (tile_height + gap) + 94
    page = Image.new("RGB", (width, height), "#F7F7F3")
    draw = ImageDraw.Draw(page)
    font_root = Path("/usr/share/fonts/truetype/dejavu")
    label_path, bold_path = font_root / "DejaVuSans.ttf", font_root / "DejaVuSans-Bold.ttf"
    label = ImageFont.truetype(str(label_path), 19)
    title = ImageFont.truetype(str(bold_path), 48)
    subtitle = ImageFont.truetype(str(label_path), 23)
    glyph_font = ImageFont.truetype(str(font_path), 170)
    draw.text((margin, 34), "Panorama Gothic", font=title, fill="#171B1B")
    draw.text((margin, 103), f"SMALL SEAL  /  {len(codepoints)}-CHARACTER STUDY", font=subtitle, fill="#526765")
    draw.line((margin, 153, width - margin, 153), fill="#BFCAC5", width=2)
    for index, cp in enumerate(codepoints):
        x = margin + index % columns * (tile_width + gap)
        y = 186 + index // columns * (tile_height + gap)
        draw.rectangle((x, y, x + tile_width, y + tile_height), fill="white", outline="#DDE2DC", width=1)
        draw.text((x + 12, y + 10), f"U+{cp:05X}", font=label, fill="#68746F")
        draw.text((x + (tile_width - 170) / 2, y + 43 + 170 * BASELINE / UPM), chr(cp),
                  font=glyph_font, fill="#111716", anchor="ls")
    footer = 186 + rows * (tile_height + gap) + 19
    draw.text((margin, footer), "Unicode 19 draft drawing studies · Rendered from the generated TrueType font", font=label, fill="#526765")
    draw.text((margin, footer + 29), "Experimental character forms; specialist script review remains necessary.", font=label, fill="#68746F")
    page.save(output / "specimen.png")

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont as PDFTTFont
    from reportlab.pdfgen import canvas
    pdf_font_name = "PanoramaSealExample-" + hashlib.sha256(font_path.read_bytes()).hexdigest()[:10]
    pdfmetrics.registerFont(PDFTTFont(pdf_font_name, str(font_path)))
    pdf_width, pdf_height, pdf_margin, pdf_gap = 595.28, 841.89, 28, 4
    pdf_tile_width, pdf_tile_height = (pdf_width - 2 * pdf_margin - 7 * pdf_gap) / 8, 78
    document = canvas.Canvas(str(output / "specimen.pdf"), pagesize=(pdf_width, pdf_height), invariant=True)
    document.setTitle("Panorama Gothic - 64-character Small Seal study")
    document.setAuthor("Panorama Gothic contributors")
    document.setFillColorRGB(0.969, 0.969, 0.953)
    document.rect(0, 0, pdf_width, pdf_height, fill=1, stroke=0)
    document.setFillColorRGB(0.09, 0.11, 0.11)
    document.setFont("Helvetica-Bold", 25)
    document.drawString(pdf_margin, pdf_height - 45, "Panorama Gothic")
    document.setFillColorRGB(0.32, 0.40, 0.39)
    document.setFont("Helvetica", 9)
    document.drawString(pdf_margin, pdf_height - 65, f"SMALL SEAL / {len(codepoints)}-CHARACTER STUDY / UNICODE 19 DRAFT")
    grid_top = pdf_height - 98
    for index, cp in enumerate(codepoints):
        x = pdf_margin + index % columns * (pdf_tile_width + pdf_gap)
        top = grid_top - index // columns * (pdf_tile_height + pdf_gap)
        document.setFillColorRGB(1, 1, 1)
        document.setStrokeColorRGB(0.86, 0.89, 0.86)
        document.setLineWidth(0.35)
        document.rect(x, top - pdf_tile_height, pdf_tile_width, pdf_tile_height, fill=1, stroke=1)
        document.setFillColorRGB(0.40, 0.46, 0.43)
        document.setFont("Helvetica", 6.5)
        document.drawString(x + 5, top - 10, f"U+{cp:05X}")
        document.setFillColorRGB(0.07, 0.09, 0.08)
        document.setFont(pdf_font_name, 52)
        document.drawString(x + (pdf_tile_width - 52) / 2, top - 18 - 52 * BASELINE / UPM, chr(cp))
    document.setFillColorRGB(0.32, 0.40, 0.39)
    document.setFont("Helvetica", 7)
    document.drawString(pdf_margin, 42, "Generated drawing studies. Rendered from the TrueType font; vector outlines embedded.")
    document.drawString(pdf_margin, 30, "Experimental character forms; specialist script review remains necessary.")
    document.save()


def trace_sheets(sheets: list[tuple[int, Path]], output: Path, retained_sources: Path,
                 columns: int = 4, rows: int = 4,
                 review_status: str = "experimental_unreviewed") -> dict:
    """Trace multiple mapped sheets and merge their disjoint cmap ranges."""
    if not sheets:
        raise ValueError("at least one mapped glyph sheet is required")
    codepoints: set[int] = set()
    for start, _ in sheets:
        points = set(range(start, start + columns * rows))
        if codepoints & points:
            raise ValueError("sheet codepoint ranges overlap")
        codepoints.update(points)
    batches, paths = [], []
    for start, source in sorted(sheets):
        batch_output = output / "batches" / f"U{start:05X}"
        manifest = trace_generated_glyphs(source, batch_output, retained_sources / f"U{start:05X}-imagegen-sheet.png",
                                         start=start, columns=columns, rows=rows, review_status=review_status)
        batches.append(manifest)
        paths.append(str(batch_output / manifest["font"]["file"]))
    merged = Merger().merge(paths)
    merged.recalcTimestamp = False
    merged["head"].created = merged["head"].modified = 2082844800
    generation_id = hashlib.sha256("".join(batch["source_generation"]["sha256"] for batch in batches).encode()).hexdigest()[:16]
    names = {1: "Panorama Gothic Seal Example", 2: "Regular", 3: f"PanoramaGothicSealExample;0.1;{generation_id}",
             4: "Panorama Gothic Seal Example Regular", 6: "PanoramaGothicSealExample-Regular",
             10: "Experimental generated Small Seal drawing studies. Specialist review required."}
    for name_id, value in names.items():
        merged["name"].removeNames(nameID=name_id)
        merged["name"].setName(value, name_id, 3, 1, 0x409)
        merged["name"].setName(value, name_id, 1, 0, 0)
    if set(merged.getBestCmap() or {}) != codepoints:
        raise ValueError("merged font cmap does not match the sheet mappings")
    for name in merged.getBestCmap().values():
        if merged["hmtx"][name][0] != UPM:
            raise ValueError("merged font has inconsistent glyph advance widths")
    ttf_path = output / "PanoramaGothicSealExample-Regular.ttf"
    merged.flavor = None
    merged.save(ttf_path)
    woff_path = ttf_path.with_suffix(".woff")
    merged.flavor = "woff"
    merged.save(woff_path)
    _write_example_proofs(ttf_path, output, sorted(codepoints))
    glyph_directory = output / "glyphs"
    glyph_directory.mkdir(exist_ok=True)
    for batch, (start, _) in zip(batches, sorted(sheets)):
        for glyph in batch["glyphs"]:
            shutil.copyfile(output / "batches" / f"U{start:05X}" / glyph["svg"], glyph_directory / glyph["svg"])
    license_path = output / "batches" / f"U{sorted(sheets)[0][0]:05X}" / "LICENSE-OFL.txt"
    if license_path.is_file():
        shutil.copyfile(license_path, output / "LICENSE-OFL.txt")
    manifest = {
        "schema_version": 1, "family": "Panorama Gothic Seal Example", "license": "OFL-1.1",
        "status": review_status, "coverage_eligible": False, "codepoint_count": len(codepoints),
        "font": {"file": ttf_path.name, "woff": woff_path.name, "codepoints": [f"U+{cp:05X}" for cp in sorted(codepoints)],
                 "sha256": hashlib.sha256(ttf_path.read_bytes()).hexdigest(), "woff_sha256": hashlib.sha256(woff_path.read_bytes()).hexdigest()},
        "batches": batches, "proofs": ["specimen.png", "specimen.pdf"],
        "notes": "Original generated drawings traced from immutable PNG sheets. Each complete cell retains the same 1024-unit advance. Experimental forms are excluded from full-coverage claims.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "README.txt").write_text(
        f"PANORAMA GOTHIC SEAL EXAMPLE\n{len(codepoints)} original generated drawing studies.\n"
        "Install the TrueType font or view specimen.png / specimen.pdf.\n"
        "Experimental character forms; no full Unicode coverage is claimed.\n"
        "Sources are retained byte-for-byte and tracing details are recorded in manifest.json.\n"
        "Font license: SIL Open Font License 1.1.\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--sheet", action="append", default=[], metavar="HEX_START=PNG_PATH", help="Repeat for mapped 4x4 sheets to merge")
    parser.add_argument("--output", type=Path, default=Path("fonts/seal-experimental"))
    parser.add_argument("--retained-source", type=Path, default=Path("design/seal/imagegen-sheet.png"))
    parser.add_argument("--start", "--start-codepoint", type=lambda value: int(value.removeprefix("U+"), 16), default=0x3D000)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--rows", type=int, default=4)
    parser.add_argument("--review-status", choices=("experimental_unreviewed", "experimental_visually_compared"), default="experimental_unreviewed")
    args = parser.parse_args()
    if args.sheet:
        if args.source:
            parser.error("use either --source or mapped --sheet inputs")
        sheets = []
        for value in args.sheet:
            start, separator, path = value.partition("=")
            if not separator:
                parser.error("each --sheet must be HEX_START=PNG_PATH")
            try:
                sheets.append((int(start.removeprefix("U+"), 16), Path(path)))
            except ValueError:
                parser.error(f"invalid mapped sheet start: {start}")
        result = trace_sheets(sheets, args.output, args.retained_source.parent,
                              columns=args.columns, rows=args.rows, review_status=args.review_status)
    else:
        if not args.source:
            parser.error("provide --source or mapped --sheet inputs")
        del vars(args)["sheet"]
        result = trace_generated_glyphs(**vars(args))
    print(json.dumps({"font": result["font"]["file"], "glyphs": result.get("codepoint_count", result["font"].get("codepoint_count")), "coverage_eligible": False}))


if __name__ == "__main__":
    main()
