Panorama Gothic Small Seal — centerline weight prototype, version 0.6

128 characters: U+3D000–U+3D07F.
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
Each character has its own ImageGen drawing informed by all available
THX, CCZ, QJZ and DYC specimens. The new U+3D040–U+3D07F page has
243 of 256 possible chart specimens. The first 64 source PNG, JSON
and SVG files remain unchanged in this expansion.

Validation combines reference review of all 128 sample glyphs at default
Regular 400 with actual-font gates in tools/verify_glyph_invariants.py.
Rules have explicit weight scopes; some dense-form checks apply only at
300 and 400. Default reference acceptance does not establish optical
acceptance at every weight. U+3D045, U+3D049, U+3D060, U+3D070,
U+3D073 and U+3D077, for example, merge some marks or counters at
600 or 700. All paths remain; heavy optical acceptance is still limited.

The full 128-entry accepted-geometry registry rejects changed source
hashes until renewed visual review. size-check.json checks all five
named instances' actual bounds, centering, source proportions and
advances, and confirms that all registered glyphs are present.
Consult the current audit and proofs for each character's limits.

This 128-character prototype adds no production Unicode coverage.

The current build's browser interaction check is blocked by sandbox socket
restrictions. browser-check.json records this explicitly; the slider is not
claimed as browser-verified. Static font rendering and the recorded font,
source, geometry and size checks passed. optical-review.json lists the new
page's 55 accepted SemiBold forms and nine known optical failures.
Character forms remain experimental; historical stroke order and
specialist paleographic correctness are unverified.
Open weight-slider.html for the self-contained interactive specimen.
Static full and page previews are in ../seal-individual/.
Package: dist/Panorama-Gothic-Seal-Stroke-128.zip in the repository.
Rebuild from the repository root: make seal-strokes seal-variable.
Licensed under the SIL Open Font License 1.1.
