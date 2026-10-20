#!/usr/bin/env python3
"""Monitor the pinned Small Seal goal without promoting drawings to acceptance.

The frozen registry certifies reviewed prototype geometry at default Regular400;
it does not grant production coverage. This command reads local evidence only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from verify_source_reviews import review_report_agrees


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SEAL_COUNT = 11328
STAGES = ("reference_indexed", "reference_overview_ready", "native_png_present", "native_provenance_valid",
          "centerline_present", "registry_listed", "frozen_default_accepted",
          "stale_registry_entry", "native_review_match", "native_review_mismatch",
          "native_review_uncertain", "native_review_stale", "native_review_pending")


def sha256(path: Path) -> str:
    # Stream native drawings and the chart rather than retaining their pixels.
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def codepoint(value: str | int) -> int:
    return int(value.removeprefix("U+").removeprefix("U"), 16) if isinstance(value, str) else value


def label(cp: int) -> str:
    return f"U+{cp:05X}"


def ranges(values) -> list[list[str]]:
    result = []
    for cp in sorted(values):
        if result and cp == codepoint(result[-1][1]) + 1:
            result[-1][1] = label(cp)
        else:
            result.append([label(cp), label(cp)])
    return result


def property_points(path: Path, name: str) -> set[int]:
    points = set()
    for line in path.read_text().splitlines():
        body = line.split("#", 1)[0].strip()
        if not body:
            continue
        interval, prop = (part.strip() for part in body.split(";", 1))
        if prop != name:
            continue
        ends = interval.split("..")
        first, last = int(ends[0], 16), int(ends[-1], 16)
        points.update(range(first, last + 1))
    return points


def pinned_goal(ucd: Path) -> tuple[tuple[int, ...], dict]:
    snapshot_path = ucd / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text())
    actual = {}
    for record in snapshot["files"]:
        path = ucd / record["file"]
        digest = sha256(path)
        if digest != record["sha256"]:
            raise ValueError(f"Pinned UCD fingerprint mismatch: {path}")
        actual[record["file"]] = digest
    for required in ("Scripts.txt", "Blocks.txt"):
        if required not in actual:
            raise ValueError(f"Snapshot lacks fingerprint for {required}")
    script, block = property_points(ucd / "Scripts.txt", "Seal"), property_points(ucd / "Blocks.txt", "Seal")
    if script != block or len(script) != EXPECTED_SEAL_COUNT:
        raise ValueError("Pinned Scripts/Blocks must agree on exactly 11328 Seal codepoints")
    points = tuple(sorted(script))
    if points != tuple(range(points[0], points[-1] + 1)):
        raise ValueError("Pinned Seal repertoire is no longer one contiguous range")
    return points, {"snapshot": str(snapshot_path), "snapshot_sha256": sha256(snapshot_path),
                    "repository": snapshot["repository"], "commit": snapshot["commit"],
                    "version": snapshot["version"], "last_external_verification_utc": snapshot.get("verified_utc"),
                    "local_file_fingerprints_verified": actual,
                    "freshness": "Cached pin; no network freshness verification performed by this command."}


def named_files(directory: Path, suffix: str) -> dict[int, Path]:
    result = {}
    for path in directory.glob(f"U*{suffix}"):
        match = re.fullmatch(r"U([0-9A-Fa-f]{4,6})" + re.escape(suffix), path.name)
        if match:
            result[int(match[1], 16)] = path
    return result


def geometry_sha256(data: dict) -> str:
    return hashlib.sha256(json.dumps({key: data[key] for key in ("viewBox", "stroke_width", "strokes")},
                                    sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_object(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def next_batch(points: tuple[int, ...], accepted: set[int], size: int) -> dict | None:
    if size < 1:
        raise ValueError("Batch size must be positive")
    first = next((cp for cp in points if cp not in accepted), None)
    if first is None:
        return None
    batch = []
    for cp in range(first, min(first + size, points[-1] + 1)):
        if cp in accepted:
            break
        batch.append(cp)
    return {"first": label(batch[0]), "last": label(batch[-1]), "count": len(batch),
            "reason": "First contiguous unaccepted run, bounded by batch size and accepted gaps."}


def status(root: Path = ROOT, batch_size: int = 64, full_worklist: bool = False) -> dict:
    root = Path(root)
    points, pin = pinned_goal(root / "reference/ucd-18")
    target = set(points)
    index_path, pdf = root / "reference/seal/chart-index.json", root / "reference/seal/U3D000.pdf"
    index_bytes = index_path.read_bytes()
    index = json.loads(index_bytes)
    indexed = {codepoint(cp) for cp in index["glyphs"]}
    registry_path = root / "design/quality/accepted-geometry.json"
    registry_bytes = registry_path.read_bytes()
    registry = json.loads(registry_bytes)
    if registry.get("schema_version") != 1 or not isinstance(registry.get("glyphs"), list):
        raise ValueError("Acceptance registry must use schema_version1 with a glyphs list")
    entries = {}
    for entry in registry["glyphs"]:
        cp = codepoint(entry["codepoint"])
        if cp in entries or cp not in target:
            raise ValueError(f"Duplicate/out-of-repertoire registry entry: {label(cp)}")
        if any(not re.fullmatch(r"[0-9a-f]{64}", str(entry.get(field, "")))
               for field in ("geometry_sha256", "source_png_sha256")) or not entry.get("review_report"):
            raise ValueError(f"Invalid frozen registry fingerprints/review: {label(cp)}")
        entries[cp] = entry
    native_dir, source_dir = root / "design/seal-individual", root / "design/strokes-individual"
    native, provenance = named_files(native_dir, ".png"), named_files(native_dir, ".json")
    centerlines = {**named_files(source_dir / "candidates", ".json"),
                   **named_files(source_dir / "auto", ".json"), **named_files(source_dir, ".json")}
    reviews = named_files(native_dir / "reviews", ".json")
    references = named_files(root / "reference/seal/individual", ".png")
    reference_metadata = named_files(root / "reference/seal/individual", ".json")
    stage_points, states, worklist, issues = defaultdict(list), Counter(), [], []
    accepted = set()
    for cp in points:
        flags = {stage: False for stage in STAGES}
        flags.update(reference_indexed=cp in indexed, native_png_present=cp in native,
                     reference_overview_ready=cp in references and cp in reference_metadata,
                     centerline_present=cp in centerlines, registry_listed=cp in entries)
        problems, data, prov, native_sha = [], {}, {}, None
        if cp in native:
            native_sha = sha256(native[cp])
            try:
                prov = read_object(provenance[cp])
                recorded = [prov[key] for key in ("output_sha256", "sha256", "original_generated_sha256") if key in prov]
                identifiers = [prov[key] for key in ("codepoint", "code_point") if key in prov]
                valid = (bool(identifiers) and all(codepoint(value) == cp for value in identifiers)
                         and prov.get("tool") == "image_gen.imagegen"
                         and bool(prov.get("full_prompt") or prov.get("prompt"))
                         and bool(recorded) and all(value == native_sha for value in recorded)
                         and prov.get("source_pixels_modified") is not True
                         and prov.get("original_pixels_unchanged") is not False
                         and cp in references and prov.get("reference_sha256") == sha256(references[cp]))
                if prov.get("reference_metadata_sha256"):
                    valid &= (cp in reference_metadata and
                              sha256(reference_metadata[cp]) == prov["reference_metadata_sha256"])
                flags["native_provenance_valid"] = bool(valid)
                if not valid:
                    problems.append("Native provenance/PNG/reference fingerprints do not agree")
            except (KeyError, ValueError, TypeError, OSError) as error:
                prov = {}
                problems.append(f"Missing/invalid native provenance: {error}")
        source_sha, geometry = None, None
        if cp in centerlines:
            try:
                data = read_object(centerlines[cp])
                if codepoint(data["codepoint"]) != cp or not data["strokes"]:
                    raise ValueError("Centerline codepoint differs or strokes are empty")
                source_sha, geometry = sha256(centerlines[cp]), geometry_sha256(data)
            except (KeyError, ValueError, TypeError, OSError) as error:
                problems.append(f"Invalid centerline source: {error}")
        review = prov.get("visual_review", {})
        if cp in reviews:
            try:
                review = read_object(reviews[cp])
            except (ValueError, OSError) as error:
                review = {}
                problems.append(f"Invalid native review: {error}")
        verdict = review.get("verdict", "pending") if isinstance(review, dict) else "pending"
        if isinstance(review, dict) and review and review.get("source_png_sha256") != native_sha:
            verdict = "stale"
        if verdict not in ("match", "mismatch", "uncertain", "stale"):
            verdict = "pending"
        flags[f"native_review_{verdict}"] = True
        entry = entries.get(cp)
        geometry_review = data.get("source", {}).get("geometry_reference_review")
        source_review_current = data.get("visual_reference_match_reviewed") is True
        if geometry_review:
            source_review_current &= (geometry_review.get("verdict") == "match"
                                      and geometry_review.get("geometry_sha256") == geometry)
        review_agrees = not entry or review_report_agrees(entry, root)
        frozen = bool(entry and native_sha and geometry and review_agrees
                      and source_review_current
                      and entry["geometry_sha256"] == geometry
                      and entry["source_png_sha256"] == native_sha
                      and data.get("source", {}).get("sha256") == native_sha)
        flags["frozen_default_accepted"] = frozen
        flags["stale_registry_entry"] = bool(entry and not frozen)
        if frozen:
            accepted.add(cp)
            state = "frozen_default_accepted"
        elif entry:
            state = "stale_acceptance"
            problems.append("Frozen acceptance requires matching native/geometry fingerprints and a current source review gate")
        elif cp not in native:
            state = "awaiting_native"
        elif not flags["native_provenance_valid"]:
            state = "invalid_native_provenance"
        elif cp not in centerlines:
            state = "awaiting_centerlines"
        elif verdict in ("mismatch", "uncertain", "stale"):
            state = "awaiting_geometry_review_with_native_" + verdict
        else:
            state = "awaiting_frozen_acceptance"
        states[state] += 1
        for stage, enabled in flags.items():
            if enabled:
                stage_points[stage].append(cp)
        if problems:
            issues.append({"codepoint": label(cp), "issues": problems})
        if full_worklist:
            worklist.append({"codepoint": label(cp), "state": state, **flags,
                             "native_png_sha256": native_sha, "centerline_sha256": source_sha,
                             "canonical_geometry_sha256": geometry, "issues": problems})
    pdf_sha = sha256(pdf) if pdf.exists() else None
    report = {"schema_version": 1, "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "goal": {"script": "Seal", "block": "Seal", "first": label(points[0]), "last": label(points[-1]),
                       "codepoint_count": len(points), "derived_from": "Matching pinned Scripts.txt and Blocks.txt"},
              "semantics": {"accepted": "Frozen prototype geometry at default Regular400; actual geometry/native hashes match registry.",
                            "native_artwork_mismatch_may_have_accepted_vector_correction": True,
                            "native_provenance_is_separate_from_frozen_geometry_acceptance": True,
                            "all_variable_weights_certified": False, "coverage_eligible": False,
                            "production_coverage_credit": 0},
              "evidence": {"ucd": pin, "registry": {"path": str(registry_path), "sha256": hashlib.sha256(registry_bytes).hexdigest()},
                           "chart": {"index": str(index_path), "index_sha256": hashlib.sha256(index_bytes).hexdigest(),
                                     "url": index.get("chart_url"), "recorded_pdf_sha256": index.get("chart_sha256"),
                                     "actual_pdf_sha256": pdf_sha,
                                     "pdf_fingerprint_verified": pdf_sha is not None and pdf_sha == index.get("chart_sha256")}},
              "counts": {stage: len(stage_points[stage]) for stage in STAGES},
              "workflow_counts": dict(sorted(states.items())),
              "stage_ranges": {stage: ranges(stage_points[stage]) for stage in STAGES},
              "unindexed_reference_ranges": ranges(target - indexed),
              "next_unaccepted_batch": next_batch(points, accepted, batch_size),
              "default_prototype_goal_complete": (len(accepted) == len(points)
                   and target <= indexed
                   and pdf_sha is not None and pdf_sha == index.get("chart_sha256")
                   and len(stage_points["native_provenance_valid"]) == len(points)),
              "issue_count": len(issues), "issues": issues[:50], "issues_truncated": len(issues) > 50}
    if full_worklist:
        report["worklist"] = worklist
    return report


def write_atomic(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--full-worklist", action="store_true", help="Include every target codepoint; default report uses compact ranges")
    args = parser.parse_args()
    output = args.output or args.root / "design/quality/small-seal-progress.json"
    protected = [args.root / "design/quality/accepted-geometry.json", args.root / "reference/seal/chart-index.json",
                 *(args.root / "reference/ucd-18").glob("*")]
    protected_roots = [args.root / "reference", args.root / "design/seal-individual",
                       args.root / "design/strokes-individual"]
    if (output.resolve() in {path.resolve() for path in protected}
            or any(output.resolve().is_relative_to(path.resolve()) for path in protected_roots)):
        parser.error("Progress output cannot overwrite registry, chart index or pinned UCD evidence")
    try:
        report = status(args.root, args.batch_size, args.full_worklist)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Cannot assess Small Seal progress: {error}\n")
    write_atomic(output, report)
    count, total, batch = report["counts"]["frozen_default_accepted"], report["goal"]["codepoint_count"], report["next_unaccepted_batch"]
    next_label = f"{batch['first']}–{batch['last']} ({batch['count']})" if batch else "none"
    print(f"{count}/{total} frozen prototype glyphs accepted at Regular400; next {next_label}. Report: {output}")


if __name__ == "__main__":
    main()
