#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline transaction tests: no credentials, provider calls, or real publication."""
import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from huggingface_hub import HfApi
import huggingface_hub._commit_api as commit_api

import hf_inventory_evidence as evidence

GENERATION = "a" * 40
BEFORE = "b" * 40
AFTER = "c" * 40
REPORT = json.dumps({"schema": "szl.hf-official-estate-inventory/v2", "organization": "SZLHOLDINGS", "generation": GENERATION, "private": "sentinel"}, sort_keys=True).encode() + b"\n"


class FakeApi:
    endpoint = "https://huggingface.co"

    def __init__(self):
        self.calls = []
        self.files = {}
        self.commits = []
        self.before = SimpleNamespace(id=evidence.EVIDENCE_DATASET, private=True, sha=BEFORE)
        self.after = SimpleNamespace(id=evidence.EVIDENCE_DATASET, private=True, sha=AFTER)
        self.history_exists = False
        self.commit_oid = AFTER
        self.commit_error = None
        self.readback = None
        self.cache = None
        self.committed = True

    def dataset_info(self, repo, **kwargs):
        self.calls.append(("dataset_info", repo, kwargs))
        return self.after if self.commits else self.before

    def file_exists(self, repo, filename, **kwargs):
        self.calls.append(("file_exists", repo, filename, kwargs))
        return self.history_exists

    def create_commit(self, **kwargs):
        self.calls.append(("create_commit", kwargs))
        if self.commit_error:
            raise self.commit_error
        self.commits.append(kwargs)
        for operation in kwargs["operations"]:
            with operation.as_file() as stream:
                self.files[operation.path_in_repo] = stream.read()
            operation._is_committed = self.committed
        return SimpleNamespace(oid=self.commit_oid)

    def hf_hub_download(self, **kwargs):
        self.calls.append(("download", kwargs))
        self.cache = Path(kwargs["cache_dir"])
        path = self.cache / ("latest" if kwargs["filename"] == evidence.LATEST_PATH else "history")
        path.write_bytes(self.files[kwargs["filename"]] if self.readback is None else self.readback)
        return str(path)


