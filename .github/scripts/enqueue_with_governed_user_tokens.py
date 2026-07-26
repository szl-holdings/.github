#!/usr/bin/env python3
"""Enqueue exact clean signed PRs using existing governed user-token secrets.

The qillqaq App correctly lacks ``merge_queues: write``. Two pre-existing
repository secrets are already governed for authenticated user operations:
``GH_NOTIFICATIONS_TOKEN`` and ``SZL_GITHUB_TOKEN``. This controller tests only
their capabilities, never exposes their values, and uses the first credential
that can pass the complete queue preflight and GitHub's exact
``enqueuePullRequest(expectedHeadOid=...)`` mutation.

The controller is idempotent: an existing queue entry or a completed merge is
accepted, so a credential that enqueues one target before failing cannot leave
the recovery in an ambiguous state.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import enqueue_exact_clean_pull_requests as enqueue
import request_exact_clean_merge_queue as preflight

REPORT_SCHEMA = "szl.governed-user-token-enqueue/v1"
CANDIDATE_ENV_NAMES = (
    "GH_NOTIFICATIONS_TOKEN",
    "SZL_GITHUB_TOKEN",
)
ALLOWED_VIEWER_PERMISSIONS = {"WRITE", "MAINTAIN", "ADMIN"}


class GovernedTokenError(RuntimeError):
    """Raised when no governed credential can complete the exact enqueue."""


@contextmanager
def _credential(token: str) -> Iterator[None]:
    previous = os.environ.get("GH_TOKEN")
    os.environ["GH_TOKEN"] = token
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("GH_TOKEN", None)
        else:
            os.environ["GH_TOKEN"] = previous


def _api_json(token: str, arguments: list[str]) -> tuple[bool, Any, str]:
    env = dict(os.environ)
    env["GH_TOKEN"] = token
    process = subprocess.run(
        ["gh", "api", *arguments],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    stdout = process.stdout.strip()
    try:
        payload: Any = json.loads(stdout) if stdout else None
    except json.JSONDecodeError:
        payload = None
    error = process.stderr.strip()[:1000]
    return process.returncode == 0, payload, error


def _capability_probe(
    token: str,
    repository: str,
) -> dict[str, Any]:
    user_ok, user_payload, user_error = _api_json(
        token,
        ["--method", "GET", "user"],
    )
    repo_ok, repo_payload, repo_error = _api_json(
        token,
        ["--method", "GET", f"repos/{repository}"],
    )
    permissions = (
        repo_payload.get("permissions")
        if repo_ok and isinstance(repo_payload, dict)
        else None
    )

    owner, name = repository.split("/", 1)
    query = """
    query($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) {
        viewerPermission
      }
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
    graph_payload: Any = None
    if process.stdout.strip():
        try:
            graph_payload = json.loads(process.stdout)
        except json.JSONDecodeError:
            graph_payload = None
    graph_errors = (
        graph_payload.get("errors")
        if isinstance(graph_payload, dict)
        else None
    )
    viewer_permission = None
    if process.returncode == 0 and isinstance(graph_payload, dict) and not graph_errors:
        viewer_permission = (
            ((graph_payload.get("data") or {}).get("repository") or {}).get(
                "viewerPermission"
            )
        )

    # Never return login, token metadata, headers, or response bodies. Only the
    # minimum capability decision is retained.
    return {
        "user_api_authenticated": user_ok,
        "repository_api_authenticated": repo_ok,
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
        "viewer_permission": viewer_permission,
        "graphql_authenticated": (
            process.returncode == 0 and not graph_errors
        ),
        "error_classes": {
            "user": "none" if user_ok else _classify_error(user_error),
            "repository": "none" if repo_ok else _classify_error(repo_error),
            "graphql": (
                "none"
                if process.returncode == 0 and not graph_errors
                else _classify_error(process.stderr)
            ),
        },
    }


def _classify_error(value: object) -> str:
    text = str(value or "").lower()
    if "401" in text or "bad credentials" in text:
        return "unauthenticated"
    if "403" in text or "resource not accessible" in text or "forbidden" in text:
        return "unauthorized"
    if "404" in text or "not found" in text:
        return "not_found_or_hidden"
    if not text:
        return "unspecified"
    return "other"


def _preflight_all(repository: str) -> list[dict[str, Any]]:
    rules = preflight._rest(repository, "rules/branches/main")
    required = preflight._required_checks(rules)
    return [
        preflight._validate_target(repository, target, required)
        for target in preflight.TARGETS
    ]


