#!/usr/bin/env python3
"""Fail-closed host-isolation checks for the Hugging Face organization card."""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT_ID = "szl-hf-org-card"
ROOT_SELECTOR = f"#{ROOT_ID}"
CLASS_PREFIX = "szl-hf-"
BODY_MARKER = "company-front-door"
CANONICAL_ASSET_URL = (
    "https://szlholdings-readme.static.hf.space/"
    "assets/evidence-lattice-v2.webp"
)
CANONICAL_DEPLOYMENT_URL = (
    "https://szlholdings-readme.static.hf.space/deployment.json"
)
VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
CSS_CLASS = re.compile(r"(?<![A-Za-z0-9_-])\.([A-Za-z_][A-Za-z0-9_-]*)")
CSS_ID = re.compile(r"(?<![A-Za-z0-9_-])#([A-Za-z_][A-Za-z0-9_-]*)")
CSS_COLOR = re.compile(r"^[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$|^[0-9a-fA-F]{4}(?:[0-9a-fA-F]{4})?$")
CSS_EXTERNAL = re.compile(r"(?i)(?:@import\b|url\s*\()")
ROOT_OVERFLOW_MASK = re.compile(
    rf"(?is)^\s*{re.escape(ROOT_SELECTOR)}(?:\[[^]]+\])?\s*$"
)


