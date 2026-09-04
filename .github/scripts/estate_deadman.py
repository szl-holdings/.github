#!/usr/bin/env python3
"""Independent dead-man supervisor for critical SZL scheduled control planes.

The supervisor reads one repository-owned policy, calls only fixed GitHub API
routes for explicitly admitted repositories and workflow files, confirms every
failure twice, and maintains one deduplicated incident. It executes no product
code and cannot modify workflows, branches, deployments, DNS, or Hub assets.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

POLICY_SCHEMA = "szl.estate-deadman-policy/v1"
RECEIPT_SCHEMA = "szl.estate-deadman-receipt/v1"
INCIDENT_STATE_SCHEMA = "szl.estate-deadman-incident-state/v1"
GITHUB_ACTIONS_BOT = "github-actions[bot]"
CONTROLLER_WORKFLOW_PATH = ".github/workflows/estate-deadman.yml"
USER_AGENT = "SZLHOLDINGS-EstateDeadman/1.0"
MAX_RESPONSE_BYTES = 1_048_576
REPOSITORY = re.compile(r"^szl-holdings/[A-Za-z0-9_.-]+$")
WORKFLOW_PATH = re.compile(r"^\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml$")
TARGET_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
ACTIVE_STATUSES = {"queued", "in_progress", "waiting", "requested", "pending"}
RUN_STATUSES = ACTIVE_STATUSES | {"completed"}
RUN_CONCLUSIONS = {
    "action_required",
    "cancelled",
    "failure",
    "neutral",
    "skipped",
    "stale",
    "startup_failure",
    "success",
    "timed_out",
}
STATE_MARKER_BEGIN = "<!-- SZL_ESTATE_DEADMAN_STATE_BEGIN\n"
STATE_MARKER_END = "\nSZL_ESTATE_DEADMAN_STATE_END -->"


class ContractError(RuntimeError):
    """Raised when a repository-owned contract is malformed or ambiguous."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects so every request stays on the fixed GitHub API origin."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Mapping[str, str],
        newurl: str,
    ) -> urllib.request.Request | None:
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            "redirect rejected by fixed-origin policy",
            headers,
            fp,
        )