def _enqueue_all(
    repository: str,
    records: list[dict[str, Any]],
) -> None:
    for target, record in zip(preflight.TARGETS, records, strict=True):
        current = preflight._pr_graph(repository, target.number)
        existing = current.get("mergeQueueEntry")
        if existing is not None:
            record["mutation"] = "already_enqueued"
            record["mutation_entry"] = existing
        elif current.get("state") == "MERGED":
            record["mutation"] = "already_merged"
        else:
            pr = preflight._rest(repository, f"pulls/{target.number}")
            node_id = str((pr or {}).get("node_id") or "")
            if not node_id:
                raise GovernedTokenError(
                    f"PR #{target.number} has no GraphQL node ID"
                )
            record["mutation"] = "enqueuePullRequest"
            record["mutation_entry"] = enqueue._enqueue(
                node_id,
                target.head_sha,
            )

        after = enqueue._observe(repository, target.number, target.head_sha)
        record["after"] = after
        if after.get("state") != "MERGED" and after.get(
            "merge_queue_entry"
        ) is None:
            raise GovernedTokenError(
                f"PR #{target.number} did not enter the queue: {after}"
            )


def _queue_state(repository: str) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for target in preflight.TARGETS:
        graph = preflight._pr_graph(repository, target.number)
        state[str(target.number)] = {
            "state": graph.get("state"),
            "head_ref_oid": graph.get("headRefOid"),
            "merge_state_status": graph.get("mergeStateStatus"),
            "merge_queue_entry": graph.get("mergeQueueEntry"),
        }
    return state


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY")
    if repository != "szl-holdings/.github":
        raise GovernedTokenError(
            f"controller is locked to szl-holdings/.github, got {repository!r}"
        )

    report_path = Path(
        os.environ.get(
            "REPORT_PATH",
            "reports/governed-user-token-enqueue.json",
        )
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    candidates: list[dict[str, Any]] = []
    selected: str | None = None
    records: list[dict[str, Any]] = []
    error: str | None = None

    try:
        present = [
            (name, os.environ.get(name) or "")
            for name in CANDIDATE_ENV_NAMES
            if os.environ.get(name)
        ]
        if not present:
            raise GovernedTokenError(
                "neither governed user-token secret is configured"
            )

        for name, token in present:
            candidate: dict[str, Any] = {
                "secret_name": name,
                "present": True,
                "capability": _capability_probe(token, repository),
                "attempted_enqueue": False,
                "result": "not_attempted",
            }
            candidates.append(candidate)
            permission = candidate["capability"].get("viewer_permission")
            if permission not in ALLOWED_VIEWER_PERMISSIONS:
                candidate["result"] = "insufficient_repository_permission"
                continue

            try:
                with _credential(token):
                    # Complete both read-only preflights before any mutation.
                    trial_records = _preflight_all(repository)
                    candidate["attempted_enqueue"] = True
                    _enqueue_all(repository, trial_records)
                    observed = _queue_state(repository)
                selected = name
                records = trial_records
                candidate["result"] = "enqueued_or_merged"
                candidate["observed_queue_state"] = observed
                break
            except Exception as exc:  # noqa: BLE001
                candidate["result"] = "failed_closed"
                candidate["failure_type"] = type(exc).__name__
                candidate["failure_class"] = _classify_error(exc)
                # Do not retain exception text because provider errors can carry
                # identity or endpoint details. Queue state is safe and confirms
                # whether a partial, idempotent enqueue occurred.
                try:
                    with _credential(token):
                        candidate["observed_queue_state"] = _queue_state(
                            repository
                        )
                except Exception:  # noqa: BLE001
                    candidate["observed_queue_state"] = "unavailable"

        if selected is None:
            raise GovernedTokenError(
                "no configured governed user token could enqueue the exact heads"
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
            "selected_secret_name": selected,
            "error": error,
            "candidates": candidates,
            "targets": records,
            "boundaries": [
                "Secret values, lengths, hashes, prefixes, identities, headers, and token metadata are never recorded.",
                "Only GH_NOTIFICATIONS_TOKEN and SZL_GITHUB_TOKEN are considered.",
                "Every candidate must authenticate and hold WRITE, MAINTAIN, or ADMIN repository permission before exact preflight.",
                "enqueuePullRequest with expectedHeadOid and jump=false is the only merge-related mutation used.",
                "An existing queue entry or completed merge is accepted idempotently.",
                "No immediate merge, branch ref update, ruleset, protection, review, status, check conclusion, or secret setting is changed.",
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
    except GovernedTokenError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1)
