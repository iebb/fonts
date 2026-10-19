#!/usr/bin/env python3
"""Show editable stroke centerlines and render their constant-width geometry."""
from __future__ import annotations

import argparse
import base64
import hashlib
from html import escape
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

COLORS = ["#BA4D30", "#337D73", "#4775AA", "#9A65A6"]


def plot_path(data: str):
    from matplotlib.path import Path as MPath
    from svgpathtools import parse_path, Line, CubicBezier, QuadraticBezier
    vertices, codes = [], []
    for subpath in parse_path(data).continuous_subpaths():
        vertices.append((subpath.start.real, subpath.start.imag))
        codes.append(MPath.MOVETO)
        for segment in subpath:
            if isinstance(segment, Line):
                vertices.append((segment.end.real, segment.end.imag)); codes.append(MPath.LINETO)
            elif isinstance(segment, CubicBezier):
                vertices.extend((p.real, p.imag) for p in (segment.control1, segment.control2, segment.end)); codes.extend([MPath.CURVE4] * 3)
            elif isinstance(segment, QuadraticBezier):
                vertices.extend((p.real, p.imag) for p in (segment.control, segment.end)); codes.extend([MPath.CURVE3] * 2)
            else:
                raise ValueError(f"Unsupported centerline segment: {type(segment).__name__}")
        if subpath.isclosed():
            vertices.append(vertices[-1]); codes.append(MPath.CLOSEPOLY)
    return MPath(vertices, codes)


def render_proof(root: Path, output: Path, data: dict, old_svg, reference_note: str = "",
                 native: Path | None = None) -> None:
    cache = root / ".cache/matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import PathPatch
    from matplotlib.transforms import Affine2D
    from matplotlib.font_manager import FontProperties

    fig = plt.figure(figsize=(15, 6.9), dpi=150, facecolor="#FAFAF7")
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1500); ax.set_ylim(690, 0); ax.set_axis_off()
    font = FontProperties(fname=str(root / "fonts/noto/PanoramaGothic-Regular.ttf"))
    def text(x, y, value, size, center=False, color="#171717"):
        ax.text(x, y, value, fontsize=size * .72, fontproperties=font, color=color, ha="center" if center else "left", va="baseline")
    text(55, 66, "Small Seal · real stroke construction", 35)
    text(55, 105, "U+3D001 · four editable paths · one shared width · rounded ends and joins", 19, color="#696963")
    if reference_note:
        text(55, 135, reference_note, 16, color="#696963")
    for x, title in [(270, "New ImageGen drawing" if native else "Previous outline"),
                     (750, "Tracked centerlines"), (1230, "Uniform-width strokes")]:
        text(x, 167, title, 24, True)
    if native:
        from PIL import Image
        ax.imshow(Image.open(native), extent=(50, 490, 623, 183), interpolation="bilinear", interpolation_stage="rgba")
    else:
        for node in old_svg.iter():
            if node.tag.rsplit("}", 1)[-1] == "path":
                ax.add_patch(PathPatch(plot_path(node.attrib["d"]), facecolor="#171717", edgecolor="none", transform=Affine2D().scale(440 / 314).translate(50, 183) + ax.transData))
    left, top, width, height = data["viewBox"]
    scale = 440 / max(width, height)
    for i, stroke in enumerate(data["strokes"]):
        path = plot_path(stroke["path"])
        for x, pen_width, color in [(530, data["stroke_width"] * 3/13, COLORS[i]),
                                     (1010, data["stroke_width"], "#171717")]:
            ax.add_patch(PathPatch(path, fill=False, linewidth=pen_width * scale * .72, capstyle="round", joinstyle="round", edgecolor=color, transform=Affine2D().translate(-left, -top).scale(scale).translate(x, 183) + ax.transData))
    text(270, 648, "Independent redraw from four specimens" if native else "Variable brush silhouette", 17, True, "#696963")
    text(750, 648, "Main curve · upper branch · crossbar · detached bar", 17, True, "#696963")
    text(1230, 648, f"{data['stroke_width']:g} units throughout each stroke", 17, True, "#696963")
    fig.savefig(output / "stroke-comparison.png", dpi=150, facecolor=fig.get_facecolor())
    fig.savefig(output / "stroke-comparison.pdf", facecolor=fig.get_facecolor())
    plt.close(fig)


