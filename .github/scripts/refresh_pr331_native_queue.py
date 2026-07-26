#!/usr/bin/env python3
"""Refresh PR #331 through GitHub's supported protected merge-queue mutations.

The controller validates the exact signed PR head, protected-main base, active
rules, required checks with integration bindings, qillqaq attestation, review
threads, and governed-token repository permission before making either mutation.

The only mutations are:

* ``dequeuePullRequest(id=<pull-request-node-id>)`` for the existing stuck entry;
* ``enqueuePullRequest(pullRequestId=..., expectedHeadOid=..., jump=false)``.

It never calls an immediate merge endpoint and never changes a branch ref,
ruleset, protection, review, status, check result, workflow, or secret setting.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPOSITORY = "szl-holdings/.github"
TARGET_PR = 331
EXPECTED_HEAD = "098cbb15c70330a57b7a8d858d47c4ef3eb847f5"
EXPECTED_BASE = "7d6a15026edab70ca99f059897dc3bdeee10f6df"
EXPECTED_COMMIT_COUNT = 1
SUCCESS_CONCLUSIONS = {"success", "neutral", "skipped"}
REPORT_PATH = Path(
    os.environ.get(
        "REPORT_PATH",
        "reports/pr331-native-queue-refresh.json",
    )
)


class QueueRefreshError(RuntimeError):
    """Raised when an exact queue-refresh invariant is not satisfied."""


def classify_error(value: object) -> str:
    text = str(value or "").lower()
    if "bad credentials" in text or "401" in text:
        return "unauthenticated"
    if "resource not accessible" in text or "forbidden" in text or "403" in text:
        return "unauthorized"
    if "not found" in text or "404" in text:
        return "not_found_or_hidden"
    if "expectedheadoid" in text or "head moved" in text:
        return "immutable_head_mismatch"
    if "required check" in text:
        return "required_check_failure"
    if "review thread" in text:
        return "review_thread_failure"
    if "signature" in text:
        return "signature_failure"
    if "queue" in text:
        return "queue_lifecycle_failure"
    return "other"


def token_env() -> dict[str, str]:
    token = os.environ.get("SZL_GITHUB_TOKEN") or ""
    if not token:
        raise QueueRefreshError("SZL_GITHUB_TOKEN is not configured")
    env = dict(os.environ)
    env["GH_TOKEN"] = token
    env.pop("GITHUB_TOKEN", None)
    return env


def invoke(
    arguments: list[str],
    *,
    payload: Mapping[str, Any] | None = None,
    allow_failure: bool = False,
) -> tuple[int, Any, str]:
    process = subprocess.run(
        ["gh", "api", *arguments],
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        check=False,
        env=token_env(),
    )
    stdout = process.stdout.strip()
    stderr = process.stderr.strip()[:3000]
    try:
        parsed: Any = json.loads(stdout) if stdout else None
    except json.JSONDecodeError:
        parsed = stdout[:3000]
    if process.returncode and not allow_failure:
        raise QueueRefreshError(
            "GitHub API operation failed: "
            f"class={classify_error(stderr or parsed)}"
        )
    return process.returncode, parsed, stderr


def rest(path: str) -> Any:
    return invoke(["--method", "GET", f"repos/{REPOSITORY}/{path}"])[1]


def graphql(query: str, variables: Mapping[str, Any]) -> dict[str, Any]:
    result = invoke(
        ["graphql", "--input", "-"],
        payload={"query": query, "variables": dict(variables)},
    )[1]
    if not isinstance(result, dict):
        raise QueueRefreshError("GraphQL response is not an object")
    if result.get("errors"):
        raise QueueRefreshError(
            "GraphQL operation failed: "
            f"class={classify_error(result.get('errors'))}"
        )
    return result


def pr_graph() -> dict[str, Any]:
    owner, name = REPOSITORY.split("/", 1)
    query = """
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        pullRequest(number: $number) {
          id
          number
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
            id
            position
            state
            enqueuedAt
          }
          reviewThreads(first: 100) {
            totalCount
            nodes { isResolved }
          }
        }
      }
    }
    """
    result = graphql(
        query,
        {"owner": owner, "name": name, "number": TARGET_PR},
    )
    pr = ((result.get("data") or {}).get("repository") or {}).get(
        "pullRequest"
    )
    if not isinstance(pr, dict):
        raise QueueRefreshError("GraphQL could not read PR #331")
    return pr


def active_rules() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    values = rest("rules/branches/main")
    if not isinstance(values, list):
        raise QueueRefreshError("active rules response is not a list")
    rules = [item for item in values if isinstance(item, dict)]
    kinds = {str(item.get("type") or "") for item in rules}
    required_kinds = {
        "merge_queue",
        "required_signatures",
        "required_linear_history",
        "required_status_checks",
        "pull_request",
    }
    missing = sorted(required_kinds - kinds)
    if missing:
        raise QueueRefreshError(f"active admission rules are missing: {missing}")

    pull_rules = [
        item.get("parameters") or {}
        for item in rules
        if item.get("type") == "pull_request"
    ]
    if not any(
        parameters.get("required_review_thread_resolution") is True
        and "squash" in (parameters.get("allowed_merge_methods") or [])
        for parameters in pull_rules
    ):
        raise QueueRefreshError(
            "active pull-request rule does not preserve thread resolution and squash"
        )

    for item in rules:
        if item.get("type") == "required_status_checks":
            parameters = item.get("parameters") or {}
            checks = parameters.get("required_status_checks") or []
            if not isinstance(checks, list) or not checks:
                raise QueueRefreshError("active required-check inventory is empty")
            return rules, [check for check in checks if isinstance(check, dict)]
    raise QueueRefreshError("active required-check rule is missing")


def compact_checks(head_sha: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    response = rest(
        f"commits/{head_sha}/check-runs?filter=latest&per_page=100"
    )
    values = response.get("check_runs") if isinstance(response, dict) else None
    if not isinstance(values, list):
        raise QueueRefreshError("head check-run inventory is unavailable")
    checks = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "status": item.get("status"),
            "conclusion": item.get("conclusion"),
            "app_id": (item.get("app") or {}).get("id"),
            "app_slug": (item.get("app") or {}).get("slug"),
        }
        for item in values
        if isinstance(item, dict)
    ]
    status_response = rest(f"commits/{head_sha}/status")
    status_values = (
        status_response.get("statuses", [])
        if isinstance(status_response, dict)
        else []
    )
    statuses = [
        {
            "id": item.get("id"),
            "context": item.get("context"),
            "state": item.get("state"),
            "creator": (item.get("creator") or {}).get("login"),
        }
        for item in status_values
        if isinstance(item, dict)
    ]
    return checks, statuses


def validate_required_checks(
    requirements: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    statuses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_context: dict[str, list[dict[str, Any]]] = {}
    for item in checks:
        by_context.setdefault(str(item.get("name") or ""), []).append(
            {"kind": "check_run", **item}
        )
    for item in statuses:
        by_context.setdefault(str(item.get("context") or ""), []).append(
            {"kind": "status", **item}
        )

    verified: list[dict[str, Any]] = []
    for requirement in requirements:
        context = str(requirement.get("context") or "")
        integration_id = requirement.get("integration_id")
        candidates = by_context.get(context, [])
        if integration_id is not None:
            candidates = [
                item
                for item in candidates
                if item.get("kind") == "check_run"
                and item.get("app_id") == integration_id
            ]
        passing = [
            item
            for item in candidates
            if (
                item.get("kind") == "check_run"
                and item.get("status") == "completed"
                and str(item.get("conclusion") or "").lower()
                in SUCCESS_CONCLUSIONS
            )
            or (
                item.get("kind") == "status"
                and str(item.get("state") or "").lower() == "success"
            )
        ]
        if not passing:
            raise QueueRefreshError(
                "required check is not successful: "
                f"context={context}; integration_id={integration_id}"
            )
        verified.append(
            {
                "requirement": requirement,
                "successful_evidence": passing,
            }
        )
    return verified


def validate_qillqaq(
    statuses: list[dict[str, Any]],
) -> dict[str, Any]:
    attestations = [
        item
        for item in statuses
        if item.get("context") == "attestation/qillqaq"
        and item.get("state") == "success"
    ]
    if not attestations:
        raise QueueRefreshError("attestation/qillqaq is not successful")
    reviews = rest(f"pulls/{TARGET_PR}/reviews?per_page=100")
    if not isinstance(reviews, list):
        raise QueueRefreshError("pull-request review inventory is unavailable")
    approvals = [
        {
            "state": item.get("state"),
            "submitted_at": item.get("submitted_at"),
            "author": (item.get("user") or {}).get("login"),
        }
        for item in reviews
        if isinstance(item, dict)
        and item.get("state") == "APPROVED"
        and str((item.get("user") or {}).get("login") or "").startswith(
            "qillqaq-attestor"
        )
    ]
    if not approvals:
        raise QueueRefreshError("qillqaq approval review is missing")
    return {
        "status": attestations[-1],
        "review": approvals[-1],
    }


def validate_token_capability() -> dict[str, Any]:
    repository = invoke(
        ["--method", "GET", f"repos/{REPOSITORY}"],
    )[1]
    if not isinstance(repository, dict):
        raise QueueRefreshError("repository capability response is not an object")
    permissions = repository.get("permissions") or {}
    capability = {
        "admin": bool(permissions.get("admin")),
        "maintain": bool(permissions.get("maintain")),
        "push": bool(permissions.get("push")),
        "pull": bool(permissions.get("pull")),
    }
    if not any(capability[key] for key in ("admin", "maintain", "push")):
        raise QueueRefreshError("governed token lacks repository write capability")
    return capability


def validate_target() -> dict[str, Any]:
    rest_pr = rest(f"pulls/{TARGET_PR}")
    if not isinstance(rest_pr, dict):
        raise QueueRefreshError("pull-request response is not an object")
    head = rest_pr.get("head") or {}
    base = rest_pr.get("base") or {}
    if rest_pr.get("state") != "open" or rest_pr.get("draft") is True:
        raise QueueRefreshError("PR #331 must be open and ready")
    if ((head.get("repo") or {}).get("full_name")) != REPOSITORY:
        raise QueueRefreshError("PR #331 is not a same-repository branch")
    if str(head.get("sha") or "").lower() != EXPECTED_HEAD:
        raise QueueRefreshError("PR #331 head moved")
    if str(base.get("sha") or "").lower() != EXPECTED_BASE:
        raise QueueRefreshError("PR #331 base moved")
    if int(rest_pr.get("commits") or 0) != EXPECTED_COMMIT_COUNT:
        raise QueueRefreshError("PR #331 does not contain exactly one commit")
    if rest_pr.get("mergeable") is not True:
        raise QueueRefreshError("PR #331 is not mergeable")

    commit = rest(f"commits/{EXPECTED_HEAD}")
    verification = ((commit or {}).get("commit") or {}).get("verification") or {}
    parents = [
        str(item.get("sha") or "").lower()
        for item in (commit or {}).get("parents") or []
        if isinstance(item, dict)
    ]
    if verification.get("verified") is not True:
        raise QueueRefreshError("PR #331 commit signature is not verified")
    if parents != [EXPECTED_BASE]:
        raise QueueRefreshError(f"PR #331 parent mismatch: {parents}")

    graph = pr_graph()
    if graph.get("state") != "OPEN" or graph.get("isDraft") is True:
        raise QueueRefreshError("GraphQL PR state is not ready")
    if str(graph.get("headRefOid") or "").lower() != EXPECTED_HEAD:
        raise QueueRefreshError("GraphQL PR head moved")
    if str(graph.get("baseRefOid") or "").lower() != EXPECTED_BASE:
        raise QueueRefreshError("GraphQL PR base moved")
    if graph.get("mergeable") != "MERGEABLE":
        raise QueueRefreshError(
            f"GraphQL PR mergeability is {graph.get('mergeable')}"
        )
    threads = (graph.get("reviewThreads") or {}).get("nodes") or []
    unresolved = sum(
        1
        for item in threads
        if isinstance(item, dict) and item.get("isResolved") is False
    )
    if unresolved:
        raise QueueRefreshError(
            f"PR #331 has {unresolved} unresolved review threads"
        )

    rules, requirements = active_rules()
    checks, statuses = compact_checks(EXPECTED_HEAD)
    required = validate_required_checks(requirements, checks, statuses)
    qillqaq = validate_qillqaq(statuses)
    capability = validate_token_capability()
    return {
        "rest": {
            "state": rest_pr.get("state"),
            "mergeable_state": rest_pr.get("mergeable_state"),
            "commits": rest_pr.get("commits"),
            "head_sha": EXPECTED_HEAD,
            "base_sha": EXPECTED_BASE,
        },
        "graphql": graph,
        "signature": {
            "verified": verification.get("verified"),
            "reason": verification.get("reason"),
            "parents": parents,
        },
        "active_rule_types": [item.get("type") for item in rules],
        "required_checks": required,
        "qillqaq": qillqaq,
        "governed_token_capability": capability,
        "credential_name": "SZL_GITHUB_TOKEN",
        "credential_value_recorded": False,
    }


def queue_branches() -> list[dict[str, Any]]:
    values = rest("branches?per_page=100")
    if not isinstance(values, list):
        raise QueueRefreshError("branch inventory is not a list")
    return [
        {
            "name": item.get("name"),
            "sha": (item.get("commit") or {}).get("sha"),
        }
        for item in values
        if isinstance(item, dict)
        and str(item.get("name") or "").startswith(
            "gh-readonly-queue/main/pr-331-"
        )
    ]


def merge_group_runs() -> list[dict[str, Any]]:
    response = rest("actions/runs?event=merge_group&per_page=100")
    values = response.get("workflow_runs") if isinstance(response, dict) else None
    if not isinstance(values, list):
        raise QueueRefreshError("merge-group run inventory is unavailable")
    return [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "status": item.get("status"),
            "conclusion": item.get("conclusion"),
            "head_branch": item.get("head_branch"),
            "head_sha": item.get("head_sha"),
            "created_at": item.get("created_at"),
            "html_url": item.get("html_url"),
        }
        for item in values
        if isinstance(item, dict)
        and str(item.get("head_branch") or "").startswith(
            "gh-readonly-queue/main/pr-331-"
        )
    ]


def dequeue(pr_node_id: str) -> None:
    mutation = """
    mutation($input: DequeuePullRequestInput!) {
      dequeuePullRequest(input: $input) {
        clientMutationId
      }
    }
    """
    graphql(mutation, {"input": {"id": pr_node_id}})


def enqueue(pr_node_id: str) -> dict[str, Any]:
    mutation = """
    mutation($input: EnqueuePullRequestInput!) {
      enqueuePullRequest(input: $input) {
        mergeQueueEntry {
          id
          position
          state
          enqueuedAt
          pullRequest { number headRefOid }
        }
      }
    }
    """
    result = graphql(
        mutation,
        {
            "input": {
                "pullRequestId": pr_node_id,
                "expectedHeadOid": EXPECTED_HEAD,
                "jump": False,
            }
        },
    )
    entry = ((result.get("data") or {}).get("enqueuePullRequest") or {}).get(
        "mergeQueueEntry"
    )
    if not isinstance(entry, dict):
        raise QueueRefreshError("enqueuePullRequest returned no queue entry")
    pull = entry.get("pullRequest") or {}
    if int(pull.get("number") or 0) != TARGET_PR:
        raise QueueRefreshError("enqueuePullRequest returned a different PR")
    if str(pull.get("headRefOid") or "").lower() != EXPECTED_HEAD:
        raise QueueRefreshError("enqueuePullRequest returned a different head")
    return entry


def wait_for_dequeue() -> dict[str, Any]:
    last = pr_graph()
    for _ in range(30):
        last = pr_graph()
        if last.get("mergeQueueEntry") is None:
            return last
        time.sleep(1)
    raise QueueRefreshError("existing queue entry did not clear after dequeue")


def wait_for_delivery(
    before_branches: list[dict[str, Any]],
    before_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    before_shas = {str(item.get("sha") or "") for item in before_branches}
    before_run_ids = {int(item.get("id") or 0) for item in before_runs}
    observation: dict[str, Any] = {}
    for _ in range(90):
        graph = pr_graph()
        branches = queue_branches()
        runs = merge_group_runs()
        current_shas = {str(item.get("sha") or "") for item in branches}
        new_runs = [
            item
            for item in runs
            if int(item.get("id") or 0) not in before_run_ids
        ]
        observation = {
            "graphql": graph,
            "queue_branches": branches,
            "new_queue_branch_sha": sorted(current_shas - before_shas),
            "merge_group_runs": runs,
            "new_merge_group_runs": new_runs,
        }
        if graph.get("state") == "MERGED":
            observation["result"] = "merged"
            return observation
        entry = graph.get("mergeQueueEntry")
        if isinstance(entry, dict) and (
            new_runs or str(entry.get("state") or "") == "QUEUED"
        ):
            observation["result"] = (
                "merge_group_dispatched" if new_runs else "queued"
            )
            return observation
        time.sleep(2)
    observation["result"] = "delivery_not_observed"
    return observation


def main() -> int:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema": "szl.pr331-native-queue-refresh/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": REPOSITORY,
        "target": {
            "pull_request": TARGET_PR,
            "head_sha": EXPECTED_HEAD,
            "base_sha": EXPECTED_BASE,
        },
        "status": "FAILED_CLOSED",
        "boundaries": [
            "The only mutations are dequeuePullRequest and enqueuePullRequest.",
            "enqueuePullRequest is bound to expectedHeadOid and jump=false.",
            "No immediate merge endpoint or admin bypass is used.",
            "No branch ref, rule, protection, review, status, check result, workflow, or secret setting is changed.",
            "Secret values, lengths, prefixes, hashes, identities, and headers are never recorded.",
        ],
    }
    error: str | None = None
    try:
        preflight = validate_target()
        before_graph = preflight["graphql"]
        node_id = str(before_graph.get("id") or "")
        if not node_id:
            raise QueueRefreshError("PR #331 lacks a GraphQL node ID")
        existing = before_graph.get("mergeQueueEntry")
        if not isinstance(existing, dict):
            raise QueueRefreshError("PR #331 has no existing queue entry to refresh")
        before_branches = queue_branches()
        before_runs = merge_group_runs()

        dequeue(node_id)
        after_dequeue = wait_for_dequeue()
        entry = enqueue(node_id)
        observation = wait_for_delivery(before_branches, before_runs)
        if observation.get("result") == "delivery_not_observed":
            raise QueueRefreshError(
                "native re-enqueue completed but merge-group delivery was not observed"
            )
        report.update(
            {
                "status": "QUEUE_REFRESH_VERIFIED",
                "preflight": preflight,
                "before": {
                    "queue_entry": existing,
                    "queue_branches": before_branches,
                    "merge_group_runs": before_runs,
                },
                "after_dequeue": after_dequeue,
                "enqueue_result": entry,
                "delivery": observation,
            }
        )
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        report["fatal"] = {
            "type": type(exc).__name__,
            "class": classify_error(exc),
        }
    finally:
        report["generated_at"] = datetime.now(timezone.utc).isoformat()
        REPORT_PATH.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if error is None else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except QueueRefreshError as exc:
        print(f"FATAL: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1)
