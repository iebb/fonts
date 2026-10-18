"""Check tracing topology and actual TrueType rasterization of a hole."""

import hashlib
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

from tools.trace_generated_glyphs import signed_area, simplify_contour, smooth_contour, trace_boundaries, trace_generated_glyphs, trace_sheets


class ContourTests(unittest.TestCase):
    def test_outer_and_hole_boundaries_have_opposite_winding_and_exact_area(self):
        mask = [[True] * 5 for _ in range(5)]
        for y in range(1, 4):
            for x in range(1, 4):
                mask[y][x] = False
        contours = trace_boundaries(mask)
        self.assertEqual([-9, 25], sorted(signed_area(contour) for contour in contours))
        self.assertEqual(16, sum(signed_area(contour) for contour in contours))
        self.assertEqual([-9, 25], sorted(signed_area(simplify_contour(contour)) for contour in contours))

    def test_diagonal_pixels_remain_two_closed_contours(self):
        contours = trace_boundaries([[True, False], [False, True]])
        self.assertEqual(2, len(contours))
        self.assertEqual([1, 1], [signed_area(contour) for contour in contours])

    def test_curved_contour_receives_a_bounded_cubic_fit(self):
        image = Image.new("L", (48, 20), 0)
        ImageDraw.Draw(image).ellipse((2, 3, 45, 16), fill=255)
        pixels = image.load()
        original = trace_boundaries([[pixels[x, y] > 0 for x in range(image.width)] for y in range(image.height)])[0]
        fitted = smooth_contour(simplify_contour(original), original)
        self.assertTrue(fitted["smoothed"])
        self.assertLessEqual(fitted["measured_error"], 0.60)
        self.assertTrue(any(len(command) == 3 for command in fitted["commands"]))

    def test_mapped_sheets_merge_astral_cmaps_and_produce_font_proofs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = []
            for index in range(2):
                image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
                draw = ImageDraw.Draw(image)
                if index:
                    draw.ellipse((3, 3, 16, 16), fill=(0, 0, 0, 255))
                else:
                    draw.rectangle((3, 3, 16, 16), fill=(0, 0, 0, 255))
                source = root / f"sheet{index}.png"
                image.save(source)
                sources.append((0x3D000 + index, source))
            output = root / "example"
            manifest = trace_sheets(sources, output, root / "retained", columns=1, rows=1)
            self.assertEqual(2, manifest["codepoint_count"])
            self.assertFalse(manifest["coverage_eligible"])
            with TTFont(output / manifest["font"]["file"]) as font:
                self.assertEqual({0x3D000, 0x3D001}, set(font.getBestCmap()))
                self.assertTrue(all(font["hmtx"][name][0] == 1024 for name in font.getBestCmap().values()))
                self.assertEqual("Panorama Gothic Seal Example", font["name"].getDebugName(1))
            self.assertGreater((output / "specimen.png").stat().st_size, 1000)
            self.assertTrue((output / "specimen.pdf").read_bytes().startswith(b"%PDF-"))

    def test_font_has_a_real_hole_and_source_png_bytes_are_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "immutable.png"
            image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.rectangle((2, 2, 13, 13), fill=(0, 0, 0, 255))
            draw.rectangle((6, 6, 9, 9), fill=(0, 0, 0, 0))
            draw.point((0, 0), fill=(0, 0, 0, 255))
            image.save(source)
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            output, retained = root / "font", root / "original-copy.png"
            manifest = trace_generated_glyphs(source, output, retained, start=0xE000, rows=1, columns=1)
            self.assertFalse(manifest["coverage_eligible"])
            self.assertEqual(original_hash, hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(source.read_bytes(), retained.read_bytes())
            self.assertEqual(1, manifest["glyphs"][0]["removed_tiny_contours"])
            self.assertEqual(1, manifest["glyphs"][0]["holes"])
            font_path = output / manifest["font"]["file"]
            with TTFont(font_path) as font:
                name = font.getBestCmap()[0xE000]
                self.assertEqual(2, font["glyf"][name].numberOfContours)
                self.assertEqual(1024, font["hmtx"][name][0])
                self.assertIn("experimental", font["name"].getDebugName(10).lower())
            raster = Image.new("L", (1024, 1024), 255)
            draw = ImageDraw.Draw(raster)
            draw.text((0, 832), chr(0xE000), font=ImageFont.truetype(str(font_path), 1024), fill=0, anchor="ls")
            self.assertEqual(0, raster.getpixel((200, 200)))
            self.assertEqual(255, raster.getpixel((512, 512)))


if __name__ == "__main__":
    unittest.main()
