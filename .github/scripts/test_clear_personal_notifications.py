#!/usr/bin/env python3
"""Network-free regressions for personal GitHub notification acknowledgement."""
from __future__ import annotations

import contextlib
import email.message
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import call, patch

MODULE_PATH = Path(__file__).with_name("clear_personal_notifications.py")
SPEC = importlib.util.spec_from_file_location("clear_personal_notifications", MODULE_PATH)
assert SPEC and SPEC.loader
clearer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = clearer
SPEC.loader.exec_module(clearer)

BASE_TIME = datetime(2026, 10, 13, tzinfo=timezone.utc)


class FakeGitHub:
    """Network-free model of the documented notification listing contract.

    * ``all=true`` is history: unread, read AND Done threads. A thread marked
      Done stays in it (the defect the old fake hid by deleting it).
    * ``all=false`` returns unread threads that are not Done.
    * Both listings are sorted by latest update, newest first, like the API,
      and page boundaries are evaluated per request (not an atomic snapshot).
    * ``DELETE /notifications/threads/{id}`` marks the thread read and Done.
    """

    def __init__(self, count: int, *, poll_interval: str | None = "60") -> None:
        self.threads: dict[str, dict[str, object]] = {}
        for index in range(1, count + 1):
            self.add(str(index), unread=index % 2 == 0, updated=index)
        self.poll_interval = poll_interval
        self.deleted: list[str] = []
        self.reads: list[tuple[bool, int]] = []
        self.on_delete = None
        self.on_page = None
        self.bump_on_delete = False
        self.fail_delete_ids: set[str] = set()
        self.fail_unread_reads_after: int | None = None
        self.clock = None

    def add(self, thread_id: str, *, unread: bool, updated: int) -> None:
        self.threads[thread_id] = {"unread": unread, "done": False, "updated": updated}

    def latest(self) -> int:
        return max((int(state["updated"]) for state in self.threads.values()), default=0)

    def touch(self, thread_id: str) -> None:
        """New activity: the thread returns unread with an advanced updated_at."""
        state = self.threads[thread_id]
        state.update(unread=True, done=False, updated=self.latest() + 1)

    @staticmethod
    def updated_at(updated: object) -> str:
        moment = BASE_TIME + timedelta(seconds=int(updated))
        return moment.isoformat().replace("+00:00", "Z")

    def ordered(self, include_read: bool) -> list[str]:
        visible = [
            thread_id
            for thread_id, state in self.threads.items()
            if include_read or (state["unread"] and not state["done"])
        ]
        return sorted(
            visible,
            key=lambda thread_id: (int(self.threads[thread_id]["updated"]), thread_id),
            reverse=True,
        )

    def request(self, token, method, path, payload=None, *, stats=None, deadline=None):
        if token != "classic-token":
            raise AssertionError("wrong token")
        if stats is not None:
            stats.logical_calls += 1
            stats.http_attempts += 1
        if method == "GET" and path == "/user":
            return clearer.ApiResponse(200, {"login": "stephenlutar2-hash"}, {})

        if method == "GET" and path.startswith("/notifications?"):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
            include_read = query["all"][0] == "true"
            page = int(query["page"][0])
            per_page = int(query["per_page"][0])
            if self.clock is not None and page == 1:
                self.clock.reads.append(self.clock.now)
            self.reads.append((include_read, page))
            if (
                not include_read
                and self.fail_unread_reads_after is not None
                and sum(1 for read, p in self.reads if not read and p == 1)
                > self.fail_unread_reads_after
            ):
                raise clearer.NotificationError(
                    "GitHub API GET /notifications failed HTTP 502: Bad Gateway"
                )
            if self.on_page is not None:
                self.on_page(self, include_read, page)
            ordered = self.ordered(include_read)
            start = (page - 1) * per_page
            body = [
                {
                    "id": thread_id,
                    "unread": bool(self.threads[thread_id]["unread"]),
                    "updated_at": self.updated_at(self.threads[thread_id]["updated"]),
                }
                for thread_id in ordered[start : start + per_page]
            ]
            headers = {} if self.poll_interval is None else {"X-Poll-Interval": self.poll_interval}
            return clearer.ApiResponse(200, body, headers)

        if method == "DELETE" and path.startswith("/notifications/threads/"):
            thread_id = urllib.parse.unquote(path.rsplit("/", 1)[-1])
            if thread_id not in self.threads:
                raise AssertionError("unknown thread")
            if thread_id in self.fail_delete_ids:
                raise clearer.NotificationError(
                    "GitHub API DELETE /notifications/threads/{thread_id} failed "
                    "HTTP 500: Internal Server Error"
                )
            state = self.threads[thread_id]
            state.update(unread=False, done=True)
            if self.bump_on_delete:
                state["updated"] = self.latest() + 1
            self.deleted.append(thread_id)
            if self.on_delete is not None:
                self.on_delete(self, thread_id)
            return clearer.ApiResponse(204, None, {})

        raise AssertionError(f"unexpected request: {method} {path} {payload}")


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []
        self.reads: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now

    def time(self) -> float:
        return self.now


