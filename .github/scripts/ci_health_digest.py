#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed organization-wide GitHub Actions health digest.

The short-lived qillqaq App reader is preferred, with the existing governed
``SZL_GITHUB_TOKEN`` as an explicit migration fallback. A reader is accepted
only after it proves the reviewed repository floor and Actions-read capability.
The ephemeral workflow token writes only the one rolling issue in this repo.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ci_health_digest_http import (
    ORG,
    ApiError,
    DigestError,
    ReaderSelectionError,
    request_json as _request_json,
    select_reader,
)
from ci_health_digest_sweep import (
    build_body,
    build_failure_body,
    sweep,
)

ISSUE_REPOSITORY = f"{ORG}/.github"
ISSUE_TITLE = "🔴 CI Health Digest — org-wide"
ISSUE_LABEL = "ci-health"
REPORT_SCHEMA = "szl.ci-health-digest/v2"


def _issue_token() -> str:
    token = (
        os.environ.get("CI_DIGEST_ISSUE_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    )
    if not token:
        raise DigestError(
            "no repository-scoped issue-write token is configured"
        )
    return token


def upsert_issue(
    body: str,
    *,
    red_total: int | None,
) -> dict[str, Any]:
    token = _issue_token()
    _, issues = _request_json(
        token,
        (
            f"https://api.github.com/repos/{ISSUE_REPOSITORY}/issues"
            f"?state=all&labels={ISSUE_LABEL}&per_page=100"
        ),
        operation="find rolling CI health issue",
    )
    if not isinstance(issues, list):
        raise DigestError(
            "rolling issue search returned a malformed payload"
        )
    existing = next(
        (
            issue
            for issue in issues
            if isinstance(issue, dict)
            and issue.get("title") == ISSUE_TITLE
            and "pull_request" not in issue
        ),
        None,
    )
    desired_state = "closed" if red_total == 0 else "open"
    if existing:
        number = int(existing["number"])
        patch: dict[str, Any] = {"body": body, "state": desired_state}
        if desired_state == "closed":
            patch["state_reason"] = "completed"
        _, result = _request_json(
            token,
            f"https://api.github.com/repos/{ISSUE_REPOSITORY}/issues/{number}",
            method="PATCH",
            body=patch,
            operation=f"update rolling CI health issue #{number}",
            expected={200},
        )
        action = "updated"
    else:
        _, result = _request_json(
            token,
            f"https://api.github.com/repos/{ISSUE_REPOSITORY}/issues",
            method="POST",
            body={
                "title": ISSUE_TITLE,
                "body": body,
                "labels": [ISSUE_LABEL],
            },
            operation="create rolling CI health issue",
            expected={201},
        )
        number = (
            int(result.get("number") or 0)
            if isinstance(result, dict)
            else 0
        )
        action = "created"
        if desired_state == "closed" and number:
            _, result = _request_json(
                token,
                (
                    f"https://api.github.com/repos/{ISSUE_REPOSITORY}/"
                    f"issues/{number}"
                ),
                method="PATCH",
                body={"state": "closed", "state_reason": "completed"},
                operation=(
                    f"close clean rolling CI health issue #{number}"
                ),
                expected={200},
            )
    if not isinstance(result, dict) or not result.get("number"):
        raise DigestError(
            "rolling issue mutation returned no issue identity"
        )
    return {
        "action": action,
        "number": int(result["number"]),
        "state": result.get("state"),
        "url": result.get("html_url"),
        "updated_at": result.get("updated_at"),
    }


def maybe_notify(actionable: int, total: int) -> dict[str, Any]:
    hook = os.environ.get("SLACK_WEBHOOK_URL") or ""
    if not hook:
        return {"attempted": False, "result": "not_configured"}
    message = (
        f"SZL CI Health: {actionable} actionable / "
        f"{total} red workflows org-wide."
    )
    attempts: list[dict[str, Any]] = []
    payloads = (
        (
            json.dumps({"text": message}).encode("utf-8"),
            "application/json",
            "slack_json",
        ),
        (
            message.encode("utf-8"),
            "text/plain; charset=utf-8",
            "plain_text",
        ),
    )
    for data, content_type, mode in payloads:
        request = urllib.request.Request(
            hook,
            data=data,
            headers={"Content-Type": content_type},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                status = int(response.status)
                attempts.append({"mode": mode, "http_status": status})
                if 200 <= status < 300:
                    return {
                        "attempted": True,
                        "result": "sent",
                        "delivery_mode": mode,
                        "http_status": status,
                        "attempts": attempts,
                    }
        except urllib.error.HTTPError as exc:
            attempts.append(
                {"mode": mode, "http_status": int(exc.code)}
            )
            if mode == "slack_json" and int(exc.code) in {405, 415}:
                continue
            break
        except Exception as exc:  # noqa: BLE001
            attempts.append(
                {"mode": mode, "failure_type": type(exc).__name__}
            )
            break
    return {
        "attempted": True,
        "result": "failed_non_terminal",
        "attempts": attempts,
    }


def _write_summary(body: str, report: Mapping[str, Any]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as summary:
        summary.write("# CI Health Digest\n\n")
        summary.write(f"- status: `{report.get('status')}`\n")
        authentication = report.get("authentication") or {}
        summary.write(
            f"- authentication: `{authentication.get('mode')}`\n"
        )
        coverage = report.get("coverage") or {}
        if coverage:
            summary.write(
                "- coverage: "
                f"`{coverage.get('queried_active_repositories')}` active repos / "
                f"`{coverage.get('active_workflows')}` workflows\n"
            )
        summary.write("\n")
        summary.write(body)
        summary.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        default=(
            os.environ.get("REPORT_PATH")
            or "reports/ci-health-digest.json"
        ),
    )
    args = parser.parse_args(argv)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation": os.environ.get("GITHUB_SHA"),
        "organization": ORG,
        "status": "NOT_VERIFIED",
        "authentication": {
            "mode": "unavailable",
            "credential_name": None,
            "value_recorded": False,
            "attempts": [],
        },
        "coverage": None,
        "red_runs": {},
        "summary": {"actionable": 0, "red_total": 0},
        "issue": None,
        "notification": None,
        "boundaries": [
            (
                "An organization reader is accepted only after proving the "
                "reviewed repository floor."
            ),
            "Every active repository and workflow API read is fail-closed.",
            (
                "The ephemeral repository token writes only the one rolling "
                "digest issue."
            ),
            (
                "No credential value, length, prefix, hash, identity, or "
                "header is recorded."
            ),
            (
                "A failed sweep opens the rolling issue as NOT VERIFIED and "
                "exits non-zero."
            ),
        ],
    }
    body = ""
    reader_attempts: Sequence[Mapping[str, Any]] = ()

    try:
        reader = select_reader()
        reader_attempts = reader.attempts
        report["authentication"] = {
            "mode": reader.mode,
            "credential_name": reader.credential_name,
            "value_recorded": False,
            "attempts": list(reader.attempts),
            "app_token_outcome": (
                os.environ.get("APP_TOKEN_OUTCOME") or "not_recorded"
            ),
        }
        reds, coverage = sweep(reader.token, reader.repositories)
        body, actionable, red_total, dispositions = build_body(
            reds,
            coverage=coverage,
            authentication_mode=reader.mode,
        )
        issue = upsert_issue(body, red_total=red_total)
        notification = maybe_notify(actionable, red_total)
        report.update(
            {
                "status": "VERIFIED",
                "coverage": coverage,
                "red_runs": {
                    repository: [asdict(item) for item in items]
                    for repository, items in reds.items()
                },
                "summary": {
                    "actionable": actionable,
                    "red_total": red_total,
                    "dispositions": dispositions,
                },
                "issue": issue,
                "notification": notification,
            }
        )
        exit_code = 0
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, ReaderSelectionError):
            reader_attempts = exc.attempts
            report["authentication"]["attempts"] = list(exc.attempts)
        report["fatal"] = {
            "type": type(exc).__name__,
            "detail_class": (
                exc.detail_class
                if isinstance(exc, ApiError)
                else "coverage_or_execution_failure"
            ),
        }
        body = build_failure_body(
            error=exc,
            attempts=reader_attempts,
        )
        try:
            report["issue"] = upsert_issue(body, red_total=None)
        except Exception as issue_exc:  # noqa: BLE001
            report["issue_error"] = {
                "type": type(issue_exc).__name__,
                "detail_class": (
                    issue_exc.detail_class
                    if isinstance(issue_exc, ApiError)
                    else "issue_publication_failure"
                ),
            }
        exit_code = 2

    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_summary(body, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
