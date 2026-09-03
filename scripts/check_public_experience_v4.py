#!/usr/bin/env python3
"""Fail-closed static public-experience gate for SZL browser surfaces.

This checker intentionally uses only the Python standard library so it can run
in every repository. It validates committed HTML/CSS evidence; it does not
pretend to replace browser/device testing or live runtime verification.
"""
from __future__ import annotations

import argparse
import html.parser
import pathlib
import re
import sys
from dataclasses import dataclass, field


@dataclass
class Page:
    path: pathlib.Path
    viewport: str | None = None
    lang: str | None = None
    headings: list[str] = field(default_factory=list)
    links: int = 0
    buttons: int = 0
    form_controls: int = 0
    has_skip_link: bool = False
    has_main: bool = False


class PageParser(html.parser.HTMLParser):
    def __init__(self, page: Page) -> None:
        super().__init__()
        self.page = page

    def handle_starttag(self, tag: str, attrs):
        values = dict(attrs)
        if tag == "html":
            self.page.lang = values.get("lang")
        elif tag == "meta" and values.get("name", "").casefold() == "viewport":
            self.page.viewport = values.get("content")
        elif tag == "main" or values.get("role") == "main":
            self.page.has_main = True
        elif tag == "a":
            self.page.links += 1
            href = values.get("href", "")
            classes = set(values.get("class", "").split())
            if href.startswith("#") and ("skip-link" in classes or "skip" in " ".join(classes).lower()):
                self.page.has_skip_link = True
        elif tag == "button" or values.get("role") == "button":
            self.page.buttons += 1
        elif tag in {"input", "select", "textarea"}:
            self.page.form_controls += 1
        elif tag in {"h1", "h2", "h3"}:
            self.page.headings.append(tag)


def read(paths: list[pathlib.Path], suffixes: set[str]) -> str:
    chunks = []
    for path in paths:
        if path.is_file() and path.suffix.lower() in suffixes:
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="HTML/CSS files or directories to validate")
    parser.add_argument("--allow-no-skip-link", action="store_true")
    args = parser.parse_args()

    roots = [pathlib.Path(raw) for raw in args.paths]
    missing = [str(path) for path in roots if not path.exists()]
    if missing:
        raise SystemExit("missing public-experience path(s): " + ", ".join(missing))

    files: list[pathlib.Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        else:
            files.extend(path for path in root.rglob("*") if path.is_file())

    html_files = sorted({path for path in files if path.suffix.lower() in {".html", ".htm"}})
    css_files = sorted({path for path in files if path.suffix.lower() == ".css"})
    if not html_files:
        raise SystemExit("no HTML files found in supplied public-experience paths")

    failures: list[str] = []
    pages: list[Page] = []
    for path in html_files:
        page = Page(path=path)
        source = path.read_text(encoding="utf-8")
        PageParser(page).feed(source)
        pages.append(page)
        if not page.lang:
            failures.append(f"{path}: <html> must declare lang")
        viewport = (page.viewport or "").replace(" ", "").lower()
        if "width=device-width" not in viewport:
            failures.append(f"{path}: viewport must include width=device-width")
        if not page.has_main:
            failures.append(f"{path}: needs a <main> or role=main landmark")
        if "h1" not in page.headings:
            failures.append(f"{path}: needs a primary h1")
        if not args.allow_no_skip_link and page.links + page.buttons + page.form_controls >= 6 and not page.has_skip_link:
            failures.append(f"{path}: interactive page needs an in-page skip link")

    html_text = read(html_files, {".html", ".htm"})
    css_text = read(css_files, {".css"}) + "\n" + "\n".join(
        re.findall(r"<style[^>]*>(.*?)</style>", html_text, flags=re.I | re.S)
    )
    compact_css = re.sub(r"\s+", " ", css_text).lower()

    required_css_signals = {
        "horizontal-overflow containment": any(token in compact_css for token in ("overflow-x:hidden", "overflow-x: hidden", "overflow-x:clip", "overflow-x: clip")),
        "mobile breakpoint": "@media" in compact_css and ("max-width" in compact_css or "width <" in compact_css),
        "visible keyboard focus": ":focus-visible" in compact_css,
        "reduced-motion support": "prefers-reduced-motion" in compact_css,
        "touch target evidence": bool(re.search(r"min-(?:height|block-size)\s*:\s*(?:44|48)px", compact_css)),
        "safe-area support": "safe-area-inset" in compact_css,
    }
    for label, present in required_css_signals.items():
        if not present:
            failures.append(f"CSS contract missing: {label}")

    form_pages = [page for page in pages if page.form_controls]
    if form_pages and not re.search(r"font-size\s*:\s*(?:max\(\s*16px|16px)", compact_css):
        failures.append("CSS contract missing: 16px-or-larger mobile form-control text evidence")

    if failures:
        print("Public Experience Frontier v4 gate FAILED")
        for failure in failures:
            print(" -", failure)
        return 1

    print("Public Experience Frontier v4 gate PASSED")
    print(f" - HTML pages: {len(html_files)}")
    print(f" - CSS files: {len(css_files)}")
    print(" - viewport/lang/main/h1 contract present")
    print(" - mobile overflow/focus/motion/touch/safe-area evidence present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
