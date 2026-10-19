Panorama Gothic Small Seal — centerline weight prototype

64 characters: U+3D000–U+3D03F.
wght 300–700, default 400. Shared pen widths per 1024-unit em:
300 Light 23.5; 400 Regular 30; 500 Medium 36.5;
600 SemiBold 43; 700 Bold 49.5.
The previous 300 width is now 400; the previous 400 width is now 600.

All masters reuse identical normalized editable centerlines and fixed
1024-unit advances. Each complete glyph is scaled proportionally to
a maximum centerline dimension of 738 units and centered at (512, 320)
in font coordinates. Pen width does not scale with glyph size; only
that shared width changes between weights. Regular's maximum ink
dimension is 768 units. No outline-offset operation is used.

Every native PNG remains immutable. Targeted manual vector corrections,
source hashes and independent review verdicts are recorded alongside
the editable sources; a vector repair does not approve a rejected PNG.
Validation combines visual review of all 64 sample glyphs with rendered
font feature regression gates in tools/verify_glyph_invariants.py.
Frozen geometry fingerprints reject source changes until reviewed again.
size-check.json verifies all five named instances' bounds and advances.
Consult the current audit and proofs for limits: dense counters and
gaps can close at heavier weights, and further optical review is needed.

This is a 64-character prototype, not full Small Seal or Unicode coverage.
Character forms remain experimental; historical stroke order and
specialist paleographic correctness are unverified.
Open weight-slider.html for the self-contained interactive specimen.
Licensed under the SIL Open Font License 1.1.
