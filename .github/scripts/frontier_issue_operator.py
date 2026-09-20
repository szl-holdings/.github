#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Public-only estate observation and explicitly authorized merge-queue requests.

Scheduled runs observe and suggest; they never merge pull requests, close issues,
replace labels, or change repository/provider settings. Queue admission requires
one unexpired authorization from exact protected source plus a manual dispatch.
Public output contains only allowlisted metadata, not titles, bodies, reviewers,
check names, provider errors, or private-repository identifiers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import base64
import tempfile
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable

API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"
MAX_API_BYTES = 10 * 1024 * 1024
DEFAULT_ORG = "szl-holdings"
REPORT_SCHEMA = "szl.frontier-issue-operator/v1"
COMMAND_CENTER_TITLE = "[estate] Frontier issue command center"
COMMAND_CENTER_MARKER = "<!-- SZL-FRONTIER-ISSUE-COMMAND-CENTER-V1 -->"
COMMAND_CENTER_NUMBER = 585
CONTROLLER_REPO = "szl-holdings/.github"
AUTHORIZATION_PATH = "config/estate-pr-authorizations.json"
AUTHORIZATION_SCHEMA = "szl.estate-pr-authorizations/v1"
QUEUE_ACKNOWLEDGEMENT = "ENQUEUE_EXACT_REVIEWED_HEAD"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
REPOSITORY = re.compile(r"szl-holdings/[A-Za-z0-9_.-]{1,100}\Z")
QUEUE_MUTATION = """mutation($input:EnqueuePullRequestInput!) {
  enqueuePullRequest(input:$input) { mergeQueueEntry { id pullRequest { id headRefOid } } }
}"""
QUEUE_QUERY = """query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) { id state isDraft headRefOid baseRefOid
      reviewDecision mergeQueueEntry { id pullRequest { id headRefOid } }
    }
  }
}"""
THREAD_QUERY = '\n        query($owner:String!, $name:String!, $number:Int!, $cursor:String) {\n          repository(owner:$owner, name:$name) {\n            pullRequest(number:$number) {\n              reviewThreads(first:100, after:$cursor) {\n                nodes { isResolved }\n                pageInfo { hasNextPage endCursor }\n              }\n            }\n          }\n        }\n        '
ALLOWED_CHECK_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})
FAILED_CHECK_CONCLUSIONS = frozenset(
    {"failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"}
)
ACTIVE_CHECK_STATES = frozenset({"queued", "in_progress", "pending", "requested", "waiting"})
SAFE_MERGE_STATES = frozenset({"clean", "has_hooks"})
TOKEN_PATTERN = re.compile(r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,})")

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
    public_verified: bool = False


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
    public_verified: bool = False


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
        self._queue_permit: tuple[str, str] | None = None
        self._queue_input: dict[str, Any] | None = None
        self._report_body: str | None = None
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
        # This is an allowlist of effects, not merely a dry-run convention.
        if method != "GET":
            allowed = False
            if method == "POST" and url == GRAPHQL and isinstance(payload, dict):
                if set(payload) == {"query", "variables"}:
                    query, variables = payload["query"], payload["variables"]
                    allowed = query in (THREAD_QUERY, QUEUE_QUERY) and isinstance(variables, dict)
                    if query == QUEUE_MUTATION:
                        allowed = (self.apply is True and self._queue_input is not None
                                   and variables == {"input": self._queue_input})
            if (method == "PATCH" and path == f"/repos/{CONTROLLER_REPO}/issues/{COMMAND_CENTER_NUMBER}"
                    and self._report_body is not None):
                allowed = payload == {"body": self._report_body}
            if not allowed:
                raise GitHubError("mutation is outside the operator capability")
        elif payload is not None:
            raise GitHubError("GET requests cannot contain a body")
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
                result = strict_json(raw) if raw else None
                status = response.status
                response_headers = dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            # Error pages, Location headers and transport messages can contain
            # credentials or private text. Keep only a numeric status class.
            raise GitHubError(f"GitHub HTTP {exc.code}") from None
        except (urllib.error.URLError, OSError, ValueError):
            raise GitHubError("GitHub transport or JSON decoding failed") from None
        if status not in set(expected):
            raise GitHubError(f"unexpected GitHub HTTP status {status}")
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
        query = THREAD_QUERY
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


    def merge(self, *args: Any, **kwargs: Any) -> str:
        """Reject obsolete callers rather than silently restoring unsafe behavior."""
        raise GitHubError("immediate merge is not an operator capability")

    def close_duplicate(self, *args: Any, **kwargs: Any) -> None:
        raise GitHubError("issue closure requires a separate reviewed disposition")

    def set_classification(self, *args: Any, **kwargs: Any) -> None:
        raise GitHubError("classification is advisory; issue labels are not replaced")

    def queue_snapshot(self, repository: str, number: int) -> dict[str, Any]:
        owner, name = repository.split("/", 1)
        data = self.graphql(QUEUE_QUERY, {"owner": owner, "name": name, "number": number})
        repo = data.get("repository")
        pull = repo.get("pullRequest") if isinstance(repo, dict) else None
        if not isinstance(pull, dict):
            raise GitHubError("queue observation unavailable")
        return pull

    def enqueue_exact(self, node_id: str, sha: str) -> Any:
        if (self.apply is not True or self._queue_permit != (node_id, sha)
                or not isinstance(node_id, str) or not node_id or not SHA40.fullmatch(sha)):
            raise GitHubError("queue capability unavailable")
        self._queue_input = {"pullRequestId": node_id, "expectedHeadOid": sha, "jump": False}
        try:
            # Exactly one send; ambiguous outcomes are handled only by readback.
            return self.graphql(QUEUE_MUTATION, {"input": self._queue_input})
        finally:
            self._queue_input = None

    def publish_command_center(self, pulls: list[PullRequestState], issues: list[IssueState]) -> str:
        """Update only the already-owned machine body; never create/reopen an issue."""
        source = protected_source(self)
        if not is_public_repository(self.repository(CONTROLLER_REPO), CONTROLLER_REPO):
            raise GitHubError("public report target unavailable")
        path = f"/repos/{CONTROLLER_REPO}/issues/{COMMAND_CENTER_NUMBER}"
        target, _, _ = self.request("GET", path)
        if (not isinstance(target, dict) or target.get("number") != COMMAND_CENTER_NUMBER
                or target.get("title") != COMMAND_CENTER_TITLE
                or target.get("state") != "open" or "pull_request" in target
                or (target.get("user") or {}).get("login") != "stephenlutar2-hash"
                or not isinstance(target.get("body"), str)
                or not target["body"].startswith(COMMAND_CENTER_MARKER)):
            raise GitHubError("machine report ownership did not match")
        # Both the report and the current visibility are checked again at the
        # publication boundary. No private rows or free text enter the body.
        for row in [*pulls, *issues]:
            if row.public_verified:
                row.public_verified = is_public_repository(self.repository(row.repository), row.repository)
        body = command_center_body(org=DEFAULT_ORG, apply=False, pulls=pulls, issues=issues)
        if protected_source(self) != source:
            raise GitHubError("controller moved before public report publication")
        if target["body"] != body:
            self._report_body = body
            try:
                self.request("PATCH", path, {"body": body})
            finally:
                self._report_body = None
        observed, _, _ = self.request("GET", path)
        if not isinstance(observed, dict) or observed.get("body") != body:
            raise GitHubError("machine report write requires readback")
        return f"https://github.com/{CONTROLLER_REPO}/issues/{COMMAND_CENTER_NUMBER}"


