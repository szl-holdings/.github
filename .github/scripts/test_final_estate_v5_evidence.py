#!/usr/bin/env python3
from __future__ import annotations

import copy
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
    summary_clean,
)
from final_estate_v5_evidence import (
    PUBLICATION_SCHEMA,
    READINESS_SCHEMA,
    evaluate_issue_gate,
    evaluate_release_revision_consistency,
    evaluate_replit_decommission,
    validate_official_inventory,
    validate_release_publication,
    validate_release_readiness,
)


class FakeIssueClient:
    def __init__(self, issues: dict[tuple[str, int], dict[str, Any]]) -> None:
        self.issues = issues

    def publication_evidence(self):
        issue = self.issues[EVIDENCE_ISSUES["hf_release_publication"]]
        if issue["state"] != "closed":
            raise RuntimeError("SYNTHETIC artifact producer not successful")
        return latest_report(issue), {"fixture": "SYNTHETIC native artifact"}

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


def readiness_report() -> dict[str, Any]:
    return {
        "schema": READINESS_SCHEMA,
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
                    "revision": chr(99 + index) * 40,
                    "remote_file_count": 10,
                    "selfcheck": {"ok": True},
                }
                for index, repo_id in enumerate(sorted(KERNEL_IDS))
            },
        },
    }


def publication_report() -> dict[str, Any]:
    ready = readiness_report()
    return {
        "schema": PUBLICATION_SCHEMA,
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
            "dataset": dict(ready["results"]["dataset"]),
            "kernels": {
                repo_id: {
                    **dict(ready["results"]["kernels"][repo_id]),
                    "transport": "authenticated-kernel-hub-git",
                    "build_variants_preserved": True,
                    "card_contract_byte_parity": True,
                    "build_tree_sha256": "f" * 64,
                }
                for repo_id in KERNEL_IDS
            },
        },
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

    def test_readiness_requires_actual_schema_viewer_and_exact_selfchecks(self) -> None:
        report = readiness_report()
        self.assertTrue(validate_release_readiness(report)[0])
        report["schema"] = "szl.hf-release-finalization/v1"
        self.assertFalse(validate_release_readiness(report)[0])
        report["schema"] = READINESS_SCHEMA
        report["results"]["kernels"][next(iter(KERNEL_IDS))].pop("selfcheck")
        self.assertFalse(validate_release_readiness(report)[0])

    def test_publication_requires_supported_git_transport_and_build_hashes(self) -> None:
        report = publication_report()
        self.assertTrue(validate_release_publication(report)[0])
        report["results"]["kernels"][next(iter(KERNEL_IDS))]["transport"] = "unsupported"
        self.assertFalse(validate_release_publication(report)[0])

    def test_readiness_and_publication_revisions_and_schemas_must_match(self) -> None:
        readiness = readiness_report()
        publication = publication_report()
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
        publication = publication_report()
        readiness["schema"] = "wrong"
        issues = {
            EVIDENCE_ISSUES["hf_release_readiness"]: issue_with_report(readiness),
            EVIDENCE_ISSUES["hf_release_publication"]: issue_with_report(publication),
        }
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


# Additional SAMPLE-only numeric regressions, no provider or release authority.
BAD_COUNTS = (True, False, 1.0, 0.5, "1", None, [], {}, 0, -1)
BAD_SUMMARIES = (True, False, 0.0, 0.5, -0.5, "0", None, [], {}, 1, -1)


def inventory_report():
    return {
        "schema": "szl.hf-official-estate-inventory/v1",
        "publish": True,
        "summary": {"error": 0, "warning": 0},
        "counts": {key: 1 for key in (
            "models", "datasets", "spaces", "kernels", "collections",
            "collection_references", "buckets",
        )},
        "canonical_a11oy": {
            "private": False, "sdk": "docker", "stage": "RUNNING",
            "sha": "a" * 40, "file_count": 1,
        },
        "clone_absence": {key: True for key in CLONE_IDS},
    }


REPORTS = (
    ("inventory", inventory_report, validate_official_inventory),
    ("readiness", readiness_report, validate_release_readiness),
    ("publication", publication_report, validate_release_publication),
)


