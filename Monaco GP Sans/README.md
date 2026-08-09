# Monaco GP Sans

Monaco GP Sans is a geometric variable display family shaped by 1930s Monaco
racing posters. The catalog release contains two independent Latin-only fonts:

- **Monaco GP Sans** — filled geometry
- **Monaco GP Sans Outline** — a true outlined companion, not a CSS stroke

Both fonts expose a continuous `wght` axis from 100 to 900 and nine named
instances at 100, 200, …, 900. The release preserves kerning, mark positioning,
tabular figures, and the named OpenType alternates below.

| Feature | Name | Forms |
| --- | --- | --- |
| `ss01` | Single-storey a | `a` |
| `ss02` | Poster S | `S Ś Ŝ Ş Š Ș` |
| `ss03` | Poster Figures | `0 1 3 6 9` |
| `ss04` | Expanding M | `M` |
| `ss05` | Barless A | `A` and accented A forms |
| `ss06` | Poster C | `C Ć Ĉ Ċ Č Ç` |
| `tnum` | Tabular Figures | figures |

This catalog build deliberately excludes Greek, Cyrillic, Japanese, and
fullwidth forms. It contains 437 encoded Latin/Common characters in each font.

## Downloads

- [Monaco GP Sans variable TTF](./fonts/MonacoGPSans%5Bwght%5D.ttf)
- [Monaco GP Sans variable WOFF2](./fonts/MonacoGPSans%5Bwght%5D.woff2)
- [Monaco GP Sans Outline variable TTF](./fonts/MonacoGPSansOutline%5Bwght%5D.ttf)
- [Monaco GP Sans Outline variable WOFF2](./fonts/MonacoGPSansOutline%5Bwght%5D.woff2)
- [Release manifest](./fonts/release-manifest.json)

## Web use

```css
@font-face {
  font-family: "Monaco GP Sans";
  src: url("MonacoGPSans[wght].woff2") format("woff2-variations");
  font-style: normal;
  font-weight: 100 900;
}

@font-face {
  font-family: "Monaco GP Sans Outline";
  src: url("MonacoGPSansOutline[wght].woff2") format("woff2-variations");
  font-style: normal;
  font-weight: 100 900;
}
```

Use the standard `font-weight` property or `font-variation-settings: "wght"`
with any value from 100 through 900. Switch `font-family` to select Filled or
Outline; there is no public fill axis.

## Rebuild the catalog binaries

The build is intentionally pinned to the frozen Monaco Vitesse 2.200 source
binaries. The source hashes are embedded in the build script, so an unexpected
input fails closed.

```sh
python3 -m pip install -r ../requirements.txt
python3 tools/build_latin_release.py \
  --filled-source /path/to/MonacoVitesse-Filled[wght].ttf \
  --outline-source /path/to/MonacoVitesse-Outline[wght].ttf

python3 tools/validate_release.py \
  --filled-source /path/to/MonacoVitesse-Filled[wght].ttf \
  --outline-source /path/to/MonacoVitesse-Outline[wght].ttf
```

Validation checks names, script exclusions, the `wght` axis, all nine named
weights, feature retention, and TTF/WOFF2 parity. Filled geometry and metrics
are compared with the frozen input at every named weight; every retained
Outline glyph is compared at 50-unit intervals across the full axis.

## License

Monaco GP Sans is distributed under the [SIL Open Font License 1.1](./OFL.txt).
See [FONTLOG.md](./FONTLOG.md) for modification history and provenance.
