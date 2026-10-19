#!/usr/bin/env python3
"""Package the reviewed Small Seal prototype and its editable sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from fontTools.ttLib import TTFont

from verify_source_reviews import ROOT, verify


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(output: Path | None = None, allow_unverified_browser: bool = False) -> dict:
    registry_path = ROOT / "design/quality/accepted-geometry.json"
    registry = json.loads(registry_path.read_text())
    source_check = verify(ROOT / "design/strokes-individual", registry_path)
    if not source_check["passed"]:
        raise ValueError(source_check["errors"])
    expected = {int(g["codepoint"].removeprefix("U+"), 16) for g in registry["glyphs"]}
    for glyph in registry["glyphs"]:
        cp = int(glyph["codepoint"].removeprefix("U+"), 16)
        assert sha(ROOT / f"design/seal-individual/U{cp:05X}.png") == glyph["source_png_sha256"]
    directories = [ROOT / "fonts/seal-individual", ROOT / "fonts/seal-individual-variable"]
    font_names = ["PanoramaGothicSealIndividual-Regular.ttf", "PanoramaGothicSealIndividualVariable.ttf"]
    for directory, font_name in zip(directories, font_names):
        font_path = directory / font_name
        with TTFont(font_path) as font:
            assert set(font.getBestCmap()) == expected, "Packaged repertoire differs from reviewed sources"
        for name in ("invariants-check.json", "size-check.json"):
            report = json.loads((directory / name).read_text())
            assert report.get("passed", report.get("pass")) is True, (directory, name)
            assert report["font_sha256"] == sha(font_path), (directory, name, "stale")
            if name == "invariants-check.json":
                assert report["specification_sha256"] == sha(ROOT / "design/quality/invariants.json")
            else:
                assert report["repertoire"]["sha256"] == sha(registry_path)
                assert report["manifest_source_comparison"]["sha256"] == sha(directory / "manifest.json")
        manifest = json.loads((directory / "manifest.json").read_text())
        for item in manifest["files"]:
            assert sha(directory / item["name"]) == item["sha256"], item["name"]
        for glyph in manifest.get("glyphs", manifest.get("sources", [])):
            source_sha = glyph.get("centerline_sha256", glyph.get("sha256"))
            assert sha(ROOT / glyph["centerline_file"]) == source_sha, glyph["codepoint"]
        report = json.loads((directory / "source-review-check.json").read_text())
        assert report["passed"] and report["registry_sha256"] == sha(registry_path)
    previews = json.loads((directories[0] / "preview-manifest.json").read_text())
    assert previews["font_sha256"] == sha(directories[0] / font_names[0])
    for item in previews["files"]:
        assert sha(directories[0] / item["name"]) == item["sha256"]
    optics = json.loads((directories[1] / "optical-review.json").read_text())
    assert optics["font_sha256"] == sha(directories[1] / font_names[1])
    assert optics["review_report_sha256"] == sha(ROOT / optics["review_report"])
    audit = json.loads((directories[0] / "audit.json").read_text())
    assert audit["source_integrity_pass"] and audit["font_sha256"] == sha(directories[0] / font_names[0])
    # Native raster and a normalized constant-width drawing can differ in pixel
    # topology. Every flagged drawing must have an independent, exact-geometry
    # compiled-font review; matching topology counts alone never approve it.
    reviewed = {}
    for path in (ROOT / "design/quality").glob("recheck-*.json"):
        data = json.loads(path.read_text())
        glyphs = data.get("glyphs", [])
        if not isinstance(glyphs, list):
            continue
        for glyph in glyphs:
            if (glyph.get("status", "").startswith("accepted_")
                    and glyph.get("font_geometry_verdict", "").startswith("match")):
                reviewed[glyph["codepoint"]] = glyph
    accepted = {g["codepoint"]: g for g in registry["glyphs"]}
    for cp in audit["unexpected_pixel_topology_flags"]:
        review = reviewed.get(cp, {})
        assert review.get("canonical_geometry_sha256") == accepted[cp]["geometry_sha256"], cp
        assert review.get("actual_font_proofs"), (cp, "missing actual-font review")
    browser = json.loads((directories[1] / "browser-check.json").read_text())
    assert browser["font_sha256"] == sha(directories[1] / font_names[1])
    assert browser["glyph_count"] == len(expected)
    assert browser["html_sha256"] == sha(directories[1] / "weight-slider.html")
    playback = json.loads((directories[0] / "browser-check.json").read_text())
    assert playback["html_sha256"] == sha(directories[0] / "stroke-playback.html")
    browser_blocked = browser.get("status") == "blocked_by_environment"
    if browser_blocked:
        assert allow_unverified_browser, "Browser verification is blocked; use the explicit packaging exception"
        assert playback.get("status") == "blocked_by_environment" and browser.get("reason")
    else:
        assert browser["embedded_variable_font_loaded"] and not browser["javascript_errors"]
        assert not playback["javascript_errors"] and playback["replay_animations"] == 4
    files = set()
    for directory in directories:
        files.update(p for p in directory.rglob("*") if p.is_file())
    for name in ("design/seal-individual", "design/strokes-individual"):
        files.update(p for p in (ROOT / name).rglob("*")
                     if p.is_file() and p.suffix in (".png", ".json", ".svg")
                     and "inspection" not in p.parts and "-inspection-white" not in p.name)
    files.update((ROOT / "design/quality").glob("*.json"))
    files.add(ROOT / "design/quality/README.md")
    files.update(ROOT / name for name in ("README.md", "Makefile", "requirements.txt", "requirements-tracing.txt",
                 "fonts/noto/PanoramaGothic-Regular.ttf", "licenses/noto/OFL-1.1.txt",
                 "fonts/seal-example/LICENSE-OFL.txt", "fonts/seal-example/OFL-1.1.txt"))
    files.update((ROOT / "tools").glob("*.py"))
    files.update((ROOT / "tests").glob("test_stroke*.py"))
    files.update(ROOT / "tests" / name for name in ("test_glyph_invariants.py", "test_source_reviews.py"))
    output = output or ROOT / f"dist/Panorama-Gothic-Seal-Stroke-{len(expected)}.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    inventory = []
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        def write(name: str, content: bytes) -> None:
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 19, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
        for path in sorted(files):
            name = path.relative_to(ROOT).as_posix()
            content = path.read_bytes()
            write(name, content)
            inventory.append({"name": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        write("package-manifest.json", (json.dumps({"prototype": True, "coverage_eligible": False,
              "glyph_count": len(expected), "version": "0.6",
              "browser_verification": {"status": "blocked_by_environment" if browser_blocked else "passed",
                                       "reason": browser.get("reason") if browser_blocked else None},
              "files": inventory}, indent=2) + "\n").encode())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for item in inventory:
            assert hashlib.sha256(archive.read(item["name"])).hexdigest() == item["sha256"]
    return {"archive": str(output), "files": len(inventory) + 1,
            "bytes": output.stat().st_size, "sha256": sha(output)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-unverified-browser", action="store_true",
                        help="Package an explicitly recorded browser environment limitation; keep font checks mandatory")
    arguments = parser.parse_args()
    print(json.dumps(package(arguments.output, arguments.allow_unverified_browser), indent=2))
