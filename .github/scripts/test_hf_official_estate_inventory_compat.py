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

compat = importlib.import_module("hf_official_estate_inventory_compat")


class Response:
    def __init__(self, payload, link=""):
        self._payload = payload
        self.headers = {"Link": link} if link else {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, timeout=None):
        self.calls.append((url, timeout))
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

    def kernel_info(self, repo_id):
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
        self.assertTrue(all(timeout == 45 for _, timeout in verifier.http.calls))

    def test_kernel_discovery_requires_hfapi_readback(self) -> None:
        verifier = object.__new__(compat.CurrentHubEstateInventory)
        verifier.api = Api()
        verifier.inventory = {}
        verifier.actions = []
        verifier.http = Session(
            [Response([
                {"id": "SZLHOLDINGS/kernel-a", "sha": "stale"},
                {"id": "other/kernel", "sha": "b" * 40},
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

    def test_active_compatibility_source_uses_no_nonexistent_list_method(self) -> None:
        source = inspect.getsource(compat)
        self.assertNotIn("list_kernels(", source)
        self.assertIn("/api/kernels?author=", source)
        self.assertIn("kernel_info(", source)
        self.assertIn("list_repo_files(", source)

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
