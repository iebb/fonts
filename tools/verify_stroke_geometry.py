#!/usr/bin/env python3
"""Audit editable SVG stroke geometry without relying on the rendered outlines.

This checks the centerline construction contract. It does not establish a
historical writing order or judge the identity of the character.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path import parse_path


PRESENTATION = ("fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin")


def inherited_style(parent: dict[str, str], element: ET.Element) -> dict[str, str]:
    result = dict(parent)
    for name in PRESENTATION:
        if name in element.attrib:
            result[name] = element.attrib[name]
    for declaration in element.attrib.get("style", "").split(";"):
        if ":" in declaration:
            name, value = declaration.split(":", 1)
            result[name.strip()] = value.strip()
    return result


def tangent_deviations(operations: list) -> list[float]:
    """Return angles between incoming and outgoing segment tangents, in degrees."""
    segments = []
    current = None
    for operator, points in operations:
        if operator == "moveTo":
            current = points[0]
        elif operator == "lineTo":
            end = points[0]
            direction = (end[0] - current[0], end[1] - current[1])
            segments.append((direction, direction))
            current = end
        elif operator == "curveTo" and len(points) == 3:
            first, second, end = points
            incoming = next((
                (point[0] - current[0], point[1] - current[1])
                for point in (first, second, end) if point != current
            ), (0.0, 0.0))
            outgoing = next((
                (end[0] - point[0], end[1] - point[1])
                for point in (second, first, current) if point != end
            ), (0.0, 0.0))
            segments.append((incoming, outgoing))
            current = end
        elif operator == "qCurveTo" and len(points) == 2 and points[-1] is not None:
            control, end = points
            segments.append(((control[0] - current[0], control[1] - current[1]),
                             (end[0] - control[0], end[1] - control[1])))
            current = end
    result = []
    for before, after in zip(segments, segments[1:]):
        a, b = before[1], after[0]
        denominator = math.hypot(*a) * math.hypot(*b)
        if denominator:
            cosine = max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / denominator))
            result.append(round(math.degrees(math.acos(cosine)), 6))
    return result


def sample_geometry(operations: list) -> tuple[list[tuple[float, float]], float | None]:
    """Sample analytic cubics and their curvature in SVG drawing units."""
    samples = []
    minimum_radius = math.inf
    current = None
    for operator, points in operations:
        if operator == "moveTo":
            current = points[0]
            samples.append(current)
        elif operator == "lineTo":
            current = points[0]
            samples.append(current)
        elif operator == "curveTo" and len(points) == 3:
            p0, p1, p2, p3 = current, *points
            for index in range(1, 257):
                t = index / 256
                u = 1 - t
                samples.append(tuple(u**3 * p0[axis] + 3*u*u*t*p1[axis]
                                     + 3*u*t*t*p2[axis] + t**3*p3[axis]
                                     for axis in (0, 1)))
                dx, dy = (3*u*u*(p1[axis] - p0[axis])
                          + 6*u*t*(p2[axis] - p1[axis])
                          + 3*t*t*(p3[axis] - p2[axis]) for axis in (0, 1))
                ddx, ddy = (6*u*(p2[axis] - 2*p1[axis] + p0[axis])
                            + 6*t*(p3[axis] - 2*p2[axis] + p1[axis])
                            for axis in (0, 1))
                cross = abs(dx*ddy - dy*ddx)
                if cross > 1e-12:
                    minimum_radius = min(minimum_radius, math.hypot(dx, dy)**3 / cross)
            current = p3
    return samples, round(minimum_radius, 6) if minimum_radius < math.inf else None


def point_segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    square_length = dx*dx + dy*dy
    if square_length == 0:
        return math.dist(point, start)
    fraction = max(0, min(1, ((point[0] - start[0])*dx + (point[1] - start[1])*dy) / square_length))
    return math.dist(point, (start[0] + fraction*dx, start[1] + fraction*dy))


def polyline_distance(first, second):
    result = math.inf
    for a, b in zip(first, first[1:]):
        rx, ry = b[0] - a[0], b[1] - a[1]
        for c, d in zip(second, second[1:]):
            sx, sy = d[0] - c[0], d[1] - c[1]
            denominator = rx*sy - ry*sx
            if abs(denominator) > 1e-12:
                qx, qy = c[0] - a[0], c[1] - a[1]
                t = (qx*sy - qy*sx) / denominator
                u = (qx*ry - qy*rx) / denominator
                if 0 <= t <= 1 and 0 <= u <= 1:
                    return 0.0
            result = min(result, point_segment_distance(a, c, d),
                         point_segment_distance(b, c, d), point_segment_distance(c, a, b),
                         point_segment_distance(d, a, b))
    return round(result, 6)


def audit(path: Path, expected_strokes: int | None = None, allow_closed: bool = False,
          junctions: tuple[str, ...] = ()) -> dict:
    root = ET.parse(path).getroot()
    errors = []
    strokes = []
    sampled_strokes = {}

    def visit(element: ET.Element, parent_style: dict[str, str], transformed: bool = False):
        style = inherited_style(parent_style, element)
        transformed = transformed or bool(element.attrib.get("transform"))
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "path":
            label = element.attrib.get("id", f"stroke-{len(strokes) + 1}")
            local_errors = []
            if transformed:
                local_errors.append("transform prevents a direct check in drawing units")
            if style.get("fill", "black").lower() != "none":
                local_errors.append("path has a fill; centerline paths must use fill=none")
            if style.get("stroke", "none").lower() in ("none", "transparent"):
                local_errors.append("path has no visible stroke")
            if style.get("stroke-linecap") != "round":
                local_errors.append("linecap is not round")
            if style.get("stroke-linejoin") != "round":
                local_errors.append("linejoin is not round")
            width = style.get("stroke-width", "1")
            if not re.fullmatch(r"(?:\d+(?:\.\d*)?|\.\d+)", width):
                local_errors.append("stroke-width must be a positive number in drawing units")
                numeric_width = None
            else:
                numeric_width = float(width)
                if numeric_width <= 0:
                    local_errors.append("stroke-width is not positive")
            pen = RecordingPen()
            try:
                parse_path(element.attrib.get("d", ""), pen)
            except Exception as error:
                local_errors.append(f"invalid centerline: {error}")
            operators = [operator for operator, _ in pen.value]
            if operators.count("moveTo") != 1:
                local_errors.append("one path must represent exactly one continuous stroke")
            if "closePath" in operators and not allow_closed:
                local_errors.append("closed subpath found where open strokes are required")
            if not any(operator in ("lineTo", "curveTo", "qCurveTo") for operator in operators):
                local_errors.append("stroke has no drawable segment")
            angles = tangent_deviations(pen.value)
            samples, minimum_radius = sample_geometry(pen.value)
            sampled_strokes[label] = samples
            strokes.append({
                "id": label,
                "width": numeric_width,
                "segments": sum(operator in ("lineTo", "curveTo", "qCurveTo") for operator in operators),
                "closed": "closePath" in operators,
                "maximum_join_angle_degrees": max(angles, default=0),
                "minimum_curve_radius": minimum_radius,
                "inner_offset_radius_positive": (minimum_radius > numeric_width / 2
                                                  if minimum_radius is not None and numeric_width is not None
                                                  else None),
            })
            errors.extend(f"{label}: {error}" for error in local_errors)
        elif tag in ("polygon", "polyline", "circle", "ellipse", "rect", "line", "image", "use", "text"):
            # Display annotations should live in a separate proof, not the glyph source.
            errors.append(f"unexpected drawable element {tag!r} in centerline glyph source")
        for child in element:
            visit(child, style, transformed)

    visit(root, {})
    if not strokes:
        errors.append("no editable centerline strokes found")
    if expected_strokes is not None and len(strokes) != expected_strokes:
        errors.append(f"expected {expected_strokes} strokes, found {len(strokes)}")
    widths = sorted({stroke["width"] for stroke in strokes if stroke["width"] is not None})
    if len(widths) > 1:
        errors.append(f"stroke widths differ: {widths}")
    junction_reports = []
    for junction in junctions:
        pair = junction.split(":")
        if len(pair) != 2 or any(label not in sampled_strokes for label in pair):
            errors.append(f"unknown stroke pair {junction!r}; use path IDs separated by ':'")
            continue
        distance = polyline_distance(*(sampled_strokes[label] for label in pair))
        width = widths[0] if len(widths) == 1 else None
        junction_reports.append({
            "strokes": pair,
            "minimum_centerline_distance": distance,
            "centerlines_intersect": distance < 0.001,
            "round_stroke_ink_connects": distance < width if width is not None else None,
        })
    return {
        "source": str(path),
        "passed": not errors,
        "stroke_count": len(strokes),
        "uniform_width": widths[0] if len(widths) == 1 else None,
        "strokes": strokes,
        "junctions": junction_reports,
        "errors": errors,
        "scope": "Editable geometry contract; join angles are descriptive, not a historical stroke-order claim.",
    }


def audit_source_data(source: Path, svg: Path, report: dict) -> None:
    """Cross-check editable stroke records against the actual rendered SVG paths."""
    data = json.loads(source.read_text())
    root = ET.parse(svg).getroot()
    svg_paths = {element.attrib.get("id"): element.attrib.get("d", "")
                 for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "path"}
    source_strokes = data.get("strokes", [])
    source_ids = [stroke.get("id") for stroke in source_strokes]
    errors = []
    if len(source_ids) != len(set(source_ids)):
        errors.append("stroke IDs are not unique")
    if set(source_ids) != set(svg_paths):
        errors.append("source and SVG stroke IDs differ")
    if data.get("stroke_width") != report["uniform_width"]:
        errors.append("source and SVG uniform widths differ")
    if data.get("linecap") != "round" or data.get("linejoin") != "round":
        errors.append("source cap/join settings are not round")
    for stroke in source_strokes:
        label = stroke.get("id")
        if stroke.get("closed") is not False:
            errors.append(f"{label}: source is not explicitly an open stroke")
        for forbidden in ("width", "stroke_width", "stroke-width", "taper", "pressure"):
            if forbidden in stroke:
                errors.append(f"{label}: per-stroke {forbidden!r} overrides the constant-width contract")
        if label in svg_paths:
            left, right = RecordingPen(), RecordingPen()
            parse_path(stroke.get("path", ""), left)
            parse_path(svg_paths[label], right)
            if left.value != right.value:
                errors.append(f"{label}: SVG path differs from editable source geometry")
    report["source_data"] = {
        "source": str(source),
        "stroke_count": len(source_strokes),
        "svg_matches_editable_paths": not errors,
        "errors": errors,
    }
    report["errors"].extend(f"source data: {error}" for error in errors)
    report["passed"] = not report["errors"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", type=Path)
    parser.add_argument("--expected-strokes", type=int)
    parser.add_argument("--allow-closed", action="store_true")
    parser.add_argument("--junction", action="append", default=[], metavar="PATH_ID:PATH_ID")
    parser.add_argument("--source-json", type=Path)
    arguments = parser.parse_args()
    report = audit(arguments.svg, arguments.expected_strokes, arguments.allow_closed,
                   tuple(arguments.junction))
    if arguments.source_json:
        audit_source_data(arguments.source_json, arguments.svg, report)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
