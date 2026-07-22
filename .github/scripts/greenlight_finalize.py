#!/usr/bin/env python3
"""Finish the exact protected SZL operational queue without weakening any gate."""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

API = "https://api.github.com"
API_VERSION = "2022-11-28"
ALLOWED_CONCLUSIONS = {"success", "neutral", "skipped"}

SOURCE_TARGETS = (
    {
        "repository": "szl-holdings/.github",
        "number": 244,
        "title": "fix(hf): finish official API estate publisher v3",
        "branch": "hf/estate-official-api-v3-final-20260722",
        "paths": {
            ".github/scripts/hf_estate_official_api_v3.py",
            ".github/scripts/test_hf_estate_official_api_v3.py",
            ".github/workflows/hf-estate-official-api-v3.yml",
        },
    },
    {
        "repository": "szl-holdings/.github",
        "number": 246,
        "title": "ops(brain): merge A11oy #1003 only after exact-scope proof",
        "branch": "ops/merge-brain-1003-exact-scope",
        "paths": {
            ".github/scripts/merge_brain_pr_1003.py",
            ".github/workflows/merge-brain-pr-1003.yml",
        },
    },
    {
        "repository": "szl-holdings/.github",
        "number": 247,
        "title": "ops(pr): install fail-closed organization-wide final sweep",
        "branch": "ops/org-pr-final-sweep-v1",
        "paths": {
            ".github/scripts/org_pr_final_sweep.py",
            ".github/scripts/test_org_pr_final_sweep.py",
            ".github/workflows/org-pr-final-sweep.yml",
        },
    },
    {
        "repository": "szl-holdings/.github",
        "number": 248,
        "title": "feat(ops): publish final estate reconciliation and showcase",
        "branch": "ops/final-estate-reconciliation-v1",
        "paths": {
            ".github/scripts/final_estate_reconciliation.py",
            ".github/scripts/test_final_estate_reconciliation.py",
            ".github/workflows/final-estate-reconciliation.yml",
        },
    },
    {
        "repository": "szl-holdings/a11oy",
        "number": 1035,
        "title": "docs(evidence): refresh independent state-plane continuity",
        "branch": "audit/state-plane-continuity-v2-20260722",
        "paths": {
            "scripts/collect_state_plane_evidence_v2.py",
            "docs/STATE_PLANE_CONTINUITY_V2.md",
            "docs/state-plane-continuity.v2.json",
            "tests/test_state_plane_continuity_v2.py",
            ".github/workflows/state-plane-continuity-v2.yml",
        },
    },
    {
        "repository": "szl-holdings/a11oy",
        "number": 1036,
        "title": "feat(nemo): preregister governed v3 curriculum and challenge set",
        "branch": "agent/nemo-v3-preregistered-curriculum-20260722",
        "paths": {
            "execution/models/szl-nemo-v3/candidate_policy.json",
            "execution/models/szl-nemo-v3/README.md",
            "execution/models/szl-nemo-v3/curriculum.jsonl",
            "execution/models/szl-nemo-v3/challenge_set.jsonl",
            "execution/models/szl-nemo-v3/v2_holdout_binding.json",
            "scripts/bind_nemo_v3_holdouts.py",
            "scripts/validate_nemo_v3_preparation.py",
            "tests/test_nemo_v3_preparation.py",
            ".github/workflows/nemo-v3-preregister.yml",
        },
    },
)

DEPENDENCY_WORKFLOWS = (
    ("szl-holdings/.github", "hf-estate-official-api-v3.yml", {"publish": "true"}, 110 * 60),
    ("szl-holdings/.github", "merge-brain-pr-1003.yml", {"execute": "true"}, 150 * 60),
    ("szl-holdings/a11oy", "state-plane-continuity-v2.yml", {}, 35 * 60),
    ("szl-holdings/a11oy", "nemo-v3-preregister.yml", {}, 35 * 60),
)
ORG_SWEEP = ("szl-holdings/.github", "org-pr-final-sweep.yml", {"execute": "true"}, 250 * 60)
FINAL_RECONCILIATION = ("szl-holdings/.github", "final-estate-reconciliation.yml", {}, 140 * 60)


