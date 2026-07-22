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


class FinalEstateReconciliationV4Tests(unittest.TestCase):
    def test_json_fence_parser_uses_latest_valid_object(self) -> None:
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

    def test_official_inventory_requires_every_positive_asset_class(self) -> None:
        report = {
            "publish": True,
            "summary": {"error": 0, "warning": 0},
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
        self.assertTrue(reconcile.validate_official_inventory(report)[0])
        report["counts"]["buckets"] = 0
        self.assertFalse(reconcile.validate_official_inventory(report)[0])

    def test_release_readiness_uses_finalizer_schema(self) -> None:
        report = {
            "publish": True,
            "summary": {"error": 0, "warning": 0},
            "results": {
                "dataset": {
                    "viewer_http_status": 200,
                    "after_sha": "b" * 40,
                },
                "kernels": {
                    repo_id: {
                        "after_sha": "c" * 40,
                        "selfcheck": {"ok": True},
                    }
                    for repo_id in reconcile.KERNEL_IDS
                },
            },
        }
        self.assertTrue(reconcile.validate_release_readiness(report)[0])
        report["results"]["dataset"]["viewer_http_status"] = 503
        self.assertFalse(reconcile.validate_release_readiness(report)[0])

    def test_kernel_readiness_uses_card_publication_schema(self) -> None:
        report = {
            "publish": True,
            "summary": {"error": 0, "warning": 0},
            "failures": [],
            "results": {
                repo_id: {
                    "revision": "d" * 40,
                    "build_variants_preserved": True,
                    "card_contract_byte_parity": True,
                    "selfcheck": {"passed": True},
                }
                for repo_id in reconcile.KERNEL_IDS
            },
        }
        self.assertTrue(reconcile.validate_kernel_readiness(report)[0])
        first = next(iter(reconcile.KERNEL_IDS))
        report["results"][first]["card_contract_byte_parity"] = False
        self.assertFalse(reconcile.validate_kernel_readiness(report)[0])

    def test_relock_requires_public_running_exact_pair_and_clone_absence(self) -> None:
        report = {
            "status": "PASS",
            "public": True,
            "sdk": "docker",
            "runtime_stage": "RUNNING",
            "github_source_sha": "e" * 40,
            "hf_repository_sha": "f" * 40,
            "hf_runtime_sha": "f" * 40,
            "clone_presence": {f"clone-{index}": False for index in range(1, 5)},
        }
        self.assertTrue(reconcile.validate_a11oy_relock(report)[0])
        report["clone_presence"]["clone-1"] = True
        self.assertFalse(reconcile.validate_a11oy_relock(report)[0])

    def test_replit_gate_requires_complete_nested_receipt(self) -> None:
        report = {
            "ok": True,
            "production_url": "https://example.replit.app",
            "receipt": {
                "source_revision": "a" * 40,
                "deployment_revision": "deploy-123",
                "production_url": "https://example.replit.app",
                "tests_passed": True,
                "mobile_passed": True,
                "keyboard_passed": True,
                "readiness": {"GET": 200, "HEAD": 200},
                "production": {"GET": 200, "HEAD": 200},
            },
        }
        self.assertTrue(reconcile.validate_replit(report)[0])
        report["receipt"].pop("keyboard_passed")
        self.assertFalse(reconcile.validate_replit(report)[0])

    def test_credential_gate_requires_live_org_read_and_closed_issue(self) -> None:
        class EvidenceClient:
            @staticmethod
            def issue(_repo: str, _number: int) -> dict[str, object]:
                return {
                    "state": "closed",
                    "html_url": "https://example.test/issues/176",
                }

        class OrgClient:
            @staticmethod
            def code_security_configurations() -> list[dict[str, object]]:
                return [{"id": 252588}]

        gate = reconcile.evaluate_credential_gate(
            EvidenceClient(), OrgClient(), True
        )
        self.assertTrue(gate.ok)
        self.assertFalse(
            reconcile.evaluate_credential_gate(EvidenceClient(), OrgClient(), False).ok
        )

    def test_issue_body_is_machine_readable(self) -> None:
        report = {
            "schema": "szl.final-estate-reconciliation/v4",
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
            "model_boundaries": {},
            "boundaries": [],
        }
        body = reconcile.issue_body(
            report, "https://github.com/example/actions/runs/1"
        )
        self.assertIn(reconcile.REPORT_MARKER, body)
        self.assertIn("NOT_VERIFIED", body)
        self.assertEqual(
            reconcile._latest_report({"body": body})["schema"], report["schema"]
        )

    def test_repository_token_precedes_organization_token(self) -> None:
        source = (HERE / "final_estate_reconciliation_v4.py").read_text(
            encoding="utf-8"
        )
        main = source[source.index("def main()") :]
        self.assertLess(
            main.index('os.environ.get("GITHUB_TOKEN")'),
            main.index('os.environ.get("SZL_GITHUB_TOKEN")'),
        )

    def test_source_contains_no_runtime_mutation_methods(self) -> None:
        source = (HERE / "final_estate_reconciliation_v4.py").read_text(
            encoding="utf-8"
        )
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
