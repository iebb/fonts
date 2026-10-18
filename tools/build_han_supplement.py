#!/usr/bin/env python3
"""Subset OFL Han source fonts to assigned graphic characters absent from Noto.

No drawings are synthesized. Source outlines, copyright and licensing metadata
are retained, and the modified faces receive new, unique family names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from fontTools import subset
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont

try:
    from tools.build_fonts import EXCLUDED_CATEGORIES, is_scalar, read_codepoints, read_ucd, unicode_ranges
except ModuleNotFoundError:  # Direct execution: python tools/build_han_supplement.py
    from build_fonts import EXCLUDED_CATEGORIES, is_scalar, read_codepoints, read_ucd, unicode_ranges


def _decode_points(values: list) -> set[int]:
    result: set[int] = set()
    for value in values:
        if isinstance(value, int):
            cp = value
        elif isinstance(value, str) and re.fullmatch(r"(?:U\+|0x)?[0-9A-Fa-f]{1,6}", value):
            cp = int(re.sub(r"^(?:U\+|0x)", "", value), 16)
        else:
            raise ValueError(f"invalid manifest codepoint: {value!r}")
        if not is_scalar(cp):
            raise ValueError(f"manifest codepoint is not a Unicode scalar: {value!r}")
        result.add(cp)
    return result


def read_baseline_codepoints(manifest_path: Path) -> set[int]:
    """Read measured baseline coverage, requiring an exact list or sidecar."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if isinstance(manifest.get("codepoints"), list):
        return _decode_points(manifest["codepoints"])
    if isinstance(manifest.get("css_codepoint_ranges"), list):
        points: set[int] = set()
        for value in manifest["css_codepoint_ranges"]:
            match = re.fullmatch(r"([0-9A-Fa-f]{1,6})(?:-([0-9A-Fa-f]{1,6}))?", value)
            if not match:
                raise ValueError(f"{manifest_path}: invalid baseline range {value!r}")
            start, end = int(match[1], 16), int(match[2] or match[1], 16)
            if start > end or end > 0x10FFFF or any(not is_scalar(cp) for cp in range(start, end + 1)):
                raise ValueError(f"{manifest_path}: invalid baseline range {value!r}")
            points.update(range(start, end + 1))
        if "css_codepoint_count" in manifest and len(points) != manifest["css_codepoint_count"]:
            raise ValueError(f"{manifest_path}: baseline range count does not match manifest")
        return points
    records = manifest.get("fonts", [])
    if records and all(isinstance(record.get("codepoints"), list) for record in records):
        return set().union(*(_decode_points(record["codepoints"]) for record in records))
    # Both builders use an adjacent, exact coverage sidecar for interoperation.
    sidecar = manifest_path.parent / "codepoints.txt"
    if sidecar.is_file():
        return read_codepoints(sidecar)
    raise ValueError(f"{manifest_path}: exact baseline codepoints are required")


def _recorded_outline(glyph_set, name: str) -> tuple:
    pen = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(pen)
    return tuple(pen.value)


def valid_source_codepoints(font: TTFont, categories: dict[int, str]) -> tuple[set[int], list[dict]]:
    """Reject missing-glyph IDs, empty visible glyphs and exact tofu copies."""
    cmap = font.getBestCmap() or {}
    glyph_set = font.getGlyphSet()
    notdef_name = font.getGlyphName(0)
    notdef_outline = _recorded_outline(glyph_set, notdef_name)
    # Cache by glyph name: many character maps deliberately share a real glyph.
    checked: dict[str, tuple[bool, bool]] = {}
    valid: set[int] = set()
    rejected: list[dict] = []
    for cp, name in sorted(cmap.items()):
        category = categories.get(cp)
        if not is_scalar(cp) or category is None or category in EXCLUDED_CATEGORIES:
            continue
        reason = None
        if name == ".notdef" or font.getGlyphID(name) == 0:
            reason = "missing_glyph_id"
        else:
            if name not in checked:
                outline = _recorded_outline(glyph_set, name)
                has_drawing = any(operator in {"lineTo", "qCurveTo", "curveTo"} for operator, _ in outline)
                matches_notdef = bool(notdef_outline) and outline == notdef_outline
                checked[name] = (has_drawing, matches_notdef)
            has_drawing, matches_notdef = checked[name]
            if matches_notdef:
                reason = "duplicate_missing_glyph_outline"
            elif not has_drawing and category != "Zs":
                reason = "empty_visible_glyph"
        if reason:
            rejected.append({"codepoint": f"U+{cp:04X}", "glyph": name, "reason": reason})
        else:
            valid.add(cp)
    return valid, rejected


