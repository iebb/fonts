"""Verify real variation interpolation preserves a pen stroke's trajectory."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_stroke_variable import build_variable, topology, stroke_width


class StrokeVariableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory()
        cls.root = Path(cls.workspace.name)
        sources = cls.root / "source"
        sources.mkdir()
        # A straight bar and an off-grid curve exercise duplicate disk closure
        # at fractional centers, where floating sin(2*pi) broke compatibility.
        for cp, path in [(0xE100, "M 200 400 L 800 400"),
                         (0xE101, "M 200.23 200.37 C 201.17 701.31 700.71 701.19 701.29 201.13")]:
            (sources / f"U{cp:05X}.json").write_text(json.dumps({
                "codepoint": f"U+{cp:05X}", "viewBox": [0, 0, 1024, 1024],
                "stroke_width": 43, "strokes": [{"path": path}],
            }))
        cls.output = cls.root / "font"
        cls.report = build_variable(sources, cls.output, "Stroke Test Variable")
        cls.path = cls.output / "StrokeTestVariable.ttf"

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def test_real_axis_and_compatible_masters(self):
        font = TTFont(self.path)
        axis = font["fvar"].axes[0]
        self.assertEqual((axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue),
                         ("wght", 300, 400, 700))
        self.assertIn("gvar", font)
        self.assertEqual(len(font.getBestCmap()), 2)
        masters = [TTFont(path) for path in (self.output / "masters").glob("*.ttf")]
        self.assertTrue(all(topology(master) == topology(masters[0]) for master in masters))

    def test_default_instance_preserves_regular_centerline_expansion(self):
        variable = TTFont(self.path)
        regular = TTFont(self.output / "masters/StrokeTestVariable-Regular.ttf")
        instance = instantiateVariableFont(variable, {"wght": 400}, inplace=False)
        for name in variable.getGlyphOrder():
            self.assertEqual(list(instance["glyf"][name].coordinates),
                             list(regular["glyf"][name].coordinates))

    def test_intermediate_width_changes_without_moving_bar_center(self):
        widths = []
        centers = []
        for weight in (300, 350, 400, 550, 700):
            font = ImageFont.truetype(str(self.path), 2048)
            font.set_variation_by_axes([weight])
            image = Image.new("L", (2304, 2304))
            ImageDraw.Draw(image).text((100, 1950), chr(0xE100), font=font,
                                      fill=255, anchor="ls")
            ink = np.flatnonzero(np.asarray(image)[:, 1100] >= 128)
            widths.append(len(ink) / 2)
            centers.append((ink[0] + ink[-1]) / 4)
        self.assertTrue(all(a < b for a, b in zip(widths, widths[1:])))
        self.assertAlmostEqual(widths[0], 23.5, delta=1)
        self.assertAlmostEqual(widths[-1], 49.5, delta=1)
        # Master quantization plus interpolation rounding can shift a raster
        # center by one 1024-em unit; the underlying pen trajectory is fixed.
        self.assertLessEqual(max(centers) - min(centers), 1.0)

    def test_remapped_anchor_weights_are_explicit_masters(self):
        self.assertEqual(stroke_width(400), 30)
        self.assertEqual(stroke_width(600), 43)
        variable = TTFont(self.path)
        self.assertIn(600, [i.coordinates["wght"] for i in variable["fvar"].instances])
        # Compare compiled integer coordinates; instancer retains fractional
        # IUP results in memory until the TrueType file is written.
        instance = TTFont(self.output / "StrokeTestVariable-SemiBold.ttf")
        master = TTFont(self.output / "masters/StrokeTestVariable-SemiBold.ttf")
        for name in variable.getGlyphOrder():
            actual, expected = instance["glyf"][name], master["glyf"][name]
            self.assertEqual(actual.endPtsOfContours, expected.endPtsOfContours)
            # IUP interpolation and final integer compilation may differ by
            # one em unit, below a quarter pixel in the 248px specimen.
            self.assertLessEqual(max(abs(a-b) for p, q in zip(actual.coordinates, expected.coordinates)
                                     for a, b in zip(p, q)), 1)
            self.assertEqual(instance["hmtx"][name][0], master["hmtx"][name][0])


if __name__ == "__main__":
    unittest.main()
