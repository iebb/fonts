#!/usr/bin/env python3
"""Render one private four-source comparison image per Unicode character.

Each image contains only THX, CCZ, QJZ, and DYC specimens for that codepoint;
unavailable chart specimens stay explicitly marked. Interleaving sixteen-code
workers makes each worker's first reference available before the next pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import fitz

from prepare_multi_references import ROOT, parse_codepoint, render_overview


def interleaved_codepoints(start: int, count: int):
    for offset in range(16):
        for base in range(start, start + count, 16):
            codepoint = base + offset
            if codepoint < start + count:
                yield codepoint


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=ROOT / "reference/seal/U3D000.pdf")
    parser.add_argument("--index", type=Path, default=ROOT / "reference/seal/consensus/chart-index.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reference/seal/individual")
    parser.add_argument("--start", type=parse_codepoint, default=0x3D000)
    parser.add_argument("--count", type=int, default=64)
    parser.add_argument("--skip", type=int, default=0)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    index = json.loads(args.index.read_text())
    if index["chart_sha256"] != hashlib.sha256(args.pdf.read_bytes()).hexdigest():
        parser.error("Cached index does not match the supplied chart PDF")
    codepoints = list(interleaved_codepoints(args.start, args.count))[args.skip:]
    if args.limit is not None:
        codepoints = codepoints[:args.limit]
    args.output.mkdir(parents=True, exist_ok=True)
    with fitz.open(args.pdf) as document:
        for codepoint in codepoints:
            path = args.output / f"U{codepoint:05X}.png"
            render_overview(args.pdf, index, codepoint, path, document=document)
            print(path, flush=True)


if __name__ == "__main__":
    main()