@contextlib.contextmanager
def offline(api: FakeGitHub):
    clock = FakeClock()
    api.clock = clock
    with (
        patch.object(clearer, "request", api.request),
        patch.object(clearer.time, "sleep", clock.sleep),
        patch.object(clearer.time, "monotonic", clock.monotonic),
        patch.object(clearer.time, "time", clock.time),
    ):
        yield clock


class FakeResponse:
    def __init__(self, status: int, body: bytes = b"", headers=None) -> None:
        self.status = status
        self.body = body
        self.headers = email.message.Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self.body


def http_error(
    *,
    status: int = 403,
    detail: bytes = b'{"message":"API rate limit exceeded"}',
    retry_after: str | None = None,
    remaining: str | None = None,
    reset: str | None = None,
) -> urllib.error.HTTPError:
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    if remaining is not None:
        headers["X-RateLimit-Remaining"] = remaining
    if reset is not None:
        headers["X-RateLimit-Reset"] = reset
    return urllib.error.HTTPError(
        url="https://api.github.com/notifications/threads/secret-id",
        code=status,
        msg="Forbidden",
        hdrs=headers,
        fp=io.BytesIO(detail),
    )


def assert_count_only(test: unittest.TestCase, report: dict, api: FakeGitHub) -> None:
    rendered = json.dumps(report, sort_keys=True)
    for retired in (
        "cleared_count",
        "delete_attempts",
        "after_inbox_count",
        "before_inbox_count",
        "rate_limit_retries",
    ):
        test.assertNotIn(retired, report)
    test.assertNotEqual(report["status"], "CLEARED")
    test.assertEqual(report["full_inbox_state"], "UNKNOWN")
    test.assertEqual(report["issue_receipt"], "NOT_PUBLISHED")
    test.assertEqual(
        report["full_inbox_verification"], "UNVERIFIED_NO_READ_ONLY_OBSERVABLE"
    )
    test.assertFalse(report["notification_content_recorded"])
    test.assertFalse(report["thread_ids_recorded"])
    for state in api.threads.values():
        test.assertNotIn(FakeGitHub.updated_at(state["updated"]), rendered)
    for thread_id in api.threads:
        if not thread_id.isdigit():
            test.assertNotIn(thread_id, rendered)


class ListingContractTests(unittest.TestCase):
    def test_history_listing_keeps_done_threads_and_paginates_at_api_maximum(self):
        api = FakeGitHub(53)
        for thread_id in ("1", "2", "3"):
            api.threads[thread_id].update(done=True, unread=False)
        with patch.object(clearer, "request", api.request):
            history = clearer.list_notification_threads("classic-token", include_read=True)
            unread = clearer.list_notification_threads("classic-token", include_read=False)
        self.assertEqual(clearer.PER_PAGE, 50)
        self.assertEqual(history.pages, 2)
        self.assertEqual(len(history.versions), 53)
        self.assertLessEqual({"1", "2", "3"}, set(history.versions))
        self.assertEqual(len(unread.versions), 25)
        self.assertEqual(list(history.versions)[:2], ["53", "52"])
        self.assertEqual(history.poll_interval_seconds, 60.0)

    def test_listing_rejects_thread_without_update_version(self):
        def no_version(token, method, path, payload=None, *, stats=None, deadline=None):
            return clearer.ApiResponse(200, [{"id": "1"}], {})

        with patch.object(clearer, "request", no_version):
            with self.assertRaises(clearer.NotificationError) as raised:
                clearer.list_notification_threads("classic-token", include_read=True)
        self.assertIn("updated_at", str(raised.exception))

    def test_mark_thread_done_uses_documented_delete_endpoint_and_keeps_history(self):
        api = FakeGitHub(1)
        with patch.object(clearer, "request", api.request):
            clearer.mark_thread_done("classic-token", "1")
            history = clearer.list_notification_threads("classic-token", include_read=True)
        self.assertEqual(api.deleted, ["1"])
        self.assertTrue(api.threads["1"]["done"])
        self.assertIn("1", history.versions)


