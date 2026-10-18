"""Integration checks using real curved outlines, cmap and OFL metadata."""

import json
from pathlib import Path
import tempfile
import unittest

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from tools.build_han_supplement import build_han_supplement


def make_source(path: Path, cmap: dict[int, str]) -> None:
    glyphs = {}
    for name in [".notdef", "curved", "second", "empty", "tofu"]:
        pen = TTGlyphPen(None)
        if name != "empty":
            pen.moveTo((50, 0))
            pen.lineTo((50, 700))
            if name == "curved":
                pen.qCurveTo((900, 900), (700, 0))
            elif name == "second":
                pen.lineTo((400, 700))
                pen.lineTo((400, 0))
            else:
                pen.lineTo((750, 700))
                pen.lineTo((750, 0))
            pen.closePath()
        glyphs[name] = pen.glyph()
    font = FontBuilder(1000, isTTF=True)
    font.setupGlyphOrder(list(glyphs))
    font.setupCharacterMap(cmap)
    font.setupGlyf(glyphs)
    font.setupHorizontalMetrics({name: (1000, 50) for name in glyphs})
    font.setupHorizontalHeader(ascent=900, descent=-100)
    font.setupNameTable({
        "familyName": "Reserved Source Han", "styleName": "Regular",
        "fullName": "Reserved Source Han Regular", "psName": "ReservedSourceHan-Regular",
        "copyright": "Copyright Original Han Designers",
        "licenseDescription": "SIL Open Font License, Version 1.1",
        "licenseInfoURL": "https://openfontlicense.org/",
    })
    font.setupOS2(sTypoAscender=900, sTypoDescender=-100, usWinAscent=900, usWinDescent=100)
    font.setupPost()
    font.setupMaxp()
    font.save(path)


def commands(font: TTFont, cp: int):
    pen = RecordingPen()
    font.getGlyphSet()[font.getBestCmap()[cp]].draw(pen)
    return pen.value


class HanSubsetIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.first = self.root / "PlangothicP1-Regular.ttf"
        self.second = self.root / "PlangothicP2-Regular.ttf"
        make_source(self.first, {
            0x20: "empty", 0x41: "curved", 0x20000: "curved", 0x20001: "second",
            0x20002: "empty", 0x20003: "tofu", 0x20004: ".notdef",
            0x20005: "curved", 0x20006: "curved",
        })
        make_source(self.second, {0x20000: "second", 0x20010: "curved"})
        self.ucd = self.root / "UnicodeData.txt"
        rows = [(0x20, "Zs"), (0x41, "Lu")]
        rows += [(cp, "Lo") for cp in range(0x20000, 0x20005)]
        rows += [(0x20005, "Cf"), (0x20010, "Lo")]
        self.ucd.write_text("".join(f"{cp:X};SYNTHETIC TEST CHARACTER;{category};0;L;;;;;N;;;;;\n" for cp, category in rows))
        self.baseline = self.root / "noto-manifest.json"
        self.baseline.write_text(json.dumps({"css_codepoint_ranges": ["0020", "0041"], "css_codepoint_count": 2}))
        self.output = self.root / "han"

    def build(self, **kwargs):
        return build_han_supplement([self.first, self.second], self.output, self.ucd, self.baseline, **kwargs)

    def test_real_curves_are_preserved_and_coverage_is_novel_and_disjoint(self):
        manifest = self.build()
        self.assertEqual(3, manifest["codepoint_count"])
        measured = set()
        with TTFont(self.first) as original:
            original_curve = commands(original, 0x20000)
        self.assertTrue(any(operator == "qCurveTo" for operator, _ in original_curve))
        for record in manifest["fonts"]:
            with TTFont(self.output / record["file"]) as font:
                points = set(font.getBestCmap())
                self.assertFalse(measured & points)
                measured.update(points)
                if 0x20000 in points:
                    self.assertEqual(original_curve, commands(font, 0x20000))
                names = font["name"]
                self.assertIn("Panorama Gothic Han", names.getDebugName(1))
                self.assertEqual("Copyright Original Han Designers", names.getDebugName(0))
                self.assertEqual("SIL Open Font License, Version 1.1", names.getDebugName(13))
                self.assertNotIn("Reserved Source Han", names.getDebugName(1))
                with TTFont(self.output / record["woff"]) as woff:
                    self.assertEqual(points, set(woff.getBestCmap()))
        self.assertEqual({0x20000, 0x20001, 0x20010}, measured)
        rejected = {entry["codepoint"]: entry["reason"] for source in manifest["sources"] for entry in source["rejected_glyphs"]}
        self.assertEqual("empty_visible_glyph", rejected["U+20002"])
        self.assertEqual("duplicate_missing_glyph_outline", rejected["U+20003"])
        self.assertEqual(measured, {int(line[2:], 16) for line in (self.output / "codepoints.txt").read_text().splitlines()})

    def test_assigned_spaces_are_allowed_but_empty_visible_glyphs_are_not(self):
        self.baseline.write_text(json.dumps({"codepoints": ["U+0041"]}))
        manifest = self.build()
        points = {int(cp[2:], 16) for record in manifest["fonts"] for cp in record["codepoints"]}
        self.assertIn(0x20, points)
        self.assertNotIn(0x20002, points)
        self.assertNotIn(0x20005, points)
        self.assertNotIn(0x20006, points)

    def test_prior_font_coverage_is_excluded_and_builds_are_reproducible(self):
        first = self.build()
        expected = {(record["file"], ext): (self.output / record[ext]).read_bytes() for record in first["fonts"] for ext in ("file", "woff")}
        second = self.build()
        actual = {(record["file"], ext): (self.output / record[ext]).read_bytes() for record in second["fonts"] for ext in ("file", "woff")}
        self.assertEqual(expected, actual)
        prior_font = self.output / first["fonts"][0]["file"]
        later_output = self.root / "later"
        later = build_han_supplement([self.second], later_output, self.ucd, self.baseline, prior_fonts=[prior_font])
        self.assertEqual(["U+20010"], later["fonts"][0]["codepoints"])


if __name__ == "__main__":
    unittest.main()
