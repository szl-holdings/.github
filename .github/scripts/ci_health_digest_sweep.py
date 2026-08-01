#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Complete workflow sweep with explicit evidence provenance.

Source-controlled workflows are included only after their exact workflow file is
proved at the repository's protected default branch, and their runs are read
only through an explicit ``branch=<default>`` filter. GitHub-managed dynamic
workflows, such as Dependabot Updates and default-setup CodeQL, have no
repository file by design; they are admitted through a separate, explicitly
labeled evidence lane and their own workflow endpoint. No source-controlled
workflow ever falls back to an arbitrary branch run.
"""
from __future__ import annotations

import json
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from ci_health_digest_http import (
    ORG,
    ApiError,
    DigestError,
    repository_floor,
    request_json,
)

RED = {"failure", "startup_failure", "timed_out", "action_required"}
SOURCE_WORKFLOW_PREFIX = ".github/workflows/"
DYNAMIC_WORKFLOW_PREFIX = "dynamic/"
POLICY = [
    (
        "lambda-bounty",
        "verify-proof",
        (
            "INTENTIONAL",
            "Proof gate rejects the still-OPEN Λ (Conjecture 1) by design — red is the honest verdict.",
        ),
    ),
    (
        "szl-doctrine",
        "secret-health",
        (
            "FOUNDER-GATED",
            "Needs org secret SECRET_HEALTH_TOKEN (founder least-privilege token).",
        ),
    ),
    (
        "",
        "Dependabot Updates",
        (
            "INFRA",
            "GitHub-managed Dependabot runner state; resolves with the grouped update PR.",
        ),
    ),
    (
        "",
        "CodeQL",
        (
            "INFRA",
            "GitHub-managed CodeQL default-setup state; reconfigure through repository Security settings.",
        ),
    ),
    (
        "",
        "ClusterFuzzLite",
        (
            "INFRA",
            "Outside-contribution fuzzing waits on GitHub's manual workflow approval.",
        ),
    ),
    (
        "",
        "Fuzz",
        (
            "INFRA",
            "Scheduled fuzzing is corpus/infra-driven, not automatically a default-branch regression.",
        ),
    ),
    (
        "",
        "Publish npm",
        (
            "INFRA",
            "Manual publication workflow; a historical manual failure is not branch health.",
        ),
    ),
    (
        "",
        "Cosign keyless",
        (
            "INFRA",
            "Release-only OIDC signing path; requires an actual tagged release.",
        ),
    ),
    (
        "",
        "SLSA",
        (
            "INFRA",
            "Provenance/attestation infrastructure path, not ordinary branch CI.",
        ),
    ),
]


@dataclass(frozen=True)
class RedRun:
    repository: str
    workflow: str
    provenance: str
    conclusion: str
    run_number: int | None
    event: str | None
    url: str | None


def classify(
    repository: str,
    workflow: str,
    *,
    event: str | None = None,
    run_number: int | None = None,
) -> tuple[str, str]:
    if (
        repository == "a11oy"
        and workflow == "Nemo v3 isolated owner GPU dispatch"
        and event == "repository_dispatch"
        and run_number == 10
    ):
        return (
            "INTENTIONAL",
            "Run #10 is the immutable zero-effect Attempt 15 prefetch rejection. "
            "Protected bridge evidence at 53b6e206 quarantines Attempts 15 and 16; "
            "NEVER_RESEND and no future successor.",
        )
    for repository_match, substring, verdict in POLICY:
        if (
            not repository_match or repository_match == repository
        ) and substring.lower() in workflow.lower():
            return verdict
    return "ACTIONABLE", ""


def list_workflows(
    token: str,
    repository: str,
) -> tuple[dict[str, Any], ...]:
    """Return the complete GitHub workflow registry for one repository."""
    workflows: list[dict[str, Any]] = []
    expected_total: int | None = None
    page = 1
    while True:
        _, payload = request_json(
            token,
            (
                f"https://api.github.com/repos/{ORG}/{repository}/actions/"
                f"workflows?per_page=100&page={page}"
            ),
            operation=f"list workflows for {repository} page {page}",
        )
        page_items = payload.get("workflows") if isinstance(payload, dict) else None
        if not isinstance(page_items, list):
            raise DigestError(
                f"workflow inventory for {repository} page {page} is malformed"
            )
        total_count = payload.get("total_count") if isinstance(payload, dict) else None
        if isinstance(total_count, int):
            expected_total = total_count
        for item in page_items:
            if not isinstance(item, dict):
                raise DigestError(
                    f"workflow inventory for {repository} page {page} "
                    "contains a malformed entry"
                )
            workflows.append(item)
        if len(page_items) < 100:
            break
        page += 1
        if page > 100:
            raise DigestError(
                f"workflow pagination for {repository} exceeded 100 pages"
            )
    if expected_total is not None and len(workflows) != expected_total:
        raise DigestError(
            f"workflow inventory count mismatch for {repository}: "
            f"observed={len(workflows)} expected={expected_total}"
        )
    identifiers = [item.get("id") for item in workflows]
    if len(identifiers) != len(set(identifiers)):
        raise DigestError(
            f"workflow inventory for {repository} contains duplicate ids"
        )
    return tuple(workflows)


def workflow_provenance(
    workflow: Mapping[str, Any],
    *,
    repository: str,
) -> tuple[str, str]:
    """Classify one active registry entry into a reviewed evidence lane."""
    path = str(workflow.get("path") or "").strip().lstrip("/")
    if not path or path.endswith("/") or ".." in path.split("/"):
        raise DigestError(
            f"active workflow in {repository} has an invalid workflow path: {path!r}"
        )
    if path.startswith(SOURCE_WORKFLOW_PREFIX):
        if not path.lower().endswith((".yml", ".yaml")):
            raise DigestError(
                f"source workflow in {repository} is not YAML: {path!r}"
            )
        return "protected_default_branch", path
    if path.startswith(DYNAMIC_WORKFLOW_PREFIX):
        return "github_managed_dynamic", path
    raise DigestError(
        f"active workflow in {repository} has an unsupported workflow path: {path!r}"
    )


def _workflow_path(workflow: Mapping[str, Any], *, repository: str) -> str:
    provenance, path = workflow_provenance(workflow, repository=repository)
    if provenance != "protected_default_branch":
        raise DigestError(
            f"workflow in {repository} has no repository-file path: {path!r}"
        )
    return path


def workflow_exists_on_default_branch(
    token: str,
    repository: str,
    default_branch: str,
    workflow: Mapping[str, Any],
) -> bool:
    """Prove that a source-controlled workflow exists at the default branch.

    A 404 means the registry entry belongs to another ref and is safely excluded
    from default-branch health. Every other API or payload failure is terminal.
    """
    path = _workflow_path(workflow, repository=repository)
    encoded_path = urllib.parse.quote(path, safe="/")
    encoded_ref = urllib.parse.quote(default_branch, safe="")
    try:
        _, payload = request_json(
            token,
            (
                f"https://api.github.com/repos/{ORG}/{repository}/contents/"
                f"{encoded_path}?ref={encoded_ref}"
            ),
            operation=(
                f"prove default-branch workflow path "
                f"{repository}/{path}@{default_branch}"
            ),
        )
    except ApiError as exc:
        if exc.status == 404:
            return False
        raise
    if not isinstance(payload, dict):
        raise DigestError(
            f"default-branch workflow lookup for {repository}/{path} is malformed"
        )
    if payload.get("type") != "file" or payload.get("path") != path:
        raise DigestError(
            f"default-branch workflow lookup for {repository}/{path} "
            "did not resolve the exact file"
        )
    sha = str(payload.get("sha") or "")
    if len(sha) != 40:
        raise DigestError(
            f"default-branch workflow {repository}/{path} lacks an immutable blob"
        )
    return True


def _workflow_id(workflow: Mapping[str, Any], repository: str) -> int:
    workflow_id = workflow.get("id")
    if not isinstance(workflow_id, int):
        raise DigestError(
            f"active workflow in {repository} lacks a numeric id"
        )
    return workflow_id


def _one_run(
    payload: Any,
    *,
    repository: str,
    workflow_id: int,
) -> Mapping[str, Any] | None:
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        raise DigestError(
            f"workflow-run inventory for {repository}/{workflow_id} is malformed"
        )
    if not runs:
        return None
    run = runs[0]
    if not isinstance(run, dict):
        raise DigestError(
            f"latest workflow run for {repository}/{workflow_id} is malformed"
        )
    return run


def latest_run(
    token: str,
    repository: str,
    default_branch: str,
    workflow: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Read only the latest source workflow run bound to the default branch."""
    if workflow.get("state") != "active":
        return None
    provenance, _ = workflow_provenance(workflow, repository=repository)
    if provenance != "protected_default_branch":
        raise DigestError(
            f"default-branch reader received {provenance} workflow in {repository}"
        )
    workflow_id = _workflow_id(workflow, repository)
    branch = urllib.parse.quote(default_branch, safe="")
    _, payload = request_json(
        token,
        (
            f"https://api.github.com/repos/{ORG}/{repository}/actions/"
            f"workflows/{workflow_id}/runs?per_page=1&branch={branch}"
        ),
        operation=(
            f"read latest default-branch run for "
            f"{repository}/{workflow_id}@{default_branch}"
        ),
    )
    run = _one_run(payload, repository=repository, workflow_id=workflow_id)
    if run is None:
        return None
    observed_branch = str(run.get("head_branch") or "")
    if observed_branch and observed_branch != default_branch:
        raise DigestError(
            f"branch-filtered workflow run for {repository}/{workflow_id} "
            f"escaped {default_branch!r}: {observed_branch!r}"
        )
    return run