class EvidenceTransactionTests(unittest.TestCase):
    def publish(self, api=None, rendered=REPORT, generation=GENERATION):
        api = api or FakeApi()
        with patch.object(evidence, "require_protected_source", return_value=GENERATION) as guard:
            result = evidence.publish_report(api, rendered, generation=generation)
        return api, guard, result

    def test_one_expected_parent_commit_contains_exact_latest_and_new_history(self):
        api, guard, result = self.publish()
        self.assertEqual(result, AFTER)
        self.assertEqual(guard.call_count, 2)
        guard.assert_called_with(GENERATION)
        self.assertEqual(len(api.commits), 1)
        commit = api.commits[0]
        self.assertEqual(commit["repo_id"], evidence.EVIDENCE_DATASET)
        self.assertEqual(commit["repo_type"], "dataset")
        self.assertEqual(commit["revision"], "main")
        self.assertEqual(commit["parent_commit"], BEFORE)
        self.assertIs(commit["create_pr"], False)
        history = f"estate/official-inventory/history/{GENERATION}/{hashlib.sha256(REPORT).hexdigest()}.json"
        self.assertEqual(api.files, {evidence.LATEST_PATH: REPORT, history: REPORT})
        existence = next(call for call in api.calls if call[0] == "file_exists")
        self.assertEqual(existence[3], {"repo_type": "dataset", "revision": BEFORE})
        downloads = [call[1] for call in api.calls if call[0] == "download"]
        self.assertEqual(len(downloads), 2)
        self.assertTrue(all(call["revision"] == AFTER and call["force_download"] is True for call in downloads))
        self.assertFalse(api.cache.exists())

    def test_public_unknown_or_wrong_dataset_cannot_write(self):
        for field, value in (("private", False), ("private", None), ("private", 1), ("id", "other/evidence")):
            api = FakeApi(); setattr(api.before, field, value)
            with self.subTest(field=field, value=value), self.assertRaisesRegex(RuntimeError, "PRIVATE_EVIDENCE"):
                self.publish(api)
            self.assertEqual(api.commits, [])

    def test_invalid_source_parent_or_endpoint_cannot_write(self):
        for value in (None, "", "x" * 40, "0" * 40, BEFORE + "\n"):
            api = FakeApi(); api.before.sha = value
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, "REVISION"):
                self.publish(api)
            self.assertEqual(api.commits, [])
        api = FakeApi(); api.endpoint = "https://outside.invalid"
        with self.assertRaisesRegex(RuntimeError, "ORIGIN"):
            self.publish(api)
        self.assertEqual(api.calls, [])
        for generation in ("manual", "0" * 40, GENERATION + "\n"):
            with self.subTest(generation=generation), self.assertRaisesRegex(RuntimeError, "SOURCE_REVISION"):
                self.publish(generation=generation)

    def test_source_must_still_be_protected_before_any_dataset_access(self):
        api = FakeApi()
        with patch.object(evidence, "require_protected_source", side_effect=RuntimeError("SOURCE_MOVED")):
            with self.assertRaisesRegex(RuntimeError, "SOURCE_MOVED"):
                evidence.publish_report(api, REPORT, generation=GENERATION)
        self.assertEqual(api.calls, [])

    def test_nonempty_bounded_byte_payload_required(self):
        for value in (b"", "report", bytearray(REPORT), b"x" * 17):
            api = FakeApi()
            with self.subTest(value=type(value)), patch.object(evidence, "MAX_REPORT_BYTES", 16), self.assertRaisesRegex(RuntimeError, "REPORT_BOUND"):
                self.publish(api, rendered=value)
            self.assertEqual(api.calls, [])

    def test_unreviewed_sdk_version_cannot_access_the_dataset(self):
        api = FakeApi()
        with patch.object(evidence, "HUB_VERSION", "unreviewed"), self.assertRaisesRegex(RuntimeError, "SDK_VERSION_UNREVIEWED"):
            self.publish(api)
        self.assertEqual(api.calls, [])

    def test_a_commit_oid_without_true_submission_flags_is_not_success(self):
        for value in (False, None, 1, "true"):
            api = FakeApi(); api.committed = value
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, "COMMIT_NOT_SUBMITTED"):
                self.publish(api)
            self.assertEqual(len(api.commits), 1)
            self.assertFalse(any(call[0] == "download" for call in api.calls))

    def test_pinned_sdk_requires_real_commit_post_before_readback(self):
        self.assertEqual(evidence.HUB_VERSION, "1.23.0")
        for duplicate in (False, True):
            api = HfApi(endpoint="https://huggingface.co", token=False)
            calls = {"posts": [], "downloads": [], "operations": []}

            def preupload(**kwargs):
                for operation in kwargs["additions"]:
                    operation._upload_mode = "regular"
                    operation._remote_oid = operation._local_oid if duplicate else None
                    calls["operations"].append(operation)

            def post(url, **kwargs):
                calls["posts"].append((url, kwargs))
                return httpx.Response(200, request=httpx.Request("POST", url), json={
                    "commitUrl": f"https://huggingface.co/datasets/{evidence.EVIDENCE_DATASET}/commit/{AFTER}",
                    "commitOid": AFTER,
                })

            def download(**kwargs):
                calls["downloads"].append(kwargs)
                path = Path(kwargs["cache_dir"]) / ("latest" if kwargs["filename"] == evidence.LATEST_PATH else "history")
                path.write_bytes(REPORT)
                return str(path)

            before = SimpleNamespace(id=evidence.EVIDENCE_DATASET, private=True, sha=BEFORE)
            after = SimpleNamespace(id=evidence.EVIDENCE_DATASET, private=True, sha=AFTER)
            with self.subTest(duplicate=duplicate), \
                    patch.object(evidence, "require_protected_source", return_value=GENERATION), \
                    patch.object(api, "dataset_info", side_effect=[before, after]), \
                    patch.object(api, "file_exists", return_value=False), \
                    patch.object(api, "preupload_lfs_files", side_effect=preupload), \
                    patch.object(api, "repo_info", return_value=SimpleNamespace(sha=AFTER)), \
                    patch.object(api, "hf_hub_download", side_effect=download), \
                    patch.object(commit_api, "get_session", return_value=SimpleNamespace(post=post)):
                if duplicate:
                    with self.assertRaisesRegex(RuntimeError, "COMMIT_NOT_SUBMITTED"):
                        evidence.publish_report(api, REPORT, generation=GENERATION)
                    self.assertEqual(calls["posts"], [])
                    self.assertEqual(calls["downloads"], [])
                    self.assertTrue(all(operation._is_committed is False for operation in calls["operations"]))
                else:
                    self.assertEqual(evidence.publish_report(api, REPORT, generation=GENERATION), AFTER)
                    self.assertEqual(len(calls["posts"]), 1)
                    url, request = calls["posts"][0]
                    self.assertEqual(url, f"https://huggingface.co/api/datasets/{evidence.EVIDENCE_DATASET}/commit/main")
                    payload = [json.loads(line) for line in request["content"].splitlines()]
                    self.assertEqual(payload[0]["value"]["parentCommit"], BEFORE)
                    self.assertEqual([row["key"] for row in payload], ["header", "file", "file"])
                    history = f"estate/official-inventory/history/{GENERATION}/{hashlib.sha256(REPORT).hexdigest()}.json"
                    self.assertEqual({row["value"]["path"]: base64.b64decode(row["value"]["content"]) for row in payload[1:]},
                                     {evidence.LATEST_PATH: REPORT, history: REPORT})
                    self.assertEqual(len(calls["downloads"]), 2)
                    self.assertTrue(all(call["revision"] == AFTER for call in calls["downloads"]))
                    self.assertTrue(all(operation._is_committed is True for operation in calls["operations"]))

    def test_payload_is_an_unambiguous_inventory_from_this_source(self):
        for value in (b"not-json", b"[]", b"{}", b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":1e999}', REPORT.replace(GENERATION.encode(), BEFORE.encode()), REPORT.replace(b"SZLHOLDINGS", b"outside")):
            api = FakeApi()
            with self.subTest(value=value[:20]), self.assertRaisesRegex(RuntimeError, "REPORT"):
                self.publish(api, rendered=value)
            self.assertEqual(api.calls, [])

    def test_history_is_never_overwritten_or_assumed_absent(self):
        for exists in (True, None, 0, "false"):
            api = FakeApi(); api.history_exists = exists
            with self.subTest(exists=exists), self.assertRaisesRegex(RuntimeError, "HISTORY"):
                self.publish(api)
            self.assertEqual(api.commits, [])

    def test_conflict_does_not_retry_or_write_a_second_head(self):
        api = FakeApi(); api.commit_error = RuntimeError("PARENT_CONFLICT")
        with self.assertRaisesRegex(RuntimeError, "PARENT_CONFLICT"):
            self.publish(api)
        self.assertEqual(sum(call[0] == "create_commit" for call in api.calls), 1)
        self.assertFalse(any(call[0] == "download" for call in api.calls))

    def test_malformed_or_nonadvancing_commit_receipt_cannot_succeed(self):
        for value in (None, "", "0" * 40, "d" * 39, BEFORE):
            api = FakeApi(); api.commit_oid = value
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, "COMMIT"):
                self.publish(api)
            self.assertEqual(len(api.commits), 1)

    def test_readback_mismatch_fails_and_removes_private_cache(self):
        api = FakeApi(); api.readback = b"different bytes"
        with self.assertRaisesRegex(RuntimeError, "READBACK_MISMATCH"):
            self.publish(api)
        self.assertEqual(len(api.commits), 1)
        self.assertFalse(api.cache.exists())

    def test_evidence_head_and_visibility_are_verified_after_write(self):
        for field, value in (("sha", "d" * 40), ("private", False), ("id", "other/evidence")):
            api = FakeApi(); setattr(api.after, field, value)
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                self.publish(api)
            self.assertEqual(len(api.commits), 1)
            self.assertFalse(api.cache.exists())

    def test_source_move_after_write_is_not_reported_as_success(self):
        api = FakeApi()
        with patch.object(evidence, "require_protected_source", side_effect=[GENERATION, RuntimeError("SOURCE_MOVED")]):
            with self.assertRaisesRegex(RuntimeError, "SOURCE_MOVED"):
                evidence.publish_report(api, REPORT, generation=GENERATION)
        self.assertEqual(len(api.commits), 1)
        self.assertFalse(api.cache.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
