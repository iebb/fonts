"""Regression tests for coverage errors that can falsely claim full Unicode."""
import gzip
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_coverage import compact_ranges, font_coverage, read_property, read_unicode_data
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_first_last_ranges_are_expanded_inclusively(self):
        p = self.root / "UnicodeData.txt"
        p.write_text("0041;LATIN CAPITAL LETTER A;Lu\n3400;<CJK Ideograph Extension A, First>;Lo\n3402;<CJK Ideograph Extension A, Last>;Lo\n")
        chars = read_unicode_data(p)
        self.assertEqual(set(chars), {0x41, 0x3400, 0x3401, 0x3402})
        self.assertEqual(chars[0x3401].category, "Lo")

    def test_malformed_ranges_fail_instead_of_silently_losing_characters(self):
        p = self.root / "UnicodeData.txt"
        p.write_text("3402;<CJK Ideograph, Last>;Lo\n")
        with self.assertRaises(ValueError):
            read_unicode_data(p)
        p.write_text("3400;<CJK Ideograph, First>;Lo\n")
        with self.assertRaises(ValueError):
            read_unicode_data(p)

    def test_properties_ignore_comments_and_expand_ranges(self):
        p = self.root / "DerivedCoreProperties.txt"
        p.write_text("0041..0042 ; Alphabetic # comment\nFE00..FE0F ; Default_Ignorable_Code_Point\n")
        self.assertEqual(len(read_property(p, "Default_Ignorable_Code_Point")), 16)
        self.assertNotIn(0x41, read_property(p, "Default_Ignorable_Code_Point"))

    def make_font(self, path, mapping):
        builder = FontBuilder(1000, isTTF=True)
        glyphs = [".notdef", "actual"]
        builder.setupGlyphOrder(glyphs)
        builder.setupCharacterMap(mapping)
        pen = TTGlyphPen(None)
        pen.moveTo((100, 0)); pen.lineTo((500, 0)); pen.lineTo((500, 700)); pen.closePath()
        outline = pen.glyph()
        builder.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "actual": outline})
        builder.setupHorizontalMetrics({g: (600, 0) for g in glyphs})
        builder.setupHorizontalHeader(ascent=800, descent=-200)
        builder.setupNameTable({"familyName": "Audit Test", "styleName": "Regular"})
        builder.setupOS2(); builder.setupPost(); builder.setupMaxp()
        builder.save(path)

    def test_supplementary_cmap_and_notdef_filter(self):
        p = self.root / "sample.ttf"
        self.make_font(p, {0x41: "actual", 0x1FAE9: "actual", 0x42: ".notdef"})
        points, record = font_coverage(p)
        self.assertEqual(points, {0x41, 0x1FAE9})
        self.assertEqual(record["faces"][0]["family"], "Audit Test")

    def test_collection_reads_all_faces(self):
        from fontTools.ttLib import TTFont
        first, second = self.root / "a.ttf", self.root / "b.ttf"
        self.make_font(first, {0x41: "actual"}); self.make_font(second, {0x1FAE9: "actual"})
        collection = TTCollection(); collection.fonts = [TTFont(first), TTFont(second)]
        p = self.root / "sample.ttc"; collection.save(p); collection.close()
        points, record = font_coverage(p)
        self.assertEqual(points, {0x41, 0x1FAE9}); self.assertEqual(len(record["faces"]), 2)

    def test_gzip_hex_blank_record_and_diagnostic_exclusion(self):
        p = self.root / "sample.hex.gz"
        with gzip.open(p, "wt") as stream:
            stream.write("0041:FF00\n0020:0000\n1FAE9:0010\n")
        points, record = font_coverage(p)
        self.assertEqual(points, {0x41, 0x20, 0x1FAE9})
        self.assertEqual(record["blank_codepoint_ranges"], ["0020"])
        points, record = font_coverage(p, diagnostic=True)
        self.assertEqual(points, set()); self.assertTrue(record["excluded_from_coverage"])

    def test_compact_ranges_retain_astral_points(self):
        self.assertEqual(compact_ranges([0x41, 0x42, 0x10000, 0x10FFFF]), ["0041-0042", "10000", "10FFFF"])

    def test_unreviewed_experimental_manifest_cannot_satisfy_coverage(self):
        p = self.root / "sample.ttf"
        self.make_font(p, {0x3D000: "actual"})
        (self.root / "manifest.json").write_text('{"coverage_eligible": false}')
        points, record = font_coverage(p)
        self.assertEqual(points, set())
        self.assertEqual(record["mapped_codepoint_count"], 1)
        self.assertFalse(record["coverage_eligible"])
        self.assertIn("manifest", record["exclusion_reason"])


if __name__ == "__main__":
    unittest.main()
