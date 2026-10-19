#!/usr/bin/env python3
"""Check reference-backed glyph structure in actual static/variable font rasters.

The checks consume only the font and an explicit invariant specification. They
do not trust centerline JSON, glyph names, or source artwork as proof that the
built font retains its required strokes and proportions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import find_objects, label


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC = ROOT / "design/quality/invariants.json"


def ink_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    rows, columns = np.nonzero(mask)
    if not len(rows):
        return None
    return int(columns.min()), int(rows.min()), int(columns.max()) + 1, int(rows.max()) + 1


def ink_runs(row: np.ndarray) -> list[tuple[int, int]]:
    edges = np.diff(np.pad(row.astype(np.int8), 1))
    return [(int(start), int(end)) for start, end in
            zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))]


def _components(mask: np.ndarray) -> list[dict]:
    labels, _ = label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    result = []
    for number, slices in enumerate(find_objects(labels), 1):
        if slices is None:
            continue
        y_slice, x_slice = slices
        area = int((labels[slices] == number).sum())
        width, height = x_slice.stop - x_slice.start, y_slice.stop - y_slice.start
        result.append({
            "bbox_pixels": [x_slice.start, y_slice.start, x_slice.stop, y_slice.stop],
            "ink_pixels": area, "ink_span_pixels": width, "height_pixels": height,
            "horizontal_aspect": width / height, "fill_ratio": area / (width * height),
            "center_y_pixels": (y_slice.start + y_slice.stop - 1) / 2,
        })
    return sorted(result, key=lambda value: value["center_y_pixels"])


def check_two_bars(mask: np.ndarray, rule: dict, em_pixels: int) -> tuple[dict, list[str]]:
    del em_pixels
    components = _components(mask)
    measured = {"ink_component_count": len(components), "components": components}
    errors = []
    if len(components) != 2:
        errors.append(f"expected exactly 2 detached bars, found {len(components)} ink components")
        return measured, errors
    for index, component in enumerate(components):
        if component["horizontal_aspect"] < rule.get("minimum_horizontal_aspect", 4):
            errors.append(f"bar {index + 1} is not sufficiently horizontal")
        if component["fill_ratio"] < rule.get("minimum_fill_ratio", 0.55):
            errors.append(f"bar {index + 1} is not a filled bar")
    upper, lower = components
    ratio = lower["ink_span_pixels"] / upper["ink_span_pixels"]
    gap = lower["center_y_pixels"] - upper["center_y_pixels"]
    gap_ratio = gap / lower["ink_span_pixels"]
    measured.update({"upper_ink_span_pixels": upper["ink_span_pixels"],
                     "lower_ink_span_pixels": lower["ink_span_pixels"],
                     "lower_to_upper_ink_span_ratio": ratio,
                     "vertical_center_gap_pixels": gap,
                     "vertical_gap_to_lower_ink_span_ratio": gap_ratio})
    if ratio < rule["minimum_lower_to_upper_ink_span_ratio"]:
        errors.append(f"lower/upper ink span ratio {ratio:.6f} is below "
                      f"{rule['minimum_lower_to_upper_ink_span_ratio']}")
    if ratio > rule.get("maximum_lower_to_upper_ink_span_ratio", math.inf):
        errors.append(f"lower/upper ink span ratio {ratio:.6f} is above "
                      f"{rule['maximum_lower_to_upper_ink_span_ratio']}")
    if gap_ratio < rule["minimum_vertical_gap_to_lower_ink_span_ratio"]:
        errors.append(f"vertical center gap/lower ink span ratio {gap_ratio:.6f} is below "
                      f"{rule['minimum_vertical_gap_to_lower_ink_span_ratio']}")
    return measured, errors


def check_lower_descenders(mask: np.ndarray, rule: dict, em_pixels: int) -> tuple[dict, list[str]]:
    bounds = ink_bbox(mask)
    if bounds is None:
        return {}, ["glyph contains no ink"]
    _, top, _, bottom = bounds
    minimum_span = max(1, math.ceil(rule.get("minimum_run_span_em", 0.004) * em_pixels))
    rows, errors = [], []
    for fraction in rule["sample_height_fractions"]:
        y = top + round((bottom - top - 1) * fraction)
        runs = ink_runs(mask[y])
        major = [(start, end) for start, end in runs if end - start >= minimum_span]
        rows.append({"height_fraction": fraction, "row_pixels": y,
                     "major_descender_count": len(major),
                     "major_ink_runs_pixels": [list(run) for run in major],
                     "ignored_short_runs_pixels": [list(run) for run in runs if run not in major]})
        if len(major) != rule["expected_descenders"]:
            errors.append(f"height fraction {fraction:g}: expected {rule['expected_descenders']} "
                          f"major lower descenders, found {len(major)}")
    return {"ink_bbox_pixels": list(bounds), "minimum_major_run_pixels": minimum_span,
            "scan_rows": rows}, errors


def check_component_count(mask: np.ndarray, rule: dict, em_pixels: int) -> tuple[dict, list[str]]:
    del em_pixels
    components = _components(mask)
    count, expected = len(components), rule["expected_components"]
    return {"ink_component_count": count, "components": components}, ([] if count == expected else
            [f"expected exactly {expected} connected ink components, found {count}"])


def check_roi_bar_ratio(mask: np.ndarray, rule: dict, em_pixels: int) -> tuple[dict, list[str]]:
    del em_pixels
    bounds = ink_bbox(mask)
    if bounds is None:
        return {}, ["glyph contains no ink"]
    left, top, right, bottom = bounds
    x_fractions = rule.get("roi_width_fractions", [0, 1])
    x_first = left + round((right-left-1) * x_fractions[0])
    x_last = left + round((right-left-1) * x_fractions[1]) + 1

    def longest_in_roi(fractions):
        first = top + round((bottom - top - 1) * fractions[0])
        last = top + round((bottom - top - 1) * fractions[1])
        candidates = [(end-start, y, start+x_first, end+x_first) for y in range(first, last + 1)
                      for start, end in ink_runs(mask[y, x_first:x_last])]
        if not candidates:
            return {"ink_span_pixels": 0, "roi_rows_pixels": [first, last]}
        width, row, start, end = max(candidates)
        return {"ink_span_pixels": width, "row_pixels": row,
                "ink_run_pixels": [start, end], "roi_rows_pixels": [first, last]}

    upper = longest_in_roi(rule["upper_roi_height_fractions"])
    lower = longest_in_roi(rule["lower_roi_height_fractions"])
    measured = {"ink_bbox_pixels": list(bounds), "upper_bar": upper, "lower_bar": lower}
    if not upper["ink_span_pixels"] or not lower["ink_span_pixels"]:
        return measured, ["one of the specified horizontal-bar regions contains no ink"]
    ratio = upper["ink_span_pixels"] / lower["ink_span_pixels"]
    measured["upper_to_lower_ink_span_ratio"] = ratio
    minimum, maximum = rule["minimum_upper_to_lower_ink_span_ratio"], rule["maximum_upper_to_lower_ink_span_ratio"]
    return measured, ([] if minimum <= ratio <= maximum else
                      [f"upper/lower horizontal ink span ratio {ratio:.6f} is outside {minimum:g}–{maximum:g}"])


def check_roi_ink_presence(mask: np.ndarray, rule: dict, em_pixels: int) -> tuple[dict, list[str]]:
    bounds = ink_bbox(mask)
    if bounds is None:
        return {}, ["glyph contains no ink"]
    left, top, right, bottom = bounds
    xf, yf = rule["roi_width_fractions"], rule["roi_height_fractions"]
    x0, x1 = (left + round((right-left-1)*fraction) for fraction in xf)
    y0, y1 = (top + round((bottom-top-1)*fraction) for fraction in yf)
    region = mask[y0:y1+1, x0:x1+1]
    pixels = int(region.sum())
    minimum = max(1, math.ceil(rule.get("minimum_ink_area_em_squared", 0) * em_pixels**2))
    fraction = float(region.mean()) if region.size else 0
    measured = {"ink_bbox_pixels": list(bounds), "roi_bbox_pixels": [x0, y0, x1+1, y1+1],
                "ink_pixels": pixels, "ink_fraction": fraction,
                "minimum_ink_pixels": minimum}
    errors = []
    if pixels < minimum or fraction < rule.get("minimum_ink_fraction", 0):
        errors.append(f"required isolated stroke region has {pixels} ink pixels "
                      f"({fraction:.4f} of the region)")
    return measured, errors


def check_roi_right_extent(mask: np.ndarray, rule: dict, em_pixels: int) -> tuple[dict, list[str]]:
    bounds = ink_bbox(mask)
    if bounds is None:
        return {}, ["glyph contains no ink"]
    left, top, right, bottom = bounds
    x0, x1 = (left + round((right-left-1)*fraction) for fraction in rule["roi_width_fractions"])
    measured = {"ink_bbox_pixels": list(bounds)}
    for name in ("upper", "lower"):
        y0, y1 = (top + round((bottom-top-1)*fraction)
                  for fraction in rule[f"{name}_roi_height_fractions"])
        _, columns = np.nonzero(mask[y0:y1+1, x0:x1+1])
        if not len(columns):
            return measured, [f"{name} endpoint region contains no ink"]
        measured[f"{name}_rightmost_ink_pixel"] = x0 + int(columns.max())
    margin = measured["lower_rightmost_ink_pixel"] - measured["upper_rightmost_ink_pixel"]
    measured["lower_rightward_margin_pixels"] = margin
    measured["lower_rightward_margin_em"] = margin / em_pixels
    minimum = rule["minimum_lower_rightward_margin_em"]
    return measured, ([] if margin / em_pixels >= minimum else
                      [f"lower rightward ink margin {margin/em_pixels:.6f} em is below {minimum:g}"])


def check_roi_elongated_components(mask: np.ndarray, rule: dict, em_pixels: int) -> tuple[dict, list[str]]:
    bounds = ink_bbox(mask)
    if bounds is None:
        return {}, ["glyph contains no ink"]
    left, top, right, bottom = bounds
    labels, _ = label(mask, structure=np.ones((3, 3), dtype=np.uint8))
    components = []
    for number, slices in enumerate(find_objects(labels), 1):
        if slices is None:
            continue
        ys, xs = np.nonzero(labels[slices] == number)
        points = np.column_stack((xs+slices[1].start, ys+slices[0].start))
        center = points.mean(axis=0)
        centered = points-center
        eigenvalues, eigenvectors = np.linalg.eigh(centered.T @ centered / len(points))
        projections = centered @ eigenvectors[:, 1]
        components.append({
            "centroid_width_fraction": float((center[0]-left)/(right-left-1)),
            "centroid_height_fraction": float((center[1]-top)/(bottom-top-1)),
            "principal_ink_span_em": float((projections.max()-projections.min()+1)/em_pixels),
            "principal_aspect": float(math.sqrt(eigenvalues[1]/max(eigenvalues[0], 1/12))),
            "ink_pixels": int(len(points)),
        })
    measured, errors = {"ink_bbox_pixels": list(bounds), "regions": []}, []
    for region in rule["regions"]:
        xf, yf = region["roi_width_fractions"], region["roi_height_fractions"]
        matches = [component for component in components
                   if xf[0] <= component["centroid_width_fraction"] <= xf[1]
                   and yf[0] <= component["centroid_height_fraction"] <= yf[1]]
        measured["regions"].append({"name": region["name"], "components": matches})
        if len(matches) != 1:
            errors.append(f"{region['name']}: expected one detached mark, found {len(matches)}")
            continue
        component = matches[0]
        if component["principal_ink_span_em"] < rule["minimum_principal_ink_span_em"]:
            errors.append(f"{region['name']}: diagonal ink span {component['principal_ink_span_em']:.6f} em "
                          f"is below {rule['minimum_principal_ink_span_em']}")
        if component["principal_aspect"] < rule["minimum_principal_aspect"]:
            errors.append(f"{region['name']}: mark is too round (principal aspect "
                          f"{component['principal_aspect']:.6f})")
    return measured, errors


CHECKS = {"two_horizontal_bars": check_two_bars,
          "lower_descender_count": check_lower_descenders,
          "ink_component_count": check_component_count,
          "roi_horizontal_bar_ratio": check_roi_bar_ratio,
          "roi_ink_presence": check_roi_ink_presence,
          "roi_rightward_endpoint_margin": check_roi_right_extent,
          "roi_elongated_components": check_roi_elongated_components}


def _weights(font: TTFont, specification: dict) -> tuple[list[float], list]:
    if "fvar" not in font:
        return [float(font["OS/2"].usWeightClass) if "OS/2" in font else 400.0], []
    axes = font["fvar"].axes
    weight_axis = next((axis for axis in axes if axis.axisTag == "wght"), None)
    if weight_axis is None:
        return [400.0], axes
    weights = {weight_axis.defaultValue}
    weights.update(instance.coordinates.get("wght", weight_axis.defaultValue)
                   for instance in font["fvar"].instances)
    weights.update(weight for weight in specification.get("variable_weights", [])
                   if weight_axis.minValue <= weight <= weight_axis.maxValue)
    return sorted(weights), axes


def _render(face: ImageFont.FreeTypeFont, codepoint: int, threshold: int) -> np.ndarray:
    character = chr(codepoint)
    left, top, right, bottom = face.getbbox(character, anchor="ls")
    pad = 32
    image = Image.new("L", (max(1, right-left) + 2*pad, max(1, bottom-top) + 2*pad))
    ImageDraw.Draw(image).text((pad-left, pad-top), character, font=face,
                              fill=255, anchor="ls", stroke_width=0)
    return np.asarray(image) >= threshold


def verify(font_path: Path, spec_path: Path = DEFAULT_SPEC) -> dict:
    """Return actual-raster invariant results for every required glyph/weight."""
    font_path, spec_path = Path(font_path), Path(spec_path)
    specification = json.loads(spec_path.read_text())
    font = TTFont(font_path)
    cmap = font.getBestCmap() or {}
    em_pixels = int(specification.get("raster_em_pixels", 2048))
    threshold = int(specification.get("ink_threshold", 128))
    weights, axes = _weights(font, specification)
    report = {"font": str(font_path), "font_sha256": hashlib.sha256(font_path.read_bytes()).hexdigest(),
              "specification": str(spec_path), "specification_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
              "rasterizer": "Pillow / FreeType; actual TTF or variable-font raster",
              "raster_em_pixels": em_pixels, "ink_threshold": threshold,
              "weights": weights, "passed": True, "checks": [], "errors": []}
    for weight in weights:
        face = ImageFont.truetype(str(font_path), em_pixels)
        if axes:
            face.set_variation_by_axes([weight if axis.axisTag == "wght" else axis.defaultValue
                                        for axis in axes])
        for glyph in specification["glyphs"]:
            codepoint = int(glyph["codepoint"].removeprefix("U+"), 16)
            check = {"codepoint": glyph["codepoint"], "weight": weight,
                     "criterion": glyph["criterion"], "source_criteria": glyph["source_criteria"]}
            if codepoint not in cmap:
                measured, errors = {}, ["codepoint is missing from the font cmap"]
            else:
                mask = _render(face, codepoint, threshold)
                measured, errors = CHECKS[glyph["criterion"]](mask, glyph["requirements"], em_pixels)
            check.update({"passed": not errors, "measured": measured, "errors": errors})
            report["checks"].append(check)
            report["errors"].extend(f"{glyph['codepoint']} weight {weight:g}: {error}" for error in errors)
    report["passed"] = not report["errors"]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = verify(args.font, args.spec)
    except (OSError, ValueError, KeyError) as error:
        report = {"font": str(args.font), "passed": False, "errors": [str(error)]}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "checks"}, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
