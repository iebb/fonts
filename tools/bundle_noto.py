#!/usr/bin/env python3
"""Package separate, renamed Noto Sans faces without sacrificing shaping.

The installed Regular fonts are the reproducible inputs. No outlines are
merged, rescaled, synthesized, or replaced. A single Japanese CJK face is
extracted from the collection, preserving all of its 65,535 glyphs. CSS assigns
each supported character to one source face; the full original cmaps and
OpenType layout tables remain in the installable fonts.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
from pathlib import Path

import fontTools
from fontTools.ttLib import TTFont


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
PRESERVED_NAME_IDS = {0, 7, 8, 9, 10, 11, 12, 13, 14}
IDENTITY_NAME_IDS = {1, 2, 3, 4, 6, 16, 17, 18, 21, 22, 25}
DEFAULT_TTF_DIR = Path("/usr/share/fonts/truetype/noto")
DEFAULT_CJK_FILE = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    """Use portable repository-relative paths, allowing external input files."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def ranges(codepoints: set[int]) -> list[str]:
    """Compact, exact, inclusive hexadecimal ranges, without U+ prefixes."""
    result: list[str] = []
    ordered = sorted(codepoints)
    if not ordered:
        return result
    start = previous = ordered[0]
    for cp in ordered[1:]:
        if cp != previous + 1:
            result.append(f"{start:04X}" if start == previous else f"{start:04X}-{previous:04X}")
            start = cp
        previous = cp
    result.append(f"{start:04X}" if start == previous else f"{start:04X}-{previous:04X}")
    return result


def read_assigned(path: Path) -> set[int]:
    """Read drawable assigned characters, including UnicodeData intervals."""
    assigned: set[int] = set()
    first: tuple[int, str, str] | None = None
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        fields = line.split(";")
        if len(fields) < 3:
            raise ValueError(f"{path}:{number}: invalid UnicodeData record")
        cp, name, category = int(fields[0], 16), fields[1], fields[2]
        if name.endswith(", First>"):
            if first is not None:
                raise ValueError(f"{path}:{number}: nested UnicodeData interval")
            first = cp, category, name[:-8]
            continue
        if name.endswith(", Last>"):
            if first is None or first[1:] != (category, name[:-7]) or cp < first[0]:
                raise ValueError(f"{path}:{number}: invalid UnicodeData interval")
            span = range(first[0], cp + 1)
            first = None
        else:
            if first is not None:
                raise ValueError(f"{path}:{number}: unterminated UnicodeData interval")
            span = [cp]
        if category not in EXCLUDED_CATEGORIES:
            assigned.update(x for x in span if 0 <= x <= 0x10FFFF and not 0xD800 <= x <= 0xDFFF)
    if first is not None:
        raise ValueError(f"{path}: unterminated UnicodeData interval")
    return assigned


def metadata(font: TTFont) -> list[dict]:
    return [
        {"id": n.nameID, "platform": n.platformID, "encoding": n.platEncID,
         "language": n.langID, "text": n.toUnicode()}
        for n in font["name"].names
    ]


def rename(font: TTFont, family: str, postscript: str) -> None:
    """Rename every language/platform identity; retain notices and attribution."""
    table = font["name"]
    version = table.getDebugName(5) or "Version 1.000"
    values = {
        1: family, 2: "Regular", 3: f"{version};PanoramaGothic;{postscript}",
        4: f"{family} Regular", 6: postscript, 16: family, 17: "Regular",
        18: f"{family} Regular", 21: family, 22: "Regular", 25: postscript.removesuffix("-Regular"),
    }
    for record in list(table.names):
        if record.nameID in IDENTITY_NAME_IDS:
            table.setName(values[record.nameID], record.nameID, record.platformID,
                          record.platEncID, record.langID)
    for name_id in (1, 2, 3, 4, 6, 16, 17):
        table.setName(values[name_id], name_id, 3, 1, 0x409)
    if "CFF " in font:
        cff = font["CFF "].cff
        cff.fontNames = [postscript]
        top = cff.topDictIndex[0]
        top.FamilyName = family
        top.FullName = f"{family} Regular"
        if hasattr(top, "FontName"):
            top.FontName = postscript


