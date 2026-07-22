#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from typing import Any

from final_estate_v5_core import (
    CLONE_IDS,
    EVIDENCE_ISSUES,
    KERNEL_IDS,
    REPLIT_DECOMMISSION_ISSUE,
    REPLIT_DECOMMISSION_MARKER,
    json_fences,
    latest_report,
)
from final_estate_v5_evidence import (
    evaluate_release_revision_consistency,
    evaluate_replit_decommission,
    validate_official_inventory,
    validate_release_publication,
    validate_release_readiness,
)


class FakeIssueClient:
    def __init__(self, issues: dict[tuple[str, int], dict[str, Any]]) -> None:
        self.issues = issues

    def issue(self, repo: str, number: int) -> dict[str, Any]:
        return self.issues[(repo, number)]


def issue_with_report(report: dict[str, Any], *, state: str = "closed") -> dict[str, Any]:
    return {
        "state": state,
        "state_reason": "completed" if state == "closed" else None,
        "body": "```json\n" + json.dumps(report, sort_keys=True) + "\n```\n",
        "html_url": "https://github.com/example/issues/1",
        "updated_at": "2026-07-22T00:00:00Z",
    }


class FinalEstateEvidenceV5Tests(unittest.TestCase):
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
        values = json_fences(body)
        self.assertEqual([value["schema"] for value in values], ["one", "two"])
        self.assertTrue(latest_report({"body": body})["ok"])

    def test_inventory_requires_positive_counts_and_zero_warnings(self) -> None:
        report = {
            "schema": "szl.hf-official-estate-inventory/v1",
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
                "file_count": 1685,
            },
            "clone_absence": {repo_id: True for repo_id in CLONE_IDS},
        }
        self.assertTrue(validate_official_inventory(report)[0])
        report["summary"]["warning"] = 1
        self.assertFalse(validate_official_inventory(report)[0])
        report["summary"]["warning"] = 0
        report["counts"]["buckets"] = 0
        self.assertFalse(validate_official_inventory(report)[0])

    def test_readiness_requires_viewer_and_exact_selfchecks(self) -> None:
        report = {
            "schema": "szl.hf-release-finalization/v1",
            "publish": True,
            "summary": {"error": 0, "warning": 0},
            "results": {
                "dataset": {
                    "viewer_http_status": 200,
                    "revision": "b" * 40,
                    "remote_file_count": 393,
                },
                "kernels": {
                    repo_id: {
                        "revision": "c" * 40,
                        "remote_file_count": 10,
                        "selfcheck": {"ok": True},
                    }
                    for repo_id in KERNEL_IDS
                },
            },
        }
        self.assertTrue(validate_release_readiness(report)[0])
        report["results"]["kernels"][next(iter(KERNEL_IDS))].pop("selfcheck")
        self.assertFalse(validate_release_readiness(report)[0])

    def test_publication_requires_supported_git_transport_and_build_hashes(self) -> None:
        report = {
            "schema": "szl.hf-release-finalization/v2",
            "publish": True,
            "kernel_transport": "authenticated-kernel-hub-git",
            "summary": {"error": 0, "warning": 0},
            "runtime": {"numpy": "2.2.6", "torch": "2.7.1+cpu"},
            "sources": {
                "szl_lake": "a" * 40,
                "szl_energy_attest": "b" * 40,
                "szl_lambda_gate": "c" * 40,
            },
            "results": {
                "dataset": {
                    "viewer_http_status": 200,
                    "revision": "d" * 40,
                    "remote_file_count": 393,
                },
                "kernels": {
                    repo_id: {
                        "revision": "e" * 40,
                        "transport": "authenticated-kernel-hub-git",
                        "remote_file_count": 10,
                        "build_variants_preserved": True,
                        "card_contract_byte_parity": True,
                        "build_tree_sha256": "f" * 64,
                        "selfcheck": {"passed": True},
                    }
                    for repo_id in KERNEL_IDS
                },
            },
        }
        self.assertTrue(validate_release_publication(report)[0])
        report["results"]["kernels"][next(iter(KERNEL_IDS))]["transport"] = "unsupported"
        self.assertFalse(validate_release_publication(report)[0])

    def test_readiness_and_publication_revisions_must_match(self) -> None:
        readiness = {
            "results": {
                "dataset": {"revision": "a" * 40},
                "kernels": {
                    repo_id: {"revision": chr(98 + index) * 40}
                    for index, repo_id in enumerate(sorted(KERNEL_IDS))
                },
            }
        }
        publication = json.loads(json.dumps(readiness))
        issues = {
            EVIDENCE_ISSUES["hf_release_readiness"]: issue_with_report(readiness),
            EVIDENCE_ISSUES["hf_release_publication"]: issue_with_report(publication),
        }
        self.assertTrue(
            evaluate_release_revision_consistency(FakeIssueClient(issues)).ok
        )
        publication["results"]["dataset"]["revision"] = "f" * 40
        issues[EVIDENCE_ISSUES["hf_release_publication"]] = issue_with_report(publication)
        self.assertFalse(
            evaluate_release_revision_consistency(FakeIssueClient(issues)).ok
        )

    def test_replit_is_decommissioned_not_operational(self) -> None:
        repo, number = REPLIT_DECOMMISSION_ISSUE
        issue = {
            "state": "closed",
            "state_reason": "not_planned",
            "body": f"<!-- {REPLIT_DECOMMISSION_MARKER} -->\n",
            "html_url": f"https://github.com/{repo}/issues/{number}",
            "updated_at": "2026-07-22T00:00:00Z",
        }
        gate = evaluate_replit_decommission(FakeIssueClient({(repo, number): issue}))
        self.assertTrue(gate.ok)
        self.assertFalse(gate.evidence["operational_claim"])
        issue["state_reason"] = "completed"
        self.assertFalse(
            evaluate_replit_decommission(FakeIssueClient({(repo, number): issue})).ok
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
