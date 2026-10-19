# Panorama Gothic

A sans-serif font family and supplements targeting the **Unicode 19 development draft**. This project prioritizes authentic character shapes for codepoints missing from Noto. Hex labels, tofu boxes and other placeholders do not count toward coverage.

## Small Seal: independent drawings and real strokes

The current design sample targets **U+3D000–U+3D03F**. Each character gets its own `image_gen.imagegen` drawing informed by all available **THX, CCZ, QJZ and DYC** specimens in the official Unicode chart. Missing specimens remain marked unavailable. Where historical variants differ, a coherent attested construction is chosen; incompatible components are not blended.

The original generated PNGs and complete prompts are preserved in `design/seal-individual/`. Separate visual reviews record branches, counters, detachments, specimen availability and the exact PNG hash. A drawing that loses a component is rejected. Any subsequent manual correction to the font geometry is explicitly recorded; it does not turn the rejected PNG into an approved drawing.

The font source is **editable Bézier centerlines**, stored as JSON and SVG in `design/strokes-individual/`. Automatic tracking follows the skeleton of the new drawing; hand-reviewed overrides take precedence. The reference font outlines and brush perimeters are not used to construct the new font. TrueType stores the constant-radius expansion of these centerlines as filled outlines, with round caps and joins.

Each complete glyph is scaled proportionally to a maximum centerline dimension of **738 units**, centered at **(512, 320) in font coordinates** within its 1024-unit em. This keeps each glyph's internal proportions and applies the same transform at every weight. The shared pen width is independent of that scale: **Regular 400 uses 30 units**, giving a maximum ink dimension of **768 units**. Editable source files retain their reviewed nominal width of 43 units.

The native generated drawing remains the main guide for trajectories, shape and proportions. Repairs preserve that drawing and change only a confirmed omission or a tracking defect. U+3D034, for example, adds the missing left descending leg beneath its upper shoulder while retaining the other stroke courses.

- Stroke construction example: `fonts/seal-individual/stroke-comparison.png`
- Interactive path replay: `fonts/seal-individual/stroke-playback.html`
- Font preview: `fonts/seal-individual/preview-64.png`
- Installable font: `fonts/seal-individual/PanoramaGothicSealIndividual-Regular.ttf`
- Download package: `dist/Panorama-Gothic-Seal-Stroke-64.zip`
- Editable example: `design/strokes-individual/U3D001.svg`

The geometry of U+3D001 is manually reviewed, including its smooth stem-to-tail curve and detached lower bar. The other glyphs' manual/automatic status and targeted repairs are recorded individually. Validation combines visual review of all **64 sample glyphs** with `tools/verify_glyph_invariants.py`, which checks recorded structural features in the rendered static and variable fonts. These regression gates check details such as bar relationships, branches and open spaces at multiple weights. `tools/verify_source_reviews.py` rejects any change to the accepted geometry or source PNG hashes; its registry is updated only after a new visual review. `tools/verify_normalized_sizes.py` checks actual font bounds, centering, proportions and advances at all named weights. Further shape and optical review remains necessary. Visual chart comparisons are not specialist paleographic certification, and the path sequence does not establish historical writing order. Experimental samples are excluded from production coverage.

### Weight from pen width

`tools/build_stroke_variable.py` builds a real `wght` axis from 300 to 700 using **identical normalized centerlines in every master**, with **400 as the default**. Only the shared pen width changes; advances stay fixed at 1024 units.

| Weight | Style | Pen width |
| --- | --- | --- |
| 300 | Light | 23.5 units |
| 400 | Regular | 30 units |
| 500 | Medium | 36.5 units |
| 600 | SemiBold | 43 units |
| 700 | Bold | 49.5 units |

The previous 300 width is now 400, and the previous 400 width is now 600. Dense forms can close small gaps or counters at heavier weights; consult the actual-font checks and visual proofs for their current limits.

The variable font and self-contained slider are written to `fonts/seal-individual-variable/`. The older `fonts/seal-variable/` outline-offset study is retained for comparison. The single-style `fonts/seal-example/` and grouped four-source `fonts/seal-redraw/` studies are superseded; the latter contains known identity errors and is marked rejected.

