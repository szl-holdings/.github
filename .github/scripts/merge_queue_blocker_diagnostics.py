#!/usr/bin/env python3
"""Explain why protected PRs are blocked before a merge-queue entry exists."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "szl.merge-queue-blocker-diagnostics/v1"
SUCCESS_CONCLUSIONS = {"success", "neutral", "skipped"}


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


def graphql(owner: str, name: str, number: int) -> dict[str, Any]:
    query = """
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        pullRequest(number: $number) {
          number
          url
          state
          isDraft
          headRefOid
          baseRefOid
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
          reviewThreads(first: 100) {
            totalCount
            nodes { isResolved }
          }
        }
      }
    }
    """
    return invoke(
        [
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"number={number}",
        ]
    )


def payload(result: dict[str, Any], default: Any) -> Any:
    value = result.get("payload")
    return value if result.get("ok") else default


def required_checks_from_rules(rules: Any) -> list[dict[str, Any]]:
    if not isinstance(rules, list):
        return []
    for rule in rules:
        if isinstance(rule, dict) and rule.get("type") == "required_status_checks":
            parameters = rule.get("parameters") or {}
            checks = parameters.get("required_status_checks") or []
            return [item for item in checks if isinstance(item, dict)]
    return []


def rule_parameters(rules: Any, kind: str) -> Any:
    if not isinstance(rules, list):
        return None
    for rule in rules:
        if isinstance(rule, dict) and rule.get("type") == kind:
            return rule.get("parameters")
    return None


def compact_pr_graph(result: dict[str, Any]) -> Any:
    graph_payload = payload(result, {})
    if not isinstance(graph_payload, dict):
        return None
    return (
        (graph_payload.get("data") or {})
        .get("repository", {})
        .get("pullRequest")
    )


def main() -> int:
    repository = os.environ["GITHUB_REPOSITORY"]
    owner, name = repository.split("/", 1)
    targets = [
        int(value)
        for value in os.environ.get("TARGET_PULL_REQUESTS", "322,323").split(",")
        if value.strip()
    ]

    rules_result = rest(f"repos/{repository}/rules/branches/main")
    rules = payload(rules_result, [])
    required_checks = required_checks_from_rules(rules)
    rule_types = [
        item.get("type")
        for item in rules
        if isinstance(item, dict) and item.get("type")
    ]

    branches_result = rest(f"repos/{repository}/branches?per_page=100")
    branches = payload(branches_result, [])
    queue_branches = [
        {
            "name": item.get("name"),
            "sha": (item.get("commit") or {}).get("sha"),
        }
        for item in branches
        if isinstance(item, dict)
        and str(item.get("name") or "").startswith("gh-readonly-queue/")
    ]

    runs_result = rest(
        f"repos/{repository}/actions/runs?event=merge_group&per_page=100"
    )
    run_payload = payload(runs_result, {})
    runs = (
        run_payload.get("workflow_runs", [])
        if isinstance(run_payload, dict)
        else []
    )
    merge_group_runs = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "status": item.get("status"),
            "conclusion": item.get("conclusion"),
            "head_branch": item.get("head_branch"),
            "head_sha": item.get("head_sha"),
            "created_at": item.get("created_at"),
        }
        for item in runs[:20]
        if isinstance(item, dict)
    ]

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation": os.environ.get("GITHUB_SHA"),
        "repository": repository,
        "rules": {
            "read_ok": rules_result["ok"],
            "types": rule_types,
            "required_status_checks": required_checks,
            "pull_request": rule_parameters(rules, "pull_request"),
            "merge_queue": rule_parameters(rules, "merge_queue"),
            "required_signatures": "required_signatures" in rule_types,
            "required_linear_history": "required_linear_history" in rule_types,
        },
        "queue_branches": queue_branches,
        "merge_group_runs": merge_group_runs,
        "targets": {},
    }

    for number in targets:
        pr_result = rest(f"repos/{repository}/pulls/{number}")
        pr = payload(pr_result, {})
        head_sha = (
            (pr.get("head") or {}).get("sha") if isinstance(pr, dict) else None
        )
        graph_result = graphql(owner, name, number)
        graph = compact_pr_graph(graph_result)

        checks_result = (
            rest(f"repos/{repository}/commits/{head_sha}/check-runs?per_page=100")
            if head_sha
            else {"ok": False, "payload": None, "stderr": "missing head SHA"}
        )
        checks_payload = payload(checks_result, {})
        check_runs = (
            checks_payload.get("check_runs", [])
            if isinstance(checks_payload, dict)
            else []
        )
        compact_checks = [
            {
                "name": item.get("name"),
                "status": item.get("status"),
                "conclusion": item.get("conclusion"),
                "app_id": (item.get("app") or {}).get("id"),
                "app_slug": (item.get("app") or {}).get("slug"),
            }
            for item in check_runs
            if isinstance(item, dict)
        ]

        statuses_result = (
            rest(f"repos/{repository}/commits/{head_sha}/status")
            if head_sha
            else {"ok": False, "payload": None, "stderr": "missing head SHA"}
        )
        statuses_payload = payload(statuses_result, {})
        compact_statuses = [
            {
                "context": item.get("context"),
                "state": item.get("state"),
                "creator": (item.get("creator") or {}).get("login"),
            }
            for item in (
                statuses_payload.get("statuses", [])
                if isinstance(statuses_payload, dict)
                else []
            )
            if isinstance(item, dict)
        ]

        commits_result = rest(
            f"repos/{repository}/pulls/{number}/commits?per_page=100"
        )
        commits = payload(commits_result, [])
        signatures = [
            {
                "sha": item.get("sha"),
                "verified": ((item.get("commit") or {}).get("verification") or {}).get(
                    "verified"
                ),
                "reason": ((item.get("commit") or {}).get("verification") or {}).get(
                    "reason"
                ),
                "message": str((item.get("commit") or {}).get("message") or "").split(
                    "\n", 1
                )[0],
            }
            for item in commits
            if isinstance(item, dict)
        ]

        evidence_by_context: dict[str, list[dict[str, Any]]] = {}
        for item in compact_checks:
            evidence_by_context.setdefault(str(item["name"]), []).append(item)
        for item in compact_statuses:
            evidence_by_context.setdefault(str(item["context"]), []).append(item)

        missing_required: list[dict[str, Any]] = []
        non_success_required: list[dict[str, Any]] = []
        for required in required_checks:
            context = str(required.get("context") or "")
            integration_id = required.get("integration_id")
            candidates = evidence_by_context.get(context, [])
            if integration_id is not None:
                candidates = [
                    item
                    for item in candidates
                    if item.get("app_id") in {None, integration_id}
                ]
            if not candidates:
                missing_required.append(required)
                continue
            successful = False
            for item in candidates:
                conclusion = str(item.get("conclusion") or "").lower()
                state = str(item.get("state") or "").lower()
                if conclusion in SUCCESS_CONCLUSIONS or state == "success":
                    successful = True
            if not successful:
                non_success_required.append(
                    {"required": required, "observed": candidates}
                )

        unresolved_threads = None
        if isinstance(graph, dict):
            threads = graph.get("reviewThreads") or {}
            nodes = threads.get("nodes") or []
            unresolved_threads = sum(
                1
                for item in nodes
                if isinstance(item, dict) and item.get("isResolved") is False
            )

        report["targets"][str(number)] = {
            "rest": {
                "read_ok": pr_result["ok"],
                "state": pr.get("state") if isinstance(pr, dict) else None,
                "draft": pr.get("draft") if isinstance(pr, dict) else None,
                "mergeable": pr.get("mergeable") if isinstance(pr, dict) else None,
                "mergeable_state": (
                    pr.get("mergeable_state") if isinstance(pr, dict) else None
                ),
                "auto_merge": pr.get("auto_merge") if isinstance(pr, dict) else None,
                "head_sha": head_sha,
                "base_sha": (
                    (pr.get("base") or {}).get("sha")
                    if isinstance(pr, dict)
                    else None
                ),
            },
            "graphql": {
                "read_ok": graph_result["ok"],
                "error": graph_result.get("stderr"),
                "pull_request": graph,
                "unresolved_review_threads": unresolved_threads,
            },
            "required_checks": {
                "missing": missing_required,
                "non_success": non_success_required,
            },
            "checks": compact_checks,
            "statuses": compact_statuses,
            "commit_signatures": signatures,
            "unverified_commits": [
                item for item in signatures if item.get("verified") is not True
            ],
        }

    summary = {
        "schema": SCHEMA,
        "generation": report["generation"],
        "rule_types": rule_types,
        "required_checks": required_checks,
        "pull_request_rule": report["rules"]["pull_request"],
        "merge_queue_rule": report["rules"]["merge_queue"],
        "queue_branches": queue_branches,
        "merge_group_run_count": len(runs),
        "latest_merge_group_runs": merge_group_runs[:5],
        "targets": {},
    }
    for number, target in report["targets"].items():
        graph = target["graphql"]["pull_request"]
        summary["targets"][number] = {
            "mergeable_state": target["rest"]["mergeable_state"],
            "rest_auto_merge": target["rest"]["auto_merge"],
            "graphql_merge_state": (
                graph.get("mergeStateStatus") if isinstance(graph, dict) else None
            ),
            "review_decision": (
                graph.get("reviewDecision") if isinstance(graph, dict) else None
            ),
            "graphql_auto_merge": (
                graph.get("autoMergeRequest") if isinstance(graph, dict) else None
            ),
            "merge_queue_entry": (
                graph.get("mergeQueueEntry") if isinstance(graph, dict) else None
            ),
            "unresolved_review_threads": target["graphql"][
                "unresolved_review_threads"
            ],
            "missing_required_checks": target["required_checks"]["missing"],
            "non_success_required_checks": target["required_checks"][
                "non_success"
            ],
            "unverified_commits": target["unverified_commits"],
        }

    path = Path(os.environ.get("REPORT_PATH", "reports/merge-queue-blocker.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("MERGE_QUEUE_BLOCKER_SUMMARY")
    print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