class AcknowledgementTests(unittest.TestCase):
    def test_repeated_204s_on_unchanged_history_are_not_replayed(self):
        api = FakeGitHub(120)
        snapshots = []
        with offline(api):
            report = clearer.clear_notifications("classic-token", progress=snapshots.append)
        self.assertEqual(len(api.deleted), 120)
        self.assertEqual(len(set(api.deleted)), 120)
        self.assertEqual(report["status"], "UNREAD_ZERO_VERIFIED")
        self.assertEqual(report["stop_reason"], "NO_NEW_OR_ADVANCED_THREADS")
        self.assertEqual(report["rounds"], 1)
        self.assertEqual(report["api_history_before_count"], 120)
        # The history does not shrink after Done; the old loop never converged.
        self.assertEqual(report["api_history_last_count"], 120)
        self.assertEqual(report["before_unread_count"], 60)
        self.assertEqual(report["after_unread_count"], 0)
        self.assertEqual(report["after_unread_measurement"], "MEASURED")
        self.assertTrue(report["unread_zero_verified"])
        self.assertEqual(report["distinct_done_acknowledged"], 120)
        self.assertEqual(report["done_acknowledgements"], 120)
        self.assertEqual(report["reacknowledged_after_update"], 0)
        self.assertEqual(report["unchanged_repeats_skipped"], 120)
        self.assertEqual(report["rate_limit_retries_observed"], 0)
        self.assertEqual(report["rate_limit_retry_ceiling"], clearer.RATE_LIMIT_RETRIES)
        # /user + history(3 pages) + unread(2 pages) + 120 DELETE + history(3) + unread(1)
        self.assertEqual(report["logical_api_calls"], 1 + 3 + 2 + 120 + 3 + 1)
        self.assertEqual(report["http_attempts"], report["logical_api_calls"])
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["measurement_errors"], [])
        self.assertTrue(snapshots)
        self.assertTrue(all(snapshot["status"] == "RUNNING" for snapshot in snapshots))
        assert_count_only(self, report, api)

    def test_no_progress_stop_when_acknowledgement_advances_every_thread(self):
        api = FakeGitHub(6)
        api.bump_on_delete = True
        with offline(api):
            report = clearer.clear_notifications("classic-token")
        self.assertEqual(sorted(api.deleted, key=int), [str(i) for i in range(1, 7)])
        self.assertEqual(report["stop_reason"], "NO_PROGRESS")
        self.assertEqual(report["rounds"], 1)
        self.assertEqual(report["done_acknowledgements"], 6)
        self.assertEqual(report["status"], "FAILED")
        # The independent unread readback still ran and is reported separately.
        self.assertEqual(report["after_unread_measurement"], "MEASURED")
        self.assertEqual(report["after_unread_count"], 0)
        self.assertTrue(report["unread_zero_verified"])
        assert_count_only(self, report, api)

    def test_reactivated_thread_is_acknowledged_again_once(self):
        api = FakeGitHub(4)

        def reactivate(fake, thread_id):
            if thread_id == "1" and fake.deleted.count("1") == 1:
                fake.touch("2")

        api.on_delete = reactivate
        with offline(api):
            report = clearer.clear_notifications("classic-token")
        self.assertEqual(api.deleted.count("2"), 2)
        self.assertEqual(len(api.deleted), 5)
        self.assertEqual(report["rounds"], 2)
        self.assertEqual(report["distinct_done_acknowledged"], 4)
        self.assertEqual(report["done_acknowledgements"], 5)
        self.assertEqual(report["reacknowledged_after_update"], 1)
        self.assertEqual(report["stop_reason"], "NO_NEW_OR_ADVANCED_THREADS")
        self.assertEqual(report["status"], "UNREAD_ZERO_VERIFIED")

    def test_thread_arriving_during_acknowledgement_is_processed_once(self):
        api = FakeGitHub(2)

        def arrive(fake, thread_id):
            if "999" not in fake.threads:
                fake.add("999", unread=True, updated=fake.latest() + 1)

        api.on_delete = arrive
        with offline(api):
            report = clearer.clear_notifications("classic-token")
        self.assertEqual(report["api_history_before_count"], 2)
        self.assertEqual(api.deleted.count("999"), 1)
        self.assertEqual(report["distinct_done_acknowledged"], 3)
        self.assertEqual(report["done_acknowledgements"], 3)
        self.assertEqual(report["rounds"], 2)
        self.assertEqual(report["status"], "UNREAD_ZERO_VERIFIED")

    def test_page_reordering_and_concurrent_arrival_are_caught_without_replay(self):
        api = FakeGitHub(60)
        fired = []

        def reorder(fake, include_read, page):
            if include_read and page == 2 and not fired:
                fired.append(True)
                # A new thread lands on page 1 and the oldest thread is updated
                # onto page 1 while page 2 is being read: page-1 items shift
                # onto page 2 (duplicates) and two threads are skipped.
                fake.add("900", unread=True, updated=fake.latest() + 1)
                fake.touch("1")

        api.on_page = reorder
        with offline(api):
            report = clearer.clear_notifications("classic-token")
        self.assertEqual(report["api_history_before_count"], 59)
        self.assertEqual(len(api.deleted), 61)
        self.assertEqual(len(set(api.deleted)), 61)
        self.assertEqual(set(api.deleted), set(api.threads))
        self.assertEqual(report["rounds"], 2)
        self.assertEqual(report["reacknowledged_after_update"], 0)
        self.assertEqual(report["api_history_last_count"], 61)
        self.assertEqual(report["status"], "UNREAD_ZERO_VERIFIED")

    def test_final_unread_readback_runs_after_failure(self):
        api = FakeGitHub(6)
        api.add("secret-thread-id", unread=True, updated=3)
        api.fail_delete_ids.add("secret-thread-id")
        with offline(api):
            report = clearer.clear_notifications("classic-token")
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["stop_reason"], "ERROR")
        self.assertEqual(len(report["errors"]), 1)
        self.assertIn("{thread_id}", report["errors"][0])
        self.assertEqual(report["measurement_errors"], [])
        self.assertEqual(report["after_unread_measurement"], "MEASURED")
        unread_left = sum(
            1 for state in api.threads.values() if state["unread"] and not state["done"]
        )
        self.assertGreater(unread_left, 0)
        self.assertEqual(report["after_unread_count"], unread_left)
        self.assertFalse(report["unread_zero_verified"])
        self.assertEqual(api.reads[-1], (False, 1))
        assert_count_only(self, report, api)

    def test_unavailable_final_readback_is_reported_unknown(self):
        api = FakeGitHub(4)
        api.fail_unread_reads_after = 1
        with offline(api):
            report = clearer.clear_notifications("classic-token")
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["stop_reason"], "NO_NEW_OR_ADVANCED_THREADS")
        self.assertIsNone(report["after_unread_count"])
        self.assertEqual(report["after_unread_measurement"], "UNAVAILABLE")
        self.assertEqual(len(report["measurement_errors"]), 1)
        self.assertFalse(report["unread_zero_verified"])
        self.assertEqual(report["status"], "FAILED")

    def test_poll_interval_is_honored_before_later_reads(self):
        api = FakeGitHub(3, poll_interval="7")
        with offline(api) as clock:
            report = clearer.clear_notifications("classic-token")
        self.assertEqual(len(clock.reads), 4)
        gaps = [later - earlier for earlier, later in zip(clock.reads, clock.reads[1:])]
        self.assertTrue(all(gap >= 7 for gap in gaps), gaps)
        self.assertEqual(report["poll_interval_seconds"], 7.0)

    def test_poll_interval_above_former_cap_is_honored_in_full(self):
        api = FakeGitHub(1, poll_interval="900")
        with offline(api) as clock:
            report = clearer.clear_notifications("classic-token")
        gaps = [later - earlier for earlier, later in zip(clock.reads, clock.reads[1:])]
        self.assertTrue(gaps)
        self.assertTrue(all(gap >= 900 for gap in gaps), gaps)
        self.assertEqual(report["poll_interval_seconds"], 900.0)
        self.assertFalse(hasattr(clearer, "POLL_INTERVAL_MAX_SECONDS"))
        self.assertFalse(report["job_deadline_configured"])
        self.assertEqual(report["status"], "UNREAD_ZERO_VERIFIED")

    def test_full_poll_interval_waits_within_job_deadline_complete(self):
        api = FakeGitHub(1, poll_interval="900")
        with offline(api) as clock:
            start = clock.now
            report = clearer.clear_notifications("classic-token", deadline=start + 86400)
        self.assertTrue(clock.sleeps)
        self.assertTrue(all(seconds >= 900 for seconds in clock.sleeps), clock.sleeps)
        self.assertEqual(report["status"], "UNREAD_ZERO_VERIFIED")
        self.assertTrue(report["job_deadline_configured"])

    def test_poll_wait_that_would_pass_job_deadline_stops_and_reports(self):
        api = FakeGitHub(2, poll_interval="900")
        with offline(api) as clock:
            start = clock.now
            report = clearer.clear_notifications("classic-token", deadline=start + 600)
        self.assertEqual(clock.sleeps, [])
        self.assertLessEqual(clock.now, start + 600)
        self.assertEqual(report["stop_reason"], "DEADLINE")
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(len(report["errors"]), 1)
        self.assertIn("DeadlineExceeded", report["errors"][0])
        self.assertIn("X-Poll-Interval", report["errors"][0])
        self.assertEqual(report["after_unread_measurement"], "UNAVAILABLE")
        self.assertIsNone(report["after_unread_count"])
        self.assertEqual(len(report["measurement_errors"]), 1)
        self.assertFalse(report["unread_zero_verified"])
        self.assertTrue(report["job_deadline_configured"])
        self.assertEqual(api.deleted, [])
        assert_count_only(self, report, api)

    def test_mutation_pacing_is_bounded_by_job_deadline(self):
        api = FakeGitHub(3, poll_interval="0")
        with offline(api) as clock:
            start = clock.now
            report = clearer.clear_notifications("classic-token", deadline=start + 1.5)
        self.assertLessEqual(clock.now, start + 1.5)
        self.assertEqual(report["stop_reason"], "DEADLINE")
        self.assertIn("Mutation pacing", report["errors"][0])
        self.assertEqual(len(api.deleted), 2)
        self.assertEqual(report["after_unread_measurement"], "MEASURED")
        self.assertEqual(report["status"], "FAILED")

    def test_missing_poll_interval_uses_fallback(self):
        api = FakeGitHub(1, poll_interval=None)
        with offline(api) as clock:
            clearer.clear_notifications("classic-token")
        gaps = [later - earlier for earlier, later in zip(clock.reads, clock.reads[1:])]
        self.assertTrue(all(gap >= clearer.POLL_INTERVAL_FALLBACK_SECONDS for gap in gaps))

    def test_mutating_requests_are_paced_serially(self):
        api = FakeGitHub(3)
        with offline(api) as clock:
            clearer.clear_notifications("classic-token")
        self.assertEqual(clock.sleeps.count(clearer.MUTATION_DELAY_SECONDS), 2)

    def test_round_limit_is_not_raised_and_stops_honestly(self):
        api = FakeGitHub(1)

        def keep_arriving(fake, thread_id):
            fake.add(f"n{len(fake.threads)}", unread=True, updated=fake.latest() + 1)

        api.on_delete = keep_arriving
        with offline(api):
            report = clearer.clear_notifications("classic-token")
        self.assertEqual(clearer.MAX_ROUNDS, 8)
        self.assertEqual(report["rounds"], 8)
        self.assertEqual(report["stop_reason"], "ROUND_LIMIT")
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(len(api.deleted), 8)
        self.assertEqual(report["after_unread_measurement"], "MEASURED")


