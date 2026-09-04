#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reconcile stalled Codex/Perplexity work across SZL GitHub and Hugging Face.

The operator is deliberately conservative:
- it never bypasses branch protection, required reviews, DCO, or checks;
- it merges only the exact observed PR head after every reported check is terminal-green;
- it reruns failed jobs and recycles genuinely stale queued/in-progress runs;
- it creates PRs only for recent orphan branches carrying explicit agent provenance;
- it restarts stopped/failed Hugging Face Spaces only after an active org-write token is proven;
- it records secret-free evidence and never prints credential values.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping

ORG = "szl-holdings"
HF_ORG = "SZLHOLDINGS"
CENTRAL_REPO = ".github"
NOW = dt.datetime.now(dt.timezone.utc)
STALE_MINUTES = 45
RECENT_BRANCH_DAYS = 21
MAX_PASSES = 4
PASS_DELAY_SECONDS = 150
MAX_ORPHAN_PRS = 40
OK_CHECK_CONCLUSIONS = {"success", "neutral", "skipped"}
FAILED_RUN_CONCLUSIONS = {
    "failure",
    "cancelled",
    "timed_out",
    "action_required",
    "startup_failure",
    "stale",
}
HOLD_LABELS = {
    "do-not-merge",
    "hold",
    "blocked",
    "security-review",
    "needs-owner-approval",
    "manual-only",
}
AGENT_MARKERS = re.compile(
    r"(?:codex|perplexity|computer[- ]agent|copilot|agent[-_/]|half[-_/]?build|"
    r"stalled|finish[-_/]|repair[-_/]|reconcile[-_/])",
    re.IGNORECASE,
)
SAFE_BRANCH_PREFIXES = (
    "codex/",
    "perplexity/",
    "agent/",
    "agents/",
    "fix/",
    "feat/",
    "ops/",
    "chore/",
    "refactor/",
    "docs/",
)


class ApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, body: Any) -> None:
        self.method = method
        self.path = path
        self.status = status
        self.body = body
        super().__init__(f"{method} {path}: HTTP {status}")


