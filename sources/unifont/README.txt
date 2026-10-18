GNU Unifont 18.0.01 source subset
================================

Official upstream release: 16 September 2026
https://unifoundry.com/pub/unifont/unifont-18.0.01/unifont-18.0.01.tar.gz
Archive SHA-256: eab60847aac34c8768765cecc7821faf50de2636187b452b9b5fa50a12b00bc3

source-manifest.json records original source file hashes, exclusions,
copyright/license locations and the clean source repertoire. The clean HEX
contains 78,191 authentic graphic/space drawings present in the pinned Unicode
draft, including 338 Unicode-18 additions. It contains no Unicode-19 additions.
It must not be advertised as complete Unicode-19 coverage.

The drawings are 8 by 16 or 16 by 16 pixel bitmaps. Their vector conversion
retains the coarse grid. The format supplies no contextual script shaping.

Placeholder protection
---------------------
The upstream font/plane00/README distinguishes original drawings from the
unassigned/private-use/control display files. font/plane01/README explicitly
states that noscript and unassigned files contain generated hexadecimal labels.
Those files, precompiled fonts, nonprinting illustrations and constructed-script
private-use collections are excluded. The genuine drawing files are then
filtered using the pinned UnicodeData categories; invisible non-space drawings
are excluded. Forty-three conflicting Japanese regional variants are omitted
in favor of the first Chinese source drawing, with their codepoints recorded.

Licensing
---------
The upstream COPYING dual-licenses the font files under SIL OFL 1.1 and GNU
GPL 2 or later with the font embedding exception. Its separate non-font
utilities are GPL 2 or later. Exact license texts and original copyright
attribution are saved in ../../licenses/unifont (relative to this directory,
the repository path is licenses/unifont). The Izumi plane-2 README additionally
identifies that file's drawings as public domain. No upstream utility code is
used by our independent Python converter.

Rebuild from repository root
----------------------------
python tools/prepare_unifont_sources.py \
  --hex \
  sources/unifont/unifont-18.0.01/font/plane00/unifont-base.hex \
  sources/unifont/unifont-18.0.01/font/plane00/wqy.hex \
  sources/unifont/unifont-18.0.01/font/plane00/hangul-syllables.hex \
  sources/unifont/unifont-18.0.01/font/plane00/spaces.hex \
  sources/unifont/unifont-18.0.01/font/plane01/plane01.hex \
  sources/unifont/unifont-18.0.01/font/plane01/plane01-space.hex \
  sources/unifont/unifont-18.0.01/font/plane02/zh-plane02.hex \
  sources/unifont/unifont-18.0.01/font/plane02/izmg16-plane02.hex \
  sources/unifont/unifont-18.0.01/font/plane03/zh-plane03.hex \
  sources/unifont/unifont-18.0.01/font/plane03/jp-plane03.hex \
  --ucd reference/ucd-19-draft/UnicodeData.txt \
  --output sources/unifont/unifont-18.0.01-clean.hex --prefer-first
