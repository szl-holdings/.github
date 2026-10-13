#!/usr/bin/env python3
"""Acknowledge authenticated GitHub notification threads as Done, count-only.

The script records counts only. It never logs notification subjects, repository
names, URLs, thread identifiers, update timestamps, or token material. The
GitHub notification API requires a classic personal access token with
``notifications`` or ``repo`` scope; GitHub App and fine-grained tokens are
intentionally unsupported by that API.

Measurement contract (``szl.github-notification-clearance/v3``):

* ``GET /notifications?all=true`` is the API *history* listing. It returns
  unread, read and already-Done threads, sorted by latest update. Its length is
  reported as ``api_history_*_count`` and is never treated as the active inbox:
  a thread acknowledged as Done stays in that history.
* ``DELETE /notifications/threads/{id}`` ("Mark a thread as done") returning
  HTTP 204 is an acknowledgement, not a verified removal. The number of
  distinct threads with at least one accepted acknowledgement is
  ``distinct_done_acknowledged``.
* An in-memory ledger keeps each thread id with the ``updated_at`` version that
  was acknowledged. Each observed version is acknowledged once. A thread is
  acknowledged again only after a later listing shows its ``updated_at``
  advanced. Unchanged observations are counted as ``unchanged_repeats_skipped``
  and never replayed. The ledger is never written to the receipt.
* A round whose only candidates are exactly the threads acknowledged in the
  previous round is a no-progress round; the run stops instead of replaying.
* After every outcome, including non-convergence and errors, an independent
  ``all=false`` unread readback is attempted. Its result is the only verified
  claim and is named ``unread-zero``. Readback errors are kept separate from
  operation errors, and an unavailable readback is reported as unknown.
* GitHub exposes no read-only observable for the full Inbox view, so
  ``full_inbox_state`` is always ``UNKNOWN``.

Mutations are serial and paced. Rate-limit responses (HTTP 403/429) honor
``Retry-After`` or ``X-RateLimit-Reset`` before retrying, and later listing
reads honor the full ``X-Poll-Interval`` returned by the previous listing.
Every wait is bounded by the job deadline the workflow records once, at job
start, in ``CLEARANCE_DEADLINE_EPOCH``: a wait that would end after it is
refused, the run stops with ``DEADLINE`` and still writes its count-only
report instead of sleeping until the runner is killed. A count-only RUNNING
receipt is updated during long runs so an interrupted runner never leaves an
evidence vacuum.
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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

API = "https://api.github.com"
API_VERSION = "2022-11-28"
SCHEMA = "szl.github-notification-clearance/v3"
PER_PAGE = 50
MAX_PAGES = 200
MAX_ROUNDS = 8

# GitHub's REST best practices recommend serial mutation and at least one second
# between POST/PATCH/PUT/DELETE requests. Keep these constants patchable for
# deterministic, network-free tests.
MUTATION_DELAY_SECONDS = 1.0
RATE_LIMIT_RETRIES = 8
RATE_LIMIT_FALLBACK_SECONDS = 60.0
RATE_LIMIT_MAX_SLEEP_SECONDS = 3700.0
RATE_LIMIT_SAFETY_SECONDS = 5.0
# Used only when a listing response carries no X-Poll-Interval header. A
# server-provided interval is honored in full; the job deadline bounds it.
POLL_INTERVAL_FALLBACK_SECONDS = 60.0
PROGRESS_INTERVAL = 100
# Absolute epoch seconds written by the workflow at job start. No wait may end
# after it. Unset only for local runs, which are then unbounded.
DEADLINE_ENV = "CLEARANCE_DEADLINE_EPOCH"

FULL_INBOX_STATE = "UNKNOWN"
FULL_INBOX_VERIFICATION = "UNVERIFIED_NO_READ_ONLY_OBSERVABLE"

STOP_NO_NEW_OR_ADVANCED = "NO_NEW_OR_ADVANCED_THREADS"
STOP_NO_PROGRESS = "NO_PROGRESS"
STOP_ROUND_LIMIT = "ROUND_LIMIT"
STOP_DEADLINE = "DEADLINE"
STOP_ERROR = "ERROR"

STATUS_RUNNING = "RUNNING"
STATUS_UNREAD_ZERO = "UNREAD_ZERO_VERIFIED"
STATUS_FAILED = "FAILED"


class NotificationError(RuntimeError):
    """Fail-closed notification API error."""


class DeadlineExceeded(NotificationError):
    """A required wait would end after the job deadline."""


class ApiResponse(NamedTuple):
    status: int
    payload: Any
    headers: Mapping[str, str] | None


@dataclass
class RequestStats:
    """Count-only request accounting kept separate from acknowledgement counts."""

    logical_calls: int = 0
    http_attempts: int = 0
    rate_limit_retries_observed: int = 0


@dataclass
class Listing:
    """One non-atomic paginated enumeration; ids stay in memory only."""

    versions: dict[str, datetime] = field(default_factory=dict)
    pages: int = 0
    poll_interval_seconds: float | None = None


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
    if value is None and hasattr(headers, "items"):
        lowered = name.lower()
        for key, candidate in headers.items():
            if str(key).lower() == lowered:
                value = candidate
                break
    return "" if value is None else str(value).strip()


def _positive_number(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def job_deadline(environ: Mapping[str, str]) -> float | None:
    """Return the workflow's absolute deadline, ``None`` when unset."""
    raw = str(environ.get(DEADLINE_ENV, "") or "").strip()
    if not raw:
        return None
    value = _positive_number(raw)
    if value is None:
        raise NotificationError(f"{DEADLINE_ENV} is not a finite non-negative epoch")
    return value


