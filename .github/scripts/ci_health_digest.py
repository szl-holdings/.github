#!/usr/bin/env python3
"""Authenticated, fail-closed organization CI health digest.

The digest has two distinct credentials:

* a read identity that must prove access to the complete installed organization
  estate and GitHub Actions metadata; and
* the ephemeral repository ``GITHUB_TOKEN`` used only to update the deterministic
  digest issue in ``szl-holdings/.github``.

The read identity is App-first. A short-lived qillqaq installation token is
preferred, with the governed ``ORG_CI_READ_TOKEN`` retained as a bounded
migration fallback. The built-in workflow token is never accepted as the org
read identity because it cannot prove private cross-repository coverage.

Every API error, coverage-floor violation, partial sweep, and issue-write failure
is terminal. No credential value, prefix, length, hash, identity response, or
authorization header is written to the report or logs.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

ORG = "szl-holdings"
REPORT_SCHEMA = "szl.ci-health-digest/v2"
ISSUE_NUMBER = 158
ISSUE_MARKER = "<!-- szl-ci-health-digest -->"
USER_AGENT = "szl-ci-health-digest/2"

EXPECTED_TOTAL_FLOOR = int(os.environ.get("CI_DIGEST_REPO_FLOOR", "57"))
EXPECTED_ACTIVE_FLOOR = int(os.environ.get("CI_DIGEST_ACTIVE_FLOOR", "52"))
EXPECTED_PRIVATE_FLOOR = int(os.environ.get("CI_DIGEST_PRIVATE_FLOOR", "3"))
STALE_DAYS = int(os.environ.get("CI_DIGEST_STALE_DAYS", "14"))
MAX_WORKERS = int(os.environ.get("CI_DIGEST_WORKERS", "8"))

IGNORE_NAMES = {
    "Organization Health Dashboard",
    "CI Health Digest",
    "CI Health Digest State — Read-Only Diagnostics",
    "Scorecard supply-chain security",
    "OpenSSF Scorecard",
    "Dependency Review",
}

FOUNDER_PATTERNS = (
    "GHCR Lifecycle",
    "GHCR Vulnerability Scan",
    "Owner Governed GPU Receipt",
)

INFRA_PATTERNS = (
    "Cosign keyless",
    "Fuzz",
    "CodeQL",
    "Release Drafter",
    "Dependabot",
    "Build + push",
    "Deploy",
    "docker",
    "publish",
    "release",
)


class DigestError(RuntimeError):
    """Terminal digest failure with a credential-safe message."""


class ApiError(DigestError):
    """GitHub API failure that never contains a credential value."""

    def __init__(self, method: str, path: str, status: int | str, detail: str = ""):
        suffix = f": {detail[:300]}" if detail else ""
        super().__init__(f"GitHub API {method} {path} failed ({status}){suffix}")
        self.method = method
        self.path = path
        self.status = status


@dataclass(frozen=True)
class ReadIdentity:
    mode: str
    credential_name: str
    token: str
    repositories: tuple[dict[str, Any], ...]
    total_repositories: int
    active_repositories: int
    archived_repositories: int
    private_repositories: int
    action_probes: tuple[str, ...]


@dataclass(frozen=True)
class RedRun:
    repo: str
    workflow: str
    workflow_id: int | None
    run_id: int
    run_number: int | None
    conclusion: str
    event: str
    created_at: str
    url: str
    category: str
    reason: str


@dataclass(frozen=True)
class RepoSweep:
    repo: str
    workflows: int
    reds: tuple[RedRun, ...]
    error: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_detail(value: object) -> str:
    text = str(value or "").replace("\x00", "").strip()
    text = re.sub(r"(token|authorization|bearer)\s+[^\s]+", r"\1 [REDACTED]", text, flags=re.I)
    return text[:300]


def api_json(
    token: str,
    path: str,
    *,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
    expected: Sequence[int] = (200,),
    retries: int = 3,
) -> Any:
    if not token:
        raise ApiError(method, path, "NO_CREDENTIAL")
    data = json.dumps(payload, sort_keys=True).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        method=method,
        data=data,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    last_error: ApiError | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
                if int(response.status) not in expected:
                    raise ApiError(method, path, int(response.status))
                if not raw:
                    return None
                try:
                    return json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError as exc:
                    raise ApiError(method, path, int(response.status), "non-JSON response") from exc
        except urllib.error.HTTPError as exc:
            detail = _safe_detail(exc.read().decode("utf-8", errors="replace"))
            last_error = ApiError(method, path, exc.code, detail)
            if exc.code not in {429, 500, 502, 503, 504} or attempt + 1 >= retries:
                raise last_error from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = ApiError(method, path, "NETWORK", _safe_detail(exc))
            if attempt + 1 >= retries:
                raise last_error from exc
        time.sleep(2**attempt)
    raise last_error or ApiError(method, path, "UNKNOWN")


def _paginate_list(token: str, path: str) -> list[Any]:
    output: list[Any] = []
    page = 1
    separator = "&" if "?" in path else "?"
    while True:
        result = api_json(token, f"{path}{separator}per_page=100&page={page}")
        if not isinstance(result, list):
            raise DigestError(f"expected list response for {path}")
        output.extend(result)
        if len(result) < 100:
            return output
        page += 1


def _paginate_object_list(token: str, path: str, key: str) -> list[Any]:
    output: list[Any] = []
    page = 1
    separator = "&" if "?" in path else "?"
    while True:
        result = api_json(token, f"{path}{separator}per_page=100&page={page}")
        if not isinstance(result, dict) or not isinstance(result.get(key), list):
            raise DigestError(f"expected object list {key!r} for {path}")
        items = result[key]
        output.extend(items)
        if len(items) < 100:
            return output
        page += 1


def load_repositories(mode: str, token: str) -> list[dict[str, Any]]:
    if mode == "github_app":
        raw = _paginate_object_list(token, "/installation/repositories", "repositories")
    elif mode == "governed_pat_fallback":
        raw = _paginate_list(token, f"/orgs/{ORG}/repos?type=all")
    else:
        raise DigestError(f"unsupported read identity mode {mode!r}")
    repos = [item for item in raw if isinstance(item, dict)]
    if len(repos) != len(raw):
        raise DigestError("repository inventory contained non-object entries")
    return repos


def verify_actions_read(token: str, repository_full_name: str) -> None:
    encoded = urllib.parse.quote(repository_full_name, safe="/")
    result = api_json(token, f"/repos/{encoded}/actions/runs?per_page=1")
    if not isinstance(result, dict) or not isinstance(result.get("workflow_runs"), list):
        raise DigestError(f"Actions read probe returned an unexpected shape for {repository_full_name}")


def assess_identity(
    mode: str,
    credential_name: str,
    token: str,
    *,
    repository_loader: Callable[[str, str], list[dict[str, Any]]] = load_repositories,
    actions_probe: Callable[[str, str], None] = verify_actions_read,
) -> ReadIdentity:
    if not token:
        raise DigestError(f"{credential_name} is not configured")
    repos = repository_loader(mode, token)
    total = len(repos)
    archived = sum(bool(repo.get("archived")) for repo in repos)
    active = total - archived
    private = sum(bool(repo.get("private")) for repo in repos)
    if total < EXPECTED_TOTAL_FLOOR:
        raise DigestError(
            f"{credential_name} exposed {total} repositories; expected at least {EXPECTED_TOTAL_FLOOR}"
        )
    if active < EXPECTED_ACTIVE_FLOOR:
        raise DigestError(
            f"{credential_name} exposed {active} active repositories; expected at least {EXPECTED_ACTIVE_FLOOR}"
        )
    if private < EXPECTED_PRIVATE_FLOOR:
        raise DigestError(
            f"{credential_name} exposed {private} private repositories; expected at least {EXPECTED_PRIVATE_FLOOR}"
        )

    by_name = {
        str(repo.get("full_name") or ""): repo
        for repo in repos
        if str(repo.get("full_name") or "")
    }
    probes = [f"{ORG}/.github"]
    private_names = sorted(
        name for name, repo in by_name.items() if bool(repo.get("private"))
    )
    if private_names:
        probes.append(private_names[0])
    for repository_full_name in probes:
        if repository_full_name not in by_name:
            raise DigestError(f"required repository {repository_full_name} is absent from inventory")
        actions_probe(token, repository_full_name)

    return ReadIdentity(
        mode=mode,
        credential_name=credential_name,
        token=token,
        repositories=tuple(repos),
        total_repositories=total,
        active_repositories=active,
        archived_repositories=archived,
        private_repositories=private,
        action_probes=tuple(probes),
    )


def select_read_identity(
    candidates: Sequence[tuple[str, str, str]] | None = None,
) -> tuple[ReadIdentity, tuple[str, ...]]:
    if candidates is None:
        candidates = (
            ("github_app", "QILLQAQ_APP_TOKEN", os.environ.get("QILLQAQ_TOKEN", "")),
            (
                "governed_pat_fallback",
                "ORG_CI_READ_TOKEN",
                os.environ.get("ORG_CI_READ_TOKEN", ""),
            ),
        )
    errors: list[str] = []
    for mode, credential_name, token in candidates:
        try:
            return assess_identity(mode, credential_name, token), tuple(errors)
        except DigestError as exc:
            errors.append(f"{credential_name}: {exc}")
    raise DigestError("no complete organization CI read identity is usable; " + "; ".join(errors))


def _object_items(token: str, path: str, key: str) -> list[dict[str, Any]]:
    raw = _paginate_object_list(token, path, key)
    if not all(isinstance(item, dict) for item in raw):
        raise DigestError(f"{path} returned non-object entries")
    return list(raw)


def list_workflows(token: str, repo: str) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote(repo, safe="/")
    return _object_items(token, f"/repos/{encoded}/actions/workflows", "workflows")


def latest_completed_run(token: str, repo: str, workflow_id: int) -> dict[str, Any] | None:
    encoded = urllib.parse.quote(repo, safe="/")
    result = api_json(
        token,
        f"/repos/{encoded}/actions/workflows/{workflow_id}/runs?per_page=20",
    )
    if not isinstance(result, dict) or not isinstance(result.get("workflow_runs"), list):
        raise DigestError(f"workflow run response is malformed for {repo}:{workflow_id}")
    for run in result["workflow_runs"]:
        if isinstance(run, dict) and run.get("status") == "completed":
            return run
    return None


def classify_red(repo: str, workflow: Mapping[str, Any], run: Mapping[str, Any]) -> tuple[str, str]:
    del repo
    name = str(workflow.get("name") or "")
    event = str(run.get("event") or "")
    actor = str((run.get("actor") or {}).get("login") or "")
    created_raw = str(run.get("created_at") or "")
    try:
        created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
    except ValueError:
        created = datetime.min.replace(tzinfo=timezone.utc)

    if any(pattern.lower() in name.lower() for pattern in FOUNDER_PATTERNS):
        return "FOUNDER_GATED", "requires a founder-controlled deployment, registry, or owner-host credential"
    if event == "release" or any(pattern.lower() in name.lower() for pattern in INFRA_PATTERNS):
        return "INFRA", "release/deployment/supply-chain lane; verify only when that lane is intentionally exercised"
    if created < datetime.now(timezone.utc) - timedelta(days=STALE_DAYS):
        return "INFRA", f"latest completed failure is older than {STALE_DAYS} days"
    if actor == "dependabot[bot]":
        return "INFRA", "automation-owned historical run"
    return "ACTIONABLE", "latest completed run is a current failure or cancellation"


def sweep_repository(repo: Mapping[str, Any], token: str) -> RepoSweep:
    full_name = str(repo.get("full_name") or "")
    if not full_name:
        return RepoSweep(repo="<missing>", workflows=0, reds=(), error="repository lacks full_name")
    try:
        workflows = list_workflows(token, full_name)
        reds: list[RedRun] = []
        for workflow in workflows:
            name = str(workflow.get("name") or "")
            if name in IGNORE_NAMES or str(workflow.get("state") or "") == "disabled_manually":
                continue
            workflow_id = workflow.get("id")
            if not isinstance(workflow_id, int):
                raise DigestError(f"workflow {name!r} in {full_name} lacks an integer id")
            run = latest_completed_run(token, full_name, workflow_id)
            if not run or run.get("conclusion") not in {"failure", "cancelled", "timed_out", "action_required"}:
                continue
            category, reason = classify_red(full_name, workflow, run)
            run_id = run.get("id")
            if not isinstance(run_id, int):
                raise DigestError(f"workflow {name!r} in {full_name} returned a run without an integer id")
            reds.append(
                RedRun(
                    repo=full_name.split("/", 1)[-1],
                    workflow=name,
                    workflow_id=workflow_id,
                    run_id=run_id,
                    run_number=run.get("run_number") if isinstance(run.get("run_number"), int) else None,
                    conclusion=str(run.get("conclusion") or "unknown"),
                    event=str(run.get("event") or "unknown"),
                    created_at=str(run.get("created_at") or ""),
                    url=str(run.get("html_url") or ""),
                    category=category,
                    reason=reason,
                )
            )
        return RepoSweep(repo=full_name, workflows=len(workflows), reds=tuple(reds))
    except DigestError as exc:
        return RepoSweep(repo=full_name, workflows=0, reds=(), error=str(exc))


def sweep_all(identity: ReadIdentity) -> tuple[list[RepoSweep], list[RedRun], list[str]]:
    active = [repo for repo in identity.repositories if not bool(repo.get("archived"))]
    sweeps: list[RepoSweep] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(sweep_repository, repo, identity.token) for repo in active]
        for future in concurrent.futures.as_completed(futures):
            sweeps.append(future.result())
    sweeps.sort(key=lambda item: item.repo)
    reds = sorted(
        (red for sweep in sweeps for red in sweep.reds),
        key=lambda item: (item.category, item.repo, item.workflow),
    )
    errors = [f"{sweep.repo}: {sweep.error}" for sweep in sweeps if sweep.error]
    return sweeps, reds, errors


def _table(rows: Iterable[RedRun]) -> str:
    items = list(rows)
    if not items:
        return "_None._\n"
    lines = [
        "| Repo | Workflow | Result | Trigger | Observed | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for item in items:
        workflow = f"[{item.workflow}]({item.url})" if item.url else item.workflow
        lines.append(
            f"| `{item.repo}` | {workflow} | `{item.conclusion}` (run #{item.run_number or '?'}) | "
            f"`{item.event}` | `{item.created_at}` | {item.reason} |"
        )
    return "\n".join(lines) + "\n"


def build_report(identity: ReadIdentity, auth_failures: Sequence[str]) -> dict[str, Any]:
    sweeps, reds, errors = sweep_all(identity)
    actionable = [item for item in reds if item.category == "ACTIONABLE"]
    founder = [item for item in reds if item.category == "FOUNDER_GATED"]
    infra = [item for item in reds if item.category == "INFRA"]
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": utc_now(),
        "generation": os.environ.get("GITHUB_SHA"),
        "organization": ORG,
        "status": "VERIFIED" if not errors else "NOT_VERIFIED",
        "authentication": {
            "mode": identity.mode,
            "credential_name": identity.credential_name,
            "authorized_endpoint_completed": True,
            "action_probes": list(identity.action_probes),
            "rejected_candidates": list(auth_failures),
            "value_recorded": False,
            "prefix_recorded": False,
            "length_recorded": False,
            "hash_recorded": False,
        },
        "coverage": {
            "repositories": identity.total_repositories,
            "active": identity.active_repositories,
            "archived": identity.archived_repositories,
            "private": identity.private_repositories,
            "repository_floor": EXPECTED_TOTAL_FLOOR,
            "active_floor": EXPECTED_ACTIVE_FLOOR,
            "private_floor": EXPECTED_PRIVATE_FLOOR,
            "swept_active": len(sweeps),
            "workflow_count": sum(item.workflows for item in sweeps),
        },
        "summary": {
            "red": len(reds),
            "actionable": len(actionable),
            "founder_gated": len(founder),
            "infra": len(infra),
            "query_errors": len(errors),
        },
        "reds": [asdict(item) for item in reds],
        "query_errors": errors,
        "issue": None,
        "boundaries": [
            "The built-in GITHUB_TOKEN is never accepted as the organization read identity.",
            "Issue mutation uses the ephemeral repository GITHUB_TOKEN separately from organization reads.",
            "A partial repository inventory, private-repository omission, Actions authorization failure, query error, or issue-write error is terminal.",
            "No credential value, prefix, length, hash, authorization header, or identity response is recorded.",
            "Historical release, deployment, and founder-controlled failures are labeled but not silently promoted to current actionable work.",
        ],
    }


def render_issue(report: Mapping[str, Any]) -> tuple[str, str, bool]:
    summary = report.get("summary") or {}
    coverage = report.get("coverage") or {}
    authentication = report.get("authentication") or {}
    actionable_count = int(summary.get("actionable", 0))
    red_count = int(summary.get("red", 0))
    query_errors = int(summary.get("query_errors", 0))
    verified = report.get("status") == "VERIFIED"
    should_open = not verified or query_errors > 0 or actionable_count > 0
    icon = "🔴" if should_open else ("🟠" if red_count else "🟢")
    title = f"{icon} CI Health Digest — org-wide"

    reds = [RedRun(**item) for item in report.get("reds", []) if isinstance(item, dict)]
    actionable = [item for item in reds if item.category == "ACTIONABLE"]
    founder = [item for item in reds if item.category == "FOUNDER_GATED"]
    infra = [item for item in reds if item.category == "INFRA"]
    run_url = None
    if all(os.environ.get(key) for key in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")):
        run_url = (
            f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
            f"/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        )

    lines = [
        ISSUE_MARKER,
        "# Organization CI health digest",
        "",
        f"- Verification: **{report.get('status')}**",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Source generation: `{report.get('generation')}`",
        f"- Run: {run_url or 'not available'}",
        f"- Read identity: `{authentication.get('mode')}` / `{authentication.get('credential_name')}`",
        "- Credential value recorded: `false`",
        f"- Repository coverage: **{coverage.get('repositories')} total / {coverage.get('active')} active / {coverage.get('private')} private / {coverage.get('archived')} archived**",
        f"- Active repositories swept: **{coverage.get('swept_active')}**",
        f"- Workflows inspected: **{coverage.get('workflow_count')}**",
        f"- Latest red workflows: **{red_count}** — **{actionable_count} actionable**, {len(founder)} founder-gated, {len(infra)} historical/infra",
        "",
    ]
    if report.get("query_errors"):
        lines.extend(["## Verification errors", ""])
        lines.extend(f"- `{error}`" for error in report["query_errors"])
        lines.append("")
    lines.extend(
        [
            "## Actionable",
            "",
            _table(actionable),
            "## Founder-gated",
            "",
            _table(founder),
            "## Historical / infrastructure",
            "",
            _table(infra),
            "## Contract",
            "",
            "The issue stays open only for incomplete verification or current actionable failures. Historical release/deployment failures remain visible here but do not keep the work queue open. A failed read, incomplete estate, or failed issue update can never look green.",
            "",
        ]
    )
    return title, "\n".join(lines), should_open


def upsert_issue(write_token: str, report: Mapping[str, Any]) -> dict[str, Any]:
    if not write_token:
        raise DigestError("GITHUB_TOKEN is missing for deterministic issue update")
    title, body, should_open = render_issue(report)
    state = "open" if should_open else "closed"
    payload: dict[str, Any] = {"title": title, "body": body, "state": state}
    if state == "closed":
        payload["state_reason"] = "completed"
    try:
        result = api_json(
            write_token,
            f"/repos/{ORG}/.github/issues/{ISSUE_NUMBER}",
            method="PATCH",
            payload=payload,
            expected=(200,),
        )
    except ApiError as exc:
        if exc.status != 404:
            raise
        result = api_json(
            write_token,
            f"/repos/{ORG}/.github/issues",
            method="POST",
            payload={"title": title, "body": body},
            expected=(201,),
        )
    if not isinstance(result, dict) or not isinstance(result.get("number"), int):
        raise DigestError("deterministic issue update returned an unexpected response")
    observed_state = str(result.get("state") or "")
    if observed_state != state:
        raise DigestError(f"digest issue state mismatch: expected {state}, observed {observed_state}")
    return {
        "number": result["number"],
        "title": result.get("title"),
        "state": observed_state,
        "url": result.get("html_url"),
        "write_credential": "GITHUB_TOKEN",
        "value_recorded": False,
    }


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_summary(report: Mapping[str, Any]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    summary = report.get("summary") or {}
    coverage = report.get("coverage") or {}
    authentication = report.get("authentication") or {}
    with open(summary_path, "a", encoding="utf-8") as handle:
        handle.write("## Organization CI health digest\n\n")
        handle.write(f"- status: `{report.get('status')}`\n")
        handle.write(f"- read identity: `{authentication.get('mode')}`\n")
        handle.write(f"- repositories: `{coverage.get('repositories')}`\n")
        handle.write(f"- active swept: `{coverage.get('swept_active')}`\n")
        handle.write(f"- workflows: `{coverage.get('workflow_count')}`\n")
        handle.write(f"- red: `{summary.get('red')}`\n")
        handle.write(f"- actionable: `{summary.get('actionable')}`\n")
        handle.write(f"- query errors: `{summary.get('query_errors')}`\n")
        issue = report.get("issue") or {}
        if issue:
            handle.write(f"- issue: `{issue.get('state')}` #{issue.get('number')}\n")
        handle.write("- credential value recorded: `false`\n")


def failure_report(message: str) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": utc_now(),
        "generation": os.environ.get("GITHUB_SHA"),
        "organization": ORG,
        "status": "NOT_VERIFIED",
        "authentication": {
            "mode": None,
            "credential_name": None,
            "authorized_endpoint_completed": False,
            "value_recorded": False,
            "prefix_recorded": False,
            "length_recorded": False,
            "hash_recorded": False,
        },
        "coverage": {
            "repositories": 0,
            "active": 0,
            "archived": 0,
            "private": 0,
            "repository_floor": EXPECTED_TOTAL_FLOOR,
            "active_floor": EXPECTED_ACTIVE_FLOOR,
            "private_floor": EXPECTED_PRIVATE_FLOOR,
            "swept_active": 0,
            "workflow_count": 0,
        },
        "summary": {
            "red": 0,
            "actionable": 0,
            "founder_gated": 0,
            "infra": 0,
            "query_errors": 1,
        },
        "reds": [],
        "query_errors": [message],
        "issue": None,
        "boundaries": [
            "The digest failed before complete organization verification.",
            "No credential value, prefix, length, or hash is recorded.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="reports/ci-health-digest.json")
    args = parser.parse_args(argv)
    report_path = Path(args.report)
    write_token = os.environ.get("GITHUB_TOKEN", "")

    try:
        identity, auth_failures = select_read_identity()
        print(
            f"authenticated mode={identity.mode} repos={identity.total_repositories} "
            f"active={identity.active_repositories} private={identity.private_repositories}"
        )
        report = build_report(identity, auth_failures)
    except DigestError as exc:
        report = failure_report(str(exc))
        write_report(report_path, report)
        try:
            report["issue"] = upsert_issue(write_token, report)
        except DigestError as issue_exc:
            report["issue"] = {"error": str(issue_exc), "value_recorded": False}
        write_report(report_path, report)
        write_summary(report)
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    write_report(report_path, report)
    try:
        report["issue"] = upsert_issue(write_token, report)
    except DigestError as exc:
        report["status"] = "NOT_VERIFIED"
        report["summary"]["query_errors"] = int(report["summary"].get("query_errors", 0)) + 1
        report["query_errors"].append(str(exc))
        report["issue"] = {"error": str(exc), "value_recorded": False}
        write_report(report_path, report)
        write_summary(report)
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    write_report(report_path, report)
    write_summary(report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "mode": report["authentication"]["mode"],
                "repositories": report["coverage"]["repositories"],
                "active": report["coverage"]["active"],
                "private": report["coverage"]["private"],
                "workflows": report["coverage"]["workflow_count"],
                "red": report["summary"]["red"],
                "actionable": report["summary"]["actionable"],
                "query_errors": report["summary"]["query_errors"],
                "issue_state": report["issue"]["state"],
                "value_recorded": False,
            },
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "VERIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
