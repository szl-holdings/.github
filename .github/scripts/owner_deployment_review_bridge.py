#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Review one exact pending deployment from an owner-issued GitHub issue.

This bridge preserves the production environment gate for a solo-builder estate.
It does not bypass protection rules: the owner must open an exact command issue,
the protected workflow/run/SHA/environment must match, and the provider must
report that the token's user can approve the pending deployment.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

API = "https://api.github.com"
SCHEMA = "szl.deployment-approval/v1"
OWNER = "stephenlutar2-hash"
REPOSITORY = "szl-holdings/.github"
TITLE = "Approve deployment review: archive-portfolio-v2"
WORKFLOW_PATH = ".github/workflows/archive-portfolio-governor-v2.yml"
ENVIRONMENT = "production"
MAX_BYTES = 1_000_000
SHA40 = re.compile(r"^[0-9a-f]{40}$")
TOKEN_RE = re.compile(r"(?:github_pat_|gh[pousr]_|hf_)[A-Za-z0-9_]{12,}")
JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)
REQUIRED_KEYS = {
    "schema",
    "repository",
    "workflow_run_id",
    "environment_id",
    "environment_name",
    "head_sha",
    "workflow_path",
    "decision",
    "reason",
}


class ReviewError(RuntimeError):
    """Malformed owner command, unavailable authority, or provider drift."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")[:1000]
    return TOKEN_RE.sub("[REDACTED]", text)


def duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ReviewError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def reject_nonfinite(value: str) -> None:
    raise ReviewError(f"non-finite JSON value: {value}")


def strict_json(text: str, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            object_pairs_hook=duplicate_guard,
            parse_constant=reject_nonfinite,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ReviewError(f"{label} is not strict JSON: {safe(exc)}") from exc
    if not isinstance(value, dict):
        raise ReviewError(f"{label} must be an object")
    return value


def parse_command(body: str) -> dict[str, Any]:
    match = JSON_BLOCK.search(body or "")
    if not match:
        raise ReviewError("issue body must contain one fenced json object")
    if len(JSON_BLOCK.findall(body or "")) != 1:
        raise ReviewError("issue body must contain exactly one fenced json object")
    command = strict_json(match.group(1), label="approval command")
    if set(command) != REQUIRED_KEYS:
        missing = sorted(REQUIRED_KEYS - set(command))
        extra = sorted(set(command) - REQUIRED_KEYS)
        raise ReviewError(f"approval command keys mismatch; missing={missing}; extra={extra}")
    if command["schema"] != SCHEMA:
        raise ReviewError(f"schema must be {SCHEMA}")
    if command["repository"] != REPOSITORY:
        raise ReviewError(f"repository must be {REPOSITORY}")
    if command["workflow_path"] != WORKFLOW_PATH:
        raise ReviewError(f"workflow_path must be {WORKFLOW_PATH}")
    if command["environment_name"] != ENVIRONMENT:
        raise ReviewError(f"environment_name must be {ENVIRONMENT}")
    if command["decision"] != "approved":
        raise ReviewError("decision must be approved")
    if not isinstance(command["workflow_run_id"], int) or command["workflow_run_id"] <= 0:
        raise ReviewError("workflow_run_id must be a positive integer")
    if not isinstance(command["environment_id"], int) or command["environment_id"] <= 0:
        raise ReviewError("environment_id must be a positive integer")
    if not isinstance(command["head_sha"], str) or not SHA40.fullmatch(command["head_sha"]):
        raise ReviewError("head_sha must be a lowercase 40-character commit SHA")
    reason = command["reason"]
    if not isinstance(reason, str) or not 20 <= len(reason.strip()) <= 500:
        raise ReviewError("reason must contain 20 to 500 characters")
    if TOKEN_RE.search(json.dumps(command, sort_keys=True)):
        raise ReviewError("credential-shaped material is forbidden in approval commands")
    return command


def load_event(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    event = strict_json(path.read_text(encoding="utf-8"), label="GitHub event")
    if event.get("action") not in {"opened", "reopened", "edited"}:
        raise ReviewError("unsupported issue action")
    issue = event.get("issue")
    if not isinstance(issue, dict):
        raise ReviewError("event.issue must be an object")
    author = issue.get("user")
    if not isinstance(author, dict) or author.get("login") != OWNER:
        raise ReviewError("approval issue must be authored by the exact estate owner")
    if issue.get("title") != TITLE:
        raise ReviewError(f"issue title must be {TITLE!r}")
    if issue.get("state") != "open":
        raise ReviewError("approval issue must be open")
    number = issue.get("number")
    if not isinstance(number, int) or number <= 0:
        raise ReviewError("issue number is unavailable")
    command = parse_command(str(issue.get("body") or ""))
    return event, command


class GitHubClient:
    def __init__(self, token: str):
        if not token:
            raise ReviewError("deployment-review credential unavailable")
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        data = (
            json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
            if payload is not None
            else None
        )
        request = urllib.request.Request(
            API + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "szl-owner-deployment-review-bridge/1.0",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    raw = response.read(MAX_BYTES + 1)
                    if len(raw) > MAX_BYTES:
                        raise ReviewError(f"{method} {path}: response too large")
                    return json.loads(raw.decode()) if raw else None
            except urllib.error.HTTPError as exc:
                detail = safe(exc.read(MAX_BYTES + 1).decode("utf-8", "replace"))
                if exc.code in {408, 425, 429, 500, 502, 503, 504} and attempt < 3:
                    time.sleep(min(2 ** (attempt + 1), 12))
                    continue
                raise ReviewError(
                    f"GitHub {method} {path} failed with {exc.code}: {detail}"
                ) from exc
            except (
                urllib.error.URLError,
                TimeoutError,
                UnicodeDecodeError,
                json.JSONDecodeError,
            ) as exc:
                if attempt < 3:
                    time.sleep(min(2 ** (attempt + 1), 12))
                    continue
                raise ReviewError(
                    f"GitHub {method} {path} transport failure: {safe(exc)}"
                ) from exc
        raise AssertionError("unreachable")

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: Mapping[str, Any]) -> Any:
        return self.request("POST", path, payload)


def review(command: Mapping[str, Any], client: GitHubClient) -> dict[str, Any]:
    run_id = int(command["workflow_run_id"])
    environment_id = int(command["environment_id"])
    owner, repo = REPOSITORY.split("/", 1)
    run_path = f"/repos/{owner}/{repo}/actions/runs/{run_id}"
    pending_path = run_path + "/pending_deployments"

    run = client.get(run_path)
    if not isinstance(run, dict):
        raise ReviewError("workflow run response is not an object")
    expected_run = {
        "head_branch": "main",
        "head_sha": command["head_sha"],
        "path": WORKFLOW_PATH,
        "event": "push",
    }
    for key, expected in expected_run.items():
        if run.get(key) != expected:
            raise ReviewError(
                f"workflow run {key} drifted: expected {expected!r}, observed {run.get(key)!r}"
            )

    branch = client.get(f"/repos/{owner}/{repo}/branches/main")
    branch_sha = (
        branch.get("commit", {}).get("sha")
        if isinstance(branch, dict) and isinstance(branch.get("commit"), dict)
        else None
    )
    if branch_sha != command["head_sha"]:
        raise ReviewError(
            f"protected main moved: expected {command['head_sha']}, observed {branch_sha}"
        )

    pending = client.get(pending_path)
    if not isinstance(pending, list):
        raise ReviewError("pending deployment response is not an array")
    matches = [
        row
        for row in pending
        if isinstance(row, dict)
        and isinstance(row.get("environment"), dict)
        and row["environment"].get("id") == environment_id
        and row["environment"].get("name") == ENVIRONMENT
    ]

    if not matches:
        if run.get("status") == "completed" and run.get("conclusion") == "success":
            return {
                "schema": "szl.deployment-review-receipt/v1",
                "status": "ALREADY_COMPLETED",
                "mutated": False,
                "repository": REPOSITORY,
                "workflow_run_id": run_id,
                "environment_id": environment_id,
                "environment_name": ENVIRONMENT,
                "head_sha": command["head_sha"],
                "workflow_path": WORKFLOW_PATH,
                "provider_status": run.get("status"),
                "provider_conclusion": run.get("conclusion"),
                "reviewed_at": now(),
                "secrets_recorded": False,
            }
        raise ReviewError("exact pending production deployment is unavailable")
    if len(matches) != 1 or len(pending) != 1:
        raise ReviewError("pending deployment set is not the exact singleton expected")
    match = matches[0]
    if match.get("current_user_can_approve") is not True:
        raise ReviewError("provider reports that the selected credential cannot approve")
    if run.get("status") != "waiting":
        raise ReviewError(f"workflow run must be waiting, observed {run.get('status')!r}")

    client.post(
        pending_path,
        {
            "environment_ids": [environment_id],
            "state": "approved",
            "comment": (
                "Owner-approved exact archive portfolio v2 restoration; "
                f"head {command['head_sha']}. {command['reason'].strip()}"
            )[:1000],
        },
    )

    after_pending = client.get(pending_path)
    if not isinstance(after_pending, list):
        raise ReviewError("post-review pending deployment response is not an array")
    if any(
        isinstance(row, dict)
        and isinstance(row.get("environment"), dict)
        and row["environment"].get("id") == environment_id
        for row in after_pending
    ):
        raise ReviewError("exact deployment remained pending after approval")
    after_run = client.get(run_path)
    if not isinstance(after_run, dict) or after_run.get("head_sha") != command["head_sha"]:
        raise ReviewError("workflow run identity drifted after approval")

    return {
        "schema": "szl.deployment-review-receipt/v1",
        "status": "APPROVED_READBACK_VERIFIED",
        "mutated": True,
        "repository": REPOSITORY,
        "workflow_run_id": run_id,
        "environment_id": environment_id,
        "environment_name": ENVIRONMENT,
        "head_sha": command["head_sha"],
        "workflow_path": WORKFLOW_PATH,
        "provider_status_after": after_run.get("status"),
        "provider_conclusion_after": after_run.get("conclusion"),
        "reason_sha256": __import__("hashlib").sha256(
            command["reason"].strip().encode()
        ).hexdigest(),
        "reviewed_at": now(),
        "visibility_mutations": False,
        "repository_setting_mutations": False,
        "secret_mutations": False,
        "secrets_recorded": False,
    }


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if TOKEN_RE.search(text):
        raise ReviewError("credential-shaped material detected in receipt")
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("/tmp/deployment-review-receipt.json"),
    )
    args = parser.parse_args()
    issue_number: int | None = None
    try:
        event, command = load_event(args.event)
        issue_number = int(event["issue"]["number"])
        report = review(
            command,
            GitHubClient(os.environ.get("SZL_DEPLOYMENT_REVIEW_TOKEN", "")),
        )
        report["issue_number"] = issue_number
        write_report(args.report, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (ReviewError, OSError, KeyError, TypeError, ValueError) as exc:
        report = {
            "schema": "szl.deployment-review-receipt/v1",
            "status": "BLOCKED",
            "issue_number": issue_number,
            "error": safe(exc),
            "mutated": False,
            "visibility_mutations": False,
            "repository_setting_mutations": False,
            "secret_mutations": False,
            "secrets_recorded": False,
            "reviewed_at": now(),
        }
        try:
            write_report(args.report, report)
        except (ReviewError, OSError) as write_exc:
            print(
                "warning: deployment-review receipt write failed: " + safe(write_exc),
                file=sys.stderr,
            )
        print(json.dumps(report, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
