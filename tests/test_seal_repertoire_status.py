"""Progress must retain the full pinned goal and reject stale acceptance."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from seal_repertoire_status import status, write_atomic


class SealProgressTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.ucd = self.root / "reference/ucd-18"
        self.ucd.mkdir(parents=True)
        for name in ("Scripts.txt", "Blocks.txt"):
            (self.ucd / name).write_text("3D000..3FC3F ; Seal # the full draft repertoire\n")
        self.write_json(self.ucd / "snapshot.json", {
            "repository": "unicode-org/unicodetools", "commit": "fixture-pin",
            "version": "development fixture", "verified_utc": "2026-10-18",
            "files": [{"file": name, "sha256": self.digest((self.ucd / name).read_bytes())}
                      for name in ("Scripts.txt", "Blocks.txt")]})
        self.index = {"chart_sha256": "0" * 64,
                      "glyphs": {f"{cp:05X}": {"page": 2} for cp in range(0x3D000, 0x3FC40)}}
        self.index_path = self.root / "reference/seal/chart-index.json"
        self.write_json(self.index_path, self.index)
        self.registry = self.root / "design/quality/accepted-geometry.json"
        self.entries = []
        self.write_registry()

    @staticmethod
    def digest(data):
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def write_json(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def write_registry(self):
        self.write_json(self.registry, {"schema_version": 1, "coverage_eligible": False,
                                        "glyphs": self.entries})

    def test_candidate_geometry_counts_as_present_without_acceptance(self):
        self.drawing(0x3D080)
        source = self.root / "design/strokes-individual/auto/U3D080.json"
        candidate = source.parent.parent / "candidates/U3D080.json"
        candidate.parent.mkdir()
        source.rename(candidate)
        report = status(self.root)
        self.assertEqual(report["counts"]["centerline_present"], 1)
        self.assertEqual(report["counts"]["frozen_default_accepted"], 0)
        self.assertFalse(report["default_prototype_goal_complete"])

    def drawing(self, cp, accept=False):
        name = f"U{cp:05X}"
        native = self.root / f"design/seal-individual/{name}.png"
        native.parent.mkdir(parents=True, exist_ok=True)
        payload = f"native fixture {cp:X}".encode()
        native.write_bytes(payload)
        native_sha = self.digest(payload)
        ref = self.root / f"reference/seal/individual/{name}.png"
        ref.parent.mkdir(parents=True, exist_ok=True)
        ref.write_bytes(b"reference fixture")
        self.write_json(native.with_suffix(".json"), {
            "codepoint": f"U+{cp:05X}", "tool": "image_gen.imagegen", "prompt": "fixture only",
            "output_sha256": native_sha, "reference_sha256": self.digest(ref.read_bytes())})
        self.write_json(native.parent / f"reviews/{name}.json", {
            "verdict": "match", "source_png_sha256": native_sha})
        geometry = {"viewBox": [0, 0, 1024, 1024], "stroke_width": 43,
                    "strokes": [{"path": "M 200 300 L 700 300"}]}
        source = {"codepoint": f"U+{cp:05X}", **geometry, "source": {"sha256": native_sha},
                  "visual_reference_match_reviewed": True}
        centerline = self.root / f"design/strokes-individual/auto/{name}.json"
        self.write_json(centerline, source)
        if accept:
            self.entries.append({"codepoint": f"U+{cp:05X}", "source_png_sha256": native_sha,
                                 "geometry_sha256": self.digest(json.dumps(geometry, sort_keys=True,
                                                                          separators=(",", ":")).encode()),
                                 "review_report": "fixture-independent-review.json"})
            self.write_registry()
        return native, centerline

    def test_missing_last_chart_label_does_not_shrink_the_pinned_goal(self):
        self.index["glyphs"].pop("3FC3F")
        self.write_json(self.index_path, self.index)
        report = status(self.root)
        self.assertEqual(report["goal"]["codepoint_count"], 11328)
        self.assertEqual(report["goal"]["last"], "U+3FC3F")
        self.assertEqual(report["counts"]["reference_indexed"], 11327)
        self.assertEqual(report["unindexed_reference_ranges"], [["U+3FC3F", "U+3FC3F"]])
        self.assertFalse(report["default_prototype_goal_complete"])

    def test_drawings_and_review_flags_do_not_manufacture_acceptance(self):
        native, _ = self.drawing(0x3D000)
        provenance = json.loads(native.with_suffix(".json").read_text())
        provenance["code_point"] = provenance.pop("codepoint")  # retained historical schema
        self.write_json(native.with_suffix(".json"), provenance)
        report = status(self.root, full_worklist=True)
        self.assertEqual(report["counts"]["native_provenance_valid"], 1)
        self.assertEqual(report["counts"]["centerline_present"], 1)
        self.assertEqual(report["counts"]["frozen_default_accepted"], 0)
        self.assertEqual(report["worklist"][0]["state"], "awaiting_frozen_acceptance")
        self.assertFalse(report["semantics"]["coverage_eligible"])
        self.assertEqual(report["semantics"]["production_coverage_credit"], 0)

    def test_changed_actual_native_png_invalidates_frozen_entry(self):
        native, _ = self.drawing(0x3D000, accept=True)
        self.drawing(0x3D001, accept=True)
        native.write_bytes(b"changed native pixels")
        report = status(self.root, full_worklist=True)
        self.assertEqual(report["counts"]["frozen_default_accepted"], 1)
        self.assertEqual(report["counts"]["stale_registry_entry"], 1)
        self.assertFalse(report["worklist"][0]["native_provenance_valid"])
        self.assertEqual(report["worklist"][0]["state"], "stale_acceptance")
        self.assertEqual(report["next_unaccepted_batch"]["last"], "U+3D000")

    def test_withdrawn_review_invalidates_even_unchanged_frozen_geometry(self):
        _, centerline = self.drawing(0x3D000, accept=True)
        source = json.loads(centerline.read_text())
        source["visual_reference_match_reviewed"] = False
        self.write_json(centerline, source)
        report = status(self.root)
        self.assertEqual(report["counts"]["frozen_default_accepted"], 0)
        self.assertEqual(report["counts"]["stale_registry_entry"], 1)

    def test_completion_requires_provenance_and_pinned_reference_evidence(self):
        native, _ = self.drawing(0x3D000, accept=True)
        pdf = self.root / "reference/seal/U3D000.pdf"
        pdf.write_bytes(b"pinned chart fixture")
        self.index["chart_sha256"] = self.digest(pdf.read_bytes())
        self.write_json(self.index_path, self.index)
        # Exercise completion policy on a small evidence graph; production
        # pinned_goal independently enforces the full11328-point repertoire.
        with patch("seal_repertoire_status.pinned_goal", return_value=((0x3D000,), {})):
            self.assertTrue(status(self.root)["default_prototype_goal_complete"])
            provenance = json.loads(native.with_suffix(".json").read_text())
            provenance["tool"] = "unverified source"
            self.write_json(native.with_suffix(".json"), provenance)
            self.assertFalse(status(self.root)["default_prototype_goal_complete"])
            provenance["tool"] = "image_gen.imagegen"
            self.write_json(native.with_suffix(".json"), provenance)
            pdf.write_bytes(b"changed chart")
            self.assertFalse(status(self.root)["default_prototype_goal_complete"])
            pdf.write_bytes(b"pinned chart fixture")
            self.index["glyphs"].pop("3D000")
            self.write_json(self.index_path, self.index)
            self.assertFalse(status(self.root)["default_prototype_goal_complete"])

    def test_changed_effective_manual_geometry_invalidates_auto_acceptance(self):
        _, auto = self.drawing(0x3D000, accept=True)
        manual = auto.parent.parent / auto.name
        data = json.loads(auto.read_text())
        data["strokes"][0]["path"] = "M 200 300 L 900 300"
        self.write_json(manual, data)
        report = status(self.root)
        self.assertEqual(report["counts"]["frozen_default_accepted"], 0)
        self.assertEqual(report["counts"]["stale_registry_entry"], 1)

    def test_next_batch_stops_at_accepted_gap_and_reports_later_pending(self):
        self.drawing(0x3D000, accept=True)
        self.drawing(0x3D002, accept=True)
        report = status(self.root, batch_size=64)
        self.assertEqual(report["next_unaccepted_batch"]["first"], "U+3D001")
        self.assertEqual(report["next_unaccepted_batch"]["last"], "U+3D001")
        self.assertEqual(report["next_unaccepted_batch"]["count"], 1)
        self.assertEqual(report["stage_ranges"]["frozen_default_accepted"],
                         [["U+3D000", "U+3D000"], ["U+3D002", "U+3D002"]])

    def test_compact_persistent_report_has_no_full_worklist_by_default(self):
        self.drawing(0x3D000, accept=True)
        report = status(self.root)
        output = self.root / "progress.json"
        write_atomic(output, report)
        saved = json.loads(output.read_text())
        self.assertNotIn("worklist", saved)
        self.assertLess(output.stat().st_size, 16000)
        self.assertEqual(saved["counts"]["frozen_default_accepted"], 1)
        self.assertEqual(saved["evidence"]["ucd"]["last_external_verification_utc"], "2026-10-18")

    def test_changed_ucd_cannot_redefine_target_under_old_pin(self):
        (self.ucd / "Scripts.txt").write_text("3D000..3FC3E ; Seal\n")
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            status(self.root)


if __name__ == "__main__":
    unittest.main()
