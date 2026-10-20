"""Verify centerline sources against an independently reviewed, frozen registry.

This tool never creates or updates the acceptance registry. A changed source
must be reviewed before its fingerprint is deliberately added to that registry.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from build_stroke_font import ROOT, codepoint_number, load_sources


def geometry_sha256(data: dict) -> str:
    """Use the same canonical fields and encoding as manual geometry reviews."""
    geometry = {key: data[key] for key in ("viewBox", "stroke_width", "strokes")}
    return hashlib.sha256(json.dumps(geometry, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def review_report_agrees(entry: dict, root: Path = ROOT) -> bool:
    """A retracted individual review cannot leave its geometry accepted.

    Historical range reports retain their original format. New individual
    reviews explicitly bind the verdict, weight and source fingerprints.
    """
    required = entry.get("review_format") == "individual-regular400-v1"
    path = Path(root) / entry["review_report"]
    if not path.exists():
        return not required
    try:
        review = json.loads(path.read_text())
        if not required and "regular400_verdict" not in review:
            return True
        return (review.get("accepted") is True
                and review.get("regular400_verdict") == "accepted"
                and review.get("reviewed_weight") == 400
                and codepoint_number(review["codepoint"]) == codepoint_number(entry["codepoint"])
                and review.get("geometry_sha256") == entry["geometry_sha256"]
                and review.get("source_png_sha256") == entry["source_png_sha256"])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def verify(source_root: Path, registry_path: Path) -> dict:
    source_root, registry_path = Path(source_root), Path(registry_path)
    report = {
        "passed": False,
        "source_root": str(source_root),
        "registry": str(registry_path),
        "registry_sha256": None,
        "glyph_count": 0,
        "glyphs": [],
        "errors": [],
    }
    errors = report["errors"]
    try:
        registry_bytes = registry_path.read_bytes()
        report["registry_sha256"] = hashlib.sha256(registry_bytes).hexdigest()
        registry = json.loads(registry_bytes)
    except (OSError, ValueError) as error:
        errors.append(f"Cannot read acceptance registry: {error}")
        return report
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        errors.append("Acceptance registry must use schema_version 1")
        return report
    if not isinstance(registry.get("glyphs"), list):
        errors.append("Acceptance registry must contain a glyphs list")
        return report

    accepted = {}
    for index, entry in enumerate(registry["glyphs"]):
        if not isinstance(entry, dict):
            errors.append(f"Registry glyph {index} must be an object")
            continue
        try:
            codepoint = codepoint_number(entry["codepoint"])
        except (KeyError, ValueError, TypeError, AttributeError) as error:
            errors.append(f"Registry glyph {index} has an invalid codepoint: {error}")
            continue
        label = f"U+{codepoint:05X}"
        if codepoint in accepted:
            errors.append(f"Registry has duplicate codepoint {label}")
            continue
        accepted[codepoint] = entry
        for field in ("geometry_sha256", "source_png_sha256"):
            value = entry.get(field)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                errors.append(f"{label}: registry {field} must be a lowercase SHA-256")
        if not isinstance(entry.get("review_report"), str) or not entry["review_report"].strip():
            errors.append(f"{label}: registry review_report must identify its review")

    try:
        # Keep the existing reviewed-boolean and matching manual-hash gates.
        # The independent registry below also covers automatically traced sources.
        sources = load_sources(source_root, require_visual_match=True)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        errors.append(f"Source review gate failed: {error}")
        return report

    current = {source["codepoint"]: source for source in sources}
    report["glyph_count"] = len(current)
    missing = sorted(current.keys() - accepted.keys())
    extra = sorted(accepted.keys() - current.keys())
    if missing:
        errors.append("Registry missing codepoints: "
                      + ", ".join(f"U+{value:05X}" for value in missing))
    if extra:
        errors.append("Registry has extra codepoints: "
                      + ", ".join(f"U+{value:05X}" for value in extra))

    for codepoint, source in sorted(current.items()):
        label = f"U+{codepoint:05X}"
        data = source["data"]
        digest = geometry_sha256(data)
        source_png_sha = data.get("source", {}).get("sha256")
        entry = accepted.get(codepoint)
        report["glyphs"].append({
            "codepoint": label,
            "source": str(source["path"]),
            "geometry_sha256": digest,
            "source_png_sha256": source_png_sha,
            "accepted_geometry_sha256": entry.get("geometry_sha256") if entry else None,
            "accepted_source_png_sha256": entry.get("source_png_sha256") if entry else None,
            "review_report": entry.get("review_report") if entry else None,
        })
        if entry is None:
            continue
        if not review_report_agrees(entry):
            errors.append(f"{label}: individual review is missing, retracted or stale")
        if digest != entry.get("geometry_sha256"):
            errors.append(f"{label}: geometry_sha256 mismatch; "
                          f"current {digest}, accepted {entry.get('geometry_sha256')}")
        if source_png_sha != entry.get("source_png_sha256"):
            errors.append(f"{label}: source_png_sha256 mismatch; "
                          f"current {source_png_sha}, accepted {entry.get('source_png_sha256')}")

    report["passed"] = not errors
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT / "design/strokes-individual")
    parser.add_argument("--registry", type=Path, default=ROOT / "design/quality/accepted-geometry.json")
    parser.add_argument("--output", type=Path, help="Write the verification report as JSON")
    arguments = parser.parse_args()
    report = verify(arguments.source_root, arguments.registry)
    if arguments.output:
        if arguments.output.resolve() == arguments.registry.resolve():
            report["errors"].append("The verification report cannot overwrite its acceptance registry")
            report["passed"] = False
        else:
            try:
                arguments.output.parent.mkdir(parents=True, exist_ok=True)
                arguments.output.write_text(json.dumps(report, indent=2) + "\n")
            except OSError as error:
                report["errors"].append(f"Cannot write verification report: {error}")
                report["passed"] = False
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