class FinalEstateNumericContractTests(unittest.TestCase):
    def test_valid_integer_fixtures_stay_admitted(self):
        for name, factory, validator in REPORTS:
            with self.subTest(report=name):
                self.assertTrue(validator(factory())[0])

    def test_summary_requires_explicit_exact_integer_zeros(self):
        self.assertTrue(summary_clean({"summary": {"error": 0, "warning": 0}}))
        for key in ("error", "warning"):
            for value in BAD_SUMMARIES:
                report = {"summary": {"error": 0, "warning": 0}}
                report["summary"][key] = value
                with self.subTest(key=key, value=value):
                    self.assertFalse(summary_clean(report))

    def test_missing_or_malformed_summary_fails_without_raising(self):
        for summary in (None, False, [], "clean", {}, {"error": 0}, {"warning": 0}):
            with self.subTest(summary=summary):
                self.assertFalse(summary_clean({"summary": summary}))
        self.assertFalse(summary_clean({}))

    def test_every_evidence_validator_rejects_bad_summary_fields(self):
        for name, factory, validator in REPORTS:
            for key in ("error", "warning"):
                for value in BAD_SUMMARIES:
                    report = factory()
                    report["summary"][key] = value
                    with self.subTest(report=name, key=key, value=value):
                        self.assertFalse(validator(report)[0])
                report = factory()
                del report["summary"][key]
                with self.subTest(report=name, missing=key):
                    self.assertFalse(validator(report)[0])

    def test_each_inventory_category_requires_positive_exact_int(self):
        for key in inventory_report()["counts"]:
            for value in BAD_COUNTS:
                report = inventory_report()
                report["counts"][key] = value
                with self.subTest(key=key, value=value):
                    self.assertFalse(validate_official_inventory(report)[0])
            report = inventory_report()
            del report["counts"][key]
            self.assertFalse(validate_official_inventory(report)[0])

    def test_canonical_inventory_file_count_requires_positive_exact_int(self):
        for value in BAD_COUNTS:
            report = inventory_report()
            report["canonical_a11oy"]["file_count"] = value
            with self.subTest(value=value):
                self.assertFalse(validate_official_inventory(report)[0])
        report = inventory_report()
        del report["canonical_a11oy"]["file_count"]
        self.assertFalse(validate_official_inventory(report)[0])

    def test_each_readiness_and_publication_file_count_requires_exact_int(self):
        for name, factory, validator in REPORTS[1:]:
            for target in ("dataset", *sorted(KERNEL_IDS)):
                for value in BAD_COUNTS:
                    report = factory()
                    item = report["results"]["dataset"] if target == "dataset" else report["results"]["kernels"][target]
                    item["remote_file_count"] = value
                    with self.subTest(report=name, target=target, value=value):
                        self.assertFalse(validator(report)[0])
                report = factory()
                item = report["results"]["dataset"] if target == "dataset" else report["results"]["kernels"][target]
                del item["remote_file_count"]
                self.assertFalse(validator(report)[0])

    def test_positive_integer_range_is_not_reduced(self):
        for value in (1, 10, 2**64):
            for name, factory, validator in REPORTS:
                report = factory()
                if name == "inventory":
                    report["counts"] = {key: value for key in report["counts"]}
                    report["canonical_a11oy"]["file_count"] = value
                else:
                    for item in (report["results"]["dataset"], *report["results"]["kernels"].values()):
                        item["remote_file_count"] = value
                with self.subTest(report=name, value=value):
                    self.assertTrue(validator(report)[0])

    def test_json_boolean_is_not_a_count_after_roundtrip(self):
        report = publication_report()
        report["results"]["dataset"]["remote_file_count"] = True
        decoded = json.loads(json.dumps(report))
        self.assertFalse(validate_release_publication(decoded)[0])

    def test_issue_and_native_artifact_gate_do_not_admit_malformed_evidence(self):
        for name, factory, _ in REPORTS:
            report = factory()
            report["summary"]["warning"] = 0.5
            gate_name = {"inventory": "official_hf_inventory",
                         "readiness": "hf_release_readiness",
                         "publication": "hf_release_publication"}[name]
            client = FakeIssueClient({EVIDENCE_ISSUES[gate_name]: issue_with_report(report)})
            with self.subTest(report=name):
                self.assertFalse(evaluate_issue_gate(client, gate_name, *EVIDENCE_ISSUES[gate_name]).ok)

    def test_revision_consistency_rejects_malformed_publication_counter(self):
        readiness = readiness_report()
        publication = publication_report()
        publication["results"]["dataset"]["remote_file_count"] = True
        issues = {
            EVIDENCE_ISSUES["hf_release_readiness"]: issue_with_report(readiness),
            EVIDENCE_ISSUES["hf_release_publication"]: issue_with_report(publication),
        }
        self.assertFalse(evaluate_release_revision_consistency(FakeIssueClient(issues)).ok)

    def test_public_projection_does_not_gain_qualification_authority(self):
        projection = {
            "schema": "szl.hf-official-estate-public-projection/v1",
            "public_counts": {"models": 1, "datasets": 1, "spaces": 1, "kernels": 1},
        }
        self.assertFalse(validate_official_inventory(copy.deepcopy(projection))[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
