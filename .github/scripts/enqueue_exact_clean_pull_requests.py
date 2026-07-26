#!/usr/bin/env python3
"""Enqueue two exact clean signed PR heads through GitHub's queue mutation.

GitHub exposes ``enqueuePullRequest`` specifically for adding a pull request to
an active merge queue. The mutation accepts ``expectedHeadOid``; this controller
uses it after reusing the full active-rules, required-check, signature, linear-
history, mergeability, and unresolved-thread preflight from
``request_exact_clean_merge_queue``.

No immediate merge mutation or REST merge endpoint is called. No ruleset,
protection, review, status, check conclusion, branch ref, or secret setting is
changed.
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

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import request_exact_clean_merge_queue as preflight

REPORT_SCHEMA = "szl.exact-clean-enqueue/v1"


class EnqueueError(RuntimeError):
    """Raised when an exact queue-entry invariant is not satisfied."""


def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    process = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=json.dumps({"query": query, "variables": variables}),
        capture_output=True,
        text=True,
        check=False,
        env=os.environ,
    )
    if process.returncode:
        raise EnqueueError(
            f"GraphQL failed ({process.returncode}): "
            f"{(process.stderr.strip() or process.stdout.strip())[:3000]}"
        )
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise EnqueueError("GraphQL returned non-JSON output") from exc
    if result.get("errors"):
        raise EnqueueError(
            "GraphQL returned errors: "
            + json.dumps(result["errors"], sort_keys=True)[:3000]
        )
    return result


def _enqueue(
    pull_request_id: str,
    expected_head_oid: str,
) -> dict[str, Any]:
    mutation = """
    mutation($input: EnqueuePullRequestInput!) {
      enqueuePullRequest(input: $input) {
        mergeQueueEntry {
          id
          position
          state
          pullRequest {
            number
            headRefOid
          }
        }
      }
    }
    """
    result = _graphql(
        mutation,
        {
            "input": {
                "pullRequestId": pull_request_id,
                "expectedHeadOid": expected_head_oid,
                "jump": False,
            }
        },
    )
    payload = ((result.get("data") or {}).get("enqueuePullRequest") or {})
    entry = payload.get("mergeQueueEntry")
    if not isinstance(entry, dict):
        raise EnqueueError("enqueuePullRequest returned no mergeQueueEntry")
    pull = entry.get("pullRequest") or {}
    if str(pull.get("headRefOid") or "").lower() != expected_head_oid:
        raise EnqueueError(
            "enqueuePullRequest returned an entry for a different head: "
            f"expected {expected_head_oid}, observed {pull.get('headRefOid')!r}"
        )
    return entry


def _observe(repository: str, number: int, head_sha: str) -> dict[str, Any]:
    observation: dict[str, Any] = {}
    for _ in range(30):
        graph = preflight._pr_graph(repository, number)
        observation = {
            "state": graph.get("state"),
            "head_ref_oid": graph.get("headRefOid"),
            "merge_state_status": graph.get("mergeStateStatus"),
            "auto_merge_request": graph.get("autoMergeRequest"),
            "merge_queue_entry": graph.get("mergeQueueEntry"),
        }
        if str(observation["head_ref_oid"] or "").lower() != head_sha:
            raise EnqueueError(
                f"PR #{number} head moved after enqueue request: "
                f"expected {head_sha}, observed {observation['head_ref_oid']!r}"
            )
        if observation["state"] == "MERGED":
            return observation
        if observation["merge_queue_entry"] is not None:
            return observation
        time.sleep(2)
    return observation


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY")
    if repository != "szl-holdings/.github":
        raise EnqueueError(
            f"enqueue controller is locked to szl-holdings/.github, got {repository!r}"
        )
    if not os.environ.get("GH_TOKEN"):
        raise EnqueueError("GH_TOKEN is required")

    report_path = Path(
        os.environ.get("REPORT_PATH", "reports/exact-clean-enqueue.json")
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    error: str | None = None

    try:
        rules = preflight._rest(repository, "rules/branches/main")
        required = preflight._required_checks(rules)

        # Complete the entire read-only preflight for both PRs before enqueueing
        # either target.
        for target in preflight.TARGETS:
            record = preflight._validate_target(repository, target, required)
            pr = preflight._rest(repository, f"pulls/{target.number}")
            node_id = str((pr or {}).get("node_id") or "")
            if not node_id:
                raise EnqueueError(
                    f"PR #{target.number} has no GraphQL node ID"
                )
            record["pull_request_id"] = node_id
            records.append(record)

        for target, record in zip(preflight.TARGETS, records, strict=True):
            current = preflight._pr_graph(repository, target.number)
            existing = current.get("mergeQueueEntry")
            if existing is not None:
                record["mutation"] = "already_enqueued"
                record["mutation_entry"] = existing
            elif current.get("state") == "MERGED":
                record["mutation"] = "already_merged"
            else:
                record["mutation"] = "enqueuePullRequest"
                record["mutation_entry"] = _enqueue(
                    str(record["pull_request_id"]),
                    target.head_sha,
                )

            after = _observe(repository, target.number, target.head_sha)
            record["after"] = after
            if after.get("state") != "MERGED" and after.get(
                "merge_queue_entry"
            ) is None:
                raise EnqueueError(
                    f"PR #{target.number} did not enter the merge queue: {after}"
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
            "status": "ENQUEUED_OR_MERGED" if error is None else "FAILED_CLOSED",
            "error": error,
            "targets": records,
            "boundaries": [
                "enqueuePullRequest is the only merge-related mutation used.",
                "Every mutation includes the exact expectedHeadOid of a verified GitHub-signed one-commit PR head.",
                "jump is explicitly false; neither PR is moved ahead of existing queue entries.",
                "The immediate mergePullRequest mutation and REST merge endpoint are never called.",
                "No ruleset, protection, review, status, check conclusion, branch ref, or secret setting is changed.",
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
    except EnqueueError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1)
