#!/usr/bin/env python3
"""Finalize source-native Adaptive Theatre v3 pull requests without bypasses.

The controller discovers only the exact generated rollout PRs, waits for their
own repository checks, verifies review state and unresolved threads, and uses
GitHub's ordinary merge endpoint. It never forces a merge, changes protection,
dismisses a review, edits a check, or substitutes source success for deployment.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

API = "https://api.github.com"
GRAPHQL = f"{API}/graphql"
ORG = "szl-holdings"
TITLE = "feat(frontend): adopt Adaptive Theatre v3"
HEAD_BRANCH = "design/adaptive-theatre-v3"
GOOD_CONCLUSIONS = {"success", "neutral", "skipped"}
BAD_CONCLUSIONS = {
    "failure",
    "timed_out",
    "action_required",
    "cancelled",
    "stale",
    "startup_failure",
}


class FinalizeError(RuntimeError):
    pass


def api_token() -> str:
    return (
        os.environ.get("ORG_ADMIN_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    ).strip()


def request_json(
    method: str,
    url: str,
    *,
    token: str,
    payload: Any | None = None,
    allow_404: bool = False,
) -> Any:
    body = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "SZL-Adaptive-Theatre-Finalizer/3.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        if allow_404 and exc.code == 404:
            return None
        text = exc.read().decode("utf-8", "replace")[:4000]
        raise FinalizeError(f"GitHub HTTP {exc.code}: {text}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise FinalizeError(f"GitHub request failed: {exc}") from exc


def search_generated_prs(token: str, *, state: str = "open") -> list[dict[str, Any]]:
    query = f'org:{ORG} is:pr is:{state} "{TITLE}" in:title'
    url = f"{API}/search/issues?" + urllib.parse.urlencode(
        {"q": query, "sort": "updated", "order": "desc", "per_page": 100}
    )
    items = request_json("GET", url, token=token).get("items") or []
    rows: list[dict[str, Any]] = []
    for item in items:
        repository_url = str(item.get("repository_url") or "")
        repo = repository_url.rsplit("/", 1)[-1]
        number = int(item["number"])
        pr = request_json("GET", f"{API}/repos/{ORG}/{repo}/pulls/{number}", token=token)
        if pr.get("title") != TITLE:
            continue
        if (pr.get("head") or {}).get("ref") != HEAD_BRANCH:
            continue
        if (pr.get("head") or {}).get("repo", {}).get("full_name") != f"{ORG}/{repo}":
            continue
        rows.append(pr)
    return rows


def list_check_runs(token: str, repo: str, sha: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        url = f"{API}/repos/{ORG}/{repo}/commits/{sha}/check-runs?per_page=100&page={page}"
        batch = request_json("GET", url, token=token).get("check_runs") or []
        rows.extend(batch)
        if len(batch) < 100:
            return rows
        page += 1


def list_statuses(token: str, repo: str, sha: str) -> list[dict[str, Any]]:
    value = request_json("GET", f"{API}/repos/{ORG}/{repo}/commits/{sha}/status", token=token)
    return value.get("statuses") or []


def latest_review_states(token: str, repo: str, number: int) -> dict[str, str]:
    reviews = request_json(
        "GET", f"{API}/repos/{ORG}/{repo}/pulls/{number}/reviews?per_page=100", token=token
    )
    latest: dict[str, tuple[int, str]] = {}
    for review in reviews:
        login = str((review.get("user") or {}).get("login") or "")
        state = str(review.get("state") or "").upper()
        review_id = int(review.get("id") or 0)
        if login and state in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            previous = latest.get(login)
            if previous is None or review_id >= previous[0]:
                latest[login] = (review_id, state)
    return {login: state for login, (_, state) in latest.items()}


def review_threads(token: str, repo: str, number: int) -> dict[str, Any]:
    query = """
    query($owner:String!, $name:String!, $number:Int!) {
      repository(owner:$owner, name:$name) {
        pullRequest(number:$number) {
          reviewThreads(first:100) {
            nodes { isResolved isOutdated }
            pageInfo { hasNextPage }
          }
        }
      }
    }
    """
    payload = {
        "query": query,
        "variables": {"owner": ORG, "name": repo, "number": number},
    }
    try:
        value = request_json("POST", GRAPHQL, token=token, payload=payload)
    except FinalizeError as exc:
        return {"available": False, "error": str(exc), "unresolved": None, "truncated": None}
    if value.get("errors"):
        return {
            "available": False,
            "error": json.dumps(value["errors"], sort_keys=True)[:2000],
            "unresolved": None,
            "truncated": None,
        }
    threads = (
        (((value.get("data") or {}).get("repository") or {}).get("pullRequest") or {})
        .get("reviewThreads")
        or {}
    )
    nodes = threads.get("nodes") or []
    unresolved = sum(1 for node in nodes if not node.get("isResolved") and not node.get("isOutdated"))
    return {
        "available": True,
        "unresolved": unresolved,
        "truncated": bool((threads.get("pageInfo") or {}).get("hasNextPage")),
    }


def repository_has_workflows(token: str, repo: str, ref: str) -> bool:
    encoded = urllib.parse.quote(ref, safe="")
    value = request_json(
        "GET",
        f"{API}/repos/{ORG}/{repo}/contents/.github/workflows?ref={encoded}",
        token=token,
        allow_404=True,
    )
    return isinstance(value, list) and bool(value)


def evaluate(token: str, pr: dict[str, Any]) -> dict[str, Any]:
    repo = str(((pr.get("base") or {}).get("repo") or {}).get("name") or "")
    number = int(pr["number"])
    head = str((pr.get("head") or {}).get("sha") or "")
    base_ref = str((pr.get("base") or {}).get("ref") or "main")
    checks = list_check_runs(token, repo, head)
    statuses = list_statuses(token, repo, head)
    reviews = latest_review_states(token, repo, number)
    threads = review_threads(token, repo, number)
    workflows = repository_has_workflows(token, repo, head)

    pending_checks = [
        {"name": row.get("name"), "status": row.get("status"), "url": row.get("html_url")}
        for row in checks
        if row.get("status") != "completed" or not row.get("conclusion")
    ]
    failing_checks = [
        {"name": row.get("name"), "conclusion": row.get("conclusion"), "url": row.get("html_url")}
        for row in checks
        if row.get("conclusion") in BAD_CONCLUSIONS
    ]
    unknown_checks = [
        {"name": row.get("name"), "conclusion": row.get("conclusion"), "url": row.get("html_url")}
        for row in checks
        if row.get("status") == "completed"
        and row.get("conclusion")
        and row.get("conclusion") not in GOOD_CONCLUSIONS | BAD_CONCLUSIONS
    ]
    pending_statuses = [
        {"context": row.get("context"), "state": row.get("state"), "url": row.get("target_url")}
        for row in statuses
        if row.get("state") == "pending"
    ]
    failing_statuses = [
        {"context": row.get("context"), "state": row.get("state"), "url": row.get("target_url")}
        for row in statuses
        if row.get("state") in {"failure", "error"}
    ]
    change_requests = sorted(login for login, state in reviews.items() if state == "CHANGES_REQUESTED")

    reason = "READY"
    if pr.get("draft"):
        reason = "DRAFT"
    elif pr.get("mergeable") is False or pr.get("mergeable_state") == "dirty":
        reason = "CONFLICT"
    elif pending_checks or pending_statuses or pr.get("mergeable") is None:
        reason = "PENDING"
    elif failing_checks or failing_statuses or unknown_checks:
        reason = "CHECKS_FAILED"
    elif workflows and not checks and not statuses:
        reason = "CHECKS_NOT_STARTED"
    elif change_requests:
        reason = "CHANGES_REQUESTED"
    elif not threads.get("available"):
        reason = "THREAD_STATE_UNAVAILABLE"
    elif threads.get("truncated"):
        reason = "THREAD_STATE_TRUNCATED"
    elif int(threads.get("unresolved") or 0) > 0:
        reason = "UNRESOLVED_THREADS"
    elif pr.get("mergeable_state") not in {"clean", "has_hooks", "unstable"}:
        reason = f"MERGEABLE_{str(pr.get('mergeable_state') or 'unknown').upper()}"

    return {
        "repository": f"{ORG}/{repo}",
        "number": number,
        "url": pr.get("html_url"),
        "head_sha": head,
        "base_ref": base_ref,
        "draft": bool(pr.get("draft")),
        "mergeable": pr.get("mergeable"),
        "mergeable_state": pr.get("mergeable_state"),
        "workflows_present": workflows,
        "checks_total": len(checks),
        "statuses_total": len(statuses),
        "pending_checks": pending_checks,
        "failing_checks": failing_checks,
        "unknown_checks": unknown_checks,
        "pending_statuses": pending_statuses,
        "failing_statuses": failing_statuses,
        "latest_reviews": reviews,
        "changes_requested_by": change_requests,
        "review_threads": threads,
        "reason": reason,
    }


def preferred_merge_method(token: str, repo: str) -> str:
    metadata = request_json("GET", f"{API}/repos/{ORG}/{repo}", token=token)
    if metadata.get("allow_squash_merge"):
        return "squash"
    if metadata.get("allow_rebase_merge"):
        return "rebase"
    if metadata.get("allow_merge_commit"):
        return "merge"
    raise FinalizeError(f"No supported pull-request merge method is enabled for {ORG}/{repo}")


def merge_ready(token: str, row: dict[str, Any]) -> dict[str, Any]:
    repo = row["repository"].split("/", 1)[1]
    method = preferred_merge_method(token, repo)
    payload = {
        "sha": row["head_sha"],
        "merge_method": method,
        "commit_title": f"feat(frontend): adopt Adaptive Theatre v3 (#{row['number']})",
        "commit_message": (
            "Adopt the shared mobile-to-theatre responsive geometry through the "
            "application's existing reviewed visual host while preserving its distinct "
            "identity, product behavior, and truth contracts.\n\n"
            "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
        ),
    }
    value = request_json(
        "PUT",
        f"{API}/repos/{ORG}/{repo}/pulls/{row['number']}/merge",
        token=token,
        payload=payload,
    )
    if value.get("merged") is not True:
        raise FinalizeError(
            f"GitHub did not merge {row['repository']}#{row['number']}: "
            + json.dumps(value, sort_keys=True)[:2000]
        )
    return {
        "repository": row["repository"],
        "number": row["number"],
        "url": row["url"],
        "method": method,
        "merge_commit_sha": value.get("sha"),
        "message": value.get("message"),
    }


def workflow_runs_for_sha(token: str, repo: str, sha: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"head_sha": sha, "per_page": 100})
    value = request_json("GET", f"{API}/repos/{ORG}/{repo}/actions/runs?{query}", token=token)
    return value.get("workflow_runs") or []


def observe_publishers(token: str, merged: list[dict[str, Any]], wait_seconds: int, poll_seconds: int) -> list[dict[str, Any]]:
    deadline = time.monotonic() + max(0, wait_seconds)
    results: dict[str, dict[str, Any]] = {}
    while True:
        all_terminal = True
        for merge in merged:
            repo = merge["repository"].split("/", 1)[1]
            sha = str(merge.get("merge_commit_sha") or "")
            key = merge["repository"]
            runs = workflow_runs_for_sha(token, repo, sha) if sha else []
            rows = [
                {
                    "id": run.get("id"),
                    "name": run.get("name"),
                    "path": run.get("path"),
                    "status": run.get("status"),
                    "conclusion": run.get("conclusion"),
                    "url": run.get("html_url"),
                }
                for run in runs
            ]
            pending = [row for row in rows if row["status"] != "completed"]
            failing = [row for row in rows if row.get("conclusion") in BAD_CONCLUSIONS]
            results[key] = {
                "repository": key,
                "merge_commit_sha": sha,
                "runs": rows,
                "runs_observed": len(rows),
                "pending": pending,
                "failing": failing,
                "state": "PENDING" if pending else ("FAILED" if failing else ("COMPLETE" if rows else "NO_RUNS_OBSERVED")),
            }
            if pending:
                all_terminal = False
        if all_terminal or time.monotonic() >= deadline:
            return [results[key] for key in sorted(results)]
        time.sleep(max(1, poll_seconds))


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=1800)
    parser.add_argument("--publisher-wait-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    token = api_token()
    report: dict[str, Any] = {
        "schema": "szl.hf-adaptive-theatre-finalizer/v3",
        "apply": args.apply,
        "token_recorded": False,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "evaluations": [],
        "merged": [],
        "publishers": [],
        "status": "BLOCKED",
    }
    if not token:
        report.update(status="UNAVAILABLE", error="No supported cross-repository GitHub token is configured.")
        write_report(args.report, report)
        return 2

    deadline = time.monotonic() + max(0, args.wait_seconds)
    final_rows: list[dict[str, Any]] = []
    while True:
        prs = search_generated_prs(token)
        final_rows = [evaluate(token, pr) for pr in prs]
        report["evaluations"] = final_rows
        write_report(args.report, report)
        pending = [row for row in final_rows if row["reason"] in {"PENDING", "CHECKS_NOT_STARTED", "MERGEABLE_UNKNOWN"}]
        if not pending or time.monotonic() >= deadline:
            break
        time.sleep(max(1, args.poll_seconds))

    ready = [row for row in final_rows if row["reason"] == "READY"]
    if args.apply:
        for row in ready:
            try:
                report["merged"].append(merge_ready(token, row))
            except FinalizeError as exc:
                failed = dict(row)
                failed["reason"] = "MERGE_FAILED"
                failed["error"] = str(exc)
                report.setdefault("merge_failures", []).append(failed)
            write_report(args.report, report)

    residual = [row for row in final_rows if row["reason"] != "READY"]
    report["residual"] = residual
    if report["merged"]:
        report["publishers"] = observe_publishers(
            token,
            report["merged"],
            wait_seconds=args.publisher_wait_seconds,
            poll_seconds=args.poll_seconds,
        )

    publisher_failures = [row for row in report["publishers"] if row["state"] in {"FAILED", "PENDING"}]
    merge_failures = report.get("merge_failures") or []
    if merge_failures or publisher_failures:
        report["status"] = "FAILED"
    elif residual:
        report["status"] = "PARTIAL"
    else:
        report["status"] = "COMPLETE"
    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report["summary"] = {
        "discovered": len(final_rows),
        "ready": len(ready),
        "merged": len(report["merged"]),
        "residual": len(residual),
        "merge_failures": len(merge_failures),
        "publisher_failures_or_pending": len(publisher_failures),
    }
    write_report(args.report, report)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 1 if report["status"] == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