This sample does not complete the **11,328-character Small Seal repertoire** or the full Unicode development target.

The family is split into multiple font files because OpenType limits each face to 65,535 glyphs. Original script shaping is retained in Noto-derived faces. Supplements are kept in separate files with their original licenses.

## Sources and reference

- Unicode development data: [`unicode-org/unicodetools`](https://github.com/unicode-org/unicodetools/tree/main/unicodetools/data/ucd/dev). The exact commit and input hashes are recorded with the coverage report.
- Representative glyph reference: [official Unicode code-chart PDFs](https://www.unicode.org/charts/). Charts are reference material; font outlines are not extracted from them.
- Noto Sans: installed redistributable source faces, preserving script-specific shaping.
- [Plangothic Project](https://github.com/Fitzgerald-Porthmouth-Koenigsegg/Plangothic_Project): sans-serif supplementary CJK glyphs.
- [GNU Unifont](https://unifoundry.com/unifont/): bitmap-derived vector supplements where suitable source glyphs are available.

Source versions, licenses, hashes, uncovered characters and additions by Unicode age are recorded in the repository. A development draft can change; its eventual repertoire is not implied by a snapshot.

## Development

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
make test
```

To rebuild the stroke sample after individual generation and review (additional dependencies are in `requirements-tracing.txt`):

```sh
python tools/track_centerlines.py --single-images
python tools/verify_source_reviews.py
python tools/build_stroke_font.py --source-root design/strokes-individual --output fonts/seal-individual --family "Panorama Gothic Seal Individual" --font-stroke-width 30 --normalize-glyphs --require-visual-match
python tools/render_stroke_font.py --font fonts/seal-individual/PanoramaGothicSealIndividual-Regular.ttf --output fonts/seal-individual
python tools/render_stroke_demo.py --source design/strokes-individual/U3D001.json --output fonts/seal-individual
python tools/audit_stroke_sample.py
python tools/verify_glyph_invariants.py --font fonts/seal-individual/PanoramaGothicSealIndividual-Regular.ttf
python tools/verify_normalized_sizes.py --font fonts/seal-individual/PanoramaGothicSealIndividual-Regular.ttf --output fonts/seal-individual/size-check.json
python tools/build_stroke_variable.py --require-visual-match
python tools/render_weight_demo.py --font fonts/seal-individual-variable/PanoramaGothicSealIndividualVariable.ttf --output fonts/seal-individual-variable
python tools/verify_glyph_invariants.py --font fonts/seal-individual-variable/PanoramaGothicSealIndividualVariable.ttf
python tools/verify_normalized_sizes.py --font fonts/seal-individual-variable/PanoramaGothicSealIndividualVariable.ttf --output fonts/seal-individual-variable/size-check.json
```

Build and installation instructions, generated fonts and the verified coverage summary are added as each source is integrated.

## Coverage policy

Graphic characters require a real character glyph. Controls, formatting characters, private-use values, surrogates and unassigned values are accounted for separately. A cmap entry alone does not prove usable shaping, mark positioning, variation sequences or emoji sequences. Bitmap-derived supplements retain a coarse grid design and are reported separately from smooth Noto and Plangothic outlines.

The audited output currently maps **156,434 of 172,636** target characters. The remaining **16,202** are Small Seal (11,328), Egyptian Hieroglyphs Extended-A (3,995), Jurchen (870) and Jurchen Radicals (9). Experimental redraws are excluded. The development data is pinned to commit `4fd8eca90b30aa4c72543ccddb4c15d05becdf8d`; its six audited UCD files were verified on 2026-10-18 and are byte-identical to the preceding baseline. See `coverage/README.md` for the full audit and its limits.

## Licensing

Third-party font licenses and attribution accompany their respective fonts. Noto and Plangothic derivatives remain under the SIL Open Font License. Unifont derivatives retain their upstream licensing and font embedding exception; outlines from incompatible license families are not merged into one face.
