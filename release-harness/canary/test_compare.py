#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the staging canary. No production host is contacted."""

from __future__ import annotations

import http.server
import os
import subprocess
import sys
import threading
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import compare  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class TestAllow(unittest.TestCase):
    def test_no_staging_flag_refuses_localhost_without_a_request(self) -> None:
        calls = []

        def transport(url: str) -> compare.Sample:
            calls.append(url)
            return compare.Sample(True, 1.0)

        with self.assertRaises(compare.Refusal) as caught:
            compare.run_comparison(
                canary_url="http://127.0.0.1:9/canary",
                control_url="http://127.0.0.1:9/control",
                staging=False,
                target_class=None,
                caps=compare.Caps(1, 5, 4),
                stops=compare.StopThresholds(1, 1000),
                samples_per_side=1,
                transport=transport,
            )
        self.assertIn("no staging flag", caught.exception.reason)
        self.assertEqual(calls, [])

    def test_production_apexes_are_refused_even_when_marked_staging(self) -> None:
        for url in (
            "https://a-11-oy.com/",
            "https://www.a-11-oy.com/console",
            "https://a11oy.net/proof",
            "https://inference.a-11-oy.com/v1",
            "https://A-11-OY.com",
            "https://user:pw@a-11-oy.com/",
        ):
            with self.subTest(url=url):
                with self.assertRaises(compare.Refusal):
                    compare.allow_target(url, staging=True, target_class="staging")

    def test_prod_space_is_refused_and_named_staging_space_needs_both_marks(self) -> None:
        prod = "https://szlholdings-a11oy.hf.space/api/build-info"
        named = "https://szlholdings-a11oy-staging.hf.space/api/build-info"
        with self.assertRaises(compare.Refusal):
            compare.allow_target(prod, staging=True, target_class="staging")
        with self.assertRaises(compare.Refusal):
            compare.allow_target(named, staging=True, target_class=None)
        self.assertEqual(
            compare.allow_target(named, staging=True, target_class="staging"),
            "szlholdings-a11oy-staging.hf.space",
        )

    def test_lookalike_host_is_not_treated_as_the_apex(self) -> None:
        host = compare.allow_target(
            "https://a-11-oy.com.example.net/status", staging=True
        )
        self.assertEqual(host, "a-11-oy.com.example.net")

    def test_subdomain_of_the_apex_is_denied_without_an_explicit_staging_name(self) -> None:
        with self.assertRaises(compare.Refusal):
            compare.allow_target("https://edge.a-11-oy.com/", staging=True, target_class="staging")
        self.assertEqual(
            compare.allow_target(
                "https://staging.a-11-oy.com/", staging=True, target_class="staging"
            ),
            "staging.a-11-oy.com",
        )