def latest_dynamic_run(
    token: str,
    repository: str,
    workflow: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Read one GitHub-managed dynamic workflow through its own registry ID.

    Dynamic workflows have no repository file and therefore no file-ref lineage.
    Their unfiltered endpoint is an explicit separate evidence contract, never a
    fallback for a source-controlled workflow.
    """
    if workflow.get("state") != "active":
        return None
    provenance, _ = workflow_provenance(workflow, repository=repository)
    if provenance != "github_managed_dynamic":
        raise DigestError(
            f"dynamic reader received {provenance} workflow in {repository}"
        )
    workflow_id = _workflow_id(workflow, repository)
    _, payload = request_json(
        token,
        (
            f"https://api.github.com/repos/{ORG}/{repository}/actions/"
            f"workflows/{workflow_id}/runs?per_page=1"
        ),
        operation=(
            f"read latest GitHub-managed dynamic run for "
            f"{repository}/{workflow_id}"
        ),
    )
    return _one_run(payload, repository=repository, workflow_id=workflow_id)


def _red_run(
    *,
    repository: str,
    workflow: Mapping[str, Any],
    provenance: str,
    run: Mapping[str, Any] | None,
) -> RedRun | None:
    if run is None:
        return None
    conclusion = str(run.get("conclusion") or "")
    if conclusion not in RED:
        return None
    return RedRun(
        repository=repository,
        workflow=str(
            workflow.get("name") or f"workflow-{workflow.get('id')}"
        ),
        provenance=provenance,
        conclusion=conclusion,
        run_number=(
            int(run["run_number"])
            if run.get("run_number") is not None
            else None
        ),
        event=str(run.get("event")) if run.get("event") else None,
        url=str(run.get("html_url")) if run.get("html_url") else None,
    )


def repository_reds(
    token: str,
    repository: Mapping[str, Any],
) -> tuple[str, tuple[RedRun, ...], int, int, int, int]:
    name = str(repository["name"])
    default_branch = str(repository["default_branch"])
    registered = tuple(
        item
        for item in list_workflows(token, name)
        if item.get("state") == "active"
    )
    source_registered: list[Mapping[str, Any]] = []
    dynamic_registered: list[Mapping[str, Any]] = []
    for item in registered:
        provenance, _ = workflow_provenance(item, repository=name)
        if provenance == "protected_default_branch":
            source_registered.append(item)
        elif provenance == "github_managed_dynamic":
            dynamic_registered.append(item)
        else:  # defensive; workflow_provenance is exhaustive and fail-closed
            raise DigestError(
                f"workflow in {name} has unsupported provenance {provenance!r}"
            )

    with ThreadPoolExecutor(max_workers=8) as executor:
        existence = tuple(
            executor.map(
                lambda item: workflow_exists_on_default_branch(
                    token,
                    name,
                    default_branch,
                    item,
                ),
                source_registered,
            )
        )
    source_workflows = tuple(
        item
        for item, present in zip(source_registered, existence)
        if present
    )
    excluded = len(source_registered) - len(source_workflows)

    def inspect_source(workflow: Mapping[str, Any]) -> RedRun | None:
        return _red_run(
            repository=name,
            workflow=workflow,
            provenance="protected_default_branch",
            run=latest_run(token, name, default_branch, workflow),
        )

    def inspect_dynamic(workflow: Mapping[str, Any]) -> RedRun | None:
        return _red_run(
            repository=name,
            workflow=workflow,
            provenance="github_managed_dynamic",
            run=latest_dynamic_run(token, name, workflow),
        )

    results: list[RedRun] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        for result in executor.map(inspect_source, source_workflows):
            if result is not None:
                results.append(result)
        for result in executor.map(inspect_dynamic, dynamic_registered):
            if result is not None:
                results.append(result)
    return (
        name,
        tuple(results),
        len(source_workflows),
        len(dynamic_registered),
        len(registered),
        excluded,
    )


def sweep(
    token: str,
    repositories: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, tuple[RedRun, ...]], dict[str, int]]:
    active = tuple(item for item in repositories if not item.get("archived"))
    reds: dict[str, tuple[RedRun, ...]] = {}
    default_branch_workflows = 0
    github_managed_dynamic_workflows = 0
    registered_active_workflows = 0
    excluded_non_default_workflows = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        for (
            name,
            repository_results,
            default_count,
            dynamic_count,
            registered_count,
            excluded_count,
        ) in executor.map(lambda item: repository_reds(token, item), active):
            default_branch_workflows += default_count
            github_managed_dynamic_workflows += dynamic_count
            registered_active_workflows += registered_count
            excluded_non_default_workflows += excluded_count
            if repository_results:
                reds[name] = repository_results
    inspected_workflows = (
        default_branch_workflows + github_managed_dynamic_workflows
    )
    coverage = {
        "organization_repositories": len(repositories),
        "active_repositories": len(active),
        "archived_repositories": len(repositories) - len(active),
        "queried_active_repositories": len(active),
        "active_workflows": inspected_workflows,
        "default_branch_workflows": default_branch_workflows,
        "github_managed_dynamic_workflows": github_managed_dynamic_workflows,
        "registered_active_workflows": registered_active_workflows,
        "excluded_non_default_workflows": excluded_non_default_workflows,
        "repository_floor": repository_floor(),
    }
    return reds, coverage


def build_body(
    reds: Mapping[str, Sequence[RedRun]],
    *,
    coverage: Mapping[str, int],
    authentication_mode: str,
) -> tuple[str, int, int, dict[str, int]]:
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
            )
            buckets[disposition].append((red, note))
            total += 1

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    default_count = int(
        coverage.get(
            "default_branch_workflows",
            coverage.get("active_workflows", 0),
        )
    )
    dynamic_count = int(
        coverage.get("github_managed_dynamic_workflows", 0)
    )
    registered_count = int(
        coverage.get(
            "registered_active_workflows",
            default_count + dynamic_count,
        )
    )
    excluded_count = int(
        coverage.get("excluded_non_default_workflows", 0)
    )
    lines = [
        (
            "_Auto-generated by `.github/workflows/ci-health-digest.yml`. "
            f"Verified sweep: **{now}**._"
        ),
        "",
        (
            f"Coverage: **{coverage['organization_repositories']} repositories** "
            f"({coverage['active_repositories']} active, "
            f"{coverage['archived_repositories']} archived); "
            f"**{coverage['queried_active_repositories']} active repositories queried**; "
            f"**{default_count} protected-default-branch workflow files** and "
            f"**{dynamic_count} GitHub-managed dynamic workflows** inspected. "
            f"GitHub registered **{registered_count}** active workflow entries; "
            f"**{excluded_count}** source-controlled registrations were excluded "
            "because their files are absent from the repository default branch."
        ),
        "",
        (
            f"Authentication mode: `{authentication_mode}`; "
            "credential value recorded: `false`."
        ),
        "",
    ]
    counts = {key: len(value) for key, value in buckets.items()}
    actionable = counts["ACTIONABLE"]
    lines.extend(
        [
            (
                f"**{total} red workflow(s)** across the verified estate — "
                f"**{actionable} ACTIONABLE**, "
                f"{counts['FOUNDER-GATED']} founder-gated, "
                f"{counts['INTENTIONAL']} intentional, "
                f"{counts['INFRA']} infra."
            ),
            "",
        ]
    )

    order = (
        (
            "ACTIONABLE",
            "### 🛠 Actionable — fix these (root-cause, no bandaids)",
        ),
        (
            "FOUNDER-GATED",
            "### 🔑 Founder-gated — needs a founder secret/action",
        ),
        ("INFRA", "### ⚙️ Infra / low-noise — reconfigure or retire"),
        ("INTENTIONAL", "### ✅ Intentional — red is correct, leave as-is"),
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
                f"| `{red.repository}` | {workflow_cell} | "
                f"`{red.provenance}` | "
                f"{red.conclusion} (run#{red.run_number or ''}) | "
                f"{red.event or ''} | {note} |"
            )
        lines.append("")

    if total == 0:
        lines.extend(
            [
                "## ✅ All clear — no red latest workflow runs in the verified estate.",
                "",
            ]
        )
    lines.extend(
        [
            "---",
            (
                "<sub>Source-controlled workflows are included only when their "
                "files are proven on each repository's protected default branch, "
                "and their runs are branch-bound. GitHub-managed `dynamic/` "
                "workflows are inspected through a separately labeled registry "
                "lane with no repository-file claim. Dispositions are "
                "policy-classified in `.github/scripts/ci_health_digest_sweep.py` "
                "(`POLICY`). Reclassify a red only with a documented reason; "
                "never silence a real defect.</sub>"
            ),
        ]
    )
    return "\n".join(lines), actionable, total, counts


def build_failure_body(
    *,
    error: Exception,
    attempts: Sequence[Mapping[str, Any]],
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return "\n".join(
        [
            (
                "_Auto-generated by `.github/workflows/ci-health-digest.yml`. "
                f"Failed sweep: **{now}**._"
            ),
            "",
            "# ❌ CI health digest NOT VERIFIED",
            "",
            (
                "The organization inventory or workflow evidence could not be "
                "read completely. The previous digest is not being reused as "
                "current evidence."
            ),
            "",
            f"- Failure class: `{type(error).__name__}`",
            f"- Reader attempts: `{json.dumps(list(attempts), sort_keys=True)}`",
            "- Credential value recorded: `false`",
            "",
            (
                "The workflow is fail-closed and must remain red until a "
                "complete authenticated sweep succeeds."
            ),
        ]
    )
