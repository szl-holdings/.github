#!/usr/bin/env python3
from __future__ import annotations

import importlib
import pathlib
import sys
import unittest
import unittest.mock

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

entrypoint = importlib.import_module("hf_release_finalization_entrypoint")


class Response:
    def __init__(self, status: int, payload: object, text: str = "") -> None:
        self.status_code = status
        self._payload = payload
        self.text = text or str(payload)

    def json(self) -> object:
        return self._payload


class ViewerRetryEntrypointTests(unittest.TestCase):
    def setUp(self) -> None:
        entrypoint._VIEWER_STATS.update(
            {"attempts": 0, "transient_retries": 0, "last_transient": None}
        )
        entrypoint._ACTIVE_FINALIZER = None

    def test_non_viewer_request_delegates_once(self) -> None:
        expected = Response(200, {"ok": True})
        with unittest.mock.patch.object(
            entrypoint, "_ORIGINAL_GET", return_value=expected
        ) as get:
            observed = entrypoint.get_with_viewer_retry("https://example.test/data")
        self.assertIs(observed, expected)
        get.assert_called_once_with("https://example.test/data")
        self.assertEqual(entrypoint._VIEWER_STATS["attempts"], 0)

    def test_transient_500_then_200_converges(self) -> None:
        responses = iter(
            [
                Response(
                    500,
                    {"error": "The server is busy and not ready; retry later."},
                ),
                Response(200, {"rows": [], "features": []}),
            ]
        )
        with unittest.mock.patch.object(
            entrypoint,
            "_ORIGINAL_GET",
            side_effect=lambda *_args, **_kwargs: next(responses),
        ), unittest.mock.patch.object(entrypoint.time, "sleep") as sleep:
            observed = entrypoint.get_with_viewer_retry(
                entrypoint.finalizer.VIEWER_URL,
                attempts=3,
                timeout=90,
            )
        self.assertEqual(observed.status_code, 200)
        self.assertEqual(entrypoint._VIEWER_STATS["attempts"], 2)
        self.assertEqual(entrypoint._VIEWER_STATS["transient_retries"], 1)
        sleep.assert_called_once_with(15)

    def test_transient_http_200_error_payload_then_success_converges(self) -> None:
        responses = iter(
            [
                Response(200, {"error": "processing; response is not ready"}),
                Response(200, {"rows": [1]}),
            ]
        )
        with unittest.mock.patch.object(
            entrypoint,
            "_ORIGINAL_GET",
            side_effect=lambda *_args, **_kwargs: next(responses),
        ), unittest.mock.patch.object(entrypoint.time, "sleep"):
            observed = entrypoint.get_with_viewer_retry(
                entrypoint.finalizer.VIEWER_URL,
                attempts=2,
            )
        self.assertEqual(observed.json(), {"rows": [1]})
        self.assertEqual(entrypoint._VIEWER_STATS["attempts"], 2)

    def test_non_transient_404_returns_without_sleep(self) -> None:
        response = Response(404, {"error": "missing"})
        with unittest.mock.patch.object(
            entrypoint, "_ORIGINAL_GET", return_value=response
        ) as get, unittest.mock.patch.object(entrypoint.time, "sleep") as sleep:
            observed = entrypoint.get_with_viewer_retry(
                entrypoint.finalizer.VIEWER_URL,
                attempts=3,
            )
        self.assertIs(observed, response)
        get.assert_called_once()
        sleep.assert_not_called()
        self.assertEqual(entrypoint._VIEWER_STATS["attempts"], 1)

    def test_network_failure_is_bounded_and_fails_closed(self) -> None:
        with unittest.mock.patch.object(
            entrypoint,
            "_ORIGINAL_GET",
            side_effect=entrypoint.requests.ConnectionError("offline"),
        ) as get, unittest.mock.patch.object(entrypoint.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "did not converge"):
                entrypoint.get_with_viewer_retry(
                    entrypoint.finalizer.VIEWER_URL,
                    attempts=3,
                )
        self.assertEqual(get.call_count, 3)
        self.assertEqual(
            sleep.call_args_list,
            [unittest.mock.call(15), unittest.mock.call(30)],
        )
        self.assertEqual(entrypoint._VIEWER_STATS["transient_retries"], 2)

    def test_report_contains_retry_evidence(self) -> None:
        instance = object.__new__(entrypoint.RetryingFinalizer)
        instance.actions = []
        instance.results = {}
        instance.publish = False
        instance.generation = "a" * 40
        entrypoint._VIEWER_STATS.update(
            {"attempts": 2, "transient_retries": 1, "last_transient": "HTTP 500"}
        )
        report = instance.report()
        self.assertEqual(
            report["dataset_viewer_retry"],
            {"attempts": 2, "transient_retries": 1, "last_transient": "HTTP 500"},
        )


if __name__ == "__main__":
    unittest.main()
