#!/usr/bin/env python3
"""Fail-closed embed checks for the Hugging Face organization card."""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT_ID = "szl-hf-org-card"
CLASS_PREFIX = "szl-hf-"
BODY_MARKER = "company-front-door"

UNSCOPED_SELECTOR_PATTERNS = (
    re.compile(r"(?m)^\s*:root\s*\{"),
    re.compile(
        r"(?m)^\s*(?:html|body|main|header|footer|nav|section|article|aside|"
        r"h1|h2|h3|a|img|\*)\s*(?:,|\{)"
    ),
    re.compile(
        r"(?m)^\s*\.(?:hero|actions|button|card|primary|secondary|shell|nav|"
        r"path|product|truth|label|status-list)\b"
    ),
)
CSS_CLASS_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])\.([A-Za-z_][A-Za-z0-9_-]*)"
)

REQUIRED_CSS_MARKERS = (
    "#szl-hf-org-card .szl-hf-button {",
    "display: inline-flex !important;",
    "@media (max-width: 640px)",
    "width: 100% !important;",
)

MOBILE_CTA_PATTERN = re.compile(
    r"@media\s*\(max-width:\s*640px\)"
    r"[\s\S]*?#szl-hf-org-card\s+\.szl-hf-cta-row\s*\{"
    r"[\s\S]*?grid-template-columns:\s*1fr\s*;",
)


class OrgCardParser(HTMLParser):
    """Collect the narrow structural facts required by the embed contract."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root_count = 0
        self.root_embed_safe = False
        self.body_marker = ""
        self.h1_count = 0
        self.main_count = 0
        self.class_tokens: set[str] = set()
        self.hrefs: list[str] = []
        self.assets: list[tuple[str, str]] = []
        self.images: list[str] = []
        self.styles: list[str] = []
        self._in_style = False
        self._style_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {key: value for key, value in attrs}
        if tag == "body":
            self.body_marker = str(values.get("data-szl-surface") or "")
        if values.get("id") == ROOT_ID:
            self.root_count += 1
            self.root_embed_safe = (
                str(values.get("data-szl-embed-safe") or "").lower() == "true"
            )
        if tag == "h1":
            self.h1_count += 1
        if tag == "main":
            self.main_count += 1

        classes = str(values.get("class") or "").split()
        self.class_tokens.update(classes)

        href = values.get("href")
        if tag == "a" and href:
            self.hrefs.append(str(href))

        if tag == "img":
            source = str(values.get("src") or "")
            self.images.append(source)
            if source:
                self.assets.append(("img", source))
        elif tag == "script" and values.get("src"):
            self.assets.append(("script", str(values["src"])))
        elif tag == "link" and values.get("href"):
            self.assets.append(("link", str(values["href"])))

        if tag == "style":
            self._in_style = True
            self._style_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "style" and self._in_style:
            self.styles.append("".join(self._style_parts))
            self._style_parts = []
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self._style_parts.append(data)


def _is_allowed_navigation_target(value: str) -> bool:
    if value.startswith("#"):
        return len(value) > 1
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _is_allowed_asset_target(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"https", "data"} and bool(
        parsed.netloc or parsed.scheme == "data"
    )


def validate_document(document: str) -> list[str]:
    """Return fail-closed contract violations for one org-card source."""

    failures: list[str] = []
    parser = OrgCardParser()
    try:
        parser.feed(document)
        parser.close()
    except Exception as exc:
        return [f"HTML parse failed: {type(exc).__name__}: {exc}"]

    if parser.root_count != 1:
        failures.append(
            f"expected exactly one #{ROOT_ID} root, observed {parser.root_count}"
        )
    if not parser.root_embed_safe:
        failures.append("org-card root must declare data-szl-embed-safe=true")
    if parser.body_marker != BODY_MARKER:
        failures.append(
            f"body marker must be {BODY_MARKER}, observed "
            f"{parser.body_marker or 'missing'}"
        )
    if parser.h1_count != 1:
        failures.append(f"expected exactly one h1, observed {parser.h1_count}")
    if parser.main_count != 1:
        failures.append(f"expected exactly one main, observed {parser.main_count}")
    if len(parser.styles) != 1:
        failures.append(
            f"expected exactly one inline style block, observed {len(parser.styles)}"
        )

    bad_classes = sorted(
        token for token in parser.class_tokens if not token.startswith(CLASS_PREFIX)
    )
    if bad_classes:
        failures.append(f"unscoped class tokens are forbidden: {bad_classes}")

    bad_hrefs = sorted(
        value for value in parser.hrefs if not _is_allowed_navigation_target(value)
    )
    if bad_hrefs:
        failures.append(
            "navigation targets must be HTTPS or same-document fragments: "
            f"{bad_hrefs}"
        )

    bad_assets = sorted(
        f"{kind}:{value}"
        for kind, value in parser.assets
        if not _is_allowed_asset_target(value)
    )
    if bad_assets:
        failures.append(
            f"relative or unsafe runtime assets are forbidden: {bad_assets}"
        )

    # The prior production defect was a broken relative SVG in the first
    # viewport. Keep the embedded card independent of separately loaded art.
    if parser.images:
        failures.append(
            "embedded org card must not depend on image assets; "
            f"observed: {sorted(parser.images)}"
        )

    css = "\n".join(parser.styles)
    for pattern in UNSCOPED_SELECTOR_PATTERNS:
        match = pattern.search(css)
        if match:
            failures.append(
                f"unscoped CSS selector is forbidden: {match.group(0).strip()}"
            )

    bad_css_classes = sorted(
        {
            match.group(1)
            for match in CSS_CLASS_PATTERN.finditer(css)
            if not match.group(1).startswith(CLASS_PREFIX)
        }
    )
    if bad_css_classes:
        failures.append(
            "unscoped CSS class selectors are forbidden, including unused rules: "
            f"{bad_css_classes}"
        )

    for marker in REQUIRED_CSS_MARKERS:
        if marker not in css:
            failures.append(f"required embed CSS marker is missing: {marker}")

    if not MOBILE_CTA_PATTERN.search(css):
        failures.append(
            "mobile CTA contract must use a one-column grid inside the "
            "640px breakpoint"
        )

    if 'id="szl-hf-main"' not in document:
        failures.append("skip-link target #szl-hf-main is missing")
    if 'href="#szl-hf-main"' not in document:
        failures.append("keyboard skip link to #szl-hf-main is missing")
    if "prefers-reduced-motion" not in css:
        failures.append("reduced-motion handling is missing")
    if 'src="assets/' in document or "src='assets/" in document:
        failures.append("relative assets/ source remains in the org card")

    return failures


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    source_path = root / "huggingface/org-card/index.html"
    failures = validate_document(source_path.read_text(encoding="utf-8"))
    report = {
        "schema": "szl.hf-org-card-embed-check/v1",
        "state": "PASS" if not failures else "FAIL",
        "source": source_path.relative_to(root).as_posix(),
        "failures": failures,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
