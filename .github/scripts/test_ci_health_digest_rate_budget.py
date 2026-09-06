#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import io
import json
import os
from email.message import Message
from pathlib import Path
import sys
import unittest
import urllib.error
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ci_health_digest_http as http


class Response:
    def __init__(self, payload, *, status=200, headers=None):
        self.status = status
        self.headers = headers or Message()
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._raw


def error(status: int, body: str, headers=None):
    return urllib.error.HTTPError(
        "https://api.github.com/example",
        status,
        body,
        headers or Message(),
        io.BytesIO(body.encode("utf-8")),
    )


class RateBudgetTests(unittest.TestCase):
    def setUp(self):
        http._reset_rate_limit_state_for_tests()

    def tearDown(self):
        http._reset_rate_limit_state_for_tests()

    def test_rate_limit_classification_precedes_generic_forbidden(self):
        self.assertEqual(
            http.classify_http_detail("API rate limit exceeded for user"),
            "rate_limited",
        )
        self.assertEqual(
            http.classify_http_detail("Resource not accessible by integration"),
            "unauthorized",
        )

    def test_retry_after_is_authoritative(self):
        headers = Message()
        headers["Retry-After"] = "17"
        headers["X-RateLimit-Reset"] = "9999999999"
        self.assertEqual(http._rate_limit_delay(headers, 1), 17.0)

    def test_primary_reset_wait_includes_clock_cushion(self):
        headers = Message()
        headers["X-RateLimit-Reset"] = "1060"
        with patch.object(http.time, "time", return_value=1000.0):
            self.assertEqual(http._rate_limit_delay(headers, 1), 62.0)

    def test_wait_beyond_reviewed_deadline_fails_closed(self):
        with patch.dict(
            os.environ,
            {
                "CI_HEALTH_MAX_RATE_LIMIT_WAIT_SECONDS": "10",
                "CI_HEALTH_DEADLINE_SECONDS": "100",
            },
            clear=False,
        ):
            with self.assertRaises(http.ApiError) as raised:
                http._publish_rate_limit_delay(
                    11.0,
                    operation="bounded probe",
                    status=429,
                )
        self.assertEqual(
            raised.exception.detail_class,
            "rate_limit_wait_exceeded",
        )
        self.assertEqual(raised.exception.retry_after_seconds, 11)

    def test_retryable_403_rate_limit_reaches_second_attempt(self):
        headers = Message()
        headers["Retry-After"] = "1"
        first = error(403, "API rate limit exceeded", headers)
        second = Response({"ok": True})
        with patch.object(
            http.urllib.request,
            "urlopen",
            side_effect=[first, second],
        ) as opener, patch.object(
            http,
            "_wait_for_shared_rate_budget",
        ), patch.object(
            http,
            "_publish_rate_limit_delay",
        ) as publish:
            status, payload = http.request_json(
                "secret-not-recorded",
                "https://api.github.com/example",
                operation="rate-limited fixture",
                attempts=2,
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(opener.call_count, 2)
        publish.assert_called_once_with(
            1.0,
            operation="rate-limited fixture",
            status=403,
        )

    def test_ordinary_403_is_terminal_and_not_retried(self):
        first = error(403, "Resource not accessible by integration")
        with patch.object(
            http.urllib.request,
            "urlopen",
            side_effect=first,
        ) as opener, patch.object(
            http,
            "_wait_for_shared_rate_budget",
        ):
            with self.assertRaises(http.ApiError) as raised:
                http.request_json(
                    "secret-not-recorded",
                    "https://api.github.com/example",
                    operation="unauthorized fixture",
                    attempts=8,
                )
        self.assertEqual(opener.call_count, 1)
        self.assertEqual(raised.exception.detail_class, "unauthorized")

    def test_success_with_exhausted_primary_budget_coordinates_next_call(self):
        headers = Message()
        headers["X-RateLimit-Remaining"] = "0"
        headers["X-RateLimit-Reset"] = "1010"
        response = Response({"ok": True}, headers=headers)
        with patch.object(
            http.urllib.request,
            "urlopen",
            return_value=response,
        ), patch.object(
            http,
            "_wait_for_shared_rate_budget",
        ), patch.object(
            http,
            "_publish_rate_limit_delay",
        ) as publish, patch.object(http.time, "time", return_value=1000.0):
            status, payload = http.request_json(
                "secret-not-recorded",
                "https://api.github.com/example",
                operation="last-budget fixture",
            )
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True})
        publish.assert_called_once_with(
            12.0,
            operation="last-budget fixture",
            status=429,
        )


class WorkflowRateBudgetContractTests(unittest.TestCase):
    def test_workflow_is_deadline_bounded_and_app_mint_is_least_privilege(self):
        source = (ROOT / ".github/workflows/ci-health-digest.yml").read_text(
            encoding="utf-8"
        )
        for marker in (
            'CI_HEALTH_HTTP_CONCURRENCY: "3"',
            'CI_HEALTH_MAX_RATE_LIMIT_WAIT_SECONDS: "3900"',
            'CI_HEALTH_DEADLINE_SECONDS: "5400"',
            "test_ci_health_digest_rate_budget.py",
            "timeout-minutes: 100",
        ):
            self.assertIn(marker, source)

        app_step = source.split(
            "- name: Mint preferred qillqaq organization reader",
            1,
        )[1].split(
            "- name: Sweep the verified organization estate",
            1,
        )[0]
        self.assertIn("permission-actions: read", app_step)
        self.assertIn("permission-contents: read", app_step)
        self.assertNotIn(
            "permission-organization-administration: read",
            app_step,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
