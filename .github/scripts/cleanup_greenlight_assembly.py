#!/usr/bin/env python3
"""Remove the temporary workflow-assembly branch and report any secret-pattern risk.

No matched value is ever logged or persisted.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

API = "https://api.github.com"
REPOSITORY = "szl-holdings/.github"
BRANCH = "ops/operational-greenlight-v2-main"
PR_TITLE = "ops(greenlight): install scheduled evidence-driven estate control plane"
ISSUE_TITLE = "[security-cleanup] operational greenlight assembly"
SECRET_PATTERNS = (
    re.compile(r"(?:ghp|github_pat|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}"),
    re.compile(r"hf_[A-Za-z0-9]{20,}"),
)


class CleanupError(RuntimeError):
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
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-greenlight-assembly-cleanup/1.0",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if allow_status and exc.code in allow_status:
            return None
        detail = exc.read().decode("utf-8", "replace")[:5000]
        raise CleanupError(f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}") from exc
    return json.loads(raw.decode("utf-8")) if raw else None


def find_pr(token: str) -> dict[str, Any] | None:
    for page in range(1, 6):
        rows = request(token, "GET", f"/repos/{REPOSITORY}/pulls?state=all&sort=updated&direction=desc&per_page=100&page={page}")
        if not isinstance(rows, list):
            raise CleanupError("pull list is malformed")
        for pr in rows:
            if str(pr.get("title") or "") == PR_TITLE and str((pr.get("head") or {}).get("ref") or "") == BRANCH:
                return pr
        if len(rows) < 100:
            break
    return None


def branch_tree(token: str) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote(BRANCH, safe="")
    ref = request(token, "GET", f"/repos/{REPOSITORY}/git/ref/heads/{encoded}", allow_status={404})
    if not isinstance(ref, dict):
        return []
    commit_sha = str(((ref.get("object") or {}).get("sha")) or "")
    commit = request(token, "GET", f"/repos/{REPOSITORY}/git/commits/{commit_sha}")
    tree_sha = str(((commit.get("tree") or {}).get("sha")) or "")
    tree = request(token, "GET", f"/repos/{REPOSITORY}/git/trees/{tree_sha}?recursive=1")
    return [item for item in tree.get("tree") or [] if isinstance(item, dict) and item.get("type") == "blob"]


def scan_without_disclosure(token: str) -> dict[str, Any]:
    suspicious: list[str] = []
    scanned = 0
    for item in branch_tree(token):
        path = str(item.get("path") or "")
        size = int(item.get("size") or 0)
        if not path or size <= 0 or size > 2 * 1024 * 1024:
            continue
        if not path.startswith((".github/workflows/", ".github/scripts/")):
            continue
        blob = request(token, "GET", f"/repos/{REPOSITORY}/git/blobs/{item.get('sha')}")
        if blob.get("encoding") != "base64":
            continue
        raw = base64.b64decode(str(blob.get("content") or ""))
        text = raw.decode("utf-8", "replace")
        scanned += 1
        # Literal workflow expressions are safe. Only token-shaped resolved values count.
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            suspicious.append(path)
    return {
        "files_scanned": scanned,
        "suspicious_file_paths": sorted(set(suspicious)),
        "credential_rotation_required": bool(suspicious),
    }


def issues(token: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for page in range(1, 11):
        rows = request(token, "GET", f"/repos/{REPOSITORY}/issues?state=all&sort=updated&direction=desc&per_page=100&page={page}")
        output.extend(row for row in rows if isinstance(row, dict))
        if len(rows) < 100:
            return output
    return output


def persist(token: str, report: dict[str, Any]) -> dict[str, Any]:
    body = (
        "<!-- szl-greenlight-assembly-security-cleanup -->\n"
        "# Operational greenlight assembly security cleanup\n\n"
        "No token value is included in this report.\n\n"
        "```json\n"
        + json.dumps(report, indent=2, sort_keys=True)
        + "\n```\n"
    )
    current = next(
        (issue for issue in issues(token) if not issue.get("pull_request") and str(issue.get("title") or "") == ISSUE_TITLE),
        None,
    )
    state = "open" if report.get("scan", {}).get("credential_rotation_required") else "closed"
    if current:
        issue = request(token, "PATCH", f"/repos/{REPOSITORY}/issues/{current['number']}", {"body": body, "state": state})
    else:
        issue = request(token, "POST", f"/repos/{REPOSITORY}/issues", {"title": ISSUE_TITLE, "body": body})
        if state == "closed":
            issue = request(token, "PATCH", f"/repos/{REPOSITORY}/issues/{issue['number']}", {"state": "closed"})
    return {"number": issue.get("number"), "url": issue.get("html_url"), "state": issue.get("state")}


def main() -> int:
    token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    if not token:
        raise SystemExit("SZL_GITHUB_TOKEN is not configured")
    report: dict[str, Any] = {
        "schema": "szl.greenlight-assembly-security-cleanup/v1",
        "generated_at": now(),
        "repository": REPOSITORY,
        "branch": BRANCH,
        "scan": {},
        "pull_request": None,
        "branch_deleted": False,
        "ok": False,
        "errors": [],
    }
    try:
        report["scan"] = scan_without_disclosure(token)
        pr = find_pr(token)
        if pr:
            report["pull_request"] = {
                "number": pr.get("number"),
                "url": pr.get("html_url"),
                "state_before": pr.get("state"),
                "merged": bool(pr.get("merged")),
            }
            if pr.get("merged"):
                report["errors"].append("Temporary assembly PR was already merged; default-branch history requires security review")
            elif pr.get("state") == "open":
                closed = request(token, "PATCH", f"/repos/{REPOSITORY}/pulls/{pr['number']}", {"state": "closed"})
                report["pull_request"]["state_after"] = closed.get("state")
        encoded = urllib.parse.quote(BRANCH, safe="")
        deleted = request(token, "DELETE", f"/repos/{REPOSITORY}/git/refs/heads/{encoded}", allow_status={404, 422})
        report["branch_deleted"] = True
        report["ok"] = not report["errors"] and not report["scan"].get("credential_rotation_required")
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
    report["durable_issue"] = persist(token, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["branch_deleted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