class GateError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request(
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    allow_status: set[int] | None = None,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "szl-greenlight-finalizer/1.0",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if allow_status and exc.code in allow_status:
            return None
        detail = exc.read().decode("utf-8", "replace")[:6000]
        raise GateError(f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise GateError(f"GitHub API {method} {path} failed: {type(exc).__name__}: {exc}") from exc
    return json.loads(raw.decode("utf-8")) if raw else None


def graphql(token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = request(token, "POST", "/graphql", {"query": query, "variables": variables})
    errors = payload.get("errors") or []
    if errors:
        raise GateError(f"GraphQL errors: {errors}")
    return payload["data"]


def paginate(token: str, path: str, *, max_pages: int = 50) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    separator = "&" if "?" in path else "?"
    for page in range(1, max_pages + 1):
        payload = request(token, "GET", f"{path}{separator}per_page=100&page={page}")
        if not isinstance(payload, list):
            raise GateError(f"paginated payload is not a list for {path}")
        output.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return output
    raise GateError(f"pagination exceeded {max_pages} pages for {path}")


REVIEW_QUERY = r"""
query GreenlightReview($owner: String!, $name: String!, $number: Int!) {
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
      reviewThreads(first: 100) {
        nodes { isResolved }
        pageInfo { hasNextPage }
      }
      latestReviews(first: 100) {
        nodes { state author { login } }
        pageInfo { hasNextPage }
      }
    }
  }
}
"""


def review_state(token: str, repository: str, number: int) -> dict[str, Any]:
    owner, name = repository.split("/", 1)
    data = graphql(token, REVIEW_QUERY, {"owner": owner, "name": name, "number": number})
    value = ((data.get("repository") or {}).get("pullRequest"))
    if not value:
        raise GateError(f"{repository}#{number} not found")
    for key in ("reviewThreads", "latestReviews"):
        if ((value.get(key) or {}).get("pageInfo") or {}).get("hasNextPage"):
            raise GateError(f"{repository}#{number} has more than 100 {key}")
    return value


def review_blockers(value: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    unresolved = sum(
        not bool(node.get("isResolved"))
        for node in ((value.get("reviewThreads") or {}).get("nodes") or [])
    )
    if unresolved:
        blockers.append(f"{unresolved} unresolved review thread(s)")
    requested = [
        (node.get("author") or {}).get("login") or "<unknown>"
        for node in ((value.get("latestReviews") or {}).get("nodes") or [])
        if node.get("state") == "CHANGES_REQUESTED"
    ]
    if requested:
        blockers.append("active change requests from " + ", ".join(requested))
    if value.get("reviewDecision") == "REVIEW_REQUIRED":
        blockers.append("independent approving review is required")
    return blockers


def list_check_runs(token: str, repository: str, sha: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for page in range(1, 101):
        payload = request(
            token,
            "GET",
            f"/repos/{repository}/commits/{sha}/check-runs?filter=latest&per_page=100&page={page}",
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("check_runs"), list):
            raise GateError(f"malformed check-run payload for {repository}@{sha}")
        rows = [item for item in payload["check_runs"] if isinstance(item, dict)]
        output.extend(rows)
        if len(rows) < 100:
            return output
    raise GateError(f"too many check runs for {repository}@{sha}")


def checks(token: str, repository: str, sha: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    pending = False
    for run in list_check_runs(token, repository, sha):
        status = str(run.get("status") or "").lower()
        conclusion = str(run.get("conclusion") or "").lower()
        rows.append({
            "type": "check_run",
            "name": run.get("name"),
            "status": status,
            "conclusion": conclusion,
            "url": run.get("html_url") or run.get("details_url"),
        })
        if status != "completed":
            pending = True
        elif conclusion not in ALLOWED_CONCLUSIONS:
            failures.append(f"check {run.get('name')!r} concluded {conclusion or 'NONE'}")
    combined = request(token, "GET", f"/repos/{repository}/commits/{sha}/status")
    if not isinstance(combined, dict):
        raise GateError(f"malformed combined status for {repository}@{sha}")
    latest: dict[str, dict[str, Any]] = {}
    for item in combined.get("statuses") or []:
        context = str(item.get("context") or "")
        if context and context not in latest:
            latest[context] = item
    for item in latest.values():
        state = str(item.get("state") or "").lower()
        rows.append({
            "type": "status_context",
            "name": item.get("context"),
            "state": state,
            "url": item.get("target_url"),
        })
        if state == "pending":
            pending = True
        elif state != "success":
            failures.append(f"status {item.get('context')!r} is {state or 'NONE'}")
    if not rows:
        pending = True
    return {"pending": pending, "failures": failures, "contexts": rows}


def get_pr(token: str, repository: str, number: int, *, attempts: int = 6) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for attempt in range(attempts):
        payload = request(token, "GET", f"/repos/{repository}/pulls/{number}")
        if not isinstance(payload, dict):
            raise GateError(f"{repository}#{number} returned a non-object")
        value = payload
        if value.get("mergeable") is not None or value.get("merged"):
            return value
        if attempt + 1 < attempts:
            time.sleep(2)
    return value


def exact_paths(token: str, target: dict[str, Any], pr: dict[str, Any]) -> list[str]:
    changed = int(pr.get("changed_files") or 0)
    if changed <= 0 or changed > 100:
        raise GateError(f"{target['repository']}#{target['number']} changed_files={changed}")
    files = paginate(token, f"/repos/{target['repository']}/pulls/{target['number']}/files", max_pages=2)
    observed = {str(item.get("filename") or "") for item in files}
    if len(files) != changed:
        raise GateError(f"incomplete file audit: {len(files)} != {changed}")
    unexpected = observed - set(target["paths"])
    if unexpected:
        raise GateError(f"scope drift: unexpected files {sorted(unexpected)}")
    return sorted(observed)


def verify_identity(target: dict[str, Any], pr: dict[str, Any]) -> None:
    if str(pr.get("title") or "") != target["title"]:
        raise GateError(f"{target['repository']}#{target['number']} title changed")
    if pr.get("draft"):
        raise GateError(f"{target['repository']}#{target['number']} is draft")
    if (pr.get("base") or {}).get("ref") != "main":
        raise GateError(f"{target['repository']}#{target['number']} does not target main")
    head = pr.get("head") or {}
    if head.get("ref") != target["branch"]:
        raise GateError(f"{target['repository']}#{target['number']} head branch changed")
    if (head.get("repo") or {}).get("full_name") != target["repository"]:
        raise GateError(f"{target['repository']}#{target['number']} uses a fork head")


def merge_source(token: str, target: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    repository = target["repository"]
    number = int(target["number"])
    current = get_pr(token, repository, number)
    if current.get("merged"):
        return {
            "repository": repository,
            "pull_request": number,
            "status": "already-merged",
            "merge_sha": current.get("merge_commit_sha"),
            "merged_at": current.get("merged_at"),
            "ok": True,
        }
    if current.get("state") != "open":
        raise GateError(f"{repository}#{number} is closed without merge")

    deadline = time.monotonic() + timeout_seconds
    updated_sha: str | None = None
    while True:
        current = get_pr(token, repository, number)
        verify_identity(target, current)
        paths = exact_paths(token, target, current)
        head_sha = str((current.get("head") or {}).get("sha") or "")
        if len(head_sha) != 40:
            raise GateError(f"invalid head SHA {head_sha!r}")
        review = review_state(token, repository, number)
        if review.get("headRefOid") != head_sha:
            raise GateError("REST/GraphQL head mismatch")
        blockers = review_blockers(review)
        if blockers:
            raise GateError("; ".join(blockers))
        check_state = checks(token, repository, head_sha)
        if check_state["failures"]:
            raise GateError("; ".join(check_state["failures"]))
        rest_state = str(current.get("mergeable_state") or "").lower()
        if rest_state == "behind" and not check_state["pending"]:
            if updated_sha == head_sha:
                raise GateError("update-branch did not advance head")
            request(
                token,
                "PUT",
                f"/repos/{repository}/pulls/{number}/update-branch",
                {"expected_head_sha": head_sha},
            )
            updated_sha = head_sha
            time.sleep(15)
            continue
        ready = (
            not check_state["pending"]
            and current.get("mergeable") is True
            and review.get("mergeable") == "MERGEABLE"
            and rest_state in {"clean", "has_hooks", "unstable"}
            and review.get("mergeStateStatus") in {"CLEAN", "HAS_HOOKS", "UNSTABLE"}
        )
        if ready:
            final = get_pr(token, repository, number, attempts=1)
            if str((final.get("head") or {}).get("sha") or "") != head_sha:
                raise GateError("head moved during final preflight")
            verify_identity(target, final)
            exact_paths(token, target, final)
            final_review = review_state(token, repository, number)
            final_checks = checks(token, repository, head_sha)
            changed = review_blockers(final_review) + final_checks["failures"]
            if final_checks["pending"]:
                changed.append("checks became pending")
            if changed:
                raise GateError("; ".join(changed))
            result = request(
                token,
                "PUT",
                f"/repos/{repository}/pulls/{number}/merge",
                {
                    "sha": head_sha,
                    "merge_method": "squash",
                    "commit_title": f"{target['title']} (#{number})",
                    "commit_message": (
                        "Merged after exact branch, scope, review, mergeability, and current-head check verification.\n\n"
                        "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
                    ),
                },
            )
            if not result.get("merged"):
                raise GateError(f"merge failed: {result!r}")
            return {
                "repository": repository,
                "pull_request": number,
                "status": "merged",
                "head_sha": head_sha,
                "merge_sha": result.get("sha"),
                "files": paths,
                "checks": check_state["contexts"],
                "ok": True,
            }
        if current.get("mergeable") is False or review.get("mergeable") == "CONFLICTING":
            raise GateError("GitHub reports conflicts")
        if time.monotonic() >= deadline:
            raise GateError(
                f"timeout: pending={check_state['pending']} REST={rest_state} "
                f"GraphQL={review.get('mergeable')}/{review.get('mergeStateStatus')}"
            )
        time.sleep(20)


def close_superseded(token: str, repository: str, stale: int, successor: int) -> dict[str, Any]:
    successor_pr = get_pr(token, repository, successor)
    if not successor_pr.get("merged"):
        return {"repository": repository, "pull_request": stale, "status": "successor-not-merged", "ok": False}
    stale_pr = get_pr(token, repository, stale)
    if stale_pr.get("merged"):
        return {"repository": repository, "pull_request": stale, "status": "unexpectedly-merged", "ok": False}
    if stale_pr.get("state") == "closed":
        return {"repository": repository, "pull_request": stale, "status": "already-closed", "ok": True}
    request(
        token,
        "POST",
        f"/repos/{repository}/issues/{stale}/comments",
        {
            "body": (
                f"Closing without merge because merged successor #{successor} replaces this historical/partial lane. "
                "No review, check, or protection gate was bypassed."
            )
        },
    )
    result = request(token, "PATCH", f"/repos/{repository}/pulls/{stale}", {"state": "closed"})
    return {
        "repository": repository,
        "pull_request": stale,
        "status": "closed" if result.get("state") == "closed" else "close-failed",
        "successor": successor,
        "ok": result.get("state") == "closed" and not result.get("merged"),
    }


def dispatch(token: str, spec: tuple[str, str, dict[str, str], int]) -> dict[str, Any]:
    repository, workflow, inputs, timeout_seconds = spec
    encoded = urllib.parse.quote(workflow, safe="")
    started = datetime.now(timezone.utc)
    payload: dict[str, Any] = {"ref": "main"}
    if inputs:
        payload["inputs"] = inputs
    request(token, "POST", f"/repos/{repository}/actions/workflows/{encoded}/dispatches", payload)
    return {
        "repository": repository,
        "workflow": workflow,
        "inputs": inputs,
        "started_at": started.isoformat(),
        "timeout_seconds": timeout_seconds,
    }


def parse_time(value: Any) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def wait_workflow(token: str, dispatch_record: dict[str, Any]) -> dict[str, Any]:
    repository = dispatch_record["repository"]
    workflow = dispatch_record["workflow"]
    encoded = urllib.parse.quote(workflow, safe="")
    started = parse_time(dispatch_record["started_at"]) - timedelta(seconds=10)
    deadline = time.monotonic() + int(dispatch_record["timeout_seconds"])
    selected: dict[str, Any] | None = None
    while True:
        payload = request(
            token,
            "GET",
            f"/repos/{repository}/actions/workflows/{encoded}/runs?branch=main&event=workflow_dispatch&per_page=30",
            allow_status={404},
        )
        runs = payload.get("workflow_runs") if isinstance(payload, dict) else []
        candidates = [
            run for run in runs or []
            if parse_time(run.get("created_at")) >= started
        ]
        if candidates:
            candidates.sort(key=lambda run: parse_time(run.get("created_at")), reverse=True)
            selected = candidates[0]
            if selected.get("status") == "completed":
                result = {
                    "repository": repository,
                    "workflow": workflow,
                    "run_id": selected.get("id"),
                    "url": selected.get("html_url"),
                    "head_sha": selected.get("head_sha"),
                    "event": selected.get("event"),
                    "status": selected.get("status"),
                    "conclusion": selected.get("conclusion"),
                    "created_at": selected.get("created_at"),
                    "updated_at": selected.get("updated_at"),
                    "ok": selected.get("conclusion") == "success",
                }
                if not result["ok"]:
                    raise GateError(f"{repository}/{workflow} concluded {result['conclusion']}; {result['url']}")
                return result
        if time.monotonic() >= deadline:
            raise GateError(f"timeout waiting for {repository}/{workflow}; latest={selected}")
        time.sleep(20)


def upsert_issue(token: str, title: str, body: str) -> dict[str, Any]:
    issues = paginate(token, "/repos/szl-holdings/.github/issues?state=all&sort=updated&direction=desc", max_pages=10)
    current = next(
        (issue for issue in issues if not issue.get("pull_request") and str(issue.get("title") or "") == title),
        None,
    )
    if current:
        issue = request(
            token,
            "PATCH",
            f"/repos/szl-holdings/.github/issues/{current['number']}",
            {"body": body, "state": "open"},
        )
    else:
        issue = request(
            token,
            "POST",
            "/repos/szl-holdings/.github/issues",
            {"title": title, "body": body},
        )
    return {"number": issue.get("number"), "url": issue.get("html_url"), "state": issue.get("state")}


def run(token: str, source_timeout: int) -> dict[str, Any]:
    identity = request(token, "GET", "/user")
    report: dict[str, Any] = {
        "schema": "szl.greenlight-finalizer/v1",
        "generated_at": now(),
        "identity": identity.get("login"),
        "source_targets": [],
        "superseded": [],
        "dependency_workflows": [],
        "organization_sweep": None,
        "final_reconciliation": None,
        "ok": False,
        "errors": [],
    }

    for target in SOURCE_TARGETS:
        result = merge_source(token, target, source_timeout)
        report["source_targets"].append(result)
        if not result.get("ok"):
            raise GateError(f"source target failed: {result}")

    report["superseded"] = [
        close_superseded(token, "szl-holdings/.github", 243, 244),
        close_superseded(token, "szl-holdings/a11oy", 1004, 1035),
    ]
    if not all(item.get("ok") for item in report["superseded"]):
        raise GateError(f"superseded closure failed: {report['superseded']}")

    dependency_dispatches = [dispatch(token, spec) for spec in DEPENDENCY_WORKFLOWS]
    dependency_results = [wait_workflow(token, item) for item in dependency_dispatches]
    report["dependency_workflows"] = dependency_results

    sweep_dispatch = dispatch(token, ORG_SWEEP)
    report["organization_sweep"] = wait_workflow(token, sweep_dispatch)

    final_dispatch = dispatch(token, FINAL_RECONCILIATION)
    report["final_reconciliation"] = wait_workflow(token, final_dispatch)

    report["ok"] = True
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-timeout", type=int, default=10800)
    args = parser.parse_args()
    token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    report: dict[str, Any]
    code = 0
    try:
        if not token:
            raise GateError("SZL_GITHUB_TOKEN is not configured")
        report = run(token, args.source_timeout)
    except Exception as exc:  # noqa: BLE001
        report = locals().get("report") if isinstance(locals().get("report"), dict) else {
            "schema": "szl.greenlight-finalizer/v1",
            "generated_at": now(),
            "ok": False,
            "errors": [],
        }
        report["ok"] = False
        report.setdefault("errors", []).append(f"{type(exc).__name__}: {exc}")
        code = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report.get("ok"), "errors": report.get("errors")}, indent=2))

    token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    if token:
        try:
            body = (
                "<!-- szl-greenlight-finalizer -->\n"
                "# Operational green-light finalizer\n\n"
                f"Generated: `{report.get('generated_at')}`\n\n"
                "```json\n"
                + json.dumps(report, indent=2, sort_keys=True)
                + "\n```\n"
            )
            issue = upsert_issue(token, "[greenlight-finalizer] operational queue", body)
            report["durable_issue"] = issue
            args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            report.setdefault("errors", []).append(f"durable issue: {type(exc).__name__}: {exc}")
            report["ok"] = False
            args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
