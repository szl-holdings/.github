#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. — SZL Holdings
"""Generate and validate ATTIC.md from the live public estate plus portfolio policy.

The GitHub API owns current repository state. ``governance/archive-portfolio-v1.json``
owns lifecycle disposition, canonical migration targets, and Hugging Face showcase
routing. Neither descriptions nor plausible-looking repository names are treated
as authority.

Usage
-----
    python scripts/build_attic_index.py --write
    python scripts/build_attic_index.py --check
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

ORG = "szl-holdings"
ROOT = Path(__file__).resolve().parent.parent
ATTIC = ROOT / "ATTIC.md"
PORTFOLIO = ROOT / "governance" / "archive-portfolio-v1.json"
SCHEMA = "szl.archive-portfolio/v1"
DISPOSITIONS = frozenset({"restore", "consolidate", "historical"})


class AtticError(RuntimeError):
    """A lifecycle contract or provider-state defect."""


def load_portfolio(path: Path = PORTFOLIO) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AtticError(f"portfolio manifest unreadable: {exc}") from exc
    if value.get("schema") != SCHEMA:
        raise AtticError(f"unsupported portfolio schema: {value.get('schema')!r}")
    if value.get("organization") != ORG:
        raise AtticError("portfolio organization does not match generator")
    rows = value.get("repositories")
    if not isinstance(rows, list) or not rows:
        raise AtticError("portfolio repositories must be a non-empty list")
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise AtticError(f"portfolio row {index} must be an object")
        name = row.get("name")
        disposition = row.get("disposition")
        targets = row.get("canonical_targets")
        if not isinstance(name, str) or not name or "/" in name or name in seen:
            raise AtticError(f"invalid or duplicate portfolio name at row {index}")
        seen.add(name)
        if disposition not in DISPOSITIONS:
            raise AtticError(f"{name}: invalid disposition")
        if not isinstance(targets, list) or any(
            not isinstance(item, str) or not item or "/" in item for item in targets
        ):
            raise AtticError(f"{name}: invalid canonical_targets")
        if disposition == "restore" and targets:
            raise AtticError(f"{name}: restore row cannot delegate authority")
        if disposition == "consolidate" and not targets:
            raise AtticError(f"{name}: consolidate row requires canonical_targets")
        if disposition == "historical" and targets:
            raise AtticError(f"{name}: historical row cannot declare a successor")
        for field in ("rationale", "hugging_face_showcase"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise AtticError(f"{name}: missing {field}")
    observed = (value.get("source_inventory") or {}).get(
        "archived_public_repositories_observed"
    )
    if observed != len(rows):
        raise AtticError("portfolio source inventory count is inconsistent")
    return value


def fetch_repos() -> list[dict[str, Any]]:
    """Read repositories visible to an unauthenticated public estate visitor."""
    completed = subprocess.run(
        [
            "gh",
            "repo",
            "list",
            ORG,
            "--limit",
            "500",
            "--json",
            "name,description,isArchived,isPrivate,url",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    repos = json.loads(completed.stdout)
    if not isinstance(repos, list):
        raise AtticError("GitHub repository inventory was not a list")
    return [repo for repo in repos if not repo.get("isPrivate", False)]


def analyse(
    repos: list[dict[str, Any]],
    portfolio: Mapping[str, Any],
) -> dict[str, Any]:
    by_name = {str(repo["name"]): repo for repo in repos}
    rows = {str(row["name"]): row for row in portfolio["repositories"]}
    archived_names = {
        name for name, repo in by_name.items() if bool(repo.get("isArchived"))
    }
    restore_names = {
        name for name, row in rows.items() if row["disposition"] == "restore"
    }

    defects: list[dict[str, str]] = []
    unclassified = sorted(archived_names - set(rows))
    for name in unclassified:
        defects.append(
            {
                "repository": name,
                "code": "UNCLASSIFIED_ARCHIVE",
                "detail": "public archived repository is absent from archive-portfolio-v1",
            }
        )

    for name in sorted(set(rows) - set(by_name)):
        defects.append(
            {
                "repository": name,
                "code": "MANIFEST_REPOSITORY_MISSING",
                "detail": "portfolio row is absent from the public organization inventory",
            }
        )

    pending_restore: list[dict[str, Any]] = []
    restored: list[dict[str, Any]] = []
    consolidated: list[dict[str, Any]] = []
    historical: list[dict[str, Any]] = []

    for name, row in sorted(rows.items()):
        repo = by_name.get(name)
        if repo is None:
            continue
        archived = bool(repo.get("isArchived"))
        disposition = row["disposition"]
        entry = {
            "name": name,
            "rationale": row["rationale"],
            "canonical_targets": list(row["canonical_targets"]),
            "hugging_face_showcase": row["hugging_face_showcase"],
        }
        if disposition == "restore":
            (pending_restore if archived else restored).append(entry)
        elif disposition == "consolidate":
            if not archived:
                defects.append(
                    {
                        "repository": name,
                        "code": "CONSOLIDATION_TOMBSTONE_ACTIVE",
                        "detail": "consolidated repository was reactivated outside the restoration wave",
                    }
                )
            else:
                consolidated.append(entry)
        elif disposition == "historical":
            if not archived:
                defects.append(
                    {
                        "repository": name,
                        "code": "HISTORICAL_RECORD_ACTIVE",
                        "detail": "immutable historical repository was reactivated",
                    }
                )
            else:
                historical.append(entry)

        for target in row["canonical_targets"]:
            target_repo = by_name.get(target)
            if target_repo is None:
                defects.append(
                    {
                        "repository": name,
                        "code": "CANONICAL_TARGET_MISSING",
                        "detail": target,
                    }
                )
            elif bool(target_repo.get("isArchived")) and target not in restore_names:
                defects.append(
                    {
                        "repository": name,
                        "code": "CANONICAL_TARGET_ARCHIVED",
                        "detail": target,
                    }
                )

    return {
        "total": len(repos),
        "active": len(repos) - len(archived_names),
        "archived": len(archived_names),
        "pending_restore": pending_restore,
        "restored": restored,
        "consolidated": consolidated,
        "historical": historical,
        "defects": defects,
        "unclassified": unclassified,
    }


def _targets(values: list[str]) -> str:
    return ", ".join(
        f"[`{value}`](https://github.com/{ORG}/{value})" for value in values
    )


def _space(value: str) -> str:
    slug = value.split("/", 1)[-1]
    return f"[`{value}`](https://huggingface.co/spaces/{value})"


def render(analysis: Mapping[str, Any]) -> str:
    lines: list[str] = [
        "# ATTIC — SZL Holdings repository lifecycle index",
        "",
        "<!-- GENERATED FILE — do not edit by hand. -->",
        "<!-- Regenerate: python scripts/build_attic_index.py --write -->",
        "",
        "This index joins live public GitHub repository state with the reviewed "
        "`governance/archive-portfolio-v1.json` lifecycle authority. Repository "
        "descriptions are informative only; they cannot silently choose a successor.",
        "",
        "**Rule.** Restore only unique maintained authorities. Move reusable source "
        "from consolidation tombstones into named active owners through reviewed PRs. "
        "Keep published evidence immutable. Present the result through existing "
        "Hugging Face flagships rather than multiplying Spaces.",
        "",
        "## Estate shape",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Public repositories total | {analysis['total']} |",
        f"| Active public repositories | {analysis['active']} |",
        f"| Archived public repositories | {analysis['archived']} |",
        f"| Strategic restorations pending | {len(analysis['pending_restore'])} |",
        f"| Strategic restorations completed | {len(analysis['restored'])} |",
        f"| Consolidation tombstones | {len(analysis['consolidated'])} |",
        f"| Immutable historical records | {len(analysis['historical'])} |",
        f"| Structural defects | {len(analysis['defects'])} |",
        "",
    ]

    if analysis["defects"]:
        lines.extend(
            [
                "## ⛔ Structural defects — fail closed",
                "",
                "| Repository | Code | Detail |",
                "|---|---|---|",
            ]
        )
        for row in analysis["defects"]:
            lines.append(
                f"| `{row['repository']}` | `{row['code']}` | {row['detail']} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Strategic restoration wave",
            "",
            "A pending row remains archived because repository-administration "
            "authority has not yet produced provider readback. It is not presented "
            "as an active source until GitHub reports `archived=false`.",
            "",
            "| Repository | State | Maintained role | Hugging Face showcase |",
            "|---|---|---|---|",
        ]
    )
    for state, rows in (
        ("PENDING_ADMIN_AUTHORITY", analysis["pending_restore"]),
        ("RESTORED_READBACK_VERIFIED", analysis["restored"]),
    ):
        for row in rows:
            lines.append(
                f"| `{row['name']}` | `{state}` | {row['rationale']} | "
                f"{_space(row['hugging_face_showcase'])} |"
            )
    lines.append("")

    lines.extend(
        [
            "## Consolidation tombstones",
            "",
            "| Archived repository | Canonical owner(s) | Hugging Face showcase | Rationale |",
            "|---|---|---|---|",
        ]
    )
    for row in analysis["consolidated"]:
        lines.append(
            f"| `{row['name']}` | {_targets(row['canonical_targets'])} | "
            f"{_space(row['hugging_face_showcase'])} | {row['rationale']} |"
        )
    lines.append("")

    lines.extend(
        [
            "## Immutable historical evidence",
            "",
            "| Archived repository | Public showcase | Retention rationale |",
            "|---|---|---|",
        ]
    )
    for row in analysis["historical"]:
        lines.append(
            f"| `{row['name']}` | {_space(row['hugging_face_showcase'])} | "
            f"{row['rationale']} |"
        )
    lines.extend(
        [
            "",
            "---",
            "",
            "Generated by `scripts/build_attic_index.py`. CI runs `--check`; "
            "unclassified archives, hidden reactivations, missing canonical targets, "
            "and stale provider state are terminal.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="regenerate ATTIC.md")
    parser.add_argument("--check", action="store_true", help="fail on drift or defects")
    args = parser.parse_args()

    try:
        portfolio = load_portfolio()
        analysis = analyse(fetch_repos(), portfolio)
        body = render(analysis)
    except (AtticError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    if args.write:
        ATTIC.write_text(body, encoding="utf-8")
        print(
            f"wrote {ATTIC} ({analysis['archived']} archived, "
            f"{len(analysis['pending_restore'])} restoration pending)"
        )

    return_code = 0
    if args.check:
        for defect in analysis["defects"]:
            print(
                f"::error::{defect['repository']} {defect['code']}: "
                f"{defect['detail']}"
            )
            return_code = 1
        if not ATTIC.exists():
            print("::error::ATTIC.md missing; run --write")
            return 1
        if ATTIC.read_text(encoding="utf-8") != body:
            print("::error::ATTIC.md is stale. Run: python scripts/build_attic_index.py --write")
            return_code = 1
        for row in analysis["pending_restore"]:
            print(
                f"::warning::{row['name']} remains PENDING_ADMIN_AUTHORITY"
            )
        if return_code == 0:
            print(
                f"ATTIC.md current — {analysis['archived']} archived, "
                f"{len(analysis['pending_restore'])} restoration pending, 0 defects"
            )

    if not (args.write or args.check):
        print(body)
    return return_code


if __name__ == "__main__":
    sys.exit(main())
