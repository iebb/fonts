PYTHON ?= python3

.PHONY: test noto supplement audit seal-strokes seal-variable seal-progress

test:
	$(PYTHON) -m unittest discover -s tests -v

noto:
	$(PYTHON) tools/bundle_noto.py

supplement:
	$(PYTHON) tools/build_fonts.py --help

audit:
	$(PYTHON) tools/audit_coverage.py --help

seal-strokes:
	# Compile frozen sources as reviewed; trace new drawings explicitly before review.
	$(PYTHON) tools/verify_source_reviews.py --output fonts/seal-individual/source-review-check.json
	$(PYTHON) tools/build_stroke_font.py --source-root design/strokes-individual --output fonts/seal-individual --family "Panorama Gothic Seal Individual" --font-stroke-width 30 --normalize-glyphs --require-visual-match
	$(PYTHON) tools/render_stroke_font.py --font fonts/seal-individual/PanoramaGothicSealIndividual-Regular.ttf --output fonts/seal-individual
	$(PYTHON) tools/render_stroke_demo.py --source design/strokes-individual/U3D001.json --output fonts/seal-individual
	$(PYTHON) tools/audit_stroke_sample.py
	$(PYTHON) tools/verify_glyph_invariants.py --font fonts/seal-individual/PanoramaGothicSealIndividual-Regular.ttf --output fonts/seal-individual/invariants-check.json
	$(PYTHON) tools/verify_normalized_sizes.py --font fonts/seal-individual/PanoramaGothicSealIndividual-Regular.ttf --registry design/quality/accepted-geometry.json --output fonts/seal-individual/size-check.json

seal-variable:
	$(PYTHON) tools/verify_source_reviews.py --output fonts/seal-individual-variable/source-review-check.json
	$(PYTHON) tools/build_stroke_variable.py --require-visual-match
	$(PYTHON) tools/render_weight_demo.py --font fonts/seal-individual-variable/PanoramaGothicSealIndividualVariable.ttf --output fonts/seal-individual-variable
	$(PYTHON) tools/verify_glyph_invariants.py --font fonts/seal-individual-variable/PanoramaGothicSealIndividualVariable.ttf --output fonts/seal-individual-variable/invariants-check.json
	$(PYTHON) tools/verify_normalized_sizes.py --font fonts/seal-individual-variable/PanoramaGothicSealIndividualVariable.ttf --registry design/quality/accepted-geometry.json --output fonts/seal-individual-variable/size-check.json

seal-progress:
	$(PYTHON) tools/seal_repertoire_status.py