class TestComparison(unittest.TestCase):
    def test_p95_nearest_rank_and_error_rate(self) -> None:
        self.assertEqual(compare.percentile_95(list(range(1, 101))), 95)
        samples = [
            compare.Sample(True, 10),
            compare.Sample(False, 20),
            compare.Sample(True, 30),
            compare.Sample(True, 40),
        ]
        self.assertEqual(compare.error_rate(samples), 0.25)

    def test_stop_threshold_fires_before_later_requests(self) -> None:
        calls = []

        def transport(url: str) -> compare.Sample:
            calls.append(url)
            return compare.Sample(ok=False, latency_ms=5)

        report = compare.run_comparison(
            canary_url="http://127.0.0.1/canary",
            control_url="http://127.0.0.1/control",
            staging=True,
            target_class=None,
            caps=compare.Caps(max_rps=5, max_duration_s=30, max_requests=10),
            stops=compare.StopThresholds(max_error_rate=0.0, max_p95_ms=1000),
            samples_per_side=5,
            transport=transport,
            clock=lambda: 0.0,
            sleep=lambda _seconds: None,
        )
        self.assertEqual(calls, ["http://127.0.0.1/canary"])
        self.assertEqual(report["issued"], 1)
        self.assertTrue(report["stopped"])
        self.assertEqual(report["stop_reason"], "error_rate")
        self.assertEqual(report["stop_side"], "canary")
        self.assertIsNone(report["control"]["error_rate"])

    def test_plan_above_max_requests_refuses_before_transport(self) -> None:
        def transport(_url: str) -> compare.Sample:
            raise AssertionError("transport called")

        with self.assertRaises(compare.Refusal):
            compare.run_comparison(
                canary_url="http://127.0.0.1/canary",
                control_url="http://127.0.0.1/control",
                staging=True,
                target_class=None,
                caps=compare.Caps(1, 5, 2),
                stops=compare.StopThresholds(1, 1000),
                samples_per_side=2,
                transport=transport,
            )

    def test_absolute_ceilings_refuse_before_transport(self) -> None:
        with self.assertRaises(compare.Refusal):
            compare.Caps(max_rps=6, max_duration_s=5, max_requests=4)
        with self.assertRaises(compare.Refusal):
            compare.Caps(max_rps=1, max_duration_s=31, max_requests=4)
        with self.assertRaises(compare.Refusal):
            compare.Caps(max_rps=1, max_duration_s=5, max_requests=41)

    def test_duration_cap_stops_the_run(self) -> None:
        clock = Clock()
        calls = []

        def transport(url: str) -> compare.Sample:
            calls.append(url)
            return compare.Sample(True, 1)

        report = compare.run_comparison(
            canary_url="http://127.0.0.1/canary",
            control_url="http://127.0.0.1/control",
            staging=True,
            target_class=None,
            caps=compare.Caps(max_rps=1, max_duration_s=1.5, max_requests=20),
            stops=compare.StopThresholds(1, 1000),
            samples_per_side=5,
            transport=transport,
            clock=clock.clock,
            sleep=clock.sleep,
        )
        self.assertLessEqual(report["issued"], 2)
        self.assertTrue(report["stopped"])
        self.assertEqual(report["stop_reason"], "max_duration")
        self.assertLessEqual(len(calls), 2)

    def test_localhost_comparison_reports_delta(self) -> None:
        def transport(url: str) -> compare.Sample:
            latency = 10 if url.endswith("/canary") else 40
            return compare.Sample(True, latency)

        report = compare.run_comparison(
            canary_url="http://127.0.0.1/canary",
            control_url="http://127.0.0.1/control",
            staging=True,
            target_class=None,
            caps=compare.Caps(5, 10, 4),
            stops=compare.StopThresholds(0.5, 1000),
            samples_per_side=2,
            transport=transport,
            clock=lambda: 0.0,
            sleep=lambda _seconds: None,
        )
        self.assertEqual(report["issued"], 4)
        self.assertFalse(report["stopped"])
        self.assertEqual(report["canary"]["error_rate"], 0)
        self.assertEqual(report["delta_error_rate"], 0)
        self.assertEqual(report["delta_p95_ms"], 10 - 40)


class TestCli(unittest.TestCase):
    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, os.path.join(_HERE, "compare.py"), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_check_only_refuses_production_and_missing_flag(self) -> None:
        denied = self._run(
            ["--check-only", "--staging", "--canary", "https://a-11-oy.com", "--control", "https://a11oy.net"]
        )
        self.assertEqual(denied.returncode, 2)
        self.assertIn("refusing", denied.stdout)
        missing = self._run(
            ["--check-only", "--canary", "http://127.0.0.1:9/", "--control", "http://127.0.0.1:9/"]
        )
        self.assertEqual(missing.returncode, 2)
        self.assertIn("no staging flag", missing.stdout)

    def test_check_only_allows_localhost(self) -> None:
        result = self._run(
            [
                "--check-only",
                "--staging",
                "--canary",
                "http://127.0.0.1:9/canary",
                "--control",
                "http://127.0.0.1:9/control",
            ]
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("allowed", result.stdout)

    def test_execute_refuses_inference_host_before_samples(self) -> None:
        result = self._run(
            [
                "--execute",
                "--staging",
                "--canary",
                "https://inference.a-11-oy.com/healthz",
                "--control",
                "http://127.0.0.1:9/",
                "--max-rps",
                "1",
                "--max-duration",
                "5",
                "--max-requests",
                "2",
                "--stop-error-rate",
                "0.5",
                "--stop-p95-ms",
                "500",
                "--samples",
                "1",
            ]
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("refusing", result.stdout)


class TestLocalTransport(unittest.TestCase):
    def test_capped_get_against_local_staging(self) -> None:
        hits = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                hits.append(self.path)
                body = b"{}"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args) -> None:
                return

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            base = f"http://127.0.0.1:{port}"
            report = compare.run_comparison(
                canary_url=base + "/canary",
                control_url=base + "/control",
                staging=True,
                target_class=None,
                caps=compare.Caps(max_rps=5, max_duration_s=5, max_requests=2),
                stops=compare.StopThresholds(0.5, 2000),
                samples_per_side=1,
                transport=lambda url: compare.urllib_transport(url, timeout=2),
            )
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(sorted(hits), ["/canary", "/control"])
        self.assertEqual(report["issued"], 2)
        self.assertEqual(report["canary"]["error_rate"], 0)
        self.assertEqual(report["control"]["error_rate"], 0)


if __name__ == "__main__":
    unittest.main()
