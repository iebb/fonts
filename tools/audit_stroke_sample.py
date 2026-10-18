#!/usr/bin/env python3
"""Check font/source integrity and flag topology changes for visual review.

Pixel topology is a diagnostic, not a character-identity certification. Both
the native artwork and the actual font are sampled at the same 1024-em size.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import label


ROOT = Path(__file__).resolve().parents[1]


def topology(mask: np.ndarray) -> dict:
    # Eight-connectivity follows rounded ink at diagonal junctions. Four-
    # connected background distinguishes actual counters from diagonal gaps.
    components = label(mask, structure=np.ones((3, 3), dtype=np.uint8))[1]
    counters = label(np.pad(~mask, 1, constant_values=True))[1] - 1
    return {"components": int(components), "counters": int(counters)}


def audit(font_path: Path, source_dir: Path, manifest_path: Path, output: Path) -> dict:
    font = TTFont(font_path)
    manifest = json.loads(manifest_path.read_text())
    records = {int(g["codepoint"].removeprefix("U+"), 16): g for g in manifest["glyphs"]}
    cmap = font.getBestCmap()
    errors, glyphs, topology_flags = [], [], []
    if set(cmap) != set(records):
        errors.append("Font cmap and manifest repertoire differ")
    specimen = ImageFont.truetype(str(font_path), 1024)
    for cp in sorted(cmap):
        name = f"U{cp:05X}"
        source_path = source_dir / (name + ".png")
        digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        record = records[cp]
        if record.get("source", {}).get("sha256") != digest:
            errors.append(f"{name}: centerlines refer to a different PNG")
        centerline_path = ROOT / record["centerline_file"]
        if hashlib.sha256(centerline_path.read_bytes()).hexdigest() != record["centerline_sha256"]:
            errors.append(f"{name}: centerline source changed after font build")
        geometry = json.loads(centerline_path.read_text())
        geometry_hash = hashlib.sha256(json.dumps(
            {key: geometry[key] for key in ("viewBox", "stroke_width", "strokes")},
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        geometry_review = record.get("source", {}).get("geometry_reference_review", {})
        corrected_vector_reviewed = (geometry_review.get("verdict") == "match"
                                     and geometry_review.get("geometry_sha256") == geometry_hash)
        with Image.open(source_path) as native:
            if native.mode != "RGBA":
                errors.append(f"{name}: original source is not RGBA")
            alpha = native.convert("RGBA").getchannel("A")
            factor = 1024 / max(native.size)
            resized = alpha.resize(tuple(round(size * factor) for size in native.size), Image.Resampling.LANCZOS)
            source_image = Image.new("L", (1024, 1024))
            source_image.paste(resized, ((1024-resized.width)//2, (1024-resized.height)//2))
        # 32-pixel pad protects the topology check from edge clipping.
        rendered = Image.new("L", (1088, 1088))
        ImageDraw.Draw(rendered).text((32, 32 + 832), chr(cp), font=specimen, fill=255, anchor="ls")
        source_mask = np.pad(np.asarray(source_image) >= 128, 32)
        font_mask = np.asarray(rendered) >= 128
        source_topology, font_topology = topology(source_mask), topology(font_mask)
        if source_topology != font_topology:
            topology_flags.append(f"U+{cp:05X}")
        review = record.get("source", {}).get("visual_reference_review", {})
        # A manual override can preserve its independent review separately.
        independent_review = source_dir / "reviews" / (name + ".json")
        if independent_review.is_file():
            review = json.loads(independent_review.read_text())
            if review.get("source_png_sha256") != digest:
                errors.append(f"{name}: independent visual review is stale")
        verdict = review.get("verdict", "pending")
        if verdict in ("mismatch", "stale") and not corrected_vector_reviewed:
            errors.append(f"{name}: unresolved visual review {verdict}")
        glyphs.append({"codepoint": f"U+{cp:05X}", "source_sha256": digest,
                       "visual_review": "match_after_manual_correction" if corrected_vector_reviewed else verdict,
                       "native_artwork_visual_review": verdict,
                       "manual_structural_correction_reviewed": corrected_vector_reviewed,
                       "centerline_status": record["status"],
                       "stroke_width": record["stroke_width_font_units"],
                       "source_pixel_topology": source_topology,
                       "font_pixel_topology": font_topology,
                       "topology_changed": source_topology != font_topology})
    report = {
        "font": str(font_path), "font_sha256": hashlib.sha256(font_path.read_bytes()).hexdigest(),
        "glyph_count": len(cmap), "source_integrity_pass": not errors, "errors": errors,
        "stroke_widths": sorted({g["stroke_width"] for g in glyphs}),
        "visual_matches": sum(g["visual_review"] in ("match", "match_after_manual_correction") for g in glyphs),
        "manual_corrections": [g["codepoint"] for g in glyphs if g["manual_structural_correction_reviewed"]],
        "visual_review_pending_or_uncertain": [g["codepoint"] for g in glyphs
                                               if g["visual_review"] not in ("match", "match_after_manual_correction")],
        "pixel_topology_flags": topology_flags,
        "unexpected_pixel_topology_flags": [g["codepoint"] for g in glyphs
                                             if g["topology_changed"] and not g["manual_structural_correction_reviewed"]],
        "limitations": "Pixel topology flags require visual inspection; matching counts do not prove glyph identity.",
        "glyphs": glyphs,
    }
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, default=ROOT / "fonts/seal-individual/PanoramaGothicSealIndividual-Regular.ttf")
    parser.add_argument("--sources", type=Path, default=ROOT / "design/seal-individual")
    parser.add_argument("--output", type=Path, default=ROOT / "fonts/seal-individual/audit.json")
    args = parser.parse_args()
    report = audit(args.font, args.sources, args.font.parent / "manifest.json", args.output)
    print(json.dumps({k: v for k, v in report.items() if k != "glyphs"}, indent=2))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
