"""Parallel review proofs must bind immutable source snapshots to real fonts."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.ttLib import TTFont
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from prepare_seal_review import prepare


class SealReviewProofTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        native = self.root / "design/seal-individual/U3D080.png"
        native.parent.mkdir(parents=True)
        Image.new("RGBA", (32, 32), (0, 0, 0, 0)).save(native)
        self.native_sha = hashlib.sha256(native.read_bytes()).hexdigest()
        self.source = self.root / "design/strokes-individual/candidates/U3D080.json"
        self.source.parent.mkdir(parents=True)
        self.data = {"codepoint": "U+3D080", "viewBox": [0, 0, 1024, 1024],
                     "stroke_width": 43, "source": {"sha256": self.native_sha},
                     "strokes": [{"path": "M 200 300 L 700 300"}]}
        self.source.write_text(json.dumps(self.data))
        self.output = self.root / "proof"

    def test_snapshot_survives_later_candidate_edits(self):
        report = prepare([0x3D080], self.output, self.root)
        snapshot = self.output / "sources/U3D080.json"
        snapshot_bytes = snapshot.read_bytes()
        self.source.write_text("changed during subsequent worker pass")
        self.assertEqual(snapshot.read_bytes(), snapshot_bytes)
        self.assertEqual(report["glyphs"][0]["source_png_sha256"], self.native_sha)
        with TTFont(report["font"]) as font:
            self.assertIn(0x3D080, font.getBestCmap())
        image = Image.open(report["glyphs"][0]["raster"]).convert("L")
        self.assertLess(image.getextrema()[0], 20)

    def test_stale_source_fails_before_creating_output(self):
        self.data["source"]["sha256"] = "0" * 64
        self.source.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, "differ"):
            prepare([0x3D080], self.output, self.root)
        self.assertFalse(self.output.exists())

    def test_existing_proof_cannot_be_overwritten(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "preserve"):
            prepare([0x3D080], self.output, self.root)

    def test_duplicates_and_outside_block_are_rejected(self):
        for points in ([0x3D080, 0x3D080], [0x41]):
            with self.assertRaises(ValueError):
                prepare(points, self.output, self.root)


if __name__ == "__main__":
    unittest.main()
