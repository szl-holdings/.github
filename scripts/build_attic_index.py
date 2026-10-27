#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. — SZL Holdings
"""Generate and validate ATTIC.md, the public org-wide tombstone index.

The index describes what an unauthenticated visitor can see on the GitHub
organization page. Private repositories are deliberately excluded, even when
the caller uses an admin token. That makes local generation and repository-
scoped CI deterministic and prevents private repository names from leaking into
the public artifact.

Doctrine
--------
Honest UNKNOWN over fabricated green. This script never invents a successor.
An archived repo with no discoverable successor is emitted as UNKNOWN and
listed for an owner decision.

Usage
-----
    python scripts/build_attic_index.py --write
    python scripts/build_attic_index.py --check
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ORG = "szl-holdings"
ATTIC = Path(__file__).resolve().parent.parent / "ATTIC.md"
CANONICAL_RE = re.compile(
    r"Canonical:\s*https://github\.com/[A-Za-z0-9_.-]+/"
    r"([A-Za-z0-9_.-]*[A-Za-z0-9_-])(?=$|[\s),.;:])"
)

TERMINAL_BY_DESIGN = {
    "evidence-typed-formula-governance": (
        "Archival preprint + reproducibility package. Immutable by design — "
        "a published record must not be superseded in place."
    ),
    "fail-closed-governed-ai-services": (
        "Archival preprint + reproducibility package. Immutable by design — "
        "a published record must not be superseded in place."
    ),
    "szl-fleet-overlay": (
        "Frozen WarHacker-2026 UDS fleet-overlay evidence snapshot. Retained "
        "for provenance; it has no active software successor."
    ),
    "szl-otel-mesh": (
        "Published OpenTelemetry/DSSE research artifact with DOI "
        "10.5281/zenodo.20434276. Immutable archival evidence by design."
    ),
    "szl-uds-deployment": (
        "Frozen WarHacker-2026 UDS deployment evidence snapshot. Retained for "
        "reproducibility; it has no active software successor."
    ),
    "warhacker-demo": (
        "One-off WarHacker-2026 hardware and air-gap dry-run snapshot. The "
        "archived demonstration is retained as evidence, not a maintained product."
    ),
}


def fetch_repos() -> list[dict]:
    """Read the live estate and return only repositories visible to the public."""
    completed = subprocess.run(
        [
            "gh",
            "repo",
            "list",
            ORG,
            "--limit",
            "500",
            "--json",
            "name,description,isArchived,isPrivate,url,pushedAt,primaryLanguage",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    repos = json.loads(completed.stdout)
    return [repo for repo in repos if not repo.get("isPrivate", False)]


def analyse(repos: list[dict]) -> dict:
    by_name = {repo["name"]: repo for repo in repos}
    archived_names = {repo["name"] for repo in repos if repo["isArchived"]}

    mapped: list[tuple[str, str, dict]] = []
    terminal: list[tuple[str, str, dict]] = []
    unknown: list[tuple[str, dict]] = []
    defects: list[tuple[str, str, str]] = []

    for repo in sorted(
        (item for item in repos if item["isArchived"]),
        key=lambda item: item["name"],
    ):
        name = repo["name"]
        description = repo.get("description") or ""
        match = CANONICAL_RE.search(description)

        if match:
            target = match.group(1)
            if target not in by_name:
                defects.append((name, target, "successor repo does not exist"))
            elif target in archived_names:
                defects.append(
                    (name, target, "successor is itself archived (tombstone chain)")
                )
            else:
                mapped.append((name, target, repo))
        elif name in TERMINAL_BY_DESIGN:
            terminal.append((name, TERMINAL_BY_DESIGN[name], repo))
        else:
            unknown.append((name, repo))

    return {
        "total": len(repos),
        "archived": len(archived_names),
        "active": len(repos) - len(archived_names),
        "mapped": mapped,
        "terminal": terminal,
        "unknown": unknown,
        "defects": defects,
    }


def render(analysis: dict) -> str:
    lines: list[str] = []
    lines.append("# ATTIC — SZL Holdings archived-repository index")
    lines.append("")
    lines.append("<!-- GENERATED FILE — do not edit by hand. -->")
    lines.append("<!-- Regenerate: python scripts/build_attic_index.py --write -->")
    lines.append("")
    lines.append(
        "Every public archived repository in the `szl-holdings` organization, "
        "mapped to the canonical repository that superseded it. Generated from "
        "the live GitHub API, never hand-maintained, so the index cannot drift "
        "from the public estate."
    )
    lines.append("")
    lines.append(
        "**Doctrine.** Honest UNKNOWN over fabricated green: an archived repo "
        "with no discoverable successor appears below as UNKNOWN and requires "
        "an owner decision. This index never invents a plausible-looking successor."
    )
    lines.append("")
    lines.append("## Estate shape")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|---|---:|")
    lines.append(f"| Public repositories total | {analysis['total']} |")
    lines.append(f"| Active public repositories | {analysis['active']} |")
    lines.append(f"| Archived public repositories (tombstones) | {analysis['archived']} |")
    lines.append(
        f"| Tombstones with a resolved successor | {len(analysis['mapped'])} |"
    )
    lines.append(f"| Tombstones terminal by design | {len(analysis['terminal'])} |")
    lines.append(
        f"| Tombstones with UNKNOWN successor | {len(analysis['unknown'])} |"
    )
    lines.append(f"| Structural defects | {len(analysis['defects'])} |")
    lines.append("")

    if analysis["defects"]:
        lines.append("## ⛔ Structural defects — fail closed")
        lines.append("")
        lines.append("| Archived repo | Declared successor | Defect |")
        lines.append("|---|---|---|")
        for name, target, reason in analysis["defects"]:
            lines.append(f"| `{name}` | `{target}` | {reason} |")
        lines.append("")

    lines.append("## Resolved tombstones")
    lines.append("")
    lines.append("| Archived repo | Canonical successor | Language | Last push |")
    lines.append("|---|---|---|---|")
    for name, target, repo in analysis["mapped"]:
        language = (repo.get("primaryLanguage") or {}).get("name") or "—"
        pushed_at = (repo.get("pushedAt") or "")[:10] or "—"
        lines.append(
            f"| `{name}` | [`{target}`](https://github.com/{ORG}/{target}) | "
            f"{language} | {pushed_at} |"
        )
    lines.append("")

    if analysis["terminal"]:
        lines.append("## Terminal by design (no successor)")
        lines.append("")
        lines.append("| Archived repo | Why it has no successor |")
        lines.append("|---|---|")
        for name, reason, _repo in analysis["terminal"]:
            lines.append(f"| `{name}` | {reason} |")
        lines.append("")

    if analysis["unknown"]:
        lines.append("## ⚠️ UNKNOWN successor — owner decision required")
        lines.append("")
        lines.append(
            "These archived repositories carry no `Canonical:` pointer and are "
            "not declared terminal. Each needs one of: a successor pointer added "
            "to its description, or an entry in `TERMINAL_BY_DESIGN` in the "
            "generator explaining why it is terminal. **They are reported, not guessed.**"
        )
        lines.append("")
        lines.append("| Archived repo | Description | Last push |")
        lines.append("|---|---|---|")
        for name, repo in analysis["unknown"]:
            description = (repo.get("description") or "—").replace("|", "\\|")
            if len(description) > 110:
                description = description[:107] + "..."
            pushed_at = (repo.get("pushedAt") or "")[:10] or "—"
            lines.append(f"| `{name}` | {description} | {pushed_at} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "Generated by `scripts/build_attic_index.py`. CI runs `--check` so this "
        "file cannot silently drift from the live public estate."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="regenerate ATTIC.md")
    parser.add_argument("--check", action="store_true", help="fail on drift or defects")
    args = parser.parse_args()

    analysis = analyse(fetch_repos())
    body = render(analysis)

    if args.write:
        ATTIC.write_text(body, encoding="utf-8")
        print(
            f"wrote {ATTIC} ({analysis['archived']} tombstones, "
            f"{len(analysis['unknown'])} UNKNOWN)"
        )

    if args.check:
        return_code = 0
        for name, target, reason in analysis["defects"]:
            print(f"::error::{name} -> {target}: {reason}")
            return_code = 1

        if not ATTIC.exists():
            print("::error::ATTIC.md missing; run --write")
            return 1

        if ATTIC.read_text(encoding="utf-8") != body:
            print("::error::ATTIC.md is stale. Run: python scripts/build_attic_index.py --write")
            return_code = 1

        for name, _repo in analysis["unknown"]:
            print(
                f"::warning::{name} has no successor pointer and is not declared terminal"
            )

        if return_code == 0:
            print(
                f"ATTIC.md current — {analysis['archived']} tombstones, "
                "0 defects"
            )
        return return_code

    if not (args.write or args.check):
        print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())