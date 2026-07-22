#!/usr/bin/env python3
from __future__ import annotations

import importlib
import inspect
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

readiness = importlib.import_module("hf_release_readiness_verify")


class FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str = "", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, *_args, **_kwargs):
        self.calls += 1
        if not self.responses:
            raise AssertionError("unexpected viewer request")
        return self.responses.pop(0)


class ReleaseReadinessContractTests(unittest.TestCase):
    def test_exact_targets(self) -> None:
        self.assertEqual(readiness.DATASET_ID, "SZLHOLDINGS/szl-lake")
        self.assertEqual(
            readiness.KERNEL_IDS,
            (
                "SZLHOLDINGS/governed-inference-meter",
                "SZLHOLDINGS/szl-governed-norm",
            ),
        )

    def test_known_busy_response_retries_then_passes(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    500,
                    {"error": "The server is busier than usual and the response is not ready yet."},
                    '{"error":"The server is busier than usual and the response is not ready yet."}',
                ),
                FakeResponse(200, {"rows": [], "features": []}, "{}"),
            ]
        )
        sleeps = []
        response, payload, attempts = readiness.wait_for_viewer(
            session,
            attempts=3,
            retry_seconds=0.25,
            sleep=sleeps.append,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["rows"], [])
        self.assertEqual(attempts, 2)
        self.assertEqual(session.calls, 2)
        self.assertEqual(sleeps, [0.25])

    def test_unknown_http_500_fails_without_retry(self) -> None:
        session = FakeSession([FakeResponse(500, {"error": "schema exploded"}, "schema exploded")])
        with self.assertRaisesRegex(RuntimeError, "terminal HTTP 500"):
            readiness.wait_for_viewer(
                session,
                attempts=5,
                retry_seconds=0,
                sleep=lambda _delay: None,
            )
        self.assertEqual(session.calls, 1)

    def test_retry_budget_is_bounded(self) -> None:
        session = FakeSession(
            [FakeResponse(503, {"error": "temporarily unavailable"}, "temporarily unavailable")]
            * 3
        )
        with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
            readiness.wait_for_viewer(
                session,
                attempts=3,
                retry_seconds=0,
                sleep=lambda _delay: None,
            )
        self.assertEqual(session.calls, 3)

    def test_verifier_is_evidence_only(self) -> None:
        source = (HERE / "hf_release_readiness_verify.py").read_text(encoding="utf-8")
        self.assertNotIn("upload_folder(", source)
        self.assertNotIn("delete_repo(", source)
        self.assertNotIn("update_repo_settings(", source)
        self.assertNotIn('repo_type="model"', source)
        self.assertNotIn("set_space_hardware", source)
        self.assertIn("release-readiness/latest.json", source)

    def test_kernel_selfcheck_is_immutable_and_explicit(self) -> None:
        source = inspect.getsource(readiness.ReadinessVerifier._run_selfcheck)
        self.assertIn("revision=revision", source)
        self.assertIn("trust_remote_code=True", source)
        self.assertIn("selfcheck", source)


if __name__ == "__main__":
    unittest.main()
