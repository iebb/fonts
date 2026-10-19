"""Semantic regression fixtures are rendered through actual TTF/VF files."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor
from fontTools.varLib import build as build_variable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_stroke_font import build_font, flatten_path
from verify_glyph_invariants import DEFAULT_SPEC, verify


class GlyphInvariantTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.directory = Path(self.workspace.name)
        self.specification = json.loads(DEFAULT_SPEC.read_text())

    def tearDown(self):
        self.workspace.cleanup()

    def spec(self, *codepoints, overrides=None):
        data = deepcopy(self.specification)
        data["glyphs"] = [g for g in data["glyphs"] if g["codepoint"] in codepoints]
        if overrides:
            for glyph in data["glyphs"]:
                glyph["requirements"].update(overrides.get(glyph["codepoint"], {}))
        path = self.directory / "invariants.json"
        path.write_text(json.dumps(data))
        return path

    def font(self, codepoint, paths, width=30, name="fixture.ttf"):
        path = self.directory / name
        build_font([{"codepoint": codepoint, "width": width,
                     "strokes": [flatten_path(stroke) for stroke in paths]}], path)
        return path

    @staticmethod
    def bars(upper=400, lower=600, gap=700):
        return [f"M {512-upper/2} {100+gap} L {512+upper/2} {100+gap}",
                f"M {512-lower/2} 100 L {512+lower/2} 100"]

    def test_short_upper_long_lower_bar_and_large_gap_pass(self):
        report = verify(self.font(0x3D007, self.bars()), self.spec("U+3D007"))
        self.assertTrue(report["passed"], report["errors"])
        measured = report["checks"][0]["measured"]
        self.assertEqual(measured["ink_component_count"], 2)
        self.assertGreater(measured["lower_to_upper_ink_span_ratio"], 1.4)

    def test_equal_and_reversed_bar_lengths_fail(self):
        for upper, lower in ((600, 600), (600, 300)):
            with self.subTest(upper=upper, lower=lower):
                report = verify(self.font(0x3D007, self.bars(upper, lower)), self.spec("U+3D007"))
                self.assertFalse(report["passed"])
                self.assertTrue(any("lower/upper ink span ratio" in error for error in report["errors"]))

    def test_compressed_vertical_bar_gap_fails(self):
        report = verify(self.font(0x3D007, self.bars(gap=250)), self.spec("U+3D007"))
        self.assertFalse(report["passed"])
        self.assertTrue(any("vertical center gap" in error for error in report["errors"]))

    def test_excessive_lower_bar_length_fails(self):
        report = verify(self.font(0x3D007, self.bars(250, 600)), self.spec("U+3D007"))
        self.assertFalse(report["passed"])
        self.assertTrue(any("above 1.6" in error for error in report["errors"]))

    def test_six_lower_legs_pass_and_missing_inner_leg_fails(self):
        for count in (6, 5):
            with self.subTest(legs=count):
                xs = [120, 260, 400, 540, 680, 820]
                if count == 5:
                    xs.remove(540)
                paths = ["M 100 820 L 840 820"] + [f"M {x} 100 L {x} 700" for x in xs]
                report = verify(self.font(0x3D034, paths), self.spec("U+3D034"))
                self.assertEqual(report["passed"], count == 6, report["errors"])
                self.assertEqual([row["major_descender_count"] for row in
                                  report["checks"][0]["measured"]["scan_rows"]], [count]*3)

    def test_detached_roof_fails_component_requirement(self):
        for components in (3, 4):
            with self.subTest(components=components):
                paths = [f"M 200 {100+index*180} L 800 {100+index*180}"
                         for index in range(components)]
                report = verify(self.font(0x3D00B, paths), self.spec("U+3D00B"))
                self.assertEqual(report["passed"], components == 3, report["errors"])

    def test_altar_upper_lower_bar_ratio_rejects_equal_bars(self):
        spec = self.spec("U+3D036", overrides={"U+3D036": {
            "upper_roi_height_fractions": [.46, .54],
            "lower_roi_height_fractions": [.64, .72]}})
        for upper_length in (400, 700):
            with self.subTest(upper_length=upper_length):
                paths = ["M 512 750 L 512 800", "M 150 250 L 850 250",
                         f"M {512-upper_length/2} 400 L {512+upper_length/2} 400"]
                paths += [f"M {x} 0 L {x} 250" for x in (300, 512, 724)]
                report = verify(self.font(0x3D036, paths), spec)
                self.assertEqual(report["passed"], upper_length == 400, report["errors"])

    def test_right_bar_roi_excludes_longer_left_component(self):
        spec = self.spec("U+3D02B", overrides={"U+3D02B": {
            "upper_roi_height_fractions": [.32, .38],
            "lower_roi_height_fractions": [.61, .68]}})
        for upper_length in (100, 200):
            with self.subTest(upper_length=upper_length):
                paths = ["M 0 0 L 0 1000", "M 1000 0 L 1000 1000",
                         "M 100 650 L 450 650", "M 100 350 L 450 350",
                         "M 600 350 L 800 350",
                         f"M {700-upper_length/2} 650 L {700+upper_length/2} 650"]
                report = verify(self.font(0x3D02B, paths), spec)
                self.assertEqual(report["passed"], upper_length == 100, report["errors"])

    def test_missing_isolated_crossbar_fails_ink_presence(self):
        spec = self.spec("U+3D029", overrides={"U+3D029": {
            "roi_width_fractions": [.45, .55], "roi_height_fractions": [.45, .55]}})
        boundary = ["M 100 100 L 900 100 L 900 900 L 100 900 Z"]
        for present in (True, False):
            with self.subTest(present=present):
                paths = boundary + (["M 470 480 L 550 520"] if present else [])
                report = verify(self.font(0x3D029, paths), spec)
                self.assertEqual(report["passed"], present, report["errors"])

    def test_free_lower_endpoint_must_extend_beyond_upper_hook(self):
        spec = self.spec("U+3D018", overrides={"U+3D018": {
            "roi_width_fractions": [.45, .85],
            "upper_roi_height_fractions": [.2, .3],
            "lower_roi_height_fractions": [.5, .6]}})
        for lower_end in (700, 600):
            with self.subTest(lower_end=lower_end):
                paths = ["M 100 100 L 100 900", "M 900 100 L 900 900",
                         "M 500 700 L 650 700", f"M 500 450 L {lower_end} 450"]
                report = verify(self.font(0x3D018, paths), spec)
                self.assertEqual(report["passed"], lower_end == 700, report["errors"])

    def test_elongated_diagonal_marks_pass_and_collapsed_dots_fail(self):
        spec = self.spec("U+3D019", overrides={"U+3D019": {"regions": [
            {"name": "left diagonal", "roi_width_fractions": [.2, .4], "roi_height_fractions": [.35, .65]},
            {"name": "right diagonal", "roi_width_fractions": [.6, .8], "roi_height_fractions": [.35, .65]}]}})
        boundary = ["M 100 100 L 900 100 L 900 900 L 100 900 Z"]
        for elongated in (True, False):
            with self.subTest(elongated=elongated):
                marks = (["M 300 450 L 380 550", "M 620 450 L 700 550"] if elongated else
                         ["M 335 495 L 345 505", "M 655 495 L 665 505"])
                report = verify(self.font(0x3D019, boundary+marks), spec)
                self.assertEqual(report["passed"], elongated, report["errors"])

    def test_missing_codepoint_cannot_pass_using_notdef(self):
        report = verify(self.font(0xE000, self.bars()), self.spec("U+3D007"))
        self.assertFalse(report["passed"])
        self.assertIn("missing from the font cmap", report["errors"][0])

    def test_all_named_and_standard_variable_weights_are_raster_checked(self):
        document = DesignSpaceDocument()
        axis = AxisDescriptor()
        axis.name, axis.tag = "Weight", "wght"
        axis.minimum, axis.default, axis.maximum = 300, 400, 700
        document.addAxis(axis)
        for weight, width in ((300, 23.5), (400, 30), (600, 43), (700, 49.5)):
            path = self.font(0x3D007, self.bars(), width, f"master-{weight}.ttf")
            source = SourceDescriptor()
            source.path, source.name = str(path), str(weight)
            source.familyName, source.styleName = "Invariant Fixture", str(weight)
            source.location = {"Weight": weight}
            if weight == 400:
                source.copyInfo = source.copyLib = source.copyFeatures = True
            document.addSource(source)
        for weight in (300, 400, 450, 500, 600, 700):
            instance = InstanceDescriptor()
            instance.name, instance.familyName, instance.styleName = str(weight), "Invariant Fixture", str(weight)
            instance.location = {"Weight": weight}
            document.addInstance(instance)
        variable, _, _ = build_variable(document)
        target = self.directory / "variable.ttf"
        variable.save(target)
        report = verify(target, self.spec("U+3D007"))
        self.assertTrue(report["passed"], report["errors"])
        self.assertEqual(report["weights"], [300, 400, 450, 500, 600, 700])
        self.assertEqual(len(report["checks"]), 6)

    def test_cli_writes_reviewable_failure_and_exits_nonzero(self):
        font = self.font(0x3D007, self.bars(600, 600))
        output = self.directory / "report.json"
        result = subprocess.run([sys.executable, str(ROOT / "tools/verify_glyph_invariants.py"),
                                 "--font", str(font), "--spec", str(self.spec("U+3D007")),
                                 "--output", str(output)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(json.loads(output.read_text())["passed"])
        self.assertFalse(json.loads(result.stdout)["passed"])


if __name__ == "__main__":
    unittest.main()
