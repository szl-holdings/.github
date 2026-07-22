#!/usr/bin/env python3
from __future__ import annotations

import importlib
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
reconcile = importlib.import_module("final_estate_reconciliation_v4")


class FinalEstateReconciliationTests(unittest.TestCase):
    def test_json_fence_parser_selects_latest_valid_object(self) -> None:
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

    def test_official_inventory_requires_all_categories_and_exact_clone_absence(self) -> None:
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
            "clone_absence": {repo_id: True for repo_id in reconcile.CLONE_IDS},
        }
        self.assertTrue(reconcile.validate_official_inventory(report)[0])
        report["clone_absence"].pop(next(iter(reconcile.CLONE_IDS)))
        self.assertFalse(reconcile.validate_official_inventory(report)[0])

    def test_release_readiness_requires_explicit_viewer_and_selfcheck_evidence(self) -> None:
        report = {
            "publish": True,
            "summary": {"error": 0},
            "results": {
                "dataset": {
                    "viewer_http_status": 200,
                    "revision": "b" * 40,
                    "remote_file_count": 7,
                },
                "kernels": {
                    repo_id: {
                        "revision": "c" * 40,
                        "remote_file_count": 10,
                        "selfcheck": {"ok": True},
                    }
                    for repo_id in reconcile.KERNEL_IDS
                },
            },
        }
        self.assertTrue(reconcile.validate_release_readiness(report)[0])
        first = next(iter(reconcile.KERNEL_IDS))
        report["results"]["kernels"][first].pop("selfcheck")
        self.assertFalse(reconcile.validate_release_readiness(report)[0])

    def test_kernel_publication_requires_exact_runtime_and_byte_readback(self) -> None:
        report = {
            "schema": "szl.hf-kernel-card-publish/v2",
            "publish": True,
            "summary": {"error": 0},
            "runtime": {"numpy": "2.2.6", "torch": "2.7.1+cpu"},
            "results": {
                repo_id: {
                    "revision": "d" * 40,
                    "remote_file_count": 10,
                    "build_variants_preserved": True,
                    "card_contract_byte_parity": True,
                    "selfcheck": {"passed": True},
                }
                for repo_id in reconcile.KERNEL_IDS
            },
        }
        self.assertTrue(reconcile.validate_kernel_publication(report)[0])
        report["runtime"]["numpy"] = "2.3.0"
        self.assertFalse(reconcile.validate_kernel_publication(report)[0])

    def test_relock_requires_source_binding_and_all_clones_absent(self) -> None:
        report = {
            "schema": "szl.a11oy-deployment-relock/v2",
            "status": "PASS",
            "public": True,
            "sdk": "docker",
            "runtime_stage": "RUNNING",
            "dockerfile_present": True,
            "build_identity_contains_source": True,
            "managed_file_count": 1685,
            "github_source_sha": "e" * 40,
            "hf_repository_sha": "f" * 40,
            "hf_runtime_sha": "f" * 40,
            "clone_presence": {repo_id: False for repo_id in reconcile.CLONE_IDS},
        }
        self.assertTrue(reconcile.validate_a11oy_relock(report)[0])
        report["clone_presence"][next(iter(reconcile.CLONE_IDS))] = True
        self.assertFalse(reconcile.validate_a11oy_relock(report)[0])

    def test_replit_requires_exact_receipt_get_head_and_accessibility(self) -> None:
        origin = "https://example.replit.app"
        report = {
            "schema": "szl.replit-public-status/v1",
            "repl_id": reconcile.REPL_ID,
            "ok": True,
            "status": "OPERATIONAL",
            "production_url": origin,
            "receipt": {
                "schema": "szl.unified-control-hub.deployment-receipt/v1",
                "repl_id": reconcile.REPL_ID,
                "source_revision": "a" * 64,
                "deployment_revision": "deployment-20260722-0001",
                "production_url": origin,
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
                    "checks": {"frontend": True, "backend": True, "receipt": True},
                },
                "accessibility": {
                    "status": "passed",
                    "keyboard": True,
                    "focus_visible": True,
                    "semantic_landmarks": True,
                    "contrast": True,
                },
            },
            "attempts": [
                {
                    "ok": True,
                    "get_status": 200,
                    "head_status": 200,
                    "final_origin": origin,
                }
            ],
        }
        self.assertTrue(reconcile.validate_replit(report)[0])
        report["receipt"]["accessibility"]["keyboard"] = False
        self.assertFalse(reconcile.validate_replit(report)[0])

    def test_issue_body_is_machine_readable(self) -> None:
        report = {
            "schema": reconcile.REPORT_SCHEMA,
            "generated_at": "2026-07-22T00:00:00+00:00",
            "status": "NOT_VERIFIED",
            "operational_verified": False,
            "gates": [
                {"name": "example", "ok": False, "detail": "not ready", "evidence": {}}
            ],
            "summary": {"ok": 0, "error": 1, "total": 1},
            "boundaries": [],
        }
        body = reconcile.issue_body(report, "https://github.com/example/actions/runs/1")
        self.assertIn(reconcile.REPORT_MARKER, body)
        parsed = reconcile._latest_report({"body": body})
        self.assertEqual(parsed["schema"], reconcile.REPORT_SCHEMA)

    def test_source_contains_no_runtime_mutation_methods(self) -> None:
        source = (HERE / "final_estate_reconciliation_v4.py").read_text(encoding="utf-8")
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
