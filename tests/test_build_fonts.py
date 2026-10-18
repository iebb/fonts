"""Small, real-font checks for the Unifont outline supplement builder."""

from pathlib import Path
import tempfile
import unittest

from fontTools.ttLib import TTFont

from tools.build_fonts import bitmap_rectangles, build_fonts, parse_hex


def bitmap(*rows: int, width: int = 8) -> str:
    """Encode explicit top rows followed by empty rows into Unifont HEX."""
    if len(rows) > 16:
        raise ValueError("A Unifont glyph has sixteen rows")
    return "".join(f"{row:0{width // 4}X}" for row in (*rows, *([0] * (16 - len(rows)))))


def ucd_record(codepoint: int, name: str, category: str) -> str:
    return ";".join(
        [f"{codepoint:04X}", name, category, "0", "L", "", "", "", "", "N", "", "", "", "", ""]
    )


class ParseHexTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def source(self, name: str, content: str) -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_reads_both_unifont_widths_and_supplementary_scalars(self):
        narrow = bitmap(0x18, 0x24, 0x42)
        wide = bitmap(0x8001, width=16)
        path = self.source("glyphs.hex", f"0041:{narrow}\n1F6DC:{wide}\n")
        result = parse_hex([path])
        self.assertEqual({0x41, 0x1F6DC}, set(result))
        self.assertEqual(narrow.upper(), result[0x41].upper())
        self.assertEqual(wide.upper(), result[0x1F6DC].upper())

    def test_ignores_blank_lines_and_comments(self):
        data = bitmap(0x80)
        path = self.source("comments.hex", f"# Source attribution\n\n0041:{data}\n")
        self.assertEqual({0x41: data}, parse_hex([path]))

    def test_identical_duplicates_are_allowed_across_sources(self):
        data = bitmap(0x80)
        first = self.source("one.hex", f"0041:{data}\n")
        second = self.source("two.hex", f"0041:{data.lower()}\n")
        self.assertEqual({0x41}, set(parse_hex([first, second])))

    def test_conflicting_duplicates_raise(self):
        first = self.source("one.hex", f"0041:{bitmap(0x80)}\n")
        second = self.source("two.hex", f"0041:{bitmap(0x40)}\n")
        with self.assertRaises(ValueError):
            parse_hex([first, second])

    def test_invalid_bitmap_data_raises(self):
        for data in ("00", "0" * 31, "0" * 33, "G" + "0" * 31):
            with self.subTest(data=data):
                path = self.source("bad.hex", f"0041:{data}\n")
                with self.assertRaises(ValueError):
                    parse_hex([path])

    def test_invalid_unicode_scalars_raise(self):
        for codepoint in ("D800", "DFFF", "110000", "-1"):
            with self.subTest(codepoint=codepoint):
                path = self.source("bad.hex", f"{codepoint}:{bitmap(0x80)}\n")
                with self.assertRaises(ValueError):
                    parse_hex([path])


class BitmapRectangleTests(unittest.TestCase):
    def test_blank_bitmap_has_no_rectangles(self):
        self.assertEqual([], bitmap_rectangles(bitmap()))

    def test_identical_horizontal_runs_merge_vertically(self):
        rectangles = bitmap_rectangles(bitmap(0xC3, 0xC3, 0x03))
        self.assertEqual({(0, 0, 2, 2), (6, 0, 2, 3)}, set(rectangles))

    def test_wide_glyph_retains_sixteenth_pixel(self):
        rectangles = bitmap_rectangles(bitmap(0x8001, 0x8001, width=16))
        self.assertEqual({(0, 0, 1, 2), (15, 0, 1, 2)}, set(rectangles))

    def test_changed_run_width_is_a_separate_rectangle(self):
        rectangles = bitmap_rectangles(bitmap(0xC0, 0xE0))
        self.assertEqual({(0, 0, 2, 1), (0, 1, 3, 1)}, set(rectangles))


class BuildFontsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.source = self.root / "input.hex"
        self.source.write_text(
            "\n".join(
                (
                    f"0020:{bitmap()}",
                    f"0041:{bitmap(0x18, 0x24, 0x42, 0x7E, 0x42)}",
                    f"0042:{bitmap(0x7C, 0x42, 0x7C, 0x42, 0x7C)}",
                    f"0301:{bitmap(0x10, 0x20)}",
                    f"1F6DC:{bitmap(0x8001, 0x4002, 0x2004, width=16)}",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        self.output = self.root / "fonts"

    def make_ucd(self, records) -> Path:
        path = self.root / "UnicodeData.txt"
        path.write_text("\n".join(ucd_record(*record) for record in records) + "\n", encoding="utf-8")
        return path

    def read_fonts(self, manifest):
        self.assertIn("fonts", manifest)
        self.assertTrue(manifest["fonts"])
        result = []
        for entry in manifest["fonts"]:
            path = self.output / entry["file"]
            self.assertTrue(path.is_file(), path)
            font = TTFont(path)
            self.addCleanup(font.close)
            self.assertEqual(entry["codepoint_count"], len(font.getBestCmap()))
            self.assertIn("first", entry)
            self.assertIn("last", entry)
            woff_path = self.output / entry["woff"]
            self.assertTrue(woff_path.is_file(), woff_path)
            woff = TTFont(woff_path)
            self.addCleanup(woff.close)
            self.assertEqual("woff", woff.flavor)
            self.assertEqual(font.getBestCmap(), woff.getBestCmap())
            result.append(font)
        return result

    def test_emits_loadable_fonts_with_real_outlines_and_licenses(self):
        manifest = build_fonts([self.source], self.output)
        fonts = self.read_fonts(manifest)
        by_codepoint = {cp: font for font in fonts for cp in font.getBestCmap()}
        self.assertEqual({0x20, 0x41, 0x42, 0x301, 0x1F6DC}, set(by_codepoint))
        for codepoint, width in ((0x41, 512), (0x1F6DC, 1024)):
            font = by_codepoint[codepoint]
            name = font.getBestCmap()[codepoint]
            self.assertGreater(font["glyf"][name].numberOfContours, 0)
            self.assertEqual(width, font["hmtx"][name][0])
        space_font = by_codepoint[0x20]
        space_name = space_font.getBestCmap()[0x20]
        self.assertEqual(0, space_font["glyf"][space_name].numberOfContours)
        self.assertEqual(512, space_font["hmtx"][space_name][0])
        supplementary = by_codepoint[0x1F6DC]
        self.assertTrue(any(table.format == 12 for table in supplementary["cmap"].tables))
        for font in fonts:
            licenses = " ".join(name.toUnicode() for name in font["name"].names if name.nameID == 13).lower()
            self.assertTrue("gpl" in licenses or "general public license" in licenses)
            self.assertIn("exception", licenses)

    def test_unicode_data_controls_categories_and_mark_advance_width(self):
        ucd = self.make_ucd(
            (
                (0x20, "SPACE", "Zs"),
                (0x41, "LATIN CAPITAL LETTER A", "Lu"),
                (0x301, "COMBINING ACUTE ACCENT", "Mn"),
                (0x1F6DC, "WIRELESS", "So"),
            )
        )
        fonts = self.read_fonts(build_fonts([self.source], self.output, ucd=ucd))
        by_codepoint = {cp: font for font in fonts for cp in font.getBestCmap()}
        self.assertEqual({0x20, 0x41, 0x301, 0x1F6DC}, set(by_codepoint))
        mark = by_codepoint[0x301]
        mark_name = mark.getBestCmap()[0x301]
        advance, lsb = mark["hmtx"][mark_name]
        self.assertEqual(0, advance)
        self.assertLessEqual(mark["glyf"][mark_name].xMax, 0)
        self.assertEqual(mark["glyf"][mark_name].xMin, lsb)

    def test_codepoint_file_supports_ranges_and_plain_hex(self):
        requested = self.root / "codepoints.txt"
        requested.write_text("# Selected graphic characters\nU+0041..U+0042\n1F6DC\n", encoding="utf-8")
        fonts = self.read_fonts(build_fonts([self.source], self.output, only_codepoints=requested))
        self.assertEqual({0x41, 0x42, 0x1F6DC}, {cp for font in fonts for cp in font.getBestCmap()})

    def test_unicode_data_first_last_ranges_include_interior_glyphs(self):
        self.source.write_text(f"4E01:{bitmap(0xFFFF, width=16)}\n", encoding="utf-8")
        ucd = self.make_ucd(
            (
                (0x4E00, "<CJK Ideograph, First>", "Lo"),
                (0x9FFF, "<CJK Ideograph, Last>", "Lo"),
            )
        )
        fonts = self.read_fonts(build_fonts([self.source], self.output, ucd=ucd))
        self.assertEqual({0x4E01}, {cp for font in fonts for cp in font.getBestCmap()})

    def test_unicode_data_excludes_controls_and_format_characters(self):
        ucd = self.make_ucd(
            (
                (0x20, "SPACE", "Zs"),
                (0x41, "SYNTHETIC CONTROL", "Cc"),
                (0x42, "SYNTHETIC FORMAT", "Cf"),
            )
        )
        fonts = self.read_fonts(build_fonts([self.source], self.output, ucd=ucd))
        self.assertEqual({0x20}, {cp for font in fonts for cp in font.getBestCmap()})

    def test_plane_and_glyph_limit_partitioning_is_lossless(self):
        fonts = self.read_fonts(build_fonts([self.source], self.output, max_glyphs=2))
        all_codepoints = [cp for font in fonts for cp in font.getBestCmap()]
        self.assertEqual(5, len(all_codepoints))
        self.assertEqual(5, len(set(all_codepoints)))
        for font in fonts:
            codepoints = set(font.getBestCmap())
            self.assertLessEqual(len(codepoints), 2)
            self.assertEqual(1, len({cp >> 16 for cp in codepoints}))

    def test_requested_codepoints_without_source_are_reported_and_not_faked(self):
        requested = self.root / "codepoints.txt"
        requested.write_text("U+0041\nU+0043\n", encoding="utf-8")
        manifest = build_fonts([self.source], self.output, only_codepoints=requested)
        fonts = self.read_fonts(manifest)
        self.assertEqual({0x41}, {cp for font in fonts for cp in font.getBestCmap()})
        self.assertEqual(2, manifest["selection"]["requested_count"])
        self.assertEqual(["U+0043"], manifest["selection"]["requested_without_source"])

    def test_repeated_builds_have_identical_font_bytes(self):
        first = build_fonts([self.source], self.output)
        expected = {
            entry[key]: (self.output / entry[key]).read_bytes()
            for entry in first["fonts"]
            for key in ("file", "woff")
        }
        second_output = self.root / "repeat"
        second = build_fonts([self.source], second_output)
        actual = {
            entry[key]: (second_output / entry[key]).read_bytes()
            for entry in second["fonts"]
            for key in ("file", "woff")
        }
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