def ensure_within_deadline(seconds: float, *, deadline: float | None, reason: str) -> None:
    """Refuse a wait that would end after the deadline."""
    if deadline is not None and time.time() + seconds > deadline:
        raise DeadlineExceeded(
            f"{reason} wait of {math.ceil(seconds)} second(s) would end after the job deadline"
        )


def bounded_sleep(seconds: float, *, deadline: float | None, reason: str) -> None:
    """Sleep only if the wait ends by the deadline; otherwise fail closed."""
    ensure_within_deadline(seconds, deadline=deadline, reason=reason)
    if seconds > 0:
        time.sleep(seconds)


def rate_limit_delay(
    *,
    status: int,
    detail: str,
    headers: Mapping[str, str] | None,
    attempt: int,
    now_epoch: float | None = None,
) -> float | None:
    """Return a compliant retry delay, or ``None`` for a non-rate-limit error.

    GitHub signals primary and secondary rate limits only with HTTP 403 or 429.
    """
    if status not in (403, 429):
        return None
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
    *,
    stats: RequestStats | None = None,
    deadline: float | None = None,
) -> ApiResponse:
    """Issue one logical REST request, retrying only observed rate limits.

    ``stats.logical_calls`` counts this call once; ``stats.http_attempts``
    counts every HTTP attempt; ``stats.rate_limit_retries_observed`` counts
    retries caused by a real HTTP 403/429 rate-limit response.
    """
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    if stats is not None:
        stats.logical_calls += 1

    for attempt in range(RATE_LIMIT_RETRIES + 1):
        req = urllib.request.Request(
            API + path,
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "szl-clear-personal-notifications/3.0",
                **({"Content-Type": "application/json"} if body is not None else {}),
            },
        )
        if stats is not None:
            stats.http_attempts += 1
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                raw = response.read()
                status = response.status
                headers = getattr(response, "headers", None)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:2000]
            delay = rate_limit_delay(
                status=exc.code,
                detail=detail,
                headers=exc.headers,
                attempt=attempt,
            )
            if delay is not None and attempt < RATE_LIMIT_RETRIES:
                # Refuse before counting or announcing a retry that cannot fit.
                ensure_within_deadline(delay, deadline=deadline, reason="Rate-limit retry")
                if stats is not None:
                    stats.rate_limit_retries_observed += 1
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
            return ApiResponse(status, None, headers)
        try:
            return ApiResponse(status, json.loads(raw.decode("utf-8")), headers)
        except json.JSONDecodeError as exc:
            raise NotificationError(
                f"GitHub API {method} {_safe_path(path)} returned non-JSON content"
            ) from exc

    raise AssertionError("rate-limit retry loop exhausted without returning")


def _thread_version(value: Any) -> datetime:
    """Parse a thread ``updated_at`` without echoing it into diagnostics."""
    if not isinstance(value, str) or not value.strip():
        raise NotificationError("GitHub returned a notification without updated_at")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise NotificationError(
            "GitHub returned a notification with an unparseable updated_at"
        ) from exc
    if parsed.tzinfo is None:
        raise NotificationError("GitHub returned a timezone-less updated_at")
    return parsed


