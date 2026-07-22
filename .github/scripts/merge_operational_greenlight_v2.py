#!/usr/bin/env python3
"""Merge the clean scheduled operational-greenlight v2 control plane after exact proof."""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API = "https://api.github.com"
REPOSITORY = "szl-holdings/.github"
HEAD_BRANCH = "ops/operational-greenlight-v2-main"
TITLE = "ops(greenlight): install scheduled evidence-driven estate control plane"
EXPECTED_PATHS = {
    ".github/scripts/operational_greenlight_v2.py",
    ".github/scripts/hf_estate_greenlight_final.py",
    ".github/scripts/discover_replit_receipt.py",
    ".github/scripts/hf_domain_receipt_publish.py",
    ".github/workflows/operational-greenlight-v2-main.yml",
    ".github/workflows/hf-estate-greenlight-final-main.yml",
    ".github/workflows/discover-replit-receipt-main.yml",
    ".github/workflows/hf-domain-receipt-publish-main.yml",
}
ALLOWED = {"success", "neutral", "skipped"}


class GateError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request(token: str, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-merge-operational-greenlight-v2/1.0",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:7000]
        raise GateError(f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}") from exc
    return json.loads(raw.decode("utf-8")) if raw else None


def find_pr(token: str) -> dict[str, Any]:
    for page in range(1, 6):
        pulls = request(token, "GET", f"/repos/{REPOSITORY}/pulls?state=open&sort=updated&direction=desc&per_page=100&page={page}")
        if not isinstance(pulls, list):
            raise GateError("pull request list is malformed")
        for pr in pulls:
            if str(pr.get("title") or "") == TITLE and str((pr.get("head") or {}).get("ref") or "") == HEAD_BRANCH:
                return pr
        if len(pulls) < 100:
            break
    raise GateError("clean operational-greenlight v2 pull request not found")


def get_pr(token: str, number: int) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for attempt in range(6):
        value = request(token, "GET", f"/repos/{REPOSITORY}/pulls/{number}")
        if value.get("mergeable") is not None:
            return value
        if attempt < 5:
            time.sleep(2)
    return value


def files(token: str, number: int, changed: int) -> list[str]:
    rows = request(token, "GET", f"/repos/{REPOSITORY}/pulls/{number}/files?per_page=100")
    if not isinstance(rows, list) or len(rows) != changed:
        raise GateError(f"file audit incomplete: expected {changed}, got {len(rows) if isinstance(rows, list) else 'non-list'}")
    observed = {str(row.get("filename") or "") for row in rows}
    if observed != EXPECTED_PATHS:
        raise GateError(f"scope drift: missing={sorted(EXPECTED_PATHS-observed)}; extra={sorted(observed-EXPECTED_PATHS)}")
    return sorted(observed)


def check_runs(token: str, sha: str) -> dict[str, Any]:
    payload = request(token, "GET", f"/repos/{REPOSITORY}/commits/{sha}/check-runs?filter=latest&per_page=100")
    if not isinstance(payload, dict) or not isinstance(payload.get("check_runs"), list):
        raise GateError("check-run payload is malformed")
    rows = payload["check_runs"]
    pending = False
    failures: list[str] = []
    contexts: list[dict[str, Any]] = []
    for run in rows:
        status = str(run.get("status") or "").lower()
        conclusion = str(run.get("conclusion") or "").lower()
        contexts.append({"name": run.get("name"), "status": status, "conclusion": conclusion, "url": run.get("html_url")})
        if status != "completed":
            pending = True
        elif conclusion not in ALLOWED:
            failures.append(f"{run.get('name')}: {conclusion or 'NONE'}")
    combined = request(token, "GET", f"/repos/{REPOSITORY}/commits/{sha}/status")
    latest: dict[str, dict[str, Any]] = {}
    for item in combined.get("statuses") or []:
        name = str(item.get("context") or "")
        if name and name not in latest:
            latest[name] = item
    for item in latest.values():
        state = str(item.get("state") or "").lower()
        contexts.append({"name": item.get("context"), "state": state, "url": item.get("target_url")})
        if state == "pending":
            pending = True
        elif state != "success":
            failures.append(f"{item.get('context')}: {state or 'NONE'}")
    if not contexts:
        pending = True
    return {"pending": pending, "failures": failures, "contexts": contexts}


def review_state(token: str, number: int) -> dict[str, Any]:
    query = """
    query ExactReview($owner:String!,$name:String!,$number:Int!){
      repository(owner:$owner,name:$name){pullRequest(number:$number){
        headRefOid mergeable mergeStateStatus reviewDecision
        reviewThreads(first:100){nodes{isResolved} pageInfo{hasNextPage}}
        latestReviews(first:100){nodes{state author{login}} pageInfo{hasNextPage}}
      }}
    }
    """
    payload = request(token, "POST", "/graphql", {"query": query, "variables": {"owner": "szl-holdings", "name": ".github", "number": number}})
    if payload.get("errors"):
        raise GateError(f"GraphQL errors: {payload['errors']}")
    value = (((payload.get("data") or {}).get("repository") or {}).get("pullRequest"))
    if not value:
        raise GateError("GraphQL PR state missing")
    for key in ("reviewThreads", "latestReviews"):
        if ((value.get(key) or {}).get("pageInfo") or {}).get("hasNextPage"):
            raise GateError(f"more than 100 {key}")
    unresolved = sum(not bool(node.get("isResolved")) for node in ((value.get("reviewThreads") or {}).get("nodes") or []))
    requested = [
        (node.get("author") or {}).get("login") or "<unknown>"
        for node in ((value.get("latestReviews") or {}).get("nodes") or [])
        if node.get("state") == "CHANGES_REQUESTED"
    ]
    blockers = []
    if unresolved:
        blockers.append(f"{unresolved} unresolved threads")
    if requested:
        blockers.append("changes requested by " + ", ".join(requested))
    if value.get("reviewDecision") == "REVIEW_REQUIRED":
        blockers.append("independent approving review required")
    return {**value, "blockers": blockers}


def run(token: str, timeout: int) -> dict[str, Any]:
    seed = find_pr(token)
    number = int(seed["number"])
    deadline = time.monotonic() + timeout
    updated: str | None = None
    while True:
        pr = get_pr(token, number)
        if pr.get("merged"):
            return {"ok": True, "status": "already-merged", "pull_request": number, "merge_sha": pr.get("merge_commit_sha")}
        if pr.get("state") != "open" or pr.get("draft"):
            raise GateError("PR is not an open non-draft")
        if str((pr.get("head") or {}).get("ref") or "") != HEAD_BRANCH or str((pr.get("head") or {}).get("repo", {}).get("full_name") or "") != REPOSITORY:
            raise GateError("head identity changed")
        if str((pr.get("base") or {}).get("ref") or "") != "main":
            raise GateError("base changed")
        exact_files = files(token, number, int(pr.get("changed_files") or 0))
        sha = str((pr.get("head") or {}).get("sha") or "")
        reviews = review_state(token, number)
        if reviews.get("headRefOid") != sha:
            raise GateError("REST/GraphQL head mismatch")
        if reviews["blockers"]:
            raise GateError("; ".join(reviews["blockers"]))
        checks = check_runs(token, sha)
        if checks["failures"]:
            raise GateError("failed checks: " + "; ".join(checks["failures"]))
        merge_state = str(pr.get("mergeable_state") or "").lower()
        if merge_state == "behind" and not checks["pending"]:
            if updated == sha:
                raise GateError("update-branch did not advance head")
            request(token, "PUT", f"/repos/{REPOSITORY}/pulls/{number}/update-branch", {"expected_head_sha": sha})
            updated = sha
            time.sleep(15)
            continue
        if (
            not checks["pending"]
            and pr.get("mergeable") is True
            and reviews.get("mergeable") == "MERGEABLE"
            and merge_state in {"clean", "has_hooks", "unstable"}
            and reviews.get("mergeStateStatus") in {"CLEAN", "HAS_HOOKS", "UNSTABLE"}
        ):
            final = get_pr(token, number)
            if str((final.get("head") or {}).get("sha") or "") != sha:
                raise GateError("head moved during final preflight")
            result = request(
                token,
                "PUT",
                f"/repos/{REPOSITORY}/pulls/{number}/merge",
                {
                    "sha": sha,
                    "merge_method": "squash",
                    "commit_title": f"{TITLE} (#{number})",
                    "commit_message": "Install the clean scheduled evidence-driven estate control plane.\n\nSigned-off-by: Stephen Lutar <stephenlutar2@gmail.com>",
                },
            )
            if not result.get("merged"):
                raise GateError(f"merge returned {result!r}")
            return {"ok": True, "status": "merged", "pull_request": number, "head_sha": sha, "merge_sha": result.get("sha"), "files": exact_files, "checks": checks["contexts"]}
        if pr.get("mergeable") is False or reviews.get("mergeable") == "CONFLICTING":
            raise GateError("merge conflict")
        if time.monotonic() >= deadline:
            raise GateError(f"timeout: pending={checks['pending']} mergeable_state={merge_state} GraphQL={reviews.get('mergeable')}/{reviews.get('mergeStateStatus')}")
        time.sleep(20)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=10800)
    args = parser.parse_args()
    token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    code = 0
    try:
        if not token:
            raise GateError("SZL_GITHUB_TOKEN is not configured")
        report = {"schema": "szl.merge-operational-greenlight-v2/v1", "generated_at": now(), **run(token, args.timeout)}
    except Exception as exc:  # noqa: BLE001
        report = {"schema": "szl.merge-operational-greenlight-v2/v1", "generated_at": now(), "ok": False, "errors": [f"{type(exc).__name__}: {exc}"]}
        code = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
