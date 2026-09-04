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
USER_AGENT = "SZLHOLDINGS-EstateDeadman/1.0"
MAX_RESPONSE_BYTES = 1_048_576
REPOSITORY = re.compile(r"^szl-holdings/[A-Za-z0-9_.-]+$")
WORKFLOW_PATH = re.compile(r"^\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml$")
TARGET_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
ACTIVE_STATUSES = {"queued", "in_progress", "waiting", "requested", "pending"}
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
    latest_completed_at: str | None
    latest_html_url: str | None
    last_success_run_id: int | None
    last_success_completed_at: str | None
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
    return max(0, int((now - parsed).total_seconds() // 60))


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
    controller_branch = require_string(raw.get("controller_branch"), "controller_branch")
    require(
        re.fullmatch(r"[A-Za-z0-9._/-]+", controller_branch) is not None
        and ".." not in controller_branch,
        "controller_branch is invalid",
    )

    confirmation = raw.get("confirmation")
    require(isinstance(confirmation, dict), "confirmation must be an object")
    samples = require_int(confirmation.get("samples"), "confirmation.samples", 2, 3)
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
    refresh_minutes = require_int(
        incident.get("refresh_minutes"), "incident.refresh_minutes", 15, 1440
    )

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
            "refresh_minutes": refresh_minutes,
        },
        "targets": targets,
    }


