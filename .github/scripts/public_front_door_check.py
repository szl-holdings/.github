#!/usr/bin/env python3
"""Fail-closed checks for the shared GitHub and Hugging Face front doors."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
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
HUB_CARD_SHORT_DESCRIPTION_MAX_CHARS = 60
BLOCK_SCALAR_HEADER = re.compile(
    r"^(?P<style>[>|])(?P<modifiers>(?:[+-][1-9]?|[1-9][+-]?)?)$"
)
BLOCK_SCALAR_VALUE = re.compile(
    r"^(?:(?:!\S+|&\S+)\s+)*(?P<header>[>|](?:[+-][1-9]?|[1-9][+-]?)?)$"
)
UNSUPPORTED_PUSH_VALUE = "!__UNSUPPORTED_YAML_NODE__"
SIMPLE_METADATA_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
SAFE_PLAIN_METADATA_VALUE = re.compile(r"^[A-Za-z][A-Za-z0-9 ./_+,&'()-]*$")
TRUTH_MARKERS = {"Current state", "HISTORICAL", "SIMULATED"}
HUB_CARD_PATH_CLASS = "szl-hf-path"
HUB_CARD_CARD_CLASS = "szl-hf-card"
CANONICAL_WEBP = "profile/assets/evidence-lattice-v2.webp"
WEBP_DESTINATION = "assets/evidence-lattice-v2.webp"
HUB_CARD_THUMBNAIL = (
    "https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/" + WEBP_DESTINATION
)
WEBP_DIMENSIONS = (1800, 776)
MAX_WEBP_BYTES = 250_000
CANONICAL_WEBP_SHA256 = (
    "aebd33ebc112f5c7f0e543415e6485ec92b0ed6d480f82391cc0b922ce50d405"
)
REQUIRED_PUBLICATION_BINDINGS = {
    ".gitattributes": "huggingface/org-card/.gitattributes",
    "README.md": "huggingface/org-card/README.md",
    "HONEST_DISCLOSURE.md": "huggingface/org-card/HONEST_DISCLOSURE.md",
    "index.html": "huggingface/org-card/index.html",
    "estate-alignment.json": "docs/ESTATE_ALIGNMENT_CONTRACT_V1.json",
    "assets/estate-command-system.svg": "profile/assets/estate-command-system.svg",
    "assets/estate-banner-v2.svg": "profile/assets/estate-banner-v2.svg",
    "assets/hf-portfolio-map.svg": "profile/assets/hf-portfolio-map.svg",
    "assets/hf-card-command.svg": "profile/assets/hf-card-command.svg",
    "assets/hf-card-intelligence.svg": "profile/assets/hf-card-intelligence.svg",
    "assets/hf-card-models.svg": "profile/assets/hf-card-models.svg",
    "assets/hf-card-evidence.svg": "profile/assets/hf-card-evidence.svg",
    WEBP_DESTINATION: CANONICAL_WEBP,
    "GOVERNANCE.md": "huggingface/org-card/GOVERNANCE.md",
    "MODELS.txt": "huggingface/org-card/MODELS.txt",
    "SEVEN_SPACES.md": "huggingface/org-card/SEVEN_SPACES.md",
    "SPACE_PROVENANCE_FRONTIER.json": "huggingface/org-card/SPACE_PROVENANCE_FRONTIER.json",
    "seven-spaces.yaml": "huggingface/org-card/seven-spaces.yaml",
}
REQUIRED_PUSH_PATHS = {
    "huggingface/org-card/**",
    "huggingface/org-card.manifest.json",
    "docs/ESTATE_ALIGNMENT_CONTRACT_V1.json",
    "profile/assets/**",
    "profile/assets/evidence-lattice-v2.webp",
    ".github/scripts/hf_static_space_deploy.py",
    ".github/scripts/hf_org_card_embed_check.py",
    ".github/scripts/public_front_door_check.py",
    ".github/scripts/test_hf_static_space_deploy.py",
    ".github/scripts/test_public_front_door_check.py",
    ".github/workflows/hf-org-card-deploy.yml",
    ".github/workflows/hf-org-card-embed-check.yml",
}
REQUIRED_PUSH_BRANCHES = {"main"}
EXPECTED_PUBLICATION_TARGET = {
    "repo_id": "SZLHOLDINGS/README",
    "repo_type": "space",
    "live_base_url": "https://szlholdings-readme.static.hf.space",
}
EXPECTED_SOURCE_REPOSITORY = "szl-holdings/.github"
EXPECTED_SMOKE = {
    "path": "/",
    "required_marker": 'data-szl-surface="company-front-door"',
}


def front_matter_value(document: str, key: str) -> str | None:
    """Return one conservative scalar from leading YAML front matter.

    This intentionally accepts less than full YAML. Ambiguous keys, duplicate
    keys, nested values, aliases, tags, collections, and multiline values all
    fail closed because this guard protects publication metadata.
    """
    lines = document.splitlines()
    if not lines or lines[0] != "---":
        return None

    closing_index = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.rstrip() == "---" and not line.startswith((" ", "\t"))
        ),
        None,
    )
    if closing_index is None:
        return None

    matches: list[str] = []
    seen_keys: set[str] = set()
    for line in lines[1:closing_index]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")):
            return None
        name, separator, value = line.partition(":")
        if not separator:
            return None
        normalized_name = _simple_metadata_key(name)
        if normalized_name is None or normalized_name in seen_keys:
            return None
        seen_keys.add(normalized_name)
        scalar = _without_yaml_comment(value).strip()
        if (
            not scalar
            or BLOCK_SCALAR_HEADER.fullmatch(scalar)
            or scalar[0] in "*!&[{}>|"
            or scalar.startswith(("- ", "? ", ": "))
        ):
            return None
        if scalar.startswith(("'", '"')) and _yaml_quoted_scalar(scalar) is None:
            return None
        if not scalar.startswith(("'", '"')) and re.search(r":(?:\s|$)", scalar):
            return None
        if normalized_name == key:
            matches.append(value)
    if len(matches) != 1:
        return None

    scalar = _without_yaml_comment(matches[0]).strip()
    if (
        not scalar
        or BLOCK_SCALAR_HEADER.fullmatch(scalar)
        or scalar[0] in "*!&[{}>|"
        or scalar.startswith(("- ", "? ", ": "))
    ):
        return None
    quoted = scalar.startswith(("'", '"'))
    normalized = _yaml_quoted_scalar(scalar)
    if normalized is None or not normalized:
        return None
    if not quoted:
        if key == "emoji" and normalized != HUB_CARD_EMOJI:
            return None
        if key == "thumbnail" and normalized != HUB_CARD_THUMBNAIL:
            return None
        if key not in {
            "emoji",
            "thumbnail",
        } and not SAFE_PLAIN_METADATA_VALUE.fullmatch(normalized):
            return None
    if not quoted and normalized.casefold() in {
        "~",
        "null",
        "y",
        "n",
        "yes",
        "no",
        "on",
        "off",
        "true",
        "false",
        ".nan",
        ".inf",
        "+.inf",
        "-.inf",
    }:
        return None
    return normalized


def has_canonical_thumbnail(document: str) -> bool:
    """Return whether Hub metadata binds exactly to the canonical thumbnail."""
    return front_matter_value(document, "thumbnail") == HUB_CARD_THUMBNAIL


def _without_yaml_comment(value: str) -> str:
    """Remove a YAML comment while retaining hashes inside quoted scalars."""
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if quote == '"' and escaped:
            escaped = False
            continue
        if quote == '"' and character == "\\":
            escaped = True
            continue
        if quote:
            if character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.rstrip()


def _yaml_quoted_scalar(value: str) -> str | None:
    """Decode the conservative quoted-scalar subset accepted by this guard."""
    if value.startswith('"'):
        if len(value) < 2 or value[-1] != '"':
            return None
        try:
            normalized = json.loads(value)
        except json.JSONDecodeError:
            return None
        return normalized if isinstance(normalized, str) else None
    if value.startswith("'"):
        if len(value) < 2 or value[-1] != "'":
            return None
        inner = value[1:-1]
        normalized: list[str] = []
        index = 0
        while index < len(inner):
            if inner[index] != "'":
                normalized.append(inner[index])
                index += 1
                continue
            if index + 1 >= len(inner) or inner[index + 1] != "'":
                return None
            normalized.append("'")
            index += 2
        return "".join(normalized)
    return value


def _simple_metadata_key(value: str) -> str | None:
    """Return a regular metadata key, rejecting YAML node properties."""
    normalized = _yaml_quoted_scalar(value.strip())
    if normalized is None or not SIMPLE_METADATA_KEY.fullmatch(normalized):
        return None
    return normalized


def hub_short_description_length(document: str) -> int | None:
    """Return a fail-closed upper bound for the Hub metadata value length.

    Block-scalar newlines are each counted as one character. This can reject
    unusually padded valid YAML, but it cannot undercount what the Hub parses.
    Unsupported, duplicate, non-string, or multiline flow values fail closed.
    """
    lines = document.splitlines()
    if not lines or lines[0] != "---":
        return None

    closing_index = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.rstrip() == "---" and not line.startswith((" ", "\t"))
        ),
        None,
    )
    if closing_index is None:
        return None

    matches: list[tuple[int, str]] = []
    for index, line in enumerate(lines[1:closing_index], start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")):
            continue
        name, separator, value = line.partition(":")
        if not separator:
            return None
        normalized_name = _simple_metadata_key(name)
        if normalized_name is None:
            return None
        if normalized_name == "short_description":
            matches.append((index, value))
    if len(matches) != 1:
        return None

    index, raw_value = matches[0]
    scalar = _without_yaml_comment(raw_value).strip()
    block = BLOCK_SCALAR_HEADER.fullmatch(scalar)
    if block is not None:
        raw_block_lines: list[str] = []
        modifiers = block.group("modifiers")
        content_indent = next(
            (int(character) for character in modifiers if character.isdigit()),
            None,
        )
        for continuation in lines[index + 1 : closing_index]:
            if re.match(r"^ *\t", continuation):
                return None
            if continuation.strip():
                indentation = len(continuation) - len(continuation.lstrip(" "))
                if indentation == 0:
                    break
                if content_indent is None:
                    content_indent = indentation
                if indentation < content_indent:
                    return None
            raw_block_lines.append(continuation)

        effective_indent = content_indent or 0
        block_lines = [
            line[effective_indent:] if len(line) > effective_indent else ""
            for line in raw_block_lines
        ]
        if not any(block_lines):
            return None

        content_characters = sum(len(line) for line in block_lines)
        separators = max(len(block_lines) - 1, 0)
        if block_lines and "-" not in modifiers:
            separators += 1
        return content_characters + separators

    if not scalar or scalar[0] in "*!&[{}>|":
        return None
    if scalar.startswith(("- ", "? ", ": ")):
        return None

    quoted = scalar.startswith(("'", '"'))
    normalized = _yaml_quoted_scalar(scalar)
    if normalized is None:
        return None
    if not normalized:
        return None
    if not quoted and not SAFE_PLAIN_METADATA_VALUE.fullmatch(normalized):
        return None
    if not quoted and normalized.casefold() in {
        "~",
        "null",
        "y",
        "n",
        "yes",
        "no",
        "on",
        "off",
        "true",
        "false",
        ".nan",
        ".inf",
        "+.inf",
        "-.inf",
    }:
        return None

    for continuation in lines[index + 1 : closing_index]:
        if not continuation.strip() or continuation.lstrip().startswith("#"):
            continue
        if continuation.startswith((" ", "\t")):
            return None
        break
    return len(normalized)


def short_description_within_limit(document: str) -> bool:
    """Return whether the Hub short description is present and within limit."""
    length = hub_short_description_length(document)
    return length is not None and length <= HUB_CARD_SHORT_DESCRIPTION_MAX_CHARS


def has_markdown_table(document: str) -> bool:
    """Return true when a Markdown table separator row is present."""
    return bool(
        re.search(
            r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$",
            document,
            flags=re.MULTILINE,
        )
    )


def _inline_yaml_nodes_balanced(line: str) -> bool:
    """Reject YAML flow collections or quoted scalars that cross a newline."""
    stack: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(line):
        character = line[index]
        if quote == '"' and escaped:
            escaped = False
        elif quote == '"' and character == "\\":
            escaped = True
        elif quote == "'" and character == "'":
            if index + 1 < len(line) and line[index + 1] == "'":
                index += 1
            else:
                quote = None
        elif quote:
            if character == quote:
                quote = None
        elif character in {'"', "'"}:
            quote = character
        elif character == "#" and (index == 0 or line[index - 1].isspace()):
            break
        elif character in "[{":
            stack.append(character)
        elif character in "]}":
            expected = "[" if character == "]" else "{"
            if not stack or stack.pop() != expected:
                return False
        index += 1
    return quote is None and not stack


def workflow_push_values(source: str, field: str) -> set[str]:
    """Parse active values nested under the workflow's on.push field."""
    stack: list[tuple[int, str]] = []
    values: set[str] = set()
    block_scalar_indent: int | None = None

    def clean_scalar(value: str) -> str | None:
        normalized = _without_yaml_comment(value).strip()
        if not normalized:
            return None
        if BLOCK_SCALAR_VALUE.fullmatch(normalized):
            return None
        if normalized.startswith(("!", "&", "*")):
            return UNSUPPORTED_PUSH_VALUE
        decoded = _yaml_quoted_scalar(normalized)
        if decoded is None or not decoded:
            return None
        return decoded

    for raw_line in source.splitlines():
        stripped = raw_line.strip()
        indent = len(raw_line) - len(raw_line.lstrip(" "))

        if block_scalar_indent is not None:
            if not stripped or indent > block_scalar_indent:
                continue
            block_scalar_indent = None

        if not stripped or stripped.startswith("#"):
            continue
        if not _inline_yaml_nodes_balanced(raw_line):
            return {UNSUPPORTED_PUSH_VALUE}
        while stack and indent <= stack[-1][0]:
            stack.pop()

        if stripped.startswith("- "):
            item = _without_yaml_comment(stripped[2:]).strip()
            _, item_separator, item_value = item.partition(":")
            block_candidate = item_value.strip() if item_separator else item
            if BLOCK_SCALAR_VALUE.fullmatch(block_candidate):
                block_scalar_indent = indent
                continue
            if tuple(key for _, key in stack) == ("on", "push", field):
                cleaned = clean_scalar(stripped[2:])
                if cleaned is not None:
                    values.add(cleaned)
            continue

        key, separator, raw_value = stripped.partition(":")
        if not separator:
            continue
        key = key.strip().strip('"').strip("'")
        raw_value = raw_value.strip()
        scalar_value = _without_yaml_comment(raw_value).strip()
        if BLOCK_SCALAR_VALUE.fullmatch(scalar_value):
            block_scalar_indent = indent
            continue
        if scalar_value.startswith(("!", "&", "*")):
            return {UNSUPPORTED_PUSH_VALUE}
        if (
            scalar_value.startswith(("'", '"'))
            and _yaml_quoted_scalar(scalar_value) is None
        ):
            return {UNSUPPORTED_PUSH_VALUE}
        parent = tuple(item for _, item in stack)
        if parent == ("on", "push") and key == field and raw_value:
            inline = scalar_value
            if inline.startswith("[") and inline.endswith("]"):
                for item in inline[1:-1].split(","):
                    cleaned = clean_scalar(item)
                    if cleaned is not None:
                        values.add(cleaned)
            else:
                cleaned = clean_scalar(inline)
                if cleaned is not None:
                    values.add(cleaned)
            continue
        if not raw_value and (key != "on" or indent == 0):
            stack.append((indent, key))
    return values


