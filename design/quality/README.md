# Small Seal review records

The version 0.6 sample contains 128 glyphs, U+3D000–U+3D07F. The original
four range reports cover the first 64; `recheck-040-07F.json` records the new
page's reference and actual-font review. The new page has 243 of 256 possible
THX, CCZ, QJZ and DYC chart specimens; missing specimens are recorded as
unavailable. Every character has its own native ImageGen drawing. The first
64 source PNG, JSON and SVG files remain unchanged in this expansion.

Reviews distinguish confirmed repairs, accepted constructions and remaining
uncertainty. Native PNGs remain unchanged; repairs are minimal, explicit
vector overrides with independent actual-font review. Corrected vectors do
not change mismatching native drawings into approved PNGs. Chart comparison
does not certify historical stroke order or specialist paleographic identity.

`accepted-geometry.json` freezes the reviewed centerline geometry and native
PNG hashes for all 128 glyphs. A build cannot refresh this registry
automatically. Review a changed drawing and its compiled glyph before
updating its accepted entry. `verify_source_reviews.py` checks this registry;
source changes require renewed visual review.

`invariants.json` defines targeted checks for previously observed errors.
`verify_glyph_invariants.py` checks actual FreeType font rasters at the
recorded weights. Some rules, including dense-form checks for U+3D045 and
U+3D049, are scoped to 300 and 400; others cover all named weights.
Matching these features does not certify every detail of a character.

Reference acceptance is assessed at default Regular 400, with a shared pen
width of 30 units. It is separate from heavy-weight optical acceptance.
Dense new forms including U+3D045, U+3D049, U+3D060, U+3D070, U+3D073 and
U+3D077 merge some marks or counters at 600 or 700 despite retaining all
centerline paths. The current reports and proofs record these limits.

All weights share a proportional maximum centerline dimension of 738 units
and center (512, 320); Regular's maximum ink dimension is 768. The pen widths
for 300/400/500/600/700 are 23.5/30/36.5/43/49.5. The previous 300 width is
now 400, and the previous 400 width is now 600. `verify_normalized_sizes.py`
uses actual compiled outlines to check size, centering, source proportions
and fixed 1024-unit advances. Its `--registry
design/quality/accepted-geometry.json` option also checks that every
registered glyph is present.

Run `make seal-strokes seal-variable` from the repository root. Both targets
reject unreviewed geometry before compiling, then check actual font features,
normalization and advances. Their JSON
evidence is saved beside the fonts. Local specimen inspection sheets and
temporary proof fonts are excluded from version control.

The release package is `dist/Panorama-Gothic-Seal-Stroke-128.zip`.
`fonts/seal-individual/` contains `preview-128.png`, the retained
`preview-64.png`, and `preview-3D040-3D07F.png`. This experimental sample is
excluded from production coverage, which remains 156,434 of 172,636 targets.