def codepoints(font: TTFont) -> set[int]:
    """Count real cmap mappings, never a .notdef diagnostic mapping."""
    return {cp for cp, glyph in (font.getBestCmap() or {}).items()
            if glyph != ".notdef" and font.getGlyphID(glyph) != 0
            and 0 <= cp <= 0x10FFFF and not 0xD800 <= cp <= 0xDFFF}


def verify(source: TTFont, output: Path, original_names: list[dict]) -> dict:
    """Check all source glyphs, cmaps, notices, and untouched binary tables."""
    with TTFont(output, lazy=True, recalcTimestamp=False) as bundled:
        if source.getGlyphOrder() != bundled.getGlyphOrder():
            raise ValueError(f"{output}: original glyph order changed")
        if source.getBestCmap() != bundled.getBestCmap():
            raise ValueError(f"{output}: cmap changed")
        if source["maxp"].numGlyphs != bundled["maxp"].numGlyphs:
            raise ValueError(f"{output}: glyph count changed")
        if set(source.keys()) != set(bundled.keys()):
            raise ValueError(f"{output}: table set changed")
        preserved = sorted(set(source.keys()) - {"GlyphOrder", "name", "head", "CFF "})
        for tag in preserved:
            # Compare the original file bytes, not a decompile/recompile result.
            if source.reader[tag] != bundled.reader[tag]:
                raise ValueError(f"{output}: source {tag!r} table changed")
        notices = [n for n in original_names if n["id"] in PRESERVED_NAME_IDS]
        actual_notices = [n for n in metadata(bundled) if n["id"] in PRESERVED_NAME_IDS]
        if notices != actual_notices:
            raise ValueError(f"{output}: original attribution/license metadata changed")
        if "CFF " in source:
            old = source["CFF "].cff.topDictIndex[0].CharStrings
            new = bundled["CFF "].cff.topDictIndex[0].CharStrings
            for glyph in source.getGlyphOrder():
                if old[glyph].bytecode != new[glyph].bytecode:
                    raise ValueError(f"{output}: CFF drawing changed for {glyph}")
        return {"original_glyph_order_preserved": True, "original_cmap_preserved": True,
                "copyright_and_license_preserved": True, "unchanged_tables": preserved,
                "all_glyph_outlines_preserved": True}


def local_versions() -> dict:
    versions = {"python": platform.python_version(), "fonttools": fontTools.__version__}
    for package in ("brotli", "uharfbuzz", "freetype-py"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    if shutil.which("dpkg-query"):
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Package}\t${Version}\n", "fonts-noto-core", "fonts-noto-cjk"],
            text=True, capture_output=True, check=False,
        )
        versions["system_font_packages"] = dict(line.split("\t", 1)
                                                for line in result.stdout.splitlines() if "\t" in line)
    return versions


def copy_licenses(destination: Path, copyright_dir: Path) -> list[dict]:
    """Retain package notices and a standalone, complete OFL text."""
    destination.mkdir(parents=True, exist_ok=True)
    results = []
    documents: dict[str, str] = {}
    for package in ("fonts-noto-core", "fonts-noto-cjk"):
        source = copyright_dir / package / "copyright"
        if not source.is_file():
            raise FileNotFoundError(f"Required Noto copyright/license source missing: {source}")
        target = destination / f"{package}-copyright.txt"
        shutil.copyfile(source, target)
        documents[package] = source.read_text(encoding="utf-8")
        results.append({"file": display_path(target), "sha256": sha256(target),
                        "source": str(source), "source_sha256": sha256(source)})
    text = documents["fonts-noto-cjk"]
    start = text.index("License: SIL-1.1\n") + len("License: SIL-1.1\n")
    # The first occurrence is the Files stanza; the license body follows later.
    start = text.index("License: SIL-1.1\n", start) + len("License: SIL-1.1\n")
    body = text[start:text.index("\nLicense: GPL-3+", start)]
    license_text = "\n".join("" if line == " ." else line.removeprefix(" ")
                             for line in body.splitlines()).strip() + "\n"
    if "PERMISSION & CONDITIONS" not in license_text or "DISCLAIMER" not in license_text:
        raise ValueError("Incomplete OFL license text in installed package")
    target = destination / "OFL-1.1.txt"
    target.write_text(license_text, encoding="utf-8")
    results.append({"file": display_path(target), "sha256": sha256(target),
                    "source": "OFL text from fonts-noto-cjk copyright file"})
    return results


