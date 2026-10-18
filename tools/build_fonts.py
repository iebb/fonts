#!/usr/bin/env python3
"""Build honestly scoped, installable outline supplements from GNU Unifont hex.

These are pixel-derived TrueType outlines. This conversion preserves the source
glyph drawings; it does not turn them into newly designed, smoothly curved sans
glyphs. The generated fonts provide character coverage, not complex-text shaping.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


UNITS_PER_EM = 1024
PIXEL_SIZE = 64
BASELINE = 13
EXCLUDED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
LICENSE = (
    "GNU General Public License version 2 or later, with the GNU Unifont font "
    "embedding exception. See the source distribution's COPYING file for the "
    "complete license and exception."
)


def is_scalar(codepoint: int) -> bool:
    return 0 <= codepoint <= 0x10FFFF and not 0xD800 <= codepoint <= 0xDFFF


def parse_hex(paths: list[Path]) -> dict[int, str]:
    """Read 8×16 and 16×16 hex glyphs; reject ambiguous or corrupt sources."""
    glyphs: dict[int, str] = {}
    for path in paths:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8-sig") as source:
            for line_number, raw in enumerate(source, 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                context = f"{path}:{line_number}"
                match = re.fullmatch(r"([0-9A-Fa-f]{4,6}):([0-9A-Fa-f]+)", line)
                if not match:
                    raise ValueError(f"{context}: invalid Unifont hex record")
                codepoint, bitmap = int(match[1], 16), match[2].upper()
                if not is_scalar(codepoint):
                    raise ValueError(f"{context}: U+{codepoint:04X} is not a Unicode scalar")
                if len(bitmap) not in (32, 64):
                    raise ValueError(f"{context}: expected 32 or 64 bitmap hex digits")
                if codepoint in glyphs and glyphs[codepoint] != bitmap:
                    raise ValueError(f"{context}: conflicting glyph for U+{codepoint:04X}")
                glyphs[codepoint] = bitmap
    return glyphs


def bitmap_rectangles(data: str) -> list[tuple[int, int, int, int]]:
    """Return pixel rectangles, joining identical horizontal runs vertically."""
    if len(data) not in (32, 64) or not re.fullmatch(r"[0-9a-fA-F]+", data):
        raise ValueError("bitmap must contain 32 or 64 hexadecimal digits")
    width = len(data) // 4
    row_digits = width // 4
    rectangles: list[tuple[int, int, int, int]] = []
    active: dict[tuple[int, int], int] = {}
    for y in range(16):
        bits = f"{int(data[y * row_digits:(y + 1) * row_digits], 16):0{width}b}"
        current: dict[tuple[int, int], int] = {}
        for match in re.finditer("1+", bits):
            run = (match.start(), match.end() - match.start())
            if run in active:
                index = active[run]
                x, top, run_width, height = rectangles[index]
                rectangles[index] = (x, top, run_width, height + 1)
            else:
                index = len(rectangles)
                rectangles.append((run[0], y, run[1], 1))
            current[run] = index
        active = current
    return rectangles


def read_ucd(path: Path) -> dict[int, str]:
    """Read UnicodeData.txt, expanding its First/Last interval records."""
    if path.is_dir():
        path = path / "UnicodeData.txt"
    categories: dict[int, str] = {}
    first: tuple[int, str, str] | None = None
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw or raw.startswith("#"):
            continue
        fields = raw.split(";")
        if len(fields) < 3:
            raise ValueError(f"{path}:{line_number}: invalid UnicodeData record")
        codepoint, name, category = int(fields[0], 16), fields[1], fields[2]
        if name.endswith(", First>"):
            if first is not None:
                raise ValueError(f"{path}:{line_number}: nested UnicodeData interval")
            first = (codepoint, category, name[:-8])
        elif name.endswith(", Last>"):
            if first is None or first[1] != category or first[2] != name[:-7] or codepoint < first[0]:
                raise ValueError(f"{path}:{line_number}: invalid UnicodeData interval")
            categories.update(dict.fromkeys(range(first[0], codepoint + 1), category))
            first = None
        else:
            if first is not None:
                raise ValueError(f"{path}:{line_number}: unclosed UnicodeData interval")
            categories[codepoint] = category
    if first is not None:
        raise ValueError(f"{path}: unclosed UnicodeData interval")
    return categories


def read_codepoints(path: Path) -> set[int]:
    """Read hex values or inclusive ranges, with optional U+ and # comments."""
    result: set[int] = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"(?:U\+)?([0-9A-Fa-f]{1,6})(?:\.\.(?:U\+)?([0-9A-Fa-f]{1,6}))?", line)
        if not match:
            raise ValueError(f"{path}:{line_number}: invalid code point or range")
        start = int(match[1], 16)
        end = int(match[2], 16) if match[2] else start
        if start > end or end > 0x10FFFF:
            raise ValueError(f"{path}:{line_number}: invalid Unicode range")
        values = range(start, end + 1)
        if any(not is_scalar(cp) for cp in values):
            raise ValueError(f"{path}:{line_number}: range includes a non-scalar")
        result.update(values)
    return result


