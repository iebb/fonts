#!/usr/bin/env python3
"""Assemble a private comparison figure; source artwork stays byte-for-byte intact."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]


def render(codepoints: list[int], output: Path):
    # Each row keeps the complete four-reference overview and adds the new
    # drawing on white. Resizing affects only this separate review figure.
    figure = Image.new("RGB", (2120, 520*len(codepoints)), "white")
    draw = ImageDraw.Draw(figure)
    label = ImageFont.truetype(str(ROOT / "fonts/noto/PanoramaGothic-Regular.ttf"), 25)
    for row, codepoint in enumerate(codepoints):
        stem = f"U{codepoint:05X}"
        reference = Image.open(ROOT / "reference/seal/individual" / f"{stem}.png").convert("RGB")
        figure.paste(reference, (0, row*520))
        source = Image.open(ROOT / "design/seal-individual" / f"{stem}.png").convert("RGBA")
        white = Image.new("RGBA", source.size, "white")
        white.alpha_composite(source)
        white = white.convert("RGB")
        white.thumbnail((430, 430), Image.Resampling.LANCZOS)
        figure.paste(white, (1645 + (430-white.width)//2,
                            row*520 + 75 + (430-white.height)//2))
        draw.text((1860, row*520 + 32), "New drawing", fill="#333333", font=label, anchor="mt")
        draw.line((1600, row*520 + 15, 1600, row*520 + 505), fill="#cccccc", width=2)
        if row:
            draw.line((20, row*520, 2100, row*520), fill="#cccccc", width=2)
    figure.save(output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("codepoints", nargs="+", type=lambda value: int(value.removeprefix("U+").removeprefix("U"), 16))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(render(args.codepoints, args.output))


if __name__ == "__main__":
    main()