class OrgCardParser(HTMLParser):
    """Collect structural facts while tracking the isolated body subtree."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root_count = 0
        self.root_embed_safe = False
        self.body_marker = ""
        self.h1_count = 0
        self.main_count = 0
        self.class_tokens: set[str] = set()
        self.ids: list[str] = []
        self.hrefs: list[str] = []
        self.images: list[dict[str, str]] = []
        self.styles: list[str] = []
        self.inline_style_count = 0
        self.forbidden_elements: list[str] = []
        self.outside_root: list[str] = []
        self._in_body = False
        self._root_depth = 0
        self._stack: list[tuple[str, bool]] = []
        self._in_style = False
        self._style_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {key: str(value or "") for key, value in attrs}
        is_root = values.get("id") == ROOT_ID
        inside_root = self._root_depth > 0 or is_root

        if tag == "body":
            self._in_body = True
            self.body_marker = values.get("data-szl-surface", "")
        elif self._in_body and not inside_root:
            self.outside_root.append(tag)

        if is_root:
            self.root_count += 1
            self.root_embed_safe = (
                values.get("data-szl-embed-safe", "").casefold() == "true"
            )

        classes = values.get("class", "").split()
        self.class_tokens.update(classes)
        if values.get("id"):
            self.ids.append(values["id"])
        if values.get("style"):
            self.inline_style_count += 1

        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"])
        if tag == "img":
            self.images.append(values)
        if tag in {"script", "link", "base"}:
            self.forbidden_elements.append(tag)
        if tag == "h1" and inside_root:
            self.h1_count += 1
        if tag == "main" and inside_root:
            self.main_count += 1
        if tag == "style":
            self._in_style = True
            self._style_parts = []

        if tag not in VOID_ELEMENTS:
            self._stack.append((tag, inside_root))
            if inside_root:
                self._root_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "style" and self._in_style:
            self.styles.append("".join(self._style_parts))
            self._style_parts = []
            self._in_style = False
        if tag == "body":
            self._in_body = False
        if self._stack:
            opened_tag, inside_root = self._stack.pop()
            if opened_tag != tag:
                self.outside_root.append(f"mismatched:{opened_tag}/{tag}")
            if inside_root:
                self._root_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self._style_parts.append(data)


def _skip_css_string(source: str, position: int) -> int:
    quote = source[position]
    position += 1
    while position < len(source):
        if source[position] == "\\":
            position += 2
        elif source[position] == quote:
            return position + 1
        else:
            position += 1
    raise ValueError("unterminated CSS string")


def css_blocks(source: str) -> list[tuple[str, str]]:
    """Return top-level CSS block preludes and bodies, rejecting bad balance."""

    cleaned = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    blocks: list[tuple[str, str]] = []
    position = 0
    while position < len(cleaned):
        while position < len(cleaned) and (
            cleaned[position].isspace() or cleaned[position] == ";"
        ):
            position += 1
        if position >= len(cleaned):
            break
        start = position
        while position < len(cleaned) and cleaned[position] not in "{;":
            if cleaned[position] in {'"', "'"}:
                position = _skip_css_string(cleaned, position)
            else:
                position += 1
        if position >= len(cleaned):
            if cleaned[start:].strip():
                raise ValueError("CSS statement lacks a terminator")
            break
        if cleaned[position] == ";":
            statement = cleaned[start : position + 1].strip()
            if statement:
                blocks.append((statement, ""))
            position += 1
            continue
        prelude = cleaned[start:position].strip()
        depth = 1
        body_start = position + 1
        position = body_start
        while position < len(cleaned) and depth:
            if cleaned[position] in {'"', "'"}:
                position = _skip_css_string(cleaned, position)
            elif cleaned[position] == "{":
                depth += 1
                position += 1
            elif cleaned[position] == "}":
                depth -= 1
                position += 1
            else:
                position += 1
        if depth:
            raise ValueError(f"unclosed CSS block: {prelude}")
        blocks.append((prelude, cleaned[body_start : position - 1]))
    return blocks


def split_selector_members(value: str) -> list[str]:
    members: list[str] = []
    start = 0
    parentheses = 0
    brackets = 0
    quote = ""
    position = 0
    while position < len(value):
        char = value[position]
        if quote:
            if char == "\\":
                position += 2
                continue
            if char == quote:
                quote = ""
        elif char in {'"', "'"}:
            quote = char
        elif char == "(":
            parentheses += 1
        elif char == ")":
            parentheses -= 1
        elif char == "[":
            brackets += 1
        elif char == "]":
            brackets -= 1
        elif char == "," and not parentheses and not brackets:
            members.append(value[start:position].strip())
            start = position + 1
        position += 1
    members.append(value[start:].strip())
    return members


def selector_failures(source: str) -> list[str]:
    failures: list[str] = []
    selector_count = 0

    def inspect(block_source: str) -> None:
        nonlocal selector_count
        for prelude, body in css_blocks(block_source):
            if prelude.startswith("@"):
                keyword = prelude.split(None, 1)[0].casefold()
                if keyword not in {"@media", "@supports", "@layer"}:
                    failures.append(f"unsupported CSS at-rule: {keyword}")
                elif body:
                    inspect(body)
                continue
            for selector in split_selector_members(prelude):
                selector_count += 1
                boundary = selector[len(ROOT_SELECTOR) : len(ROOT_SELECTOR) + 1]
                if not selector.startswith(ROOT_SELECTOR) or (
                    boundary and (boundary.isalnum() or boundary in "_-")
                ):
                    failures.append(f"unrooted CSS selector: {selector}")
                if ":root" in selector or re.search(r"(?<![-\w])(html|body)(?![-\w])", selector):
                    failures.append(f"host-level CSS selector: {selector}")
            if ROOT_OVERFLOW_MASK.fullmatch(prelude) and re.search(
                r"(?i)\boverflow(?:-[xy])?\s*:\s*(?:hidden|clip)\b", body
            ):
                failures.append("org-card root must not mask overflow")

    try:
        inspect(source)
    except ValueError as exc:
        failures.append(f"CSS parse failed: {exc}")
    if not selector_count:
        failures.append("no CSS selectors were evaluated")
    return failures


def _safe_href(value: str) -> bool:
    if value.startswith("#"):
        return len(value) > 1 and " " not in value
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
    )


def validate_document(document: str) -> list[str]:
    failures: list[str] = []
    parser = OrgCardParser()
    try:
        parser.feed(document)
        parser.close()
    except Exception as exc:
        return [f"HTML parse failed: {type(exc).__name__}: {exc}"]

    if parser.root_count != 1:
        failures.append(f"expected one isolated root, observed {parser.root_count}")
    if not parser.root_embed_safe:
        failures.append("isolated root must declare data-szl-embed-safe=true")
    if parser.body_marker != BODY_MARKER:
        failures.append(f"body marker must be {BODY_MARKER}")
    if parser.outside_root:
        failures.append(f"body content escaped the isolated root: {parser.outside_root}")
    if parser.h1_count != 1 or parser.main_count != 1:
        failures.append("isolated card requires exactly one h1 and one main")
    if len(parser.styles) != 1:
        failures.append(f"expected one inline style block, observed {len(parser.styles)}")
    if parser.inline_style_count:
        failures.append("inline style attributes are forbidden")
    if parser.forbidden_elements:
        failures.append(
            f"script, link, and base elements are forbidden: {parser.forbidden_elements}"
        )

    bad_classes = sorted(
        token for token in parser.class_tokens if not token.startswith(CLASS_PREFIX)
    )
    if bad_classes:
        failures.append(f"unscoped class tokens: {bad_classes}")
    duplicate_ids = sorted({value for value in parser.ids if parser.ids.count(value) > 1})
    bad_ids = sorted(value for value in parser.ids if not value.startswith(CLASS_PREFIX))
    if duplicate_ids:
        failures.append(f"duplicate DOM ids: {duplicate_ids}")
    if bad_ids:
        failures.append(f"unscoped DOM ids: {bad_ids}")

    bad_hrefs = sorted(value for value in parser.hrefs if not _safe_href(value))
    if bad_hrefs:
        failures.append(f"unsafe navigation targets: {bad_hrefs}")
    fragments = {value[1:] for value in parser.hrefs if value.startswith("#")}
    missing_fragments = sorted(fragments - set(parser.ids))
    if missing_fragments:
        failures.append(f"fragment targets are missing: {missing_fragments}")

    if len(parser.images) != 1:
        failures.append(f"expected one reviewed image, observed {len(parser.images)}")
    elif parser.images[0] != {
        "class": "szl-hf-hero-art",
        "src": CANONICAL_ASSET_URL,
        "alt": "",
        "width": "1800",
        "height": "776",
        "fetchpriority": "high",
        "decoding": "async",
    }:
        failures.append("hero image contract drifted from the canonical asset")

    css = "\n".join(parser.styles)
    if CSS_EXTERNAL.search(css):
        failures.append("CSS imports and URL dependencies are forbidden")
    failures.extend(selector_failures(css))
    bad_css_classes = sorted(
        {
            match.group(1)
            for match in CSS_CLASS.finditer(css)
            if not match.group(1).startswith(CLASS_PREFIX)
        }
    )
    bad_css_ids = sorted(
        {
            match.group(1)
            for match in CSS_ID.finditer(css)
            if not match.group(1).startswith(CLASS_PREFIX)
            and not CSS_COLOR.fullmatch(match.group(1))
        }
    )
    if bad_css_classes:
        failures.append(f"unscoped CSS classes: {bad_css_classes}")
    if bad_css_ids:
        failures.append(f"unscoped CSS ids: {bad_css_ids}")

    normalized = re.sub(r"\s+", " ", css)
    required_patterns = {
        "44px touch token": r"--tap:\s*44px",
        "48px CTA": rf"{re.escape(ROOT_SELECTOR)} \.szl-hf-button \{{[^}}]*display:\s*inline-flex\s*!important;[^}}]*min-height:\s*48px",
        "44px navigation": rf"{re.escape(ROOT_SELECTOR)} nav a \{{[^}}]*min-height:\s*var\(--tap\)",
        "one-column mobile CTA": rf"@media \(max-width:\s*640px\).*?{re.escape(ROOT_SELECTOR)} \.szl-hf-actions \.szl-hf-button \{{[^}}]*width:\s*100%\s*!important",
    }
    for label, pattern in required_patterns.items():
        if not re.search(pattern, normalized):
            failures.append(f"missing {label} contract")
    for marker in (
        "prefers-reduced-motion",
        "prefers-contrast",
        "forced-colors",
        "safe-area-inset-top",
        "safe-area-inset-right",
        "safe-area-inset-bottom",
        "safe-area-inset-left",
        "overflow-wrap: anywhere",
    ):
        if marker not in css:
            failures.append(f"missing CSS marker: {marker}")
    if re.search(r"(?i)overflow-x\s*:\s*(?:hidden|auto|clip)", css):
        failures.append("horizontal overflow must remain observable")

    if 'href="#szl-hf-main"' not in document:
        failures.append("keyboard skip link is missing")
    if CANONICAL_DEPLOYMENT_URL not in document:
        failures.append("absolute deployment source binding is missing")
    return failures


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    source = root / "huggingface/org-card/index.html"
    failures = validate_document(source.read_text(encoding="utf-8"))
    report = {
        "schema": "szl.hf-org-card-embed-check/v2",
        "state": "PASS" if not failures else "FAIL",
        "source": source.relative_to(root).as_posix(),
        "failures": failures,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
