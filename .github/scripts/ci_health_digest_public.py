#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Publish a privacy-safe CI-health projection from the complete org reader.

The underlying reader and sweep still enumerate every repository they are
entitled to read so coverage failures remain fail-closed. This adapter is the
only scheduled publication path in the public ``.github`` repository: it emits
repository/workflow/run detail for public repositories only. Private/internal
repository identities and workflow detail are intentionally not persisted to
the public rolling issue, public-repository artifact, step summary, or optional
notification.

A source workflow in this report is proved to exist at the repository's current
default branch and its selected run is branch-bound. That evidence does *not*
prove branch protection, ruleset coverage, required checks, or merge policy.
Those are independent governance observations.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ci_health_digest import (
    REPORT_SCHEMA,
    _normalize_coverage,
    _write_summary,
    maybe_notify,
    upsert_issue,
)
from ci_health_digest_http import (
    ORG,
    ApiError,
    DigestError,
    ReaderSelectionError,
    select_reader,
)
from ci_health_digest_sweep import (
    RedRun,
    build_failure_body,
    classify,
    sweep,
)

PUBLIC_REPORT_SCHEMA = "szl.ci-health-digest.public-projection/v1"
SOURCE_PROVENANCE_INTERNAL = "protected_default_branch"
SOURCE_PROVENANCE_PUBLIC = "default_branch_source"
PUBLICATION_SCOPE = "PUBLIC_REPOSITORY_DETAILS_ONLY"


def repository_visibility(repository: Mapping[str, Any]) -> str:
    """Return public/private only when GitHub metadata is self-consistent."""
    private = repository.get("private")
    visibility = str(repository.get("visibility") or "").strip().lower()
    if private is True:
        if visibility not in {"", "private", "internal"}:
            raise DigestError("repository visibility metadata is contradictory")
        return "private"
    if private is False:
        if visibility not in {"", "public"}:
            raise DigestError("repository visibility metadata is contradictory")
        return "public"
    raise DigestError("repository visibility metadata is unavailable")


def public_projection(
    repositories: Sequence[Mapping[str, Any]],
    reds: Mapping[str, Sequence[RedRun]],
) -> tuple[dict[str, tuple[RedRun, ...]], dict[str, Any]]:
    """Project detail to public repositories without retaining private names."""
    visibility_by_name: dict[str, str] = {}
    public_active = 0
    private_active = 0
    for repository in repositories:
        name = str(repository.get("name") or "").strip()
        if not name:
            raise DigestError("repository inventory contains an unnamed entry")
        if name in visibility_by_name:
            raise DigestError("repository inventory contains duplicate names")
        visibility = repository_visibility(repository)
        visibility_by_name[name] = visibility
        if repository.get("archived"):
            continue
        if visibility == "public":
            public_active += 1
        else:
            private_active += 1

    projected: dict[str, tuple[RedRun, ...]] = {}
    private_red_workflows = 0
    for name, runs in reds.items():
        visibility = visibility_by_name.get(name)
        if visibility is None:
            raise DigestError("sweep result references an unknown repository")
        if visibility == "private":
            private_red_workflows += len(runs)
            continue
        converted: list[RedRun] = []
        for run in runs:
            provenance = run.provenance
            if provenance == SOURCE_PROVENANCE_INTERNAL:
                provenance = SOURCE_PROVENANCE_PUBLIC
            converted.append(replace(run, provenance=provenance))
        if converted:
            projected[name] = tuple(converted)

    return projected, {
        "scope": PUBLICATION_SCOPE,
        "public_active_repositories": public_active,
        "private_active_repositories_withheld": private_active,
        "private_red_workflows_withheld": private_red_workflows,
        "private_repository_identities_persisted": False,
        "private_workflow_details_persisted": False,
        "branch_protection_inferred": False,
        "private_detail_sink": "UNAVAILABLE_IN_PUBLIC_WORKFLOW",
    }


