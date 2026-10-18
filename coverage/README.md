# Character coverage audit

Assigned graphic and spacing characters in the pinned Unicode development snapshot

Real Unicode cmap entries and HEX records; diagnostics and sources with coverage_eligible=false excluded. This is encoding coverage, not proof of correct glyph design, sans-serif style, shaping, mark attachment, or variation-sequence support.

Exactly the installed Noto fonts listed below; this does not claim to audit the latest Noto repositories worldwide.

UCD commit: `03f128b76c2917bba02f497fccb44ba833855700`.

Graphic target: **172,636** characters. Output: **154,287** covered; **18,349** missing.

Installed Noto Sans: 69,981 covered; all installed Noto: 78,872 covered.

Characters introduced since Unicode 16 missing from all installed Noto: **22,981**; covered in output: **6,617**.

## Coverage by Unicode age

| Age | Target | Installed Noto Sans | Any installed Noto | Output | Missing output |
|---|---:|---:|---:|---:|---:|
| 1.1 | 27,491 | 27,490 | 27,490 | 27,491 | 0 |
| 10.0 | 8,518 | 682 | 736 | 8,464 | 54 |
| 11.0 | 683 | 526 | 657 | 557 | 126 |
| 12.0 | 545 | 286 | 409 | 382 | 163 |
| 12.1 | 1 | 1 | 1 | 1 | 0 |
| 13.0 | 5,930 | 290 | 370 | 5,872 | 58 |
| 14.0 | 836 | 0 | 40 | 767 | 69 |
| 15.0 | 4,482 | 0 | 20 | 4,461 | 21 |
| 15.1 | 627 | 0 | 0 | 627 | 0 |
| 16.0 | 5,185 | 0 | 7 | 1,043 | 4,142 |
| 17.0 | 4,803 | 0 | 7 | 4,796 | 7 |
| 18.0 | 13,007 | 0 | 0 | 778 | 12,229 |
| 2.0 | 11,373 | 11,205 | 11,373 | 11,266 | 107 |
| 2.1 | 2 | 2 | 2 | 2 | 0 |
| 3.0 | 10,302 | 10,277 | 10,302 | 10,278 | 24 |
| 3.1 | 44,841 | 3,294 | 3,751 | 44,384 | 457 |
| 3.2 | 1,012 | 997 | 997 | 1,005 | 7 |
| 4.0 | 1,222 | 982 | 982 | 1,222 | 0 |
| 4.1 | 1,273 | 1,095 | 1,167 | 1,201 | 72 |
| 5.0 | 1,369 | 1,369 | 1,369 | 1,369 | 0 |
| 5.1 | 1,623 | 1,616 | 1,623 | 1,618 | 5 |
| 5.2 | 6,647 | 2,541 | 2,545 | 6,643 | 4 |
| 6.0 | 2,088 | 1,287 | 1,898 | 1,478 | 610 |
| 6.1 | 731 | 718 | 731 | 718 | 13 |
| 6.2 | 1 | 1 | 1 | 1 | 0 |
| 7.0 | 2,829 | 2,819 | 2,829 | 2,819 | 10 |
| 8.0 | 7,716 | 1,957 | 2,066 | 7,618 | 98 |
| 9.0 | 7,499 | 546 | 7,499 | 7,426 | 73 |

Full per-codepoint priorities are in `new-missing-noto.tsv`; exact source names, versions, hashes, and script/block summaries are in `coverage.json`.

A development directory may contain different file version headers. The recorded per-file headers and hashes are authoritative; a 19.0 Blocks header alone does not establish any assigned Age=19.0 characters.
