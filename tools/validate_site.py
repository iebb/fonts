#!/usr/bin/env python3
"""Validate static catalog links and the Latin-only specimen boundary."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).parents[1]
HTML_FILES = (ROOT / "index.html", ROOT / "Monaco GP Sans" / "index.html")
FORBIDDEN_RANGES = (
    (0x0370, 0x03FF, "Greek"),
    (0x0400, 0x052F, "Cyrillic"),
    (0x3040, 0x30FF, "Kana"),
)
EXPECTED_FEATURES = {"ss01", "ss03", "ss06", "ss07", "ss08", "ss09"}
COMPARISONS = (
    ("ss01", "a", "single-storey-a"),
    ("ss03", "ACSM", "poster-capitals"),
    ("ss06", "0", "poster-zero"),
    ("ss07", "1", "poster-one"),
    ("ss08", "3", "poster-three"),
    ("ss09", "69", "poster-six-nine"),
)


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        for attribute in ("href", "src"):
            if values.get(attribute):
                self.references.append(values[attribute])


def validate_html(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    parser = LinkParser()
    parser.feed(source)

    for reference in parser.references:
        parsed = urlsplit(reference)
        if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("data:"):
            continue
        target = (path.parent / unquote(parsed.path)).resolve()
        if parsed.path.endswith("/"):
            target /= "index.html"
        assert target.is_file(), f"broken local reference in {path}: {reference} -> {target}"


def validate_specimen_text() -> None:
    specimen = (ROOT / "Monaco GP Sans" / "index.html").read_text(encoding="utf-8")
    for start, end, label in FORBIDDEN_RANGES:
        offenders = sorted({char for char in specimen if start <= ord(char) <= end})
        assert not offenders, f"specimen contains {label}: {offenders}"

    controls = set(re.findall(r'data-feature="(ss\d\d)"', specimen))
    assert controls == EXPECTED_FEATURES, (controls, EXPECTED_FEATURES)
    assert 'class="live-font poster-capitals"' in specimen
    assert 'class="poster-date poster-date-figures"' in specimen
    for tag, text, alternate_class in COMPARISONS:
        marker = f"{tag} /"
        start = specimen.index(marker)
        end = specimen.index("</article>", start)
        card = specimen[start:end]
        assert card.count(f">{text}</p>") == 2, (tag, text)
        assert f'class="current-weight {alternate_class}">{text}</p>' in card


def main() -> None:
    for path in HTML_FILES:
        validate_html(path)
    validate_specimen_text()
    css = (ROOT / "Monaco GP Sans" / "specimen.css").read_text(encoding="utf-8")
    assert css.count("@font-face") == 2
    assert 'font-family: "Monaco GP Sans"' in css
    assert 'font-family: "Monaco GP Sans Outline"' in css
    css_features = set(re.findall(r'"(ss\d\d)" 1', css))
    assert css_features == EXPECTED_FEATURES, (css_features, EXPECTED_FEATURES)
    assert "v=1.003" in css
    print("PASS: static catalog links")
    print("PASS: specimen contains no Greek, Cyrillic, or Kana")
    print("PASS: both independent webfont families are declared")
    print("PASS: exact stylistic-set controls and paired comparisons")


if __name__ == "__main__":
    main()