def unicode_ranges(codepoints: list[int]) -> str:
    ranges: list[str] = []
    start = previous = codepoints[0]
    for cp in codepoints[1:] + [0x110001]:
        if cp == previous + 1:
            previous = cp
            continue
        ranges.append(f"U+{start:X}" if start == previous else f"U+{start:X}-{previous:X}")
        start = previous = cp
    return ", ".join(ranges)


def glyph_name(codepoint: int) -> str:
    return f"uni{codepoint:04X}" if codepoint <= 0xFFFF else f"u{codepoint:05X}"


def make_glyph(bitmap: str, x_offset: int = 0):
    pen = TTGlyphPen(None)
    for x, y, width, height in bitmap_rectangles(bitmap):
        left, right = x * PIXEL_SIZE + x_offset, (x + width) * PIXEL_SIZE + x_offset
        bottom, top = (BASELINE - y - height) * PIXEL_SIZE, (BASELINE - y) * PIXEL_SIZE
        pen.moveTo((left, bottom))
        pen.lineTo((left, top))
        pen.lineTo((right, top))
        pen.lineTo((right, bottom))
        pen.closePath()
    return pen.glyph()


def _make_font(glyphs: dict[int, str], codepoints: list[int], categories: dict[int, str],
               family: str, version: str, label: str, output: Path) -> dict:
    names = [".notdef"] + [glyph_name(cp) for cp in codepoints]
    font = FontBuilder(UNITS_PER_EM, isTTF=True)
    font.setupGlyphOrder(names)
    font.setupCharacterMap({cp: glyph_name(cp) for cp in codepoints}, allowFallback=True)
    # A normal missing-glyph box exists only at GID 0 and is never cmap coverage.
    notdef_bitmap = "007E42424242424242424242427E0000"
    outlines = {".notdef": make_glyph(notdef_bitmap)}
    metrics = {".notdef": (512, 0)}
    for cp in codepoints:
        name, bitmap = glyph_name(cp), glyphs[cp]
        advance = (len(bitmap) // 4) * PIXEL_SIZE
        x_offset = 0
        if categories.get(cp) in {"Mn", "Me"}:
            # Unifont bitmaps draw marks in a complete cell. Back up by one
            # source cell so a zero-advance mark can overlay its preceding cell.
            # This is basic cell positioning, not script-specific GPOS shaping.
            x_offset = -advance
            advance = 0
        outlines[name] = make_glyph(bitmap, x_offset)
        # LSB must match xMin to avoid renderer phantom-point shifts.
        rectangles = bitmap_rectangles(bitmap)
        lsb = min((rect[0] for rect in rectangles), default=0) * PIXEL_SIZE + x_offset if rectangles else 0
        metrics[name] = (advance, lsb)
    font.setupGlyf(outlines)
    font.setupHorizontalMetrics(metrics)
    font.setupHorizontalHeader(ascent=832, descent=-192, lineGap=0)
    safe_version = re.sub(r"[^0-9.]", "", version).strip(".") or "0.1"
    postscript_name = re.sub(r"[^A-Za-z0-9-]", "", family + label)
    font.setupNameTable({
        # Each shard needs a distinct desktop family/style pair. The CSS below
        # aliases their disjoint cmap ranges into the requested common family.
        "familyName": f"{family} {label}",
        "styleName": "Regular",
        "uniqueFontIdentifier": f"{family};{version};{label}",
        "fullName": f"{family} {label}",
        "psName": postscript_name,
        "version": f"Version {safe_version}; Unicode {version}",
        "copyright": "Derived from GNU Unifont. Original glyph copyrights are retained in the source distribution.",
        "description": "Pixel-derived outline supplement. Monochrome, unhinted; complex-script shaping is not implemented.",
        "licenseDescription": LICENSE,
        "licenseInfoURL": "https://unifoundry.com/LICENSE.txt",
    })
    font.setupOS2(
        sTypoAscender=832, sTypoDescender=-192, sTypoLineGap=0,
        usWinAscent=832, usWinDescent=192,
        usWeightClass=400, usWidthClass=5, fsType=0,
        fsSelection=0x40, sFamilyClass=0x0809,
    )
    font.setupPost(isFixedPitch=0)
    font.setupMaxp()
    # Fixed timestamps make a build repeatable from the same inputs.
    font.font["head"].created = font.font["head"].modified = 2082844800
    font.font.recalcTimestamp = False
    ttf_path = output / f"{postscript_name}.ttf"
    font.save(ttf_path)
    font.font.flavor = "woff"
    woff_path = output / f"{postscript_name}.woff"
    font.save(woff_path)
    return {
        "file": ttf_path.name, "woff": woff_path.name,
        "desktop_family": f"{family} {label}",
        "codepoint_count": len(codepoints),
        "first": f"U+{codepoints[0]:04X}", "last": f"U+{codepoints[-1]:04X}",
        "unicode_range": unicode_ranges(codepoints),
        "sha256": hashlib.sha256(ttf_path.read_bytes()).hexdigest(),
        "woff_sha256": hashlib.sha256(woff_path.read_bytes()).hexdigest(),
    }


def build_fonts(hex_paths: list[Path], output: Path, ucd: Path | None = None,
                only_codepoints: Path | None = None, max_glyphs: int = 50000,
                family: str = "Panorama Gothic Supplement", version: str = "19.0.0-draft") -> dict:
    """Build selected glyphs and write a source/coverage manifest alongside them."""
    if not 1 <= max_glyphs <= 65534:
        raise ValueError("max_glyphs must be between 1 and 65534 (plus .notdef)")
    if not family.strip() or not re.sub(r"[^A-Za-z0-9-]", "", family):
        raise ValueError("family must contain ASCII letters or digits for font filenames")
    glyphs = parse_hex(hex_paths)
    categories = read_ucd(ucd) if ucd else {}
    selected = set(glyphs)
    if ucd:
        selected &= {cp for cp, category in categories.items() if category not in EXCLUDED_CATEGORIES and is_scalar(cp)}
    requested = read_codepoints(only_codepoints) if only_codepoints else None
    if requested is not None:
        selected &= requested
    by_plane: dict[int, list[int]] = defaultdict(list)
    for cp in sorted(selected):
        by_plane[cp >> 16].append(cp)
    output.mkdir(parents=True, exist_ok=True)
    fonts: list[dict] = []
    for plane, codepoints in sorted(by_plane.items()):
        chunks = [codepoints[start:start + max_glyphs] for start in range(0, len(codepoints), max_glyphs)]
        for index, chunk in enumerate(chunks, 1):
            label = f"P{plane:X}" + (f"-{index:02d}" if len(chunks) > 1 else "")
            record = _make_font(glyphs, chunk, categories, family, version, label, output)
            record["plane"] = plane
            fonts.append(record)
    css_family = family.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    css = "/* Generated from the exact cmap of each font. */\n" + "\n".join(
        '@font-face {\n'
        f'  font-family: "{css_family}";\n'
        f'  src: url("{record["woff"]}") format("woff"), url("{record["file"]}") format("truetype");\n'
        '  font-weight: 400;\n  font-style: normal;\n  font-display: swap;\n'
        f'  unicode-range: {record["unicode_range"]};\n'
        '}\n' for record in fonts
    )
    (output / "fonts.css").write_text(css, encoding="utf-8")
    (output / "codepoints.txt").write_text("".join(f"U+{cp:04X}\n" for cp in sorted(selected)), encoding="utf-8")
    manifest = {
        "schema_version": 1, "family": family, "unicode_version": version,
        "source_format": "GNU Unifont 8x16/16x16 hex",
        "outline_style": "pixel-derived rectangular outlines",
        "shaping": "unshaped; zero-advance Mn/Me only when UnicodeData is supplied",
        "license": LICENSE, "codepoint_count": len(selected), "fonts": fonts,
        "selection": {
            "ucd": str(ucd) if ucd else None,
            "only_codepoints": str(only_codepoints) if only_codepoints else None,
            "requested_count": len(requested) if requested is not None else None,
            "requested_without_source": [f"U+{cp:04X}" for cp in sorted((requested or set()) - set(glyphs))],
            "source_codepoint_count": len(glyphs),
            "excluded_source_codepoint_count": len(glyphs) - len(selected),
        },
        "sources": [{"file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in hex_paths],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hex", dest="hex_paths", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, default=Path("fonts/supplement"))
    parser.add_argument("--ucd", type=Path, help="UnicodeData.txt or its containing directory")
    parser.add_argument("--only-codepoints", type=Path, help="Hex code points/ranges to select")
    parser.add_argument("--max-glyphs", type=int, default=50000)
    parser.add_argument("--family", default="Panorama Gothic Supplement")
    parser.add_argument("--version", default="19.0.0-draft")
    args = parser.parse_args()
    try:
        manifest = build_fonts(**vars(args))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"fonts": len(manifest["fonts"]), "codepoints": manifest["codepoint_count"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
