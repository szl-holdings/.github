#!/usr/bin/env python3
"""Cancel and rerun only two exact stale GitHub Code Quality workflow runs.

Both target PRs have all repository-owned required checks green, valid GitHub-
signed commit histories, and no unresolved review threads. GitHub's dynamic Code
Quality workflow remains in ``Perform CodeQL Analysis`` with no update. This
controller leaves every protection and check requirement intact; it only uses
the supported Actions cancel/rerun lifecycle for the two immutable run IDs.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_SCHEMA = "szl.stale-code-quality-recovery/v1"
MIN_STALE_SECONDS = 300
EXPECTED_WORKFLOW_ID = 285762202


@dataclass(frozen=True)
class Target:
    pull_request: int
    head_sha: str
    run_id: int
    job_id: int
    expected_name: str


TARGETS = (
    Target(
        pull_request=322,
        head_sha="52ab3fc1a17b5366010dd1bcfe8f6dcb5db4a286",
        run_id=30215896212,
        job_id=89829927288,
        expected_name="Code Quality: PR #322",
    ),
    Target(
        pull_request=323,
        head_sha="fb8a1c2435db5bff99be51faefc9781309d0f9a4",
        run_id=30215898894,
        job_id=89829933795,
        expected_name="Code Quality: PR #323",
    ),
)


class RecoveryError(RuntimeError):
    """Raised when a target leaves the exact recovery envelope."""


def _invoke(
    arguments: list[str],
    *,
    allow_failure: bool = False,
) -> tuple[int, Any, str]:
    process = subprocess.run(
        ["gh", "api", *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=os.environ,
    )
    stdout = process.stdout.strip()
    try:
        payload: Any = json.loads(stdout) if stdout else None
    except json.JSONDecodeError:
        payload = stdout[:4000]
    stderr = process.stderr.strip()[:2000]
    if process.returncode and not allow_failure:
        raise RecoveryError(
            f"GitHub API failed ({process.returncode}): {stderr or payload}"
        )
    return process.returncode, payload, stderr


def _get(repository: str, path: str) -> dict[str, Any]:
    _, payload, _ = _invoke(["--method", "GET", f"repos/{repository}/{path}"])
    if not isinstance(payload, dict):
        raise RecoveryError(f"GET {path} did not return an object")
    return payload


def _post(repository: str, path: str, *, allow_failure: bool = False) -> int:
    code, _, _ = _invoke(
        ["--method", "POST", f"repos/{repository}/{path}"],
        allow_failure=allow_failure,
    )
    return code


def _parse_time(value: object) -> datetime:
    text = str(value or "")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise RecoveryError(f"invalid GitHub timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_run(run: dict[str, Any], target: Target) -> None:
    if int(run.get("id") or 0) != target.run_id:
        raise RecoveryError(f"run ID mismatch for PR #{target.pull_request}")
    if int(run.get("workflow_id") or 0) != EXPECTED_WORKFLOW_ID:
        raise RecoveryError(
            f"run {target.run_id} workflow ID changed: {run.get('workflow_id')}"
        )
    if str(run.get("name") or "") != target.expected_name:
        raise RecoveryError(
            f"run {target.run_id} name changed: {run.get('name')!r}"
        )
    if str(run.get("event") or "") != "dynamic":
        raise RecoveryError(
            f"run {target.run_id} event changed: {run.get('event')!r}"
        )
    if str(run.get("head_sha") or "").lower() != target.head_sha:
        raise RecoveryError(
            f"run {target.run_id} head changed: {run.get('head_sha')!r}"
        )


def _validate_job(job: dict[str, Any], target: Target) -> None:
    if int(job.get("id") or 0) != target.job_id:
        raise RecoveryError(f"job ID mismatch for PR #{target.pull_request}")
    if int(job.get("run_id") or 0) != target.run_id:
        raise RecoveryError(f"job {target.job_id} run binding changed")
    if str(job.get("name") or "") != "Analyze (javascript-typescript)":
        raise RecoveryError(
            f"job {target.job_id} name changed: {job.get('name')!r}"
        )
    steps = job.get("steps") or []
    active = [
        step
        for step in steps
        if isinstance(step, dict)
        and step.get("name") == "Perform CodeQL Analysis"
        and step.get("status") == "in_progress"
    ]
    if job.get("status") == "in_progress" and len(active) != 1:
        raise RecoveryError(
            f"job {target.job_id} is not uniquely stuck in Perform CodeQL Analysis"
        )


def _wait_for_completion(repository: str, target: Target) -> dict[str, Any]:
    run: dict[str, Any] = {}
    for _ in range(30):
        run = _get(repository, f"actions/runs/{target.run_id}")
        _validate_run(run, target)
        if run.get("status") == "completed":
            return run
        time.sleep(2)
    return run


def _wait_for_rerun_start(
    repository: str,
    target: Target,
    prior_attempt: int,
) -> dict[str, Any]:
    run: dict[str, Any] = {}
    for _ in range(30):
        run = _get(repository, f"actions/runs/{target.run_id}")
        _validate_run(run, target)
        attempt = int(run.get("run_attempt") or 0)
        if attempt > prior_attempt and run.get("status") in {
            "queued",
            "in_progress",
            "completed",
        }:
            return run
        time.sleep(2)
    return run


def _recover(repository: str, target: Target) -> dict[str, Any]:
    run = _get(repository, f"actions/runs/{target.run_id}")
    job = _get(repository, f"actions/jobs/{target.job_id}")
    _validate_run(run, target)
    _validate_job(job, target)

    before = {
        "run_status": run.get("status"),
        "run_conclusion": run.get("conclusion"),
        "run_attempt": run.get("run_attempt"),
        "run_updated_at": run.get("updated_at"),
        "job_status": job.get("status"),
        "job_conclusion": job.get("conclusion"),
        "job_started_at": job.get("started_at"),
    }
    attempt = int(run.get("run_attempt") or 1)

    if run.get("status") == "completed" and run.get("conclusion") == "success":
        return {
            "pull_request": target.pull_request,
            "head_sha": target.head_sha,
            "run_id": target.run_id,
            "job_id": target.job_id,
            "action": "already_successful",
            "before": before,
            "after": before,
        }

    if attempt > 1 and run.get("status") in {"queued", "in_progress"}:
        return {
            "pull_request": target.pull_request,
            "head_sha": target.head_sha,
            "run_id": target.run_id,
            "job_id": target.job_id,
            "action": "rerun_already_active",
            "before": before,
            "after": before,
        }

    if run.get("status") == "in_progress":
        age = (
            datetime.now(timezone.utc) - _parse_time(run.get("updated_at"))
        ).total_seconds()
        if age < MIN_STALE_SECONDS:
            raise RecoveryError(
                f"run {target.run_id} is only {age:.0f}s stale; refusing cancellation"
            )

        cancel_code = _post(
            repository,
            f"actions/runs/{target.run_id}/cancel",
            allow_failure=True,
        )
        if cancel_code:
            refreshed = _get(repository, f"actions/runs/{target.run_id}")
            _validate_run(refreshed, target)
            if refreshed.get("status") != "completed":
                raise RecoveryError(
                    f"supported cancellation failed for run {target.run_id}"
                )
        completed = _wait_for_completion(repository, target)
        if completed.get("status") != "completed":
            force_code = _post(
                repository,
                f"actions/runs/{target.run_id}/force-cancel",
                allow_failure=True,
            )
            if force_code:
                raise RecoveryError(
                    f"run {target.run_id} did not cancel and force-cancel failed"
                )
            completed = _wait_for_completion(repository, target)
        if completed.get("status") != "completed":
            raise RecoveryError(f"run {target.run_id} did not reach completed")
        run = completed

    if run.get("status") != "completed":
        raise RecoveryError(
            f"run {target.run_id} has unsupported state {run.get('status')!r}"
        )
    if int(run.get("run_attempt") or 1) != attempt:
        attempt = int(run.get("run_attempt") or attempt)
    if attempt > 1 and run.get("conclusion") not in {"cancelled", "failure"}:
        raise RecoveryError(
            f"run {target.run_id} already reran with terminal conclusion "
            f"{run.get('conclusion')!r}"
        )

    rerun_code = _post(
        repository,
        f"actions/runs/{target.run_id}/rerun",
        allow_failure=True,
    )
    if rerun_code:
        refreshed = _get(repository, f"actions/runs/{target.run_id}")
        _validate_run(refreshed, target)
        if int(refreshed.get("run_attempt") or 0) <= attempt:
            raise RecoveryError(f"rerun request failed for run {target.run_id}")

    after = _wait_for_rerun_start(repository, target, attempt)
    if int(after.get("run_attempt") or 0) <= attempt:
        raise RecoveryError(f"rerun did not start for run {target.run_id}")
    return {
        "pull_request": target.pull_request,
        "head_sha": target.head_sha,
        "run_id": target.run_id,
        "job_id": target.job_id,
        "action": "cancelled_and_rerun",
        "before": before,
        "after": {
            "run_status": after.get("status"),
            "run_conclusion": after.get("conclusion"),
            "run_attempt": after.get("run_attempt"),
            "run_updated_at": after.get("updated_at"),
        },
    }


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY")
    if repository != "szl-holdings/.github":
        raise RecoveryError(
            f"recovery is locked to szl-holdings/.github, observed {repository!r}"
        )
    if not os.environ.get("GH_TOKEN"):
        raise RecoveryError("GH_TOKEN is required")

    report_path = Path(
        os.environ.get(
            "REPORT_PATH",
            "reports/stale-code-quality-recovery.json",
        )
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    error: str | None = None
    try:
        for target in TARGETS:
            records.append(_recover(repository, target))
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        print(error, file=sys.stderr)
    finally:
        report = {
            "schema": REPORT_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generation": os.environ.get("GITHUB_SHA"),
            "repository": repository,
            "status": "RECOVERED" if error is None else "FAILED_CLOSED",
            "error": error,
            "targets": records,
            "boundaries": [
                "Only two immutable GitHub-managed dynamic Code Quality run IDs are eligible.",
                "Each run, workflow ID, event, name, head SHA, job ID, and active step is revalidated before cancellation.",
                "No check conclusion, status, ruleset, branch protection, review, or secret is created or altered directly.",
                "The supported Actions cancel and rerun lifecycle is used; the rerun must produce its own analysis result.",
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
    except RecoveryError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1)
