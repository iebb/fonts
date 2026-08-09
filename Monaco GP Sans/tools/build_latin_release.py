#!/usr/bin/env python3
"""Build the Latin-only Monaco GP Sans catalog release.

The inputs are the hash-locked Monaco Vitesse 2.200 Filled and Outline variable
TTFs.  This script subsets only the approved Latin/Common repertoire, preserves
OpenType layout closure, renames the public families, and emits deterministic
TTF/WOFF2 deliverables plus a release manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont


SOURCE_SHA256 = {
    "filled": "f7a914b30f3c790217fc19b04c87f0b56f3719e4b133a5ef4fce5ec101a5ca01",
    "outline": "49a3bb9a3e3ec2760c7d125a5e108b509e63ad326c287c47594f79c5c5353ffe",
}
RELEASE_VERSION = "1.002"

# Exact repertoire audited from the frozen source.  These ranges retain all
# encoded Latin, Latin accents, combining marks, figures, punctuation, currency,
# and useful typographic/math symbols while excluding Greek, Cyrillic, Kana,
# and fullwidth script characters.
KEPT_RANGES = (
    (0x0000, 0x0000),
    (0x000D, 0x000D),
    (0x0020, 0x007E),
    (0x00A0, 0x017E),
    (0x0192, 0x0192),
    (0x0212, 0x0213),
    (0x0218, 0x021B),
    (0x0226, 0x0227),
    (0x0237, 0x0237),
    (0x02C6, 0x02C7),
    (0x02D8, 0x02DD),
    (0x0300, 0x0304),
    (0x0306, 0x0308),
    (0x030A, 0x030C),
    (0x0312, 0x0312),
    (0x0326, 0x0328),
    (0x1E80, 0x1E89),
    (0x1E9E, 0x1E9E),
    (0x1EF2, 0x1EF3),
    (0x2010, 0x2014),
    (0x2018, 0x201A),
    (0x201C, 0x201E),
    (0x2020, 0x2022),
    (0x2026, 0x2026),
    (0x2030, 0x2031),
    (0x2039, 0x203A),
    (0x203D, 0x203D),
    (0x2044, 0x2044),
    (0x2070, 0x2070),
    (0x2074, 0x2079),
    (0x2080, 0x2089),
    (0x20AC, 0x20AC),
    (0x20BD, 0x20BD),
    (0x2122, 0x2122),
    (0x2150, 0x215E),
    (0x2202, 0x2202),
    (0x2205, 0x2205),
    (0x220F, 0x220F),
    (0x2211, 0x2212),
    (0x2215, 0x2215),
    (0x2219, 0x221A),
    (0x221E, 0x221E),
    (0x222B, 0x222B),
    (0x2248, 0x2248),
    (0x2260, 0x2260),
    (0x2264, 0x2265),
    (0x25CA, 0x25CA),
)

FAMILIES = {
    "filled": {
        "family": "Monaco GP Sans",
        "ps_family": "MonacoGPSans",
        "filename": "MonacoGPSans[wght]",
    },
    "outline": {
        "family": "Monaco GP Sans Outline",
        "ps_family": "MonacoGPSansOutline",
        "filename": "MonacoGPSansOutline[wght]",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def allowed_codepoints(font: TTFont) -> set[int]:
    encoded = set(font.getBestCmap())
    allowed = {
        cp
        for start, end in KEPT_RANGES
        for cp in range(start, end + 1)
        if cp in encoded
    }
    return allowed


def subset_font(source: Path) -> TTFont:
    font = TTFont(source, recalcTimestamp=False)
    options = subset.Options()
    options.layout_features = ["*"]
    options.layout_scripts = ["*"]
    options.layout_closure = True
    options.glyph_names = True
    options.symbol_cmap = True
    options.legacy_cmap = True
    options.notdef_glyph = True
    options.notdef_outline = True
    options.recommended_glyphs = True
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]
    options.prune_unicode_ranges = True
    options.prune_codepage_ranges = True
    options.recalc_average_width = True
    options.recalc_bounds = True
    options.recalc_timestamp = False
    options.canonical_order = True

    worker = subset.Subsetter(options=options)
    worker.populate(unicodes=allowed_codepoints(font))
    worker.subset(font)
    return font


def rewrite_existing_names(font: TTFont, kind: str) -> None:
    config = FAMILIES[kind]
    replacements = {
        "Monaco Vitesse Filled": "Monaco GP Sans",
        "MonacoVitesse-Filled": "MonacoGPSans",
        "Monaco Vitesse Outline": "Monaco GP Sans Outline",
        "MonacoVitesse-Outline": "MonacoGPSansOutline",
    }
    for record in font["name"].names:
        try:
            value = record.toUnicode()
        except UnicodeDecodeError:
            continue
        for old, new in replacements.items():
            value = value.replace(old, new)
        if record.nameID == 0:
            value = value.replace(
                "Monaco Vitesse is a renamed modified version.",
                "Monaco GP Sans is a renamed, Latin-only modified version derived from Monaco Vitesse 2.200.",
            )
        if record.nameID == 5:
            value = f"Version {RELEASE_VERSION}"
        record.string = value.encode(record.getEncoding(), errors="replace")

    # Replace the public identity records with a minimal, internally consistent
    # set across Windows and Macintosh name platforms.
    identity_ids = {1, 2, 3, 4, 5, 6, 16, 17, 25}
    font["name"].names = [
        record for record in font["name"].names if record.nameID not in identity_ids
    ]
    family = config["family"]
    ps_family = config["ps_family"]
    values = {
        1: family,
        2: "Regular",
        3: f"{RELEASE_VERSION};IEBB;{ps_family}-Regular",
        4: f"{family} Regular",
        5: f"Version {RELEASE_VERSION}",
        6: f"{ps_family}-Regular",
        16: family,
        17: "Regular",
        25: ps_family,
    }
    for name_id, value in values.items():
        font["name"].setName(value, name_id, 3, 1, 0x0409)
        font["name"].setName(value, name_id, 1, 0, 0)

    font["head"].fontRevision = float(RELEASE_VERSION)
    font["OS/2"].achVendID = "IEBB"


def feature_tags(font: TTFont, table_tag: str) -> list[str]:
    if table_tag not in font:
        return []
    table = font[table_tag].table
    if not table.FeatureList:
        return []
    return sorted({record.FeatureTag for record in table.FeatureList.FeatureRecord})


def build_one(kind: str, source: Path, output_dir: Path) -> dict[str, object]:
    actual_hash = sha256(source)
    if actual_hash != SOURCE_SHA256[kind]:
        raise SystemExit(
            f"Refusing unpinned {kind} source: expected {SOURCE_SHA256[kind]}, got {actual_hash}"
        )

    font = subset_font(source)
    rewrite_existing_names(font, kind)
    base = output_dir / FAMILIES[kind]["filename"]
    ttf_path = base.with_suffix(".ttf")
    woff2_path = base.with_suffix(".woff2")
    font.flavor = None
    font.save(ttf_path, reorderTables=True)

    webfont = TTFont(ttf_path, recalcTimestamp=False)
    webfont.flavor = "woff2"
    webfont.save(woff2_path, reorderTables=True)

    release = TTFont(ttf_path, recalcTimestamp=False)
    cmap = release.getBestCmap()
    axis = release["fvar"].axes[0]
    return {
        "kind": kind,
        "family": FAMILIES[kind]["family"],
        "source_sha256": actual_hash,
        "ttf": {"file": ttf_path.name, "sha256": sha256(ttf_path), "bytes": ttf_path.stat().st_size},
        "woff2": {"file": woff2_path.name, "sha256": sha256(woff2_path), "bytes": woff2_path.stat().st_size},
        "encoded_codepoints": len(cmap),
        "glyphs": len(release.getGlyphOrder()),
        "axis": {
            "tag": axis.axisTag,
            "minimum": axis.minValue,
            "default": axis.defaultValue,
            "maximum": axis.maxValue,
        },
        "instances": [instance.coordinates["wght"] for instance in release["fvar"].instances],
        "gsub_features": feature_tags(release, "GSUB"),
        "gpos_features": feature_tags(release, "GPOS"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--filled-source", required=True, type=Path)
    parser.add_argument("--outline-source", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parents[1] / "fonts")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "family": "Monaco GP Sans",
        "version": RELEASE_VERSION,
        "scope": "Latin only",
        "fonts": [
            build_one("filled", args.filled_source.resolve(), args.output_dir),
            build_one("outline", args.outline_source.resolve(), args.output_dir),
        ],
    }
    manifest_path = args.output_dir / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