def _bucket_public_reds(
    reds: Mapping[str, Sequence[RedRun]],
) -> tuple[dict[str, list[tuple[RedRun, str]]], int]:
    buckets: dict[str, list[tuple[RedRun, str]]] = {
        "ACTIONABLE": [],
        "FOUNDER-GATED": [],
        "INTENTIONAL": [],
        "INFRA": [],
    }
    total = 0
    for repository in sorted(reds):
        for red in reds[repository]:
            disposition, note = classify(
                repository,
                red.workflow,
                event=red.event,
                run_number=red.run_number,
                run_id=red.run_id,
                run_attempt=red.run_attempt,
            )
            buckets[disposition].append((red, note))
            total += 1
    return buckets, total


def build_public_body(
    reds: Mapping[str, Sequence[RedRun]],
    *,
    coverage: Mapping[str, Any],
    publication: Mapping[str, Any],
    authentication_mode: str,
) -> tuple[str, int, int, dict[str, int]]:
    """Build the public issue without claiming branch-protection evidence."""
    buckets, total = _bucket_public_reds(reds)
    counts = {key: len(value) for key, value in buckets.items()}
    actionable = counts["ACTIONABLE"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    default_count = int(
        coverage.get(
            "default_branch_workflows",
            coverage.get("active_workflows", 0),
        )
    )
    dynamic_count = int(coverage.get("github_managed_dynamic_workflows", 0))
    registered_count = int(
        coverage.get(
            "registered_active_workflows",
            default_count + dynamic_count,
        )
    )
    excluded_count = int(coverage.get("excluded_non_default_workflows", 0))

    lines = [
        (
            "_Auto-generated by `.github/workflows/ci-health-digest.yml`. "
            f"Verified public projection: **{now}**._"
        ),
        "",
        "## Publication boundary",
        "",
        (
            "The authenticated reader completed its configured organization sweep, "
            "but this public issue publishes repository/workflow/run detail for "
            "**public repositories only**. Private/internal repository identities, "
            "workflow names, run links, and run metadata are withheld and are not "
            "persisted in this public workflow's report artifact."
        ),
        "",
        (
            "`default_branch_source` means the workflow file was proved at the "
            "repository's current default branch and the selected source-controlled "
            "run was branch-bound. It does **not** prove branch protection, a "
            "ruleset, required checks, review policy, or release admission."
        ),
        "",
        (
            "A private full-detail report requires a separately reviewed private "
            "sink/owner. This public publisher does not create, repurpose, or "
            "upgrade credentials to manufacture one."
        ),
        "",
        (
            f"Public projection: **{publication['public_active_repositories']} active "
            "public repositories**. Private/internal detail: **WITHHELD**."
        ),
        "",
        (
            f"Full-reader workflow coverage: **{default_count} default-branch source "
            f"workflow files** and **{dynamic_count} GitHub-managed dynamic workflows**. "
            f"GitHub registered **{registered_count}** active workflow entries; "
            f"**{excluded_count}** source-controlled registrations were excluded "
            "because their files were absent from the repository default branch."
        ),
        "",
        (
            f"Authentication mode: `{authentication_mode}`; credential value "
            "recorded: `false`."
        ),
        "",
        (
            f"**{total} red public workflow(s)** — **{actionable} ACTIONABLE**, "
            f"{counts['FOUNDER-GATED']} founder-gated, "
            f"{counts['INTENTIONAL']} intentional, {counts['INFRA']} infra."
        ),
        "",
    ]

    order = (
        ("ACTIONABLE", "### 🛠 Actionable — public source evidence"),
        ("FOUNDER-GATED", "### 🔑 Founder-gated — public source evidence"),
        ("INFRA", "### ⚙️ Infra / low-noise — public source evidence"),
        ("INTENTIONAL", "### ✅ Intentional — public source evidence"),
    )
    for key, heading in order:
        rows = buckets[key]
        if not rows:
            continue
        lines.extend(
            [
                heading,
                "",
                "| Repo | Workflow | Evidence | Result | Trigger | Note |",
                "|---|---|---|---|---|---|",
            ]
        )
        for red, note in sorted(
            rows,
            key=lambda item: (item[0].repository, item[0].workflow),
        ):
            workflow_cell = (
                f"[{red.workflow}]({red.url})" if red.url else red.workflow
            )
            lines.append(
                f"| `{red.repository}` | {workflow_cell} | `{red.provenance}` | "
                f"{red.conclusion} (run#{red.run_number or ''}) | "
                f"{red.event or ''} | {note} |"
            )
        lines.append("")

    if total == 0:
        lines.extend(
            [
                "## ✅ No red latest workflow runs in the verified public projection.",
                "",
                (
                    "This is not a whole-organization all-clear because private/internal "
                    "detail is intentionally outside this public publication surface."
                ),
                "",
            ]
        )
    lines.extend(
        [
            "---",
            (
                "<sub>Source-controlled workflow evidence is default-branch-source "
                "evidence, not branch-protection evidence. GitHub-managed `dynamic/` "
                "workflows use a separate registry lane. Classification is advisory; "
                "reclassify only with a documented reason and never silence a real "
                "defect.</sub>"
            ),
        ]
    )
    return "\n".join(lines), actionable, total, counts


def sanitized_attempts(
    attempts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Keep credential-selection state while dropping inventory cardinality."""
    allowed = {
        "mode",
        "credential_name",
        "present",
        "result",
        "failure_type",
        "failure_class",
        "authoritative_inventory_match",
        "value_recorded",
    }
    return [
        {key: value for key, value in attempt.items() if key in allowed}
        for attempt in attempts
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        default=(
            os.environ.get("REPORT_PATH")
            or "reports/ci-health-digest.json"
        ),
    )
    args = parser.parse_args(argv)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "schema": PUBLIC_REPORT_SCHEMA,
        "source_report_schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation": os.environ.get("GITHUB_SHA"),
        "organization": ORG,
        "status": "NOT_VERIFIED",
        "authentication": {
            "mode": "unavailable",
            "credential_name": None,
            "value_recorded": False,
            "attempts": [],
        },
        "coverage": None,
        "publication": {
            "scope": PUBLICATION_SCOPE,
            "private_repository_identities_persisted": False,
            "private_workflow_details_persisted": False,
            "branch_protection_inferred": False,
        },
        "red_runs": {},
        "summary": {"actionable": 0, "red_total": 0},
        "issue": None,
        "notification": None,
    }
    body = ""
    reader_attempts: Sequence[Mapping[str, Any]] = ()

    try:
        reader = select_reader()
        reader_attempts = reader.attempts
        safe_attempts = sanitized_attempts(reader.attempts)
        report["authentication"] = {
            "mode": reader.mode,
            "credential_name": reader.credential_name,
            "value_recorded": False,
            "attempts": safe_attempts,
            "app_token_outcome": (
                os.environ.get("APP_TOKEN_OUTCOME") or "not_recorded"
            ),
        }
        full_reds, coverage = sweep(reader.token, reader.repositories)
        coverage = _normalize_coverage(coverage)
        public_reds, publication = public_projection(
            reader.repositories,
            full_reds,
        )
        body, actionable, red_total, dispositions = build_public_body(
            public_reds,
            coverage=coverage,
            publication=publication,
            authentication_mode=reader.mode,
        )
        issue = upsert_issue(body, red_total=red_total)
        notification = maybe_notify(actionable, red_total)
        report.update(
            {
                "status": "VERIFIED_PUBLIC_PROJECTION",
                "coverage": coverage,
                "publication": publication,
                "red_runs": {
                    repository: [asdict(item) for item in items]
                    for repository, items in public_reds.items()
                },
                "summary": {
                    "actionable": actionable,
                    "red_total": red_total,
                    "dispositions": dispositions,
                },
                "issue": issue,
                "notification": notification,
            }
        )
        exit_code = 0
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, ReaderSelectionError):
            reader_attempts = exc.attempts
        report["authentication"]["attempts"] = sanitized_attempts(reader_attempts)
        report["fatal"] = {
            "type": type(exc).__name__,
            "detail_class": (
                exc.detail_class
                if isinstance(exc, ApiError)
                else "coverage_or_execution_failure"
            ),
        }
        body = build_failure_body(
            error=exc,
            attempts=sanitized_attempts(reader_attempts),
        )
        try:
            report["issue"] = upsert_issue(body, red_total=None)
        except Exception as issue_exc:  # noqa: BLE001
            report["issue_error"] = {"type": type(issue_exc).__name__}
        exit_code = 1

    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_summary(body, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "publication_scope": report["publication"]["scope"],
                "red_total": report["summary"]["red_total"],
                "actionable": report["summary"]["actionable"],
                "private_details_persisted": False,
            },
            sort_keys=True,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
