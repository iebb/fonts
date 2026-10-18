"""Raster checks of the actual centerline expansion, independent of source art."""

from pathlib import Path
import math
import json
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_stroke_font import build_font, flatten_path, load_sources, point_segment_distance


class StrokeFontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory()
        cls.font_path = Path(cls.workspace.name) / "strokes.ttf"
        paths = [
            ["M 200 300 L 700 300"],
            ["M 450 100 L 450 700"],
            ["M 200 300 L 700 300", "M 450 100 L 450 700"],
            ["M 200 200 C 200 500 500 500 500 200"],
            ["M 200 200 L 700 200 L 700 700 L 200 700 Z"],
        ]
        sources = [{"codepoint": 0xE000 + index, "width": 40,
                    "strokes": [flatten_path(path) for path in strokes]}
                   for index, strokes in enumerate(paths)]
        build_font(sources, cls.font_path)
        cls.font = ImageFont.truetype(str(cls.font_path), 4096)

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def render(self, codepoint):
        image = Image.new("L", (4300, 4300))
        ImageDraw.Draw(image).text((100, 3900), chr(codepoint), font=self.font,
                                  fill=255, anchor="ls", stroke_width=0)
        return image

    @staticmethod
    def pixel(image, x, y):
        return image.getpixel((round(100 + 4*x), round(3900 - 4*y)))

    def test_straight_stroke_width_and_round_caps(self):
        image = self.render(0xE000)
        for x in (225, 350, 500, 675):
            column = np.asarray(image)[:, round(100 + 4*x)] >= 128
            self.assertAlmostEqual(int(column.sum()) / 4, 40, delta=0.5)
        # Round cap includes its axial pole; the corner of its bounding square
        # stays empty, which a square cap would not satisfy.
        self.assertGreater(self.pixel(image, 182, 300), 200)
        self.assertEqual(self.pixel(image, 182, 318), 0)
        self.assertEqual(self.pixel(image, 178, 300), 0)

    def test_crossings_render_the_union_without_knockouts(self):
        horizontal = np.asarray(self.render(0xE000)) >= 128
        vertical = np.asarray(self.render(0xE001)) >= 128
        crossing = np.asarray(self.render(0xE002)) >= 128
        self.assertTrue(np.array_equal(crossing, horizontal | vertical))
        self.assertTrue(crossing[round(3900 - 4*300), round(100 + 4*450)])

    def test_curved_stroke_keeps_width_along_its_normals(self):
        image = self.render(0xE003)
        p0, p1, p2, p3 = (200, 200), (200, 500), (500, 500), (500, 200)
        for t in (0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875):
            u = 1 - t
            point = tuple(u**3*p0[a] + 3*u*u*t*p1[a] + 3*u*t*t*p2[a]
                          + t**3*p3[a] for a in (0, 1))
            tangent = tuple(3*u*u*(p1[a]-p0[a]) + 6*u*t*(p2[a]-p1[a])
                            + 3*t*t*(p3[a]-p2[a]) for a in (0, 1))
            norm = math.hypot(*tangent)
            normal = (-tangent[1]/norm, tangent[0]/norm)
            ink = [distance for distance in np.arange(-30, 30.125, 0.125)
                   if self.pixel(image, point[0] + normal[0]*distance,
                                 point[1] + normal[1]*distance) >= 128]
            self.assertAlmostEqual(max(ink) - min(ink), 40, delta=1.0)

    def test_closed_stroke_keeps_its_counter(self):
        image = self.render(0xE004)
        self.assertEqual(self.pixel(image, 450, 450), 0)
        self.assertGreater(self.pixel(image, 200, 450), 200)
        self.assertGreater(self.pixel(image, 200, 200), 200)

    def test_flattening_stays_within_source_unit_tolerance(self):
        points, _ = flatten_path("M 200 200 C 200 500 500 500 500 200")
        for t in np.linspace(0, 1, 257):
            u = 1 - t
            point = (200*u**3 + 600*u*u*t + 1500*u*t*t + 500*t**3,
                     200*u**3 + 1500*u*u*t + 1500*u*t*t + 200*t**3)
            distance = min(point_segment_distance(point, a, b)
                           for a, b in zip(points, points[1:]))
            self.assertLessEqual(distance, 0.1)

    def test_all_primitive_contours_share_clockwise_winding(self):
        font = TTFont(self.font_path)
        for name in font.getBestCmap().values():
            glyph = font["glyf"][name]
            self.assertTrue(glyph.flags[0] & 64)
            start = 0
            for end in glyph.endPtsOfContours:
                contour = glyph.coordinates[start:end + 1]
                area_twice = sum(a[0]*b[1] - b[0]*a[1]
                                 for a, b in zip(contour, [*contour[1:], contour[0]]))
                self.assertLess(area_twice, 0)
                start = end + 1

    def test_family_and_absolute_width_overrides(self):
        target = Path(self.workspace.name) / "redraw.ttf"
        sources = [{"codepoint": 0xE100 + index, "width": width,
                    "strokes": [flatten_path("M 200 300 L 700 300")]}
                   for index, width in enumerate((40, 88))]
        reports = build_font(sources, target, family="Panorama Gothic Seal Redraw",
                             font_stroke_width=43)
        self.assertEqual({record["stroke_width_font_units"] for record in reports.values()}, {43})
        reopened = TTFont(target)
        self.assertEqual(reopened["name"].getDebugName(1), "Panorama Gothic Seal Redraw")
        self.assertEqual(reopened["name"].getDebugName(6), "PanoramaGothicSealRedraw-Regular")
        self.assertEqual(list(reopened["glyf"]["u0E100"].coordinates),
                         list(reopened["glyf"]["u0E101"].coordinates))

    def test_strict_source_review_gate(self):
        directory = Path(self.workspace.name) / "review-gate"
        directory.mkdir(exist_ok=True)
        path = directory / "UE200.json"
        data = {"codepoint": "U+E200", "viewBox": [0, 0, 1024, 1024],
                "stroke_width": 43, "strokes": [{"path": "M 200 300 L 700 300"}]}
        path.write_text(json.dumps(data))
        self.assertEqual(len(load_sources(directory)), 1)
        with self.assertRaisesRegex(ValueError, "U\\+0E200"):
            load_sources(directory, require_visual_match=True)
        data["visual_reference_match_reviewed"] = True
        path.write_text(json.dumps(data))
        self.assertEqual(len(load_sources(directory, require_visual_match=True)), 1)


if __name__ == "__main__":
    unittest.main()
