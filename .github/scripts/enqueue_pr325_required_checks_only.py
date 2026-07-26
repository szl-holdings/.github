#!/usr/bin/env python3
"""Enqueue exact signed PR #325 after validating only active admission rules.

The previous auxiliary controller rejected every unrelated non-terminal check
run, even though GitHub's active ruleset requires only the declared status
contexts. This controller keeps every repository safeguard intact and validates:

* active merge-queue, signature, linear-history, and status-check rules;
* the exact immutable PR head and base;
* one GitHub-verified commit whose sole parent is the exact base;
* zero unresolved review threads;
* every active required status context, including integration binding;
* a governed user token with sufficient repository permission.

The only merge-related mutation is ``enqueuePullRequest`` with
``expectedHeadOid`` and ``jump=false``. It never immediately merges a pull
request and never changes a ruleset, protection, review, status, check result,
branch ref, or secret setting.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import enqueue_exact_clean_pull_requests as enqueue
import request_exact_clean_merge_queue as preflight

REPOSITORY = "szl-holdings/.github"
TARGET = preflight.Target(
    number=325,
    head_sha="93a5138742497345cca21b8bd1a385d3b499c579",
    base_sha="527fd000c5189f7b1ca4e56b7993d1daa952308a",
)
REPORT_SCHEMA = "szl.required-check-only-enqueue/v1"
REPORT_PATH = Path(
    os.environ.get(
        "REPORT_PATH",
        "reports/pr325-required-check-enqueue.json",
    )
)
CANDIDATE_ENV_NAMES = (
    "SZL_GITHUB_TOKEN",
    "GH_NOTIFICATIONS_TOKEN",
)
ALLOWED_VIEWER_PERMISSIONS = {"WRITE", "MAINTAIN", "ADMIN"}
PASSING_CONCLUSIONS = {"success", "neutral", "skipped"}


class AdmissionError(RuntimeError):
    """Raised when an exact admission invariant is not satisfied."""


@contextmanager
def credential(token: str) -> Iterator[None]:
    previous = os.environ.get("GH_TOKEN")
    os.environ["GH_TOKEN"] = token
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("GH_TOKEN", None)
        else:
            os.environ["GH_TOKEN"] = previous


def classify_error(value: object) -> str:
    text = str(value or "").lower()
    if "401" in text or "bad credentials" in text:
        return "unauthenticated"
    if "403" in text or "forbidden" in text or "resource not accessible" in text:
        return "unauthorized"
    if "404" in text or "not found" in text:
        return "not_found_or_hidden"
    if "head moved" in text or "expectedheadoid" in text:
        return "immutable_head_mismatch"
    if "required check" in text:
        return "required_check_failure"
    if "signature" in text:
        return "signature_failure"
    if "review thread" in text:
        return "review_thread_failure"
    if not text:
        return "unspecified"
    return "other"


def api_json(token: str, arguments: list[str]) -> tuple[bool, Any, str]:
    env = dict(os.environ)
    env["GH_TOKEN"] = token
    process = subprocess.run(
        ["gh", "api", *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    output = process.stdout.strip()
    try:
        payload: Any = json.loads(output) if output else None
    except json.JSONDecodeError:
        payload = None
    error = process.stderr.strip()[:1000]
    return process.returncode == 0, payload, error


def capability_probe(token: str) -> dict[str, Any]:
    user_ok, _, user_error = api_json(token, ["--method", "GET", "user"])
    repo_ok, repo_payload, repo_error = api_json(
        token,
        ["--method", "GET", f"repos/{REPOSITORY}"],
    )
    permissions = (
        repo_payload.get("permissions")
        if repo_ok and isinstance(repo_payload, dict)
        else None
    )

    owner, name = REPOSITORY.split("/", 1)
    query = """
    query($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) { viewerPermission }
      viewer { id }
    }
    """
    env = dict(os.environ)
    env["GH_TOKEN"] = token
    process = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        input=json.dumps(
            {
                "query": query,
                "variables": {"owner": owner, "name": name},
            }
        ),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    graph: Any = None
    if process.stdout.strip():
        try:
            graph = json.loads(process.stdout)
        except json.JSONDecodeError:
            graph = None
    graph_errors = graph.get("errors") if isinstance(graph, dict) else None
    viewer_permission = None
    if process.returncode == 0 and isinstance(graph, dict) and not graph_errors:
        viewer_permission = (
            ((graph.get("data") or {}).get("repository") or {}).get(
                "viewerPermission"
            )
        )

    return {
        "user_api_authenticated": user_ok,
        "repository_api_authenticated": repo_ok,
        "graphql_authenticated": process.returncode == 0 and not graph_errors,
        "viewer_permission": viewer_permission,
        "repository_permissions": (
            {
                "admin": bool((permissions or {}).get("admin")),
                "maintain": bool((permissions or {}).get("maintain")),
                "push": bool((permissions or {}).get("push")),
                "triage": bool((permissions or {}).get("triage")),
                "pull": bool((permissions or {}).get("pull")),
            }
            if isinstance(permissions, dict)
            else None
        ),
        "error_classes": {
            "user": "none" if user_ok else classify_error(user_error),
            "repository": "none" if repo_ok else classify_error(repo_error),
            "graphql": (
                "none"
                if process.returncode == 0 and not graph_errors
                else classify_error(process.stderr)
            ),
        },
    }


def active_rule_types(rules: Any) -> set[str]:
    if not isinstance(rules, list):
        raise AdmissionError("active rules response is not a list")
    return {
        str(item.get("type"))
        for item in rules
        if isinstance(item, dict) and item.get("type")
    }


def validate_required_checks(
    head_sha: str,
    required: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    response = preflight._rest(
        REPOSITORY,
        f"commits/{head_sha}/check-runs?filter=latest&per_page=100",
    )
    checks = response.get("check_runs") if isinstance(response, dict) else None
    if not isinstance(checks, list):
        raise AdmissionError("check-run inventory is unavailable")

    status_response = preflight._rest(REPOSITORY, f"commits/{head_sha}/status")
    statuses = (
        status_response.get("statuses", [])
        if isinstance(status_response, dict)
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
                "creator": (item.get("creator") or {}).get("login"),
                "app_id": None,
            }
        )

    verified: list[dict[str, Any]] = []
    for requirement in required:
        context = str(requirement.get("context") or "")
        integration_id = requirement.get("integration_id")
        candidates = by_context.get(context, [])
        if integration_id is not None:
            # Integration-bound requirements must be satisfied by a check run
            # from that exact App. A legacy status with the same text is not enough.
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
                in PASSING_CONCLUSIONS
            )
            or (
                item.get("kind") == "status"
                and str(item.get("state") or "").lower() == "success"
            )
        ]
        if not passing:
            raise AdmissionError(
                f"required check is not successful: {context}; "
                f"integration={integration_id}; observed={candidates}"
            )
        verified.append(
            {
                "requirement": requirement,
                "successful_evidence": passing,
            }
        )
    return verified


def validate_target() -> dict[str, Any]:
    rules = preflight._rest(REPOSITORY, "rules/branches/main")
    rule_types = active_rule_types(rules)
    required_types = {
        "merge_queue",
        "required_signatures",
        "required_linear_history",
        "required_status_checks",
        "pull_request",
    }
    missing_types = sorted(required_types - rule_types)
    if missing_types:
        raise AdmissionError(f"active admission rules are missing: {missing_types}")
    required_checks = preflight._required_checks(rules)

    pr = preflight._rest(REPOSITORY, f"pulls/{TARGET.number}")
    if not isinstance(pr, dict):
        raise AdmissionError("pull-request response is not an object")
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    observed_head = str(head.get("sha") or "").lower()
    observed_base = str(base.get("sha") or "").lower()
    if pr.get("state") != "open" or pr.get("draft") is True:
        raise AdmissionError("PR #325 must be open and ready")
    if ((head.get("repo") or {}).get("full_name")) != REPOSITORY:
        raise AdmissionError("PR #325 is not a same-repository branch")
    if observed_head != TARGET.head_sha:
        raise AdmissionError(
            f"head moved: expected {TARGET.head_sha}; observed {observed_head}"
        )
    if observed_base != TARGET.base_sha:
        raise AdmissionError(
            f"base moved: expected {TARGET.base_sha}; observed {observed_base}"
        )
    if int(pr.get("commits") or 0) != 1:
        raise AdmissionError("PR #325 must contain one signed snapshot commit")
    if pr.get("mergeable") is not True:
        raise AdmissionError("PR #325 is not mergeable")

    commit = preflight._rest(REPOSITORY, f"commits/{TARGET.head_sha}")
    verification = ((commit.get("commit") or {}).get("verification") or {})
    if verification.get("verified") is not True:
        raise AdmissionError(f"signature is not verified: {verification}")
    parents = commit.get("parents") or []
    parent_shas = [
        str(item.get("sha") or "").lower()
        for item in parents
        if isinstance(item, dict)
    ]
    if parent_shas != [TARGET.base_sha]:
        raise AdmissionError(
            f"linear-history parent mismatch: expected {[TARGET.base_sha]}; "
            f"observed {parent_shas}"
        )

    graph = preflight._pr_graph(REPOSITORY, TARGET.number)
    if str(graph.get("headRefOid") or "").lower() != TARGET.head_sha:
        raise AdmissionError("GraphQL head moved")
    if str(graph.get("baseRefOid") or "").lower() != TARGET.base_sha:
        raise AdmissionError("GraphQL base moved")
    if graph.get("state") != "OPEN" or graph.get("isDraft") is True:
        raise AdmissionError("GraphQL PR state is not ready")
    if graph.get("mergeable") != "MERGEABLE":
        raise AdmissionError(f"GraphQL mergeability is {graph.get('mergeable')}")
    threads = (graph.get("reviewThreads") or {}).get("nodes") or []
    unresolved = sum(
        1
        for item in threads
        if isinstance(item, dict) and item.get("isResolved") is False
    )
    if unresolved:
        raise AdmissionError(f"PR #325 has {unresolved} unresolved review threads")

    required_evidence = validate_required_checks(TARGET.head_sha, required_checks)
    node_id = str(pr.get("node_id") or "")
    if not node_id:
        raise AdmissionError("PR #325 lacks a GraphQL node ID")
    return {
        "pull_request": TARGET.number,
        "pull_request_id": node_id,
        "head_sha": TARGET.head_sha,
        "base_sha": TARGET.base_sha,
        "rule_types": sorted(rule_types),
        "signature": {
            "verified": verification.get("verified"),
            "reason": verification.get("reason"),
            "verified_at": verification.get("verified_at"),
        },
        "parent_shas": parent_shas,
        "unresolved_threads": unresolved,
        "required_checks": required_evidence,
        "before": {
            "mergeable_state": pr.get("mergeable_state"),
            "graphql_merge_state": graph.get("mergeStateStatus"),
            "auto_merge_request": graph.get("autoMergeRequest"),
            "merge_queue_entry": graph.get("mergeQueueEntry"),
        },
    }


def queue_state() -> dict[str, Any]:
    graph = preflight._pr_graph(REPOSITORY, TARGET.number)
    return {
        "state": graph.get("state"),
        "head_ref_oid": graph.get("headRefOid"),
        "merge_state_status": graph.get("mergeStateStatus"),
        "merge_queue_entry": graph.get("mergeQueueEntry"),
    }


def main() -> int:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    candidates: list[dict[str, Any]] = []
    selected: str | None = None
    record: dict[str, Any] | None = None
    error: str | None = None

    try:
        present = [
            (name, os.environ.get(name) or "")
            for name in CANDIDATE_ENV_NAMES
            if os.environ.get(name)
        ]
        if not present:
            raise AdmissionError("no governed user-token secret is configured")

        for name, token in present:
            candidate: dict[str, Any] = {
                "secret_name": name,
                "present": True,
                "capability": capability_probe(token),
                "attempted_enqueue": False,
                "result": "not_attempted",
            }
            candidates.append(candidate)
            permission = candidate["capability"].get("viewer_permission")
            if permission not in ALLOWED_VIEWER_PERMISSIONS:
                candidate["result"] = "insufficient_repository_permission"
                continue
            try:
                with credential(token):
                    record = validate_target()
                    candidate["attempted_enqueue"] = True
                    current = preflight._pr_graph(REPOSITORY, TARGET.number)
                    if current.get("state") == "MERGED":
                        record["mutation"] = "already_merged"
                    elif current.get("mergeQueueEntry") is not None:
                        record["mutation"] = "already_enqueued"
                        record["mutation_entry"] = current.get("mergeQueueEntry")
                    else:
                        record["mutation"] = "enqueuePullRequest"
                        record["mutation_entry"] = enqueue._enqueue(
                            str(record["pull_request_id"]),
                            TARGET.head_sha,
                        )
                    record["after"] = enqueue._observe(
                        REPOSITORY,
                        TARGET.number,
                        TARGET.head_sha,
                    )
                after = record.get("after") or {}
                if after.get("state") != "MERGED" and after.get(
                    "merge_queue_entry"
                ) is None:
                    raise AdmissionError(f"PR #325 did not enter the queue: {after}")
                selected = name
                candidate["result"] = "enqueued_or_merged"
                candidate["observed_queue_state"] = queue_state()
                break
            except Exception as exc:  # noqa: BLE001
                candidate["result"] = "failed_closed"
                candidate["failure_type"] = type(exc).__name__
                candidate["failure_class"] = classify_error(exc)
                try:
                    with credential(token):
                        candidate["observed_queue_state"] = queue_state()
                except Exception:  # noqa: BLE001
                    candidate["observed_queue_state"] = "unavailable"

        if selected is None:
            raise AdmissionError(
                "no configured governed user token could enqueue exact PR #325"
            )
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        print(error, file=sys.stderr)
    finally:
        report = {
            "schema": REPORT_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generation": os.environ.get("GITHUB_SHA"),
            "repository": REPOSITORY,
            "status": "ENQUEUED_OR_MERGED" if error is None else "FAILED_CLOSED",
            "selected_secret_name": selected,
            "error": error,
            "candidates": candidates,
            "target": record,
            "boundaries": [
                "Secret values, lengths, hashes, prefixes, identities, headers, and token metadata are never recorded.",
                "All active required checks, integration binding, signature, one-commit linear history, exact head/base, and thread resolution are verified.",
                "Unrelated non-required check runs are not promoted into repository admission rules.",
                "enqueuePullRequest with expectedHeadOid and jump=false is the only merge-related mutation.",
                "No immediate merge, ruleset, protection, review, status, check conclusion, branch ref, or secret setting is changed.",
            ],
        }
        REPORT_PATH.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, sort_keys=True))

    return 0 if error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
