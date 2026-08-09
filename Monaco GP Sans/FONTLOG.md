# FONTLOG for Monaco GP Sans

## 1.003 — 2026-08-10

- Unified the barless A, poster C, poster S, and expanding M under `ss03`
  Poster Capitals so the core poster alphabet is selected as one design.
- Split poster figures into independent `ss06` zero, `ss07` one, `ss08`
  three, and combined `ss09` six-and-nine features.
- Rebuilt the poster three as a separated seven-style top and lower bowl,
  strengthened the poster zero slash to the font's own stem width, and aligned
  the principal Latin capitals to the shared cap line.
- Rebuilt the barless A-ogonek Outline from independently stable A and ogonek
  components so its attachment stays clean throughout the variable axis.
- Updated the browser specimen with identical default/alternate comparison
  strings for every stylistic set and exact release feature validation.

## 1.002 — 2026-08-09

- Reworked A and Barless A with parallel, uniform legs, cap-aligned apexes,
  and crossbar motion distributed across the weight axis.
- Made all accented Barless A forms reuse the same ten-point A body and
  pinned their exact Outline bands every 50 units, including Á, Å, and Ą.
- Stabilized 50-unit Outline interpolation samples for `£`, `a`, `b`, `g`,
  `p`, `c`, and `ç`.
- Kept the Poster S shelf semantically stable across the axis, without the
  mid-axis wedge, and redesigned the poster 3 with a straight seven-style top
  and rounded lower bowl.
- Retained the 1.001 AV/VA kerning schedule and expanded catalog validation to
  compare every Outline glyph at 50-unit intervals.

## 1.001 — 2026-08-09

- Preserved the default S Outline's stable native contour throughout the
  700–900 interval, removing the lower-left terminal kink at 700–800 and
  800–900 without changing the Filled S.
- Aligned A and Barless A's sharp apex exactly to the cap line at every named
  weight, including accented A-family bodies.
- Replaced the constant AV pair with a smooth optical schedule from -93 at
  Thin to -139 at Black, with matching AV/VA behavior for default, accented,
  and Barless A forms.
- Rebuilt and revalidated both Latin-only TTF/WOFF2 families at weights 100,
  200, …, 900; encoded Greek, Cyrillic, and Kana remain absent.

## 1.000 — 2026-08-09

- Renamed the filled family to **Monaco GP Sans** and the independent outline
  family to **Monaco GP Sans Outline**.
- Derived the catalog release directly from the hash-locked Monaco Vitesse
  2.200 public variable fonts.
- Limited encoded coverage to the audited Latin/Common repertoire: 437 encoded
  characters per family.
- Removed encoded Greek, Cyrillic, Katakana, halfwidth, and fullwidth forms.
- Preserved the continuous `wght` 100–900 axis, nine named weight instances,
  variable kerning, mark positioning, tabular figures, and stylistic sets.
- Verified exact outline and metric parity with the frozen inputs for every
  retained encoded glyph at weights 100, 200, …, 900.

## Provenance

Monaco GP Sans is a renamed and modified type family based primarily on Jost.
Selected poster-figure geometry is informed by Montserrat. Both upstream
projects are distributed under the SIL Open Font License 1.1. Copyright and
license notices remain embedded in the font binaries and in `OFL.txt`.

The exact frozen source SHA-256 values for each release are recorded in its
release manifest and hash-locked build script.