def source_is_watched(source: str, push_paths: set[str]) -> bool:
    """Return true when a manifest source is covered by an active push path."""
    if any(pattern.startswith("!") for pattern in push_paths):
        return False
    for pattern in push_paths:
        if pattern.endswith("/**") and source.startswith(pattern[:-2]):
            return True
        if source == pattern:
            return True
    return False


def push_branches_are_exact(push_branches: set[str]) -> bool:
    """Allow publication only from the single protected source branch."""
    return push_branches == REQUIRED_PUSH_BRANCHES


def webp_dimensions(data: bytes) -> tuple[int, int] | None:
    """Read dimensions from a structurally complete, still WebP container."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    if int.from_bytes(data[4:8], "little") + 8 != len(data):
        return None

    canvas: tuple[int, int] | None = None
    raster: tuple[int, int] | None = None
    offset = 12
    while offset < len(data):
        if offset + 8 > len(data):
            return None
        kind = data[offset : offset + 4]
        chunk_size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        payload_start = offset + 8
        payload_end = payload_start + chunk_size
        padded_end = payload_end + (chunk_size & 1)
        if payload_end > len(data) or padded_end > len(data):
            return None
        payload = data[payload_start:payload_end]

        if chunk_size & 1 and data[payload_end] != 0:
            return None
        if kind == b"VP8X":
            if chunk_size != 10 or offset != 12 or canvas is not None:
                return None
            if payload[0] & 0xC3:
                return None
            canvas = (
                int.from_bytes(payload[4:7], "little") + 1,
                int.from_bytes(payload[7:10], "little") + 1,
            )
        elif kind == b"VP8 ":
            if chunk_size < 10 or payload[3:6] != b"\x9d\x01\x2a" or raster:
                return None
            frame_tag = int.from_bytes(payload[:3], "little")
            first_partition_size = frame_tag >> 5
            if (
                frame_tag & 1
                or ((frame_tag >> 1) & 0x7) > 3
                or not ((frame_tag >> 4) & 1)
                or chunk_size <= 10 + first_partition_size
            ):
                return None
            raster = (
                int.from_bytes(payload[6:8], "little") & 0x3FFF,
                int.from_bytes(payload[8:10], "little") & 0x3FFF,
            )
        elif kind == b"VP8L":
            return None
        elif kind in {b"ANIM", b"ANMF"}:
            return None
        offset = padded_end

    if offset != len(data) or raster is None or 0 in raster:
        return None
    if canvas is not None and canvas != raster:
        return None
    return raster


def canonical_webp_is_pinned(data: bytes) -> bool:
    """Bind the pre-decoded hero to the reviewed canonical bytes."""
    return deploy.sha256_bytes(data) == CANONICAL_WEBP_SHA256


def publication_binding_issues(
    root: Path, files: list[deploy.PublicationFile]
) -> dict[str, object]:
    """Return exact manifest binding, duplicate, and unexpected-path issues."""
    pairs: list[tuple[str, str]] = []
    for item in files:
        try:
            source = item.source.relative_to(root).as_posix()
        except ValueError:
            source = str(item.source)
        pairs.append((item.destination, source))
    counts = Counter(destination for destination, _ in pairs)
    actual = dict(pairs)
    mismatched = {
        destination: {
            "expected": expected,
            "actual": actual.get(destination),
        }
        for destination, expected in REQUIRED_PUBLICATION_BINDINGS.items()
        if actual.get(destination) != expected
    }
    return {
        "mismatched": mismatched,
        "unexpected": sorted(set(actual) - set(REQUIRED_PUBLICATION_BINDINGS)),
        "duplicates": sorted(
            destination for destination, count in counts.items() if count > 1
        ),
    }


def publication_contract_issues(contract: dict[str, object]) -> dict[str, object]:
    """Return security-sensitive publication destinations that drifted."""
    expected = {
        "target": EXPECTED_PUBLICATION_TARGET,
        "source_repository": EXPECTED_SOURCE_REPOSITORY,
        "smoke": EXPECTED_SMOKE,
    }
    return {
        name: {"expected": value, "actual": contract.get(name)}
        for name, value in expected.items()
        if contract.get(name) != value
    }


class SurfaceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: set[str] = set()
        self.h1_count = 0
        self.main_count = 0
        self.body_marker = ""
        self.external_assets: list[str] = []
        self.card_link_count = 0
        self.path_link_count = 0
        self.images: list[tuple[str, str, str, str, str, str]] = []
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set(str(values.get("class", "")).split())
        if tag == "a" and values.get("href"):
            self.links.add(str(values["href"]))
            self.card_link_count += int(HUB_CARD_CARD_CLASS in classes)
            self.path_link_count += int(HUB_CARD_PATH_CLASS in classes)
        if tag == "h1":
            self.h1_count += 1
        if tag == "main":
            self.main_count += 1
        if tag == "body":
            self.body_marker = str(values.get("data-szl-surface", ""))
        if tag == "img":
            self.images.append(
                (
                    str(values.get("src", "")),
                    str(values.get("alt", "")),
                    str(values.get("width", "")),
                    str(values.get("height", "")),
                    str(values.get("fetchpriority", "")),
                    str(values.get("decoding", "")),
                )
            )
        if tag == "meta" and values.get("content"):
            key = str(values.get("property") or values.get("name") or "")
            self.meta[key] = str(values["content"])
        if tag == "script" and str(values.get("src", "")).startswith(
            ("http://", "https://")
        ):
            self.external_assets.append(str(values["src"]))
        if tag == "link" and str(values.get("href", "")).startswith(
            ("http://", "https://")
        ):
            self.external_assets.append(str(values["href"]))


class FailureList(list[str]):
    """Failure messages plus an exact count of evaluated assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.checks = 0


