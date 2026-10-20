#!/usr/bin/env python3
"""Render a real font-weight comparison and a slider specimen."""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path
from urllib.parse import quote

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont


def repertoire_label(codepoints: list[int]) -> str:
    """Describe contiguous runs without implying that gaps are covered."""
    if not codepoints:
        return "No encoded characters"
    runs, first, previous = [], codepoints[0], codepoints[0]
    for cp in codepoints[1:]:
        if cp != previous + 1:
            runs.append((first, previous))
            first = cp
        previous = cp
    runs.append((first, previous))
    return ", ".join(f"U+{first:05X}" if first == last else f"U+{first:05X}–U+{last:05X}"
                     for first, last in runs)


def render(font_path: Path, output: Path, label_font: Path, *, embed_font: bool = False) -> None:
    output.mkdir(parents=True, exist_ok=True)
    metadata = TTFont(font_path)
    weights = sorted((round(instance.coordinates["wght"]),
                      metadata["name"].getDebugName(instance.subfamilyNameID))
                     for instance in metadata["fvar"].instances)
    axis = next(axis for axis in metadata["fvar"].axes if axis.axisTag == "wght")
    minimum, default, maximum = map(round, (axis.minValue, axis.defaultValue, axis.maxValue))
    codepoints = sorted(metadata.getBestCmap() or {})
    metadata.close()
    if not codepoints:
        raise ValueError("Cannot render a font without cmap characters")
    glyphs = [cp for cp in (0x3D003, 0x3D00E, 0x3D01E, 0x3D03F) if cp in codepoints]
    if not glyphs:
        glyphs = codepoints[:4]
    image = Image.new("RGB", (140 + 340 * len(weights), 1200), "#FAFAF7")
    draw = ImageDraw.Draw(image)
    heading = ImageFont.truetype(str(label_font), 38)
    label = ImageFont.truetype(str(label_font), 27)
    small = ImageFont.truetype(str(label_font), 20)
    draw.text((70, 38), "Panorama Gothic · Small Seal", font=heading, fill="#171717")
    draw.text((70, 96), "Variable weight · same characters and spacing", font=small, fill="#656560")
    for column, (weight, name) in enumerate(weights):
        center = 240 + column * 340
        draw.text((center, 180), name, font=label, fill="#171717", anchor="mm")
        draw.text((center, 221), str(weight), font=small, fill="#73736B", anchor="mm")
        font = ImageFont.truetype(str(font_path), 230)
        axes = font.get_variation_axes()
        font.set_variation_by_axes([weight if axis["name"] == b"Weight" else axis["default"] for axis in axes])
        for row, cp in enumerate(glyphs):
            baseline = 420 + row * 238
            draw.text((center - 115, baseline), chr(cp), font=font, fill="#121212", anchor="ls")
    image.save(output / "weight-comparison.png")

    if embed_font:
        encoded = base64.b64encode(font_path.read_bytes()).decode("ascii")
        font_url = f"data:font/ttf;base64,{encoded}"
    else:
        relative_font = Path(os.path.relpath(font_path.resolve(), output.resolve()))
        font_url = quote(relative_font.as_posix(), safe="/")
    characters = "".join(f'<span title="U+{cp:05X}">{chr(cp)}</span>' for cp in codepoints)
    html = f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Panorama Gothic — weight specimen</title>
<style>
@font-face{{font-family:Seal;src:url("{font_url}") format("truetype");font-weight:{minimum} {maximum}}}
*{{box-sizing:border-box}}body{{margin:0;padding:clamp(24px,5vw,72px);background:#fafaf7;color:#171717;font-family:system-ui,sans-serif}}
main{{max-width:1200px;margin:auto}}h1{{font-size:clamp(24px,4vw,38px);font-weight:500;margin:0 0 10px}}p{{color:#66665e;margin:0 0 28px}}
.control{{display:flex;align-items:center;gap:20px;margin:30px 0 44px}}input{{flex:1;accent-color:#171717}}output{{font-variant-numeric:tabular-nums;min-width:3ch}}
#glyphs{{font-family:Seal;font-variation-settings:"wght" {default};font-size:clamp(56px,9vw,120px);display:grid;grid-template-columns:repeat(8,1fr);gap:clamp(8px,2vw,28px);line-height:1.45}}
#glyphs span{{text-align:center}}footer{{margin-top:42px;color:#77776f;font-size:13px}}
@media(max-width:650px){{#glyphs{{grid-template-columns:repeat(4,1fr);font-size:clamp(64px,15vw,120px)}}}}
</style><main><h1>Panorama Gothic · Small Seal</h1>
<p>Move the slider to change stroke weight continuously.</p>
<label class="control">Light <input id="weight" aria-label="Font weight" type="range" min="{minimum}" max="{maximum}" value="{default}" step="1"> Bold <output id="number">{default}</output></label>
<div id="glyphs">{characters}</div>
<footer>{len(codepoints)}-character design prototype · {repertoire_label(codepoints)} · SIL Open Font License 1.1</footer></main>
<script>const slider=document.getElementById('weight'),glyphs=document.getElementById('glyphs'),number=document.getElementById('number');slider.addEventListener('input',()=>{{glyphs.style.fontVariationSettings='"wght" '+slider.value;number.value=slider.value;}});</script></html>'''
    (output / "weight-slider.html").write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, default=Path("fonts/seal-variable/PanoramaGothicSealVariable.ttf"))
    parser.add_argument("--output", type=Path, default=Path("fonts/seal-variable"))
    parser.add_argument("--label-font", type=Path, default=Path("fonts/noto/PanoramaGothic-Regular.ttf"))
    parser.add_argument("--embed-font", action="store_true", help="Embed the font for a standalone HTML specimen")
    args = parser.parse_args()
    render(args.font, args.output, args.label_font, embed_font=args.embed_font)
    print(args.output / "weight-comparison.png")
    print(args.output / "weight-slider.html")


if __name__ == "__main__":
    main()
