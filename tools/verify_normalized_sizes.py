#!/usr/bin/env python3
"""Check the expected compiled Small Seal glyphs' size, alignment and advances.

Regular uses a 738-unit centerline envelope and a 30-unit pen: 768 units of
ink. Named variable instances use the same envelope and their specified pen
width. BoundsPen measures curve extrema, rather than TrueType control boxes.
This is a size check; it does not certify character identity or stroke order.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Iterable

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont


DEFAULT_CODEPOINTS = tuple(range(0x3D000, 0x3D040))
# Kept for consumers of the original 64-character verifier.
CODEPOINTS = DEFAULT_CODEPOINTS
CENTERLINE_EXTENT = 738.0
CENTER = (512.0, 320.0)
ADVANCE = 1024
SIZE_TOLERANCE = 2.0
CENTER_TOLERANCE = 1.5
NAMED_WEIGHTS = (300, 400, 500, 600, 700)


def pen_width(weight: float) -> float:
    """Independent specification of the thinner weight mapping."""
    if not 300 <= weight <= 700:
        raise ValueError(f"Unsupported weight {weight:g}; expected 300 through 700")
    return 30.0 + (weight - 400.0) * 0.065


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_codepoint(value: str | int) -> int:
    codepoint = int(value.removeprefix("U+"), 16) if isinstance(value, str) else value
    if isinstance(codepoint, bool) or not isinstance(codepoint, int) or not 0 <= codepoint <= 0x10FFFF:
        raise ValueError(f"Invalid Unicode codepoint: {value!r}")
    return codepoint


def expected_repertoire(values: Iterable[str | int]) -> tuple[int, ...]:
    codepoints = tuple(parse_codepoint(value) for value in values)
    if not codepoints or len(set(codepoints)) != len(codepoints):
        raise ValueError("Expected repertoire must be nonempty and contain no duplicate codepoints")
    return tuple(sorted(codepoints))


def manifest_expectations(font_path: Path, font_sha256: str,
                          codepoints: Iterable[int] | None = None) -> tuple[dict, dict]:
    """Use metadata only when its file hash identifies this exact font."""
    path = font_path.parent / "manifest.json"
    report = {"checked": False, "aspect_ratio_checked": False}
    if not path.exists():
        report["reason"] = "No adjacent manifest; compiled size checks still apply."
        return report, {}
    manifest = json.loads(path.read_text())
    if not any(item.get("name") == font_path.name and item.get("sha256") == font_sha256
               for item in manifest.get("files", [])):
        report["reason"] = "Adjacent manifest does not identify this font hash."
        return report, {}
    report.update({"checked": True, "path": str(path.resolve()), "sha256": digest(path)})
    errors, expected = [], {}
    records = manifest.get("glyphs", manifest.get("sources", []))
    declared = expected_repertoire(item["codepoint"] for item in records)
    required = expected_repertoire(codepoints) if codepoints is not None else declared
    report["codepoints"] = [f"U+{cp:05X}" for cp in declared]
    if manifest.get("glyph_count") != len(declared):
        errors.append("Manifest glyph_count differs from its declared repertoire")
    if set(declared) != set(required):
        errors.append("Manifest repertoire differs from the independently expected repertoire")
    for item in records:
        cp = item.get("codepoint")
        norm = item.get("normalization") or {}
        matrix = norm.get("matrix_font_units", [])
        bounds = norm.get("original_centerline_bounds_font_units", [])
        if len(matrix) != 6 or len(bounds) != 4:
            errors.append(f"{cp}: missing normalization matrix or original bounds")
            continue
        a, b, c, d, tx, ty = matrix
        valid = (all(math.isfinite(float(v)) for v in [*matrix, *bounds])
                 and a > 0 and abs(a-d) <= 1e-9 and abs(b) <= 1e-9 and abs(c) <= 1e-9
                 and norm.get("preserve_aspect_ratio") is True
                 and norm.get("pen_width_scaled") is False
                 and norm.get("target_centerline_extent") == CENTERLINE_EXTENT)
        width, height = (bounds[2]-bounds[0])*a, (bounds[3]-bounds[1])*d
        center = ((bounds[0]+bounds[2])*a/2+tx, (bounds[1]+bounds[3])*d/2+ty)
        valid &= (width >= 0 and height >= 0
                  and abs(max(width, height)-CENTERLINE_EXTENT) <= 1e-6
                  and all(abs(actual-wanted) <= 1e-6 for actual, wanted in zip(center, CENTER)))
        if not valid:
            errors.append(f"{cp}: normalization does not preserve aspect/envelope/center/pen")
        else:
            expected[cp] = (width, height)
    missing = [f"U+{cp:05X}" for cp in required if f"U+{cp:05X}" not in expected]
    report.update({"pass": not errors and not missing, "errors": errors,
                   "missing_codepoints": missing, "aspect_ratio_checked": not missing,
                   "method": "Compare compiled width and height with original source bounds "
                             "under the manifest's verified uniform affine matrix."})
    return report, expected


def inspect_instance(font: TTFont, weight: float, labels: list[str], expected: dict,
                     codepoints: Iterable[int] = DEFAULT_CODEPOINTS) -> dict:
    width = pen_width(weight)
    wanted_extent = CENTERLINE_EXTENT + width
    glyph_set, cmap = font.getGlyphSet(), font.getBestCmap() or {}
    records = []
    for cp in codepoints:
        codepoint = f"U+{cp:05X}"
        name = cmap.get(cp)
        record = {"codepoint": codepoint, "glyph": name, "pass": False}
        if name is None:
            record["errors"] = ["Missing cmap entry"]
            records.append(record)
            continue
        pen = BoundsPen(glyph_set)
        glyph_set[name].draw(pen)
        advance = font["hmtx"].metrics[name][0]
        record["advance"] = advance
        if pen.bounds is None:
            record["errors"] = ["Empty actual glyph outline"]
            records.append(record)
            continue
        x_min, y_min, x_max, y_max = pen.bounds
        ink_size = (x_max-x_min, y_max-y_min)
        center = ((x_min+x_max)/2, (y_min+y_max)/2)
        extent_error = abs(max(ink_size)-wanted_extent)
        center_error = tuple(abs(actual-wanted) for actual, wanted in zip(center, CENTER))
        errors = []
        if extent_error > SIZE_TOLERANCE:
            errors.append("Longest ink dimension outside size tolerance")
        if max(center_error) > CENTER_TOLERANCE:
            errors.append("Ink bounds center outside alignment tolerance")
        if advance != ADVANCE:
            errors.append("Advance must equal 1024")
        if codepoint in expected:
            wanted_size = [value+width for value in expected[codepoint]]
            size_error = [abs(actual-wanted) for actual, wanted in zip(ink_size, wanted_size)]
            record.update({"source_expected_ink_size": wanted_size,
                           "source_aspect_extent_error": size_error})
            if max(size_error) > SIZE_TOLERANCE:
                errors.append("Compiled proportions differ from normalized source bounds")
        record.update({"bounds": list(pen.bounds), "ink_size": list(ink_size),
                       "longest_dimension": max(ink_size), "extent_error": extent_error,
                       "center": list(center), "center_error": list(center_error),
                       "errors": errors, "pass": not errors})
        records.append(record)
    return {"weight": weight, "labels": labels, "expected_pen_width": width,
            "expected_longest_dimension": wanted_extent,
            "pass": all(record["pass"] for record in records), "glyphs": records}


def verify(font_path: Path, expected_codepoints: Iterable[str | int] | None = None,
           registry_path: Path | None = None) -> dict:
    font_sha256 = digest(font_path)
    required = expected_repertoire(expected_codepoints) if expected_codepoints is not None else None
    repertoire = {"source": "explicit" if required is not None else "64-character fallback"}
    if registry_path is not None:
        registry = json.loads(registry_path.read_text())
        if registry.get("schema_version") != 1:
            raise ValueError("Expected acceptance registry schema_version 1")
        registered = expected_repertoire(item["codepoint"] for item in registry["glyphs"])
        if required is not None and required != registered:
            raise ValueError("Explicit repertoire differs from the acceptance registry")
        required = registered
        repertoire.update({"source": "frozen acceptance registry", "path": str(registry_path.resolve()),
                           "sha256": digest(registry_path)})
    manifest, expected = manifest_expectations(font_path, font_sha256, required)
    if required is None and manifest["checked"]:
        required = expected_repertoire(manifest["codepoints"])
        repertoire["source"] = "hash-matched font manifest"
    required = required if required is not None else DEFAULT_CODEPOINTS
    repertoire.update({"glyph_count": len(required), "codepoints": [f"U+{cp:05X}" for cp in required]})
    report = {"font": str(font_path.resolve()), "font_sha256": font_sha256,
              "specification": {"centerline_extent": CENTERLINE_EXTENT,
                                "regular_ink_extent": 768, "center": list(CENTER),
                                "advance": ADVANCE, "size_tolerance": SIZE_TOLERANCE,
                                "center_tolerance": CENTER_TOLERANCE},
              "repertoire": repertoire,
              "manifest_source_comparison": manifest, "errors": [], "instances": [],
              "limitations": ["Bounds validate the shared envelope, not every interior stroke's width.",
                              "Source aspect comparison requires an adjacent hash-matched manifest.",
                              "Character identity, topology and historical order require separate checks."]}
    with TTFont(font_path) as font:
        unexpected = sorted(set(font.getBestCmap() or {}) - set(required))
        if unexpected:
            report["errors"].append("Font cmap contains codepoints outside the expected repertoire: "
                                    + ", ".join(f"U+{cp:05X}" for cp in unexpected))
        if font["head"].unitsPerEm != ADVANCE:
            report["errors"].append("unitsPerEm must equal 1024")
        if "fvar" not in font:
            weight = float(font["OS/2"].usWeightClass)
            report["instances"].append(inspect_instance(font, weight, ["static"], expected, required))
        else:
            axes = {axis.axisTag: axis for axis in font["fvar"].axes}
            if "wght" not in axes:
                raise ValueError("Variable font lacks a weight axis")
            axis = axes["wght"]
            if (axis.minValue, axis.defaultValue, axis.maxValue) != (300, 400, 700):
                report["errors"].append("Weight axis must be 300..700 with default 400")
            locations = {float(axis.defaultValue): ["default"]}
            named_weights = set()
            for instance in font["fvar"].instances:
                weight = float(instance.coordinates.get("wght", axis.defaultValue))
                named_weights.add(weight)
                name = font["name"].getDebugName(instance.subfamilyNameID) or "unnamed"
                locations.setdefault(weight, []).append(name)
            missing = sorted(set(NAMED_WEIGHTS)-named_weights)
            if missing:
                report["errors"].append(f"Missing named weights: {missing}")
            for weight, labels in sorted(locations.items()):
                # Compile/reopen to include the integer rounding present in the shipped TTF.
                instance = instantiateVariableFont(font, {"wght": weight}, inplace=False)
                instance.recalcTimestamp = False
                instance.flavor = None
                buffer = io.BytesIO()
                instance.save(buffer)
                instance.close()
                data = buffer.getvalue()
                with TTFont(io.BytesIO(data)) as compiled:
                    result = inspect_instance(compiled, weight, labels, expected, required)
                result["compiled_instance_sha256"] = hashlib.sha256(data).hexdigest()
                report["instances"].append(result)
    report["pass"] = (not report["errors"] and manifest.get("pass", True)
                      and all(item["pass"] for item in report["instances"]))
    report["glyph_checks"] = sum(len(item["glyphs"]) for item in report["instances"])
    report["failed_glyph_checks"] = sum(not glyph["pass"] for item in report["instances"]
                                        for glyph in item["glyphs"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--registry", type=Path,
                        help="Frozen acceptance registry supplying the expected repertoire")
    args = parser.parse_args()
    try:
        report = verify(args.font, registry_path=args.registry)
    except Exception as error:
        report = {"font": str(args.font.resolve()), "pass": False,
                  "error": f"{type(error).__name__}: {error}"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{'PASS' if report['pass'] else 'FAIL'}: normalized sizes; "
          f"{report.get('glyph_checks', 0)} actual glyph checks; report {args.output}")
    raise SystemExit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