def require(condition: bool, message: str, failures: FailureList) -> None:
    failures.checks += 1
    if not condition:
        failures.append(message)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    profile = (root / "profile/README.md").read_text(encoding="utf-8")
    hub_card = (root / "huggingface/org-card/README.md").read_text(encoding="utf-8")
    html = (root / "huggingface/org-card/index.html").read_text(encoding="utf-8")
    canonical_webp = (root / CANONICAL_WEBP).read_bytes()
    manifest_path = root / "huggingface/org-card.manifest.json"
    deploy_workflow = (root / ".github/workflows/hf-org-card-deploy.yml").read_text(
        encoding="utf-8"
    )
    failures = FailureList()

    for url in REQUIRED_LINKS:
        require(
            url in profile, f"GitHub profile missing canonical link: {url}", failures
        )
        require(
            url in hub_card,
            f"Hugging Face card missing canonical link: {url}",
            failures,
        )
        require(
            url in html, f"Static front door missing canonical link: {url}", failures
        )

    require(
        "./assets/evidence-lattice-v2.webp" in profile,
        "profile does not use the canonical WebP hero",
        failures,
    )
    require(
        "assets/evidence-lattice-v2.webp" in hub_card,
        "Hub card does not use the canonical WebP hero",
        failures,
    )
    require(
        "https://szlholdings-readme.static.hf.space/assets/evidence-lattice-v2.webp" in html,
        "static front door does not use the canonical absolute WebP hero",
        failures,
    )
    require(
        not (root / "huggingface/org-card/assets/evidence-lattice-v2.webp").exists(),
        "duplicate WebP source must not drift from the canonical profile asset",
        failures,
    )
    require(
        "deployment.json" in hub_card,
        "Hub card does not expose served source binding",
        failures,
    )
    require(
        "--materialize" in hub_card and "python -m http.server 8000" in hub_card,
        "Hub card does not expose a manifest-materialized reproduction command",
        failures,
    )

    card_emoji = front_matter_value(hub_card, "emoji")
    require(card_emoji is not None, "Hub card front matter is missing emoji", failures)
    require(
        card_emoji == HUB_CARD_EMOJI,
        f"Hub card emoji must be the approved value {HUB_CARD_EMOJI}",
        failures,
    )
    short_description_length = hub_short_description_length(hub_card)
    require(
        short_description_length is not None,
        "Hub card front matter has a missing, duplicate, or unsupported short_description",
        failures,
    )
    require(
        short_description_within_limit(hub_card),
        "Hub card short_description exceeds the Hugging Face 60-character limit",
        failures,
    )
    require(
        has_canonical_thumbnail(hub_card),
        "Hub card thumbnail is not bound to the canonical WebP",
        failures,
    )
    require(
        not has_markdown_table(profile),
        "GitHub profile uses a mobile-hostile table",
        failures,
    )
    require(
        not has_markdown_table(hub_card),
        "Hub card uses a mobile-hostile table",
        failures,
    )
    require(
        len(profile.split()) <= 430,
        "GitHub profile exceeds the 430-word budget",
        failures,
    )
    require(
        len(hub_card.split()) <= 380, "Hub card exceeds the 380-word budget", failures
    )

    combined = f"{profile}\n{hub_card}\n{html}".lower()
    for phrase in BANNED_COPY:
        require(
            phrase not in combined,
            f"unsupported public copy remains: {phrase}",
            failures,
        )
    for marker in TRUTH_MARKERS:
        require(
            marker in profile and marker in hub_card and marker in html,
            f"truth boundary marker must remain on every front door: {marker}",
            failures,
        )

    parser = SurfaceParser()
    parser.feed(html)
    require(
        parser.h1_count == 1, "static front door must contain exactly one h1", failures
    )
    require(
        parser.main_count == 1,
        "static front door must contain exactly one main landmark",
        failures,
    )
    require(
        parser.body_marker == "company-front-door",
        "static front door marker is missing",
        failures,
    )
    require(
        not parser.external_assets,
        f"runtime external assets are forbidden: {parser.external_assets}",
        failures,
    )
    require(
        parser.path_link_count == 4,
        "mission paths must be four full-card links",
        failures,
    )
    require(
        parser.card_link_count >= 5,
        "artifact links must expose full-card hit areas",
        failures,
    )
    require(
        parser.meta.get("og:image", "").endswith(WEBP_DESTINATION),
        "Open Graph image is not bound to the canonical WebP",
        failures,
    )
    require(
        (
            "https://szlholdings-readme.static.hf.space/assets/evidence-lattice-v2.webp",
            "",
            "1800",
            "776",
            "high",
            "async",
        )
        in parser.images,
        "decorative HTML hero must retain an empty alt attribute",
        failures,
    )
    require(
        "prefers-reduced-motion" in html, "reduced-motion contract is missing", failures
    )
    require(
        "prefers-contrast" in html, "increased-contrast contract is missing", failures
    )
    require("forced-colors" in html, "forced-colors contract is missing", failures)
    require(
        "@media (max-width: 640px)" in html,
        "mobile breakpoint contract is missing",
        failures,
    )
    require(
        "@media (max-width: 390px)" in html,
        "small-phone breakpoint contract is missing",
        failures,
    )
    require(
        "@media (max-width: 760px)" in html,
        "tablet navigation breakpoint is missing",
        failures,
    )
    require(
        "orientation: landscape" in html,
        "phone landscape contract is missing",
        failures,
    )
    require(
        "env(safe-area-inset-left)" in html,
        "horizontal display-cutout safe area is missing",
        failures,
    )
    require(
        "env(safe-area-inset-top)" in html,
        "top display-cutout safe area is missing",
        failures,
    )
    require("--tap: 44px" in html, "44px touch-target token is missing", failures)
    require(
        "overflow-wrap: anywhere" in html,
        "long-identifier reflow guard is missing",
        failures,
    )
    require(
        "overflow-x: hidden" not in html,
        "horizontal overflow must not be hidden",
        failures,
    )
    require(
        "overflow-x: auto" not in html,
        "primary navigation must not hide routes in a scroller",
        failures,
    )
    require("Skip to main content" in html, "keyboard skip link is missing", failures)
    require('tabindex="-1"' in html, "main landmark must remain focusable", failures)

    require(
        canonical_webp.startswith(b"RIFF") and canonical_webp[8:12] == b"WEBP",
        "canonical hero must be a valid WebP asset",
        failures,
    )
    require(
        canonical_webp_is_pinned(canonical_webp),
        "canonical hero bytes do not match the reviewed WebP digest",
        failures,
    )
    require(
        webp_dimensions(canonical_webp) == WEBP_DIMENSIONS,
        f"canonical hero must be {WEBP_DIMENSIONS[0]}x{WEBP_DIMENSIONS[1]}",
        failures,
    )
    require(
        len(canonical_webp) <= MAX_WEBP_BYTES,
        f"canonical hero exceeds {MAX_WEBP_BYTES} bytes",
        failures,
    )

    svg_sources = sorted(
        source
        for source in REQUIRED_PUBLICATION_BINDINGS.values()
        if source.endswith(".svg")
    )
    require(len(svg_sources) == 7, "compatibility SVG family is incomplete", failures)
    for source in svg_sources:
        svg = (root / source).read_text(encoding="utf-8")
        require(
            "<title" in svg and "<desc" in svg,
            f"published SVG needs an accessible title and description: {source}",
            failures,
        )
        require(
            "<script" not in svg.lower(),
            f"published SVG must not execute scripts: {source}",
            failures,
        )

    push_paths = workflow_push_values(deploy_workflow, "paths")
    push_branches = workflow_push_values(deploy_workflow, "branches")
    negative_push_paths = sorted(path for path in push_paths if path.startswith("!"))
    require(
        push_branches_are_exact(push_branches),
        f"org-card deployment branches must be exactly main: {sorted(push_branches)}",
        failures,
    )
    require(
        not negative_push_paths,
        f"org-card deployment trigger contains fail-open exclusions: {negative_push_paths}",
        failures,
    )
    require(
        REQUIRED_PUSH_PATHS <= push_paths,
        f"org-card deployment trigger is incomplete: {sorted(REQUIRED_PUSH_PATHS - push_paths)}",
        failures,
    )
    require(
        "-p test_hf_static_space_deploy.py" in deploy_workflow,
        "deployment workflow does not run publisher tests",
        failures,
    )
    require(
        "-p test_public_front_door_check.py" in deploy_workflow,
        "deployment workflow does not run front-door tests",
        failures,
    )
    require(
        "hf_org_card_embed_check.py" in deploy_workflow,
        "deployment workflow does not run the embed hardening check",
        failures,
    )

    try:
        contract, files = deploy.load_contract(root, manifest_path)
        require(
            contract.get("prune") is True,
            "org-card publication must prune unmanaged legacy files",
            failures,
        )
        require(
            contract.get("allowed_deletions") == [],
            "org-card publication must fail closed on every unexpected deletion",
            failures,
        )
        contract_issues = publication_contract_issues(contract)
        require(
            not contract_issues,
            f"publication destination or smoke binding drifted: {contract_issues}",
            failures,
        )
        binding_issues = publication_binding_issues(root, files)
        require(
            not any(binding_issues.values()),
            f"manifest source bindings are invalid: {binding_issues}",
            failures,
        )
        unwatched = sorted(
            item.source.relative_to(root).as_posix()
            for item in files
            if not source_is_watched(
                item.source.relative_to(root).as_posix(), push_paths
            )
        )
        require(
            not unwatched,
            f"manifest sources can change without scheduling publication: {unwatched}",
            failures,
        )
    except Exception as exc:
        require(
            False,
            f"publication manifest invalid: {type(exc).__name__}: {exc}",
            failures,
        )

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
