#!/usr/bin/env python3
"""Validate Monaco GP Sans release files and optional frozen-source parity."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont


WEIGHTS = tuple(range(100, 901, 100))
OUTLINE_WEIGHTS = tuple(range(100, 901, 50))
FORBIDDEN_RANGES = (
    (0x0370, 0x03FF, "Greek"),
    (0x1F00, 0x1FFF, "Greek Extended"),
    (0x0400, 0x052F, "Cyrillic"),
    (0x1C80, 0x1C8F, "Cyrillic Extended C"),
    (0x2DE0, 0x2DFF, "Cyrillic Extended A"),
    (0xA640, 0xA69F, "Cyrillic Extended B"),
    (0x3040, 0x30FF, "Hiragana or Katakana"),
    (0x31F0, 0x31FF, "Katakana extensions"),
    (0xFF00, 0xFFEF, "Halfwidth or fullwidth forms"),
)
EXPECTED_GSUB = {"ss01", "ss03", "ss06", "ss07", "ss08", "ss09", "tnum"}
EXPECTED_GPOS = {"kern", "mark", "mkmk"}
RELEASE_VERSION = "1.003"
EXPECTED_STYLISTIC_SUBSTITUTIONS = {
    "ss03": {
        "A": "A.barless",
        "C": "C.poster",
        "S": "S.poster",
        "M": "M.expanding",
    },
    "ss06": {"zero": "zero.poster"},
    "ss07": {"one": "one.poster"},
    "ss08": {"three": "three.poster"},
    "ss09": {"six": "six.poster", "nine": "nine.poster"},
}


def best_name(font: TTFont, name_id: int) -> str:
    value = font["name"].getDebugName(name_id)
    if value is None:
        raise AssertionError(f"missing name ID {name_id}")
    return value


def feature_tags(font: TTFont, table_tag: str) -> set[str]:
    if table_tag not in font:
        return set()
    table = font[table_tag].table
    if not table.FeatureList:
        return set()
    return {record.FeatureTag for record in table.FeatureList.FeatureRecord}


def feature_single_substitutions(font: TTFont, tag: str) -> dict[str, str]:
    """Collect every SingleSubst mapping exposed by one GSUB feature tag."""

    table = font["GSUB"].table
    records = table.FeatureList.FeatureRecord
    lookup_indices = {
        index
        for record in records
        if record.FeatureTag == tag
        for index in record.Feature.LookupListIndex
    }
    mapping: dict[str, str] = {}
    for index in sorted(lookup_indices):
        lookup = table.LookupList.Lookup[index]
        assert lookup.LookupType == 1, (tag, index, lookup.LookupType)
        for subtable in lookup.SubTable:
            for source, target in subtable.mapping.items():
                prior = mapping.setdefault(source, target)
                assert prior == target, (tag, source, prior, target)
    return mapping


def validate_stylistic_substitutions(font: TTFont, outline: bool) -> None:
    for tag, expected in EXPECTED_STYLISTIC_SUBSTITUTIONS.items():
        mapping = feature_single_substitutions(font, tag)
        assert expected.items() <= mapping.items(), (tag, mapping, expected)
        if outline:
            expected_outline = {
                f"{source}.outline": f"{target}.outline"
                for source, target in expected.items()
            }
            assert expected_outline.items() <= mapping.items(), (
                tag,
                mapping,
                expected_outline,
            )


def validate_structure(path: Path, family: str, outline: bool) -> TTFont:
    font = TTFont(path, recalcTimestamp=False)
    assert best_name(font, 1) == family
    assert best_name(font, 16) == family
    assert best_name(font, 2) == "Regular"
    assert best_name(font, 5) == f"Version {RELEASE_VERSION}"
    assert font["OS/2"].achVendID == "IEBB"
    assert math.isclose(
        font["head"].fontRevision,
        float(RELEASE_VERSION),
        rel_tol=0.0,
        abs_tol=1 / 65536,
    )

    axes = font["fvar"].axes
    assert len(axes) == 1
    axis = axes[0]
    assert (axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue) == (
        "wght",
        100.0,
        400.0,
        900.0,
    )
    assert [instance.coordinates["wght"] for instance in font["fvar"].instances] == list(WEIGHTS)

    cmap = font.getBestCmap()
    assert len(cmap) == 437, f"unexpected encoded repertoire in {path}: {len(cmap)}"
    for start, end, label in FORBIDDEN_RANGES:
        offenders = sorted(cp for cp in cmap if start <= cp <= end)
        assert not offenders, f"{path} retains {label}: {offenders[:8]}"

    gsub = feature_tags(font, "GSUB")
    gpos = feature_tags(font, "GPOS")
    expected_gsub = EXPECTED_GSUB | ({"rvrn"} if outline else set())
    assert gsub == expected_gsub, (path, gsub, expected_gsub)
    assert EXPECTED_GPOS <= gpos, (path, gpos)
    validate_stylistic_substitutions(font, outline)
    if outline:
        assert font["GSUB"].table.FeatureVariations is not None
    assert "FILL" not in {axis.axisTag for axis in axes}
    return font


def glyph_record(font: TTFont, glyph_name: str):
    pen = RecordingPen()
    font.getGlyphSet()[glyph_name].draw(pen)
    return pen.value


def compare_at_weights(
    reference: Path,
    release: Path,
    *,
    weights: tuple[int, ...] = WEIGHTS,
    all_glyphs: bool = False,
) -> None:
    reference_variable = TTFont(reference, recalcTimestamp=False)
    release_variable = TTFont(release, recalcTimestamp=False)
    release_cmap = release_variable.getBestCmap()
    reference_cmap = reference_variable.getBestCmap()
    assert set(release_cmap) <= set(reference_cmap)

    if all_glyphs:
        reference_glyphs = set(reference_variable.getGlyphOrder())
        comparisons = [
            (name, name, name)
            for name in release_variable.getGlyphOrder()
            if name in reference_glyphs
        ]
        assert len(comparisons) == len(release_variable.getGlyphOrder()), (
            "release glyphs missing from reference",
            sorted(set(release_variable.getGlyphOrder()) - reference_glyphs),
        )
    else:
        comparisons = [
            (hex(cp), release_name, reference_cmap[cp])
            for cp, release_name in release_cmap.items()
        ]

    for weight in weights:
        reference_static = instantiateVariableFont(reference_variable, {"wght": weight}, inplace=False)
        release_static = instantiateVariableFont(release_variable, {"wght": weight}, inplace=False)
        for label, release_name, reference_name in comparisons:
            assert release_static["hmtx"].metrics[release_name] == reference_static["hmtx"].metrics[reference_name], (
                label,
                weight,
                "metrics",
            )
            assert glyph_record(release_static, release_name) == glyph_record(reference_static, reference_name), (
                label,
                weight,
                "outline",
            )


def compare_ttf_woff2(
    ttf: Path,
    woff2: Path,
    *,
    weights: tuple[int, ...] = WEIGHTS,
    all_glyphs: bool = False,
) -> None:
    ttf_font = TTFont(ttf, recalcTimestamp=False)
    web_font = TTFont(woff2, recalcTimestamp=False)
    assert ttf_font.getBestCmap() == web_font.getBestCmap()
    if all_glyphs:
        assert ttf_font.getGlyphOrder() == web_font.getGlyphOrder()
        comparisons = [(name, name) for name in ttf_font.getGlyphOrder()]
    else:
        comparisons = [(hex(cp), name) for cp, name in ttf_font.getBestCmap().items()]

    for weight in weights:
        ttf_static = instantiateVariableFont(ttf_font, {"wght": weight}, inplace=False)
        web_static = instantiateVariableFont(web_font, {"wght": weight}, inplace=False)
        for label, name in comparisons:
            assert ttf_static["hmtx"].metrics[name] == web_static["hmtx"].metrics[name], (
                label,
                weight,
                "web metrics",
            )
            assert glyph_record(ttf_static, name) == glyph_record(web_static, name), (
                label,
                weight,
                "web outline",
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font-dir", type=Path, default=Path(__file__).parents[1] / "fonts")
    parser.add_argument("--filled-source", type=Path)
    parser.add_argument("--outline-source", type=Path)
    args = parser.parse_args()

    files = {
        "filled_ttf": args.font_dir / "MonacoGPSans[wght].ttf",
        "filled_woff2": args.font_dir / "MonacoGPSans[wght].woff2",
        "outline_ttf": args.font_dir / "MonacoGPSansOutline[wght].ttf",
        "outline_woff2": args.font_dir / "MonacoGPSansOutline[wght].woff2",
    }
    for path in files.values():
        assert path.is_file(), path

    validate_structure(files["filled_ttf"], "Monaco GP Sans", False)
    validate_structure(files["filled_woff2"], "Monaco GP Sans", False)
    validate_structure(files["outline_ttf"], "Monaco GP Sans Outline", True)
    validate_structure(files["outline_woff2"], "Monaco GP Sans Outline", True)
    compare_ttf_woff2(files["filled_ttf"], files["filled_woff2"])
    compare_ttf_woff2(
        files["outline_ttf"],
        files["outline_woff2"],
        weights=OUTLINE_WEIGHTS,
        all_glyphs=True,
    )

    if bool(args.filled_source) != bool(args.outline_source):
        raise SystemExit("Provide both frozen source fonts or neither")
    if args.filled_source:
        compare_at_weights(args.filled_source, files["filled_ttf"])
        compare_at_weights(
            args.outline_source,
            files["outline_ttf"],
            weights=OUTLINE_WEIGHTS,
            all_glyphs=True,
        )

    print("PASS: Monaco GP Sans Latin release")
    print("  families: Monaco GP Sans / Monaco GP Sans Outline")
    print("  weights: 100, 200, 300, 400, 500, 600, 700, 800, 900")
    print("  encoded codepoints: 437 each")
    print("  forbidden scripts: absent")
    print("  Filled TTF/WOFF2 parity: exact at all nine named weights")
    print("  Outline TTF/WOFF2 parity: all glyphs exact every 50 weight units")
    if args.filled_source:
        print("  frozen-source geometry and metrics: exact at named Filled weights")
        print("  frozen-source Outline geometry and metrics: all glyphs exact every 50 weight units")


if __name__ == "__main__":
    main()