class RequestTests(unittest.TestCase):
    def test_rate_limit_delay_honors_retry_after(self):
        self.assertEqual(
            clearer.rate_limit_delay(
                status=429,
                detail="",
                headers={"Retry-After": "7"},
                attempt=0,
                now_epoch=100,
            ),
            7,
        )

    def test_rate_limit_delay_honors_primary_reset_with_safety_margin(self):
        self.assertEqual(
            clearer.rate_limit_delay(
                status=403,
                detail="API rate limit exceeded",
                headers={
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": "110",
                },
                attempt=0,
                now_epoch=100,
            ),
            15,
        )

    def test_rate_limit_delay_ignores_non_403_429_statuses(self):
        self.assertIsNone(
            clearer.rate_limit_delay(
                status=503,
                detail="rate limit",
                headers={"Retry-After": "7"},
                attempt=0,
                now_epoch=100,
            )
        )

    def test_request_counts_attempts_and_observed_rate_limit_retries(self):
        error = http_error(retry_after="1")
        response = FakeResponse(204)
        stats = clearer.RequestStats()
        with (
            patch.object(
                clearer.urllib.request,
                "urlopen",
                side_effect=[error, response],
            ),
            patch.object(clearer.time, "sleep", return_value=None) as sleeper,
        ):
            status, payload, _headers = clearer.request(
                "classic-token",
                "DELETE",
                "/notifications/threads/secret-id",
                stats=stats,
            )
        self.assertEqual(status, 204)
        self.assertIsNone(payload)
        sleeper.assert_called_once_with(1.0)
        self.assertEqual(stats.logical_calls, 1)
        self.assertEqual(stats.http_attempts, 2)
        self.assertEqual(stats.rate_limit_retries_observed, 1)

    def test_rate_limit_retry_that_would_pass_job_deadline_fails_without_sleeping(self):
        error = http_error(status=429, retry_after="120")
        stats = clearer.RequestStats()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stderr(stderr),
            patch.object(clearer.urllib.request, "urlopen", side_effect=[error]) as opener,
            patch.object(clearer.time, "sleep") as sleeper,
            patch.object(clearer.time, "time", return_value=5000.0),
        ):
            with self.assertRaises(clearer.DeadlineExceeded) as raised:
                clearer.request(
                    "classic-token",
                    "DELETE",
                    "/notifications/threads/secret-id",
                    stats=stats,
                    deadline=5060.0,
                )
        sleeper.assert_not_called()
        self.assertEqual(opener.call_count, 1)
        self.assertEqual(stats.rate_limit_retries_observed, 0)
        self.assertNotIn("retrying", stderr.getvalue())
        self.assertIn("Rate-limit retry", str(raised.exception))
        self.assertNotIn("secret-id", str(raised.exception))

    def test_job_deadline_parses_epoch_and_rejects_invalid_values(self):
        self.assertIsNone(clearer.job_deadline({}))
        self.assertIsNone(clearer.job_deadline({"CLEARANCE_DEADLINE_EPOCH": " "}))
        self.assertEqual(
            clearer.job_deadline({"CLEARANCE_DEADLINE_EPOCH": "1791900000"}),
            1791900000.0,
        )
        for bad in ("soon", "-1", "nan", "inf"):
            with self.subTest(bad=bad), self.assertRaises(clearer.NotificationError):
                clearer.job_deadline({"CLEARANCE_DEADLINE_EPOCH": bad})

    def test_request_keeps_response_headers_for_poll_interval(self):
        response = FakeResponse(200, b"[]", {"X-Poll-Interval": "90"})
        with patch.object(clearer.urllib.request, "urlopen", return_value=response):
            result = clearer.request("classic-token", "GET", "/notifications?all=false")
        self.assertEqual(result.payload, [])
        self.assertEqual(clearer._header(result.headers, "x-poll-interval"), "90")

    def test_non_rate_limit_error_redacts_thread_identifier(self):
        error = http_error(
            detail=b'{"message":"Forbidden"}',
            remaining="10",
        )
        stats = clearer.RequestStats()
        with patch.object(
            clearer.urllib.request,
            "urlopen",
            side_effect=error,
        ):
            with self.assertRaises(clearer.NotificationError) as raised:
                clearer.request(
                    "classic-token",
                    "DELETE",
                    "/notifications/threads/secret-id",
                    stats=stats,
                )
        message = str(raised.exception)
        self.assertIn("/notifications/threads/{thread_id}", message)
        self.assertNotIn("secret-id", message)
        self.assertEqual(stats.http_attempts, 1)
        self.assertEqual(stats.rate_limit_retries_observed, 0)