def list_notification_threads(
    token: str,
    *,
    include_read: bool,
    stats: RequestStats | None = None,
    deadline: float | None = None,
) -> Listing:
    """Enumerate one paginated listing as ``{thread_id: updated_at}``.

    ``include_read=True`` is the API history listing (unread, read and Done).
    ``include_read=False`` is the unread listing. Pages are not an atomic
    snapshot: an id seen twice keeps its latest version, and a record moved
    onto an already-read page is caught only by a later enumeration.
    """
    listing = Listing()
    for page in range(1, MAX_PAGES + 1):
        query = urllib.parse.urlencode(
            {
                "all": "true" if include_read else "false",
                "participating": "false",
                "per_page": PER_PAGE,
                "page": page,
            }
        )
        response = request(
            token, "GET", f"/notifications?{query}", stats=stats, deadline=deadline
        )
        listing.pages = page
        poll = _positive_number(_header(response.headers, "X-Poll-Interval"))
        if poll is not None:
            listing.poll_interval_seconds = poll
        payload = response.payload
        if not isinstance(payload, list):
            raise NotificationError("GitHub notifications endpoint returned a non-list")
        for item in payload:
            if not isinstance(item, Mapping):
                raise NotificationError("GitHub returned a non-object notification")
            thread_id = str(item.get("id") or "")
            if not thread_id:
                raise NotificationError(
                    "GitHub returned a notification without a thread id"
                )
            version = _thread_version(item.get("updated_at"))
            previous = listing.versions.get(thread_id)
            if previous is None or version > previous:
                listing.versions[thread_id] = version
        if len(payload) < PER_PAGE:
            return listing
    raise NotificationError(
        "Notification listing exceeded the fail-closed limit of "
        f"{MAX_PAGES * PER_PAGE} threads"
    )


def mark_thread_done(
    token: str,
    thread_id: str,
    *,
    stats: RequestStats | None = None,
    deadline: float | None = None,
) -> None:
    encoded = urllib.parse.quote(thread_id, safe="")
    response = request(
        token,
        "DELETE",
        f"/notifications/threads/{encoded}",
        stats=stats,
        deadline=deadline,
    )
    if response.status != 204:
        raise NotificationError(
            f"Unexpected mark-done response status for one thread: {response.status}"
        )


class PollGate:
    """Wait the server's full polling interval before a later listing read."""

    def __init__(self) -> None:
        self._not_before: float | None = None
        self.last_interval_seconds: float | None = None

    def observe(self, listing: Listing) -> None:
        interval = listing.poll_interval_seconds
        if interval is None:
            interval = POLL_INTERVAL_FALLBACK_SECONDS
        self.last_interval_seconds = interval
        self._not_before = time.monotonic() + interval

    def wait(self, deadline: float | None = None) -> None:
        if self._not_before is None:
            return
        remaining = self._not_before - time.monotonic()
        if remaining > 0:
            bounded_sleep(remaining, deadline=deadline, reason="X-Poll-Interval")


@dataclass
class Clearance:
    """Count-only state for one process; the ledger never leaves memory."""

    identity: str = ""
    deadline: float | None = None
    api_history_before_count: int | None = None
    api_history_last_count: int | None = None
    before_unread_count: int | None = None
    after_unread_count: int | None = None
    after_unread_measurement: str = "NOT_REACHED"
    stop_reason: str | None = None
    rounds: int = 0
    done_acknowledgements: int = 0
    reacknowledged_after_update: int = 0
    unchanged_repeats_skipped: int = 0
    ledger: dict[str, datetime] = field(default_factory=dict)
    stats: RequestStats = field(default_factory=RequestStats)
    poll: PollGate = field(default_factory=PollGate)
    errors: list[str] = field(default_factory=list)
    measurement_errors: list[str] = field(default_factory=list)

    def report(self, status: str) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "generated_at": utc_now(),
            "identity": self.identity,
            "status": status,
            "stop_reason": self.stop_reason,
            "api_history_listing": "GET /notifications?all=true (unread, read and Done history)",
            "api_history_before_count": self.api_history_before_count,
            "api_history_last_count": self.api_history_last_count,
            "unread_listing": "GET /notifications?all=false",
            "before_unread_count": self.before_unread_count,
            "after_unread_count": self.after_unread_count,
            "after_unread_measurement": self.after_unread_measurement,
            "unread_zero_verified": (
                self.after_unread_measurement == "MEASURED"
                and self.after_unread_count == 0
            ),
            "full_inbox_state": FULL_INBOX_STATE,
            "full_inbox_verification": FULL_INBOX_VERIFICATION,
            "distinct_done_acknowledged": len(self.ledger),
            "done_acknowledgements": self.done_acknowledgements,
            "reacknowledged_after_update": self.reacknowledged_after_update,
            "unchanged_repeats_skipped": self.unchanged_repeats_skipped,
            "rounds": self.rounds,
            "logical_api_calls": self.stats.logical_calls,
            "http_attempts": self.stats.http_attempts,
            "rate_limit_retries_observed": self.stats.rate_limit_retries_observed,
            "rate_limit_retry_ceiling": RATE_LIMIT_RETRIES,
            "mutation_delay_seconds": MUTATION_DELAY_SECONDS,
            "poll_interval_seconds": self.poll.last_interval_seconds,
            "job_deadline_configured": self.deadline is not None,
            "notification_content_recorded": False,
            "thread_ids_recorded": False,
            "errors": list(self.errors),
            "measurement_errors": list(self.measurement_errors),
        }


