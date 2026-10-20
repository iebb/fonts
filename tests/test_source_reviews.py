"""Check frozen acceptance independently of inherited native-image reviews."""

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_source_reviews import verify


class SourceReviewTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.sources = self.root / "sources"
        (self.sources / "auto").mkdir(parents=True)
        self.source_path = self.sources / "auto/U3D000.json"
        self.data = {
            "codepoint": "U+3D000",
            "viewBox": [0, 0, 1024, 1024],
            "stroke_width": 43,
            "strokes": [{"id": "bar", "path": "M 200 300 L 700 300"}],
            "visual_reference_match_reviewed": True,
            "source": {"sha256": "a" * 64},
        }
        self.write_source(self.data)
        geometry = {key: self.data[key] for key in ("viewBox", "stroke_width", "strokes")}
        digest = hashlib.sha256(json.dumps(geometry, sort_keys=True,
                                           separators=(",", ":")).encode()).hexdigest()
        self.entry = {"codepoint": "U+3D000", "geometry_sha256": digest,
                      "source_png_sha256": "a" * 64, "review_report": "review/U3D000.json"}
        self.registry = self.root / "accepted-geometry.json"
        self.write_registry([self.entry])

    def write_source(self, data, path=None):
        (path or self.source_path).write_text(json.dumps(data))

    def test_retracted_individual_review_invalidates_unchanged_geometry(self):
        review = self.root / "review.json"
        entry = {**self.entry, "review_report": str(review),
                 "review_format": "individual-regular400-v1"}
        decision = {**entry, "accepted": True, "regular400_verdict": "accepted",
                    "reviewed_weight": 400}
        review.write_text(json.dumps(decision))
        self.write_registry([entry])
        self.assertTrue(verify(self.sources, self.registry)["passed"])
        decision.update(accepted=False, regular400_verdict="needs_structural_repair")
        review.write_text(json.dumps(decision))
        result = verify(self.sources, self.registry)
        self.assertFalse(result["passed"])
        self.assertTrue(any("retracted" in error for error in result["errors"]))
        review.unlink()
        self.assertFalse(verify(self.sources, self.registry)["passed"])

    def write_registry(self, entries):
        self.registry.write_text(json.dumps({"schema_version": 1, "purpose": "Fixture review",
                                             "glyphs": entries}))

    def test_accepted_source_passes_and_reports_registry_fingerprint(self):
        before = self.registry.read_bytes()
        result = verify(self.sources, self.registry)
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["glyph_count"], 1)
        self.assertEqual(result["registry_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(self.registry.read_bytes(), before)

    def test_path_mutation_fails_even_with_native_visual_flag_true(self):
        self.data["strokes"][0]["path"] = "M 200 300 L 750 300"
        self.write_source(self.data)
        result = verify(self.sources, self.registry)
        self.assertFalse(result["passed"])
        self.assertTrue(any("geometry_sha256 mismatch" in error for error in result["errors"]))
        self.assertTrue(self.data["visual_reference_match_reviewed"])

    def test_changed_source_png_fingerprint_fails(self):
        self.data["source"]["sha256"] = "b" * 64
        self.write_source(self.data)
        result = verify(self.sources, self.registry)
        self.assertFalse(result["passed"])
        self.assertTrue(any("source_png_sha256 mismatch" in error for error in result["errors"]))

    def test_extra_source_codepoint_fails(self):
        extra = copy.deepcopy(self.data)
        extra["codepoint"] = "U+3D001"
        self.write_source(extra, self.sources / "auto/U3D001.json")
        result = verify(self.sources, self.registry)
        self.assertFalse(result["passed"])
        self.assertIn("Registry missing codepoints: U+3D001", result["errors"])

    def test_extra_registry_codepoint_fails(self):
        extra = {**self.entry, "codepoint": "U+3D001"}
        self.write_registry([self.entry, extra])
        result = verify(self.sources, self.registry)
        self.assertFalse(result["passed"])
        self.assertIn("Registry has extra codepoints: U+3D001", result["errors"])

    def test_unreviewed_source_fails_existing_review_gate(self):
        self.data["visual_reference_match_reviewed"] = False
        self.write_source(self.data)
        result = verify(self.sources, self.registry)
        self.assertFalse(result["passed"])
        self.assertTrue(any("Source review gate failed" in error for error in result["errors"]))

    def test_stale_manual_review_fails_even_when_registry_matches_geometry(self):
        self.data["source"]["geometry_reference_review"] = {
            "verdict": "match", "geometry_sha256": "0" * 64,
        }
        self.write_source(self.data)
        result = verify(self.sources, self.registry)
        self.assertFalse(result["passed"])
        self.assertTrue(any("manual geometry review is stale" in error for error in result["errors"]))

    def test_manual_override_uses_the_effective_source(self):
        self.write_source(self.data, self.sources / "U3D000.json")
        self.data["strokes"][0]["path"] = "M 200 300 L 999 300"
        self.data["visual_reference_match_reviewed"] = False
        self.write_source(self.data)
        result = verify(self.sources, self.registry)
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(Path(result["glyphs"][0]["source"]), self.sources / "U3D000.json")

    def test_cli_failure_exits_one_and_writes_report_without_changing_registry(self):
        self.data["source"]["sha256"] = "b" * 64
        self.write_source(self.data)
        registry_before = self.registry.read_bytes()
        output = self.root / "reports/check.json"
        tool = Path(__file__).resolve().parents[1] / "tools/verify_source_reviews.py"
        process = subprocess.run([sys.executable, str(tool), "--source-root", str(self.sources),
                                  "--registry", str(self.registry), "--output", str(output)],
                                 capture_output=True, text=True)
        self.assertEqual(process.returncode, 1, process.stderr)
        self.assertFalse(json.loads(process.stdout)["passed"])
        self.assertEqual(json.loads(output.read_text()), json.loads(process.stdout))
        self.assertEqual(self.registry.read_bytes(), registry_before)


if __name__ == "__main__":
    unittest.main()
