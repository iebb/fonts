# Small Seal continuation candidates

The candidate font maps U+3D000–U+3D080 (129 characters). U+3D080 is a new
ImageGen drawing with editable automatically tracked Bézier centerlines. Its
independent structural and actual-font reviews are pending. It is not included
in the frozen acceptance registry. The reviewed 128-character sample remains
in `../seal-individual/`.

All characters use the existing shared construction: 1024-unit advances,
maximum centerline extent 738, center (512,320), Regular 400 pen width 30,
round caps and joins. Original drawings are preserved byte for byte.

- [Candidate Regular TTF](PanoramaGothicSealCandidate-Regular.ttf?raw=1)
- [New U+3D080 rendered from the font](U3D080.png)
- [Font construction manifest](manifest.json)

Rebuild from the repository root:

```sh
python3 tools/track_centerlines.py --single-images --start 3D080 --count 1 --output design/strokes-individual/candidates
python3 tools/build_stroke_font.py --source-root design/strokes-individual --additional-source-root design/strokes-individual/candidates --output fonts/seal-candidates --family 'Panorama Gothic Seal Candidate' --font-stroke-width 30 --normalize-glyphs
python3 tools/render_stroke_font.py --font fonts/seal-candidates/PanoramaGothicSealCandidate-Regular.ttf --output fonts/seal-candidates --sample-codepoint 3D080
```

The complete Unicode 18 goal remains 11,328 characters, U+3D000–U+3FC3F.
The current accepted count is 128; candidate presence does not grant acceptance.
