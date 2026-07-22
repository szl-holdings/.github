#!/usr/bin/env python3
"""Contract tests for discover_replit_receipt.py."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from email.message import Message

import discover_replit_receipt as target


class FakeResponse:
    def __init__(
        self,
        *,
        status: int,
        url: str,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.code = status
        self._url = url
        self._body = body
        self._headers = Message()
        for key, value in (headers or {}).items():
            self._headers[key] = value

    @property
    def headers(self) -> Message:
        return self._headers

    def read(self, amount: int = -1) -> bytes:
        return self._body if amount < 0 else self._body[:amount]

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeOpener:
    def __init__(self, responses: dict[tuple[str, str], FakeResponse]) -> None:
        self.responses = responses

    def open(self, request: object, timeout: float) -> FakeResponse:
        method = request.get_method()
        url = request.full_url
        response = self.responses.get((method, url))
        if response is None:
            raise AssertionError(f"unexpected request: {method} {url}")
        return response


def valid_receipt(origin: str) -> dict[str, object]:
    return {
        "schema": target.RECEIPT_SCHEMA,
        "repl_id": target.REPL_ID,
        "source_revision": "a" * 64,
        "deployment_revision": "deployment-20260722-0001",
        "production_url": origin,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tests": {
            "status": "passed",
            "commands": ["npm run lint", "npm test", "npm run build"],
        },
        "mobile": {
            "status": "passed",
            "viewport_widths": [320, 390, 768, 1440],
        },
        "readiness": {
            "ok": True,
            "status": "ready",
            "checks": {
                "http": True,
                "frontend": True,
                "backend": True,
                "receipt": True,
            },
        },
    }


def opener_for(origin: str, receipt: dict[str, object]) -> FakeOpener:
    url = origin + target.RECEIPT_PATH
    return FakeOpener(
        {
            ("GET", url): FakeResponse(
                status=200,
                url=url,
                body=json.dumps(receipt).encode(),
                headers={"Content-Type": "application/json; charset=utf-8"},
            ),
            ("HEAD", url): FakeResponse(
                status=200,
                url=url,
                headers={
                    "X-SZL-Source-Revision": str(receipt["source_revision"]),
                    "X-SZL-Deployment-Revision": str(receipt["deployment_revision"]),
                },
            ),
        }
    )


class ReceiptContractTests(unittest.TestCase):
    def test_valid_receipt_passes_get_head_and_evidence(self) -> None:
        origin = "https://example.replit.app"
        receipt = valid_receipt(origin)
        attempt, observed = target.probe_origin(
            origin,
            opener=opener_for(origin, receipt),
            timeout=1,
        )
        self.assertTrue(attempt.ok)
        self.assertEqual(observed, receipt)
        self.assertEqual(attempt.get_status, 200)
        self.assertEqual(attempt.head_status, 200)

    def test_missing_mobile_evidence_fails_closed(self) -> None:
        origin = "https://example.replit.app"
        receipt = valid_receipt(origin)
        receipt.pop("mobile")
        attempt, observed = target.probe_origin(
            origin,
            opener=opener_for(origin, receipt),
            timeout=1,
        )
        self.assertFalse(attempt.ok)
        self.assertIsNone(observed)
        self.assertIn("mobile", attempt.missing)

    def test_head_revision_mismatch_fails_closed(self) -> None:
        origin = "https://example.replit.app"
        receipt = valid_receipt(origin)
        opener = opener_for(origin, receipt)
        url = origin + target.RECEIPT_PATH
        opener.responses[("HEAD", url)] = FakeResponse(
            status=200,
            url=url,
            headers={
                "X-SZL-Source-Revision": "b" * 64,
                "X-SZL-Deployment-Revision": str(receipt["deployment_revision"]),
            },
        )
        attempt, observed = target.probe_origin(origin, opener=opener, timeout=1)
        self.assertFalse(attempt.ok)
        self.assertIsNone(observed)
        self.assertIn("HEAD X-SZL-Source-Revision", attempt.missing)

    def test_candidate_origins_deduplicate_and_reject_http(self) -> None:
        origins = target.candidate_origins(
            [
                "https://Example.Replit.App/",
                "https://example.replit.app",
                "http://unsafe.example",
            ],
            environment={"REPLIT_PRODUCTION_URL": ""},
        )
        self.assertEqual(origins[0], "https://example.replit.app")
        self.assertEqual(origins.count("https://example.replit.app"), 1)
        self.assertNotIn("http://unsafe.example", origins)

    def test_discover_returns_first_complete_origin(self) -> None:
        broken = "https://broken.replit.app"
        working = "https://working.replit.app"
        broken_receipt = valid_receipt(broken)
        broken_receipt["tests"] = {"status": "failed", "commands": ["npm test"]}
        working_receipt = valid_receipt(working)
        openers = iter(
            [
                opener_for(broken, broken_receipt),
                opener_for(working, working_receipt),
            ]
        )
        report = target.discover(
            [broken, working],
            attempts=1,
            interval_seconds=0,
            timeout=1,
            opener_factory=lambda: next(openers),
            sleep=lambda _: None,
        )
        self.assertTrue(report["ok"])
        self.assertEqual(report["status"], "OPERATIONAL")
        self.assertEqual(report["production_url"], working)
        self.assertEqual(len(report["attempts"]), 2)


if __name__ == "__main__":
    unittest.main()