def _candidates(listing: Listing, state: Clearance) -> dict[str, datetime]:
    """Select new ids and ids whose ``updated_at`` advanced past the ledger."""
    selected: dict[str, datetime] = {}
    for thread_id, version in listing.versions.items():
        acknowledged = state.ledger.get(thread_id)
        if acknowledged is None or version > acknowledged:
            selected[thread_id] = version
        else:
            state.unchanged_repeats_skipped += 1
    return selected


def _read(
    state: Clearance, token: str, *, include_read: bool
) -> Listing:
    state.poll.wait(state.deadline)
    listing = list_notification_threads(
        token, include_read=include_read, stats=state.stats, deadline=state.deadline
    )
    state.poll.observe(listing)
    return listing


def _run_rounds(
    token: str,
    state: Clearance,
    progress: Callable[[dict[str, Any]], None] | None,
) -> None:
    _, user, _ = request(
        token, "GET", "/user", stats=state.stats, deadline=state.deadline
    )
    identity = str((user or {}).get("login") or "")
    if not identity:
        raise NotificationError("Authenticated GitHub identity did not expose a login")
    state.identity = identity

    history = _read(state, token, include_read=True)
    state.api_history_before_count = len(history.versions)
    state.api_history_last_count = len(history.versions)
    state.before_unread_count = len(_read(state, token, include_read=False).versions)
    if progress is not None:
        progress(state.report(STATUS_RUNNING))

    candidates = _candidates(history, state)
    previous_round: set[str] | None = None
    while candidates:
        if previous_round is not None and set(candidates) == previous_round:
            state.stop_reason = STOP_NO_PROGRESS
            return
        if state.rounds >= MAX_ROUNDS:
            state.stop_reason = STOP_ROUND_LIMIT
            return
        state.rounds += 1
        for thread_id, version in candidates.items():
            if state.done_acknowledgements:
                bounded_sleep(
                    MUTATION_DELAY_SECONDS,
                    deadline=state.deadline,
                    reason="Mutation pacing",
                )
            mark_thread_done(
                token, thread_id, stats=state.stats, deadline=state.deadline
            )
            if thread_id in state.ledger:
                state.reacknowledged_after_update += 1
            state.ledger[thread_id] = version
            state.done_acknowledgements += 1
            if state.done_acknowledgements % PROGRESS_INTERVAL == 0:
                print(
                    "notification acknowledgement progress: "
                    f"distinct_done_acknowledged={len(state.ledger)}",
                    flush=True,
                )
                if progress is not None:
                    progress(state.report(STATUS_RUNNING))

        previous_round = set(candidates)
        history = _read(state, token, include_read=True)
        state.api_history_last_count = len(history.versions)
        candidates = _candidates(history, state)
        if progress is not None:
            progress(state.report(STATUS_RUNNING))

    state.stop_reason = STOP_NO_NEW_OR_ADVANCED


