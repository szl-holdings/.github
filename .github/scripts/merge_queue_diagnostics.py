#!/usr/bin/env python3
"""Capture read-only merge-queue state for the blocked protected PRs."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_SCHEMA = "szl.merge-queue-diagnostics/v1"


def invoke(arguments: list[str]) -> dict[str, Any]:
    process = subprocess.run(
        ["gh", "api", *arguments],
        check=False,
        capture_output=True,
        text=True,
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


def main() -> int:
    repository = os.environ["GITHUB_REPOSITORY"]
    owner, name = repository.split("/", 1)
    targets = [
        int(value)
        for value in os.environ.get("TARGET_PULL_REQUESTS", "322,323").split(",")
        if value.strip()
    ]

    graphql_query = """
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        pullRequest(number: $number) {
          id
          number
          url
          state
          isDraft
          headRefOid
          baseRefName
          mergeable
          mergeStateStatus
          reviewDecision
          autoMergeRequest {
            enabledAt
            mergeMethod
            enabledBy { login }
          }
          mergeQueueEntry {
            position
            state
          }
        }
      }
    }
    """
    introspection_query = """
    query {
      pullRequestType: __type(name: "PullRequest") { fields { name } }
      mergeQueueEntryType: __type(name: "MergeQueueEntry") { fields { name } }
    }
    """

    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation": os.environ.get("GITHUB_SHA"),
        "repository": repository,
        "workflow": {
            "event": os.environ.get("GITHUB_EVENT_NAME"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_url": (
                f"{os.environ.get('GITHUB_SERVER_URL')}/{repository}/actions/runs/"
                f"{os.environ.get('GITHUB_RUN_ID')}"
            ),
        },
        "targets": {},
        "control_plane": {},
    }

    control = report["control_plane"]
    control["graphql_schema"] = invoke(
        ["graphql", "-f", f"query={introspection_query}"]
    )
    control["active_rules_main"] = rest(f"repos/{repository}/rules/branches/main")
    control["main_protection"] = rest(
        f"repos/{repository}/branches/main/protection"
    )
    control["recent_rule_suites"] = rest(
        f"repos/{repository}/rulesets/rule-suites?ref=refs/heads/main&per_page=20"
    )

    branch_response = rest(f"repos/{repository}/branches?per_page=100")
    if branch_response["ok"] and isinstance(branch_response["payload"], list):
        branch_response["payload"] = [
            {
                "name": item.get("name"),
                "sha": (item.get("commit") or {}).get("sha"),
                "protected": item.get("protected"),
            }
            for item in branch_response["payload"]
            if str(item.get("name") or "").startswith("gh-readonly-queue/")
        ]
    control["queue_branches"] = branch_response

    merge_group_runs = rest(
        f"repos/{repository}/actions/runs?event=merge_group&per_page=100"
    )
    if merge_group_runs["ok"] and isinstance(merge_group_runs["payload"], dict):
        merge_group_runs["payload"] = [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "event": item.get("event"),
                "status": item.get("status"),
                "conclusion": item.get("conclusion"),
                "head_branch": item.get("head_branch"),
                "head_sha": item.get("head_sha"),
                "created_at": item.get("created_at"),
                "html_url": item.get("html_url"),
            }
            for item in merge_group_runs["payload"].get("workflow_runs", [])
        ]
    control["merge_group_runs"] = merge_group_runs

    for number in targets:
        pr_rest = rest(f"repos/{repository}/pulls/{number}")
        target: dict[str, Any] = {"rest": pr_rest}
        head_sha = None
        if pr_rest["ok"] and isinstance(pr_rest["payload"], dict):
            payload = pr_rest["payload"]
            head_sha = (payload.get("head") or {}).get("sha")
            pr_rest["payload"] = {
                "number": payload.get("number"),
                "state": payload.get("state"),
                "draft": payload.get("draft"),
                "mergeable": payload.get("mergeable"),
                "mergeable_state": payload.get("mergeable_state"),
                "rebaseable": payload.get("rebaseable"),
                "auto_merge": payload.get("auto_merge"),
                "head": payload.get("head"),
                "base": payload.get("base"),
                "updated_at": payload.get("updated_at"),
            }

        target["graphql"] = invoke(
            [
                "graphql",
                "-f",
                f"query={graphql_query}",
                "-F",
                f"owner={owner}",
                "-F",
                f"name={name}",
                "-F",
                f"number={number}",
            ]
        )
        if head_sha:
            check_suites = rest(
                f"repos/{repository}/commits/{head_sha}/check-suites?per_page=100"
            )
            if check_suites["ok"] and isinstance(check_suites["payload"], dict):
                check_suites["payload"] = [
                    {
                        "id": item.get("id"),
                        "status": item.get("status"),
                        "conclusion": item.get("conclusion"),
                        "head_branch": item.get("head_branch"),
                        "head_sha": item.get("head_sha"),
                        "app": (item.get("app") or {}).get("slug"),
                        "latest_check_runs_count": item.get(
                            "latest_check_runs_count"
                        ),
                        "url": item.get("url"),
                    }
                    for item in check_suites["payload"].get("check_suites", [])
                ]
            target["check_suites"] = check_suites
            target["combined_status"] = rest(
                f"repos/{repository}/commits/{head_sha}/status"
            )
        report["targets"][str(number)] = target

    summary: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "generation": report["generation"],
        "active_rules_main_ok": control["active_rules_main"]["ok"],
        "main_protection_ok": control["main_protection"]["ok"],
        "recent_rule_suites_ok": control["recent_rule_suites"]["ok"],
        "queue_branches": control["queue_branches"].get("payload"),
        "merge_group_runs": control["merge_group_runs"].get("payload"),
        "targets": {},
    }
    for number, target in report["targets"].items():
        rest_payload = target["rest"].get("payload")
        graph_payload = target["graphql"].get("payload")
        pull_request = None
        if isinstance(graph_payload, dict):
            pull_request = (
                (graph_payload.get("data") or {})
                .get("repository", {})
                .get("pullRequest")
            )
        suites = target.get("check_suites", {}).get("payload")
        summary["targets"][number] = {
            "rest_ok": target["rest"]["ok"],
            "rest_state": (
                {
                    "mergeable": rest_payload.get("mergeable"),
                    "mergeable_state": rest_payload.get("mergeable_state"),
                    "auto_merge": rest_payload.get("auto_merge"),
                    "head_sha": (rest_payload.get("head") or {}).get("sha"),
                }
                if isinstance(rest_payload, dict)
                else rest_payload
            ),
            "graphql_ok": target["graphql"]["ok"],
            "graphql_error": target["graphql"].get("stderr"),
            "graphql_state": pull_request,
            "check_suite_count": len(suites) if isinstance(suites, list) else None,
        }

    path = Path(os.environ.get("REPORT_PATH", "reports/merge-queue-state.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("MERGE_QUEUE_DIAGNOSTIC_SUMMARY")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
