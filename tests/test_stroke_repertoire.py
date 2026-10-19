"""Expanded specimens must not silently skip the new end of the repertoire."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_stroke_font import build_font
from build_stroke_variable import build_variable
from render_stroke_font import render as render_specimen
from render_weight_demo import render as render_weights, repertoire_label
from verify_normalized_sizes import verify


class StrokeRepertoireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory()
        cls.root = Path(cls.workspace.name)
        cls.codepoints = tuple(range(0x3D000, 0x3D080))
        cls.sources = [{"codepoint": cp, "width": 30,
                        "strokes": [([(143, 320), (881, 320)], False)]}
                       for cp in cls.codepoints]
        cls.full = cls.root / "full.ttf"
        cls.missing = cls.root / "missing.ttf"
        build_font(cls.sources, cls.full, font_stroke_width=30)
        build_font(cls.sources[:-1], cls.missing, font_stroke_width=30)
        cls.legacy = cls.root / "legacy" / "legacy.ttf"
        cls.legacy.parent.mkdir()
        build_font(cls.sources[:64], cls.legacy, font_stroke_width=30)

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def manifest(self, path, codepoints=None):
        records = [{"codepoint": f"U+{cp:05X}", "normalization": {
            "matrix_font_units": [1, 0, 0, 1, 0, 0],
            "original_centerline_bounds_font_units": [143, 320, 881, 320],
            "preserve_aspect_ratio": True, "pen_width_scaled": False,
            "target_centerline_extent": 738}}
            for cp in (self.codepoints if codepoints is None else codepoints)]
        data = {"glyph_count": len(records), "glyphs": records,
                "files": [{"name": path.name,
                           "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]}
        (path.parent / "manifest.json").write_text(json.dumps(data))

    def test_matching_manifest_checks_all_128_actual_glyphs(self):
        self.manifest(self.full)
        report = verify(self.full)
        self.assertTrue(report["pass"], report)
        self.assertEqual(report["repertoire"]["source"], "hash-matched font manifest")
        self.assertEqual(report["glyph_checks"], 128)

    def test_unmanifested_64_character_fixture_keeps_original_default(self):
        report = verify(self.legacy)
        self.assertTrue(report["pass"], report)
        self.assertEqual(report["repertoire"]["source"], "64-character fallback")
        self.assertEqual(report["glyph_checks"], 64)

    def test_missing_128th_glyph_fails_even_with_hash_matching_manifest(self):
        self.manifest(self.missing)
        report = verify(self.missing)
        self.assertFalse(report["pass"])
        self.assertEqual(report["glyph_checks"], 128)
        failure = report["instances"][0]["glyphs"][-1]
        self.assertEqual(failure["codepoint"], "U+3D07F")
        self.assertIn("Missing cmap entry", failure["errors"])

    def test_frozen_registry_catches_shortened_font_and_manifest(self):
        self.manifest(self.missing, self.codepoints[:-1])
        registry = self.root / "accepted.json"
        registry.write_text(json.dumps({"schema_version": 1,
                                       "glyphs": [{"codepoint": f"U+{cp:05X}"}
                                                  for cp in self.codepoints]}))
        report = verify(self.missing, registry_path=registry)
        self.assertFalse(report["pass"])
        self.assertEqual(report["repertoire"]["glyph_count"], 128)
        self.assertIn("U+3D07F", report["manifest_source_comparison"]["missing_codepoints"])

    def test_preview_keeps_first64_and_renders_new128th_glyph(self):
        output = self.root / "preview"
        report = render_specimen(self.full, output)
        previews = {item["name"]: item for item in report["previews"]}
        self.assertEqual(previews["preview-128.png"]["glyph_count"], 128)
        self.assertEqual(previews["preview-128.png"]["codepoints"][-1], "U+3D07F")
        self.assertEqual(previews["preview-64.png"]["glyph_count"], 64)
        self.assertEqual(previews["preview-64.png"]["codepoints"][-1], "U+3D03F")
        second_page = previews["preview-3D040-3D07F.png"]
        self.assertEqual((second_page["codepoints"][0], second_page["codepoints"][-1]),
                         ("U+3D040", "U+3D07F"))
        self.assertTrue((output / "preview-128.png").is_file())
        self.assertTrue((output / "preview-64.png").is_file())

    def test_weight_slider_displays_actual_128_character_repertoire(self):
        source = self.root / "variable-source"
        source.mkdir()
        (source / "U3D000.json").write_text(json.dumps({
            "codepoint": "U+3D000", "viewBox": [0, 0, 1024, 1024], "stroke_width": 43,
            "strokes": [{"path": "M 143 512 L 881 512"}]}))
        output = self.root / "variable"
        build_variable(source, output, "Repertoire Fixture")
        path = output / "RepertoireFixture.ttf"
        # Aliases suffice to test rendering membership; this fixture does not
        # claim that its repeated bar represents 128 Small Seal identities.
        with TTFont(path) as font:
            name = font.getBestCmap()[0x3D000]
            for table in font["cmap"].tables:
                if table.isUnicode() and table.format == 12:
                    table.cmap = {cp: name for cp in self.codepoints}
            font.save(path)
        render_weights(path, output, ROOT / "fonts/noto/PanoramaGothic-Regular.ttf")
        html = (output / "weight-slider.html").read_text()
        self.assertEqual(html.count('<span title="U+'), 128)
        self.assertIn('<span title="U+3D07F">', html)
        self.assertIn("128-character design prototype · U+3D000–U+3D07F", html)
        self.assertEqual(repertoire_label([0x3D000, 0x3D001, 0x3D007]),
                         "U+3D000–U+3D001, U+3D007")


if __name__ == "__main__":
    unittest.main()
