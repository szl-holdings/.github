#!/usr/bin/env python3
"""Trace non-terminal check runs blocking otherwise-green signed PR heads."""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "szl.stale-check-diagnostics/v1"
TARGETS = {
    "322": "52ab3fc1a17b5366010dd1bcfe8f6dcb5db4a286",
    "323": "fb8a1c2435db5bff99be51faefc9781309d0f9a4",
}
TERMINAL = {"completed"}


def invoke(arguments: list[str]) -> dict[str, Any]:
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
    return {
        "ok": process.returncode == 0,
        "returncode": process.returncode,
        "payload": payload,
        "stderr": process.stderr.strip()[:2000],
    }


def rest(path: str) -> dict[str, Any]:
    return invoke(["--method", "GET", path])


def compact_check(item: dict[str, Any]) -> dict[str, Any]:
    output = item.get("output") or {}
    app = item.get("app") or {}
    return {
        "id": item.get("id"),
        "node_id": item.get("node_id"),
        "name": item.get("name"),
        "status": item.get("status"),
        "conclusion": item.get("conclusion"),
        "details_url": item.get("details_url"),
        "external_id": item.get("external_id"),
        "started_at": item.get("started_at"),
        "completed_at": item.get("completed_at"),
        "head_sha": item.get("head_sha"),
        "app": {
            "id": app.get("id"),
            "slug": app.get("slug"),
            "name": app.get("name"),
        },
        "output": {
            "title": output.get("title"),
            "summary": str(output.get("summary") or "")[:2000],
            "text": str(output.get("text") or "")[:2000],
            "annotations_count": output.get("annotations_count"),
        },
    }


def compact_run(item: dict[str, Any]) -> dict[str, Any]:
    actor = item.get("actor") or {}
    triggering_actor = item.get("triggering_actor") or {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "event": item.get("event"),
        "status": item.get("status"),
        "conclusion": item.get("conclusion"),
        "run_attempt": item.get("run_attempt"),
        "head_sha": item.get("head_sha"),
        "head_branch": item.get("head_branch"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "html_url": item.get("html_url"),
        "jobs_url": item.get("jobs_url"),
        "actor": actor.get("login"),
        "triggering_actor": triggering_actor.get("login"),
    }


def main() -> int:
    repository = os.environ["GITHUB_REPOSITORY"]
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation": os.environ.get("GITHUB_SHA"),
        "repository": repository,
        "targets": {},
    }

    for number, head_sha in TARGETS.items():
        check_result = rest(
            f"repos/{repository}/commits/{head_sha}/check-runs?filter=latest&per_page=100"
        )
        check_payload = check_result.get("payload") if check_result.get("ok") else {}
        checks = (
            check_payload.get("check_runs", [])
            if isinstance(check_payload, dict)
            else []
        )
        compact_checks = [
            compact_check(item) for item in checks if isinstance(item, dict)
        ]
        non_terminal = [
            item
            for item in compact_checks
            if str(item.get("status") or "") not in TERMINAL
        ]

        runs_result = rest(
            f"repos/{repository}/actions/runs?head_sha={head_sha}&per_page=100"
        )
        runs_payload = runs_result.get("payload") if runs_result.get("ok") else {}
        runs = (
            runs_payload.get("workflow_runs", [])
            if isinstance(runs_payload, dict)
            else []
        )
        compact_runs = [
            compact_run(item) for item in runs if isinstance(item, dict)
        ]

        linked: list[dict[str, Any]] = []
        for check in non_terminal:
            details_url = str(check.get("details_url") or "")
            match = re.search(r"/actions/runs/(\d+)(?:/job/(\d+))?", details_url)
            entry: dict[str, Any] = {
                "check_run": check,
                "details_match": bool(match),
            }
            if match:
                run_id = int(match.group(1))
                job_id = int(match.group(2)) if match.group(2) else None
                entry["workflow_run"] = rest(
                    f"repos/{repository}/actions/runs/{run_id}"
                )
                if job_id is not None:
                    entry["workflow_job"] = rest(
                        f"repos/{repository}/actions/jobs/{job_id}"
                    )
            check_id = int(check.get("id") or 0)
            if check_id:
                entry["check_run_readback"] = rest(
                    f"repos/{repository}/check-runs/{check_id}"
                )
            linked.append(entry)

        report["targets"][number] = {
            "head_sha": head_sha,
            "check_read_ok": check_result.get("ok"),
            "checks": compact_checks,
            "non_terminal_checks": non_terminal,
            "actions_read_ok": runs_result.get("ok"),
            "workflow_runs": compact_runs,
            "linked_non_terminal": linked,
        }

    summary = {
        "schema": SCHEMA,
        "targets": {
            number: {
                "head_sha": target["head_sha"],
                "non_terminal_checks": target["non_terminal_checks"],
                "workflow_runs": target["workflow_runs"],
            }
            for number, target in report["targets"].items()
        },
    }
    path = Path(
        os.environ.get("STALE_REPORT_PATH", "reports/stale-check-diagnostics.json")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("STALE_CHECK_DIAGNOSTIC_SUMMARY")
    print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
