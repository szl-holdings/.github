#!/usr/bin/env python3
"""Fail-closed checks for the shared GitHub and Hugging Face front doors."""

from __future__ import annotations

import ast
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
TRUTH_MARKERS = {"Current state", "HISTORICAL", "SIMULATED"}
HF_HERO_DESTINATION = "assets/evidence-lattice-v2.webp"
HF_HERO_SOURCE = Path("huggingface/org-card/assets/evidence-lattice-v2.webp")


def front_matter_value(document: str, key: str) -> str | None:
    """
    Parse one-line front-matter scalars only, with strict rejection rules.

    Rejects duplicated keys, aliases/anchors, continuation lines, and block
    scalars so the contract cannot be bypassed by front-matter syntax games.
    """

    lines = document.splitlines()
    if not lines or lines[0].strip() != "---":
        return None

    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return values.get(key)
        if not line or line.startswith(" ") or line.startswith("\t"):
            return None
        if line.strip().startswith("#"):
            continue
        if ":" not in line:
            return None

        name, _, raw_value = line.partition(":")
        if not name or name.strip() != name or not name.strip():
            return None
        name = name.strip()
        if name in values:
            return None

        value = raw_value.strip()
        if not value:
            return None
        if value.startswith((">", "|")):
            return None
        if value.startswith(("&", "*")):
            return None

        if value[0] in "\"'" and value[-1] == value[0]:
            try:
                value = ast.literal_eval(value)
            except Exception:
                return None
        values[name] = value

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


class FailureList(list[str]):
    """Failure messages plus an exact count of evaluated assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.checks = 0


def manifest_hero_source(files: list[deploy.PublicationFile], destination: str) -> Path | None:
    """Return the exact source path for a manifest destination, if present."""

    for file in files:
        if file.destination == destination:
            return file.source
    return None


def require(condition: bool, message: str, failures: FailureList) -> None:
    failures.checks += 1
    if not condition:
        failures.append(message)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    profile = (root / "profile/README.md").read_text(encoding="utf-8")
    hub_card = (root / "huggingface/org-card/README.md").read_text(encoding="utf-8")
    html = (root / "huggingface/org-card/index.html").read_text(encoding="utf-8")
    profile_banner = (root / "profile/assets/evidence-lattice-v2.webp").read_bytes()
    space_banner = (root / "huggingface/org-card/assets/evidence-lattice-v2.webp").read_bytes()
    manifest_path = root / "huggingface/org-card.manifest.json"
    failures = FailureList()

    for url in REQUIRED_LINKS:
        require(url in profile, f"GitHub profile missing canonical link: {url}", failures)
        require(url in hub_card, f"Hugging Face card missing canonical link: {url}", failures)
    require(
        "./assets/evidence-lattice-v2.webp" in profile,
        "profile does not use canonical hero",
        failures,
    )
    require(
        "assets/evidence-lattice-v2.webp" in hub_card,
        "Hub card does not use canonical hero",
        failures,
    )
    require("deployment.json" in hub_card, "Hub card does not expose served source binding", failures)
    require(
        "python -m http.server 8000 --directory huggingface/org-card" in hub_card,
        "Hub card does not expose a local reproduction command",
        failures,
    )
    card_emoji = front_matter_value(hub_card, "emoji")
    require(card_emoji is not None, "Hub card front matter is missing emoji", failures)
    require(
        card_emoji == HUB_CARD_EMOJI,
        f"Hub card emoji must be the approved Extended Pictographic value {HUB_CARD_EMOJI}",
        failures,
    )
    short_description = front_matter_value(hub_card, "short_description")
    require(short_description is not None, "Hub card front matter is missing short_description", failures)
    require(
        short_description is not None and len(short_description) <= 60,
        "Hub card short_description exceeds the Hugging Face 60-character limit",
        failures,
    )

    combined = f"{profile}\n{hub_card}\n{html}".lower()
    for phrase in BANNED_COPY:
        require(phrase not in combined, f"unsupported public copy remains: {phrase}", failures)
    for marker in TRUTH_MARKERS:
        require(
            marker in profile and marker in hub_card and marker in html,
            f"truth boundary marker must remain on every front door: {marker}",
            failures,
        )

    parser = SurfaceParser()
    parser.feed(html)
    require(parser.h1_count == 1, "static front door must contain exactly one h1", failures)
    require(parser.main_count == 1, "static front door must contain exactly one main landmark", failures)
    require(parser.body_marker == "company-front-door", "static front door marker is missing", failures)
    require(not parser.external_assets, f"runtime external assets are forbidden: {parser.external_assets}", failures)
    require("prefers-reduced-motion" in html, "reduced-motion contract is missing", failures)
    require("prefers-contrast" in html, "increased-contrast contract is missing", failures)
    require("forced-colors" in html, "forced-colors contract is missing", failures)
    require("@media (max-width: 640px)" in html, "mobile breakpoint contract is missing", failures)
    require("Skip to main content" in html, "keyboard skip link is missing", failures)
    require('tabindex="-1"' in html, "main landmark must remain programmatically focusable", failures)

    require(
        profile_banner.startswith(b"RIFF") and profile_banner[8:12] == b"WEBP",
        "GitHub profile hero must be a valid WebP asset",
        failures,
    )
    require(
        space_banner.startswith(b"RIFF") and space_banner[8:12] == b"WEBP",
        "Hugging Face Space hero must be a valid WebP asset",
        failures,
    )
    require(profile_banner == space_banner, "front doors must publish the same hero bytes", failures)
    require(len(profile_banner) <= 250_000, "canonical hero exceeds 250 KB", failures)

    try:
        contract, files = deploy.load_contract(root, manifest_path)
        destinations = {item.destination for item in files}
        require(contract.get("prune") is True, "org-card publication must prune unmanaged legacy files", failures)
        require(
            HF_HERO_DESTINATION in destinations,
            "manifest must publish canonical hero",
            failures,
        )
        hero_source = manifest_hero_source(files, HF_HERO_DESTINATION)
        require(
            hero_source is not None and hero_source == (root / HF_HERO_SOURCE).resolve(),
            f"manifest hero destination {HF_HERO_DESTINATION!r} must bind to {HF_HERO_SOURCE.as_posix()}",
            failures,
        )
    except Exception as exc:
        failures.append(f"publication manifest invalid: {type(exc).__name__}: {exc}")

    report = {
        "schema": "szl.public-front-door-check/v1",
        "state": "PASS" if not failures else "FAIL",
        "checks": failures.checks,
        "failures": failures,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
