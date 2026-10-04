#!/usr/bin/env python3
from __future__ import annotations

import importlib
import inspect
import json
import pathlib
import sys
import unittest
from unittest.mock import patch

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

compat = importlib.import_module("hf_official_estate_inventory_compat")


class Response:
    def __init__(self, payload, link="", status=200, raw=None):
        self._payload = payload
        self.headers = {"Link": link} if link else {}
        self.status_code = status
        self.raw = json.dumps(payload).encode() if raw is None else raw
        self.closed = False

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=None):
        yield self.raw

    def close(self):
        self.closed = True


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class KernelInfo:
    def __init__(self, repo_id, sha):
        self.id = repo_id
        self.sha = sha
        self.downloads = 12
        self.likes = 3
        self.private = False


class Api:
    def __init__(self):
        self.info_calls = []
        self.file_calls = []

    def kernel_info(self, repo_id, timeout=None):
        self.info_calls.append(repo_id)
        return KernelInfo(repo_id, "a" * 40)

    def list_repo_files(self, repo_id, repo_type=None, revision=None):
        self.file_calls.append((repo_id, repo_type, revision))
        return ["README.md", "contract.json", "build/torch27-cxx11-cpu-x86_64-linux/__init__.py"]


class KernelInventoryCompatibilityTests(unittest.TestCase):
    def test_next_link_parser(self) -> None:
        header = '<https://huggingface.co/api/kernels?cursor=next>; rel="next"'
        self.assertEqual(
            compat._next_link(header),
            "https://huggingface.co/api/kernels?cursor=next",
        )
        self.assertEqual(compat._next_link(""), "")
        self.assertEqual(compat._next_link('<https://huggingface.co/api/kernels?cursor=next>; rel = "NEXT"'), "https://huggingface.co/api/kernels?cursor=next")

    def test_official_endpoint_pagination(self) -> None:
        verifier = object.__new__(compat.CurrentHubEstateInventory)
        verifier.http = Session(
            [
                Response(
                    [{"id": "SZLHOLDINGS/kernel-a", "sha": "1" * 40}],
                    '<https://huggingface.co/api/kernels?cursor=next>; rel="next"',
                ),
                Response([{"id": "SZLHOLDINGS/kernel-b", "sha": "2" * 40}]),
            ]
        )
        values = verifier._list_kernel_summaries()
        self.assertEqual([item["id"] for item in values], [
            "SZLHOLDINGS/kernel-a",
            "SZLHOLDINGS/kernel-b",
        ])
        self.assertEqual(len(verifier.http.calls), 2)
        self.assertTrue(all(kwargs == {"timeout": (10, 15), "allow_redirects": False, "stream": True} for _, kwargs in verifier.http.calls))

    def test_kernel_discovery_requires_hfapi_readback(self) -> None:
        verifier = object.__new__(compat.CurrentHubEstateInventory)
        verifier.api = Api()
        verifier.inventory = {}
        verifier.actions = []
        verifier.http = Session(
            [Response([
                {"id": "SZLHOLDINGS/kernel-a", "sha": "stale"},
            ])]
        )
        verifier.inventory_kernels()
        self.assertEqual(len(verifier.inventory["kernels"]), 1)
        item = verifier.inventory["kernels"][0]
        self.assertEqual(item["id"], "SZLHOLDINGS/kernel-a")
        self.assertEqual(item["sha"], "a" * 40)
        self.assertTrue(item["build_variants_present"])
        self.assertEqual(verifier.api.info_calls, ["SZLHOLDINGS/kernel-a"])
        self.assertEqual(
            verifier.api.file_calls,
            [("SZLHOLDINGS/kernel-a", "kernel", "a" * 40)],
        )

    def verifier(self, responses):
        verifier = object.__new__(compat.CurrentHubEstateInventory)
        verifier.http = Session(responses)
        verifier.api = Api()
        verifier.inventory = {}
        verifier.actions = []
        return verifier

    def test_foreign_pagination_link_never_sends_bearer_header(self):
        verifier = self.verifier([Response([], '<https://attacker.example/api/kernels?cursor=x>; rel="next"')])
        verifier.http.headers["Authorization"] = "Bearer test-never-leak"
        with self.assertRaisesRegex(ValueError, "KERNEL_URL_REJECTED"):
            verifier._list_kernel_summaries()
        self.assertEqual(len(verifier.http.calls), 1)
        self.assertTrue(all(url.startswith("https://huggingface.co/api/kernels?") for url, _ in verifier.http.calls))

    def test_redirect_is_rejected_and_response_closed(self):
        response = Response([], status=302)
        verifier = self.verifier([response])
        with self.assertRaisesRegex(RuntimeError, "KERNEL_HTTP_STATUS_REJECTED"):
            verifier._list_kernel_summaries()
        self.assertIs(verifier.http.calls[0][1]["allow_redirects"], False)
        self.assertTrue(response.closed)

    def test_unsafe_urls_are_rejected_before_request(self):
        urls = ["http://huggingface.co/api/kernels", "https://huggingface.co.attacker/api/kernels",
                "https://user@huggingface.co/api/kernels", "https://huggingface.co:443/api/kernels",
                "https://huggingface.co/api/models", "https://huggingface.co/api/kernels#x",
                "https://huggingface.co/api/kernels?author=other", "https://huggingface.co/api/kernels?limit=1000",
                "https://huggingface.co/api/kernels?cursor=a&cursor=b", "https://huggingface.co/api/kernels\n"]
        for url in urls:
            with self.subTest(url=url), patch.object(compat, "KERNEL_LIST_URL", url):
                verifier = self.verifier([])
                with self.assertRaises(ValueError): verifier._list_kernel_summaries()
                self.assertEqual(verifier.http.calls, [])

    def test_json_boundaries_and_record_shape_fail_closed(self):
        payloads = [b'[{"id":"SZLHOLDINGS/a","id":"SZLHOLDINGS/b"}]',
                    b'[{"id":"SZLHOLDINGS/a","likes":NaN}]', b'[{"id":"SZLHOLDINGS/a","likes":1e999}]', b'[null]', b'[{"id":"other/kernel"}]',
                    b'[{"id":"SZLHOLDINGS/a"},{"id":"SZLHOLDINGS/a"}]', b'{"error":"not-a-list"}']
        for raw in payloads:
            with self.subTest(raw=raw):
                verifier = self.verifier([Response([], raw=raw)])
                with self.assertRaises((ValueError, TypeError)): verifier.inventory_kernels()
                self.assertNotIn("kernels", verifier.inventory)

    def test_byte_page_item_and_cycle_bounds(self):
        verifier = self.verifier([Response([], raw=b' ' * 65)])
        with patch.object(compat, "MAX_KERNEL_PAGE_BYTES", 64), self.assertRaisesRegex(RuntimeError, "BYTE_BOUND"):
            verifier._list_kernel_summaries()
        verifier = self.verifier([Response([{ "id": "SZLHOLDINGS/a" }, { "id": "SZLHOLDINGS/b" }])])
        with patch.object(compat, "MAX_KERNEL_ITEMS", 1), self.assertRaisesRegex(RuntimeError, "ITEM_BOUND"):
            verifier._list_kernel_summaries()
        verifier = self.verifier([Response([], '<https://huggingface.co/api/kernels?cursor=x>; rel="next"')])
        with patch.object(compat, "MAX_KERNEL_PAGES", 1), self.assertRaisesRegex(RuntimeError, "PAGE_BOUND"):
            verifier._list_kernel_summaries()
        verifier = self.verifier([Response([], f'<{compat.KERNEL_LIST_URL}>; rel="next"')])
        with self.assertRaisesRegex(RuntimeError, "PAGINATION_CYCLE"): verifier._list_kernel_summaries()
        self.assertEqual(len(verifier.http.calls), 1)

    def test_duplicate_and_malformed_next_links_are_not_end_of_census(self):
        url = "https://huggingface.co/api/kernels?cursor=x"
        for header in (f'<{url}>; rel="next", <{url}>; rel="next"', 'bad; rel="next"'):
            with self.subTest(header=header), self.assertRaises(ValueError): compat._next_link(header)

    def test_readback_identity_and_sha_are_not_taken_from_listing(self):
        verifier = self.verifier([Response([{"id": "SZLHOLDINGS/a", "sha": "a" * 40}])])
        verifier.api.kernel_info = lambda *args, **kwargs: KernelInfo("SZLHOLDINGS/other", "b" * 40)
        with self.assertRaisesRegex(RuntimeError, "ID_MISMATCH"): verifier.inventory_kernels()
        for revision in (None, "0" * 40):
            verifier = self.verifier([Response([{"id": "SZLHOLDINGS/a", "sha": "a" * 40}])])
            verifier.api.kernel_info = lambda *args, **kwargs: KernelInfo("SZLHOLDINGS/a", revision)
            with self.subTest(revision=revision), self.assertRaisesRegex(RuntimeError, "IMMUTABLE_REVISION_MISSING"):
                verifier.inventory_kernels()

    def test_kernel_visibility_cannot_fall_back_to_stale_public_listing(self):
        for value in (None, "false", 0):
            verifier = self.verifier([Response([{"id": "SZLHOLDINGS/a", "private": False}])])
            info = KernelInfo("SZLHOLDINGS/a", "a" * 40); info.private = value
            verifier.api.kernel_info = lambda *args, **kwargs: info
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, "VISIBILITY_READBACK_MISSING"):
                verifier.inventory_kernels()
            self.assertNotIn("kernels", verifier.inventory)

    def test_public_projection_excludes_private_ids_notes_actions_errors_and_digests(self):
        secret = "PRIVATE-SENTINEL"
        raw = {"assets": {"kernels": [{"id":"SZLHOLDINGS/public", "private":False},
                                      {"id":secret,"private":True}, {"id":secret,"private":None}]},
               "collections":[{"title":secret}],"buckets":[{"id":secret}],
               "actions":[{"detail":secret}],"fatal":secret,"sha256":secret,"summary":{"error":1}}
        projected = compat.public_report(raw)
        self.assertNotIn(secret, json.dumps(projected))
        self.assertEqual(projected["counts"]["kernels"], 1)
        self.assertIsNone(projected["counts"]["models"])
        self.assertEqual(projected["coverage"]["models"], "UNKNOWN")
        projected = compat.public_report({"assets":{"models":[]}, "counts":{"models":None}})
        self.assertIsNone(projected["counts"]["models"])
        self.assertEqual(projected["coverage"]["models"], "UNKNOWN")

    def test_compat_uses_the_same_private_expected_parent_publisher(self):
        self.assertIs(compat.CurrentHubEstateInventory.persist, compat.base.OfficialEstateInventory.persist)
        import hf_inventory_evidence as evidence
        self.assertIs(compat.base.publish_report, evidence.publish_report)

    def test_active_compatibility_source_uses_no_nonexistent_list_method(self) -> None:
        executable = "\n".join(
            (
                inspect.getsource(compat.CurrentHubEstateInventory.inventory_repositories),
                inspect.getsource(compat.CurrentHubEstateInventory.inventory_kernels),
            )
        )
        source = inspect.getsource(compat)
        self.assertNotIn("self.api.list_kernels(", executable)
        self.assertNotIn('base._invoke_supported(self.api, "list_kernels"', executable)
        self.assertIn("/api/kernels?author=", source)
        self.assertIn("kernel_info(", executable)
        self.assertIn("list_repo_files(", executable)

    def test_source_is_read_only_except_inherited_evidence_report(self) -> None:
        source = (HERE / "hf_official_estate_inventory_compat.py").read_text(encoding="utf-8")
        for forbidden in (
            "duplicate_repo(",
            "create_repo(",
            "delete_repo(",
            "update_repo_settings(",
            "restart_space(",
            "CommitOperationCopy",
        ):
            self.assertNotIn(forbidden, source)

    def test_report_names_mixed_official_api_contract_honestly(self) -> None:
        source = inspect.getsource(compat.CurrentHubEstateInventory.report)
        self.assertIn("Official Hub REST /api/kernels", source)
        self.assertIn("HfApi.kernel_info", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