@dataclass(frozen=True)
class TargetObservation:
    id: str
    repository: str
    workflow_path: str
    healthy: bool
    state: str
    reason: str
    workflow_state: str | None
    workflow_id: int | None
    workflow_revision: str | None
    workflow_changed_at: str | None
    latest_run_id: int | None
    latest_status: str | None
    latest_conclusion: str | None
    latest_created_at: str | None
    latest_updated_at: str | None
    latest_html_url: str | None
    last_success_run_id: int | None
    last_success_updated_at: str | None
    success_age_minutes: int | None
    active_age_minutes: int | None
    error_kind: str | None = None

    def receipt(self) -> dict[str, Any]:
        return asdict(self)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def minutes_old(value: Any, now: dt.datetime) -> int | None:
    parsed = parse_time(value)
    if parsed is None:
        return None
    seconds = (now - parsed).total_seconds()
    if seconds < 0:
        return None
    return int(seconds // 60)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def reject_duplicate_pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def parse_incident_state(body: Any, repository: str) -> dict[str, Any]:
    require(isinstance(body, str), "controller incident body is missing")
    require(
        body.count(STATE_MARKER_BEGIN) == 1 and body.count(STATE_MARKER_END) == 1,
        "controller incident state marker is missing or ambiguous",
    )
    start = body.index(STATE_MARKER_BEGIN) + len(STATE_MARKER_BEGIN)
    end = body.index(STATE_MARKER_END, start)
    try:
        state = json.loads(body[start:end])
    except json.JSONDecodeError as exc:
        raise ContractError("controller incident state is not valid JSON") from exc
    require(isinstance(state, dict), "controller incident state must be an object")
    require(
        state.get("schema") == INCIDENT_STATE_SCHEMA,
        "controller incident state schema is invalid",
    )
    require(
        state.get("controller_repository") == repository,
        "controller incident repository binding is invalid",
    )
    revision = state.get("controller_revision")
    require(
        isinstance(revision, str) and bool(SHA40.fullmatch(revision)),
        "controller incident revision is invalid",
    )
    branch = state.get("controller_branch")
    require(
        isinstance(branch, str)
        and bool(re.fullmatch(r"[A-Za-z0-9._/-]+", branch))
        and ".." not in branch,
        "controller incident branch is invalid",
    )
    run_id = state.get("controller_run_id")
    require(
        isinstance(run_id, int) and not isinstance(run_id, bool) and run_id > 0,
        "controller incident run id is invalid",
    )
    run_attempt = state.get("controller_run_attempt")
    require(
        isinstance(run_attempt, int)
        and not isinstance(run_attempt, bool)
        and run_attempt > 0,
        "controller incident run attempt is invalid",
    )
    policy_sha256 = state.get("policy_sha256")
    require(
        isinstance(policy_sha256, str)
        and bool(re.fullmatch(r"[0-9a-f]{64}", policy_sha256)),
        "controller incident policy digest is invalid",
    )
    evidence_sha256 = state.get("evidence_sha256")
    require(
        isinstance(evidence_sha256, str)
        and bool(re.fullmatch(r"[0-9a-f]{64}", evidence_sha256)),
        "controller incident evidence digest is invalid",
    )
    require(
        parse_time(state.get("updated_at")) is not None,
        "controller incident timestamp is invalid",
    )
    failed = state.get("failed_target_ids")
    require(isinstance(failed, list), "controller incident failed targets are invalid")
    require(
        all(
            isinstance(item, str) and bool(TARGET_ID.fullmatch(item)) for item in failed
        ),
        "controller incident failed target id is invalid",
    )
    require(len(failed) == len(set(failed)), "controller incident target ids repeat")
    return dict(state)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def require_string(value: Any, label: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{label} must be a string")
    return value.strip()


def require_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    require(
        isinstance(value, int) and not isinstance(value, bool),
        f"{label} must be an integer",
    )
    require(minimum <= value <= maximum, f"{label} is outside its bounded range")
    return value


def safe_error_kind(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP_{int(exc.code)}"
    if isinstance(exc, urllib.error.URLError):
        return "URL_ERROR"
    if isinstance(exc, TimeoutError):
        return "TIMEOUT"
    if isinstance(exc, ssl.SSLError):
        return "TLS_ERROR"
    return type(exc).__name__.upper()[:64]


def validate_policy(raw: Any) -> dict[str, Any]:
    require(isinstance(raw, dict), "policy must be an object")
    require(raw.get("schema") == POLICY_SCHEMA, "unexpected policy schema")
    controller_repository = require_string(
        raw.get("controller_repository"), "controller_repository"
    )
    require(
        bool(REPOSITORY.fullmatch(controller_repository)),
        "controller_repository escaped szl-holdings",
    )
    controller_branch = require_string(
        raw.get("controller_branch"), "controller_branch"
    )
    require(
        re.fullmatch(r"[A-Za-z0-9._/-]+", controller_branch) is not None
        and ".." not in controller_branch,
        "controller_branch is invalid",
    )

    confirmation = raw.get("confirmation")
    require(isinstance(confirmation, dict), "confirmation must be an object")
    samples = require_int(confirmation.get("samples"), "confirmation.samples", 2, 2)
    interval_seconds = require_int(
        confirmation.get("interval_seconds"),
        "confirmation.interval_seconds",
        15,
        300,
    )

    incident = raw.get("incident")
    require(isinstance(incident, dict), "incident must be an object")
    incident_title = require_string(incident.get("title"), "incident.title")
    require(len(incident_title) <= 120, "incident.title is too long")

    targets_raw = raw.get("targets")
    require(isinstance(targets_raw, list) and targets_raw, "targets must be non-empty")
    require(len(targets_raw) <= 16, "targets exceeds the bounded inventory")
    targets: list[dict[str, Any]] = []
    ids: set[str] = set()
    identities: set[tuple[str, str]] = set()
    for index, item in enumerate(targets_raw):
        require(isinstance(item, dict), f"targets[{index}] must be an object")
        target_id = require_string(item.get("id"), f"targets[{index}].id")
        require(bool(TARGET_ID.fullmatch(target_id)), f"{target_id} has an invalid id")
        require(target_id not in ids, f"duplicate target id: {target_id}")
        repository = require_string(
            item.get("repository"), f"targets[{index}].repository"
        )
        require(
            bool(REPOSITORY.fullmatch(repository)),
            f"{target_id} repository escaped szl-holdings",
        )
        workflow_path = require_string(
            item.get("workflow_path"), f"targets[{index}].workflow_path"
        )
        require(
            bool(WORKFLOW_PATH.fullmatch(workflow_path)),
            f"{target_id} workflow path is not canonical",
        )
        identity = (repository, workflow_path)
        require(identity not in identities, f"duplicate workflow target: {identity}")
        branch = require_string(item.get("branch"), f"{target_id}.branch")
        require(
            re.fullmatch(r"[A-Za-z0-9._/-]+", branch) is not None
            and ".." not in branch,
            f"{target_id} branch is invalid",
        )
        event = require_string(item.get("event"), f"{target_id}.event")
        require(event == "schedule", f"{target_id} must monitor provider schedules")
        max_success = require_int(
            item.get("max_success_age_minutes"),
            f"{target_id}.max_success_age_minutes",
            10,
            1440,
        )
        max_active = require_int(
            item.get("max_active_age_minutes"),
            f"{target_id}.max_active_age_minutes",
            5,
            240,
        )
        bootstrap = require_int(
            item.get("bootstrap_grace_minutes"),
            f"{target_id}.bootstrap_grace_minutes",
            max_active,
            2880,
        )
        ids.add(target_id)
        identities.add(identity)
        targets.append(
            {
                "id": target_id,
                "repository": repository,
                "workflow_path": workflow_path,
                "branch": branch,
                "event": event,
                "max_success_age_minutes": max_success,
                "max_active_age_minutes": max_active,
                "bootstrap_grace_minutes": bootstrap,
            }
        )
    return {
        "schema": POLICY_SCHEMA,
        "controller_repository": controller_repository,
        "controller_branch": controller_branch,
        "confirmation": {
            "samples": samples,
            "interval_seconds": interval_seconds,
        },
        "incident": {
            "title": incident_title,
        },
        "targets": targets,
    }


def load_policy(path: Path) -> tuple[dict[str, Any], str]:
    try:
        worktree_source = path.read_bytes()
        source = worktree_source.replace(b"\r\n", b"\n")
        require(b"\r" not in source, "policy contains a lone carriage return")
        raw = json.loads(
            source.decode("utf-8"), object_pairs_hook=reject_duplicate_pairs
        )
    except OSError as exc:
        raise ContractError(f"cannot read policy: {safe_error_kind(exc)}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("policy is not valid JSON") from exc
    return validate_policy(raw), sha256_hex(source)


class GitHubApi:
    """Minimal GitHub REST client restricted to one fixed API origin."""

    def __init__(self, token: str | None, timeout: int = 20) -> None:
        self.token = token
        self.timeout = timeout
        context = ssl.create_default_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context), NoRedirectHandler()
        )

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        require(path.startswith("/"), "GitHub API path must begin with /")
        require("//" not in path, "GitHub API path contains an empty segment")
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = None
        if payload is not None:
            data = canonical_json(payload)
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"https://api.github.com{path}",
            data=data,
            headers=headers,
            method=method,
        )
        with self.opener.open(request, timeout=self.timeout) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            require(
                len(body) <= MAX_RESPONSE_BYTES,
                "GitHub API response exceeded the byte limit",
            )
            if not body:
                return None
            try:
                return json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ContractError("GitHub API returned non-JSON content") from exc

    def verified_branch_tip(self, repository: str, branch: str) -> str:
        quoted = urllib.parse.quote(branch, safe="")
        payload = self.request("GET", f"/repos/{repository}/branches/{quoted}")
        require(isinstance(payload, dict), "branch response must be an object")
        commit = payload.get("commit")
        require(isinstance(commit, dict), "branch response is missing a commit")
        revision = require_string(commit.get("sha"), "branch commit sha").lower()
        require(bool(SHA40.fullmatch(revision)), "branch commit sha is invalid")
        detail = commit.get("commit")
        require(isinstance(detail, dict), "branch commit detail is missing")
        verification = detail.get("verification")
        require(
            isinstance(verification, dict) and verification.get("verified") is True,
            "branch tip is not cryptographically verified",
        )
        return revision

    @staticmethod
    def workflow_name(target: Mapping[str, Any]) -> str:
        return PurePosixPath(target["workflow_path"]).name

    def workflow(self, target: Mapping[str, Any]) -> dict[str, Any]:
        workflow = urllib.parse.quote(self.workflow_name(target), safe="")
        payload = self.request(
            "GET", f"/repos/{target['repository']}/actions/workflows/{workflow}"
        )
        require(isinstance(payload, dict), "workflow response must be an object")
        require(
            payload.get("path") == target["workflow_path"],
            "workflow path resolved to a different definition",
        )
        return payload

    def workflow_runs(self, target: Mapping[str, Any]) -> list[dict[str, Any]]:
        workflow = urllib.parse.quote(self.workflow_name(target), safe="")
        query = urllib.parse.urlencode(
            {
                "branch": target["branch"],
                "event": target["event"],
                "per_page": "20",
            }
        )
        payload = self.request(
            "GET",
            f"/repos/{target['repository']}/actions/workflows/{workflow}/runs?{query}",
        )
        require(isinstance(payload, dict), "workflow-runs response must be an object")
        runs = payload.get("workflow_runs")
        require(isinstance(runs, list), "workflow_runs must be a list")
        require(
            all(isinstance(item, dict) for item in runs),
            "workflow_runs contains a malformed row",
        )
        return [dict(item) for item in runs]

    def workflow_change(
        self, target: Mapping[str, Any]
    ) -> tuple[str | None, str | None]:
        query = urllib.parse.urlencode(
            {
                "path": target["workflow_path"],
                "sha": target["branch"],
                "per_page": "1",
            }
        )
        payload = self.request("GET", f"/repos/{target['repository']}/commits?{query}")
        require(isinstance(payload, list), "workflow commit response must be a list")
        if not payload or not isinstance(payload[0], dict):
            return None, None
        revision = payload[0].get("sha")
        commit = payload[0].get("commit")
        changed_at = None
        if isinstance(commit, dict):
            committer = commit.get("committer")
            author = commit.get("author")
            if isinstance(committer, dict):
                changed_at = committer.get("date")
            if not changed_at and isinstance(author, dict):
                changed_at = author.get("date")
        return (
            str(revision) if isinstance(revision, str) else None,
            str(changed_at) if isinstance(changed_at, str) else None,
        )

    def authenticate_referenced_controller_run(
        self, repository: str, state: Mapping[str, Any]
    ) -> str:
        run_id = state["controller_run_id"]
        run_attempt = state["controller_run_attempt"]
        payload = self.request(
            "GET",
            f"/repos/{repository}/actions/runs/{run_id}/attempts/{run_attempt}",
        )
        require(isinstance(payload, dict), "controller run response must be an object")
        run_repository = payload.get("repository")
        head_repository = payload.get("head_repository")
        require(
            isinstance(run_repository, dict)
            and run_repository.get("full_name") == repository,
            "controller run repository binding is invalid",
        )
        require(
            isinstance(head_repository, dict)
            and head_repository.get("full_name") == repository,
            "controller run head repository binding is invalid",
        )
        require(payload.get("id") == run_id, "controller run id binding is invalid")
        require(
            payload.get("run_attempt") == run_attempt,
            "controller run attempt binding is invalid",
        )
        require(payload.get("event") == "schedule", "controller run event is invalid")
        require(
            payload.get("path") == CONTROLLER_WORKFLOW_PATH,
            "controller run workflow path is invalid",
        )
        require(
            payload.get("head_branch") == state["controller_branch"],
            "controller run branch binding is invalid",
        )
        require(
            payload.get("head_sha") == state["controller_revision"],
            "controller run revision binding is invalid",
        )
        require(
            payload.get("status") == "completed",
            "controller run is not terminal",
        )
        started_at = payload.get("run_started_at") or payload.get("created_at")
        updated_at = payload.get("updated_at")
        state_at = parse_time(state.get("updated_at"))
        started_time = parse_time(started_at)
        updated_time = parse_time(updated_at)
        require(
            started_time is not None
            and updated_time is not None
            and state_at is not None,
            "controller run timestamp is invalid",
        )
        require(
            started_time <= state_at <= updated_time + dt.timedelta(minutes=5),
            "controller incident timestamp is outside its authenticated run",
        )
        return str(state.get("updated_at"))

    def find_incident(self, repository: str, title: str) -> dict[str, Any] | None:
        query = urllib.parse.urlencode(
            {
                "q": f'repo:{repository} is:issue is:open in:title "{title}"',
                "per_page": "100",
            }
        )
        payload = self.request("GET", f"/search/issues?{query}")
        require(isinstance(payload, dict), "issue search response must be an object")
        require(
            payload.get("incomplete_results") is False,
            "issue search results are incomplete",
        )
        items = payload.get("items")
        require(isinstance(items, list), "issue search items must be a list")
        total_count = payload.get("total_count")
        require(
            isinstance(total_count, int)
            and not isinstance(total_count, bool)
            and 0 <= total_count <= len(items),
            "issue search results are truncated or malformed",
        )
        matches: list[dict[str, Any]] = []
        for item in items:
            if (
                not isinstance(item, dict)
                or "pull_request" in item
                or item.get("title") != title
            ):
                continue
            user = item.get("user")
            if not isinstance(user, dict) or user.get("login") != GITHUB_ACTIONS_BOT:
                continue
            require(
                user.get("type") == "Bot", "controller incident author type is invalid"
            )
            match = dict(item)
            match["_controller_state"] = parse_incident_state(
                match.get("body"), repository
            )
            match["_referenced_run_authenticated_at"] = (
                self.authenticate_referenced_controller_run(
                    repository, match["_controller_state"]
                )
            )
            matches.append(match)
        require(
            len(matches) <= 1,
            "multiple bot-authored marker-consistent dead-man incidents exist",
        )
        return matches[0] if matches else None

    def create_issue(self, repository: str, title: str, body: str) -> dict[str, Any]:
        require(bool(self.token), "GITHUB_TOKEN is required to create an incident")
        payload = self.request(
            "POST",
            f"/repos/{repository}/issues",
            {"title": title, "body": body},
        )
        require(isinstance(payload, dict), "issue create response must be an object")
        return payload

    def issue(self, repository: str, number: int) -> dict[str, Any]:
        payload = self.request("GET", f"/repos/{repository}/issues/{number}")
        require(isinstance(payload, dict), "issue readback response must be an object")
        require(
            "pull_request" not in payload,
            "incident readback resolved to a pull request",
        )
        return payload

    def update_issue(
        self,
        repository: str,
        number: int,
        *,
        body: str | None = None,
        state: str | None = None,
    ) -> dict[str, Any]:
        require(bool(self.token), "GITHUB_TOKEN is required to update an incident")
        update: dict[str, Any] = {}
        if body is not None:
            update["body"] = body
        if state is not None:
            update["state"] = state
            if state == "closed":
                update["state_reason"] = "completed"
        payload = self.request("PATCH", f"/repos/{repository}/issues/{number}", update)
        require(isinstance(payload, dict), "issue update response must be an object")
        return payload

    def add_comment(self, repository: str, number: int, body: str) -> None:
        require(bool(self.token), "GITHUB_TOKEN is required to comment")
        self.request(
            "POST", f"/repos/{repository}/issues/{number}/comments", {"body": body}
        )


def validate_run_rows(runs: Sequence[Mapping[str, Any]]) -> None:
    ids: set[int] = set()
    for index, item in enumerate(runs):
        require(isinstance(item, Mapping), f"workflow run {index} is not an object")
        run_id = item.get("id")
        require(
            isinstance(run_id, int) and not isinstance(run_id, bool) and run_id > 0,
            f"workflow run {index} id is invalid",
        )
        require(run_id not in ids, "workflow run ids repeat")
        ids.add(run_id)
        require(
            parse_time(item.get("created_at")) is not None,
            f"workflow run {run_id} creation timestamp is invalid",
        )
        status = item.get("status")
        require(status in RUN_STATUSES, f"workflow run {run_id} status is invalid")
        conclusion = item.get("conclusion")
        if status == "completed":
            require(
                conclusion in RUN_CONCLUSIONS,
                f"workflow run {run_id} conclusion is invalid",
            )
            require(
                parse_time(item.get("updated_at")) is not None,
                f"workflow run {run_id} terminal update timestamp is invalid",
            )
        else:
            require(
                conclusion is None,
                f"active workflow run {run_id} has a conclusion",
            )
        started_at = item.get("run_started_at")
        require(
            started_at is None or parse_time(started_at) is not None,
            f"workflow run {run_id} start timestamp is invalid",
        )


def evaluate_target(
    target: Mapping[str, Any],
    *,
    workflow: Mapping[str, Any],
    runs: Sequence[Mapping[str, Any]],
    workflow_revision: str | None,
    workflow_changed_at: str | None,
    now: dt.datetime,
) -> TargetObservation:
    validate_run_rows(runs)
    workflow_state = workflow.get("state")
    workflow_id = workflow.get("id") if isinstance(workflow.get("id"), int) else None
    if workflow_state != "active":
        return TargetObservation(
            id=target["id"],
            repository=target["repository"],
            workflow_path=target["workflow_path"],
            healthy=False,
            state="WORKFLOW_DISABLED",
            reason="workflow is not active",
            workflow_state=str(workflow_state) if workflow_state is not None else None,
            workflow_id=workflow_id,
            workflow_revision=workflow_revision,
            workflow_changed_at=workflow_changed_at,
            latest_run_id=None,
            latest_status=None,
            latest_conclusion=None,
            latest_created_at=None,
            latest_updated_at=None,
            latest_html_url=None,
            last_success_run_id=None,
            last_success_updated_at=None,
            success_age_minutes=None,
            active_age_minutes=None,
        )

    ordered = sorted(
        runs,
        key=lambda item: (
            parse_time(item.get("created_at"))
            or dt.datetime.min.replace(tzinfo=dt.timezone.utc)
        ),
        reverse=True,
    )
    latest = ordered[0] if ordered else None
    successes = [
        item
        for item in ordered
        if item.get("status") == "completed" and item.get("conclusion") == "success"
    ]
    completed = [item for item in ordered if item.get("status") == "completed"]
    latest_completed = completed[0] if completed else None
    last_success = successes[0] if successes else None
    success_age = minutes_old((last_success or {}).get("created_at"), now)
    change_age = minutes_old(workflow_changed_at, now)

    if latest is None:
        bootstrapping = (
            change_age is not None and change_age <= target["bootstrap_grace_minutes"]
        )
        return TargetObservation(
            id=target["id"],
            repository=target["repository"],
            workflow_path=target["workflow_path"],
            healthy=bootstrapping,
            state="BOOTSTRAPPING" if bootstrapping else "NO_SCHEDULED_RUN",
            reason=(
                "workflow is inside its bounded first-run grace period"
                if bootstrapping
                else "workflow has no scheduled-run evidence"
            ),
            workflow_state="active",
            workflow_id=workflow_id,
            workflow_revision=workflow_revision,
            workflow_changed_at=workflow_changed_at,
            latest_run_id=None,
            latest_status=None,
            latest_conclusion=None,
            latest_created_at=None,
            latest_updated_at=None,
            latest_html_url=None,
            last_success_run_id=None,
            last_success_updated_at=None,
            success_age_minutes=None,
            active_age_minutes=None,
        )

    latest_status = str(latest.get("status") or "UNKNOWN")
    latest_conclusion = (
        str(latest.get("conclusion")) if latest.get("conclusion") is not None else None
    )
    latest_age = minutes_old(latest.get("created_at"), now)
    last_success_id = (
        last_success.get("id")
        if isinstance(last_success, dict) and isinstance(last_success.get("id"), int)
        else None
    )
    common = {
        "id": target["id"],
        "repository": target["repository"],
        "workflow_path": target["workflow_path"],
        "workflow_state": "active",
        "workflow_id": workflow_id,
        "workflow_revision": workflow_revision,
        "workflow_changed_at": workflow_changed_at,
        "latest_run_id": latest.get("id")
        if isinstance(latest.get("id"), int)
        else None,
        "latest_status": latest_status,
        "latest_conclusion": latest_conclusion,
        "latest_created_at": latest.get("created_at"),
        "latest_updated_at": latest.get("updated_at"),
        "latest_html_url": latest.get("html_url"),
        "last_success_run_id": last_success_id,
        "last_success_updated_at": (last_success or {}).get("updated_at"),
        "success_age_minutes": success_age,
        "active_age_minutes": latest_age if latest_status in ACTIVE_STATUSES else None,
    }

    if latest_status in ACTIVE_STATUSES:
        active_fresh = (
            latest_age is not None and latest_age <= target["max_active_age_minutes"]
        )
        completed_baseline_age = minutes_old(
            (latest_completed or {}).get("created_at"), now
        )
        completed_baseline_fresh = (
            latest_completed is not None
            and latest_completed.get("conclusion") == "success"
            and completed_baseline_age is not None
            and completed_baseline_age <= target["max_success_age_minutes"]
        )
        bootstrapping = (
            latest_completed is None
            and change_age is not None
            and change_age <= target["bootstrap_grace_minutes"]
        )
        healthy = active_fresh and (completed_baseline_fresh or bootstrapping)
        return TargetObservation(
            healthy=healthy,
            state=(
                "RUNNING"
                if healthy
                else (
                    "ACTIVE_WITH_FAILED_BASELINE"
                    if latest_completed is not None
                    and latest_completed.get("conclusion") != "success"
                    else "STUCK_ACTIVE"
                )
            ),
            reason=(
                "scheduled run is active within its duration budget"
                if healthy
                else (
                    "latest completed scheduled run did not succeed"
                    if latest_completed is not None
                    and latest_completed.get("conclusion") != "success"
                    else "active run exceeded its duration or has no fresh success baseline"
                )
            ),
            **common,
        )

    if latest_status != "completed":
        return TargetObservation(
            healthy=False,
            state="UNKNOWN_RUN_STATE",
            reason="latest scheduled run has an unrecognized status",
            **common,
        )

    if latest_conclusion != "success":
        return TargetObservation(
            healthy=False,
            state="LATEST_RUN_FAILED",
            reason="latest completed scheduled run did not succeed",
            **common,
        )

    healthy = (
        success_age is not None and success_age <= target["max_success_age_minutes"]
    )
    return TargetObservation(
        healthy=healthy,
        state="HEALTHY" if healthy else "STALE_SUCCESS",
        reason=(
            "latest scheduled success is inside its freshness budget"
            if healthy
            else "latest scheduled success exceeded its freshness budget"
        ),
        **common,
    )


def observe_target(
    api: GitHubApi,
    target: Mapping[str, Any],
    now: dt.datetime,
) -> TargetObservation:
    try:
        workflow = api.workflow(target)
        runs = api.workflow_runs(target)
        revision, changed_at = api.workflow_change(target)
        return evaluate_target(
            target,
            workflow=workflow,
            runs=runs,
            workflow_revision=revision,
            workflow_changed_at=changed_at,
            now=now,
        )
    except Exception as exc:
        return TargetObservation(
            id=target["id"],
            repository=target["repository"],
            workflow_path=target["workflow_path"],
            healthy=False,
            state="OBSERVATION_ERROR",
            reason="fixed-origin observation failed",
            workflow_state=None,
            workflow_id=None,
            workflow_revision=None,
            workflow_changed_at=None,
            latest_run_id=None,
            latest_status=None,
            latest_conclusion=None,
            latest_created_at=None,
            latest_updated_at=None,
            latest_html_url=None,
            last_success_run_id=None,
            last_success_updated_at=None,
            success_age_minutes=None,
            active_age_minutes=None,
            error_kind=safe_error_kind(exc),
        )


def observe_all(
    api: GitHubApi,
    policy: Mapping[str, Any],
    now: dt.datetime,
) -> list[TargetObservation]:
    return [observe_target(api, target, now) for target in policy["targets"]]


def confirmed_failure_ids(
    samples: Sequence[Sequence[TargetObservation]], required_samples: int
) -> list[str]:
    require(bool(samples), "dead-man samples are missing")
    first_ids = [item.id for item in samples[0]]
    require(len(first_ids) == len(set(first_ids)), "dead-man target ids repeat")
    first_failed = {item.id for item in samples[0] if not item.healthy}
    if not first_failed:
        return []
    require(
        len(samples) == required_samples,
        "suspected failures were not sampled the required number of times",
    )
    confirmed = set(first_failed)
    for sample in samples[1:]:
        sample_ids = [item.id for item in sample]
        require(sample_ids == first_ids, "dead-man sample target order drifted")
        confirmed.intersection_update(item.id for item in sample if not item.healthy)
    return [item_id for item_id in first_ids if item_id in confirmed]


def classify_confirmation(
    samples: Sequence[Sequence[TargetObservation]], confirmed_ids: Sequence[str]
) -> str:
    require(bool(samples), "dead-man samples are missing")
    if confirmed_ids:
        return "CONFIRMED_FAILURE"
    if any(not item.healthy for sample in samples for item in sample):
        return "INCONCLUSIVE"
    return "HEALTHY"


def issue_body(report: Mapping[str, Any]) -> str:
    final = report.get("final_sample") or []
    confirmed_ids = report.get("confirmed_failed_target_ids")
    require(
        isinstance(confirmed_ids, list)
        and all(isinstance(item, str) for item in confirmed_ids),
        "confirmed failed target ids are missing or invalid",
    )
    failed = [item for item in final if item.get("id") in set(confirmed_ids)]
    state = {
        "schema": INCIDENT_STATE_SCHEMA,
        "updated_at": report.get("generated_at"),
        "controller_repository": report.get("controller_repository"),
        "controller_branch": report.get("controller_branch"),
        "controller_revision": report.get("controller_revision"),
        "controller_run_id": report.get("controller_run_id"),
        "controller_run_attempt": report.get("controller_run_attempt"),
        "policy_sha256": report.get("policy_sha256"),
        "evidence_sha256": report.get("evidence_sha256"),
        "failed_target_ids": [item.get("id") for item in failed],
    }
    lines = [
        "# SZL Estate Dead-Man Incident",
        "",
        "Two independent samples confirmed that one or more critical scheduled control planes are degraded.",
        "",
        f"- Observed: `{report.get('generated_at')}`",
        f"- Failed targets: `{len(failed)}/{len(final)}`",
        f"- Evidence: `{report.get('evidence_sha256', 'UNAVAILABLE')}`",
        "",
        "| Target | State | Latest run | Latest conclusion | Last success age | Reason |",
        "|---|---|---:|---|---:|---|",
    ]
    for item in final:
        lines.append(
            "| {id} | {state} | {run} | {conclusion} | {age} | {reason} |".format(
                id=item.get("id"),
                state=item.get("state"),
                run=item.get("latest_run_id") or "—",
                conclusion=item.get("latest_conclusion")
                or item.get("latest_status")
                or "—",
                age=(
                    f"{item.get('success_age_minutes')}m"
                    if item.get("success_age_minutes") is not None
                    else "—"
                ),
                reason=str(item.get("reason") or "—").replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "The supervisor cannot modify workflow definitions, branches, deployments, DNS, or product assets. No secret values are included.",
            "",
            STATE_MARKER_BEGIN
            + json.dumps(state, sort_keys=True, separators=(",", ":"))
            + STATE_MARKER_END,
            "",
        ]
    )
    return "\n".join(lines)


def reconcile_incident(
    api: GitHubApi,
    policy: Mapping[str, Any],
    report: Mapping[str, Any],
    _now: dt.datetime,
) -> dict[str, Any]:
    repository = policy["controller_repository"]
    title = policy["incident"]["title"]
    current = api.find_incident(repository, title)

    def prove_readback(
        number: int, *, state: str, body: str | None = None
    ) -> dict[str, Any]:
        readback = api.issue(repository, number)
        require(readback.get("number") == number, "incident readback number drifted")
        require(readback.get("title") == title, "incident readback title drifted")
        require(readback.get("state") == state, "incident readback state drifted")
        if body is not None:
            require(readback.get("body") == body, "incident readback body drifted")
        return readback

    confirmation_state = report.get("confirmation_state")
    require(
        confirmation_state in {"HEALTHY", "CONFIRMED_FAILURE", "INCONCLUSIVE"},
        "confirmation state is invalid",
    )
    if confirmation_state == "HEALTHY":
        if current is None:
            return {"action": "none", "ok": True}
        number = current.get("number")
        require(isinstance(number, int), "incident number is invalid")
        api.add_comment(
            repository,
            number,
            f"Independent scheduled-control evidence recovered at `{report['generated_at']}`. Closing automatically.",
        )
        api.update_issue(repository, number, state="closed")
        prove_readback(number, state="closed")
        return {"action": "closed", "ok": True, "issue_number": number}

    if confirmation_state == "INCONCLUSIVE":
        return {"action": "inconclusive", "ok": False}

    body = issue_body(report)
    if current is None:
        created = api.create_issue(repository, title, body)
        number = created.get("number")
        require(isinstance(number, int), "created incident number is invalid")
        prove_readback(number, state="open", body=body)
        return {
            "action": "created",
            "ok": True,
            "issue_number": number,
        }
    number = current.get("number")
    require(isinstance(number, int), "incident number is invalid")
    api.update_issue(repository, number, body=body)
    prove_readback(number, state="open", body=body)
    return {"action": "refreshed", "ok": True, "issue_number": number}


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def offline_contract(policy: Mapping[str, Any], policy_sha256: str) -> dict[str, Any]:
    return {
        "schema": "szl.estate-deadman-contract/v1",
        "valid": True,
        "policy_sha256": policy_sha256,
        "controller_repository": policy["controller_repository"],
        "target_count": len(policy["targets"]),
        "target_ids": [item["id"] for item in policy["targets"]],
        "authority": {
            "fixed_github_origin": True,
            "fixed_repositories": True,
            "fixed_workflow_paths": True,
            "two_sample_confirmation": policy["confirmation"]["samples"] >= 2,
            "workflow_mutation": False,
            "branch_mutation": False,
            "deployment_mutation": False,
            "dns_mutation": False,
            "product_execution": False,
            "incident_lifecycle_only": True,
        },
        "secret_values_recorded": False,
    }


def run_live(
    policy: Mapping[str, Any],
    policy_sha256: str,
    output: Path,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> int:
    read_token = (os.getenv("ESTATE_READ_TOKEN") or "").strip() or None
    issue_token = (os.getenv("GITHUB_TOKEN") or "").strip() or None
    require(bool(read_token), "ESTATE_READ_TOKEN is required for live observation")
    require(bool(issue_token), "GITHUB_TOKEN is required for incident lifecycle")
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    if repository:
        require(
            repository == policy["controller_repository"],
            "workflow repository does not match the dead-man authority",
        )
    read_api = GitHubApi(read_token)
    incident_api = GitHubApi(issue_token)
    controller_tip = read_api.verified_branch_tip(
        policy["controller_repository"], policy["controller_branch"]
    )
    workflow_sha = os.getenv("GITHUB_SHA", "").strip()
    if workflow_sha:
        require(
            workflow_sha == controller_tip,
            "dead-man is not running from the exact verified controller tip",
        )
    run_id_text = os.getenv("GITHUB_RUN_ID", "").strip()
    run_attempt_text = os.getenv("GITHUB_RUN_ATTEMPT", "").strip()
    require(
        bool(re.fullmatch(r"[1-9][0-9]*", run_id_text)),
        "GITHUB_RUN_ID is missing or invalid",
    )
    require(
        bool(re.fullmatch(r"[1-9][0-9]*", run_attempt_text)),
        "GITHUB_RUN_ATTEMPT is missing or invalid",
    )
    controller_run_id = int(run_id_text)
    controller_run_attempt = int(run_attempt_text)

    samples: list[list[TargetObservation]] = []
    samples.append(observe_all(read_api, policy, dt.datetime.now(dt.timezone.utc)))
    for _ in range(1, policy["confirmation"]["samples"]):
        if all(item.healthy for item in samples[-1]):
            break
        sleep_fn(policy["confirmation"]["interval_seconds"])
        samples.append(observe_all(read_api, policy, dt.datetime.now(dt.timezone.utc)))

    final_sample = samples[-1]
    confirmed_failed_target_ids = confirmed_failure_ids(
        samples, policy["confirmation"]["samples"]
    )
    confirmation_state = classify_confirmation(samples, confirmed_failed_target_ids)
    confirmed_healthy = confirmation_state == "HEALTHY"
    report: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "generated_at": utc_now(),
        "controller_repository": policy["controller_repository"],
        "controller_branch": policy["controller_branch"],
        "controller_revision": controller_tip,
        "controller_run_id": controller_run_id,
        "controller_run_attempt": controller_run_attempt,
        "policy_sha256": policy_sha256,
        "sample_count": len(samples),
        "confirmation_state": confirmation_state,
        "confirmed_healthy": confirmed_healthy,
        "healthy_target_count": sum(item.healthy for item in final_sample),
        "target_count": len(final_sample),
        "confirmed_failed_target_ids": confirmed_failed_target_ids,
        "samples": [[item.receipt() for item in sample] for sample in samples],
        "final_sample": [item.receipt() for item in final_sample],
        "authority": {
            "fixed_github_origin": True,
            "controller_tip_reverified": False,
            "workflow_mutation": False,
            "branch_mutation": False,
            "deployment_mutation": False,
            "dns_mutation": False,
            "product_execution": False,
            "incident_lifecycle_only": True,
        },
        "secret_values_recorded": False,
    }
    try:
        current_controller_tip = read_api.verified_branch_tip(
            policy["controller_repository"], policy["controller_branch"]
        )
        require(
            current_controller_tip == controller_tip,
            "controller authority changed during observation",
        )
        report["authority"]["controller_tip_reverified"] = True
        report["evidence_sha256"] = sha256_hex(canonical_json(report))
        report["incident"] = reconcile_incident(
            incident_api,
            policy,
            report,
            dt.datetime.now(dt.timezone.utc),
        )
    except Exception as exc:
        report.setdefault("evidence_sha256", sha256_hex(canonical_json(report)))
        report["incident"] = {
            "action": "failed",
            "ok": False,
            "error_kind": safe_error_kind(exc),
        }
    write_json_atomic(output, report)
    receipt_file_sha256 = sha256_hex(output.read_bytes())
    output.with_suffix(output.suffix + ".sha256").write_text(
        receipt_file_sha256 + "\n", encoding="ascii"
    )
    return 0 if confirmation_state == "HEALTHY" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy",
        type=Path,
        default=Path("governance/estate-deadman.v1.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/estate-deadman.json"),
    )
    parser.add_argument("--offline-contract-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        policy, policy_sha256 = load_policy(args.policy)
        if args.offline_contract_only:
            result = offline_contract(policy, policy_sha256)
            write_json_atomic(args.output, result)
            print(json.dumps(result, sort_keys=True))
            return 0
        return run_live(policy, policy_sha256, args.output)
    except Exception as exc:
        failure = {
            "schema": RECEIPT_SCHEMA,
            "generated_at": utc_now(),
            "confirmed_healthy": False,
            "error_kind": safe_error_kind(exc),
            "secret_values_recorded": False,
        }
        try:
            write_json_atomic(args.output, failure)
        except Exception as write_exc:
            failure["failure_write_error_kind"] = safe_error_kind(write_exc)
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
