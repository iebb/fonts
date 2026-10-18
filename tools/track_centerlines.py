#!/usr/bin/env python3
"""Derive editable pen centerlines from immutable ImageGen glyph drawings.

This is a geometric aid, not an assertion of a historical writing order. Alpha
is thinned to a one-pixel graph; tiny terminal spurs are removed and straight
continuations are paired at crossings. Ambiguous junctions remain recorded for
manual review. The output is open SVG stroke paths, never brush perimeters.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.interpolate import splprep, splev


Pixel = tuple[int, int]
ROOT = Path(__file__).resolve().parents[1]


def thin(mask: np.ndarray) -> np.ndarray:
    """Zhang–Suen topology-preserving thinning, using only NumPy arrays."""
    result = np.pad(np.asarray(mask, dtype=bool), 1)
    while True:
        changed = False
        for step in (0, 1):
            center = result[1:-1, 1:-1]
            ring = [result[:-2, 1:-1], result[:-2, 2:], result[1:-1, 2:],
                    result[2:, 2:], result[2:, 1:-1], result[2:, :-2],
                    result[1:-1, :-2], result[:-2, :-2]]
            neighbours = sum(value.astype(np.uint8) for value in ring)
            transitions = sum((~ring[index] & ring[(index + 1) % 8]).astype(np.uint8)
                              for index in range(8))
            remove = center & (neighbours >= 2) & (neighbours <= 6) & (transitions == 1)
            if step == 0:
                remove &= ~(ring[0] & ring[2] & ring[4]) & ~(ring[2] & ring[4] & ring[6])
            else:
                remove &= ~(ring[0] & ring[2] & ring[6]) & ~(ring[0] & ring[4] & ring[6])
            if remove.any():
                center[remove] = False
                changed = True
        if not changed:
            return result[1:-1, 1:-1].copy()


def pixel_graph(skeleton: np.ndarray) -> dict[Pixel, set[Pixel]]:
    """Use diagonal links only where no orthogonal step already connects them.

    This avoids artificial three-edge triangles around staircase pixels while
    preserving diagonal strokes and their true crossings.
    """
    pixels = {(int(x), int(y)) for y, x in np.argwhere(skeleton)}
    graph = {point: set() for point in pixels}
    for x, y in pixels:
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            other = x + dx, y + dy
            if other not in pixels:
                continue
            if dx and dy and ((x + dx, y) in pixels or (x, y + dy) in pixels):
                continue
            graph[x, y].add(other)
            graph[other].add((x, y))
    return graph


def _length(points) -> float:
    return sum(math.dist(first, last) for first, last in zip(points, points[1:]))


def prune_spurs(graph: dict[Pixel, set[Pixel]], limit: float = 7) -> int:
    """Remove short endpoint-to-junction twigs, keeping isolated small strokes."""
    removed = 0
    while True:
        candidates = set()
        for start in sorted(graph):
            if len(graph[start]) != 1:
                continue
            chain, previous, current = [start], None, start
            while True:
                following = graph[current] - ({previous} if previous is not None else set())
                if len(following) != 1:
                    break
                previous, current = current, next(iter(following))
                chain.append(current)
                if len(graph[current]) != 2:
                    break
            if len(graph[current]) > 2 and _length(chain) < limit:
                candidates.update(chain[:-1])
        if not candidates:
            break
        for point in candidates:
            for neighbour in graph[point]:
                graph[neighbour].discard(point)
            del graph[point]
        removed += len(candidates)
    return removed


def compress_graph(graph: dict[Pixel, set[Pixel]], cluster_distance: float = 4) -> tuple[list, list]:
    """Collapse junction clusters, retaining graph edges as ordered polylines."""
    branch = {point for point, neighbours in graph.items() if len(neighbours) > 2}
    parent = {point: point for point in branch}

    def find(point):
        while parent[point] != point:
            parent[point] = parent[parent[point]]
            point = parent[point]
        return point

    # Nearby branch pixels joined by a short skeleton chain describe one joint.
    # Only the connecting chain is absorbed; endpoints are never swept into it.
    connectors = []
    for start in sorted(branch):
        for neighbour in graph[start]:
            chain, previous, current = [start, neighbour], start, neighbour
            while current not in branch and len(graph[current]) == 2 and _length(chain) <= cluster_distance:
                following = next(iter(graph[current] - {previous}))
                previous, current = current, following
                chain.append(current)
            if current in branch and _length(chain) <= cluster_distance:
                parent[find(current)] = find(start)
                connectors.append(chain)
    groups = defaultdict(set)
    for point in branch:
        groups[find(point)].add(point)
    for chain in connectors:
        groups[find(chain[0])].update(chain)
    nodes = [groups[key] for key in sorted(groups)]
    nodes += [{point} for point in sorted(graph) if len(graph[point]) < 2]
    node_of = {point: index for index, group in enumerate(nodes) for point in group}
    centers = [np.asarray(sorted(group), dtype=float).mean(axis=0).tolist() for group in nodes]
    edges, visited = [], set()

    def link(first, last):
        return tuple(sorted((first, last)))

    for node_index, group in enumerate(nodes):
        for first in sorted(group):
            for second in sorted(graph[first]):
                if second in group or link(first, second) in visited:
                    continue
                visited.add(link(first, second))
                path, previous, current = [centers[node_index]], first, second
                while current not in node_of:
                    path.append(list(current))
                    choices = graph[current] - {previous}
                    if not choices:
                        break
                    following = min(choices)
                    visited.add(link(current, following))
                    previous, current = current, following
                end = node_of.get(current)
                if end is None:
                    raise ValueError("unclassified skeleton endpoint")
                path.append(centers[end])
                edges.append({"start": node_index, "end": end, "points": path})
    # Components with no endpoint or branch are loops. Keep their centerlines.
    for first in sorted(graph):
        choices = [point for point in sorted(graph[first]) if link(first, point) not in visited]
        if not choices or first in node_of:
            continue
        path, previous, current = [list(first)], first, choices[0]
        visited.add(link(first, current))
        while current != first:
            path.append(list(current))
            choices = graph[current] - {previous}
            if not choices:
                break
            following = min(choices)
            visited.add(link(current, following))
            previous, current = current, following
        path.append(list(first))
        node_index = len(centers)
        centers.append(list(first))
        edges.append({"start": node_index, "end": node_index, "points": path})
    for point in sorted(graph):
        if not graph[point]:
            # A tiny round mark has no measurable direction; keep an explicit
            # short open segment instead of inventing an outline contour.
            node_index = len(centers)
            centers.append(list(point))
            edges.append({"start": node_index, "end": node_index,
                          "points": [[point[0] - 0.05, point[1]], [point[0] + 0.05, point[1]]],
                          "point_mark": True})
    return centers, edges


def _outward_tangent(points, end, reach=12):
    sequence = points if end == 0 else points[::-1]
    origin = np.asarray(sequence[0], dtype=float)
    travelled = 0
    for first, last in zip(sequence, sequence[1:]):
        travelled += math.dist(first, last)
        target = np.asarray(last, dtype=float)
        if travelled >= reach:
            break
    vector = target - origin
    length = float(np.linalg.norm(vector))
    return vector / length if length else np.zeros(2)


def connect_strokes(centers: list, edges: list) -> tuple[list, list]:
    """Follow near-straight branches across joints, without adding new links."""
    incident = defaultdict(list)
    for index, edge in enumerate(edges):
        incident[edge["start"]].append((index, 0))
        incident[edge["end"]].append((index, 1))
    continuations, junctions = {}, []
    for node, halves in sorted(incident.items()):
        vectors = {half: _outward_tangent(edges[half[0]]["points"], half[1]) for half in halves}
        candidates = sorted((float(np.dot(vectors[a], vectors[b])), a, b)
                            for a, b in itertools.combinations(halves, 2)
                            if a[0] != b[0])
        paired = set()
        pairs = []
        for cosine, a, b in candidates:
            # A 120-degree Y joint is deliberately not forced into a stroke.
            if cosine > -math.sqrt(0.5) or a in paired or b in paired:
                continue
            continuations[node, a] = b
            continuations[node, b] = a
            paired.update((a, b))
            pairs.append({"edges": [a[0], b[0]], "angle_degrees": round(math.degrees(math.acos(max(-1, min(1, cosine)))), 2)})
        if len(halves) > 2:
            junctions.append({"point": centers[node], "degree": len(halves), "continuations": pairs,
                              "unpaired_branches": len(halves) - 2 * len(pairs),
                              "review_required": True})
    starts = []
    for node, halves in sorted(incident.items()):
        starts.extend(half for half in halves if (node, half) not in continuations)
    starts.extend((index, 0) for index in range(len(edges)))
    seen, strokes = set(), []
    for first_edge, first_end in starts:
        if first_edge in seen:
            continue
        points, constituents = [], []
        edge_index, end = first_edge, first_end
        while edge_index not in seen:
            seen.add(edge_index)
            constituents.append(edge_index)
            edge = edges[edge_index]
            sequence = edge["points"] if end == 0 else edge["points"][::-1]
            points.extend(sequence if not points else sequence[1:])
            node = edge["end"] if end == 0 else edge["start"]
            following = continuations.get((node, (edge_index, 1 - end)))
            if following is None:
                break
            edge_index, end = following
        if len(points) >= 2:
            strokes.append({"points": points, "graph_edges": constituents,
                            "is_loop": math.dist(points[0], points[-1]) < 0.01})
    return strokes, junctions


def _number(value) -> float:
    return round(float(value), 4)


def _pair(point) -> str:
    return f"{_number(point[0]):g},{_number(point[1]):g}"


def fit_centerline(points: list, tolerance: float = 1) -> dict:
    """Smooth cubic fit, checked against every original centerline sample."""
    array = np.asarray(points, dtype=float)
    keep = np.r_[True, np.any(np.diff(array, axis=0) != 0, axis=1)]
    array = array[keep]
    if len(array) < 2:
        raise ValueError("a stroke needs two distinct centerline points")
    # Replace almost-straight pixel staircases with one actual straight stroke.
    direction = array[-1] - array[0]
    length = float(np.linalg.norm(direction))
    if length:
        relative = array - array[0]
        distance = np.abs(direction[0] * relative[:, 1] - direction[1] * relative[:, 0]) / length
        projections = (array - array[0]) @ direction / (length * length)
        if float(distance.max()) <= tolerance and projections.min() >= 0 and projections.max() <= 1:
            return {"path": f"M {_pair(array[0])} L {_pair(array[-1])}",
                    "commands": [["M", *map(_number, array[0])], ["L", *map(_number, array[-1])]],
                    "maximum_fit_error": _number(distance.max()), "curve_segments": 1}
    degree = min(3, len(array) - 1)
    for multiplier in (1, 0.5, 0.25, 0.125, 0.0625, 0):
        tck, parameter = splprep(array.T, s=len(array) * 0.40 * multiplier, k=degree)
        tck[1][0][0], tck[1][1][0] = array[0]
        tck[1][0][-1], tck[1][1][-1] = array[-1]
        approximation = np.asarray(splev(parameter, tck)).T
        maximum_error = float(np.linalg.norm(approximation - array, axis=1).max())
        if maximum_error <= tolerance + 1e-8:
            break
    knots = sorted({float(value) for value in tck[0] if 0 <= value <= 1})
    commands = [["M", *map(_number, array[0])]]
    svg = ["M " + _pair(array[0])]
    for start, end in zip(knots, knots[1:]):
        first, last = np.asarray(splev(start, tck)), np.asarray(splev(end, tck))
        control1 = first + np.asarray(splev(start, tck, der=1)) * (end - start) / 3
        control2 = last - np.asarray(splev(end, tck, der=1)) * (end - start) / 3
        commands.append(["C", *map(_number, control1), *map(_number, control2), *map(_number, last)])
        svg.append("C " + " ".join(_pair(point) for point in (control1, control2, last)))
    return {"path": " ".join(svg), "commands": commands,
            "maximum_fit_error": _number(maximum_error), "curve_segments": len(commands) - 1}


def extract_strokes(mask: np.ndarray, tolerance=1, spur_limit=7) -> tuple[list, dict]:
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=bool))
    areas = np.bincount(labels.ravel())
    retained = areas >= 12
    retained[0] = False
    clean = retained[labels]
    skeleton = thin(clean)
    graph = pixel_graph(skeleton)
    pruned = prune_spurs(graph, spur_limit)
    centers, edges = compress_graph(graph)
    strokes, junctions = connect_strokes(centers, edges)
    for index, stroke in enumerate(strokes):
        stroke.update(fit_centerline(stroke["points"], tolerance))
        stroke.update({"id": f"stroke-{index + 1}", "closed": False})
        stroke["points"] = [[_number(x), _number(y)] for x, y in stroke["points"]]
    return strokes, {"retained_mask_components": int(np.count_nonzero(retained)),
                     "removed_small_components": int(count - np.count_nonzero(retained)),
                     "skeleton_pixels": int(skeleton.sum()), "pruned_spur_pixels": pruned,
                     "graph_edges": len(edges), "junctions": junctions,
                     "ambiguity": "Branches are geometric inferences. Original writing order and crossing pen lifts cannot be established from a flat image."}


def write_svg(record: dict, output: Path) -> None:
    view = " ".join(str(value) for value in record["viewBox"])
    paths = "\n".join(f'  <path id="{stroke["id"]}" d="{stroke["path"]}"/>' for stroke in record["strokes"])
    output.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}">\n'
                      f'<title>{record["codepoint"]} editable geometric centerlines</title>\n'
                      f'<g fill="none" stroke="black" stroke-width="{record["stroke_width"]}" '
                      f'stroke-linecap="round" stroke-linejoin="round">\n{paths}\n</g>\n</svg>\n', encoding="utf-8")


def track_sheets(source: Path = ROOT / "design/seal", output: Path = ROOT / "design/strokes/auto",
                 batch_count: int = 4) -> dict:
    if not 1 <= batch_count <= 4:
        raise ValueError("batch_count must be between 1 and 4")
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for batch in range(batch_count):
        start = 0x3D000 + batch * 16
        path = source / f"redraw-{start:05X}-{start + 15:05X}.png"
        source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        generation_manifest = path.with_suffix(".json")
        generation = json.loads(generation_manifest.read_text()) if generation_manifest.is_file() else {}
        generation_review = {key: generation[key] for key in (
            "tool", "flags", "status", "review_status", "historical_stroke_order_verified",
            "reference_evidence", "evidence", "evidence_policy") if key in generation}
        if generation_manifest.is_file():
            generation_review.update({"manifest": str(generation_manifest.relative_to(ROOT)),
                                      "manifest_sha256": hashlib.sha256(generation_manifest.read_bytes()).hexdigest()})
        image = Image.open(path)
        if image.mode != "RGBA":
            raise ValueError(f"{path}: expected original RGBA source")
        alpha = np.asarray(image.getchannel("A"))
        for index in range(16):
            row, column = divmod(index, 4)
            left, right = column * image.width // 4, (column + 1) * image.width // 4
            top, bottom = row * image.height // 4, (row + 1) * image.height // 4
            strokes, topology = extract_strokes(alpha[top:bottom, left:right] >= 128)
            cp = start + index
            record = {"schema_version": 1, "codepoint": f"U+{cp:05X}",
                      "viewBox": [0, 0, right - left, bottom - top],
                      "stroke_width": 13, "linecap": "round", "linejoin": "round",
                      "status": "automatic_unreviewed", "coverage_eligible": False,
                      "character_identity_verified": False, "historical_stroke_order_verified": False,
                      "stroke_order": "Geometrically inferred path sequence; not historical writing order.",
                      "source": {"file": str(path.relative_to(ROOT)), "sha256": source_hash,
                                 "cell": [left, top, right, bottom], "alpha_threshold": 128,
                                 "source_pixels_modified": False,
                                 "generation_review": generation_review},
                      "algorithm": {"skeleton": "Zhang-Suen", "spur_limit_source_pixels": 7,
                                    "junction_cluster_distance_source_pixels": 4,
                                    "minimum_continuation_angle_degrees": 135,
                                    "fit_tolerance_source_pixels": 1,
                                    "outline_sources_used": False},
                      "topology": topology, "strokes": strokes}
            target = output / f"U{cp:05X}"
            target.with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            write_svg(record, target.with_suffix(".svg"))
            records.append({"codepoint": record["codepoint"], "strokes": len(strokes),
                            "junctions": len(topology["junctions"]),
                            "maximum_fit_error": max((stroke["maximum_fit_error"] for stroke in strokes), default=0)})
        if hashlib.sha256(path.read_bytes()).hexdigest() != source_hash:
            raise ValueError("immutable source changed while processing")
    summary = {"glyph_count": len(records), "stroke_count": sum(record["strokes"] for record in records),
               "status": "automatic_unreviewed", "source_type": "immutable ImageGen alpha drawings",
               "maximum_fit_error_source_pixels": max(record["maximum_fit_error"] for record in records),
               "manual_overrides": f"Use {output.parent.relative_to(ROOT)}/Uxxxxx.json in preference to auto/Uxxxxx.json when present.",
               "glyphs": records}
    (output / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def _location(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _atomic_text(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _normalized_stroke(stroke: dict, factor: float) -> dict:
    result = dict(stroke)
    result["points"] = [[_number(x * factor), _number(y * factor)] for x, y in stroke["points"]]
    result["commands"] = [[command[0], *(_number(value * factor) for value in command[1:])]
                          for command in stroke["commands"]]
    result["path"] = " ".join(command[0] + " " + " ".join(
        _pair(command[index:index + 2]) for index in range(1, len(command), 2))
        for command in result["commands"])
    result["maximum_fit_error_analysis_pixels"] = stroke["maximum_fit_error"]
    result["maximum_fit_error_font_units"] = _number(stroke["maximum_fit_error"] * factor)
    result["maximum_fit_error"] = result["maximum_fit_error_font_units"]
    return result


def track_single_images(source: Path, output: Path, start: int = 0x3D000,
                        count: int = 64, incremental: bool = False) -> dict:
    """Track one native PNG per codepoint; skip unchanged complete records.

    Each PNG and its per-character provenance JSON must both exist. Incremental
    runs skip pairs still being produced, so glyphs can be delivered one by one.
    Alpha is resized only in memory for analysis; source files are immutable.
    """
    if count < 1 or start < 0 or start + count > 0x110000 or start <= 0xDFFF and start + count > 0xD800:
        raise ValueError("requested range must contain Unicode scalar values")
    output.mkdir(parents=True, exist_ok=True)
    updated, unchanged, pending = [], [], []
    for cp in range(start, start + count):
        label = f"U{cp:05X}"
        image_path, provenance_path = source / (label + ".png"), source / (label + ".json")
        if not image_path.is_file() or not provenance_path.is_file():
            if incremental:
                pending.append(f"U+{cp:05X}")
                continue
            raise FileNotFoundError(f"{label}: both the native PNG and its provenance JSON are required")
        source_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
        provenance_hash = hashlib.sha256(provenance_path.read_bytes()).hexdigest()
        review_path = source / "reviews" / (label + ".json")
        review_hash = hashlib.sha256(review_path.read_bytes()).hexdigest() if review_path.is_file() else None
        target = output / (label + ".json")
        svg_path = output / (label + ".svg")
        if target.is_file() and svg_path.is_file():
            previous = json.loads(target.read_text())
            previous_source = previous.get("source", {})
            if (previous_source.get("sha256") == source_hash
                    and previous_source.get("generation_review", {}).get("manifest_sha256") == provenance_hash
                    and previous_source.get("visual_reference_review", {}).get("review_sha256") == review_hash):
                unchanged.append(f"U+{cp:05X}")
                continue
        generation = json.loads(provenance_path.read_text())
        visual_review = json.loads(review_path.read_text()) if review_path.is_file() else {}
        if visual_review and visual_review.get("source_png_sha256") != source_hash:
            visual_review = {"verdict": "stale", "notes": ["Review applies to a different PNG hash."]}
        if review_hash:
            visual_review.update({"review_file": _location(review_path), "review_sha256": review_hash})
        with Image.open(image_path) as image:
            if image.mode != "RGBA":
                raise ValueError(f"{image_path}: expected original RGBA source")
            original_size = list(image.size)
            original_alpha = image.getchannel("A")
            analysis_size = 313
            size_factor = analysis_size / max(image.size)
            resized_size = tuple(max(1, round(dimension * size_factor)) for dimension in image.size)
            resized_alpha = original_alpha.resize(resized_size, resample=Image.Resampling.LANCZOS)
            analysis_alpha = np.zeros((analysis_size, analysis_size), dtype=np.uint8)
            offset_x, offset_y = ((analysis_size - dimension) // 2 for dimension in resized_size)
            analysis_alpha[offset_y:offset_y + resized_size[1], offset_x:offset_x + resized_size[0]] = np.asarray(resized_alpha)
        strokes, topology = extract_strokes(analysis_alpha >= 128)
        factor = 1024 / analysis_size
        normalized = [_normalized_stroke(stroke, factor) for stroke in strokes]
        for junction in topology["junctions"]:
            junction["point_analysis_pixels"] = junction["point"]
            junction["point"] = [_number(coordinate * factor) for coordinate in junction["point"]]
        generation_review = dict(generation)
        generation_review.update({"manifest": _location(provenance_path),
                                  "manifest_sha256": provenance_hash})
        maximum_analysis_error = max((stroke["maximum_fit_error_analysis_pixels"] for stroke in normalized), default=0)
        maximum_font_error = max((stroke["maximum_fit_error_font_units"] for stroke in normalized), default=0)
        record = {"schema_version": 1, "codepoint": f"U+{cp:05X}", "viewBox": [0, 0, 1024, 1024],
                  "stroke_width": 43, "linecap": "round", "linejoin": "round",
                  "status": "automatic_unreviewed", "coverage_eligible": False,
                  "character_identity_verified": generation.get("character_identity_verified") is True,
                  "visual_reference_match_reviewed": visual_review.get("verdict") == "match",
                  "historical_stroke_order_verified": False,
                  "stroke_order": "Geometrically inferred path sequence; not historical writing order.",
                  "source": {"file": _location(image_path), "sha256": source_hash,
                             "source_pixels_modified": False, "source_layout": "one complete glyph per native PNG",
                             "original_size": original_size, "generation_review": generation_review,
                             "visual_reference_review": visual_review,
                             "alpha_threshold": 128,
                             "readonly_alpha_analysis": {"size": [analysis_size, analysis_size],
                                                         "resized_alpha_size": list(resized_size),
                                                         "padding_offset": [offset_x, offset_y],
                                                         "resample": "Pillow LANCZOS; in-memory alpha only"}},
                  "algorithm": {"skeleton": "Zhang-Suen", "spur_limit_analysis_pixels": 7,
                                "junction_cluster_distance_analysis_pixels": 4,
                                "minimum_continuation_angle_degrees": 135,
                                "fit_tolerance_analysis_pixels": 1,
                                "fit_tolerance_font_units": _number(factor),
                                "analysis_pixels_to_font_units": factor,
                                "outline_sources_used": False},
                  "maximum_fit_error_analysis_pixels": maximum_analysis_error,
                  "maximum_fit_error_font_units": maximum_font_error,
                  "topology": topology, "strokes": normalized}
        if not normalized:
            raise ValueError(f"{label}: native source contains no retained glyph strokes")
        if hashlib.sha256(image_path.read_bytes()).hexdigest() != source_hash:
            raise ValueError("immutable source changed while processing")
        _atomic_text(target, json.dumps(record, indent=2) + "\n")
        temporary_svg = svg_path.with_suffix(".svg.tmp")
        write_svg(record, temporary_svg)
        temporary_svg.replace(svg_path)
        updated.append(record["codepoint"])
    records = []
    for path in sorted(output.glob("U*.json")):
        record = json.loads(path.read_text())
        records.append({"codepoint": record["codepoint"], "strokes": len(record["strokes"]),
                        "source_sha256": record["source"]["sha256"],
                        "status": record["status"],
                        "character_identity_verified": record.get("character_identity_verified", False),
                        "maximum_fit_error_analysis_pixels": record.get("maximum_fit_error_analysis_pixels", 0),
                        "maximum_fit_error_font_units": record.get("maximum_fit_error_font_units", 0)})
    summary = {"glyph_count": len(records), "stroke_count": sum(record["strokes"] for record in records),
               "status": "automatic_unreviewed", "source_type": "one immutable native ImageGen PNG per glyph",
               "viewBox": [0, 0, 1024, 1024], "stroke_width_font_units": 43,
               "maximum_fit_error_analysis_pixels": max((record["maximum_fit_error_analysis_pixels"] for record in records), default=0),
               "maximum_fit_error_font_units": max((record["maximum_fit_error_font_units"] for record in records), default=0),
               "updated": updated, "unchanged": unchanged, "pending": pending,
               "manual_overrides": f"Use {_location(output.parent)}/Uxxxxx.json in preference to auto/Uxxxxx.json when present.",
               "glyphs": records}
    _atomic_text(output / "manifest.json", json.dumps(summary, indent=2) + "\n")
    return summary


def _codepoint(value: str) -> int:
    value = value.upper().removeprefix("U+").removeprefix("U").removeprefix("0X")
    return int(value, 16)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--batch-count", type=int, default=4, choices=range(1, 5))
    parser.add_argument("--single-images", action="store_true", help="one native Uxxxxx.png and provenance JSON per glyph")
    parser.add_argument("--start", type=_codepoint, default=0x3D000, help="first codepoint, hexadecimal (default U+3D000)")
    parser.add_argument("--count", type=int, default=64, help="number of individual glyphs (default 64)")
    parser.add_argument("--incremental", action="store_true", help="skip native image/provenance pairs still being produced")
    arguments = parser.parse_args()
    if arguments.single_images:
        report = track_single_images(arguments.source or ROOT / "design/seal-individual",
                                     arguments.output or ROOT / "design/strokes-individual/auto",
                                     arguments.start, arguments.count, arguments.incremental)
    else:
        report = track_sheets(arguments.source or ROOT / "design/seal",
                              arguments.output or ROOT / "design/strokes/auto", arguments.batch_count)
    print(json.dumps({key: value for key, value in report.items() if key != "glyphs"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