class WorkflowPhaseTests(unittest.TestCase):
    def write(self, directory: Path, name: str, **overrides) -> Path:
        report = {
            "schema": clearer.SCHEMA,
            "status": "UNREAD_ZERO_VERIFIED",
            "after_unread_measurement": "MEASURED",
            "after_unread_count": 0,
            "unread_zero_verified": True,
            "full_inbox_state": "UNKNOWN",
        }
        report.update(overrides)
        path = directory / name
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def test_describe_phase_names_states_instead_of_sentinel_codes(self):
        self.assertEqual(clearer.describe_phase("skipped", ""), "SKIPPED")
        self.assertEqual(clearer.describe_phase("", ""), "NOT_REACHED")
        self.assertEqual(clearer.describe_phase("success", "0"), "PASSED")
        self.assertEqual(clearer.describe_phase("success", "1"), "FAILED(exit=1)")
        self.assertEqual(clearer.describe_phase("cancelled", ""), "CANCELLED")
        self.assertEqual(
            clearer.describe_phase("failure", ""),
            "FAILED(outcome=failure, exit=unavailable)",
        )

    def enforce(self, directory: Path, *, outcome="success", exit_code="0", **overrides):
        return clearer.enforce_phases(
            clearance_outcome=outcome,
            clearance_exit_code=exit_code,
            report_path=self.write(directory, "receipt.json", **overrides),
        )

    def test_failed_clearance_is_named_and_states_no_issue_receipt(self):
        for outcome, exit_code, expected in (
            ("success", "1", "clearance=FAILED(exit=1)"),
            ("skipped", "", "clearance=SKIPPED"),
            ("", "", "clearance=NOT_REACHED"),
        ):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as raw:
                code, message = self.enforce(
                    Path(raw), outcome=outcome, exit_code=exit_code, status="FAILED"
                )
                self.assertEqual(code, 1)
                self.assertIn(expected, message)
                self.assertIn("No issue receipt is published", message)
                self.assertNotIn("post-receipt", message)
                self.assertNotIn("=2", message)

    def test_enforce_phases_verifies_unread_zero_without_inbox_zero_claim(self):
        with tempfile.TemporaryDirectory() as raw:
            code, message = self.enforce(Path(raw))
        self.assertEqual(code, 0)
        self.assertIn("Unread-zero (all=false) verified; clearance=PASSED", message)
        self.assertIn("UNKNOWN", message)
        self.assertIn("No issue receipt is published", message)
        self.assertIn(clearer.RECEIPT_ARTIFACT, message)
        self.assertNotIn("receipt publication", message)
        self.assertNotIn("inbox verified at zero", message.lower())

    def test_enforce_phases_rejects_nonzero_or_unmeasured_unread(self):
        for overrides in (
            {"after_unread_count": 1},
            {"after_unread_measurement": "UNAVAILABLE", "after_unread_count": None},
            {"status": "CLEARED"},
            {"full_inbox_state": "ZERO"},
            {"schema": "szl.github-notification-clearance/v2"},
        ):
            with self.subTest(overrides=overrides), tempfile.TemporaryDirectory() as raw:
                code, message = self.enforce(Path(raw), **overrides)
                self.assertEqual(code, 1)
                self.assertIn("No issue receipt is published", message)

    def test_enforce_phases_rejects_unreadable_or_non_object_receipt(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            missing, _ = clearer.enforce_phases(
                clearance_outcome="success",
                clearance_exit_code="0",
                report_path=directory / "missing.json",
            )
            listed = directory / "list.json"
            listed.write_text("[]", encoding="utf-8")
            not_object, message = clearer.enforce_phases(
                clearance_outcome="success",
                clearance_exit_code="0",
                report_path=listed,
            )
        self.assertEqual(missing, 1)
        self.assertEqual(not_object, 1)
        self.assertIn("does not verify unread-zero", message)

    def test_enforce_phases_accepts_only_the_integer_zero(self):
        for value in (False, 0.0, "0", [], None):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as raw:
                code, message = self.enforce(Path(raw), after_unread_count=value)
                self.assertEqual(code, 1)
                self.assertIn("does not verify unread-zero", message)
        with tempfile.TemporaryDirectory() as raw:
            code, _message = self.enforce(Path(raw), after_unread_count=0)
        self.assertEqual(code, 0)

    def test_main_enforce_reads_the_clearance_step_environment(self):
        with tempfile.TemporaryDirectory() as raw, contextlib.chdir(raw):
            self.write(Path(raw), "github-notification-clearance.json")
            stdout = io.StringIO()
            with (
                patch.dict(
                    os.environ,
                    {"CLEARANCE_OUTCOME": "success", "CLEARANCE_EXIT_CODE": "0"},
                    clear=True,
                ),
                contextlib.redirect_stdout(stdout),
            ):
                passed = clearer.main(["--enforce-phases"])
            with (
                patch.dict(
                    os.environ,
                    {"CLEARANCE_OUTCOME": "success", "CLEARANCE_EXIT_CODE": "1"},
                    clear=True,
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                failed = clearer.main(["--enforce-phases"])
            skipped_out = io.StringIO()
            with (
                patch.dict(
                    os.environ,
                    {"CLEARANCE_OUTCOME": "skipped", "CLEARANCE_EXIT_CODE": ""},
                    clear=True,
                ),
                contextlib.redirect_stdout(skipped_out),
            ):
                skipped = clearer.main(["--enforce-phases"])
        self.assertEqual(passed, 0)
        self.assertEqual(failed, 1)
        self.assertEqual(skipped, 1)
        self.assertIn("No issue receipt is published", stdout.getvalue())
        self.assertIn("clearance=SKIPPED", skipped_out.getvalue())
        self.assertIn("No issue receipt is published", skipped_out.getvalue())

    def workflow_text(self) -> str:
        return (
            MODULE_PATH.parents[1] / "workflows" / "clear-personal-notifications.yml"
        ).read_text(encoding="utf-8")

    def test_workflow_records_job_deadline_before_the_clearance_step(self):
        workflow = self.workflow_text()
        timeouts = re.findall(r"^\s*timeout-minutes:\s*(\d+)\s*$", workflow, re.M)
        budget = re.search(
            r"CLEARANCE_DEADLINE_EPOCH=\$\(\( \$\(date \+%s\) \+ \((\d+) - (\d+)\) \* 60 \)\)",
            workflow,
        )
        self.assertEqual(len(timeouts), 1)
        self.assertIsNotNone(budget)
        self.assertEqual(budget.group(1), timeouts[0])
        self.assertGreater(int(budget.group(2)), 0)
        self.assertLess(int(budget.group(2)), int(timeouts[0]))
        self.assertLess(
            budget.start(), workflow.index("--report github-notification-clearance.json")
        )

    def test_workflow_publishes_no_issue_receipt_and_holds_no_write_permission(self):
        workflow = self.workflow_text()
        self.assertIsNone(re.search(r"^\s*[a-z-]+:\s*write\s*$", workflow, re.M))
        self.assertNotIn("write-all", workflow)
        for retired in ("gh issue", "RECEIPT_TITLE", "post_receipt", "POST_RECEIPT", "github.token"):
            self.assertNotIn(retired, workflow)
        self.assertEqual(workflow.count("--report "), 1)
        self.assertIn(f"name: {clearer.RECEIPT_ARTIFACT}\n", workflow)
        self.assertIn("retention-days: 30", workflow)
        self.assertIn("No issue receipt is published.", workflow)
        self.assertIn("CLEARANCE_OUTCOME: ${{ steps.clearance.outcome }}", workflow)
        self.assertIn("CLEARANCE_EXIT_CODE: ${{ steps.clearance.outputs.exit_code }}", workflow)

    def test_main_with_invalid_job_deadline_fails_closed_without_api_calls(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "receipt.json"
            with (
                patch.dict(
                    os.environ,
                    {
                        "GH_NOTIFICATIONS_TOKEN": "classic-token",
                        "CLEARANCE_DEADLINE_EPOCH": "soon",
                    },
                    clear=True,
                ),
                patch.object(
                    clearer, "request", side_effect=AssertionError("no API call expected")
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                code = clearer.main(["--report", str(path)])
            report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["after_unread_measurement"], "UNAVAILABLE")
        self.assertEqual(len(report["errors"]), 1)
        self.assertIn("CLEARANCE_DEADLINE_EPOCH", report["errors"][0])
        self.assertEqual(len(report["measurement_errors"]), 1)
        self.assertNotIn("classic-token", json.dumps(report))

    def test_main_without_token_writes_count_only_failure_receipt(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "receipt.json"
            with (
                patch.dict(os.environ, {}, clear=True),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                code = clearer.main(["--report", str(path)])
            report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["after_unread_measurement"], "UNAVAILABLE")
        self.assertIsNone(report["after_unread_count"])
        self.assertEqual(report["full_inbox_state"], "UNKNOWN")
        self.assertEqual(report["issue_receipt"], "NOT_PUBLISHED")
        self.assertEqual(len(report["errors"]), 1)
        self.assertEqual(len(report["measurement_errors"]), 1)


if __name__ == "__main__":
    unittest.main()
