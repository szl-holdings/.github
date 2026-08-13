#!/usr/bin/env python3
"""Tests for exact live pull-request identity admission."""

from __future__ import annotations

import contextlib
import http.client
import io
import json
import sys
import unittest
import unittest.mock
import urllib.error
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import hf_live_pr_pair as live_pair  # noqa: E402


BASE = "a" * 40
HEAD = "b" * 40


class _Response:
    status = 200

    def __init__(
        self,
        payload: bytes,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        self.payload = payload
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self) -> int:
        return self.status

    def read(self, bound: int) -> bytes:
        return self.payload[:bound]


class _Opener:
    def __init__(
        self,
        payload: bytes,
        *,
        error: Exception | None = None,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        self.payload = payload
        self.error = error
        self.content_type = content_type
        self.request = None

    def open(self, request, timeout: int):
        self.request = request
        if self.error:
            raise self.error
        return _Response(self.payload, content_type=self.content_type)


def _environment() -> dict[str, str]:
    return {
        "GITHUB_API_URL": "https://api.github.com",
        "GITHUB_REPOSITORY": "szl-holdings/example",
        "GITHUB_TOKEN": "secret-token-never-print",
        "PR_NUMBER": "42",
        "EXPECTED_BASE_REPO": "szl-holdings/example",
        "EXPECTED_HEAD_REPO": "szl-holdings/example",
        "EXPECTED_BASE_REF": "main",
        "EXPECTED_BASE_SHA": BASE,
        "EXPECTED_HEAD_SHA": HEAD,
    }


def _payload(**overrides) -> bytes:
    payload = {
        "number": 42,
        "state": "open",
        "merged": False,
        "base": {
            "ref": "main",
            "sha": BASE,
            "repo": {"full_name": "szl-holdings/example"},
        },
        "head": {
            "sha": HEAD,
            "repo": {"full_name": "szl-holdings/example"},
        },
    }
    for key, value in overrides.items():
        if "." not in key:
            payload[key] = value
            continue
        parent, child = key.split(".", 1)
        payload[parent][child] = value
    return json.dumps(payload).encode()


class TestLivePRPair(unittest.TestCase):
    def test_exact_live_pair_passes_without_exposing_token_in_url(self) -> None:
        opener = _Opener(_payload())

        actual = live_pair.validate_live_pr_pair(_environment(), opener=opener)

        self.assertEqual(actual["base_sha"], BASE)
        self.assertEqual(actual["head_sha"], HEAD)
        self.assertNotIn("secret-token-never-print", opener.request.full_url)
        self.assertEqual(opener.request.get_method(), "GET")

    def test_every_live_identity_mismatch_fails_closed(self) -> None:
        cases = {
            "number": {"number": 43},
            "closed": {"state": "closed"},
            "merged": {"merged": True},
            "base repo": {"base.repo": {"full_name": "other/example"}},
            "head repo": {"head.repo": {"full_name": "other/example"}},
            "base ref": {"base.ref": "release/stale"},
            "base sha": {"base.sha": "c" * 40},
            "head sha": {"head.sha": "d" * 40},
        }
        for name, overrides in cases.items():
            with (
                self.subTest(case=name),
                self.assertRaisesRegex(live_pair.LivePRPairError, "mismatch"),
            ):
                live_pair.validate_live_pr_pair(
                    _environment(), opener=_Opener(_payload(**overrides))
                )

    def test_malformed_duplicate_and_oversized_responses_fail_closed(self) -> None:
        payloads = (
            b"not json",
            b'{"number":42,"number":42}',
            b"{" + b" " * live_pair.MAX_RESPONSE_BYTES + b"}",
            _payload()
            .decode()
            .replace('"merged": false', '"merged": false, "x": NaN')
            .encode(),
            _payload()
            .decode()
            .replace('"merged": false', '"merged": false, "x": Infinity')
            .encode(),
            _payload()
            .decode()
            .replace('"merged": false', '"merged": false, "x": -Infinity')
            .encode(),
            _payload().decode().encode("utf-16"),
        )
        for payload in payloads:
            with (
                self.subTest(size=len(payload)),
                self.assertRaises(live_pair.LivePRPairError),
            ):
                live_pair.validate_live_pr_pair(_environment(), opener=_Opener(payload))

    def test_false_positive_json_content_types_fail_closed(self) -> None:
        for content_type in (
            "application/jsonp",
            "text/application/json",
            "fooapplication/jsonbar",
            "text/plain",
        ):
            with (
                self.subTest(content_type=content_type),
                self.assertRaisesRegex(
                    live_pair.LivePRPairError, "non-JSON content type"
                ),
            ):
                live_pair.validate_live_pr_pair(
                    _environment(),
                    opener=_Opener(_payload(), content_type=content_type),
                )

    def test_wrong_field_types_fail_closed(self) -> None:
        for overrides in ({"number": True}, {"merged": 0}, {"state": ["open"]}):
            with (
                self.subTest(overrides=overrides),
                self.assertRaisesRegex(live_pair.LivePRPairError, "wrong type"),
            ):
                live_pair.validate_live_pr_pair(
                    _environment(), opener=_Opener(_payload(**overrides))
                )

    def test_http_failure_redirect_and_bad_api_origin_fail_closed(self) -> None:
        with self.assertRaisesRegex(live_pair.LivePRPairError, "request failed"):
            live_pair.validate_live_pr_pair(
                _environment(),
                opener=_Opener(
                    b"",
                    error=urllib.error.URLError("offline"),
                ),
            )
        with self.assertRaisesRegex(live_pair.LivePRPairError, "redirect"):
            live_pair._NoRedirect().redirect_request(None, None, 302, "", {}, "")
        environment = _environment()
        environment["GITHUB_API_URL"] = "http://api.github.com"
        with self.assertRaisesRegex(live_pair.LivePRPairError, "exactly https"):
            live_pair.validate_live_pr_pair(environment, opener=_Opener(_payload()))

    def test_transport_errors_never_reflect_bearer_token(self) -> None:
        environment = _environment()
        token = environment["GITHUB_TOKEN"]
        errors = (
            urllib.error.HTTPError("https://api.github.com", 403, token, {}, None),
            urllib.error.URLError(token),
            http.client.BadStatusLine(token),
            OSError(token),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(live_pair.LivePRPairError) as raised:
                    live_pair.validate_live_pr_pair(
                        environment,
                        opener=_Opener(b"", error=error),
                    )
                self.assertNotIn(token, str(raised.exception))

    def test_response_diagnostics_and_main_never_reflect_bearer_token(self) -> None:
        environment = _environment()
        token = environment["GITHUB_TOKEN"]
        reflected_cases = (
            _Opener(_payload(), content_type=token),
            _Opener(f'{{"{token}":1,"{token}":2}}'.encode()),
            _Opener(_payload(state=token)),
        )
        for opener in reflected_cases:
            with self.subTest(opener=opener):
                with self.assertRaises(live_pair.LivePRPairError) as raised:
                    live_pair.validate_live_pr_pair(environment, opener=opener)
                self.assertNotIn(token, str(raised.exception))

        stderr = io.StringIO()
        with (
            unittest.mock.patch.object(
                live_pair,
                "validate_live_pr_pair",
                side_effect=live_pair.LivePRPairError(token),
            ),
            unittest.mock.patch.dict(live_pair.os.environ, environment, clear=True),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(live_pair.main(), 1)
        self.assertNotIn(token, stderr.getvalue())

    def test_repository_dot_segments_fail_before_network(self) -> None:
        for repository in ("../example", "owner/..", "./example", "owner/."):
            environment = _environment()
            environment["GITHUB_REPOSITORY"] = repository
            environment["EXPECTED_BASE_REPO"] = repository
            environment["EXPECTED_HEAD_REPO"] = repository
            opener = _Opener(_payload())
            with (
                self.subTest(repository=repository),
                self.assertRaisesRegex(
                    live_pair.LivePRPairError, "canonical owner/repository"
                ),
            ):
                live_pair.validate_live_pr_pair(environment, opener=opener)
            self.assertIsNone(opener.request)

    def test_invalid_environment_fails_before_network(self) -> None:
        cases = {
            "PR_NUMBER": "0",
            "EXPECTED_BASE_SHA": BASE.upper(),
            "EXPECTED_HEAD_SHA": "short",
            "EXPECTED_HEAD_REPO": "other/example",
        }
        for key, value in cases.items():
            environment = _environment()
            environment[key] = value
            opener = _Opener(_payload())
            with self.subTest(field=key), self.assertRaises(live_pair.LivePRPairError):
                live_pair.validate_live_pr_pair(environment, opener=opener)
            self.assertIsNone(opener.request)


if __name__ == "__main__":
    unittest.main(verbosity=2)
