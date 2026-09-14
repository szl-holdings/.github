#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the real stdlib request path with inert offline transport fixtures.

The complete publisher is loaded, not a copied smoke implementation. These
checks prove public-probe semantics and retained Hub authentication; they do
not attest any live deployment or qualify application/model functionality.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.error

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "hf_public_smoke_subject", HERE / "hf_deploy_from_dockerfile.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("the source-owned publisher must be present")
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)

REPO = "SZLHOLDINGS/lyte"
REVISION = "a" * 40
ORIGIN = "https://szlholdings-lyte.hf.space"
CONTROL_TOKEN = "fixture-control-token-not-a-credential"
ENTITY_PATHS = tuple("/api/lyte/v2/" + name for name in (
    "services", "journeys", "outcomes", "agents", "incidents", "decisions",
    "playback", "second-brain", "evidence", "receipts",
))


class Reply(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status


class PublicSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.requests: list[object] = []
        self.opener_handlers: list[tuple] = []
        self.responses: dict[str, tuple[int, bytes]] = {}
        self.addCleanup(mock.patch.stopall)
        mock.patch.dict(os.environ, {"HF_TOKEN": CONTROL_TOKEN}, clear=True).start()
        mock.patch.object(publisher.time, "sleep").start()
        mock.patch("socket.create_connection", side_effect=AssertionError("network forbidden")).start()
        mock.patch.object(publisher.urllib.request, "build_opener", side_effect=self.build_opener).start()

    def build_opener(self, *handlers):
        self.opener_handlers.append(handlers)
        return mock.Mock(open=self.open_request)

    def open_request(self, request, timeout):
        self.requests.append(request)
        self.assertEqual(timeout, 45)
        url = request.full_url
        if url.startswith(ORIGIN + "/"):
            # This reproduces the observed route class: public demo reads are
            # available, but a supplied bearer enters configured tenant auth.
            if request.get_header("Authorization") is not None:
                status, body = 503, b'{"detail":"authentication is not configured; request denied"}'
            else:
                status, body = self.responses.get(url, (200, b'{"truth_label":"SAMPLE"}'))
        elif url == f"https://huggingface.co/api/spaces/{REPO}":
            self.assertEqual(request.get_header("Authorization"), "Bearer " + CONTROL_TOKEN)
            status, body = self.responses.get(url, (200, json.dumps({
                "sha": REVISION, "runtime": {"stage": "RUNNING"},
            }).encode()))
        elif url == f"https://huggingface.co/spaces/{REPO}/resolve/{REVISION}/app.py":
            self.assertEqual(request.get_header("Authorization"), "Bearer " + CONTROL_TOKEN)
            status, body = self.responses.get(url, (200, b"source-bytes"))
        else:
            raise AssertionError("unexpected fixture endpoint")
        if status >= 300:
            raise urllib.error.HTTPError(url, status, "fixture response", {}, io.BytesIO(body))
        return Reply(body, status)

    def app_requests(self):
        return [request for request in self.requests if request.full_url.startswith(ORIGIN + "/")]

    def attest(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps({
                "hf_repo": REPO, "hf_commit_oid": REVISION,
                "files": {"app.py": {"sha256": publisher.sha256(b"source-bytes")}},
                "smoke_paths": list(ENTITY_PATHS),
            }), encoding="utf-8")
            return publisher.main([
                "--attest", "--manifest", str(manifest), "--hf-repo", REPO,
                "--wait-running", "0", "--smoke-retries", "1",
            ])

    def test_public_routes_never_read_hub_credentials(self):
        with mock.patch.object(publisher, "_auth_headers", side_effect=AssertionError("not application auth")):
            self.assertEqual(publisher.probe_smoke_routes(REPO, list(ENTITY_PATHS), retries=1), [])
        self.assertEqual(len(self.app_requests()), len(ENTITY_PATHS))

    def test_actual_requests_are_anonymous_and_redirects_disabled(self):
        self.assertEqual(publisher.probe_smoke_routes(REPO, list(ENTITY_PATHS), retries=1), [])
        for request in self.app_requests():
            self.assertIsNone(request.get_header("Authorization"))
            self.assertIsNone(request.get_header("Cookie"))
            self.assertNotIn(CONTROL_TOKEN, repr(request.header_items()))
            self.assertEqual(request.get_header("Cache-control"), "no-cache")
        self.assertTrue(self.opener_handlers)
        for handlers in self.opener_handlers:
            self.assertEqual(len(handlers), 1)
            self.assertIsInstance(handlers[0], publisher._NoRedirect)

    def test_public_routes_do_not_need_any_environment_token(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(publisher.probe_smoke_routes(REPO, ["/"], retries=1), [])

    def test_hub_state_and_immutable_file_keep_control_authentication(self):
        self.assertEqual(publisher.hf_space_state(REPO), ("RUNNING", REVISION))
        self.assertEqual(publisher.hf_resolve(REPO, "app.py", REVISION), (200, b"source-bytes"))
        self.assertEqual(len(self.requests), 2)

    def test_non_200_and_empty_responses_still_fail(self):
        for status, body in ((200, b""), (204, b"x"), (302, b"moved"), (401, b"denied"),
                             (403, b"denied"), (404, b"absent"), (429, b"busy"), (503, b"unavailable")):
            with self.subTest(status=status, empty=not body):
                self.responses[ORIGIN + "/"] = (status, body)
                failures = publisher.probe_smoke_routes(REPO, ["/"], retries=1)
                self.assertEqual(len(failures), 1)
                self.assertEqual(failures[0][0], "/")

    def test_retries_stay_anonymous_and_bounded(self):
        self.responses[ORIGIN + "/"] = (503, b"unavailable")
        self.assertEqual(len(publisher.probe_smoke_routes(REPO, ["/"], retries=3)), 1)
        self.assertEqual(len(self.app_requests()), 3)
        self.assertTrue(all(request.get_header("Authorization") is None for request in self.app_requests()))

    def test_unsafe_paths_fail_before_transport(self):
        for path in ("https://other.invalid/", "//other.invalid/", "/\\other", "/x\nheader", "/#fragment"):
            with self.subTest(path=path), self.assertRaises(publisher.DeployContractError):
                publisher.probe_smoke_routes(REPO, [path], retries=1)
        self.assertEqual(self.requests, [])

    def test_full_attestation_keeps_hub_auth_but_public_routes_are_anonymous(self):
        self.assertEqual(self.attest(), 0)
        self.assertEqual(len(self.requests), 2 + len(ENTITY_PATHS))
        self.assertEqual(len(self.app_requests()), len(ENTITY_PATHS))

    def test_immutable_byte_mismatch_still_blocks_all_public_probes(self):
        self.responses[f"https://huggingface.co/spaces/{REPO}/resolve/{REVISION}/app.py"] = (200, b"wrong-bytes")
        self.assertEqual(self.attest(), 1)
        self.assertEqual(self.app_requests(), [])

    def test_wrong_runtime_revision_still_blocks_file_and_route_probes(self):
        self.responses[f"https://huggingface.co/api/spaces/{REPO}"] = (
            200, json.dumps({"sha": "b" * 40, "runtime": {"stage": "RUNNING"}}).encode(),
        )
        self.assertEqual(self.attest(), 1)
        self.assertEqual(len(self.requests), 1)

    def test_one_failed_route_keeps_full_attestation_failed(self):
        self.responses[ORIGIN + ENTITY_PATHS[0]] = (503, b"unavailable")
        self.assertEqual(self.attest(), 1)
        self.assertEqual(len(self.app_requests()), len(ENTITY_PATHS))


if __name__ == "__main__":
    unittest.main()