def strict_json(raw: bytes | str) -> Any:
    """Refuse duplicate keys and non-finite values rather than selecting a side."""
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def nonfinite(value: str) -> None:
        raise ValueError("non-finite JSON value")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def repository_from_api_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(api_url(url))
    name = parsed.path.removeprefix("/repos/")
    if (not parsed.path.startswith("/repos/") or parsed.query or not REPOSITORY.fullmatch(name)
            or name.split("/")[1] in {".", ".."}):
        raise GitHubError("repository identity is outside the public estate")
    return name


def is_public_repository(value: Any, expected: str) -> bool:
    return (isinstance(value, dict) and REPOSITORY.fullmatch(expected) is not None
            and value.get("full_name") == expected and value.get("private") is False
            and value.get("visibility") == "public")


def normalized_issue_text(value: str | None) -> str:
    # Code, paths, whitespace and case can change meaning. No lossy normalization.
    return value if isinstance(value, str) else ""


def issue_fingerprint(title: str, body: str | None) -> str | None:
    if not isinstance(title, str) or not title or not isinstance(body, str) or len(body) < 40:
        return None
    # JSON framing prevents delimiter collisions. Hashes remain in memory only.
    return hashlib.sha256(json.dumps([title, body], ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()


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
        if not is_public_repository(repo, repository):
            raise GitHubError("public repository identity could not be verified")
        row.public_verified = True
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
            row.action = "REVIEW_CANDIDATE"
        else:
            row.action = "BLOCKED"
    except Exception:  # each PR remains independently observable
        row.error = "OBSERVATION_FAILED"
        row.action = "ERROR"
    return row


def issue_rows(api: GitHub, org: str, *, limit: int) -> list[dict[str, Any]]:
    rows = api.search(f"org:{org} is:issue is:open is:public", limit=limit)
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
            canonical_for[fingerprint] = min(group, key=lambda row: int(row["number"]))

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
            if not is_public_repository(repo, repository):
                raise GitHubError("public repository identity could not be verified")
            state.public_verified = True
            if repo["archived"]:
                state.action = "READ_ONLY_ARCHIVED"
                results.append(state)
                continue
            fingerprint = issue_fingerprint(state.title, row.get("body"))
            canonical = canonical_for.get((repository, fingerprint or ""))
            if canonical and int(canonical["number"]) != state.number:
                state.duplicate_of = str(canonical.get("html_url") or "")
                state.action = "DUPLICATE_CANDIDATE"
            else:
                state.action = "CLASSIFICATION_PROPOSED"
        except Exception:
            state.error = "OBSERVATION_FAILED"
            state.action = "ERROR"
        results.append(state)
    return results


PUBLIC_ACTIONS = frozenset({"REVIEW_CANDIDATE", "BLOCKED", "ERROR", "READ_ONLY_ARCHIVED",
    "DUPLICATE_CANDIDATE", "CLASSIFICATION_PROPOSED"})
PUBLIC_BLOCKERS = frozenset({"draft", "external-fork", "non-default-base", "mergeability-not-clean",
    "no-check-evidence", "failed-checks", "active-checks", "changes-requested", "unresolved-review-threads"})


def public_row(row: PullRequestState | IssueState) -> dict[str, Any] | None:
    """A projection, not a redaction regex: never serialize free-form content."""
    if (row.public_verified is not True or not REPOSITORY.fullmatch(row.repository)
            or type(row.number) is not int or row.number <= 0):
        return None
    result: dict[str, Any] = {"repository": row.repository, "number": row.number,
        "action": row.action if row.action in PUBLIC_ACTIONS else "ERROR"}
    if isinstance(row, PullRequestState):
        result["head_sha"] = row.head_sha if isinstance(row.head_sha, str) and SHA40.fullmatch(row.head_sha) else None
        result["blockers"] = sorted({item if item in PUBLIC_BLOCKERS else "OTHER_REVIEW_BLOCKER" for item in row.blockers})
        result["checks"] = {"passed": len(row.checks.passed), "failed": len(row.checks.failed), "active": len(row.checks.active)}
    else:
        result["classification"] = row.classification if row.classification in LABELS else "estate:backlog"
        # Reconstruct links from validated identities, never from issue text/API URLs.
        match = re.fullmatch(r"https://github\.com/" + re.escape(row.repository) + r"/issues/([1-9][0-9]*)", row.duplicate_of or "")
        result["possible_duplicate_of"] = int(match[1]) if match else None
    result["url"] = f"https://github.com/{row.repository}/{'pull' if isinstance(row, PullRequestState) else 'issues'}/{row.number}"
    return result


def refresh_public_scope(api: GitHub, rows: list[Any]) -> None:
    observed: dict[str, bool] = {}
    for row in rows:
        if row.public_verified:
            if row.repository not in observed:
                try:
                    observed[row.repository] = is_public_repository(api.repository(row.repository), row.repository)
                except Exception:
                    observed[row.repository] = False
            row.public_verified = observed[row.repository]
            if not row.public_verified:
                row.action, row.error = "ERROR", "PUBLIC_SCOPE_UNAVAILABLE"


def command_center_body(*, org: str, apply: bool, pulls: list[PullRequestState], issues: list[IssueState]) -> str:
    # Fixed publisher identity and generated prose prevent Markdown injection,
    # private-repository aggregation and reflective provider-error disclosure.
    if org != DEFAULT_ORG:
        raise GitHubError("public report organization mismatch")
    public_pulls = [item for row in pulls if (item := public_row(row)) is not None]
    public_issues = [item for row in issues if (item := public_row(row)) is not None]
    counts = Counter(row["classification"] for row in public_issues if row["action"] != "READ_ONLY_ARCHIVED")
    lines = [COMMAND_CENTER_MARKER, "# Frontier issue command center", "",
        f"Generated: `{utc_now()}`", "Mode: `PUBLIC_OBSERVATION`", "",
        ("Scope: public search-visible items only, with repository visibility rechecked before publication. "
         + "Private repositories and security alerts are NOT OBSERVED. This is not a complete organization audit, "
         + "a security clearance, a model qualification, or a runtime-readiness certificate."), "",
        "## Public pull-request observations", "",
        f"- Observed public pull requests: **{len(public_pulls)}**",
        "- Immediate merges: **0**",
        f"- Operator errors: **{sum(row.action == 'ERROR' for row in [*pulls, *issues])}**"]
    for row in public_pulls[:100]:
        lines.append(f"- [{row['repository']}#{row['number']}]({row['url']}) — `{row['action']}`")
    lines += ["", "## Advisory public-issue classifications", ""]
    for label in LABELS:
        lines.append(f"- `{label}`: **{counts.get(label, 0)}**")
    lines += ["", "Classification is a keyword-based triage suggestion, not a confirmed severity or resolution.",
        "Matching text is only a duplicate candidate. No issue is closed and no human labels are replaced.",
        "", "## Authority", "",
        ("Queue requests require one unexpired exact-head authorization from protected source and explicit manual dispatch. "
         + "Normal GitHub checks, signatures, review-thread resolution and the merge queue remain authoritative. "
         + "A queue request is not a merge or deployment claim."), "",
        "Source repair and estate work remain tracked in #740 and #694. API observations are bounded and non-atomic."]
    return "\n".join(lines) + "\n"


def write_report(path: Path, payload: dict[str, Any]) -> None:
    """Atomically replace only a report assembled from public_row and fixed codes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # This defense supplements the positive projection; it does not prove that
    # arbitrary input is safe to publish. Callers never pass raw API data here.
    text = json.dumps(redact(payload), indent=2, sort_keys=True, allow_nan=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=".frontier-report-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(api: GitHub, path: str) -> Any:
    value, _, _ = api.request("GET", path)
    return value


def timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise GitHubError("authorization timestamp must be exact UTC")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise GitHubError("authorization timestamp is invalid") from None


def validate_authorizations(value: Any, authorization_id: str, now: datetime) -> dict[str, Any]:
    if (not isinstance(value, dict) or set(value) != {"schema", "authorizations"}
            or value["schema"] != AUTHORIZATION_SCHEMA or not isinstance(value["authorizations"], list)
            or len(value["authorizations"]) > 25):
        raise GitHubError("authorization collection is invalid")
    required = {"id", "repository", "pr_number", "head_sha", "base_sha", "not_before", "expires_at", "rules_sha256"}
    ids, targets = set(), set()
    selected = None
    for row in value["authorizations"]:
        if not isinstance(row, dict) or set(row) != required:
            raise GitHubError("authorization fields are invalid")
        identity, repo, number = row["id"], row["repository"], row["pr_number"]
        if (not isinstance(identity, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", identity)
                or identity in ids or not isinstance(repo, str) or not REPOSITORY.fullmatch(repo)
                or repo.split("/")[1] in {".", ".."} or type(number) is not int or number <= 0
                or (repo, number) in targets):
            raise GitHubError("authorization identity is invalid or duplicated")
        ids.add(identity)
        targets.add((repo, number))
        for key in ("head_sha", "base_sha"):
            if not isinstance(row[key], str) or not SHA40.fullmatch(row[key]):
                raise GitHubError("authorization requires an exact commit")
        if not isinstance(row["rules_sha256"], str) or not SHA256.fullmatch(row["rules_sha256"]):
            raise GitHubError("authorization requires an effective-rules digest")
        start, end = timestamp(row["not_before"]), timestamp(row["expires_at"])
        if not timedelta(0) < end - start <= timedelta(hours=24):
            raise GitHubError("authorization lifetime exceeds 24 hours")
        if identity == authorization_id:
            if not start <= now < end:
                raise GitHubError("selected authorization is not currently valid")
            selected = row
    if selected is None:
        raise GitHubError("no exact protected authorization was selected")
    return dict(selected)


def protected_source(api: GitHub) -> str:
    source = os.environ.get("GITHUB_SHA", "")
    if (not SHA40.fullmatch(source) or os.environ.get("GITHUB_REPOSITORY") != CONTROLLER_REPO
            or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_REF_PROTECTED") != "true"):
        raise GitHubError("protected controller context is required")
    branch = read_json(api, f"/repos/{CONTROLLER_REPO}/branches/main")
    if (not isinstance(branch, dict) or branch.get("protected") is not True
            or (branch.get("commit") or {}).get("sha") != source):
        raise GitHubError("protected controller source moved or is unavailable")
    return source


def dispatch_authorization(api: GitHub, authorization_id: str, acknowledgement: str) -> tuple[str, dict[str, Any]]:
    if acknowledgement != QUEUE_ACKNOWLEDGEMENT or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", authorization_id):
        raise GitHubError("manual exact-head acknowledgement is required")
    if (os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
            or os.environ.get("GITHUB_RUN_ATTEMPT") != "1"
            or os.environ.get("GITHUB_WORKFLOW_REF") != f"{CONTROLLER_REPO}/.github/workflows/frontier-issue-operator.yml@refs/heads/main"):
        raise GitHubError("only a first-attempt protected manual dispatch may enqueue")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if not re.fullmatch(r"[1-9][0-9]{0,19}", run_id):
        raise GitHubError("workflow run identity is unavailable")
    source = protected_source(api)
    run = read_json(api, f"/repos/{CONTROLLER_REPO}/actions/runs/{run_id}")
    if (not isinstance(run, dict) or run.get("id") != int(run_id)
            or run.get("head_sha") != source or run.get("head_branch") != "main"
            or run.get("event") != "workflow_dispatch" or run.get("run_attempt") != 1
            or run.get("status") != "in_progress"
            or run.get("path") != ".github/workflows/frontier-issue-operator.yml"):
        raise GitHubError("workflow run is not the expected live protected dispatch")
    content = read_json(api, f"/repos/{CONTROLLER_REPO}/contents/{AUTHORIZATION_PATH}?ref={source}")
    if (not isinstance(content, dict) or content.get("type") != "file"
            or content.get("path") != AUTHORIZATION_PATH or content.get("encoding") != "base64"
            or type(content.get("size")) is not int or not 0 < content["size"] <= 32768
            or not isinstance(content.get("content"), str) or len(content["content"]) > 50000):
        raise GitHubError("protected authorization file is unavailable")
    try:
        raw = base64.b64decode(content["content"].replace("\n", ""), validate=True)
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False).hexdigest()
        if len(raw) != content["size"] or content.get("sha") != blob:
            raise ValueError("source blob mismatch")
        policy = strict_json(raw)
    except (ValueError, TypeError, UnicodeError):
        raise GitHubError("protected authorization bytes are invalid") from None
    return source, validate_authorizations(policy, authorization_id, datetime.now(timezone.utc))


def effective_rules(api: GitHub, repo: str, branch: str) -> list[dict[str, Any]]:
    # Read the provider's effective branch rules, including inherited rules.
    # No ruleset or branch-protection mutation endpoint exists in this operator.
    rows = read_json(api, f"/repos/{repo}/rules/branches/{urllib.parse.quote(branch, safe='')}?per_page=100&page=1")
    if not isinstance(rows, list) or not 1 <= len(rows) < 100 or not all(isinstance(row, dict) and isinstance(row.get("type"), str) for row in rows):
        raise GitHubError("effective branch-rule coverage is unavailable or truncated")
    return rows


def rules_digest(rows: list[dict[str, Any]]) -> str:
    framed = sorted(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) for row in rows)
    return hashlib.sha256(json.dumps(framed, separators=(",", ":")).encode()).hexdigest()


def promotion_preflight(api: GitHub, grant: dict[str, Any]) -> dict[str, Any]:
    repo, number, head = grant["repository"], grant["pr_number"], grant["head_sha"]
    metadata = api.repository(repo)
    if not is_public_repository(metadata, repo) or metadata.get("archived") is not False:
        raise GitHubError("promotion target is not a verified active public repository")
    branch = metadata.get("default_branch")
    if not isinstance(branch, str) or not branch:
        raise GitHubError("default branch unavailable")
    branch_state = read_json(api, f"/repos/{repo}/branches/{urllib.parse.quote(branch, safe='')}")
    if (not isinstance(branch_state, dict) or branch_state.get("protected") is not True
            or (branch_state.get("commit") or {}).get("sha") != grant["base_sha"]):
        raise GitHubError("protected target base moved or is unavailable")
    rules = effective_rules(api, repo, branch)
    if rules_digest(rules) != grant["rules_sha256"]:
        raise GitHubError("effective target rules differ from the authorization")
    types = {row.get("type") for row in rules}
    if not {"pull_request", "required_status_checks", "required_signatures", "non_fast_forward", "deletion", "merge_queue"} <= types:
        raise GitHubError("protected queue or required safety controls are absent")
    requirements: list[dict[str, Any]] = []
    needs_approval = False
    for rule in rules:
        parameters = rule.get("parameters") or {}
        if not isinstance(parameters, dict):
            raise GitHubError("rule parameters are malformed")
        if rule.get("type") == "merge_queue" and parameters.get("merge_method") != "SQUASH":
            raise GitHubError("only the protected squash queue is supported")
        if not isinstance(parameters, dict):
            raise GitHubError("rule parameters are malformed")
        if rule.get("type") == "pull_request":
            if parameters.get("required_review_thread_resolution") is not True:
                raise GitHubError("review-thread protection is required")
            approvals = parameters.get("required_approving_review_count")
            if type(approvals) is not int or approvals < 0:
                raise GitHubError("approval policy is unavailable")
            needs_approval = needs_approval or approvals > 0 or any(
                parameters.get(key) is not False for key in ("require_code_owner_review", "require_last_push_approval"))
        if rule.get("type") == "required_status_checks":
            if parameters.get("strict_required_status_checks_policy") is not True:
                raise GitHubError("strict required checks are required")
            contexts = parameters.get("required_status_checks")
            if not isinstance(contexts, list) or not contexts:
                raise GitHubError("required-check configuration is empty or malformed")
            requirements.extend(contexts)
    pull = api.pull(repo, number)
    if (pull.get("number") != number or type(pull.get("number")) is not int
            or not isinstance(pull.get("node_id"), str) or not pull["node_id"]
            or pull.get("state") != "open" or pull.get("draft") is not False
            or pull.get("merged") is not False or pull.get("mergeable") is not True
            or pull.get("mergeable_state") not in SAFE_MERGE_STATES
            or (pull.get("base") or {}).get("ref") != branch
            or (pull.get("base") or {}).get("sha") != grant["base_sha"]
            or ((pull.get("base") or {}).get("repo") or {}).get("full_name") != repo
            or (pull.get("head") or {}).get("sha") != head
            or ((pull.get("head") or {}).get("repo") or {}).get("full_name") != repo):
        raise GitHubError("pull request is not the exact ready internal candidate")
    labels = pull.get("labels")
    if not isinstance(labels, list):
        raise GitHubError("pull-request labels are unavailable")
    for label in labels:
        name = label.get("name") if isinstance(label, dict) else None
        if not isinstance(name, str) or re.search(r"hold|blocked|do[ -]?not[ -]?merge|wip|awaiting[ -]?evidence", name, re.I):
            raise GitHubError("pull-request label requires review or evidence")
    # The provider queue retains its own signature rules. This additional
    # exact-head observation never substitutes a locally manufactured signature.
    commit = read_json(api, f"/repos/{repo}/commits/{head}")
    if (not isinstance(commit, dict) or commit.get("sha") != head
            or ((commit.get("commit") or {}).get("verification") or {}).get("verified") is not True):
        raise GitHubError("exact candidate signature is not verified")
    observed = api.checks(repo, head)
    if observed.count == 0 or observed.failed or observed.active:
        raise GitHubError("check evidence is absent, failed, or active")
    check_rows = api.counted_pages(f"/repos/{repo}/commits/{head}/check-runs", "check_runs")
    status_rows = api.counted_pages(f"/repos/{repo}/commits/{head}/status", "statuses", sha=head)
    for requirement in requirements:
        name = requirement.get("context") if isinstance(requirement, dict) else None
        app = requirement.get("integration_id") if isinstance(requirement, dict) else None
        if not isinstance(name, str) or not name or (app is not None and (type(app) is not int or app <= 0)):
            raise GitHubError("required-check identity is malformed")
        candidates = [row for row in check_rows if row.get("name") == name
            and (app is None or (row.get("app") or {}).get("id") == app)]
        if candidates:
            if any(row.get("head_sha") != head or row.get("status") != "completed"
                    or row.get("conclusion") != "success" for row in candidates):
                raise GitHubError("required exact-head check did not succeed")
        elif app is None:
            statuses = [row for row in status_rows if row.get("context") == name]
            if not statuses or any(row.get("state") != "success" for row in statuses):
                raise GitHubError("required status was not successfully observed")
        else:
            # Legacy statuses do not independently identify an integration ID.
            raise GitHubError("required check application could not be verified")
    if api.reviews(repo, number) or api.unresolved_threads(repo, number) != 0:
        raise GitHubError("review changes or threads remain outstanding")
    snapshot = api.queue_snapshot(repo, number)
    if needs_approval and snapshot.get("reviewDecision") != "APPROVED":
        raise GitHubError("required approval decision is not verified")
    if (snapshot.get("state") != "OPEN" or snapshot.get("isDraft") is not False
            or snapshot.get("headRefOid") != head or snapshot.get("baseRefOid") != grant["base_sha"]
            or snapshot.get("reviewDecision") not in {None, "APPROVED"}
            or snapshot.get("id") != pull["node_id"]):
        raise GitHubError("fresh queue identity or review decision does not match")
    return snapshot


def execute_authorized_queue(api: GitHub, authorization_id: str, acknowledgement: str,
        save_stage: Any) -> dict[str, str]:
    """One explicit grant, two full preflights, one send, independent readback.

    save_stage persists public fixed-state evidence before the first possible
    mutation. A transport exception never triggers a second mutation call.
    """
    source, grant = dispatch_authorization(api, authorization_id, acknowledgement)
    first = promotion_preflight(api, grant)
    source_again, current = dispatch_authorization(api, authorization_id, acknowledgement)
    if source_again != source or current != grant:
        raise GitHubError("controller source or grant changed during preflight")
    final = promotion_preflight(api, grant)
    if first.get("id") != final.get("id"):
        raise GitHubError("pull request identity changed during preflight")
    if protected_source(api) != source:
        raise GitHubError("controller source changed at the write boundary")
    if not timestamp(grant["not_before"]) <= datetime.now(timezone.utc) < timestamp(grant["expires_at"]):
        raise GitHubError("authorization expired at the write boundary")
    entry = final.get("mergeQueueEntry")
    if (isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"]
            and (entry.get("pullRequest") or {}).get("id") == final["id"]
            and (entry.get("pullRequest") or {}).get("headRefOid") == grant["head_sha"]):
        return {"state": "ALREADY_QUEUED_EXACT_HEAD"}
    if entry is not None:
        raise GitHubError("existing queue entry does not match the candidate")
    save_stage({"state": "QUEUE_WRITE_ATTEMPTED_READBACK_REQUIRED"})
    sent_error = False
    try:
        api._queue_permit = (final["id"], grant["head_sha"])
        api.enqueue_exact(final["id"], grant["head_sha"])
    except Exception:
        sent_error = True
    finally:
        api._queue_permit = None
    # Reconciliation reads never treat the send acknowledgement as proof.
    try:
        after = api.queue_snapshot(grant["repository"], grant["pr_number"])
        entry = after.get("mergeQueueEntry")
        if (after.get("id") == final["id"] and after.get("headRefOid") == grant["head_sha"]
                and after.get("state") == "OPEN" and after.get("isDraft") is False
                and isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"]
                and (entry.get("pullRequest") or {}).get("id") == final["id"]
                and (entry.get("pullRequest") or {}).get("headRefOid") == grant["head_sha"]):
            return {"state": "QUEUED_EXACT_HEAD_OBSERVED"}
    except Exception:
        # Readback failure cannot establish the write outcome. Preserve UNKNOWN
        # below, never echo provider details, and never resend the mutation.
        pass
    # Even an immediate provider merge needs a separate source/merge receipt;
    # neither absence from the queue nor an HTTP 200 qualifies that outcome here.
    return {"state": "QUEUE_WRITE_OUTCOME_UNKNOWN", "send": "ERROR" if sent_error else "ACKNOWLEDGED"}


DIAGNOSTIC_CODES = {
    "exact candidate signature is not verified": "SIGNATURE_UNVERIFIED",
    "no exact protected authorization was selected": "AUTHORIZATION_NOT_SELECTED",
    "selected authorization is not currently valid": "AUTHORIZATION_EXPIRED_OR_FUTURE",
    "authorization expired at the write boundary": "AUTHORIZATION_EXPIRED_AT_WRITE",
    "effective target rules differ from the authorization": "PROTECTION_DRIFT",
    "protected controller source moved or is unavailable": "CONTROLLER_SOURCE_UNAVAILABLE",
    "protected target base moved or is unavailable": "TARGET_BASE_MOVED",
    "required check application could not be verified": "REQUIRED_CHECK_APP_UNVERIFIED",
    "review changes or threads remain outstanding": "REVIEW_HOLD",
    "pull-request label requires review or evidence": "REVIEW_LABEL_HOLD",
    "machine report ownership did not match": "REPORT_OWNERSHIP_MISMATCH",
    "repository-scoped report credential is unavailable": "REPORT_CREDENTIAL_UNAVAILABLE",
    "GitHub HTTP 401": "API_AUTHENTICATION_DENIED",
    "GitHub HTTP 403": "API_ACCESS_DENIED",
    "GitHub HTTP 404": "API_RESOURCE_UNAVAILABLE",
    "GitHub HTTP 429": "API_RATE_LIMITED",
    "GitHub transport or JSON decoding failed": "API_TRANSPORT_UNAVAILABLE",
}


def diagnostic_code(exc: Exception) -> str:
    # The message selects a known code; it is never returned or reflected.
    return DIAGNOSTIC_CODES.get(str(exc), "OPERATOR_PRECONDITION_OR_OBSERVATION_FAILED")


def read_dispatch_inputs() -> tuple[str, str]:
    """Read inputs from the runner event, not echoed env values or command args."""
    path = Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    with path.open("rb") as handle:
        raw = handle.read(65537)
    if len(raw) > 65536:
        raise GitHubError("dispatch event exceeds its byte budget")
    value = strict_json(raw)
    inputs = value.get("inputs") if isinstance(value, dict) else None
    if not isinstance(inputs, dict) or set(inputs) != {"apply", "authorization_id", "acknowledgement"}:
        raise GitHubError("dispatch input schema is invalid")
    apply = inputs["apply"]
    if apply is not True and not (isinstance(apply, str) and apply == "true"):
        raise GitHubError("dispatch does not request apply")
    identity, acknowledgement = inputs["authorization_id"], inputs["acknowledgement"]
    if (not isinstance(identity, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", identity)
            or acknowledgement != QUEUE_ACKNOWLEDGEMENT):
        raise GitHubError("dispatch acknowledgement or identity is invalid")
    return identity, acknowledgement


def build_report(started: str, pulls: list[PullRequestState], issues: list[IssueState], *,
        apply: bool, fatal: bool = False, promotion: dict[str, str] | None = None,
        command_center: str = "NOT_REQUESTED", error_code: str | None = None) -> dict[str, Any]:
    public_pulls = [item for row in pulls if (item := public_row(row)) is not None]
    public_issues = [item for row in issues if (item := public_row(row)) is not None]
    errors = sum(row.action == "ERROR" for row in [*pulls, *issues])
    uncertain = (promotion or {}).get("state") in {"QUEUE_WRITE_ATTEMPTED_READBACK_REQUIRED", "QUEUE_WRITE_OUTCOME_UNKNOWN"}
    source = os.environ.get("GITHUB_SHA", "")
    return {"schema": REPORT_SCHEMA, "status": "PARTIAL_FAILURE" if fatal or errors or uncertain else "OBSERVATION_COMPLETE",
        "mode": "EXACT_QUEUE" if apply else "PUBLIC_OBSERVATION", "organization": DEFAULT_ORG,
        "started_at": started, "finished_at": utc_now(), "token_value_recorded": False,
        "coverage": {"scope": "public-search-visible-only", "complete_organization": False,
            "private_repositories": "NOT_OBSERVED", "security_alerts": "NOT_OBSERVED", "atomic_snapshot": False},
        "source_revision": source if SHA40.fullmatch(source) else None,
        "pull_requests": public_pulls, "issues": public_issues,
        "promotion": promotion or {"state": "NOT_REQUESTED"}, "command_center": command_center,
        "error_code": error_code if error_code in set(DIAGNOSTIC_CODES.values()) | {"OPERATOR_PRECONDITION_OR_OBSERVATION_FAILED"} else None,
        "summary": {"observed_pull_requests": len(public_pulls), "observed_issues": len(public_issues),
            "merged_pull_requests": 0, "closed_exact_duplicates": 0, "changed_issue_labels": 0,
            "pull_request_errors": sum(row.action == "ERROR" for row in pulls),
            "issue_errors": sum(row.action == "ERROR" for row in issues), "observation_failed": fatal,
            "classification_counts": dict(Counter(row["classification"] for row in public_issues))}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", choices=[DEFAULT_ORG], default=DEFAULT_ORG)
    parser.add_argument("--apply", action="store_true", help="Request one protected exact-head queue entry; never merge directly")
    parser.add_argument("--authorization-id", default="")
    parser.add_argument("--acknowledgement", default="")
    parser.add_argument("--publish-command-center", action="store_true")
    parser.add_argument("--from-dispatch-event", action="store_true")
    parser.add_argument("--report", type=Path, default=Path("frontier-issue-operator.json"))
    parser.add_argument("--max-prs", type=int, default=300)
    parser.add_argument("--max-issues", type=int, default=1000)
    args = parser.parse_args(argv)
    started = utc_now()
    token = (os.environ.get("SZL_ORG_TOKEN") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if args.apply and not token:
        payload = build_report(started, [], [], apply=True, fatal=True)
        payload["status"] = "BLOCKED_MANAGED_PREREQUISITE"
        write_report(args.report, payload)
        return 2
    api = GitHub(token, apply=args.apply)
    pulls: list[PullRequestState] = []
    issues: list[IssueState] = []
    promotion: dict[str, str] = {"state": "NOT_REQUESTED"}
    center, fatal, error_code = "NOT_REQUESTED", False, None
    def save_stage(stage: dict[str, str]) -> None:
        nonlocal promotion
        promotion = stage
        write_report(args.report, build_report(started, pulls, issues, apply=args.apply, promotion=stage))
    try:
        # Ordinary schedules cannot acquire write authority through the old bool.
        # Validate apply context before any estate-wide observation.
        if args.from_dispatch_event:
            if not args.apply:
                raise GitHubError("event inputs cannot authorize an observation-only invocation")
            args.authorization_id, args.acknowledgement = read_dispatch_inputs()
        if args.apply:
            dispatch_authorization(api, args.authorization_id, args.acknowledgement)
        raw = api.search(f"org:{DEFAULT_ORG} is:pr is:open is:public", limit=args.max_prs)
        for item in raw:
            pulls.append(evaluate_pr(api, item))
        issues = reconcile_issues(api, DEFAULT_ORG, limit=args.max_issues)
        refresh_public_scope(api, [*pulls, *issues])
        if args.apply:
            if any(row.action == "ERROR" for row in [*pulls, *issues]):
                raise GitHubError("incomplete observation cannot promote a candidate")
            promotion = execute_authorized_queue(api, args.authorization_id, args.acknowledgement, save_stage)
        if args.publish_command_center:
            protected_source(api)
            report_token = os.environ.get("SZL_REPORT_TOKEN", "").strip()
            if not report_token:
                raise GitHubError("repository-scoped report credential is unavailable")
            # The public machine issue uses only the repository token, not the
            # cross-repository reader/queue credential.
            writer = GitHub(report_token, apply=False)
            writer.publish_command_center(pulls, issues)
            center = "PUBLIC_BODY_READBACK_VERIFIED"
    except Exception as exc:
        fatal = True
        error_code = diagnostic_code(exc)
        if args.publish_command_center and center == "NOT_REQUESTED":
            center = "NOT_VERIFIED"
    refresh_public_scope(api, [*pulls, *issues])
    payload = build_report(started, pulls, issues, apply=args.apply, fatal=fatal,
        promotion=promotion, command_center=center, error_code=error_code)
    write_report(args.report, payload)
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    return 1 if payload["status"] == "PARTIAL_FAILURE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
