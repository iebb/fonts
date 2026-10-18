"""Topology tests: independent strokes must survive centerline reconstruction."""

from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from track_centerlines import extract_strokes, fit_centerline, track_single_images


def drawing(lines):
    image = Image.new("L", (101, 101))
    pen = ImageDraw.Draw(image)
    for line in lines:
        pen.line(line, fill=255, width=9)
    return np.asarray(image) > 128


class CenterlineTests(unittest.TestCase):
    def test_crossing_is_two_independent_continuous_strokes(self):
        strokes, topology = extract_strokes(drawing([[(12, 50), (88, 50)], [(50, 12), (50, 88)]]))
        self.assertEqual(len(strokes), 2)
        self.assertEqual(len(topology["junctions"]), 1)
        self.assertEqual(topology["junctions"][0]["degree"], 4)
        self.assertEqual(len(topology["junctions"][0]["continuations"]), 2)
        displacements = sorted(tuple(np.abs(np.asarray(stroke["points"][-1]) - stroke["points"][0])) for stroke in strokes)
        self.assertLess(displacements[0][0], 2)
        self.assertGreater(displacements[0][1], 60)
        self.assertGreater(displacements[1][0], 60)
        self.assertLess(displacements[1][1], 2)

    def test_separated_lines_are_not_connected(self):
        strokes, topology = extract_strokes(drawing([[(12, 25), (88, 25)], [(12, 75), (88, 75)]]))
        self.assertEqual(len(strokes), 2)
        self.assertEqual(topology["junctions"], [])
        for stroke in strokes:
            self.assertLess(np.ptp(np.asarray(stroke["points"])[:, 1]), 2)

    def test_y_branch_is_not_forced_to_an_invented_continuation(self):
        mask = drawing([[(50, 52), (50, 90)], [(50, 52), (17, 33)], [(50, 52), (83, 33)]])
        strokes, topology = extract_strokes(mask)
        self.assertEqual(len(strokes), 3)
        self.assertEqual(len(topology["junctions"]), 1)
        joint = topology["junctions"][0]
        self.assertEqual(joint["degree"], 3)
        self.assertEqual(joint["continuations"], [])
        self.assertEqual(joint["unpaired_branches"], 3)
        for stroke in strokes:
            # Every tracked sample lies in the actual connected ink; no link
            # may jump between physically separated branches.
            for x, y in stroke["points"]:
                self.assertTrue(mask[round(y), round(x)])

    def test_cubic_fit_is_smooth_and_bounded(self):
        values = np.linspace(0, np.pi / 2, 100)
        points = np.column_stack((10 + 40 * np.cos(values), 10 + 40 * np.sin(values))).tolist()
        curve = fit_centerline(points)
        self.assertLessEqual(curve["maximum_fit_error"], 1)
        self.assertIn(" C ", curve["path"])
        self.assertNotIn("Z", curve["path"])
        self.assertLess(curve["curve_segments"], 10)

    def test_individual_tracking_normalizes_and_caches_without_changing_native_png(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, output = Path(temporary) / "sources", Path(temporary) / "auto"
            source.mkdir()
            image = Image.new("RGBA", (626, 626))
            ImageDraw.Draw(image).line([(100, 313), (526, 313)], fill="black", width=27)
            native = source / "U3D000.png"
            image.save(native)
            (source / "U3D000.json").write_text(json.dumps({"reference_evidence": ["THX", "CCZ", "QJZ", "DYC"],
                                                         "prompt": "all four reference specimens", "review_status": "unreviewed"}))
            digest = hashlib.sha256(native.read_bytes()).hexdigest()
            result = track_single_images(source, output, count=2, incremental=True)
            self.assertEqual(result["updated"], ["U+3D000"])
            self.assertEqual(result["pending"], ["U+3D001"])
            record = json.loads((output / "U3D000.json").read_text())
            self.assertEqual(record["viewBox"], [0, 0, 1024, 1024])
            self.assertEqual(record["stroke_width"], 43)
            self.assertEqual(record["source"]["generation_review"]["reference_evidence"], ["THX", "CCZ", "QJZ", "DYC"])
            self.assertFalse(record["character_identity_verified"])
            self.assertGreater(record["strokes"][0]["points"][-1][0], 800)
            modified = (output / "U3D000.json").stat().st_mtime_ns
            second = track_single_images(source, output, count=1, incremental=True)
            self.assertEqual(second["unchanged"], ["U+3D000"])
            self.assertEqual((output / "U3D000.json").stat().st_mtime_ns, modified)
            self.assertEqual(hashlib.sha256(native.read_bytes()).hexdigest(), digest)
            # A later visual review must invalidate cached provenance without
            # requiring a change to the immutable generated artwork.
            (source / "reviews").mkdir()
            (source / "reviews/U3D000.json").write_text(json.dumps({
                "verdict": "match", "source_png_sha256": digest,
            }))
            reviewed = track_single_images(source, output, count=1, incremental=True)
            self.assertEqual(reviewed["updated"], ["U+3D000"])
            record = json.loads((output / "U3D000.json").read_text())
            self.assertTrue(record["visual_reference_match_reviewed"])
            self.assertFalse(record["character_identity_verified"])
            self.assertEqual(hashlib.sha256(native.read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
