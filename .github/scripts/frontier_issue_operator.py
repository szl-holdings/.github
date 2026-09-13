#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded organization-wide pull-request and issue convergence operator.

The operator is intentionally conservative:

* it merges only same-repository, non-draft pull requests into the repository's
  default branch when GitHub reports a clean merge, every observed check and
  status is terminal-success/neutral/skipped, no reviewer currently requests
  changes, and no review thread is unresolved;
* it closes only exact normalized duplicate issues, retaining the most recently
  updated canonical issue and leaving a durable pointer on each duplicate;
* it classifies every remaining issue with one deterministic ``estate:*`` label;
* it never changes branch protection, rulesets, visibility, secrets, provider
  resources, repository archival state, or issue content authored by humans;
* it records no token value and redacts token-like strings from its report;
* incomplete check/review coverage fails closed, archived targets are read-only,
  and per-item errors produce a partial-failure receipt and nonzero exit.

Dry-run is the default. ``--apply`` enables the bounded mutations above.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"
MAX_API_BYTES = 10 * 1024 * 1024
DEFAULT_ORG = "szl-holdings"
REPORT_SCHEMA = "szl.frontier-issue-operator/v1"
COMMAND_CENTER_TITLE = "[estate] Frontier issue command center"
COMMAND_CENTER_MARKER = "<!-- SZL-FRONTIER-ISSUE-COMMAND-CENTER-V1 -->"
DUPLICATE_MARKER = "<!-- SZL-EXACT-DUPLICATE-CLOSURE-V1 -->"
ALLOWED_CHECK_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})
FAILED_CHECK_CONCLUSIONS = frozenset(
    {"failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"}
)
ACTIVE_CHECK_STATES = frozenset({"queued", "in_progress", "pending", "requested", "waiting"})
SAFE_MERGE_STATES = frozenset({"clean", "has_hooks"})
TOKEN_PATTERN = re.compile(r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,})")
URL_PATTERN = re.compile(r"https?://\S+")
WHITESPACE = re.compile(r"\s+")

LABELS = {
    "estate:p0": ("b60205", "Immediate security, data-integrity, or production-boundary defect"),
    "estate:runtime-drift": ("d93f0b", "Deployment, runtime, source-parity, health, or public-origin drift"),
    "estate:blocked-external": ("5319e7", "Requires a managed provider, credential, billing, quota, or owner decision"),
    "estate:code-actionable": ("1d76db", "Repository code, tests, documentation, or CI work that can be implemented"),
    "estate:execution-ledger": ("0e8a16", "Coordination or evidence ledger tracking multiple execution lanes"),
    "estate:roadmap": ("c5def5", "Deliberate research, benchmark, training, or future product work"),
    "estate:backlog": ("ededed", "Unclassified product or engineering backlog"),
}


