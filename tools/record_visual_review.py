#!/usr/bin/env python3
"""Record a manually performed structural comparison without modifying artwork."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def record(codepoint: int, verdict: str, notes: list[str], root: Path = ROOT,
           reviewer: str = "independent visual structural review by stroke_font_engine") -> Path:
    if verdict not in ("match", "uncertain", "mismatch"):
        raise ValueError("Verdict must be match, uncertain, or mismatch")
    stem = f"U{codepoint:05X}"
    source = root / "design/seal-individual" / f"{stem}.png"
    reference = root / "reference/seal/individual" / f"{stem}.png"
    reference_data = json.loads(reference.with_suffix(".json").read_text())
    report = {
        "schema_version": 1, "codepoint": f"U+{codepoint:05X}", "verdict": verdict,
        "reviewer": reviewer,
        "notes": notes,
        "source_png": str(source.relative_to(root)),
        "source_png_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "reference_overview": str(reference.relative_to(root)),
        "reference_png_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
        "reviewed_specimens": [name for name, data in reference_data["variants"].items()
                               if data["available"]],
        "unavailable_specimens": [name for name, data in reference_data["variants"].items()
                                  if not data["available"]],
        "limitations": [
            "Visual comparison against the supplied chart raster; not specialist paleographic certification.",
            "Does not verify historical writing order, exact metrics, or final font stroke width.",
            "Verdict applies only to the source PNG hash recorded here.",
        ],
    }
    inspection = root / "design/seal-individual/inspection" / f"{stem}-white.png"
    if inspection.exists():
        report["inspection_file"] = str(inspection.relative_to(root))
    output = root / "design/seal-individual/reviews" / f"{stem}.json"
    output.parent.mkdir(exist_ok=True)
    if output.exists():
        previous = json.loads(output.read_text())
        history = previous.get("previous_reviews", [])
        if (previous.get("source_png_sha256"), previous.get("verdict")) != (report["source_png_sha256"], verdict):
            history.append({key: previous.get(key) for key in
                            ("source_png_sha256", "verdict", "notes", "reference_png_sha256")})
        if history:
            report["previous_reviews"] = history
    output.write_text(json.dumps(report, indent=2) + "\n")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("codepoint", type=lambda value: int(value.removeprefix("U+").removeprefix("U"), 16))
    parser.add_argument("verdict", choices=("match", "uncertain", "mismatch"))
    parser.add_argument("--note", action="append", required=True)
    parser.add_argument("--reviewer", default="independent visual structural review")
    args = parser.parse_args()
    print(record(args.codepoint, args.verdict, args.note, reviewer=args.reviewer))


if __name__ == "__main__":
    main()
