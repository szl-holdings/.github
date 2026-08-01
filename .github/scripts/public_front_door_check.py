#!/usr/bin/env python3
"""Fail-closed checks for the shared GitHub and Hugging Face front doors."""

from __future__ import annotations

import json
import sys
from html.parser import HTMLParser
from pathlib import Path

import hf_static_space_deploy as deploy


REQUIRED_LINKS = {
    "https://a-11-oy.com",
    "https://a11oy.net",
    "https://github.com/szl-holdings",
    "https://huggingface.co/SZLHOLDINGS",
}
BANNED_COPY = {
    "every model ships with signed receipts",
    "70+ live surfaces",
    "trust ceiling 0.97",
    "all models operational",
}
HUB_CARD_EMOJI = "🛡️"
REQUIRED_HF_ASSETS = {
    "assets/estate-command-system.svg": "profile/assets/estate-command-system.svg",
    "assets/estate-banner-v2.svg": "profile/assets/estate-banner-v2.svg",
    "assets/hf-portfolio-map.svg": "profile/assets/hf-portfolio-map.svg",
    "assets/hf-card-command.svg": "profile/assets/hf-card-command.svg",
    "assets/hf-card-intelligence.svg": "profile/assets/hf-card-intelligence.svg",
    "assets/hf-card-models.svg": "profile/assets/hf-card-models.svg",
    "assets/hf-card-evidence.svg": "profile/assets/hf-card-evidence.svg",
}


def front_matter_value(document: str, key: str) -> str | None:
    """Return an unquoted scalar from the leading YAML front matter only."""
    lines = document.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None
        name, separator, value = line.partition(":")
        if separator and name.strip() == key:
            return value.strip()
    return None


class SurfaceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: set[str] = set()
        self.h1_count = 0
        self.main_count = 0
        self.body_marker = ""
        self.external_assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.add(str(values["href"]))
        if tag == "h1":
            self.h1_count += 1
        if tag == "main":
            self.main_count += 1
        if tag == "body":
            self.body_marker = str(values.get("data-szl-surface", ""))
        if tag == "script" and str(values.get("src", "")).startswith(("http://", "https://")):
            self.external_assets.append(str(values["src"]))
        if tag == "link" and str(values.get("href", "")).startswith(("http://", "https://")):
            self.external_assets.append(str(values["href"]))


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def required_asset_mismatches(
    root: Path, files: list[deploy.PublicationFile]
) -> dict[str, dict[str, str | None]]:
    """Return required destinations that are absent or bound to the wrong source."""
    actual = {
        item.destination: item.source.relative_to(root).as_posix()
        for item in files
        if item.destination in REQUIRED_HF_ASSETS
    }
    return {
        destination: {"expected": expected, "actual": actual.get(destination)}
        for destination, expected in REQUIRED_HF_ASSETS.items()
        if actual.get(destination) != expected
    }


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    profile = (root / "profile/README.md").read_text(encoding="utf-8")
    hub_card = (root / "huggingface/org-card/README.md").read_text(encoding="utf-8")
    html = (root / "huggingface/org-card/index.html").read_text(encoding="utf-8")
    svg = (root / "profile/assets/estate-command-system.svg").read_text(encoding="utf-8")
    portfolio_assets = {
        path.name: path.read_text(encoding="utf-8")
        for path in (root / "profile/assets").glob("hf-*.svg")
    }
    portfolio_assets["estate-banner-v2.svg"] = (
        root / "profile/assets/estate-banner-v2.svg"
    ).read_text(encoding="utf-8")
    manifest_path = root / "huggingface/org-card.manifest.json"
    failures: list[str] = []

    for url in REQUIRED_LINKS:
        require(url in profile, f"GitHub profile missing canonical link: {url}", failures)
        require(url in hub_card, f"Hugging Face card missing canonical link: {url}", failures)
    require("./assets/estate-command-system.svg" in profile, "profile does not use canonical hero", failures)
    require("deployment.json" in hub_card, "Hub card does not expose served source binding", failures)
    card_emoji = front_matter_value(hub_card, "emoji")
    require(card_emoji is not None, "Hub card front matter is missing emoji", failures)
    require(
        card_emoji == HUB_CARD_EMOJI,
        f"Hub card emoji must be the approved Extended Pictographic value {HUB_CARD_EMOJI}",
        failures,
    )
    require(
        front_matter_value(hub_card, "thumbnail") is not None,
        "Hub card front matter is missing a portfolio thumbnail",
        failures,
    )
    require("| --- |" not in hub_card, "Hub card uses a mobile-hostile Markdown table", failures)
    require(len(hub_card.split()) <= 520, "Hub card exceeds the concise 520-word budget", failures)

    combined = f"{profile}\n{hub_card}\n{html}".lower()
    for phrase in BANNED_COPY:
        require(phrase not in combined, f"unsupported public copy remains: {phrase}", failures)

    parser = SurfaceParser()
    parser.feed(html)
    require(parser.h1_count == 1, "static front door must contain exactly one h1", failures)
    require(parser.main_count == 1, "static front door must contain exactly one main landmark", failures)
    require(parser.body_marker == "company-front-door", "static front door marker is missing", failures)
    require(not parser.external_assets, f"runtime external assets are forbidden: {parser.external_assets}", failures)
    require("prefers-reduced-motion" in html, "reduced-motion contract is missing", failures)
    require("@media (max-width: 640px)" in html, "mobile breakpoint contract is missing", failures)
    require("@media (max-width: 390px)" in html, "small-phone breakpoint contract is missing", failures)
    require("min-height: 44px" in html, "touch-target contract is missing", failures)
    require(
        ".brand { display: inline-flex; min-height: 44px" in html,
        "brand touch target must remain at least 44px",
        failures,
    )
    require(
        ".artifact { display: block;" in html,
        "artifact links must expose their full card as the hit area",
        failures,
    )
    require("overflow-x: hidden" in html, "horizontal-overflow guard is missing", failures)
    require("overflow-wrap: anywhere" in html, "long-identifier reflow guard is missing", failures)
    require("Skip to main content" in html, "keyboard skip link is missing", failures)

    require("<title" in svg and "<desc" in svg, "hero SVG needs an accessible title and description", failures)
    require("<script" not in svg.lower(), "hero SVG must not execute scripts", failures)
    require(len(portfolio_assets) >= 6, "portfolio asset family is incomplete", failures)
    for name, source in portfolio_assets.items():
        require(
            "<title" in source and "<desc" in source,
            f"portfolio SVG needs an accessible title and description: {name}",
            failures,
        )
        require("<script" not in source.lower(), f"portfolio SVG must not execute scripts: {name}", failures)

    try:
        contract, files = deploy.load_contract(root, manifest_path)
        require(contract.get("prune") is True, "org-card publication must prune unmanaged legacy files", failures)
        mismatched_assets = required_asset_mismatches(root, files)
        require(
            not mismatched_assets,
            f"manifest portfolio source bindings are invalid: {mismatched_assets}",
            failures,
        )
    except Exception as exc:
        failures.append(f"publication manifest invalid: {type(exc).__name__}: {exc}")

    report = {
        "schema": "szl.public-front-door-check/v1",
        "state": "PASS" if not failures else "FAIL",
        "checks": 28 + len(REQUIRED_LINKS) * 2 + len(BANNED_COPY) + len(portfolio_assets) * 2,
        "failures": failures,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
