# Panorama Gothic

A sans-serif font family and supplements targeting the **Unicode 19 development draft**. This project prioritizes authentic character shapes for codepoints missing from Noto. Hex labels, tofu boxes and other placeholders do not count toward coverage.

## 64-character Small Seal example

The current design example covers **U+3D000–U+3D03F**. All 64 glyphs were redrawn with `image_gen.imagegen` from raster references prepared from the official Unicode chart, then converted to smooth quadratic TrueType outlines. The glyphs contain only character strokes. Original ImageGen source sheets and generation records are retained in `design/seal/`.

- Preview: `fonts/seal-example/preview-64.png`
- Installable font: `fonts/seal-example/PanoramaGothicSealExample-Regular.ttf`
- Browser font: `fonts/seal-example/PanoramaGothicSealExample-Regular.woff`
- Download package: `Panorama-Gothic-Seal-64-sample.zip`

This is an experimental design sample. It is excluded from the production coverage count. It does not claim completion of the 11,328-character Small Seal repertoire or the complete Unicode 19 font.

### Variable-weight study

`fonts/seal-variable/` contains a real `wght` axis from 300 to 700, with Light, Regular, Medium and Bold named instances. Regular 400 preserves the original outlines and spacing. `weight-comparison.png` shows four weights; `weight-slider.html` is a self-contained interactive specimen.

This weight study is a prototype made by adjusting the font outlines. Dense glyphs need optical corrections to their fine joins and counters before the heavy weights are production-ready. The original ImageGen artwork is unchanged. Rebuild with `python tools/build_weight_demo.py` and `python tools/render_weight_demo.py`.

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

Build and installation instructions, generated fonts and the verified coverage summary are added as each source is integrated.

## Coverage policy

Graphic characters require a real character glyph. Controls, formatting characters, private-use values, surrogates and unassigned values are accounted for separately. A cmap entry alone does not prove usable shaping, mark positioning, variation sequences or emoji sequences. Bitmap-derived supplements retain a coarse grid design and are reported separately from smooth Noto and Plangothic outlines.

## Licensing

Third-party font licenses and attribution accompany their respective fonts. Noto and Plangothic derivatives remain under the SIL Open Font License. Unifont derivatives retain their upstream licensing and font embedding exception; outlines from incompatible license families are not merged into one face.
