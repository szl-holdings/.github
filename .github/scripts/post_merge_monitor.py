#!/usr/bin/env python3
"""Read-only monitor for the protected-main post-merge workflow chain."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "szl.post-merge-monitor/v1"
EXPECTED_MAIN = "527fd000c5189f7b1ca4e56b7993d1daa952308a"
TARGET_ISSUES = (176, 257, 298, 301, 321)
TARGET_PULLS = (322, 323)


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


def compact_run(item: dict[str, Any]) -> dict[str, Any]:
    actor = item.get("actor") or {}
    triggering = item.get("triggering_actor") or {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "event": item.get("event"),
        "status": item.get("status"),
        "conclusion": item.get("conclusion"),
        "run_attempt": item.get("run_attempt"),
        "head_branch": item.get("head_branch"),
        "head_sha": item.get("head_sha"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "html_url": item.get("html_url"),
        "actor": actor.get("login"),
        "triggering_actor": triggering.get("login"),
    }


def main() -> int:
    repository = os.environ["GITHUB_REPOSITORY"]
    ref_result = rest(f"repos/{repository}/git/ref/heads/main")
    ref_payload = ref_result.get("payload") if ref_result.get("ok") else {}
    main_sha = str(((ref_payload or {}).get("object") or {}).get("sha") or "")

    runs_result = rest(
        f"repos/{repository}/actions/runs?head_sha={main_sha or EXPECTED_MAIN}&per_page=100"
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

    pulls: dict[str, Any] = {}
    for number in TARGET_PULLS:
        result = rest(f"repos/{repository}/pulls/{number}")
        payload = result.get("payload") if result.get("ok") else None
        pulls[str(number)] = {
            "read_ok": result.get("ok"),
            "state": payload.get("state") if isinstance(payload, dict) else None,
            "merged": payload.get("merged") if isinstance(payload, dict) else None,
            "merge_commit_sha": (
                payload.get("merge_commit_sha") if isinstance(payload, dict) else None
            ),
            "head_sha": (
                ((payload.get("head") or {}).get("sha"))
                if isinstance(payload, dict)
                else None
            ),
            "base_sha": (
                ((payload.get("base") or {}).get("sha"))
                if isinstance(payload, dict)
                else None
            ),
        }

    issues: dict[str, Any] = {}
    for number in TARGET_ISSUES:
        result = rest(f"repos/{repository}/issues/{number}")
        payload = result.get("payload") if result.get("ok") else None
        issues[str(number)] = {
            "read_ok": result.get("ok"),
            "title": payload.get("title") if isinstance(payload, dict) else None,
            "state": payload.get("state") if isinstance(payload, dict) else None,
            "state_reason": (
                payload.get("state_reason") if isinstance(payload, dict) else None
            ),
            "updated_at": (
                payload.get("updated_at") if isinstance(payload, dict) else None
            ),
            "closed_at": (
                payload.get("closed_at") if isinstance(payload, dict) else None
            ),
        }

    report = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation": os.environ.get("GITHUB_SHA"),
        "repository": repository,
        "main": {
            "read_ok": ref_result.get("ok"),
            "revision": main_sha,
            "expected_revision": EXPECTED_MAIN,
            "matches_expected": main_sha == EXPECTED_MAIN,
        },
        "workflow_runs": compact_runs,
        "pull_requests": pulls,
        "issues": issues,
    }
    summary = {
        "schema": SCHEMA,
        "main": report["main"],
        "workflows": [
            {
                "id": item["id"],
                "name": item["name"],
                "event": item["event"],
                "status": item["status"],
                "conclusion": item["conclusion"],
            }
            for item in compact_runs
        ],
        "pull_requests": pulls,
        "issues": issues,
    }
    path = Path(
        os.environ.get("REPORT_PATH", "reports/post-merge-monitor.json")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("POST_MERGE_MONITOR_SUMMARY")
    print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
