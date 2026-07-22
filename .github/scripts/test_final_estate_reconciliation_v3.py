#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

reconcile = importlib.import_module("final_estate_reconciliation_v3")


class FinalEstateReconciliationTests(unittest.TestCase):
    def test_json_fence_parser_uses_valid_objects(self) -> None:
        body = """text
```json
{"schema":"one","ok":false}
```
more
```json
{"schema":"two","ok":true}
```
"""
        values = reconcile._json_fences(body)
        self.assertEqual([value["schema"] for value in values], ["one", "two"])
        self.assertTrue(reconcile._latest_report({"body": body})["ok"])

    def test_official_inventory_requires_singleton_and_all_counts(self) -> None:
        report = {
            "publish": True,
            "summary": {"error": 0},
            "counts": {
                "models": 15,
                "datasets": 32,
                "spaces": 26,
                "kernels": 10,
                "collections": 12,
                "collection_references": 160,
                "buckets": 6,
            },
            "canonical_a11oy": {
                "private": False,
                "sdk": "docker",
                "stage": "RUNNING",
                "sha": "a" * 40,
            },
            "clone_absence": {f"clone-{index}": True for index in range(1, 5)},
        }
        ok, _detail = reconcile.validate_official_inventory(report)
        self.assertTrue(ok)
        report["clone_absence"]["clone-1"] = False
        self.assertFalse(reconcile.validate_official_inventory(report)[0])

    def test_readiness_requires_viewer_and_both_exact_kernels(self) -> None:
        report = {
            "summary": {"error": 0},
            "results": {
                "dataset": {"viewer_http_status": 200, "revision": "b" * 40},
                "kernels": {
                    repo_id: {"revision": "c" * 40, "selfcheck": {"ok": True}}
                    for repo_id in reconcile.KERNEL_IDS
                },
            },
        }
        self.assertTrue(reconcile.validate_readiness(report)[0])
        report["results"]["dataset"]["viewer_http_status"] = 503
        self.assertFalse(reconcile.validate_readiness(report)[0])

    def test_relock_requires_exact_public_running_pair(self) -> None:
        report = {
            "status": "PASS",
            "public": True,
            "sdk": "docker",
            "runtime_stage": "RUNNING",
            "github_source_sha": "d" * 40,
            "hf_repository_sha": "e" * 40,
            "hf_runtime_sha": "e" * 40,
        }
        self.assertTrue(reconcile.validate_a11oy_relock(report)[0])
        report["hf_runtime_sha"] = "f" * 40
        self.assertFalse(reconcile.validate_a11oy_relock(report)[0])

    def test_replit_gate_requires_receipt_not_just_live_url(self) -> None:
        report = {
            "ok": True,
            "receipt": {
                "source_revision": "a" * 40,
                "deployment_revision": "deploy-123",
                "production_url": "https://example.replit.app",
                "tests_passed": True,
                "mobile_passed": True,
                "keyboard_passed": True,
                "readiness": {"GET": 200, "HEAD": 200},
            },
        }
        self.assertTrue(reconcile.validate_replit(report)[0])
        report["receipt"].pop("keyboard_passed")
        self.assertFalse(reconcile.validate_replit(report)[0])

    def test_issue_body_is_machine_readable(self) -> None:
        report = {
            "schema": "szl.final-estate-reconciliation/v3",
            "generated_at": "2026-07-22T00:00:00+00:00",
            "status": "NOT_VERIFIED",
            "operational_verified": False,
            "gates": [
                {
                    "name": "example",
                    "ok": False,
                    "detail": "not ready",
                    "evidence": {},
                }
            ],
            "summary": {"ok": 0, "error": 1, "total": 1},
            "boundaries": [],
        }
        body = reconcile.issue_body(report, "https://github.com/example/actions/runs/1")
        self.assertIn(reconcile.REPORT_MARKER, body)
        self.assertIn("NOT_VERIFIED", body)
        parsed = reconcile._latest_report({"body": body})
        self.assertEqual(parsed["schema"], report["schema"])

    def test_source_contains_no_runtime_mutation_methods(self) -> None:
        source = (HERE / "final_estate_reconciliation_v3.py").read_text(encoding="utf-8")
        for forbidden in (
            "delete_repo(",
            "create_repo(",
            "duplicate_repo(",
            "update_repo_settings(",
            "restart_space(",
            "upload_file(",
            "upload_folder(",
            "CommitOperationCopy",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