def load_policy(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ContractError(f"cannot read policy: {safe_error_kind(exc)}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError("policy is not valid JSON") from exc
    return validate_policy(raw), sha256_hex(canonical_json(raw))


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
        return [dict(item) for item in runs if isinstance(item, dict)]

    def workflow_change(self, target: Mapping[str, Any]) -> tuple[str | None, str | None]:
        query = urllib.parse.urlencode(
            {
                "path": target["workflow_path"],
                "sha": target["branch"],
                "per_page": "1",
            }
        )
        payload = self.request(
            "GET", f"/repos/{target['repository']}/commits?{query}"
        )
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

    def find_incident(self, repository: str, title: str) -> dict[str, Any] | None:
        query = urllib.parse.urlencode(
            {
                "q": f'repo:{repository} is:issue is:open in:title "{title}"',
                "per_page": "100",
            }
        )
        payload = self.request("GET", f"/search/issues?{query}")
        require(isinstance(payload, dict), "issue search response must be an object")
        items = payload.get("items")
        require(isinstance(items, list), "issue search items must be a list")
        matches = [
            dict(item)
            for item in items
            if isinstance(item, dict)
            and "pull_request" not in item
            and item.get("title") == title
        ]
        require(len(matches) <= 1, "multiple dead-man incidents exist")
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
        payload = self.request(
            "PATCH", f"/repos/{repository}/issues/{number}", update
        )
        require(isinstance(payload, dict), "issue update response must be an object")
        return payload

    def add_comment(self, repository: str, number: int, body: str) -> None:
        require(bool(self.token), "GITHUB_TOKEN is required to comment")
        self.request(
            "POST", f"/repos/{repository}/issues/{number}/comments", {"body": body}
        )


def latest_timestamp(run: Mapping[str, Any]) -> str | None:
    for name in ("completed_at", "updated_at", "run_started_at", "created_at"):
        value = run.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def evaluate_target(
    target: Mapping[str, Any],
    *,
    workflow: Mapping[str, Any],
    runs: Sequence[Mapping[str, Any]],
    workflow_revision: str | None,
    workflow_changed_at: str | None,
    now: dt.datetime,
) -> TargetObservation:
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
            latest_completed_at=None,
            latest_html_url=None,
            last_success_run_id=None,
            last_success_completed_at=None,
            success_age_minutes=None,
            active_age_minutes=None,
        )

    ordered = sorted(
        runs,
        key=lambda item: parse_time(item.get("created_at"))
        or dt.datetime.min.replace(tzinfo=dt.timezone.utc),
        reverse=True,
    )
    latest = ordered[0] if ordered else None
    successes = [
        item
        for item in ordered
        if item.get("status") == "completed" and item.get("conclusion") == "success"
    ]
    last_success = successes[0] if successes else None
    success_age = minutes_old(latest_timestamp(last_success or {}), now)
    change_age = minutes_old(workflow_changed_at, now)

    if latest is None:
        bootstrapping = change_age is not None and change_age <= target["bootstrap_grace_minutes"]
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
            latest_completed_at=None,
            latest_html_url=None,
            last_success_run_id=None,
            last_success_completed_at=None,
            success_age_minutes=None,
            active_age_minutes=None,
        )

    latest_status = str(latest.get("status") or "UNKNOWN")
    latest_conclusion = (
        str(latest.get("conclusion")) if latest.get("conclusion") is not None else None
    )
    latest_age = minutes_old(latest.get("run_started_at") or latest.get("created_at"), now)
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
        "latest_run_id": latest.get("id") if isinstance(latest.get("id"), int) else None,
        "latest_status": latest_status,
        "latest_conclusion": latest_conclusion,
        "latest_created_at": latest.get("created_at"),
        "latest_completed_at": latest.get("completed_at"),
        "latest_html_url": latest.get("html_url"),
        "last_success_run_id": last_success_id,
        "last_success_completed_at": latest_timestamp(last_success or {}),
        "success_age_minutes": success_age,
        "active_age_minutes": latest_age if latest_status in ACTIVE_STATUSES else None,
    }

    if latest_status in ACTIVE_STATUSES:
        active_fresh = latest_age is not None and latest_age <= target["max_active_age_minutes"]
        success_fresh = success_age is not None and success_age <= target["max_success_age_minutes"]
        bootstrapping = (
            last_success is None
            and change_age is not None
            and change_age <= target["bootstrap_grace_minutes"]
        )
        healthy = active_fresh and (success_fresh or bootstrapping)
        return TargetObservation(
            healthy=healthy,
            state="RUNNING" if healthy else "STUCK_ACTIVE",
            reason=(
                "scheduled run is active within its duration budget"
                if healthy
                else "active run exceeded its duration or has no fresh success baseline"
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

    healthy = success_age is not None and success_age <= target["max_success_age_minutes"]
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
            latest_completed_at=None,
            latest_html_url=None,
            last_success_run_id=None,
            last_success_completed_at=None,
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


def issue_body(report: Mapping[str, Any]) -> str:
    final = report.get("final_sample") or []
    failed = [item for item in final if not item.get("healthy")]
    state = {
        "schema": "szl.estate-deadman-incident-state/v1",
        "updated_at": report.get("generated_at"),
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
                conclusion=item.get("latest_conclusion") or item.get("latest_status") or "—",
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
    now: dt.datetime,
) -> dict[str, Any]:
    repository = policy["controller_repository"]
    title = policy["incident"]["title"]
    current = api.find_incident(repository, title)
    if report["confirmed_healthy"]:
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
        return {"action": "closed", "ok": True, "issue_number": number}

    body = issue_body(report)
    if current is None:
        created = api.create_issue(repository, title, body)
        return {
            "action": "created",
            "ok": True,
            "issue_number": created.get("number"),
        }
    number = current.get("number")
    require(isinstance(number, int), "incident number is invalid")
    age = minutes_old(current.get("updated_at"), now)
    if age is not None and age < policy["incident"]["refresh_minutes"]:
        return {
            "action": "throttled",
            "ok": True,
            "issue_number": number,
            "age_minutes": age,
        }
    api.update_issue(repository, number, body=body)
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
    token = (os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or "").strip() or None
    require(bool(token), "GITHUB_TOKEN is required for live supervision")
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    if repository:
        require(
            repository == policy["controller_repository"],
            "workflow repository does not match the dead-man authority",
        )
    api = GitHubApi(token)
    controller_tip = api.verified_branch_tip(
        policy["controller_repository"], policy["controller_branch"]
    )
    workflow_sha = os.getenv("GITHUB_SHA", "").strip()
    if workflow_sha:
        require(
            workflow_sha == controller_tip,
            "dead-man is not running from the exact verified controller tip",
        )

    samples: list[list[TargetObservation]] = []
    samples.append(observe_all(api, policy, dt.datetime.now(dt.timezone.utc)))
    for _ in range(1, policy["confirmation"]["samples"]):
        if all(item.healthy for item in samples[-1]):
            break
        sleep_fn(policy["confirmation"]["interval_seconds"])
        samples.append(observe_all(api, policy, dt.datetime.now(dt.timezone.utc)))

    final_sample = samples[-1]
    confirmed_healthy = all(item.healthy for item in final_sample)
    report: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "generated_at": utc_now(),
        "controller_repository": policy["controller_repository"],
        "controller_revision": controller_tip,
        "policy_sha256": policy_sha256,
        "sample_count": len(samples),
        "confirmed_healthy": confirmed_healthy,
        "healthy_target_count": sum(item.healthy for item in final_sample),
        "target_count": len(final_sample),
        "samples": [[item.receipt() for item in sample] for sample in samples],
        "final_sample": [item.receipt() for item in final_sample],
        "authority": {
            "fixed_github_origin": True,
            "workflow_mutation": False,
            "branch_mutation": False,
            "deployment_mutation": False,
            "dns_mutation": False,
            "product_execution": False,
            "incident_lifecycle_only": True,
        },
        "secret_values_recorded": False,
    }
    report["evidence_sha256"] = sha256_hex(canonical_json(report))
    try:
        report["incident"] = reconcile_incident(
            api,
            policy,
            report,
            dt.datetime.now(dt.timezone.utc),
        )
    except Exception as exc:
        report["incident"] = {
            "action": "failed",
            "ok": False,
            "error_kind": safe_error_kind(exc),
        }
    report["receipt_sha256"] = sha256_hex(canonical_json(report))
    write_json_atomic(output, report)
    output.with_suffix(output.suffix + ".sha256").write_text(
        report["receipt_sha256"] + "\n", encoding="ascii"
    )
    return 0 if confirmed_healthy else 2


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
        except Exception:
            pass
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
