#!/usr/bin/env python3
"""Move every authenticated GitHub notification inbox thread to Done.

The script records counts only. It never logs notification subjects, repository
names, URLs, thread identifiers, or token material. The GitHub notification API
requires a classic personal access token with ``notifications`` or ``repo``
scope; GitHub App and fine-grained tokens are intentionally unsupported by that
API.

Inbox clearance is stronger than marking notifications read: every thread still
returned by ``GET /notifications?all=true`` is deleted through the documented
"Mark a thread as done" endpoint. The final readback must show both zero inbox
threads and zero unread threads.
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
PER_PAGE = 50
MAX_PAGES = 200
MAX_ROUNDS = 8
SETTLE_SECONDS = 2


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
            "User-Agent": "szl-clear-personal-notifications/2.0",
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


def notification_thread_ids(token: str, *, include_read: bool) -> list[str]:
    """Return current inbox thread IDs without recording notification content."""

    ids: list[str] = []
    seen: set[str] = set()
    for page in range(1, MAX_PAGES + 1):
        query = urllib.parse.urlencode(
            {
                "all": "true" if include_read else "false",
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
                raise NotificationError(
                    "GitHub returned a notification without a thread id"
                )
            if thread_id not in seen:
                seen.add(thread_id)
                ids.append(thread_id)
        if len(payload) < PER_PAGE:
            return ids
    raise NotificationError(
        f"Inbox inventory exceeded the fail-closed limit of "
        f"{MAX_PAGES * PER_PAGE} threads"
    )


def mark_thread_done(token: str, thread_id: str) -> None:
    encoded = urllib.parse.quote(thread_id, safe="")
    status, _ = request(token, "DELETE", f"/notifications/threads/{encoded}")
    if status != 204:
        raise NotificationError(
            f"Unexpected mark-done response status for one thread: {status}"
        )


def clear_inbox(token: str) -> dict[str, Any]:
    _, user = request(token, "GET", "/user")
    identity = str((user or {}).get("login") or "")
    if not identity:
        raise NotificationError("Authenticated GitHub identity did not expose a login")

    before_inbox = notification_thread_ids(token, include_read=True)
    before_unread = notification_thread_ids(token, include_read=False)

    cleared_ids: set[str] = set()
    delete_attempts = 0
    rounds = 0
    remaining = before_inbox

    for round_number in range(1, MAX_ROUNDS + 1):
        rounds = round_number
        if not remaining:
            break
        for thread_id in remaining:
            mark_thread_done(token, thread_id)
            delete_attempts += 1
            cleared_ids.add(thread_id)
        time.sleep(SETTLE_SECONDS)
        remaining = notification_thread_ids(token, include_read=True)

    if remaining:
        raise NotificationError(
            f"Notification inbox did not converge to zero; "
            f"remaining_count={len(remaining)}"
        )

    final_unread = notification_thread_ids(token, include_read=False)
    if final_unread:
        raise NotificationError(
            f"Unread notifications remained after inbox clearance; "
            f"remaining_count={len(final_unread)}"
        )

    return {
        "schema": "szl.github-notification-clearance/v2",
        "generated_at": utc_now(),
        "identity": identity,
        "before_inbox_count": len(before_inbox),
        "before_unread_count": len(before_unread),
        "after_inbox_count": 0,
        "after_unread_count": 0,
        "cleared_count": len(cleared_ids),
        "clearance_rounds": rounds,
        "delete_attempts": delete_attempts,
        "notification_content_recorded": False,
        "thread_ids_recorded": False,
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
            "schema": "szl.github-notification-clearance/v2",
            "generated_at": utc_now(),
            "after_inbox_count": None,
            "after_unread_count": None,
            "notification_content_recorded": False,
            "thread_ids_recorded": False,
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