def build(args: argparse.Namespace) -> dict:
    unicode_data = args.unicode_data.resolve()
    assigned = read_assigned(unicode_data)
    args.output.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    license_dir = ROOT / "licenses" / "noto"
    licenses = copy_licenses(license_dir, args.copyright_dir)
    candidates = [(p, None) for p in sorted(args.ttf_dir.glob("NotoSans*-Regular.ttf"))
                  if not any(part in p.name for part in ("Display", "Mono", "Condensed"))]
    if not candidates or candidates[0][0].name != "NotoSans-Regular.ttf":
        raise ValueError("Required main NotoSans-Regular.ttf input missing")
    candidates.append((args.cjk_file, args.cjk_face))
    faces, skipped, owned = [], [], set()
    source_hashes: dict[Path, str] = {}
    css = ["/* Panorama Gothic: preserved Noto Sans Regular faces; SIL OFL 1.1.",
           " * Keep licenses/noto and coverage/noto-manifest.json with this bundle.",
           " * Source cmaps and shaping tables are intact; unicode-range is disjoint.",
           " * Common marks belong to their first face. For a script-specific mark",
           " * sequence, install/select that face's internal family directly. */", ""]
    attribution = ["Panorama Gothic — Noto Sans baseline attribution", "",
                   "These separately installable fonts are renamed derivatives of Noto Sans.",
                   "Only identity metadata is changed; no source glyph or shaping table is replaced.",
                   "The CJK JP face is extracted from NotoSansCJK-Regular.ttc.",
                   "Each output remains licensed under the SIL Open Font License, Version 1.1.",
                   "The original copyright, author, designer, trademark, and license name records",
                   "are preserved in every font and reproduced in full below and in the manifest.",
                   "No endorsement by the original contributors is implied.",
                   "Upstream: https://github.com/notofonts/noto-fonts", 
                   "CJK upstream: https://github.com/notofonts/noto-cjk", ""]
    for path, face_index in candidates:
        with TTFont(path, fontNumber=face_index if face_index is not None else -1,
                    lazy=True, recalcTimestamp=False) as source:
            cmap_cps = codepoints(source)
            eligible = cmap_cps & assigned
            novel = eligible - owned
            if not novel:
                skipped.append({"source": str(path), "face_index": face_index,
                                "reason": "No additional drawable assigned codepoints"})
                continue
            names = metadata(source)
            original_family = source["name"].getDebugName(16) or source["name"].getDebugName(1)
            original_postscript = source["name"].getDebugName(6)
            if face_index is not None and original_family != "Noto Sans CJK JP":
                raise ValueError(f"Expected Noto Sans CJK JP; got {original_family}")
            suffix = "CJKJP" if face_index is not None else path.stem.removeprefix("NotoSans").removesuffix("-Regular")
            script_label = original_family.removeprefix("Noto Sans").strip()
            family = "Panorama Gothic" + (f" {script_label}" if script_label else "")
            postscript = f"PanoramaGothic{suffix}-Regular"
            extension = ".otf" if "CFF " in source else ".ttf"
            output = args.output / f"{postscript}{extension}"
            preserved_hashes = {tag: hashlib.sha256(source.reader[tag]).hexdigest()
                                for tag in ("GSUB", "GPOS", "GDEF") if tag in source}
            # Open a second lazy handle: the verification source stays unmodified.
            with TTFont(path, fontNumber=face_index if face_index is not None else -1,
                        lazy=True, recalcTimestamp=False) as target:
                rename(target, family, postscript)
                target.save(output, reorderTables=False)
            checks = verify(source, output, names)
            owned.update(novel)
            source_hashes.setdefault(path, sha256(path))
            entry = {
                "file": display_path(output), "sha256": sha256(output),
                "bytes": output.stat().st_size, "family": family,
                "postscript_name": postscript, "style": "Regular", "license": "OFL-1.1",
                "source": str(path), "source_sha256": source_hashes[path],
                "source_collection_face_index": face_index,
                "source_family": original_family, "source_postscript_name": original_postscript,
                "source_name_records": names, "glyph_count": source["maxp"].numGlyphs,
                "source_cmap_count": len(cmap_cps), "source_cmap_ranges": ranges(cmap_cps),
                "drawable_assigned_count": len(eligible), "drawable_assigned_ranges": ranges(eligible),
                "css_codepoint_count": len(novel), "css_codepoint_ranges": ranges(novel),
                "preserved_layout_table_sha256": preserved_hashes, "verification": checks,
            }
            faces.append(entry)
            css.extend([
                f"/* {family}: {len(novel):,} additional assigned codepoints. */",
                "@font-face {", '  font-family: "Panorama Gothic";',
                f'  src: url("./{output.name}") format("{"opentype" if extension == ".otf" else "truetype"}");',
                "  font-style: normal;", "  font-weight: 400;", "  font-display: swap;",
                "  unicode-range: " + ", ".join("U+" + r for r in ranges(novel)) + ";", "}", "",
            ])
            attribution.extend([f"{output.name}", f"Source: {path.name}" +
                                (f", collection face {face_index}" if face_index is not None else ""),
                                f"Source SHA-256: {source_hashes[path]}"])
            for record in names:
                if record["id"] in PRESERVED_NAME_IDS:
                    attribution.append(f"Name {record['id']} (platform {record['platform']}, "
                                       f"encoding {record['encoding']}, language {record['language']}): "
                                       f"{record['text']}")
            attribution.append("")
            print(f"{output.name}: {len(novel):,} assigned codepoints, {entry['glyph_count']:,} glyphs", flush=True)
    css_path = args.output / "panorama-gothic-noto.css"
    css_path.write_text("\n".join(css), encoding="utf-8")
    attribution_path = license_dir / "ATTRIBUTION.txt"
    attribution_path.write_text("\n".join(attribution), encoding="utf-8")
    codepoint_path = args.output / "codepoints.txt"
    codepoint_path.write_text(
        "# Exact assigned graphic Noto baseline; UCD hash is in manifest.json.\n" +
        "".join(f"U+{cp:04X}\n" for cp in sorted(owned)), encoding="utf-8",
    )
    manifest = {
        "schema": 1, "family": "Panorama Gothic", "license": "OFL-1.1",
        "description": "Independent, complete Noto Sans Regular faces, renamed without outline or shaping changes.",
        "unicode_data": {"file": display_path(unicode_data), "sha256": sha256(unicode_data)},
        "excluded_css_categories": sorted(EXCLUDED_CATEGORIES), "libraries": local_versions(),
        "face_count": len(faces), "bytes": sum(f["bytes"] for f in faces),
        "css_codepoint_count": len(owned), "css_codepoint_ranges": ranges(owned),
        "css_file": display_path(css_path), "codepoint_file": display_path(codepoint_path), "faces": faces,
        "skipped_redundant_or_variant_fonts": skipped, "licenses": licenses,
        "attribution_file": display_path(attribution_path),
        "limitations": [
            "Unicode ranges describe the supplied snapshot, not all Unicode 19 draft characters.",
            "This baseline contains no generated diagnostic or unassigned-character placeholders.",
            "Shared combining characters use the first selected face in the CSS union. Select a script-specific internal family for sequences requiring its shared-mark shaping.",
            "Only Japanese CJK regional forms are bundled. Use a regional CJK source when other locale-specific forms are required.",
        ],
    }
    manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    args.manifest.write_text(manifest_text, encoding="utf-8")
    (args.output / "manifest.json").write_text(manifest_text, encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ttf-dir", type=Path, default=DEFAULT_TTF_DIR)
    parser.add_argument("--cjk-file", type=Path, default=DEFAULT_CJK_FILE)
    parser.add_argument("--cjk-face", type=int, default=0)
    parser.add_argument("--unicode-data", type=Path, default=ROOT / "reference" / "ucd" / "UnicodeData.txt")
    parser.add_argument("--copyright-dir", type=Path, default=Path("/usr/share/doc"))
    parser.add_argument("--output", type=Path, default=ROOT / "fonts" / "noto")
    parser.add_argument("--manifest", type=Path, default=ROOT / "coverage" / "noto-manifest.json")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.manifest = args.manifest.resolve()
    manifest = build(args)
    print(f"Bundled {manifest['face_count']} faces, {manifest['css_codepoint_count']:,} assigned codepoints, "
          f"{manifest['bytes'] / (1024 * 1024):.1f} MiB.")


if __name__ == "__main__":
    main()
