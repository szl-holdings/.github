#!/usr/bin/env python3
"""Clear the authenticated GitHub user's unread notification inbox.

The script records counts only. It never logs notification subjects, repository
names, URLs, or token material. Bulk clearing is followed by an exact unread
inventory and an individual-thread fallback so the final count must be zero.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API = "https://api.github.com"
API_VERSION = "2022-11-28"
PER_PAGE = 100
MAX_PAGES = 100
MAX_ATTEMPTS = 5


class NotificationError(RuntimeError):
    """Fail-closed notification API error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def request(
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "szl-clear-personal-notifications/1.0",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:2000]
        raise NotificationError(
            f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise NotificationError(
            f"GitHub API {method} {path} failed: {type(exc).__name__}: {exc}"
        ) from exc

    if not raw:
        return status, None
    try:
        return status, json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise NotificationError(
            f"GitHub API {method} {path} returned non-JSON content"
        ) from exc


def unread_thread_ids(token: str) -> list[str]:
    ids: list[str] = []
    for page in range(1, MAX_PAGES + 1):
        query = urllib.parse.urlencode(
            {
                "all": "false",
                "participating": "false",
                "per_page": PER_PAGE,
                "page": page,
            }
        )
        _, payload = request(token, "GET", f"/notifications?{query}")
        if not isinstance(payload, list):
            raise NotificationError("GitHub notifications endpoint returned a non-list")
        for item in payload:
            thread_id = str((item or {}).get("id") or "")
            if not thread_id:
                raise NotificationError("GitHub returned a notification without a thread id")
            ids.append(thread_id)
        if len(payload) < PER_PAGE:
            return ids
    raise NotificationError(
        f"Unread inventory exceeded the fail-closed limit of {MAX_PAGES * PER_PAGE}"
    )


def mark_all_read(token: str) -> int:
    status, _ = request(
        token,
        "PUT",
        "/notifications",
        {"last_read_at": utc_now()},
    )
    if status not in {202, 205}:
        raise NotificationError(f"Unexpected bulk-clear response status: {status}")
    return status


def mark_thread_read(token: str, thread_id: str) -> None:
    status, _ = request(
        token,
        "PATCH",
        f"/notifications/threads/{urllib.parse.quote(thread_id, safe='')}",
        {"read": True},
    )
    if status not in {200, 205}:
        raise NotificationError(
            f"Unexpected thread-clear response status for {thread_id}: {status}"
        )


def clear_inbox(token: str) -> dict[str, Any]:
    _, user = request(token, "GET", "/user")
    identity = str((user or {}).get("login") or "")
    if not identity:
        raise NotificationError("Authenticated GitHub identity did not expose a login")

    before_ids = unread_thread_ids(token)
    bulk_attempts = 0
    fallback_threads = 0
    remaining = before_ids

    for attempt in range(1, MAX_ATTEMPTS + 1):
        bulk_attempts = attempt
        mark_all_read(token)
        time.sleep(2)
        remaining = unread_thread_ids(token)
        if not remaining:
            break

        for thread_id in remaining:
            mark_thread_read(token, thread_id)
            fallback_threads += 1
        time.sleep(2)
        remaining = unread_thread_ids(token)
        if not remaining:
            break

    if remaining:
        mark_all_read(token)
        time.sleep(3)
        remaining = unread_thread_ids(token)

    if remaining:
        raise NotificationError(
            f"Unread inbox did not converge to zero; remaining_count={len(remaining)}"
        )

    return {
        "schema": "szl.github-notification-clearance/v1",
        "generated_at": utc_now(),
        "identity": identity,
        "before_unread_count": len(before_ids),
        "after_unread_count": 0,
        "cleared_count": len(before_ids),
        "bulk_attempts": bulk_attempts,
        "individual_thread_fallbacks": fallback_threads,
        "notification_content_recorded": False,
        "status": "CLEARED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    report: dict[str, Any]
    code = 1
    token = (
        os.environ.get("GH_NOTIFICATIONS_TOKEN", "").strip()
        or os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    )
    try:
        if not token:
            raise NotificationError(
                "GH_NOTIFICATIONS_TOKEN/SZL_GITHUB_TOKEN is not configured"
            )
        report = clear_inbox(token)
        code = 0
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema": "szl.github-notification-clearance/v1",
            "generated_at": utc_now(),
            "after_unread_count": None,
            "notification_content_recorded": False,
            "status": "FAILED",
            "errors": [f"{type(exc).__name__}: {exc}"],
        }
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
