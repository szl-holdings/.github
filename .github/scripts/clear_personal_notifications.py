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

Large inboxes are deliberately drained serially. Mutating requests are paced,
and primary/secondary rate-limit responses honor ``Retry-After`` or
``X-RateLimit-Reset`` before retrying. A count-only RUNNING receipt is updated
during long drains so an interrupted runner never leaves an evidence vacuum.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API = "https://api.github.com"
API_VERSION = "2022-11-28"
PER_PAGE = 50
MAX_PAGES = 200
MAX_ROUNDS = 8
SETTLE_SECONDS = 2.0

# GitHub's REST best practices recommend serial mutation and at least one second
# between POST/PATCH/PUT/DELETE requests. Keep these constants patchable for
# deterministic, network-free tests.
MUTATION_DELAY_SECONDS = 1.0
RATE_LIMIT_RETRIES = 8
RATE_LIMIT_FALLBACK_SECONDS = 60.0
RATE_LIMIT_MAX_SLEEP_SECONDS = 3700.0
RATE_LIMIT_SAFETY_SECONDS = 5.0
PROGRESS_INTERVAL = 100


class NotificationError(RuntimeError):
    """Fail-closed notification API error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_path(path: str) -> str:
    """Return a diagnostic path that cannot disclose a notification thread id."""
    parsed = urllib.parse.urlsplit(path)
    if parsed.path.startswith("/notifications/threads/"):
        return "/notifications/threads/{thread_id}"
    return parsed.path


def _header(headers: Mapping[str, str] | None, name: str) -> str:
    if headers is None:
        return ""
    value = headers.get(name)
    return "" if value is None else str(value).strip()


def _positive_number(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def rate_limit_delay(
    *,
    status: int,
    detail: str,
    headers: Mapping[str, str] | None,
    attempt: int,
    now_epoch: float | None = None,
) -> float | None:
    """Return a compliant retry delay, or ``None`` for a non-rate-limit error."""
    retry_after = _positive_number(_header(headers, "Retry-After"))
    remaining = _header(headers, "X-RateLimit-Remaining")
    reset_epoch = _positive_number(_header(headers, "X-RateLimit-Reset"))
    lower_detail = detail.lower()

    is_rate_limited = (
        status == 429
        or "rate limit" in lower_detail
        or retry_after is not None
        or remaining == "0"
    )
    if not is_rate_limited:
        return None

    if retry_after is not None:
        delay = retry_after
    elif remaining == "0" and reset_epoch is not None:
        now = time.time() if now_epoch is None else now_epoch
        delay = max(0.0, reset_epoch - now) + RATE_LIMIT_SAFETY_SECONDS
    else:
        delay = RATE_LIMIT_FALLBACK_SECONDS * (2**attempt)

    return max(1.0, min(delay, RATE_LIMIT_MAX_SLEEP_SECONDS))


def request(
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """Issue one REST request, retrying only documented rate-limit failures."""
    body = None if payload is None else json.dumps(payload).encode("utf-8")

    for attempt in range(RATE_LIMIT_RETRIES + 1):
        req = urllib.request.Request(
            API + path,
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "szl-clear-personal-notifications/2.1",
                **({"Content-Type": "application/json"} if body is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:2000]
            delay = rate_limit_delay(
                status=exc.code,
                detail=detail,
                headers=exc.headers,
                attempt=attempt,
            )
            if delay is not None and attempt < RATE_LIMIT_RETRIES:
                print(
                    "GitHub rate limit encountered; "
                    f"retrying after {math.ceil(delay)} second(s) "
                    f"(attempt {attempt + 1}/{RATE_LIMIT_RETRIES}).",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(delay)
                continue
            raise NotificationError(
                f"GitHub API {method} {_safe_path(path)} failed "
                f"HTTP {exc.code}: {detail}"
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise NotificationError(
                f"GitHub API {method} {_safe_path(path)} failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        if not raw:
            return status, None
        try:
            return status, json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise NotificationError(
                f"GitHub API {method} {_safe_path(path)} returned non-JSON content"
            ) from exc

    raise AssertionError("rate-limit retry loop exhausted without returning")


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
        "Inbox inventory exceeded the fail-closed limit of "
        f"{MAX_PAGES * PER_PAGE} threads"
    )


def mark_thread_done(token: str, thread_id: str) -> None:
    encoded = urllib.parse.quote(thread_id, safe="")
    status, _ = request(token, "DELETE", f"/notifications/threads/{encoded}")
    if status != 204:
        raise NotificationError(
            f"Unexpected mark-done response status for one thread: {status}"
        )


def _running_report(
    *,
    identity: str,
    before_inbox_count: int,
    before_unread_count: int,
    cleared_count: int,
    clearance_rounds: int,
    delete_attempts: int,
    remaining_count: int | None,
) -> dict[str, Any]:
    return {
        "schema": "szl.github-notification-clearance/v2",
        "generated_at": utc_now(),
        "identity": identity,
        "before_inbox_count": before_inbox_count,
        "before_unread_count": before_unread_count,
        "after_inbox_count": remaining_count,
        "after_unread_count": None,
        "cleared_count": cleared_count,
        "clearance_rounds": clearance_rounds,
        "delete_attempts": delete_attempts,
        "mutation_delay_seconds": MUTATION_DELAY_SECONDS,
        "rate_limit_retries": RATE_LIMIT_RETRIES,
        "notification_content_recorded": False,
        "thread_ids_recorded": False,
        "status": "RUNNING",
    }


def clear_inbox(
    token: str,
    *,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
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

    if progress is not None:
        progress(
            _running_report(
                identity=identity,
                before_inbox_count=len(before_inbox),
                before_unread_count=len(before_unread),
                cleared_count=0,
                clearance_rounds=0,
                delete_attempts=0,
                remaining_count=len(remaining),
            )
        )

    for round_number in range(1, MAX_ROUNDS + 1):
        rounds = round_number
        if not remaining:
            break

        for thread_id in remaining:
            if delete_attempts:
                time.sleep(MUTATION_DELAY_SECONDS)
            mark_thread_done(token, thread_id)
            delete_attempts += 1
            cleared_ids.add(thread_id)

            if delete_attempts % PROGRESS_INTERVAL == 0:
                print(
                    f"notification clearance progress: cleared={len(cleared_ids)}",
                    flush=True,
                )
                if progress is not None:
                    progress(
                        _running_report(
                            identity=identity,
                            before_inbox_count=len(before_inbox),
                            before_unread_count=len(before_unread),
                            cleared_count=len(cleared_ids),
                            clearance_rounds=rounds,
                            delete_attempts=delete_attempts,
                            remaining_count=None,
                        )
                    )

        time.sleep(SETTLE_SECONDS)
        remaining = notification_thread_ids(token, include_read=True)
        if progress is not None:
            progress(
                _running_report(
                    identity=identity,
                    before_inbox_count=len(before_inbox),
                    before_unread_count=len(before_unread),
                    cleared_count=len(cleared_ids),
                    clearance_rounds=rounds,
                    delete_attempts=delete_attempts,
                    remaining_count=len(remaining),
                )
            )

    if remaining:
        raise NotificationError(
            "Notification inbox did not converge to zero; "
            f"remaining_count={len(remaining)}"
        )

    final_unread = notification_thread_ids(token, include_read=False)
    if final_unread:
        raise NotificationError(
            "Unread notifications remained after inbox clearance; "
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
        "mutation_delay_seconds": MUTATION_DELAY_SECONDS,
        "rate_limit_retries": RATE_LIMIT_RETRIES,
        "notification_content_recorded": False,
        "thread_ids_recorded": False,
        "status": "CLEARED",
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    report: dict[str, Any]
    last_snapshot: dict[str, Any] = {}
    code = 1
    token = (
        os.environ.get("GH_NOTIFICATIONS_TOKEN", "").strip()
        or os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    )

    def record_progress(snapshot: dict[str, Any]) -> None:
        last_snapshot.clear()
        last_snapshot.update(snapshot)
        _write_report(args.report, snapshot)

    try:
        if not token:
            raise NotificationError(
                "GH_NOTIFICATIONS_TOKEN/SZL_GITHUB_TOKEN is not configured"
            )
        report = clear_inbox(token, progress=record_progress)
        code = 0
    except Exception as exc:  # noqa: BLE001
        report = {
            **last_snapshot,
            "schema": "szl.github-notification-clearance/v2",
            "generated_at": utc_now(),
            "after_inbox_count": last_snapshot.get("after_inbox_count"),
            "after_unread_count": None,
            "notification_content_recorded": False,
            "thread_ids_recorded": False,
            "status": "FAILED",
            "errors": [f"{type(exc).__name__}: {exc}"],
        }
    finally:
        _write_report(args.report, report)

    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
