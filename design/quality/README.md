# Small Seal review records

The four `recheck-*-*.json` reports document the second visual review of all
64 sample glyphs against every available chart specimen. They distinguish
confirmed repairs, accepted constructions and remaining stylistic uncertainty.
Native ImageGen PNGs remain unchanged; repairs are explicit vector overrides.

`accepted-geometry.json` freezes the reviewed centerline geometry and native
PNG hashes. A build cannot refresh this registry automatically. Review a
changed drawing and its compiled glyph before updating its accepted entry.

`invariants.json` defines targeted checks for previously observed errors.
`verify_glyph_invariants.py` checks actual FreeType font rasters at every named
weight. Matching these features does not certify every detail of a character.

Both Makefile sample targets reject unreviewed geometry before compiling,
then check actual font features, normalization and advances. Their JSON
evidence is saved beside the fonts. Local specimen inspection sheets and
temporary proof fonts are excluded from version control.