class GitHubError(RuntimeError):
    """GitHub API failure with a secret-free message."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward a credentialed API request to a redirect target."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api_url(path: str) -> str:
    """Confine all credentialed requests to the canonical GitHub API origin."""
    if not isinstance(path, str) or any(ord(c) < 33 or ord(c) == 127 for c in path):
        raise GitHubError("invalid GitHub API target")
    url = API + path if path.startswith("/") and not path.startswith("//") else path
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError:
        raise GitHubError("invalid GitHub API target") from None
    if (parsed.scheme != "https" or parsed.hostname != "api.github.com"
            or parsed.username is not None or parsed.password is not None
            or port not in (None, 443) or parsed.fragment
            or "\\" in url or any(x in {".", ".."} for x in urllib.parse.unquote(parsed.path).split("/"))):
        raise GitHubError("noncanonical GitHub API target refused")
    return url


@dataclass
class CheckState:
    count: int = 0
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    active: list[str] = field(default_factory=list)


@dataclass
class PullRequestState:
    repository: str
    number: int
    title: str
    url: str
    head_sha: str | None = None
    base_ref: str | None = None
    default_branch: str | None = None
    draft: bool = False
    same_repository: bool = False
    mergeable: bool | None = None
    mergeable_state: str | None = None
    unresolved_threads: int | None = None
    changes_requested_by: list[str] = field(default_factory=list)
    checks: CheckState = field(default_factory=CheckState)
    blockers: list[str] = field(default_factory=list)
    action: str = "OBSERVED"
    merge_sha: str | None = None
    error: str | None = None


@dataclass
class IssueState:
    repository: str
    number: int
    title: str
    url: str
    updated_at: str
    classification: str
    duplicate_of: str | None = None
    action: str = "CLASSIFIED"
    error: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def redact(value: Any) -> Any:
    """Recursively remove credential-shaped strings before persistence."""
    if isinstance(value, str):
        return TOKEN_PATTERN.sub("[REDACTED]", value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact(item) for key, item in value.items()}
    return value


class GitHub:
    def __init__(self, token: str, *, apply: bool) -> None:
        self.token = token.strip()
        self.apply = apply
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-frontier-issue-operator/1.0",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        *,
        expected: Iterable[int] = (200,),
    ) -> tuple[Any, dict[str, str], int]:
        url = api_url(path)
        body = None
        headers = dict(self.headers)
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=45) as response:
                raw = response.read(MAX_API_BYTES + 1)
                if len(raw) > MAX_API_BYTES:
                    raise GitHubError("GitHub response exceeded its byte budget")
                result = json.loads(raw) if raw else None
                status = response.status
                response_headers = dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            # Error pages, Location headers and transport messages can contain
            # credentials or private text. Keep only a numeric status class.
            raise GitHubError(f"GitHub HTTP {exc.code}") from None
        except (urllib.error.URLError, OSError, ValueError):
            raise GitHubError("GitHub transport or JSON decoding failed") from None
        if status not in set(expected):
            raise GitHubError(f"unexpected GitHub status {status} for {method} {path}")
        return result, response_headers, status

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        result, _headers, _status = self.request(
            "POST", GRAPHQL, {"query": query, "variables": variables}, expected=(200,)
        )
        if not isinstance(result, dict):
            raise GitHubError("GitHub GraphQL returned a non-object")
        if result.get("errors"):
            raise GitHubError("GitHub GraphQL rejected the bounded query")
        data = result.get("data")
        if not isinstance(data, dict):
            raise GitHubError("GitHub GraphQL response has no data object")
        return data

    def search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        """Require a complete bounded census before using it for mutations.

        GitHub pagination must keep a fixed page size. Shrinking it on the last
        page repeats earlier rows and silently omits later ones.
        """
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise GitHubError("issue search limit must be between 1 and 1000")
        rows: list[dict[str, Any]] = []
        expected_total: int | None = None
        seen: set[int] = set()
        for page in range(1, 11):
            encoded = urllib.parse.quote(query)
            result, _headers, _status = self.request(
                "GET", f"/search/issues?q={encoded}&sort=updated&order=desc&per_page=100&page={page}",
            )
            if not isinstance(result, dict) or result.get("incomplete_results") is not False:
                raise GitHubError("issue search is incomplete or malformed")
            total, batch = result.get("total_count"), result.get("items")
            if type(total) is not int or not 0 <= total <= limit or not isinstance(batch, list):
                raise GitHubError("issue search coverage exceeds its limit or is unavailable")
            if expected_total is None:
                expected_total = total
            if total != expected_total or len(batch) != min(100, total - len(rows)):
                raise GitHubError("issue search coverage moved or a page is incomplete")
            for row in batch:
                identity = row.get("id") if isinstance(row, dict) else None
                if type(identity) is not int or identity <= 0 or identity in seen:
                    raise GitHubError("issue search contains invalid or repeated identities")
                seen.add(identity)
                rows.append(row)
            if len(rows) == expected_total:
                return rows
        raise GitHubError("issue search exceeded its page budget")

    def counted_pages(self, path: str, key: str, *, sha: str | None = None) -> list[dict[str, Any]]:
        """Collect every advertised check/status page, or refuse the observation.

        Construct same-endpoint page URLs rather than trusting a provider Link
        target. Counts and duplicate IDs detect common movement/truncation; this
        is not an atomic GitHub snapshot and does not replace merge protections.
        """
        rows: list[dict[str, Any]] = []
        seen: set[int] = set()
        expected_total: int | None = None
        for page in range(1, 101):
            result, _headers, _status = self.request("GET", f"{path}?per_page=100&page={page}")
            if not isinstance(result, dict):
                raise GitHubError("check/status collection is not an object")
            total, batch = result.get("total_count"), result.get(key)
            if type(total) is not int or not 0 <= total <= 10000 or not isinstance(batch, list):
                raise GitHubError("check/status coverage is malformed or outside its budget")
            if sha is not None and result.get("sha") != sha:
                raise GitHubError("combined status belongs to a different revision")
            if expected_total is None:
                expected_total = total
            if total != expected_total or len(batch) != min(100, total - len(rows)):
                raise GitHubError("check/status coverage moved or a page is incomplete")
            for row in batch:
                identity = row.get("id") if isinstance(row, dict) else None
                if type(identity) is not int or identity <= 0 or identity in seen:
                    raise GitHubError("check/status collection has invalid or repeated identities")
                seen.add(identity)
                rows.append(row)
            if len(rows) == expected_total:
                return rows
        raise GitHubError("check/status collection exceeded its page budget")

    def repository(self, full_name: str) -> dict[str, Any]:
        result, _headers, _status = self.request("GET", f"/repos/{full_name}")
        if not isinstance(result, dict):
            raise GitHubError(f"repository response is not an object: {full_name}")
        return result

    def pull(self, full_name: str, number: int) -> dict[str, Any]:
        # GitHub may briefly return mergeable=null while computing the merge.
        result: dict[str, Any] = {}
        for attempt in range(4):
            value, _headers, _status = self.request("GET", f"/repos/{full_name}/pulls/{number}")
            if not isinstance(value, dict):
                raise GitHubError(f"pull response is not an object: {full_name}#{number}")
            result = value
            if result.get("mergeable") is not None:
                break
            if attempt < 3:
                time.sleep(2 + attempt)
        return result

    def checks(self, full_name: str, sha: str) -> CheckState:
        check_runs = self.counted_pages(
            f"/repos/{full_name}/commits/{sha}/check-runs", "check_runs"
        )
        statuses = self.counted_pages(
            f"/repos/{full_name}/commits/{sha}/status", "statuses", sha=sha
        )
        passed: list[str] = []
        failed: list[str] = []
        active: list[str] = []
        for row in check_runs:
            name = str(row.get("name") or row.get("id"))
            status = str(row.get("status") or "").lower()
            conclusion = str(row.get("conclusion") or "").lower()
            if status in ACTIVE_CHECK_STATES or not conclusion:
                active.append(name)
            elif status == "completed" and conclusion in ALLOWED_CHECK_CONCLUSIONS:
                passed.append(name)
            elif conclusion in FAILED_CHECK_CONCLUSIONS:
                failed.append(name)
            else:
                failed.append(f"{name}:{conclusion or status or 'unknown'}")
        for row in statuses:
            name = str(row.get("context") or row.get("id"))
            state = str(row.get("state") or "").lower()
            if state == "success":
                passed.append(name)
            elif state == "pending":
                active.append(name)
            elif state in {"failure", "error"}:
                failed.append(name)
            else:
                failed.append(f"{name}:{state or 'unknown'}")
        return CheckState(
            count=len(check_runs) + len(statuses),
            passed=sorted(set(passed)),
            failed=sorted(set(failed)),
            active=sorted(set(active)),
        )

    def reviews(self, full_name: str, number: int) -> list[str]:
        # COMMENTED/PENDING do not revoke a prior change request. Require all
        # pages before accepting a later approval/dismissal as the final state.
        latest_decisive: dict[str, str] = {}
        decisive = {"CHANGES_REQUESTED", "APPROVED", "DISMISSED"}
        seen_pages: set[str] = set()
        for page in range(1, 101):
            result, _headers, _status = self.request(
                "GET", f"/repos/{full_name}/pulls/{number}/reviews?per_page=100&page={page}"
            )
            if not isinstance(result, list) or len(result) > 100:
                raise GitHubError("review collection is malformed")
            fingerprint = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
            if result and fingerprint in seen_pages:
                raise GitHubError("review pagination repeated a page")
            seen_pages.add(fingerprint)
            for row in result:
                if not isinstance(row, dict) or not isinstance(row.get("user"), dict):
                    raise GitHubError("review identity is unavailable")
                login, state = row["user"].get("login"), row.get("state")
                if not isinstance(login, str) or not login or state not in decisive | {"COMMENTED", "PENDING"}:
                    raise GitHubError("review state or identity is unavailable")
                if state in decisive:
                    latest_decisive[login] = state
            if len(result) < 100:
                return sorted(login for login, state in latest_decisive.items()
                              if state == "CHANGES_REQUESTED")
        raise GitHubError("review collection exceeded its page budget")

    def unresolved_threads(self, full_name: str, number: int) -> int:
        owner, name = full_name.split("/", 1)
        query = """
        query($owner:String!, $name:String!, $number:Int!, $cursor:String) {
          repository(owner:$owner, name:$name) {
            pullRequest(number:$number) {
              reviewThreads(first:100, after:$cursor) {
                nodes { isResolved }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }
        """
        unresolved = 0
        cursor: str | None = None
        seen_cursors: set[str] = set()
        for _ in range(100):
            data = self.graphql(query, {"owner": owner, "name": name, "number": number, "cursor": cursor})
            repo = data.get("repository") if isinstance(data, dict) else None
            pull = repo.get("pullRequest") if isinstance(repo, dict) else None
            threads = pull.get("reviewThreads") if isinstance(pull, dict) else None
            if not isinstance(threads, dict):
                raise GitHubError("review-thread evidence is unavailable")
            nodes, page = threads.get("nodes"), threads.get("pageInfo")
            if not isinstance(nodes, list) or len(nodes) > 100 or not isinstance(page, dict):
                raise GitHubError("review-thread page is malformed")
            if type(page.get("hasNextPage")) is not bool:
                raise GitHubError("review-thread pagination state is unavailable")
            for row in nodes:
                if not isinstance(row, dict) or type(row.get("isResolved")) is not bool:
                    raise GitHubError("review-thread resolution state is unavailable")
                unresolved += not row["isResolved"]
            if page["hasNextPage"] is False:
                return unresolved
            cursor = page.get("endCursor")
            if not isinstance(cursor, str) or not cursor or len(cursor) > 1024 or cursor in seen_cursors:
                raise GitHubError("review-thread pagination has an invalid or repeated cursor")
            seen_cursors.add(cursor)
        raise GitHubError("review-thread collection exceeded its page budget")


    def merge(self, full_name: str, number: int, sha: str, title: str) -> str:
        if not self.apply:
            return "DRY_RUN"
        payload = {
            "sha": sha,
            "merge_method": "squash",
            "commit_title": f"{title} (#{number})",
            "commit_message": (
                "Protected frontier merge after exact-head terminal checks, clean mergeability, "
                "no outstanding change request, and zero unresolved review threads.\n\n"
                "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
            ),
        }
        result, _headers, _status = self.request(
            "PUT", f"/repos/{full_name}/pulls/{number}/merge", payload, expected=(200, 201)
        )
        if not isinstance(result, dict) or result.get("merged") is not True:
            raise GitHubError(f"GitHub rejected merge for {full_name}#{number}: {redact(result)}")
        value = result.get("sha")
        return str(value or "UNKNOWN")

    def ensure_label(self, full_name: str, name: str) -> None:
        if not self.apply:
            return
        color, description = LABELS[name]
        encoded = urllib.parse.quote(name, safe="")
        try:
            self.request("GET", f"/repos/{full_name}/labels/{encoded}")
        except GitHubError as exc:
            if "HTTP 404" not in str(exc):
                raise
            self.request(
                "POST",
                f"/repos/{full_name}/labels",
                {"name": name, "color": color, "description": description},
                expected=(201,),
            )

    def set_classification(
        self,
        full_name: str,
        number: int,
        label: str,
        existing_labels: Iterable[str],
    ) -> None:
        """Preserve human labels while enforcing exactly one estate label."""
        if not self.apply:
            return
        current = [name for name in existing_labels if name]
        preserved = [name for name in current if not name.startswith("estate:")]
        labels = sorted(set([*preserved, label]))
        if sorted(set(current)) == labels:
            return
        self.ensure_label(full_name, label)
        self.request(
            "PATCH",
            f"/repos/{full_name}/issues/{number}",
            {"labels": labels},
            expected=(200,),
        )

    def comment(self, full_name: str, number: int, body: str) -> None:
        if not self.apply:
            return
        self.request(
            "POST",
            f"/repos/{full_name}/issues/{number}/comments",
            {"body": body},
            expected=(201,),
        )

    def close_duplicate(self, full_name: str, number: int, canonical_url: str) -> None:
        if not self.apply:
            return
        body = (
            f"{DUPLICATE_MARKER}\n"
            "Closing this issue because its normalized title and body are byte-equivalent to "
            f"the newer canonical issue: {canonical_url}. No underlying defect is being declared fixed."
        )
        self.comment(full_name, number, body)
        self.request(
            "PATCH",
            f"/repos/{full_name}/issues/{number}",
            {"state": "closed", "state_reason": "not_planned"},
            expected=(200,),
        )

    def upsert_command_center(self, org: str, body: str) -> str:
        query = f'org:{org} repo:{org}/.github is:issue in:title "{COMMAND_CENTER_TITLE}"'
        rows = self.search(query, limit=20)
        exact = [row for row in rows if row.get("title") == COMMAND_CENTER_TITLE]
        if exact:
            target = max(exact, key=lambda row: str(row.get("updated_at") or ""))
            url = str(target.get("html_url"))
            if self.apply:
                self.request(
                    "PATCH",
                    f"/repos/{org}/.github/issues/{target['number']}",
                    {"body": body, "state": "open"},
                    expected=(200,),
                )
            return url
        if not self.apply:
            return "DRY_RUN"
        self.ensure_label(f"{org}/.github", "estate:execution-ledger")
        result, _headers, _status = self.request(
            "POST",
            f"/repos/{org}/.github/issues",
            {"title": COMMAND_CENTER_TITLE, "body": body, "labels": ["estate:execution-ledger"]},
            expected=(201,),
        )
        return str(result.get("html_url") or "UNKNOWN")


def repository_from_api_url(url: str) -> str:
    parts = url.rstrip("/").split("/")
    if len(parts) < 2:
        raise ValueError(f"invalid repository URL: {url!r}")
    return "/".join(parts[-2:])


def normalized_issue_text(value: str | None) -> str:
    text = (value or "").replace("\r\n", "\n")
    text = WHITESPACE.sub(" ", text).strip().casefold()
    return text


def issue_fingerprint(title: str, body: str | None) -> str | None:
    normalized_title = normalized_issue_text(title)
    normalized_body = normalized_issue_text(body)
    if not normalized_title or len(normalized_body) < 40:
        return None
    framed = f"{normalized_title}\n{normalized_body}".encode("utf-8")
    return hashlib.sha256(framed).hexdigest()


def classify_issue(title: str, body: str | None, labels: Iterable[str] = ()) -> str:
    text = " ".join([title, body or "", *labels]).casefold()
    if any(token in text for token in ("p0", "critical", "unsafe", "vulnerability", "security", "credential leak", "writable evidence", "pickle", "joblib")):
        return "estate:p0"
    if any(token in text for token in ("cloudflare", "dns", "token", "secret", "billing", "quota", "provider", "owner decision", "external prerequisite", "capacity")):
        return "estate:blocked-external"
    if any(token in text for token in ("runtime", "deploy", "hugging face", "hf space", "source parity", "drift", "healthz", "domain", "404", "ssl", "certificate", "unpause", "restart")):
        return "estate:runtime-drift"
    if any(token in text for token in ("workcell", "execution ledger", "command center", "reconciliation", "estate audit", "whole-thread")):
        return "estate:execution-ledger"
    if any(token in text for token in ("roadmap", "research", "benchmark", "training", "webgpu", "nemo", "chip", "kernel acceleration", "future")):
        return "estate:roadmap"
    if any(token in text for token in ("bug", "fix", "test", "docs", "readme", "ci", "workflow", "dependency", "frontend", "mobile", "accessibility", "api")):
        return "estate:code-actionable"
    return "estate:backlog"


def evaluate_pr(api: GitHub, item: dict[str, Any]) -> PullRequestState:
    repository = repository_from_api_url(str(item["repository_url"]))
    number = int(item["number"])
    row = PullRequestState(
        repository=repository,
        number=number,
        title=str(item.get("title") or ""),
        url=str(item.get("html_url") or ""),
    )
    try:
        repo = api.repository(repository)
        if type(repo.get("archived")) is not bool:
            raise GitHubError("repository archival state is unavailable")
        if repo["archived"]:
            row.action = "READ_ONLY_ARCHIVED"
            return row
        pull = api.pull(repository, number)
        row.default_branch = str(repo.get("default_branch") or "")
        row.base_ref = str((pull.get("base") or {}).get("ref") or "")
        row.head_sha = str((pull.get("head") or {}).get("sha") or "")
        row.draft = pull.get("draft") is True
        row.mergeable = pull.get("mergeable")
        row.mergeable_state = str(pull.get("mergeable_state") or "unknown")
        row.same_repository = (
            str(((pull.get("head") or {}).get("repo") or {}).get("full_name") or "")
            == repository
        )
        if row.head_sha:
            row.checks = api.checks(repository, row.head_sha)
        row.changes_requested_by = api.reviews(repository, number)
        row.unresolved_threads = api.unresolved_threads(repository, number)

        if row.draft:
            row.blockers.append("draft")
        if not row.same_repository:
            row.blockers.append("external-fork")
        if row.base_ref != row.default_branch:
            row.blockers.append("non-default-base")
        if row.mergeable is not True:
            row.blockers.append("mergeability-not-clean")
        if row.mergeable_state not in SAFE_MERGE_STATES:
            row.blockers.append(f"merge-state:{row.mergeable_state}")
        if row.checks.count == 0:
            row.blockers.append("no-check-evidence")
        if row.checks.failed:
            row.blockers.append("failed-checks")
        if row.checks.active:
            row.blockers.append("active-checks")
        if row.changes_requested_by:
            row.blockers.append("changes-requested")
        if row.unresolved_threads is None or row.unresolved_threads > 0:
            row.blockers.append("unresolved-review-threads")

        if not row.blockers and row.head_sha:
            row.merge_sha = api.merge(repository, number, row.head_sha, row.title)
            row.action = "WOULD_MERGE" if not api.apply else "MERGED"
        else:
            row.action = "BLOCKED"
    except Exception as exc:  # each PR remains independently observable
        row.error = str(redact(str(exc)))
        row.action = "ERROR"
    return row


def issue_rows(api: GitHub, org: str, *, limit: int) -> list[dict[str, Any]]:
    rows = api.search(f"org:{org} is:issue is:open", limit=limit)
    return [row for row in rows if "pull_request" not in row]


def reconcile_issues(api: GitHub, org: str, *, limit: int) -> list[IssueState]:
    raw = issue_rows(api, org, limit=limit)
    # Duplicate closure is repository-local. Identical text can represent an
    # independently valid defect when filed against two different components.
    by_fingerprint: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in raw:
        repository = repository_from_api_url(str(row["repository_url"]))
        fingerprint = issue_fingerprint(str(row.get("title") or ""), row.get("body"))
        if fingerprint:
            by_fingerprint[(repository, fingerprint)].append(row)

    canonical_for: dict[tuple[str, str], dict[str, Any]] = {}
    for fingerprint, group in by_fingerprint.items():
        if len(group) > 1:
            canonical_for[fingerprint] = max(
                group,
                key=lambda row: (str(row.get("updated_at") or ""), int(row.get("number") or 0)),
            )

    results: list[IssueState] = []
    # Archived repositories remain part of the observation, never a write target.
    # Cache metadata once per repository; an API failure remains a failure.
    repository_cache: dict[str, dict[str, Any] | Exception] = {}
    for row in raw:
        repository = repository_from_api_url(str(row["repository_url"]))
        labels = [str(label.get("name") or "") for label in row.get("labels") or []]
        classification_labels = [
            label for label in labels if not label.startswith("estate:")
        ]
        classification = classify_issue(
            str(row.get("title") or ""), row.get("body"), classification_labels
        )
        state = IssueState(
            repository=repository,
            number=int(row["number"]),
            title=str(row.get("title") or ""),
            url=str(row.get("html_url") or ""),
            updated_at=str(row.get("updated_at") or ""),
            classification=classification,
        )
        try:
            if repository not in repository_cache:
                try:
                    repository_cache[repository] = api.repository(repository)
                except Exception as exc:
                    repository_cache[repository] = exc
            repo = repository_cache[repository]
            if isinstance(repo, Exception):
                raise GitHubError("repository metadata could not be observed")
            if not isinstance(repo, dict) or type(repo.get("archived")) is not bool:
                raise GitHubError("repository archival state is unavailable")
            if repo["archived"]:
                state.action = "READ_ONLY_ARCHIVED"
                results.append(state)
                continue
            fingerprint = issue_fingerprint(state.title, row.get("body"))
            canonical = canonical_for.get((repository, fingerprint or ""))
            if canonical and int(canonical["number"]) != state.number:
                state.duplicate_of = str(canonical.get("html_url") or "")
                api.close_duplicate(repository, state.number, state.duplicate_of)
                state.action = "WOULD_CLOSE_EXACT_DUPLICATE" if not api.apply else "CLOSED_EXACT_DUPLICATE"
            else:
                api.set_classification(
                    repository, state.number, classification, labels
                )
                state.action = "WOULD_CLASSIFY" if not api.apply else "CLASSIFIED"
        except Exception as exc:
            state.error = str(redact(str(exc)))
            state.action = "ERROR"
        results.append(state)
    return results


def command_center_body(
    *,
    org: str,
    apply: bool,
    pulls: list[PullRequestState],
    issues: list[IssueState],
) -> str:
    issue_counts = Counter(row.classification for row in issues if row.action not in {"CLOSED_EXACT_DUPLICATE", "READ_ONLY_ARCHIVED"})
    repository_counts = Counter(row.repository for row in issues if row.action not in {"CLOSED_EXACT_DUPLICATE", "READ_ONLY_ARCHIVED"})
    merged = [row for row in pulls if row.action == "MERGED"]
    blocked = [row for row in pulls if row.action == "BLOCKED"]
    errors = [row for row in pulls if row.action == "ERROR"] + [row for row in issues if row.action == "ERROR"]
    lines = [
        COMMAND_CENTER_MARKER,
        "# Frontier issue command center",
        "",
        f"Generated: `{utc_now()}`",
        f"Mode: `{'APPLY' if apply else 'DRY_RUN'}`",
        "",
        "This ledger is machine-generated. It does not treat reachability as readiness, does not close unresolved work, and does not bypass repository protections.",
        "",
        "## Pull-request convergence",
        "",
        f"- Observed: **{len(pulls)}**",
        f"- Merged this pass: **{len(merged)}**",
        f"- Still blocked or active: **{len(blocked)}**",
        f"- Operator errors: **{len(errors)}**",
        f"- Read-only archived issues: **{sum(row.action == 'READ_ONLY_ARCHIVED' for row in issues)}**",
    ]
    for row in blocked[:50]:
        lines.append(
            f"- `{row.repository}#{row.number}` — {row.title} — `{', '.join(row.blockers)}`"
        )
    lines += ["", "## Open-issue classification", ""]
    for label in LABELS:
        lines.append(f"- `{label}`: **{issue_counts.get(label, 0)}**")
    lines += ["", "## Repositories with the largest active queues", ""]
    for repository, count in repository_counts.most_common(30):
        lines.append(f"- `{repository}`: **{count}**")
    lines += [
        "",
        "## Mutation boundaries",
        "",
        "- Pull requests merge only after clean exact-head checks and review state.",
        "- Only exact normalized duplicate issues are closed automatically.",
        "- Provider credentials, DNS, billing, quotas, branch protection, visibility, archive state, models, datasets, and runtime allocations are not changed.",
        "- Token values are neither printed nor persisted.",
    ]
    if errors:
        lines += ["", "## Operator errors", ""]
        for row in errors[:50]:
            lines.append(
                f"- `{row.repository}#{row.number}` — `{redact(row.error or 'unknown')}`"
            )
    return "\n".join(lines) + "\n"


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = redact(payload)
    path.write_text(json.dumps(safe, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default=DEFAULT_ORG)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, default=Path("frontier-issue-operator.json"))
    parser.add_argument("--max-prs", type=int, default=300)
    parser.add_argument("--max-issues", type=int, default=1000)
    args = parser.parse_args(argv)

    token = (
        os.environ.get("SZL_ORG_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    ).strip()
    if args.apply and not token:
        payload = {
            "schema": REPORT_SCHEMA,
            "status": "BLOCKED_MANAGED_PREREQUISITE",
            "error": "Apply mode requires an organization-capable GitHub token.",
            "token_value_recorded": False,
            "generated_at": utc_now(),
        }
        write_report(args.report, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 2

    api = GitHub(token, apply=args.apply)
    started = utc_now()
    pulls: list[PullRequestState] = []
    # Up to three passes allow merges that unblock stacked same-repository PRs.
    observed_keys: set[tuple[str, int, str | None]] = set()
    for _pass in range(3):
        raw = api.search(f"org:{args.org} is:pr is:open", limit=args.max_prs)
        current: list[PullRequestState] = []
        for item in raw:
            state = evaluate_pr(api, item)
            current.append(state)
            key = (state.repository, state.number, state.head_sha)
            if key not in observed_keys:
                pulls.append(state)
                observed_keys.add(key)
        if not args.apply or not any(row.action == "MERGED" for row in current):
            break

    issues = reconcile_issues(api, args.org, limit=args.max_issues)
    body = command_center_body(org=args.org, apply=args.apply, pulls=pulls, issues=issues)
    command_center_url = "UNAVAILABLE"
    command_center_error = None
    try:
        command_center_url = api.upsert_command_center(args.org, body)
    except Exception as exc:
        command_center_error = str(redact(str(exc)))

    final_prs = api.search(f"org:{args.org} is:pr is:open", limit=args.max_prs)
    final_issues = issue_rows(api, args.org, limit=args.max_issues)
    operation_errors = sum(row.action == "ERROR" for row in [*pulls, *issues])
    incomplete = bool(operation_errors or command_center_error)
    payload = {
        "schema": REPORT_SCHEMA,
        "status": "PARTIAL_FAILURE" if incomplete else "COMPLETE",
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "organization": args.org,
        "started_at": started,
        "finished_at": utc_now(),
        "token_value_recorded": False,
        "pull_requests": [
            {**asdict(row), "checks": asdict(row.checks)} for row in pulls
        ],
        "issues": [asdict(row) for row in issues],
        "summary": {
            "observed_pull_requests": len(pulls),
            "merged_pull_requests": sum(row.action == "MERGED" for row in pulls),
            "blocked_pull_requests": sum(row.action == "BLOCKED" for row in pulls),
            "pull_request_errors": sum(row.action == "ERROR" for row in pulls),
            "observed_issues": len(issues),
            "closed_exact_duplicates": sum(row.action == "CLOSED_EXACT_DUPLICATE" for row in issues),
            "classified_issues": sum(row.action == "CLASSIFIED" for row in issues),
            "read_only_archived_issues": sum(row.action == "READ_ONLY_ARCHIVED" for row in issues),
            "read_only_archived_pull_requests": sum(row.action == "READ_ONLY_ARCHIVED" for row in pulls),
            "issue_errors": sum(row.action == "ERROR" for row in issues),
            "final_open_pull_requests": len(final_prs),
            "final_open_issues": len(final_issues),
            "classification_counts": dict(Counter(row.classification for row in issues)),
        },
        "command_center_url": command_center_url,
        "command_center_error": command_center_error,
    }
    write_report(args.report, payload)
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    return 1 if incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())
