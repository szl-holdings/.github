#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Contract-checker tests against the local fixture and against refusals."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "contract"))
sys.path.insert(0, os.path.join(_ROOT, "canary"))

import check_api  # noqa: E402
import compare  # noqa: E402


class TestValidator(unittest.TestCase):
    def test_schema_mismatch_is_not_a_pass(self) -> None:
        schema = {
            "type": "object",
            "required": ["status"],
            "properties": {"status": {"type": "string"}},
        }
        with self.assertRaises(check_api.SchemaMismatch):
            check_api.validate(schema, {"status": 1})

    def test_production_host_does_not_call_the_opener(self) -> None:
        def opener(*_args):
            raise AssertionError("opener called")

        with self.assertRaises(compare.Refusal):
            check_api.run_checks(
                "https://a-11-oy.com",
                staging=True,
                target_class="staging",
                opener=opener,
            )

    def test_missing_staging_flag_refuses_localhost(self) -> None:
        def opener(*_args):
            raise AssertionError("opener called")

        with self.assertRaises(compare.Refusal) as caught:
            check_api.run_checks(
                "http://127.0.0.1:9",
                staging=False,
                target_class=None,
                opener=opener,
            )
        self.assertIn("no staging flag", caught.exception.reason)


class TestFixture(unittest.TestCase):
    def test_fixture_statuses_and_unknown_turn_schema(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        server = subprocess.Popen(
            [sys.executable, os.path.join(_ROOT, "fixtures", "a11oy_fixture.py"), "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            deadline = time.time() + 5
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen(base + "/api/livez", timeout=0.5) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.05)
            else:
                self.fail("fixture did not start")
            report = check_api.run_checks(
                base, staging=True, target_class=None, opener=check_api.urllib_opener
            )
        finally:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()
        self.assertFalse(report["failed"], json.dumps(report, indent=2))
        self.assertTrue(report["fixture"])
        self.assertEqual(report["openapi"], "PRESENT")
        by_id = {row["id"]: row for row in report["results"]}
        self.assertEqual(by_id["build-info"]["status_result"], "PASS")
        self.assertEqual(by_id["build-info"]["schema_result"], "PASS")
        self.assertEqual(by_id["atelier-turn-unauthenticated"]["status_result"], "PASS")
        self.assertEqual(by_id["atelier-turn-unauthenticated"]["schema_result"], "UNKNOWN")
        self.assertEqual(by_id["atelier-turn-forbidden"]["status_result"], "PASS")
        self.assertEqual(by_id["atelier-turn-payment"]["status_result"], "PASS")
        self.assertEqual(by_id["atelier-turn-ok"]["status_result"], "PASS")
        self.assertEqual(by_id["atelier-turn-ok"]["schema_result"], "UNKNOWN")
        self.assertEqual(by_id["atelier-health"]["schema_result"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
