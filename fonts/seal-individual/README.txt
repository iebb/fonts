Panorama Gothic Small Seal — 128-character stroke sample, version 0.6

U+3D000–U+3D07F. One independent ImageGen drawing per character,
informed by all available THX, CCZ, QJZ and DYC chart specimens.
The new U+3D040–U+3D07F page has 243 of 256 possible specimens;
unavailable specimens are explicitly recorded. The first 64 source
PNG, JSON and SVG files are unchanged in this expansion.
Native drawing trajectories and proportions guide reconstruction.
Only confirmed structural and tracing defects receive minimal repairs.

Editable Bezier centerlines have round ends and joins. Each complete
glyph is scaled proportionally to a maximum centerline dimension of
738 units and centered at (512, 320) in font coordinates. The shared
pen width does not scale with the glyph. This Regular 400 font uses
30 pen units per 1024-unit em, with maximum ink dimension 768 units.
Reviewed editable sources retain their nominal width 43.

Original PNGs remain immutable. Targeted manual vector repairs and
their source hashes are recorded individually; automatic paths and
manual overrides are distinguished in the manifest. A corrected
vector does not change a rejected native drawing's review verdict.
Repaired geometry receives independent review in the actual font.
Preserved provenance records omissions, tracing defects and any
excluded non-stroke specks.

The companion variable font defaults to 400 and uses these pen widths:
300 Light 23.5; 400 Regular 30; 500 Medium 36.5;
600 SemiBold 43; 700 Bold 49.5.
The previous 300 width is now 400; the previous 400 width is now 600.
All weights reuse the same normalized centerlines and fixed advances.

Validation combines reference review of all 128 sample glyphs at default
Regular 400 with actual-font gates in tools/verify_glyph_invariants.py.
Recorded checks cover bar relationships, branches and open spaces;
some dense-form rules apply only at weights 300 and 400. Default
reference acceptance does not imply heavy-weight optical acceptance.
Dense forms such as U+3D045, U+3D049, U+3D060, U+3D070, U+3D073 and
U+3D077 merge marks or counters at 600 or 700, with paths retained.
These weights remain subject to optical review.

The full 128-entry accepted-geometry registry rejects changed source
hashes until renewed visual review. size-check.json verifies actual
compiled bounds, centering, source proportions and fixed advances,
and checks that all registered glyphs are present. Passing these
checks does not certify every detail or every future source change.

Historical stroke order and specialist paleographic correctness
remain unverified. This sample adds no production Unicode coverage.
See manifest.json and audit.json for evidence and checks.
Editable SVGs: centerlines/. Interactive example: stroke-playback.html.
Previews: preview-128.png, preview-64.png (retained first page),
and preview-3D040-3D07F.png (new page).
Package: dist/Panorama-Gothic-Seal-Stroke-128.zip in the repository.

Static previews are rendered from the actual TTF with FreeType. The current
sandbox blocks Chromium's socket operations, so browser-check.json records
the path replay as unverified rather than reporting a browser pass.
Rebuild from the repository root: make seal-strokes seal-variable.
Licensed under the SIL Open Font License 1.1.
