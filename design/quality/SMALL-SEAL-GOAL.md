# Full Small Seal creation

The target is every code point in the pinned Unicode 18.0.0 Seal script and
block: U+3D000–U+3FC3F, 11,328 characters. Both UCD properties must agree, and
the cached UCD files must retain their recorded fingerprints. A shorter chart,
font cmap or work queue cannot redefine this target.

Run `make seal-progress` to refresh `small-seal-progress.json` from local
evidence. Use `python3 tools/seal_repertoire_status.py --full-worklist` when
per-character states are needed. The compact default report stores counts and
ranges. It is a dated workspace snapshot; unpublished drawings can be present
locally before their batch appears on GitHub.

Every character needs its own native ImageGen drawing, based on all available
THX, CCZ, QJZ and DYC chart specimens. Missing columns remain unavailable. A
coherent attested construction is chosen where specimens differ. Original PNGs,
prompts, fingerprints and failed attempts are preserved. Available private chart
references are raster crops; embedded reference-font outlines are not used to
construct the new glyphs.

Editable Bézier centerlines follow those drawings. An independent reviewer
checks branches, bars, counters, detachments and proportions in the native
drawing and actual normalized Regular400 font. Confirmed defects receive a
bounded retry or a minimal, recorded vector repair. A repaired vector does not
turn a mismatching PNG into an approved native drawing. Heavy weights receive
separate optical verdicts; their path presence alone is insufficient.

Only an exact, reviewed geometry/native fingerprint deliberately added to
`accepted-geometry.json` counts as frozen acceptance. The current source review
gate must remain valid. Generated files, drawing-worker match flags and chart
labels do not create accepted coverage. Completion also requires valid native
provenance and the pinned chart evidence for the complete target. Final compiled
fonts still require repertoire, bounds, advance, structure and artifact checks.

The shared size and weight rules remain: maximum centerline dimension738,
center(512,320), Regular400 pen width30, with proportional glyph scaling and a
pen width independent of that scale. The old300 width is400; old400 is600.
Visual comparison is not specialist paleographic certification or historical
stroke-order verification.

Full-range exports will be split into bounded font files when necessary.
Sharding controls file sizes; individual glyph point counts and variation tuple
payloads must also fit their format limits. Compiler changes must preserve the
reviewed source trajectories and pass raster and width checks before use.

The published128-character v0.6 sample is an intermediate artifact. It does not
complete this goal and remains excluded from production coverage.

## Resume from a clean checkout

The published Unicode 18 UCD is pinned in `reference/ucd-18/`; the older
Unicode 19 development files remain only as historical coverage evidence.
Download the chart to `reference/seal/U3D000.pdf` from the URL in the chart
index and verify its SHA-256 before use. Recreate the private all-specimen
index without generating hundreds of comparison sheets:

```sh
python3 tools/prepare_multi_references.py --start 3D000 --count 11328 --index-only
python3 tools/prepare_individual_references.py --start 3D000 --count 192
make seal-progress
```

The references remain private and excluded from Git. Do not promote the
U+3D080 candidate or any later glyph merely because it compiles successfully.