def clear_notifications(
    token: str,
    *,
    progress: Callable[[dict[str, Any]], None] | None = None,
    deadline: float | None = None,
) -> dict[str, Any]:
    """Acknowledge each observed thread version once, then read back unread.

    Always returns a count-only report. ``status`` is ``UNREAD_ZERO_VERIFIED``
    only when the rounds stopped without new or advanced threads, no error
    occurred, and the independent ``all=false`` readback measured zero. A wait
    that would pass ``deadline`` stops the run with ``DEADLINE``; the readback
    is still attempted and reported ``UNAVAILABLE`` if it cannot fit.
    """
    state = Clearance(deadline=deadline)
    try:
        _run_rounds(token, state, progress)
    except DeadlineExceeded as exc:
        state.stop_reason = STOP_DEADLINE
        state.errors.append(f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001
        state.stop_reason = STOP_ERROR
        state.errors.append(f"{type(exc).__name__}: {exc}")

    try:
        unread = _read(state, token, include_read=False)
    except Exception as exc:  # noqa: BLE001
        state.after_unread_count = None
        state.after_unread_measurement = "UNAVAILABLE"
        state.measurement_errors.append(f"{type(exc).__name__}: {exc}")
    else:
        state.after_unread_count = len(unread.versions)
        state.after_unread_measurement = "MEASURED"

    verified = (
        not state.errors
        and state.stop_reason == STOP_NO_NEW_OR_ADVANCED
        and state.after_unread_measurement == "MEASURED"
        and state.after_unread_count == 0
    )
    return state.report(STATUS_UNREAD_ZERO if verified else STATUS_FAILED)


def describe_phase(outcome: str, exit_code: str) -> str:
    """Name a workflow phase result without inventing a numeric code."""
    outcome = (outcome or "").strip().lower()
    exit_code = (exit_code or "").strip()
    if outcome == "skipped":
        return "SKIPPED"
    if not outcome and not exit_code:
        return "NOT_REACHED"
    if outcome == "cancelled":
        return "CANCELLED"
    if exit_code == "0":
        return "PASSED"
    if exit_code.isdigit():
        return f"FAILED(exit={exit_code})"
    return f"FAILED(outcome={outcome or 'unknown'}, exit=unavailable)"


def enforce_phases(
    *,
    initial_outcome: str,
    initial_exit_code: str,
    post_receipt_outcome: str,
    post_receipt_exit_code: str,
    initial_report: Path,
    post_receipt_report: Path,
) -> tuple[int, str]:
    """Return the workflow verdict for both phases; zero only for unread-zero."""
    initial = describe_phase(initial_outcome, initial_exit_code)
    post_receipt = describe_phase(post_receipt_outcome, post_receipt_exit_code)
    phases = f"initial={initial}, post-receipt={post_receipt}"
    if initial != "PASSED" or post_receipt != "PASSED":
        return 1, f"Notification clearance failed closed: {phases}."

    for path in (initial_report, post_receipt_report):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return 1, f"Notification receipt unreadable ({phases}): {type(exc).__name__}"
        if (
            report.get("schema") != SCHEMA
            or report.get("status") != STATUS_UNREAD_ZERO
            or report.get("after_unread_measurement") != "MEASURED"
            # Exactly the integer zero: JSON false and 0.0 compare equal to 0.
            or type(report.get("after_unread_count")) is not int
            or report.get("after_unread_count") != 0
            or report.get("unread_zero_verified") is not True
            or report.get("full_inbox_state") != FULL_INBOX_STATE
        ):
            return 1, f"Notification receipt does not verify unread-zero ({phases})."

    return 0, (
        "Unread-zero (all=false) verified after receipt publication; "
        f"{phases}. Full-inbox state remains {FULL_INBOX_STATE} "
        f"({FULL_INBOX_VERIFICATION})."
    )


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _main_enforce() -> int:
    code, message = enforce_phases(
        initial_outcome=os.environ.get("INITIAL_OUTCOME", ""),
        initial_exit_code=os.environ.get("INITIAL_EXIT_CODE", ""),
        post_receipt_outcome=os.environ.get("POST_RECEIPT_OUTCOME", ""),
        post_receipt_exit_code=os.environ.get("POST_RECEIPT_EXIT_CODE", ""),
        initial_report=Path("github-notification-clearance.json"),
        post_receipt_report=Path("github-notification-post-receipt-clearance.json"),
    )
    print(("::error::" if code else "") + message)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--report", type=Path)
    mode.add_argument(
        "--enforce-phases",
        action="store_true",
        help="Evaluate both workflow phases from step outcomes and receipts.",
    )
    args = parser.parse_args(argv)
    if args.enforce_phases:
        return _main_enforce()

    token = (
        os.environ.get("GH_NOTIFICATIONS_TOKEN", "").strip()
        or os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    )
    deadline: float | None = None
    deadline_error: str | None = None
    try:
        deadline = job_deadline(os.environ)
    except NotificationError as exc:
        deadline_error = f"{type(exc).__name__}: {exc}"

    def record_progress(snapshot: dict[str, Any]) -> None:
        _write_report(args.report, snapshot)

    if token and deadline_error is None:
        report = clear_notifications(token, progress=record_progress, deadline=deadline)
    else:
        state = Clearance(after_unread_measurement="UNAVAILABLE")
        state.stop_reason = STOP_ERROR
        if not token:
            state.errors.append(
                "NotificationError: GH_NOTIFICATIONS_TOKEN/SZL_GITHUB_TOKEN is not configured"
            )
            state.measurement_errors.append(
                "NotificationError: no token for unread readback"
            )
        else:
            state.errors.append(deadline_error or "")
            state.measurement_errors.append(
                "NotificationError: invalid job deadline; unread readback not attempted"
            )
        report = state.report(STATUS_FAILED)
    _write_report(args.report, report)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == STATUS_UNREAD_ZERO else 1


if __name__ == "__main__":
    raise SystemExit(main())