def _rename_font(font: TTFont, family: str, label: str, version: str) -> str:
    desktop_family = f"{family} {label}"
    postscript_name = re.sub(r"[^A-Za-z0-9-]", "", desktop_family) + "-Regular"
    name_table = font["name"]
    # Preserve original copyright, designer, manufacturer and license records.
    # Replace localized family records too, to respect reserved source names.
    replaced_ids = {1, 2, 3, 4, 5, 6, 16, 17, 18, 21, 22}
    name_table.names = [record for record in name_table.names if record.nameID not in replaced_ids]
    replacements = {
        1: desktop_family, 2: "Regular",
        3: f"{postscript_name};Unicode-{version};Panorama-Gothic",
        4: f"{desktop_family} Regular", 5: f"Version 0.1; Unicode {version}",
        6: postscript_name,
    }
    for name_id, text in replacements.items():
        name_table.setName(text, name_id, 3, 1, 0x409)
        name_table.setName(text, name_id, 1, 0, 0)
    font["head"].created = font["head"].modified = 2082844800
    font.recalcTimestamp = False
    return postscript_name


def build_han_supplement(
    source_paths: list[Path], output: Path, ucd: Path, noto_manifest: Path,
    prior_fonts: list[Path] | None = None, family: str = "Panorama Gothic Han",
    version: str = "19.0.0-draft", woff: bool = True,
) -> dict:
    """Build disjoint modified OFL faces without replacing Noto coverage."""
    if not family.strip() or not re.sub(r"[^A-Za-z0-9-]", "", family):
        raise ValueError("family must contain ASCII letters or digits for font filenames")
    categories = read_ucd(ucd)
    baseline = read_baseline_codepoints(noto_manifest)
    covered = set(baseline)
    prior = []
    for path in prior_fonts or []:
        with TTFont(path, lazy=True) as font:
            points = set(font.getBestCmap() or {})
        covered.update(points)
        prior.append({"file": str(path), "codepoint_count": len(points), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    output.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    sources: list[dict] = []
    all_points: set[int] = set()
    for index, path in enumerate(source_paths, 1):
        source_record = {"file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        with TTFont(path, recalcBBoxes=True, recalcTimestamp=False) as font:
            valid, rejected = valid_source_codepoints(font, categories)
            points = sorted(valid - covered)
            source_record.update({
                "assigned_graphic_with_verified_outline_count": len(valid),
                "selected_codepoint_count": len(points), "rejected_glyphs": rejected,
                "copyright": sorted({record.toUnicode() for record in font["name"].names if record.nameID == 0}),
                "license": sorted({record.toUnicode() for record in font["name"].names if record.nameID == 13}),
            })
            sources.append(source_record)
            if not points:
                continue
            match = re.search(r"P([0-9]+)", path.stem, re.IGNORECASE)
            label = f"P{match[1]}" if match else f"Source{index}"
            # A caller can supply multiple sources with similarly named stems.
            if any(record["label"] == label for record in records):
                label += f"-{index}"
            options = subset.Options()
            options.name_IDs = ["*"]
            options.name_languages = ["*"]
            options.name_legacy = True
            options.glyph_names = True
            options.layout_features = ["*"]
            options.recalc_timestamp = False
            options.recalc_bounds = True
            options.notdef_glyph = True
            options.notdef_outline = True
            subsetter = subset.Subsetter(options=options)
            subsetter.populate(unicodes=points)
            subsetter.subset(font)
            postscript_name = _rename_font(font, family, label, version)
            actual = set(font.getBestCmap() or {})
            if actual != set(points):
                raise ValueError(f"{path}: subset cmap differs from selected codepoints")
            ttf_path = output / f"{postscript_name}.ttf"
            font.flavor = None
            font.save(ttf_path)
            record = {
                "file": ttf_path.name, "label": label,
                "desktop_family": f"{family} {label}",
                "license": "OFL-1.1", "source": str(path),
                "codepoint_count": len(points),
                "codepoints": [f"U+{cp:04X}" for cp in points],
                "first": f"U+{points[0]:04X}", "last": f"U+{points[-1]:04X}",
                "unicode_range": unicode_ranges(points),
                "sha256": hashlib.sha256(ttf_path.read_bytes()).hexdigest(),
            }
            if woff:
                woff_path = output / f"{postscript_name}.woff"
                font.flavor = "woff"
                font.save(woff_path)
                record["woff"] = woff_path.name
                record["woff_sha256"] = hashlib.sha256(woff_path.read_bytes()).hexdigest()
            records.append(record)
            all_points.update(points)
            covered.update(points)
    css_family = family.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    css = "/* OFL sources; exact disjoint cmap ranges measured after subsetting. */\n"
    for record in records:
        urls = ([f'url("{record["woff"]}") format("woff")'] if "woff" in record else [])
        urls.append(f'url("{record["file"]}") format("truetype")')
        css += (
            '@font-face {\n'
            f'  font-family: "{css_family}";\n  src: {", ".join(urls)};\n'
            '  font-weight: 400;\n  font-style: normal;\n  font-display: swap;\n'
            f'  unicode-range: {record["unicode_range"]};\n'
            '}\n'
        )
    (output / "fonts.css").write_text(css, encoding="utf-8")
    (output / "codepoints.txt").write_text("".join(f"U+{cp:04X}\n" for cp in sorted(all_points)), encoding="utf-8")
    ucd_file = ucd / "UnicodeData.txt" if ucd.is_dir() else ucd
    manifest = {
        "schema_version": 1, "family": family, "unicode_version": version,
        "license": "OFL-1.1", "outline_style": "original smooth source outlines",
        "codepoint_count": len(all_points), "fonts": records, "sources": sources,
        "selection": {
            "ucd": str(ucd_file), "ucd_sha256": hashlib.sha256(ucd_file.read_bytes()).hexdigest(),
            "noto_manifest": str(noto_manifest), "baseline_codepoint_count": len(baseline),
            "noto_manifest_sha256": hashlib.sha256(noto_manifest.read_bytes()).hexdigest(),
            "prior_fonts": prior,
            "excluded_categories": sorted(EXCLUDED_CATEGORIES),
        },
        "notes": "Modified OFL fonts renamed from their sources. Outlines and source copyright/license metadata retained. Coverage requires an actual drawing except assigned space separators.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", dest="source_paths", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, default=Path("fonts/han"))
    parser.add_argument("--ucd", type=Path, required=True)
    parser.add_argument("--noto-manifest", type=Path, default=Path("fonts/noto/manifest.json"))
    parser.add_argument("--prior-fonts", type=Path, nargs="*", default=[])
    parser.add_argument("--family", default="Panorama Gothic Han")
    parser.add_argument("--version", default="19.0.0-draft")
    parser.add_argument("--no-woff", dest="woff", action="store_false")
    args = parser.parse_args()
    try:
        manifest = build_han_supplement(**vars(args))
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps({"fonts": len(manifest["fonts"]), "codepoints": manifest["codepoint_count"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
