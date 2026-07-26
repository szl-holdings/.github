#!/usr/bin/env python3
"""Approve only exact PR workflow runs created by signed-history recovery.

GitHub marks workflow runs triggered by the GitHub-created replacement commit as
``action_required``. This controller approves those runs without changing,
forging, or waiving any check result. Every run must be a pull-request run at the
declared immutable signed head and use an explicitly allowed workflow name.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_SCHEMA = "szl.signed-recovery-run-approval/v1"
TARGETS = {
    "93a5138742497345cca21b8bd1a385d3b499c579": 325,
}
ALLOWED_WORKFLOWS = {
    "ci",
    "FORGE-9 staging",
    "CodeQL",
    "FORGE-9 gates",
    "Tests",
    "DCO",
    "Pin Check",
    "trivy",
    "gitleaks",
    "SZL Doctrine Check",
    "Final Estate Reconciliation v5 — Pull Request Verification",
    "HF Release Readiness Terminal — Pull Request Verification",
    "HF Release Finalization — Pull Request Verification",
    "FORGE-9 bootstrap invariants",
}


class ApprovalError(RuntimeError):
    """Raised when a run is outside the declared approval envelope."""


def _gh(arguments: list[str]) -> Any:
    process = subprocess.run(
        ["gh", "api", *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=os.environ,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip()
        raise ApprovalError(
            f"GitHub API failed ({process.returncode}): {detail[:2000]}"
        )
    output = process.stdout.strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise ApprovalError(f"GitHub API returned non-JSON: {output[:1000]}") from exc


def _get_run(repository: str, run_id: int) -> dict[str, Any]:
    value = _gh(["--method", "GET", f"repos/{repository}/actions/runs/{run_id}"])
    if not isinstance(value, dict):
        raise ApprovalError(f"workflow run {run_id} did not return an object")
    return value


def _list_runs(repository: str, head_sha: str) -> list[dict[str, Any]]:
    response = _gh(
        [
            "--method",
            "GET",
            f"repos/{repository}/actions/runs?event=pull_request&head_sha={head_sha}&per_page=100",
        ]
    )
    runs = (response or {}).get("workflow_runs") if isinstance(response, dict) else None
    if not isinstance(runs, list) or not runs:
        raise ApprovalError(f"no pull-request workflow runs found for {head_sha}")
    return [item for item in runs if isinstance(item, dict)]


def _validate_run(run: dict[str, Any], head_sha: str, pr_number: int) -> None:
    run_id = int(run.get("id") or 0)
    name = str(run.get("name") or "")
    observed_sha = str(run.get("head_sha") or "").lower()
    event = str(run.get("event") or "")
    pulls = run.get("pull_requests") or []
    pull_numbers = {
        int(item.get("number") or 0)
        for item in pulls
        if isinstance(item, dict)
    }
    if run_id <= 0:
        raise ApprovalError("workflow run lacks an ID")
    if observed_sha != head_sha:
        raise ApprovalError(
            f"run {run_id} head mismatch: expected {head_sha}, observed {observed_sha}"
        )
    if event != "pull_request":
        raise ApprovalError(f"run {run_id} has unexpected event {event!r}")
    if name not in ALLOWED_WORKFLOWS:
        raise ApprovalError(f"run {run_id} has unapproved workflow name {name!r}")
    if pull_numbers and pr_number not in pull_numbers:
        raise ApprovalError(
            f"run {run_id} is not bound to expected PR #{pr_number}: {pull_numbers}"
        )


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY")
    if repository != "szl-holdings/.github":
        raise ApprovalError(
            f"approval controller is locked to szl-holdings/.github, got {repository!r}"
        )
    if not os.environ.get("GH_TOKEN"):
        raise ApprovalError("GH_TOKEN is required")

    report_path = Path(
        os.environ.get(
            "REPORT_PATH",
            "reports/signed-recovery-run-approval.json",
        )
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    error: str | None = None

    try:
        candidates: list[tuple[dict[str, Any], str, int]] = []
        for head_sha, pr_number in TARGETS.items():
            runs = _list_runs(repository, head_sha)
            for run in runs:
                _validate_run(run, head_sha, pr_number)
                candidates.append((run, head_sha, pr_number))

        actionable = [
            item
            for item in candidates
            if str(item[0].get("conclusion") or "") == "action_required"
        ]
        if not actionable:
            raise ApprovalError("no action_required runs remain in the exact envelope")

        for run, head_sha, pr_number in actionable:
            run_id = int(run["id"])
            name = str(run["name"])
            _gh(
                [
                    "--method",
                    "POST",
                    f"repos/{repository}/actions/runs/{run_id}/approve",
                ]
            )
            records.append(
                {
                    "run_id": run_id,
                    "workflow": name,
                    "head_sha": head_sha,
                    "pull_request": pr_number,
                    "before": {
                        "status": run.get("status"),
                        "conclusion": run.get("conclusion"),
                    },
                    "approved": True,
                }
            )

        # Require GitHub to acknowledge every approval by leaving the
        # action_required state. Actual conclusions still come only from each
        # workflow and are never altered here.
        remaining = {record["run_id"] for record in records}
        for _ in range(20):
            complete: set[int] = set()
            for record in records:
                observed = _get_run(repository, int(record["run_id"]))
                record["after"] = {
                    "status": observed.get("status"),
                    "conclusion": observed.get("conclusion"),
                }
                if str(observed.get("conclusion") or "") != "action_required":
                    complete.add(int(record["run_id"]))
            remaining.difference_update(complete)
            if not remaining:
                break
            time.sleep(2)
        if remaining:
            raise ApprovalError(
                f"workflow runs remained action_required after approval: {sorted(remaining)}"
            )
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        print(error, file=sys.stderr)
    finally:
        report = {
            "schema": REPORT_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generation": os.environ.get("GITHUB_SHA"),
            "repository": repository,
            "status": "APPROVED" if error is None else "FAILED_CLOSED",
            "error": error,
            "runs": records,
            "boundaries": [
                "Only pull_request runs at the declared GitHub-signed head are eligible.",
                "Only explicitly allowed workflow names are eligible.",
                "This controller approves execution; it does not create, alter, or waive any check conclusion.",
                "No secret value is recorded.",
            ],
        }
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, sort_keys=True))

    return 0 if error is None else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ApprovalError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1)
