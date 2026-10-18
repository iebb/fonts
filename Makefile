PYTHON ?= python3

.PHONY: test noto supplement audit

test:
	$(PYTHON) -m unittest discover -s tests -v

noto:
	$(PYTHON) tools/bundle_noto.py

supplement:
	$(PYTHON) tools/build_fonts.py --help

audit:
	$(PYTHON) tools/audit_coverage.py --help