def render(root: Path, source: Path | None = None, output: Path | None = None) -> None:
    source = source or root / "design/strokes-individual/U3D001.json"
    data = json.loads(source.read_text())
    output = output or root / "fonts/seal-individual"
    output.mkdir(parents=True, exist_ok=True)
    # Show the exact exported font trajectories and current Regular width.
    # Authoring JSON retains its reviewed nominal width and original placement.
    manifest_path = output / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        record = next((g for g in manifest.get("glyphs", [])
                       if g["codepoint"] == data["codepoint"]), None)
        svg_path = output / "centerlines" / source.with_suffix(".svg").name
        if (record and svg_path.is_file()
                and record["centerline_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()):
            exported = ET.parse(svg_path).getroot()
            data["strokes"] = [{"id": node.attrib["id"], "path": node.attrib["d"]}
                               for node in exported.iter()
                               if node.tag.rsplit("}", 1)[-1] == "path"]
            data["viewBox"] = [float(value) for value in exported.attrib["viewBox"].split()]
            data["stroke_width"] = record["stroke_width_font_units"]
    legacy_svg_path = root / "fonts/seal-example/glyphs/U3D001.svg"
    old_svg = ET.parse(legacy_svg_path).getroot() if legacy_svg_path.is_file() else ET.Element("svg")
    old_paths = "".join(f'<path d="{escape(node.attrib["d"])}" fill="#171717"/>'
                        for node in old_svg.iter() if node.tag.rsplit("}", 1)[-1] == "path")
    strokes = data["strokes"]
    pen_width = float(data["stroke_width"])
    left, top, view_width, view_height = data["viewBox"]
    scale = 440 / max(view_width, view_height)
    native = root / data.get("source", {}).get("file", "missing-native.png")
    native = native if native.is_file() and "individual" in str(source) else None
    if native is None and not legacy_svg_path.is_file():
        raise FileNotFoundError("The stroke proof needs its native PNG or the legacy comparison SVG")
    first_art = (f'<image x="50" y="183" width="440" height="440" '
                 f'href="data:image/png;base64,{base64.b64encode(native.read_bytes()).decode()}"/>'
                 if native else f'<g transform="translate(50,183) scale(1.401273885)">{old_paths}</g>')
    reference_note = ("Independent drawing informed by THX · CCZ · QJZ · DYC"
                      if any(name in str(source) for name in ("consensus", "individual")) else "")
    black_paths = "".join(f'<path id="{s["id"]}" d="{escape(s["path"])}"/>' for s in strokes)
    tracked_paths = "".join(f'<path d="{escape(s["path"])}" stroke="{COLORS[i]}"/>'
                            for i, s in enumerate(strokes))
    proof = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="690" viewBox="0 0 1500 690">
<rect width="1500" height="690" fill="#FAFAF7"/>
<g font-family="Helvetica" fill="#171717"><text x="55" y="66" font-size="35">Small Seal · real stroke construction</text>
<text x="55" y="105" font-size="19" fill="#696963">U+3D001 · four editable paths · one shared width · rounded ends and joins</text>
<text x="270" y="167" text-anchor="middle" font-size="24">{'New ImageGen drawing' if native else 'Previous outline'}</text>
<text x="750" y="167" text-anchor="middle" font-size="24">Tracked centerlines</text>
<text x="1230" y="167" text-anchor="middle" font-size="24">Uniform-width strokes</text></g>
{first_art}
<g transform="translate(530,183) scale({scale}) translate({-left},{-top})" fill="none" stroke-width="{pen_width*3/13}" stroke-linecap="round" stroke-linejoin="round">{tracked_paths}</g>
<g transform="translate(1010,183) scale({scale}) translate({-left},{-top})" fill="none" stroke="#171717" stroke-width="{pen_width}" stroke-linecap="round" stroke-linejoin="round">{black_paths}</g>
<g font-family="Helvetica" font-size="17" fill="#696963"><text x="270" y="648" text-anchor="middle">{'Independent redraw from four specimens' if native else 'Variable brush silhouette'}</text>
<text x="750" y="648" text-anchor="middle">Main curve · upper branch · crossbar · detached bar</text>
<text x="1230" y="648" text-anchor="middle">{pen_width:g} units throughout each stroke</text></g></svg>'''
    (output / "stroke-comparison.svg").write_text(proof)
    # Render actual native curve strokes: the PDF SVG importer does not reliably
    # honor round caps and nested viewport transforms.
    render_proof(root, output, data, old_svg, reference_note, native)

    colored_paths = "".join(f'<path d="{escape(s["path"])}" stroke="{COLORS[i]}"/>'
                            for i, s in enumerate(strokes))
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Small Seal — editable stroke construction</title><style>
*{{box-sizing:border-box}}body{{margin:0;padding:clamp(24px,5vw,64px);font:16px system-ui,sans-serif;background:#fafaf7;color:#171717}}
main{{max-width:1000px;margin:auto}}h1{{font-size:30px;font-weight:500;margin:0 0 12px}}p{{color:#66665f;line-height:1.6}}.controls{{display:flex;gap:20px;align-items:center;flex-wrap:wrap;margin:24px 0}}
input[type=range]{{width:220px;accent-color:#171717}}button{{background:#171717;color:white;border:0;border-radius:6px;padding:12px 18px;font:inherit;cursor:pointer}}
.drawing{{display:flex;justify-content:center}}svg{{width:min(100%,650px);height:auto}}#ink{{fill:none;stroke:#171717;stroke-width:{pen_width:g};stroke-linecap:round;stroke-linejoin:round}}#guides{{fill:none;stroke-width:{pen_width*1.5/13:g};stroke-linecap:round;stroke-linejoin:round;display:none}}
.note{{font-size:13px;color:#77776f;margin-top:20px}}output{{font-variant-numeric:tabular-nums}}
</style><main><h1>Small Seal · real stroke construction</h1>
<p>{escape(reference_note + '. ') if reference_note else ''}Four editable centerline paths. A single shared width controls all strokes; their endpoints and joins are round.</p>
<div class="controls"><button id="play">Replay path construction</button><label>Stroke width <input id="width" type="range" min="{pen_width*7/13:.1f}" max="{pen_width:g}" value="{pen_width:g}" step="0.1"> <output id="value">{pen_width:g}</output></label><label><input id="show" type="checkbox"> Show centerlines</label></div>
<div class="drawing"><svg xmlns="http://www.w3.org/2000/svg" viewBox="{left} {top} {view_width} {view_height}" role="img" aria-label="Small Seal character built from four real stroke paths"><g id="ink">{black_paths}</g><g id="guides">{colored_paths}</g></svg></div>
<p class="note">U+3D001 · Paths stay separate at crossings. The replay shows geometric construction, not an assertion of historical stroke order. Source geometry is stored as editable Bézier centerlines.</p></main>
<script>
const ink=document.getElementById('ink'),paths=[...ink.querySelectorAll('path')],width=document.getElementById('width'),value=document.getElementById('value');let animations=[];
width.addEventListener('input',()=>{{ink.style.strokeWidth=width.value;value.value=width.value;}});
document.getElementById('show').addEventListener('change',event=>{{document.getElementById('guides').style.display=event.target.checked?'block':'none';}});
document.getElementById('play').addEventListener('click',()=>{{animations.forEach(a=>a.cancel());animations=[];paths.forEach((path,index)=>{{let length=path.getTotalLength();path.style.strokeDasharray=length;path.style.strokeDashoffset=length;let animation=path.animate([{{strokeDashoffset:String(length)}},{{strokeDashoffset:'0'}}],{{duration:1000,delay:index*1050,fill:'forwards',easing:'linear'}});animations.push(animation);}});}});
</script></html>'''
    (output / "stroke-playback.html").write_text(html)
    print(output / "stroke-comparison.png")
    print(output / "stroke-playback.html")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    render(args.root, args.source, args.output)
