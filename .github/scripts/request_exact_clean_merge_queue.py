#!/usr/bin/env python3
"""Request GitHub's protected merge queue for two exact clean signed PR heads.

The repository's reviewed attestor uses ``gh pr merge --auto --squash`` as the
supported queue-entry path. This controller invokes that same path only after
revalidating the active merge-queue rule, immutable head/base SHAs, GitHub
signature verification, one-commit linear history, zero unresolved review
threads, and every active required status check including integration IDs.

It never calls the immediate pull-request merge REST endpoint and never changes
rulesets, protections, reviews, statuses, checks, or secret configuration.
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

REPORT_SCHEMA = "szl.exact-clean-merge-queue-request/v1"
SUCCESS_CONCLUSIONS = {"success", "neutral", "skipped"}


@dataclass(frozen=True)
class Target:
    number: int
    head_sha: str
    base_sha: str


TARGETS = (
    Target(
        number=322,
        head_sha="52ab3fc1a17b5366010dd1bcfe8f6dcb5db4a286",
        base_sha="a03122857a1bc77f348c3db01d0be00ca39e6d69",
    ),
    Target(
        number=323,
        head_sha="fb8a1c2435db5bff99be51faefc9781309d0f9a4",
        base_sha="a03122857a1bc77f348c3db01d0be00ca39e6d69",
    ),
)


class QueueError(RuntimeError):
    """Raised when a queue precondition or queue request fails."""


def _invoke(
    command: list[str],
    *,
    json_output: bool = True,
    allow_failure: bool = False,
) -> tuple[int, Any, str]:
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        env=os.environ,
    )
    stdout = process.stdout.strip()
    stderr = process.stderr.strip()[:3000]
    payload: Any = stdout
    if json_output and stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            if not allow_failure:
                raise QueueError(
                    f"command returned non-JSON output: {' '.join(command[:4])}: "
                    f"{stdout[:1000]}"
                ) from exc
    if process.returncode and not allow_failure:
        raise QueueError(
            f"command failed ({process.returncode}): {' '.join(command[:5])}; "
            f"{stderr or str(payload)[:2000]}"
        )
    return process.returncode, payload, stderr


def _gh_api(arguments: list[str], *, allow_failure: bool = False) -> Any:
    code, payload, stderr = _invoke(
        ["gh", "api", *arguments],
        allow_failure=allow_failure,
    )
    if code and allow_failure:
        return {"error": stderr or payload, "returncode": code}
    return payload


def _rest(repository: str, path: str) -> Any:
    return _gh_api(["--method", "GET", f"repos/{repository}/{path}"])


def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = _gh_api(
        ["graphql", "--input", "-"],
        allow_failure=False,
    ) if False else None
    # gh api --input reads a complete JSON request from stdin, so use the common
    # subprocess helper directly to avoid shell interpolation.
    process = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=json.dumps({"query": query, "variables": variables}),
        capture_output=True,
        text=True,
        check=False,
        env=os.environ,
    )
    if process.returncode:
        raise QueueError(
            f"GraphQL failed ({process.returncode}): "
            f"{(process.stderr.strip() or process.stdout.strip())[:3000]}"
        )
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise QueueError("GraphQL returned non-JSON output") from exc
    if result.get("errors"):
        raise QueueError(
            "GraphQL returned errors: "
            + json.dumps(result["errors"], sort_keys=True)[:3000]
        )
    return result


def _pr_graph(repository: str, number: int) -> dict[str, Any]:
    owner, name = repository.split("/", 1)
    query = """
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        pullRequest(number: $number) {
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
    result = _graphql(
        query,
        {"owner": owner, "name": name, "number": number},
    )
    pr = ((result.get("data") or {}).get("repository") or {}).get(
        "pullRequest"
    )
    if not isinstance(pr, dict):
        raise QueueError(f"GraphQL could not read PR #{number}")
    return pr


def _required_checks(rules: Any) -> list[dict[str, Any]]:
    if not isinstance(rules, list):
        raise QueueError("active rules response is not a list")
    if not any(
        isinstance(rule, dict) and rule.get("type") == "merge_queue"
        for rule in rules
    ):
        raise QueueError("active main rules do not contain a merge_queue rule")
    if not any(
        isinstance(rule, dict) and rule.get("type") == "required_signatures"
        for rule in rules
    ):
        raise QueueError("active main rules do not contain required_signatures")
    for rule in rules:
        if isinstance(rule, dict) and rule.get("type") == "required_status_checks":
            parameters = rule.get("parameters") or {}
            checks = parameters.get("required_status_checks") or []
            if not isinstance(checks, list) or not checks:
                raise QueueError("required status checks are empty")
            return [item for item in checks if isinstance(item, dict)]
    raise QueueError("active main rules do not contain required_status_checks")


def _validate_checks(
    repository: str,
    head_sha: str,
    required: list[dict[str, Any]],
) -> dict[str, Any]:
    response = _rest(
        repository,
        f"commits/{head_sha}/check-runs?filter=latest&per_page=100",
    )
    checks = response.get("check_runs") if isinstance(response, dict) else None
    if not isinstance(checks, list):
        raise QueueError(f"check-run inventory unavailable for {head_sha}")
    statuses_response = _rest(repository, f"commits/{head_sha}/status")
    statuses = (
        statuses_response.get("statuses", [])
        if isinstance(statuses_response, dict)
        else []
    )

    by_context: dict[str, list[dict[str, Any]]] = {}
    for item in checks:
        if not isinstance(item, dict):
            continue
        app = item.get("app") or {}
        by_context.setdefault(str(item.get("name") or ""), []).append(
            {
                "kind": "check_run",
                "id": item.get("id"),
                "status": item.get("status"),
                "conclusion": item.get("conclusion"),
                "app_id": app.get("id"),
                "app_slug": app.get("slug"),
            }
        )
    for item in statuses:
        if not isinstance(item, dict):
            continue
        by_context.setdefault(str(item.get("context") or ""), []).append(
            {
                "kind": "status",
                "id": item.get("id"),
                "state": item.get("state"),
                "app_id": None,
                "creator": (item.get("creator") or {}).get("login"),
            }
        )

    verified: list[dict[str, Any]] = []
    for requirement in required:
        context = str(requirement.get("context") or "")
        integration_id = requirement.get("integration_id")
        candidates = by_context.get(context, [])
        if integration_id is not None:
            candidates = [
                candidate
                for candidate in candidates
                if candidate.get("app_id") in {None, integration_id}
            ]
        successful = [
            candidate
            for candidate in candidates
            if str(candidate.get("conclusion") or "").lower()
            in SUCCESS_CONCLUSIONS
            or str(candidate.get("state") or "").lower() == "success"
        ]
        if not successful:
            raise QueueError(
                f"required check is not successful for {head_sha}: "
                f"{context} integration={integration_id}; observed={candidates}"
            )
        verified.append(
            {
                "requirement": requirement,
                "successful_evidence": successful,
            }
        )

    non_terminal = [
        {
            "name": item.get("name"),
            "id": item.get("id"),
            "status": item.get("status"),
            "conclusion": item.get("conclusion"),
        }
        for item in checks
        if isinstance(item, dict) and item.get("status") != "completed"
    ]
    if non_terminal:
        raise QueueError(
            f"head {head_sha} still has non-terminal checks: {non_terminal}"
        )
    return {"required": verified, "non_terminal": non_terminal}


def _validate_target(
    repository: str,
    target: Target,
    required: list[dict[str, Any]],
) -> dict[str, Any]:
    pr = _rest(repository, f"pulls/{target.number}")
    if not isinstance(pr, dict):
        raise QueueError(f"PR #{target.number} response is not an object")
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    observed_head = str(head.get("sha") or "").lower()
    observed_base = str(base.get("sha") or "").lower()
    if pr.get("state") != "open" or pr.get("draft") is True:
        raise QueueError(f"PR #{target.number} must be open and ready")
    if ((head.get("repo") or {}).get("full_name")) != repository:
        raise QueueError(f"PR #{target.number} is not a same-repository branch")
    if observed_head != target.head_sha:
        raise QueueError(
            f"PR #{target.number} head moved: expected {target.head_sha}, "
            f"observed {observed_head}"
        )
    if observed_base != target.base_sha:
        raise QueueError(
            f"PR #{target.number} base moved: expected {target.base_sha}, "
            f"observed {observed_base}"
        )
    if int(pr.get("commits") or 0) != 1:
        raise QueueError(
            f"PR #{target.number} must have one signed snapshot commit"
        )
    if pr.get("mergeable") is not True:
        raise QueueError(f"PR #{target.number} is not mergeable")

    commit = _rest(repository, f"commits/{target.head_sha}")
    verification = ((commit.get("commit") or {}).get("verification") or {})
    if verification.get("verified") is not True:
        raise QueueError(
            f"PR #{target.number} commit signature is not verified: "
            f"{verification}"
        )

    graph = _pr_graph(repository, target.number)
    if str(graph.get("headRefOid") or "").lower() != target.head_sha:
        raise QueueError(f"PR #{target.number} GraphQL head moved")
    if str(graph.get("baseRefOid") or "").lower() != target.base_sha:
        raise QueueError(f"PR #{target.number} GraphQL base moved")
    if graph.get("state") != "OPEN" or graph.get("isDraft") is True:
        raise QueueError(f"PR #{target.number} GraphQL state is not ready")
    if graph.get("mergeable") != "MERGEABLE":
        raise QueueError(
            f"PR #{target.number} GraphQL mergeability is {graph.get('mergeable')}"
        )
    threads = (graph.get("reviewThreads") or {}).get("nodes") or []
    unresolved = sum(
        1
        for item in threads
        if isinstance(item, dict) and item.get("isResolved") is False
    )
    if unresolved:
        raise QueueError(
            f"PR #{target.number} has {unresolved} unresolved review threads"
        )

    checks = _validate_checks(repository, target.head_sha, required)
    return {
        "pull_request": target.number,
        "head_sha": target.head_sha,
        "base_sha": target.base_sha,
        "mergeable_state": pr.get("mergeable_state"),
        "graphql_merge_state": graph.get("mergeStateStatus"),
        "review_decision": graph.get("reviewDecision"),
        "signature": verification,
        "unresolved_threads": unresolved,
        "checks": checks,
        "before": {
            "auto_merge_request": graph.get("autoMergeRequest"),
            "merge_queue_entry": graph.get("mergeQueueEntry"),
        },
    }


def _request(repository: str, target: Target) -> tuple[int, str, str]:
    return _invoke(
        [
            "gh",
            "pr",
            "merge",
            str(target.number),
            "--repo",
            repository,
            "--auto",
            "--squash",
        ],
        json_output=False,
        allow_failure=True,
    )


def _observe_queue(repository: str, target: Target) -> dict[str, Any]:
    observation: dict[str, Any] = {}
    for _ in range(30):
        pr = _rest(repository, f"pulls/{target.number}")
        graph = _pr_graph(repository, target.number)
        observation = {
            "rest_state": pr.get("state") if isinstance(pr, dict) else None,
            "merged": pr.get("merged") if isinstance(pr, dict) else None,
            "mergeable_state": (
                pr.get("mergeable_state") if isinstance(pr, dict) else None
            ),
            "graphql_state": graph.get("state"),
            "auto_merge_request": graph.get("autoMergeRequest"),
            "merge_queue_entry": graph.get("mergeQueueEntry"),
        }
        if observation["merged"] is True or observation["graphql_state"] == "MERGED":
            return observation
        if observation["merge_queue_entry"] is not None:
            return observation
        time.sleep(2)
    return observation


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY")
    if repository != "szl-holdings/.github":
        raise QueueError(
            f"queue controller is locked to szl-holdings/.github, got {repository!r}"
        )
    if not os.environ.get("GH_TOKEN"):
        raise QueueError("GH_TOKEN is required")

    report_path = Path(
        os.environ.get(
            "REPORT_PATH",
            "reports/exact-clean-merge-queue-request.json",
        )
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    error: str | None = None

    try:
        rules = _rest(repository, "rules/branches/main")
        required = _required_checks(rules)

        # Validate both targets completely before requesting either one.
        records = [
            _validate_target(repository, target, required)
            for target in TARGETS
        ]

        for target, record in zip(TARGETS, records, strict=True):
            code, stdout, stderr = _request(repository, target)
            record["request"] = {
                "returncode": code,
                "stdout": str(stdout)[:3000],
                "stderr": stderr,
            }
            # `gh pr merge --auto` may return non-zero when the exact auto-merge
            # request already exists. The authoritative result is the subsequent
            # GraphQL queue/merge observation, not CLI wording.
            after = _observe_queue(repository, target)
            record["after"] = after
            if after.get("merged") is not True and after.get(
                "graphql_state"
            ) != "MERGED" and after.get("merge_queue_entry") is None:
                raise QueueError(
                    f"PR #{target.number} did not enter the merge queue: "
                    f"cli={record['request']}; observation={after}"
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
            "status": "QUEUED_OR_MERGED" if error is None else "FAILED_CLOSED",
            "error": error,
            "targets": records,
            "boundaries": [
                "The immediate pull-request merge REST endpoint is never called.",
                "The supported gh pr merge --auto --squash path is used after exact preflight.",
                "The active merge-queue, required-signatures, and required-check rules are read and left unchanged.",
                "No review, status, check conclusion, ruleset, protection, or secret value is created or altered by this controller.",
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
    except QueueError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1)
