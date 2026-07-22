#!/usr/bin/env python3
"""Fail-closed exact-SHA merge wave for owner-authorized review bypasses.

The script never changes a protection rule and never approves a pull request.  It
preflights the whole manifest before merging anything.  Admin override is used
only when GitHub reports an otherwise mergeable pull request as BLOCKED with the
sole visible policy state REVIEW_REQUIRED.  Pending/failing checks, conflicts,
behind branches, change requests, and unresolved review threads always stop the
entire wave.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API = "https://api.github.com"
ALLOWED_CHECK_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
ALLOWED_STATUS_STATES = {"SUCCESS"}


class GateError(RuntimeError):
    pass


def _request(token: str, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        API + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-owner-authorized-merge-wave/1.0",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:2000]
        raise GateError(f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise GateError(f"GitHub API {method} {path} failed: {type(exc).__name__}: {exc}") from exc
    return json.loads(raw.decode("utf-8")) if raw else None


def _graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = _request(token, "POST", "/graphql", {"query": query, "variables": variables})
    errors = payload.get("errors") or []
    if errors:
        raise GateError(f"GraphQL returned errors: {errors}")
    return payload["data"]


PR_QUERY = r"""
query MergeWavePullRequest($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      state
      isDraft
      merged
      mergeable
      mergeStateStatus
      reviewDecision
      headRefOid
      baseRefName
      baseRefOid
      reviewThreads(first: 100) {
        nodes { isResolved }
        pageInfo { hasNextPage }
      }
      latestReviews(first: 100) {
        nodes { state author { login } }
        pageInfo { hasNextPage }
      }
      commits(last: 1) {
        nodes {
          commit {
            oid
            statusCheckRollup {
              state
              contexts(first: 100) {
                nodes {
                  __typename
                  ... on CheckRun {
                    name
                    status
                    conclusion
                    detailsUrl
                    app { slug }
                  }
                  ... on StatusContext {
                    context
                    state
                    targetUrl
                  }
                }
                pageInfo { hasNextPage }
              }
            }
          }
        }
      }
    }
  }
}
"""


def _check_context(context: dict[str, Any]) -> dict[str, Any]:
    kind = context.get("__typename")
    if kind == "CheckRun":
        name = context.get("name") or "<unnamed-check>"
        status = context.get("status")
        conclusion = context.get("conclusion")
        if status != "COMPLETED":
            raise GateError(f"check {name!r} is {status}, not COMPLETED")
        if conclusion not in ALLOWED_CHECK_CONCLUSIONS:
            raise GateError(f"check {name!r} concluded {conclusion}, not green/neutral/skipped")
        return {
            "type": kind,
            "name": name,
            "status": status,
            "conclusion": conclusion,
            "app": (context.get("app") or {}).get("slug"),
            "url": context.get("detailsUrl"),
        }
    if kind == "StatusContext":
        name = context.get("context") or "<unnamed-status>"
        state = context.get("state")
        if state not in ALLOWED_STATUS_STATES:
            raise GateError(f"legacy status {name!r} is {state}, not SUCCESS")
        return {"type": kind, "name": name, "state": state, "url": context.get("targetUrl")}
    raise GateError(f"unsupported status-check context type: {kind!r}")


def preflight_target(token: str, identity: str, target: dict[str, Any], base_branch: str) -> dict[str, Any]:
    repository = str(target["repository"])
    number = int(target["pull_request"])
    expected_head = str(target["expected_head_sha"])
    owner, name = repository.split("/", 1)

    encoded_identity = urllib.parse.quote(identity, safe="")
    permission = _request(
        token,
        "GET",
        f"/repos/{owner}/{name}/collaborators/{encoded_identity}/permission",
    ).get("permission")
    if permission != "admin":
        raise GateError(f"{identity} has repository permission {permission!r}, not admin, on {repository}")

    data = _graphql(
        token,
        PR_QUERY,
        {"owner": owner, "name": name, "number": number},
    )
    pr = ((data.get("repository") or {}).get("pullRequest"))
    if not pr:
        raise GateError(f"{repository}#{number} was not found")
    if pr.get("state") != "OPEN" or pr.get("merged"):
        raise GateError(f"{repository}#{number} is not an open unmerged pull request")
    if pr.get("isDraft"):
        raise GateError(f"{repository}#{number} is still a draft")
    if pr.get("headRefOid") != expected_head:
        raise GateError(
            f"{repository}#{number} head moved: expected {expected_head}, got {pr.get('headRefOid')}"
        )
    if pr.get("baseRefName") != base_branch:
        raise GateError(
            f"{repository}#{number} targets {pr.get('baseRefName')!r}, expected {base_branch!r}"
        )
    if pr.get("mergeable") != "MERGEABLE":
        raise GateError(f"{repository}#{number} mergeable={pr.get('mergeable')}")

    threads = pr.get("reviewThreads") or {}
    if (threads.get("pageInfo") or {}).get("hasNextPage"):
        raise GateError(f"{repository}#{number} has more than 100 review threads; refusing incomplete audit")
    unresolved = sum(not bool(node.get("isResolved")) for node in threads.get("nodes") or [])
    if unresolved:
        raise GateError(f"{repository}#{number} has {unresolved} unresolved review thread(s)")

    reviews = pr.get("latestReviews") or {}
    if (reviews.get("pageInfo") or {}).get("hasNextPage"):
        raise GateError(f"{repository}#{number} has more than 100 latest reviews; refusing incomplete audit")
    changes_requested = [
        (node.get("author") or {}).get("login") or "<unknown>"
        for node in reviews.get("nodes") or []
        if node.get("state") == "CHANGES_REQUESTED"
    ]
    if changes_requested:
        raise GateError(
            f"{repository}#{number} has active change requests from {', '.join(changes_requested)}"
        )

    commit_nodes = ((pr.get("commits") or {}).get("nodes") or [])
    if len(commit_nodes) != 1:
        raise GateError(f"{repository}#{number} did not expose exactly one latest commit node")
    commit = commit_nodes[0]["commit"]
    if commit.get("oid") != expected_head:
        raise GateError(f"{repository}#{number} status rollup is not anchored to the exact head")
    rollup = commit.get("statusCheckRollup")
    if not rollup:
        raise GateError(f"{repository}#{number} has no status-check rollup")
    contexts = rollup.get("contexts") or {}
    if (contexts.get("pageInfo") or {}).get("hasNextPage"):
        raise GateError(f"{repository}#{number} has more than 100 checks; refusing incomplete audit")
    context_nodes = contexts.get("nodes") or []
    if not context_nodes:
        raise GateError(f"{repository}#{number} has no check contexts")
    checked = [_check_context(context) for context in context_nodes]
    if rollup.get("state") != "SUCCESS":
        raise GateError(f"{repository}#{number} aggregate check state is {rollup.get('state')}, not SUCCESS")

    merge_state = pr.get("mergeStateStatus")
    review_decision = pr.get("reviewDecision")
    if merge_state == "CLEAN":
        use_admin = False
    elif merge_state == "BLOCKED" and review_decision == "REVIEW_REQUIRED":
        use_admin = True
    else:
        raise GateError(
            f"{repository}#{number} is not blocked solely by approval: "
            f"mergeStateStatus={merge_state}, reviewDecision={review_decision}"
        )

    return {
        "repository": repository,
        "pull_request": number,
        "expected_head_sha": expected_head,
        "base_sha": pr.get("baseRefOid"),
        "merge_method": target.get("merge_method", "squash"),
        "purpose": target.get("purpose", ""),
        "identity": identity,
        "permission": permission,
        "merge_state_status": merge_state,
        "review_decision": review_decision,
        "unresolved_review_threads": unresolved,
        "checks": checked,
        "admin_override_required": use_admin,
        "status": "verified",
    }


def merge_target(token: str, item: dict[str, Any]) -> dict[str, Any]:
    repository = item["repository"]
    number = str(item["pull_request"])
    expected_head = item["expected_head_sha"]
    method = item["merge_method"]
    method_flag = {"squash": "--squash", "merge": "--merge", "rebase": "--rebase"}.get(method)
    if method_flag is None:
        raise GateError(f"unsupported merge method {method!r}")
    command = [
        "gh", "pr", "merge", number,
        "--repo", repository,
        method_flag,
        "--match-head-commit", expected_head,
        "--delete-branch",
    ]
    if item["admin_override_required"]:
        command.append("--admin")
    environment = dict(os.environ)
    environment["GH_TOKEN"] = token
    result = subprocess.run(command, env=environment, text=True, capture_output=True, timeout=120)
    if result.returncode != 0:
        output = (result.stdout + "\n" + result.stderr).strip()[-3000:]
        raise GateError(f"gh merge failed for {repository}#{number}: {output}")
    owner, name = repository.split("/", 1)
    pr = _request(token, "GET", f"/repos/{owner}/{name}/pulls/{number}")
    if not pr.get("merged_at"):
        raise GateError(f"{repository}#{number} command returned success but GitHub reports it unmerged")
    return {
        **item,
        "status": "merged",
        "merged_at": pr.get("merged_at"),
        "merge_commit_sha": pr.get("merge_commit_sha"),
        "admin_override_used": bool(item["admin_override_required"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    if not token:
        raise GateError("SZL_GITHUB_TOKEN is not configured")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if manifest.get("schema") != "szl.owner-authorized-merge-wave/v1":
        raise GateError("unexpected manifest schema")
    targets = manifest.get("targets") or []
    if not targets:
        raise GateError("manifest contains no targets")

    identity_payload = _request(token, "GET", "/user")
    identity = identity_payload.get("login")
    if not identity:
        raise GateError("authenticated GitHub identity has no login")

    report: dict[str, Any] = {
        "schema": "szl.owner-authorized-merge-report/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execute": bool(args.execute),
        "identity": identity,
        "base_branch": manifest.get("base_branch", "main"),
        "targets": [],
        "errors": [],
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)

    try:
        verified = [
            preflight_target(token, identity, target, report["base_branch"])
            for target in targets
        ]
        report["targets"] = verified
        if args.execute:
            merged = []
            # Preflight has completed for the entire wave.  Re-run each target's
            # exact-head preflight immediately before its merge to close TOCTOU.
            for target in targets:
                current = preflight_target(token, identity, target, report["base_branch"])
                merged.append(merge_target(token, current))
            report["targets"] = merged
        report["ok"] = True
    except Exception as exc:
        report["ok"] = False
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        raise SystemExit(1)