@dataclasses.dataclass
class GitHubApi:
    token: str
    base: str = "https://api.github.com"

    def request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        *,
        accept: str = "application/vnd.github+json",
        allow: Iterable[int] = (200, 201, 202, 204),
        timeout: int = 45,
    ) -> Any:
        url = path if path.startswith("https://") else self.base + path
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": accept,
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "szl-estate-reconciler/1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                if response.status not in set(allow):
                    raise ApiError(method, path, response.status, raw[:500].decode("utf-8", "replace"))
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                body: Any = json.loads(raw)
            except json.JSONDecodeError:
                body = raw[:1000]
            raise ApiError(method, path, exc.code, body) from exc

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, payload: Any | None = None, **kwargs: Any) -> Any:
        return self.request("POST", path, payload, **kwargs)

    def put(self, path: str, payload: Any | None = None, **kwargs: Any) -> Any:
        return self.request("PUT", path, payload, **kwargs)

    def patch(self, path: str, payload: Any | None = None, **kwargs: Any) -> Any:
        return self.request("PATCH", path, payload, **kwargs)

    def paginate(self, path: str, *, limit_pages: int = 20) -> list[Any]:
        separator = "&" if "?" in path else "?"
        items: list[Any] = []
        for page in range(1, limit_pages + 1):
            payload = self.get(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(payload, list):
                raise RuntimeError(f"pagination endpoint did not return a list: {path}")
            items.extend(payload)
            if len(payload) < 100:
                break
        return items


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def age_minutes(value: str | None) -> float | None:
    parsed = parse_time(value)
    if parsed is None:
        return None
    return (dt.datetime.now(dt.timezone.utc) - parsed).total_seconds() / 60.0


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def safe_error(exc: Exception) -> dict[str, Any]:
    row: dict[str, Any] = {"type": type(exc).__name__, "message": str(exc)[:500]}
    if isinstance(exc, ApiError):
        row.update({"status": exc.status, "method": exc.method, "path": exc.path})
        if isinstance(exc.body, Mapping):
            row["provider_message"] = str(exc.body.get("message") or "")[:300]
    return row


def select_github_token() -> tuple[GitHubApi | None, dict[str, Any]]:
    aliases = (
        "GH_ORG_ADMIN_TOKEN",
        "ORG_ADMIN_TOKEN",
        "GH_ADMIN_TOKEN",
        "SZL_GITHUB_TOKEN",
        "GITHUB_PAT",
        "GH_PAT",
        "GH_TOKEN_SECRET",
        "REPOSITORY_TOKEN",
    )
    attempts: list[dict[str, Any]] = []
    for alias in aliases:
        token = os.getenv(alias, "").strip()
        if not token:
            continue
        print(f"::add-mask::{token}")
        api = GitHubApi(token)
        try:
            user = api.get("/user")
            repo = api.get(f"/repos/{ORG}/{CENTRAL_REPO}")
            permissions = repo.get("permissions") or {}
            has_write = bool(permissions.get("push") or permissions.get("maintain") or permissions.get("admin"))
            attempts.append(
                {
                    "alias": alias,
                    "identity": user.get("login"),
                    "active": True,
                    "central_write": has_write,
                    "admin": bool(permissions.get("admin")),
                }
            )
            if has_write:
                return api, {
                    "state": "ACTIVE_WRITE_AUTHORITY",
                    "alias": alias,
                    "identity": user.get("login"),
                    "admin": bool(permissions.get("admin")),
                    "attempts": attempts,
                }
        except Exception as exc:
            attempts.append({"alias": alias, "active": False, "error": safe_error(exc)})
    return None, {"state": "UNAVAILABLE", "attempts": attempts}


def repository_inventory(api: GitHubApi) -> list[dict[str, Any]]:
    repos = api.paginate(f"/orgs/{ORG}/repos?type=all&sort=updated&direction=desc")
    return [repo for repo in repos if not repo.get("archived") and not repo.get("disabled")]


def protection_summary(api: GitHubApi, repo: str, branch: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(branch, safe="")
    try:
        value = api.get(f"/repos/{ORG}/{repo}/branches/{encoded}/protection")
    except ApiError as exc:
        if exc.status == 404:
            return {"observed": True, "protected": False}
        return {"observed": False, "error": safe_error(exc)}
    reviews = value.get("required_pull_request_reviews") or {}
    checks = value.get("required_status_checks") or {}
    return {
        "observed": True,
        "protected": True,
        "required_approvals": reviews.get("required_approving_review_count"),
        "dismiss_stale_reviews": reviews.get("dismiss_stale_reviews"),
        "require_code_owner_reviews": reviews.get("require_code_owner_reviews"),
        "required_status_checks": [
            item.get("context") for item in (checks.get("checks") or []) if item.get("context")
        ] or checks.get("contexts") or [],
        "strict": checks.get("strict"),
        "enforce_admins": bool((value.get("enforce_admins") or {}).get("enabled")),
    }


def check_state(api: GitHubApi, repo: str, sha: str) -> dict[str, Any]:
    checks_payload = api.get(
        f"/repos/{ORG}/{repo}/commits/{sha}/check-runs?per_page=100",
        accept="application/vnd.github+json",
    )
    check_runs = checks_payload.get("check_runs") or []
    statuses_payload = api.get(f"/repos/{ORG}/{repo}/commits/{sha}/status")
    statuses = statuses_payload.get("statuses") or []
    rows: list[dict[str, Any]] = []
    pending = False
    failing = False
    for run in check_runs:
        conclusion = run.get("conclusion")
        status = run.get("status")
        row = {
            "kind": "check_run",
            "id": run.get("id"),
            "name": run.get("name"),
            "status": status,
            "conclusion": conclusion,
            "details_url": run.get("details_url"),
        }
        rows.append(row)
        if status != "completed" or conclusion is None:
            pending = True
        elif str(conclusion).lower() not in OK_CHECK_CONCLUSIONS:
            failing = True
    latest_context: dict[str, dict[str, Any]] = {}
    for status in statuses:
        context = str(status.get("context") or "")
        if context and context not in latest_context:
            latest_context[context] = status
    for context, status in latest_context.items():
        state = str(status.get("state") or "").lower()
        rows.append(
            {
                "kind": "commit_status",
                "id": status.get("id"),
                "name": context,
                "status": state,
                "conclusion": state,
                "details_url": status.get("target_url"),
            }
        )
        if state in {"pending", "expected"}:
            pending = True
        elif state not in {"success"}:
            failing = True
    return {
        "total": len(rows),
        "pending": pending,
        "failing": failing,
        "green": not pending and not failing,
        "checks": rows,
    }


def review_state(api: GitHubApi, repo: str, number: int) -> dict[str, Any]:
    reviews = api.paginate(f"/repos/{ORG}/{repo}/pulls/{number}/reviews")
    latest: dict[str, dict[str, Any]] = {}
    for review in reviews:
        login = str((review.get("user") or {}).get("login") or "")
        if login:
            latest[login] = review
    states = {login: str(review.get("state") or "").upper() for login, review in latest.items()}
    return {
        "states": states,
        "approvals": sum(1 for value in states.values() if value == "APPROVED"),
        "changes_requested": [login for login, value in states.items() if value == "CHANGES_REQUESTED"],
    }


def rerun_for_head(
    api: GitHubApi,
    repo: str,
    sha: str,
    already: set[int],
    report: dict[str, Any],
) -> int:
    query = urllib.parse.urlencode({"head_sha": sha, "per_page": 100})
    payload = api.get(f"/repos/{ORG}/{repo}/actions/runs?{query}")
    runs = payload.get("workflow_runs") or []
    changed = 0
    for run in runs:
        run_id = int(run.get("id") or 0)
        conclusion = str(run.get("conclusion") or "").lower()
        status = str(run.get("status") or "").lower()
        if not run_id or run_id in already:
            continue
        if status == "completed" and conclusion in FAILED_RUN_CONCLUSIONS:
            endpoint = (
                f"/repos/{ORG}/{repo}/actions/runs/{run_id}/rerun-failed-jobs"
                if conclusion not in {"startup_failure", "action_required"}
                else f"/repos/{ORG}/{repo}/actions/runs/{run_id}/rerun"
            )
            try:
                api.post(endpoint, {}, allow=(201, 202, 204))
                already.add(run_id)
                changed += 1
                report["workflow_actions"].append(
                    {
                        "repository": f"{ORG}/{repo}",
                        "run_id": run_id,
                        "workflow": run.get("name"),
                        "action": "RERUN_REQUESTED",
                        "prior_conclusion": conclusion,
                        "head_sha": sha,
                    }
                )
            except Exception as exc:
                report["workflow_actions"].append(
                    {
                        "repository": f"{ORG}/{repo}",
                        "run_id": run_id,
                        "workflow": run.get("name"),
                        "action": "RERUN_BLOCKED",
                        "error": safe_error(exc),
                    }
                )
    return changed


def process_pull_requests(
    api: GitHubApi,
    repositories: list[dict[str, Any]],
    rerun_ids: set[int],
    report: dict[str, Any],
) -> dict[str, int]:
    counts = {"observed": 0, "merged": 0, "updated": 0, "rerun": 0, "blocked": 0}
    for repository in repositories:
        repo = repository["name"]
        default_branch = repository.get("default_branch") or "main"
        try:
            pulls = api.paginate(f"/repos/{ORG}/{repo}/pulls?state=open")
        except Exception as exc:
            report["errors"].append({"scope": f"{repo}:pull-list", "error": safe_error(exc)})
            continue
        for compact in pulls:
            counts["observed"] += 1
            number = int(compact["number"])
            observation: dict[str, Any] = {
                "repository": f"{ORG}/{repo}",
                "number": number,
                "title": compact.get("title"),
                "draft": compact.get("draft"),
                "base": (compact.get("base") or {}).get("ref"),
                "head": (compact.get("head") or {}).get("ref"),
                "head_sha": (compact.get("head") or {}).get("sha"),
                "author": (compact.get("user") or {}).get("login"),
                "updated_at": compact.get("updated_at"),
                "action": "OBSERVED",
            }
            try:
                pull = api.get(f"/repos/{ORG}/{repo}/pulls/{number}")
                head = pull.get("head") or {}
                head_sha = str(head.get("sha") or "")
                head_repo = ((head.get("repo") or {}).get("full_name") or "")
                labels = {str(item.get("name") or "").lower() for item in pull.get("labels") or []}
                title = str(pull.get("title") or "")
                observation.update(
                    {
                        "head_sha": head_sha,
                        "mergeable": pull.get("mergeable"),
                        "mergeable_state": pull.get("mergeable_state"),
                        "changed_files": pull.get("changed_files"),
                        "commits": pull.get("commits"),
                        "labels": sorted(labels),
                    }
                )
                checks = check_state(api, repo, head_sha)
                reviews = review_state(api, repo, number)
                protection = protection_summary(api, repo, default_branch)
                observation["check_state"] = checks
                observation["review_state"] = reviews
                observation["base_protection"] = protection

                hold_reason = None
                if pull.get("draft"):
                    hold_reason = "DRAFT"
                elif pull.get("base", {}).get("ref") != default_branch:
                    hold_reason = "NON_DEFAULT_BASE"
                elif head_repo and head_repo.casefold() != f"{ORG}/{repo}".casefold():
                    hold_reason = "EXTERNAL_HEAD_REPOSITORY"
                elif labels & HOLD_LABELS:
                    hold_reason = "HOLD_LABEL"
                elif re.search(r"\b(?:wip|do not merge|hold)\b", title, re.IGNORECASE):
                    hold_reason = "TITLE_HOLD"
                elif reviews["changes_requested"]:
                    hold_reason = "CHANGES_REQUESTED"

                mergeable_state = str(pull.get("mergeable_state") or "").lower()
                if hold_reason:
                    observation.update({"action": "BLOCKED", "blocker": hold_reason})
                    counts["blocked"] += 1
                elif mergeable_state == "behind":
                    try:
                        api.put(
                            f"/repos/{ORG}/{repo}/pulls/{number}/update-branch",
                            {"expected_head_sha": head_sha},
                            allow=(200, 202),
                        )
                        observation["action"] = "UPDATE_BRANCH_REQUESTED"
                        counts["updated"] += 1
                    except Exception as exc:
                        observation.update({"action": "UPDATE_BRANCH_BLOCKED", "error": safe_error(exc)})
                        counts["blocked"] += 1
                elif checks["pending"]:
                    observation.update({"action": "WAITING_CHECKS", "blocker": "CHECKS_PENDING"})
                    counts["blocked"] += 1
                elif checks["failing"]:
                    rerun_count = rerun_for_head(api, repo, head_sha, rerun_ids, report)
                    counts["rerun"] += rerun_count
                    observation.update(
                        {
                            "action": "FAILED_CHECKS_RERUN_REQUESTED" if rerun_count else "BLOCKED_FAILED_CHECKS",
                            "blocker": "CHECKS_FAILED",
                            "rerun_count": rerun_count,
                        }
                    )
                    counts["blocked"] += 1
                elif pull.get("mergeable") is True and mergeable_state in {"clean", "unstable", "has_hooks"}:
                    try:
                        merged = api.put(
                            f"/repos/{ORG}/{repo}/pulls/{number}/merge",
                            {
                                "sha": head_sha,
                                "merge_method": "squash",
                                "commit_title": f"{title} (#{number})",
                                "commit_message": (
                                    "Exact-head estate reconciliation: all observed checks were terminal-green; "
                                    "GitHub branch protection and review policy remained authoritative.\n\n"
                                    "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
                                ),
                            },
                            allow=(200, 201, 405, 409),
                        )
                        if isinstance(merged, Mapping) and merged.get("merged") is True:
                            observation.update(
                                {
                                    "action": "MERGED",
                                    "merge_sha": merged.get("sha"),
                                    "merge_message": merged.get("message"),
                                }
                            )
                            counts["merged"] += 1
                        else:
                            observation.update(
                                {
                                    "action": "MERGE_BLOCKED_BY_GITHUB",
                                    "blocker": str((merged or {}).get("message") or "merge rejected"),
                                }
                            )
                            counts["blocked"] += 1
                    except Exception as exc:
                        observation.update({"action": "MERGE_BLOCKED_BY_GITHUB", "error": safe_error(exc)})
                        counts["blocked"] += 1
                else:
                    observation.update(
                        {
                            "action": "BLOCKED",
                            "blocker": f"MERGEABILITY_{mergeable_state or 'UNKNOWN'}",
                        }
                    )
                    counts["blocked"] += 1
            except Exception as exc:
                observation.update({"action": "OBSERVATION_FAILED", "error": safe_error(exc)})
                counts["blocked"] += 1
            report["pull_requests"].append(observation)
    return counts


def recycle_stale_runs(
    api: GitHubApi,
    repositories: list[dict[str, Any]],
    current_run_id: int | None,
    rerun_ids: set[int],
    report: dict[str, Any],
) -> dict[str, int]:
    counts = {"stale_observed": 0, "cancelled": 0, "rerun": 0, "blocked": 0}
    for repository in repositories:
        repo = repository["name"]
        for status in ("queued", "in_progress"):
            try:
                payload = api.get(f"/repos/{ORG}/{repo}/actions/runs?status={status}&per_page=100")
            except Exception as exc:
                report["errors"].append({"scope": f"{repo}:runs:{status}", "error": safe_error(exc)})
                continue
            for run in payload.get("workflow_runs") or []:
                run_id = int(run.get("id") or 0)
                if not run_id or run_id == current_run_id:
                    continue
                age = age_minutes(run.get("run_started_at") or run.get("created_at"))
                if age is None or age < STALE_MINUTES:
                    continue
                counts["stale_observed"] += 1
                row = {
                    "repository": f"{ORG}/{repo}",
                    "run_id": run_id,
                    "workflow": run.get("name"),
                    "status": status,
                    "age_minutes": round(age, 1),
                    "head_sha": run.get("head_sha"),
                }
                try:
                    api.post(f"/repos/{ORG}/{repo}/actions/runs/{run_id}/cancel", {}, allow=(202, 204, 409))
                    row["action"] = "CANCEL_REQUESTED"
                    counts["cancelled"] += 1
                    rerun_ids.add(run_id)
                except Exception as exc:
                    row.update({"action": "CANCEL_BLOCKED", "error": safe_error(exc)})
                    counts["blocked"] += 1
                report["stale_runs"].append(row)
    return counts


def rerun_recent_default_failures(
    api: GitHubApi,
    repositories: list[dict[str, Any]],
    rerun_ids: set[int],
    report: dict[str, Any],
) -> int:
    count = 0
    for repository in repositories:
        repo = repository["name"]
        default_branch = repository.get("default_branch") or "main"
        try:
            payload = api.get(
                f"/repos/{ORG}/{repo}/actions/runs?branch={urllib.parse.quote(default_branch, safe='')}&per_page=100"
            )
        except Exception as exc:
            report["errors"].append({"scope": f"{repo}:default-runs", "error": safe_error(exc)})
            continue
        seen_workflows: set[int] = set()
        for run in payload.get("workflow_runs") or []:
            workflow_id = int(run.get("workflow_id") or 0)
            if workflow_id in seen_workflows:
                continue
            seen_workflows.add(workflow_id)
            run_id = int(run.get("id") or 0)
            if not run_id or run_id in rerun_ids:
                continue
            conclusion = str(run.get("conclusion") or "").lower()
            status = str(run.get("status") or "").lower()
            age = age_minutes(run.get("updated_at"))
            if status != "completed" or conclusion not in FAILED_RUN_CONCLUSIONS:
                continue
            if age is None or age > 7 * 24 * 60:
                continue
            try:
                endpoint = (
                    f"/repos/{ORG}/{repo}/actions/runs/{run_id}/rerun-failed-jobs"
                    if conclusion not in {"startup_failure", "action_required"}
                    else f"/repos/{ORG}/{repo}/actions/runs/{run_id}/rerun"
                )
                api.post(endpoint, {}, allow=(201, 202, 204))
                rerun_ids.add(run_id)
                count += 1
                report["workflow_actions"].append(
                    {
                        "repository": f"{ORG}/{repo}",
                        "run_id": run_id,
                        "workflow": run.get("name"),
                        "action": "LATEST_DEFAULT_FAILURE_RERUN_REQUESTED",
                        "prior_conclusion": conclusion,
                        "head_sha": run.get("head_sha"),
                    }
                )
            except Exception as exc:
                report["workflow_actions"].append(
                    {
                        "repository": f"{ORG}/{repo}",
                        "run_id": run_id,
                        "workflow": run.get("name"),
                        "action": "DEFAULT_RERUN_BLOCKED",
                        "error": safe_error(exc),
                    }
                )
    return count


def branch_has_agent_provenance(branch: str, commit: Mapping[str, Any]) -> bool:
    if AGENT_MARKERS.search(branch):
        return True
    message = str(((commit.get("commit") or {}).get("message") or ""))
    author = str(((commit.get("author") or {}).get("login") or ""))
    committer = str(((commit.get("committer") or {}).get("login") or ""))
    combined = " ".join((message, author, committer))
    return bool(AGENT_MARKERS.search(combined))


def create_orphan_agent_prs(
    api: GitHubApi,
    repositories: list[dict[str, Any]],
    report: dict[str, Any],
) -> int:
    created = 0
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=RECENT_BRANCH_DAYS)
    for repository in repositories:
        if created >= MAX_ORPHAN_PRS:
            break
        repo = repository["name"]
        default_branch = repository.get("default_branch") or "main"
        try:
            open_pulls = api.paginate(f"/repos/{ORG}/{repo}/pulls?state=open")
            open_heads = {str((pr.get("head") or {}).get("ref") or "") for pr in open_pulls}
            branches = api.paginate(f"/repos/{ORG}/{repo}/branches")
        except Exception as exc:
            report["errors"].append({"scope": f"{repo}:orphan-scan", "error": safe_error(exc)})
            continue
        for branch_row in branches:
            if created >= MAX_ORPHAN_PRS:
                break
            branch = str(branch_row.get("name") or "")
            if not branch or branch == default_branch or branch in open_heads:
                continue
            if not branch.startswith(SAFE_BRANCH_PREFIXES) and not AGENT_MARKERS.search(branch):
                continue
            sha = str(((branch_row.get("commit") or {}).get("sha") or ""))
            if not re.fullmatch(r"[0-9a-f]{40}", sha):
                continue
            try:
                commit = api.get(f"/repos/{ORG}/{repo}/commits/{sha}")
                committed_at = parse_time(((commit.get("commit") or {}).get("committer") or {}).get("date"))
                if committed_at is None or committed_at < cutoff:
                    continue
                if not branch_has_agent_provenance(branch, commit):
                    continue
                head_query = urllib.parse.quote(f"{ORG}:{branch}", safe="")
                prior = api.get(f"/repos/{ORG}/{repo}/pulls?state=all&head={head_query}&per_page=10")
                if prior:
                    report["orphan_branches"].append(
                        {
                            "repository": f"{ORG}/{repo}",
                            "branch": branch,
                            "head_sha": sha,
                            "action": "PR_HISTORY_ALREADY_EXISTS",
                            "prior_prs": [item.get("number") for item in prior],
                        }
                    )
                    continue
                base_encoded = urllib.parse.quote(default_branch, safe="")
                head_encoded = urllib.parse.quote(branch, safe="")
                comparison = api.get(f"/repos/{ORG}/{repo}/compare/{base_encoded}...{head_encoded}")
                ahead_by = int(comparison.get("ahead_by") or 0)
                if ahead_by <= 0:
                    continue
                first_line = str(((commit.get("commit") or {}).get("message") or branch)).splitlines()[0][:180]
                title = first_line if first_line else f"Reconcile {branch}"
                created_pr = api.post(
                    f"/repos/{ORG}/{repo}/pulls",
                    {
                        "title": title,
                        "head": branch,
                        "base": default_branch,
                        "draft": False,
                        "maintainer_can_modify": True,
                        "body": (
                            "## Recovered agent branch\n\n"
                            "The estate reconciler found this recent Codex/Perplexity/agent branch ahead of the "
                            "default branch with no open pull request. This PR restores the normal review, CI, and "
                            "exact-head merge path.\n\n"
                            f"- Head: `{sha}`\n"
                            f"- Ahead by: `{ahead_by}` commit(s)\n"
                            "- No protection, review, or status check is bypassed.\n\n"
                            "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
                        ),
                    },
                    allow=(201,),
                )
                created += 1
                report["orphan_branches"].append(
                    {
                        "repository": f"{ORG}/{repo}",
                        "branch": branch,
                        "head_sha": sha,
                        "ahead_by": ahead_by,
                        "action": "PR_CREATED",
                        "pull_number": created_pr.get("number"),
                        "pull_url": created_pr.get("html_url"),
                    }
                )
            except Exception as exc:
                report["orphan_branches"].append(
                    {
                        "repository": f"{ORG}/{repo}",
                        "branch": branch,
                        "head_sha": sha,
                        "action": "ORPHAN_RECOVERY_BLOCKED",
                        "error": safe_error(exc),
                    }
                )
    return created


def select_hf_token() -> tuple[str | None, dict[str, Any]]:
    aliases = (
        "HF_ORG_TOKEN",
        "HF_ORG_TOKEN1",
        "HF_WRITE_TOKEN",
        "HF_TOKEN",
        "HUGGINGFACE_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
    )
    attempts: list[dict[str, Any]] = []
    try:
        from huggingface_hub import HfApi
    except Exception as exc:
        return None, {"state": "CLIENT_UNAVAILABLE", "error": safe_error(exc), "attempts": attempts}
    for alias in aliases:
        token = os.getenv(alias, "").strip()
        if not token:
            continue
        print(f"::add-mask::{token}")
        try:
            identity = HfApi(token=token).whoami()
            name = identity.get("name") if isinstance(identity, Mapping) else None
            orgs = identity.get("orgs") if isinstance(identity, Mapping) else []
            role = None
            for org in orgs or []:
                if str(org.get("name") or "").casefold() == HF_ORG.casefold():
                    role = org.get("role")
                    break
            write = str(role or "").lower() in {"admin", "write", "contributor"}
            attempts.append({"alias": alias, "identity": name, "active": True, "org_role": role, "org_write": write})
            if write:
                return token, {
                    "state": "ACTIVE_ORG_WRITE_AUTHORITY",
                    "alias": alias,
                    "identity": name,
                    "org_role": role,
                    "attempts": attempts,
                }
        except Exception as exc:
            attempts.append({"alias": alias, "active": False, "error": safe_error(exc)})
    return None, {"state": "UNAVAILABLE", "attempts": attempts}


def runtime_stage(info: Any) -> str:
    runtime = getattr(info, "runtime", None)
    if runtime is None:
        return "UNKNOWN"
    value = getattr(runtime, "stage", None)
    if value is None and isinstance(runtime, Mapping):
        value = runtime.get("stage")
    return str(value or "UNKNOWN").upper()


def reconcile_hugging_face(report: dict[str, Any]) -> dict[str, int]:
    counts = {"spaces": 0, "running": 0, "restart_requested": 0, "failed": 0, "building": 0}
    token, authority = select_hf_token()
    report["hugging_face_authority"] = authority
    try:
        from huggingface_hub import HfApi
    except Exception as exc:
        report["errors"].append({"scope": "hugging-face-client", "error": safe_error(exc)})
        return counts
    api = HfApi(token=token) if token else HfApi()
    try:
        spaces = list(
            api.list_spaces(
                author=HF_ORG,
                full=True,
                expand=["runtime", "sha", "lastModified", "private", "sdk", "subdomain", "tags"],
            )
        )
    except Exception as exc:
        report["errors"].append({"scope": "hugging-face-space-inventory", "error": safe_error(exc)})
        return counts
    counts["spaces"] = len(spaces)
    restart_ids: list[str] = []
    restartable = {
        "PAUSED",
        "STOPPED",
        "RUNTIME_ERROR",
        "BUILD_ERROR",
        "CONFIG_ERROR",
        "NO_APP_FILE",
    }
    for info in spaces:
        repo_id = str(getattr(info, "id", None) or getattr(info, "repo_id", None) or "")
        stage = runtime_stage(info)
        row: dict[str, Any] = {
            "repo_id": repo_id,
            "sdk": getattr(info, "sdk", None),
            "private": getattr(info, "private", None),
            "sha": getattr(info, "sha", None),
            "last_modified": str(getattr(info, "last_modified", None) or getattr(info, "lastModified", None) or ""),
            "stage_before": stage,
            "action": "OBSERVED",
        }
        if stage == "RUNNING":
            counts["running"] += 1
        elif stage in {"BUILDING", "STARTING", "RESTARTING"}:
            counts["building"] += 1
            row["action"] = "BUILD_IN_PROGRESS"
        elif stage in restartable:
            if token:
                try:
                    api.restart_space(repo_id=repo_id)
                    restart_ids.append(repo_id)
                    counts["restart_requested"] += 1
                    row["action"] = "RESTART_REQUESTED"
                except Exception as exc:
                    counts["failed"] += 1
                    row.update({"action": "RESTART_BLOCKED", "error": safe_error(exc)})
            else:
                counts["failed"] += 1
                row.update({"action": "RESTART_BLOCKED", "blocker": "HF_ORG_WRITE_TOKEN_UNAVAILABLE"})
        else:
            counts["failed"] += 1
            row.update({"action": "NON_RUNNING_TERMINAL", "blocker": f"STAGE_{stage}"})
        report["hugging_face_spaces"].append(row)

    if restart_ids:
        deadline = time.monotonic() + 900
        remaining = set(restart_ids)
        while remaining and time.monotonic() < deadline:
            time.sleep(30)
            for repo_id in list(remaining):
                try:
                    current = api.space_info(repo_id=repo_id, expand=["runtime", "sha", "lastModified"])
                    stage = runtime_stage(current)
                    for row in report["hugging_face_spaces"]:
                        if row.get("repo_id") == repo_id:
                            row["stage_after"] = stage
                            row["sha_after"] = getattr(current, "sha", None)
                            break
                    if stage == "RUNNING":
                        counts["running"] += 1
                        remaining.remove(repo_id)
                    elif stage in {"RUNTIME_ERROR", "BUILD_ERROR", "CONFIG_ERROR", "NO_APP_FILE", "PAUSED", "STOPPED"}:
                        counts["failed"] += 1
                        remaining.remove(repo_id)
                except Exception as exc:
                    for row in report["hugging_face_spaces"]:
                        if row.get("repo_id") == repo_id:
                            row["poll_error"] = safe_error(exc)
                            break
        for repo_id in remaining:
            counts["building"] += 1
            for row in report["hugging_face_spaces"]:
                if row.get("repo_id") == repo_id:
                    row["stage_after"] = "NON_TERMINAL_AFTER_BOUNDED_WAIT"
                    break

    for kind, method in (("models", api.list_models), ("datasets", api.list_datasets)):
        try:
            assets = list(method(author=HF_ORG, limit=None, full=True))
            report["hugging_face_assets"][kind] = {
                "count": len(assets),
                "ids": [str(getattr(item, "id", "")) for item in assets],
            }
        except Exception as exc:
            report["hugging_face_assets"][kind] = {"state": "UNAVAILABLE", "error": safe_error(exc)}
    return counts


def terminal_snapshot(api: GitHubApi, repositories: list[dict[str, Any]]) -> dict[str, Any]:
    open_prs: list[dict[str, Any]] = []
    stale_runs: list[dict[str, Any]] = []
    failed_default_runs: list[dict[str, Any]] = []
    for repository in repositories:
        repo = repository["name"]
        default_branch = repository.get("default_branch") or "main"
        try:
            for pr in api.paginate(f"/repos/{ORG}/{repo}/pulls?state=open"):
                open_prs.append(
                    {
                        "repository": f"{ORG}/{repo}",
                        "number": pr.get("number"),
                        "title": pr.get("title"),
                        "draft": pr.get("draft"),
                        "head": (pr.get("head") or {}).get("ref"),
                        "head_sha": (pr.get("head") or {}).get("sha"),
                    }
                )
        except Exception as exc:
            open_prs.append({"repository": f"{ORG}/{repo}", "state": "UNAVAILABLE", "error": safe_error(exc)})
        for status in ("queued", "in_progress"):
            try:
                payload = api.get(f"/repos/{ORG}/{repo}/actions/runs?status={status}&per_page=100")
                for run in payload.get("workflow_runs") or []:
                    age = age_minutes(run.get("run_started_at") or run.get("created_at"))
                    if age is not None and age >= STALE_MINUTES:
                        stale_runs.append(
                            {
                                "repository": f"{ORG}/{repo}",
                                "run_id": run.get("id"),
                                "workflow": run.get("name"),
                                "status": status,
                                "age_minutes": round(age, 1),
                            }
                        )
            except Exception:
                pass
        try:
            branch = urllib.parse.quote(default_branch, safe="")
            payload = api.get(f"/repos/{ORG}/{repo}/actions/runs?branch={branch}&per_page=100")
            latest: dict[int, dict[str, Any]] = {}
            for run in payload.get("workflow_runs") or []:
                workflow_id = int(run.get("workflow_id") or 0)
                if workflow_id and workflow_id not in latest:
                    latest[workflow_id] = run
            for run in latest.values():
                conclusion = str(run.get("conclusion") or "").lower()
                if str(run.get("status") or "").lower() == "completed" and conclusion in FAILED_RUN_CONCLUSIONS:
                    failed_default_runs.append(
                        {
                            "repository": f"{ORG}/{repo}",
                            "run_id": run.get("id"),
                            "workflow": run.get("name"),
                            "conclusion": conclusion,
                            "head_sha": run.get("head_sha"),
                        }
                    )
        except Exception:
            pass
    return {
        "open_pull_requests": open_prs,
        "stale_runs": stale_runs,
        "latest_failed_default_workflows": failed_default_runs,
        "counts": {
            "open_pull_requests": len(open_prs),
            "stale_runs": len(stale_runs),
            "latest_failed_default_workflows": len(failed_default_runs),
        },
    }


def publish_issue_summary(api: GitHubApi, report: dict[str, Any]) -> None:
    title = "[Estate Reconciliation] Codex and Perplexity completion ledger"
    query = urllib.parse.urlencode({"q": f'repo:{ORG}/{CENTRAL_REPO} is:issue in:title "{title}"'})
    try:
        result = api.get(f"/search/issues?{query}")
        items = result.get("items") or []
        if items:
            number = int(items[0]["number"])
        else:
            created = api.post(
                f"/repos/{ORG}/{CENTRAL_REPO}/issues",
                {
                    "title": title,
                    "body": (
                        "Canonical machine-generated ledger for stalled/half-built agent work. "
                        "The operator respects branch protection, reviews, DCO, exact-head checks, and provider authority."
                    ),
                },
                allow=(201,),
            )
            number = int(created["number"])
        terminal = report.get("terminal") or {}
        counts = terminal.get("counts") or {}
        hf = report.get("hugging_face_summary") or {}
        body = "\n".join(
            [
                f"## Estate reconciliation — {report.get('finished_at')}",
                "",
                f"- State: `{report.get('state')}`",
                f"- Repositories scanned: `{report.get('repository_count')}`",
                f"- PRs remaining: `{counts.get('open_pull_requests')}`",
                f"- Stale Actions runs remaining: `{counts.get('stale_runs')}`",
                f"- Latest failed default-branch workflows: `{counts.get('latest_failed_default_workflows')}`",
                f"- Hugging Face Spaces observed: `{hf.get('spaces')}`",
                f"- Hugging Face Spaces running: `{hf.get('running')}`",
                f"- Hugging Face restart requests: `{hf.get('restart_requested')}`",
                f"- Hugging Face terminal failures: `{hf.get('failed')}`",
                "",
                f"Evidence digest: `{report.get('report_sha256')}`",
                "",
                "Secret values, prompts, model outputs, and hidden reasoning are not recorded.",
            ]
        )
        api.post(f"/repos/{ORG}/{CENTRAL_REPO}/issues/{number}/comments", {"body": body}, allow=(201,))
        report["issue_ledger"] = {"repository": f"{ORG}/{CENTRAL_REPO}", "number": number, "commented": True}
    except Exception as exc:
        report["issue_ledger"] = {"state": "UNAVAILABLE", "error": safe_error(exc)}


def derive_state(report: dict[str, Any]) -> str:
    terminal = report.get("terminal") or {}
    counts = terminal.get("counts") or {}
    hf = report.get("hugging_face_summary") or {}
    if report.get("github_authority", {}).get("state") != "ACTIVE_WRITE_AUTHORITY":
        return "BLOCKED_GITHUB_AUTHORITY"
    if report.get("hugging_face_authority", {}).get("state") != "ACTIVE_ORG_WRITE_AUTHORITY":
        return "BLOCKED_HUGGING_FACE_AUTHORITY"
    if counts.get("stale_runs"):
        return "BLOCKED_STALE_ACTIONS"
    if counts.get("latest_failed_default_workflows"):
        return "BLOCKED_FAILED_DEFAULT_WORKFLOWS"
    if hf.get("failed"):
        return "BLOCKED_HUGGING_FACE_RUNTIME"
    if counts.get("open_pull_requests"):
        return "CONVERGED_WITH_REVIEW_OR_CHECK_BLOCKERS"
    if hf.get("building"):
        return "CONVERGED_WITH_PROVIDER_BUILDS_IN_PROGRESS"
    return "VERIFIED_COMPLETE"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--passes", type=int, default=MAX_PASSES)
    parser.add_argument("--pass-delay", type=int, default=PASS_DELAY_SECONDS)
    args = parser.parse_args(argv)

    report: dict[str, Any] = {
        "schema": "szl.agent-estate-reconciliation/v1",
        "started_at": now_iso(),
        "organization": ORG,
        "hugging_face_organization": HF_ORG,
        "policy": {
            "branch_protection_bypass": False,
            "review_bypass": False,
            "dco_bypass": False,
            "exact_head_required": True,
            "all_observed_checks_terminal_green_before_merge": True,
            "secret_values_recorded": False,
            "hidden_reasoning_recorded": False,
        },
        "passes": [],
        "pull_requests": [],
        "workflow_actions": [],
        "stale_runs": [],
        "orphan_branches": [],
        "hugging_face_spaces": [],
        "hugging_face_assets": {},
        "errors": [],
    }
    api, authority = select_github_token()
    report["github_authority"] = authority
    if api is None:
        report["state"] = "BLOCKED_GITHUB_AUTHORITY"
        report["finished_at"] = now_iso()
        report["report_sha256"] = sha256_json({k: v for k, v in report.items() if k != "report_sha256"})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 2

    try:
        repositories = repository_inventory(api)
    except Exception as exc:
        report["errors"].append({"scope": "repository-inventory", "error": safe_error(exc)})
        report["state"] = "BLOCKED_GITHUB_INVENTORY"
        report["finished_at"] = now_iso()
        report["report_sha256"] = sha256_json({k: v for k, v in report.items() if k != "report_sha256"})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 2

    report["repository_count"] = len(repositories)
    report["repositories"] = [
        {
            "full_name": repo.get("full_name"),
            "default_branch": repo.get("default_branch"),
            "private": repo.get("private"),
            "updated_at": repo.get("updated_at"),
            "pushed_at": repo.get("pushed_at"),
        }
        for repo in repositories
    ]
    rerun_ids: set[int] = set()
    current_run_id = int(os.getenv("GITHUB_RUN_ID") or 0) or None

    orphan_created = create_orphan_agent_prs(api, repositories, report)
    for index in range(max(1, min(args.passes, 8))):
        pass_row: dict[str, Any] = {"index": index + 1, "started_at": now_iso()}
        pass_row["stale_runs"] = recycle_stale_runs(api, repositories, current_run_id, rerun_ids, report)
        pass_row["default_failure_reruns"] = rerun_recent_default_failures(api, repositories, rerun_ids, report)
        pass_row["pull_requests"] = process_pull_requests(api, repositories, rerun_ids, report)
        pass_row["finished_at"] = now_iso()
        report["passes"].append(pass_row)
        if index + 1 < max(1, min(args.passes, 8)):
            time.sleep(max(0, min(args.pass_delay, 600)))

    report["orphan_pull_requests_created"] = orphan_created
    report["hugging_face_summary"] = reconcile_hugging_face(report)
    report["terminal"] = terminal_snapshot(api, repositories)
    report["finished_at"] = now_iso()
    report["state"] = derive_state(report)
    report["report_sha256"] = sha256_json({k: v for k, v in report.items() if k != "report_sha256"})
    publish_issue_summary(api, report)
    report["report_sha256"] = sha256_json({k: v for k, v in report.items() if k != "report_sha256"})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "state": report["state"],
                "repository_count": report.get("repository_count"),
                "terminal_counts": (report.get("terminal") or {}).get("counts"),
                "hugging_face_summary": report.get("hugging_face_summary"),
                "report_sha256": report["report_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["state"] == "VERIFIED_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
