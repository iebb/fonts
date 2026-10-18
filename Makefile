PYTHON ?= python3

.PHONY: test noto supplement audit seal-strokes seal-variable

test:
	$(PYTHON) -m unittest discover -s tests -v

noto:
	$(PYTHON) tools/bundle_noto.py

supplement:
	$(PYTHON) tools/build_fonts.py --help

audit:
	$(PYTHON) tools/audit_coverage.py --help

seal-strokes:
	$(PYTHON) tools/track_centerlines.py --single-images
	$(PYTHON) tools/build_stroke_font.py --source-root design/strokes-individual --output fonts/seal-individual --family "Panorama Gothic Seal Individual" --font-stroke-width 43 --require-visual-match
	$(PYTHON) tools/render_stroke_font.py --font fonts/seal-individual/PanoramaGothicSealIndividual-Regular.ttf --output fonts/seal-individual
	$(PYTHON) tools/render_stroke_demo.py --source design/strokes-individual/U3D001.json --output fonts/seal-individual
	$(PYTHON) tools/audit_stroke_sample.py

seal-variable:
	$(PYTHON) tools/build_stroke_variable.py
	$(PYTHON) tools/render_weight_demo.py --font fonts/seal-individual-variable/PanoramaGothicSealIndividualVariable.ttf --output fonts/seal-individual-variable

