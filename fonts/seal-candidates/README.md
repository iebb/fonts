# Historical Small Seal continuation candidate

The candidate font maps U+3D000–U+3D080 (129 characters). U+3D080 is a new
ImageGen drawing with editable automatically tracked Bézier centerlines. Its
original geometry had pending independent review when this snapshot was built.
U+3D080 has since received a bounded smoothing correction and independent
Regular400 acceptance; the corrected font is in `../seal-individual/`. This
file and candidate binary preserve the earlier unreviewed snapshot.

All characters use the existing shared construction: 1024-unit advances,
maximum centerline extent 738, center (512,320), Regular 400 pen width 30,
round caps and joins. Original drawings are preserved byte for byte.

- [Candidate Regular TTF](PanoramaGothicSealCandidate-Regular.ttf?raw=1)
- [New U+3D080 rendered from the font](U3D080.png)
- [Font construction manifest](manifest.json)

The historical candidate snapshot can be rebuilt from commit `60ed28f`. Current
candidate builds may contain further pending drawings; their presence never
grants frozen acceptance. The complete Unicode 18 goal remains 11,328
characters, U+3D000–U+3FC3F. Consult the live progress audit for reviewed counts.
