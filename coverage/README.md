# Character coverage audit

Assigned graphic and spacing characters in the pinned Unicode development snapshot

Real Unicode cmap entries and HEX records; diagnostics and sources with coverage_eligible=false excluded. This is encoding coverage, not proof of correct glyph design, sans-serif style, shaping, mark attachment, or variation-sequence support.

Exactly the installed Noto fonts listed below; this does not claim to audit the latest Noto repositories worldwide.

UCD commit: `4fd8eca90b30aa4c72543ccddb4c15d05becdf8d`.

Graphic target: **172,636** characters. Output: **156,434** covered; **16,202** missing.

Installed Noto Sans: 69,981 covered; all installed Noto: 78,872 covered.

Characters introduced since Unicode 16 missing from all installed Noto: **22,981**; covered in output: **6,779**.

## Coverage by Unicode age

| Age | Target | Installed Noto Sans | Any installed Noto | Output | Missing output |
|---|---:|---:|---:|---:|---:|
| 1.1 | 27,491 | 27,490 | 27,490 | 27,491 | 0 |
| 10.0 | 8,518 | 682 | 736 | 8,518 | 0 |
| 11.0 | 683 | 526 | 657 | 683 | 0 |
| 12.0 | 545 | 286 | 409 | 545 | 0 |
| 12.1 | 1 | 1 | 1 | 1 | 0 |
| 13.0 | 5,930 | 290 | 370 | 5,930 | 0 |
| 14.0 | 836 | 0 | 40 | 836 | 0 |
| 15.0 | 4,482 | 0 | 20 | 4,482 | 0 |
| 15.1 | 627 | 0 | 0 | 627 | 0 |
| 16.0 | 5,185 | 0 | 7 | 1,190 | 3,995 |
| 17.0 | 4,803 | 0 | 7 | 4,803 | 0 |
| 18.0 | 13,007 | 0 | 0 | 800 | 12,207 |
| 2.0 | 11,373 | 11,205 | 11,373 | 11,373 | 0 |
| 2.1 | 2 | 2 | 2 | 2 | 0 |
| 3.0 | 10,302 | 10,277 | 10,302 | 10,302 | 0 |
| 3.1 | 44,841 | 3,294 | 3,751 | 44,841 | 0 |
| 3.2 | 1,012 | 997 | 997 | 1,012 | 0 |
| 4.0 | 1,222 | 982 | 982 | 1,222 | 0 |
| 4.1 | 1,273 | 1,095 | 1,167 | 1,273 | 0 |
| 5.0 | 1,369 | 1,369 | 1,369 | 1,369 | 0 |
| 5.1 | 1,623 | 1,616 | 1,623 | 1,623 | 0 |
| 5.2 | 6,647 | 2,541 | 2,545 | 6,647 | 0 |
| 6.0 | 2,088 | 1,287 | 1,898 | 2,088 | 0 |
| 6.1 | 731 | 718 | 731 | 731 | 0 |
| 6.2 | 1 | 1 | 1 | 1 | 0 |
| 7.0 | 2,829 | 2,819 | 2,829 | 2,829 | 0 |
| 8.0 | 7,716 | 1,957 | 2,066 | 7,716 | 0 |
| 9.0 | 7,499 | 546 | 7,499 | 7,499 | 0 |

Full per-codepoint priorities are in `new-missing-noto.tsv`; exact source names, versions, hashes, and script/block summaries are in `coverage.json`.

A development directory may contain different file version headers. The recorded per-file headers and hashes are authoritative; a 19.0 Blocks header alone does not establish any assigned Age=19.0 characters.
