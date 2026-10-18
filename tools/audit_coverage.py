#!/usr/bin/env python3
"""Audit real font cmap/HEX coverage against a pinned Unicode development UCD.

This measures encoded character coverage, not shaping quality or glyph correctness.
No host Python unicodedata is used: First/Last ranges and all properties come from
the supplied snapshot. Diagnostic fonts must never satisfy character coverage.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable

from fontTools.ttLib import TTCollection, TTFont

EXCLUDED_CATEGORIES = {"Cc", "Cf", "Cn", "Co", "Cs", "Zl", "Zp"}
EXTENSIONS = {".ttf", ".otf", ".ttc", ".otc", ".hex"}
DIAGNOSTIC_WORDS = re.compile(r"(?:^|[-_. ])(?:unassigned|diagnostic|placeholder|tofu)(?:$|[-_. ])", re.I)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Character:
    name: str
    category: str


def read_unicode_data(path: Path) -> dict[int, Character]:
    """Expand inclusive UCD First/Last ranges (CJK, Hangul, Tangut, etc.)."""
    result: dict[int, Character] = {}
    pending = None
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        fields = line.split(";")
        if len(fields) < 3:
            raise ValueError(f"{path}:{line_number}: invalid UnicodeData record")
        cp, name, category = int(fields[0], 16), fields[1], fields[2]
        if name.endswith(", First>"):
            if pending:
                raise ValueError("nested UnicodeData First range")
            pending = (cp, name[:-8] + ">", category)
        elif name.endswith(", Last>"):
            if not pending or pending[1] != name[:-7] + ">" or pending[2] != category or cp < pending[0]:
                raise ValueError("unmatched UnicodeData Last range")
            first, range_name, range_category = pending
            for value in range(first, cp + 1):
                result[value] = Character(range_name, range_category)
            pending = None
        else:
            if pending:
                raise ValueError("unterminated UnicodeData First range")
            result[cp] = Character(name, category)
    if pending:
        raise ValueError("unterminated UnicodeData First range")
    return result


def read_property(path: Path, property_name: str | None = None) -> dict[int, str]:
    result: dict[int, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = [f.strip() for f in line.split(";")]
        if len(fields) < 2 or (property_name is not None and fields[1] != property_name):
            continue
        bounds = fields[0].split("..")
        for cp in range(int(bounds[0], 16), int(bounds[-1], 16) + 1):
            result[cp] = fields[1]
    return result


def codepoint(cp: int) -> str:
    return f"U+{cp:04X}"


def compact_ranges(values: Iterable[int]) -> list[str]:
    ordered = sorted(set(values))
    result: list[str] = []
    if not ordered:
        return result
    start = previous = ordered[0]
    for current in ordered[1:]:
        if current != previous + 1:
            result.append(f"{start:04X}" if start == previous else f"{start:04X}-{previous:04X}")
            start = current
        previous = current
    result.append(f"{start:04X}" if start == previous else f"{start:04X}-{previous:04X}")
    return result


def font_paths(roots: Iterable[Path], noto_only: bool = False) -> list[Path]:
    paths = set()
    for root in roots:
        candidates = root.rglob("*") if root.is_dir() else [root]
        for path in candidates:
            suffix = path.suffix.lower()
            if path.is_file() and (suffix in EXTENSIONS or path.name.lower().endswith(".hex.gz")):
                if not noto_only or path.name.lower().startswith("noto"):
                    paths.add(path)
    return sorted(paths)


def font_name(font: TTFont, name_id: int) -> str | None:
    return font["name"].getDebugName(name_id) if "name" in font else None


def font_coverage(path: Path, diagnostic: bool = False) -> tuple[set[int], dict]:
    """Read every Unicode cmap, including format 12 and all TTC faces.

    cmap entries mapping to glyph zero/.notdef are excluded. Zero HEX bitmaps are
    reported separately, because default-ignorables/space may legitimately be blank.
    """
    diagnostic = diagnostic or any(DIAGNOSTIC_WORDS.search(part) for part in path.parts)
    eligible = not diagnostic
    exclusion_reason = "diagnostic source" if diagnostic else None
    manifest_path = path.parent / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("coverage_eligible") is False:
            eligible = False
            exclusion_reason = "sibling manifest explicitly sets coverage_eligible=false"
    record = {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size,
              "diagnostic": diagnostic, "coverage_eligible": eligible,
              "exclusion_reason": exclusion_reason, "faces": [], "mapped_codepoint_count": 0}
    points: set[int] = set()
    if path.name.lower().endswith((".hex", ".hex.gz")):
        opener = gzip.open if path.name.lower().endswith(".gz") else open
        blank = set()
        with opener(path, "rt", encoding="ascii") as stream:
            for line_number, raw in enumerate(stream, 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    value, bitmap = line.split(":", 1)
                    cp = int(value, 16)
                    if not 0 <= cp <= 0x10FFFF or not bitmap or len(bitmap) % 2:
                        raise ValueError()
                    bitmap_bytes = bytes.fromhex(bitmap)
                except ValueError:
                    raise ValueError(f"{path}:{line_number}: invalid HEX record") from None
                points.add(cp)
                if not any(bitmap_bytes):
                    blank.add(cp)
        record["blank_codepoint_ranges"] = compact_ranges(blank)
        record["format"] = "hex"
    else:
        collection = None
        if path.suffix.lower() in {".ttc", ".otc"}:
            collection = TTCollection(path, lazy=True)
            fonts = collection.fonts
        else:
            fonts = [TTFont(path, lazy=True)]
        try:
            for index, font in enumerate(fonts):
                face_points = set()
                if "cmap" in font:
                    for table in font["cmap"].tables:
                        if table.isUnicode():
                            face_points.update(cp for cp, glyph in table.cmap.items()
                                               if glyph != ".notdef" and font.getGlyphID(glyph) != 0)
                points.update(face_points)
                record["faces"].append({"index": index, "family": font_name(font, 1),
                                         "subfamily": font_name(font, 2), "version": font_name(font, 5),
                                         "mapped_codepoint_count": len(face_points)})
        finally:
            for font in fonts:
                font.close()
            if collection:
                collection.close()
        record["format"] = path.suffix.lower().lstrip(".")
    record["mapped_codepoint_count"] = len(points)
    record["excluded_from_coverage"] = not eligible
    return (points if eligible else set()), record


def inventory(paths: Iterable[Path], diagnostics: set[Path] | None = None) -> tuple[set[int], list[dict]]:
    union: set[int] = set()
    records = []
    for path in paths:
        points, record = font_coverage(path, path.resolve() in (diagnostics or set()))
        union.update(points)
        records.append(record)
    return union, records


def grouped(target: set[int], covered: set[int], props: dict[int, str]) -> dict:
    total = Counter(props.get(cp, "Unknown") for cp in target)
    present = Counter(props.get(cp, "Unknown") for cp in target & covered)
    return {key: {"target": total[key], "covered": present[key], "missing": total[key] - present[key]}
            for key in sorted(total)}


def audit(ucd: Path, noto_paths: list[Path], output_paths: list[Path], diagnostics: set[Path] | None = None) -> dict:
    characters = read_unicode_data(ucd / "UnicodeData.txt")
    ages = read_property(ucd / "DerivedAge.txt")
    scripts = read_property(ucd / "Scripts.txt")
    blocks = read_property(ucd / "Blocks.txt")
    ignorables = read_property(ucd / "DerivedCoreProperties.txt", "Default_Ignorable_Code_Point")
    target = {cp for cp, char in characters.items() if char.category not in EXCLUDED_CATEGORIES}
    # Default ignorables include variation selectors. Their cmap entry does not
    # establish UVS/shaping support, but remains visible in this separate count.
    visible = target - ignorables.keys()
    noto, noto_records = inventory(noto_paths)
    sans = set()
    for path in noto_paths:
        if path.name.startswith("NotoSans"):
            points, _ = font_coverage(path)
            sans.update(points)
    output, output_records = inventory(output_paths, diagnostics)
    combined = output | sans
    missing_noto = target - noto
    missing_sans = target - sans
    missing_output = target - output
    new = {cp for cp in target if float(ages.get(cp, "0")) >= 16}
    snapshot_path = ucd / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text()) if snapshot_path.exists() else {}
    files = []
    for path in sorted(ucd.glob("*.txt")):
        header = path.read_text(encoding="utf-8").splitlines()[:8]
        files.append({"file": path.name, "sha256": sha256(path), "bytes": path.stat().st_size,
                      "header": header})
    def group_all(covered):
        return {"by_age": grouped(target, covered, ages), "by_script": grouped(target, covered, scripts),
                "by_block": grouped(target, covered, blocks)}
    gap_rows = [{"codepoint": codepoint(cp), "name": characters[cp].name,
                 "category": characters[cp].category, "age": ages.get(cp, "Unknown"),
                 "script": scripts.get(cp, "Unknown"), "block": blocks.get(cp, "No_Block"),
                 "noto_sans_covered": cp in sans, "any_installed_noto_covered": cp in noto,
                 "output_covered": cp in output, "default_ignorable": cp in ignorables}
                for cp in sorted(new & missing_noto)]
    return {
        "schema": 1, "scope": "Assigned graphic and spacing characters in the pinned Unicode development snapshot",
        "coverage_semantics": "Real Unicode cmap entries and HEX records; diagnostics and sources with coverage_eligible=false excluded. This is encoding coverage, not proof of correct glyph design, sans-serif style, shaping, mark attachment, or variation-sequence support.",
        "noto_baseline_scope": "Exactly the installed Noto fonts listed below; this does not claim to audit the latest Noto repositories worldwide.",
        "unicode_snapshot": snapshot, "ucd_files": files,
        "excluded_general_categories": sorted(EXCLUDED_CATEGORIES),
        "summary": {"assigned_records_expanded": len(characters), "graphic_target": len(target),
                    "visible_target_excluding_default_ignorables": len(visible),
                    "target_default_ignorables": len(target & ignorables.keys()),
                    "noto_sans_font_files": sum(p.name.startswith("NotoSans") for p in noto_paths),
                    "all_noto_font_files": len(noto_paths), "output_font_files": len(output_paths),
                    "noto_sans_covered": len(target & sans), "noto_sans_missing": len(missing_sans),
                    "any_installed_noto_covered": len(target & noto), "any_installed_noto_missing": len(missing_noto),
                    "output_covered": len(target & output), "output_missing": len(missing_output),
                    "output_plus_noto_sans_covered": len(target & combined),
                    "new_since_16_target": len(new), "new_since_16_missing_any_installed_noto": len(new & missing_noto),
                    "new_since_16_missing_any_installed_noto_now_covered": len(new & missing_noto & output)},
        "noto_sans": group_all(sans), "any_installed_noto": group_all(noto), "output": group_all(output),
        "new_missing_noto": gap_rows,
        "noto_sans_missing_ranges": compact_ranges(missing_sans),
        "any_installed_noto_missing_ranges": compact_ranges(missing_noto),
        "output_missing_ranges": compact_ranges(missing_output),
        "noto_fonts": noto_records, "output_fonts": output_records,
    }


def write_report(report: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "coverage.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    new_rows = report["new_missing_noto"]
    fields = ["codepoint", "name", "category", "age", "script", "block", "noto_sans_covered", "any_installed_noto_covered", "output_covered", "default_ignorable"]
    import csv
    with (output / "new-missing-noto.tsv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(new_rows)
    s = report["summary"]
    text = ["# Character coverage audit", "", report["scope"], "", report["coverage_semantics"], "",
            report["noto_baseline_scope"], "", f"UCD commit: `{report['unicode_snapshot'].get('commit', 'unrecorded')}`.", "",
            f"Graphic target: **{s['graphic_target']:,}** characters. Output: **{s['output_covered']:,}** covered; **{s['output_missing']:,}** missing.", "",
            f"Installed Noto Sans: {s['noto_sans_covered']:,} covered; all installed Noto: {s['any_installed_noto_covered']:,} covered.", "",
            f"Characters introduced since Unicode 16 missing from all installed Noto: **{s['new_since_16_missing_any_installed_noto']:,}**; covered in output: **{s['new_since_16_missing_any_installed_noto_now_covered']:,}**.", "",
            "## Coverage by Unicode age", "", "| Age | Target | Installed Noto Sans | Any installed Noto | Output | Missing output |", "|---|---:|---:|---:|---:|---:|"]
    for age, row in report["output"]["by_age"].items():
        text.append(f"| {age} | {row['target']:,} | {report['noto_sans']['by_age'][age]['covered']:,} | {report['any_installed_noto']['by_age'][age]['covered']:,} | {row['covered']:,} | {row['missing']:,} |")
    text += ["", "Full per-codepoint priorities are in `new-missing-noto.tsv`; exact source names, versions, hashes, and script/block summaries are in `coverage.json`.", "",
             "A development directory may contain different file version headers. The recorded per-file headers and hashes are authoritative; a 19.0 Blocks header alone does not establish any assigned Age=19.0 characters.", ""]
    (output / "README.md").write_text("\n".join(text))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ucd", type=Path, default=Path("reference/ucd-19-draft"))
    parser.add_argument("--noto-root", type=Path, action="append")
    parser.add_argument("--font", type=Path, action="append", help="Font/HEX file or recursively scanned directory; repeatable")
    parser.add_argument("--diagnostic", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, default=Path("coverage"))
    args = parser.parse_args()
    noto = font_paths(args.noto_root or [Path("/usr/share/fonts")], noto_only=True)
    fonts = font_paths(args.font or [Path("fonts")])
    report = audit(args.ucd, noto, fonts, {p.resolve() for p in args.diagnostic})
    write_report(report, args.output)
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
