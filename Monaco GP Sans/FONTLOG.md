# FONTLOG for Monaco GP Sans

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
  variable kerning, mark positioning, tabular figures, and `ss01`–`ss06`.
- Verified exact outline and metric parity with the frozen inputs for every
  retained encoded glyph at weights 100, 200, …, 900.

## Provenance

Monaco GP Sans is a renamed and modified type family based primarily on Jost.
Selected poster-figure geometry is informed by Montserrat. Both upstream
projects are distributed under the SIL Open Font License 1.1. Copyright and
license notices remain embedded in the font binaries and in `OFL.txt`.

Frozen source SHA-256 values:

- Filled: `dd5a970d58c862f21a9370e0870068b829fbd963171ee697fc838cc6346e7f65`
- Outline: `b37bdf5d21de2d7e110197a916a1277895c8d0d6c53fb4e5dfa024ee86e70a99`
