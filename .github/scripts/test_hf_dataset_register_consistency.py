#!/usr/bin/env python3
"""Offline consistency checks for captured dataset audit metadata.

These synthetic fixtures use the real audit envelope and CSV columns. They
establish comparison behavior, not legal rights, dataset validity, or raw JSON
signature verification. Only stdlib modules are required; no network or auth
operation is permitted by the fixtures.
"""
from __future__ import annotations

import contextlib
import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.request


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "hf_dataset_register_consistency", HERE / "hf_dataset_register_consistency.py"
)
assert SPEC and SPEC.loader
guard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = guard
SPEC.loader.exec_module(guard)

REGISTER_ID = "SZLHOLDINGS/model-bom"
DATASET_ID = "SZLHOLDINGS/synthetic-register-fixture"
REGISTER_REVISION = "a" * 40
DATASET_REVISION = "b" * 40
HISTORICAL_PARENT = "c" * 40
CSV_FIELDS = [
    "dataset_id", "license", "training_eligibility", "source_datasets",
    "downloads_30d", "last_modified", "notes",
]
UNREGISTERED_IDS = [
    "SZLHOLDINGS/oac-clinical-transport-observability-synthetic",
    "SZLHOLDINGS/release-assets",
    "SZLHOLDINGS/szl-estate-graph",
    "SZLHOLDINGS/szl-frontier-evaluation-receipts",
]


def raw_url(repo_id, revision, filename):
    return f"https://huggingface.co/datasets/{repo_id}/raw/{revision}/{filename}"


def envelope(repo_id, revision, filename, raw=b"captured fixture bytes\n"):
    return {
        "url": raw_url(repo_id, revision, filename),
        "server_revision": revision,
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "http_status": 200,
        "error": None,
        "truncated": False,
    }


def dataset(repo_id=DATASET_ID, revision=DATASET_REVISION, license_name="apache-2.0"):
    status = {
        "schema": "szl.hf-status/v1",
        "subject": {
            "repo_id": repo_id, "repo_type": "dataset",
            "based_on_revision": HISTORICAL_PARENT,
        },
        "training_suitability": "BLOCKED",
        "production_ready": False,
        "promotion_gate": {"state": "BLOCKED"},
    }
    provenance = {
        "schema": "szl.hf-provenance/v1",
        "subject": {"repo_id": repo_id, "repo_type": "dataset"},
        "upstream_snapshot": {"revision": HISTORICAL_PARENT},
        "dataset_artifact_provenance": {
            "consent_and_usage_rights": {"state": "UNKNOWN"},
            "artifact_license": {"state": "UNKNOWN"},
            "training_suitability": {"state": "BLOCKED"},
        },
    }
    return {
        "id": repo_id,
        "asset_type": "dataset",
        "revision": revision,
        "scope": "metadata-card-license-and-file-inventory",
        "card_metadata": {"license": license_name, "training_eligible": False},
        "card_evidence": envelope(repo_id, revision, "README.md"),
        "card_claim_excerpts": [{"line": 12, "text": "training_eligible: false"}],
        "provenance": {"contracts": {
            "status.json": {
                "content": status, "evidence": envelope(repo_id, revision, "status.json")
            },
            "provenance.json": {
                "content": provenance,
                "evidence": envelope(repo_id, revision, "provenance.json"),
            },
        }},
    }


def rows_for(snapshot):
    raw = snapshot["datasets"][0]["provenance"]["contracts"][
        "DATASET_LICENSE_REGISTER.csv"
    ]["content"]
    return list(csv.DictReader(io.StringIO(raw)))


def put_rows(snapshot, rows, *, observed_rows=None):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    raw = output.getvalue()
    snapshot["datasets"][0]["provenance"]["contracts"][
        "DATASET_LICENSE_REGISTER.csv"
    ] = {
        "content": raw,
        "evidence": envelope(
            REGISTER_ID, REGISTER_REVISION, "DATASET_LICENSE_REGISTER.csv", raw.encode("utf-8")
        ),
    }
    snapshot["license_register"]["observed_rows"] = (
        len(rows) if observed_rows is None else observed_rows
    )


def snapshot():
    register = dataset(REGISTER_ID, REGISTER_REVISION, "other")
    register["provenance"]["contracts"]["status.json"]["content"] = {
        "schema": "szl.hf-license-candidate-status/v1",
        "repository_id": REGISTER_ID,
        "repository_type": "dataset",
        "parent_sha": HISTORICAL_PARENT,
        "claims": {
            "copyright_ownership": "UNKNOWN",
            "relicensing_authority": "UNKNOWN",
            "training_suitability": "BLOCKED",
            "production_ready": False,
        },
    }
    register["provenance"]["contracts"]["provenance.json"]["content"] = {
        "schema": "szl.hf-license-candidate-provenance/v1",
        "repository": {"id": REGISTER_ID, "type": "dataset", "parent_sha": HISTORICAL_PARENT},
        "evidence_boundaries": {
            "copyright_ownership": "UNKNOWN", "relicensing_authority": "UNKNOWN",
            "training_suitability": "BLOCKED", "production_ready": False,
        },
    }
    audit = {
        "schema": "szl.dataset-collection-evidence-audit/v1",
        "generated_at_utc": "2026-09-30T00:00:00+00:00",
        "coverage": {"public_datasets_listed": 2},
        "license_register": {
            "id": REGISTER_ID, "revision": REGISTER_REVISION, "observed_rows": 2,
            "source_url": raw_url(REGISTER_ID, REGISTER_REVISION, "DATASET_LICENSE_REGISTER.csv"),
        },
        "datasets": [register, dataset()],
    }
    put_rows(audit, [
        dict(zip(CSV_FIELDS, [REGISTER_ID, "other", "REVIEW-REQUIRED", "", "0", "2026-09-29", ""])),
        dict(zip(CSV_FIELDS, [DATASET_ID, "apache-2.0", "BANNED", "", "0", "2026-09-29", ""])),
    ])
    return audit


def report_row(report, repo_id=DATASET_ID):
    return next(row for row in report["assets"] if row["id"] == repo_id)


class DatasetRegisterConsistencyTests(unittest.TestCase):
    def setUp(self):
        # Resolve the stdlib scratch location before the guard's no-environment
        # sentinel. TemporaryDirectory must not need environment reads while
        # check_snapshot/main are being exercised.
        self.temporary_base = tempfile.gettempdir()
        self.assertTrue(Path(self.temporary_base).is_absolute())
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        denied = AssertionError("offline dataset guard attempted a network or auth operation")
        for target in (
            "socket.create_connection", "socket.getaddrinfo",
            "urllib.request.urlopen", "subprocess.run", "os.getenv",
        ):
            self.stack.enter_context(mock.patch(target, side_effect=denied))
        auth_names = {"HF_TOKEN", "HF_ORG_TOKEN", "HF_WRITE_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"}
        self.stack.enter_context(mock.patch.dict(os.environ, {name: "" for name in auth_names}))

    def check(self, audit):
        before = copy.deepcopy(audit)
        report = guard.check_snapshot(audit)
        self.assertEqual(audit, before, "checker must preserve its captured input")
        for field in ("legal_approval", "training_approval", "rights_changed", "hub_requests"):
            self.assertIs(report[field], False)
        self.assertEqual(
            report["content_claim_fidelity"],
            "INHERITED_FROM_SUPPLIED_AUDIT_NOT_CRYPTOGRAPHICALLY_AUTHENTICATED",
        )
        for row in report["assets"]:
            self.assertIn(row["license_consistency"], {"MATCHED_METADATA", "CONFLICT", "UNKNOWN"})
            self.assertIn(row["training_comparison"], {"MATCHED_METADATA", "CONFLICT", "UNKNOWN"})
            self.assertTrue(row["training_allowed"] is False or row["training_allowed"] is None)
            self.assertIsInstance(row["training_disposition"], str)
            self.assertEqual(row["rights_clearance"], "NOT_ESTABLISHED")
            self.assertIsInstance(row["restrictions"], list)
            self.assertTrue(all(isinstance(value, str) for value in row["restrictions"]))
            self.assertTrue(all(isinstance(value.get("code"), str) for value in row["findings"]))
        return report

    def test_matching_restricted_metadata_never_authorizes_training(self):
        report = self.check(snapshot())
        self.assertEqual(report["state"], "MATCHED_METADATA")
        row = report_row(report)
        self.assertEqual(row["license_consistency"], "MATCHED_METADATA")
        self.assertEqual(row["training_comparison"], "MATCHED_METADATA")
        self.assertIs(row["training_allowed"], False)
        self.assertIn("BANNED", " ".join(row["restrictions"]))

    def test_current_blocked_conflicts_with_positive_register_label(self):
        audit = snapshot()
        rows = rows_for(audit)
        rows[1]["training_eligibility"] = "ELIGIBLE-WITH-ATTRIBUTION"
        put_rows(audit, rows)
        report = self.check(audit)
        row = report_row(report)
        self.assertEqual(report["state"], "CONFLICT")
        self.assertEqual(row["training_comparison"], "CONFLICT")
        self.assertIs(row["training_allowed"], False)
        self.assertIn("BLOCKED", row["training_disposition"])
        self.assertTrue(row["findings"])

    def test_model_bom_other_versus_apache_conflict_preserves_review_and_blocked(self):
        audit = snapshot()
        audit["datasets"][0]["card_metadata"]["license"] = "apache-2.0"
        report = self.check(audit)
        row = report_row(report, REGISTER_ID)
        self.assertEqual(report["state"], "CONFLICT")
        self.assertEqual(row["license_consistency"], "CONFLICT")
        self.assertEqual(row["register_eligibility"], "REVIEW-REQUIRED")
        self.assertIs(row["training_allowed"], False)
        self.assertIn("BLOCKED", row["training_disposition"])
        self.assertIn("REVIEW-REQUIRED", " ".join(row["restrictions"]))

    def test_banned_and_counsel_hold_survive_apache_metadata(self):
        for eligibility in ("BANNED", "HELD-COUNSEL"):
            with self.subTest(eligibility=eligibility):
                audit = snapshot()
                rows = rows_for(audit)
                rows[1]["training_eligibility"] = eligibility
                put_rows(audit, rows)
                row = report_row(self.check(audit))
                self.assertEqual(row["register_eligibility"], eligibility)
                self.assertIs(row["training_allowed"], False)
                self.assertIn(eligibility, " ".join(row["restrictions"]))

    def test_card_boolean_false_restricts_even_without_status_contract(self):
        audit = snapshot()
        rows = rows_for(audit)
        rows[1]["training_eligibility"] = "ELIGIBLE-WITH-ATTRIBUTION"
        put_rows(audit, rows)
        audit["datasets"][1]["provenance"]["contracts"] = {}
        row = report_row(self.check(audit))
        self.assertIs(row["training_allowed"], False)
        self.assertEqual(row["training_comparison"], "CONFLICT")
        self.assertIn("BLOCKED", row["restrictions"])
        self.assertNotEqual(row["training_disposition"], "ALLOWED")

    def test_positive_register_and_apache_cannot_establish_unknown_upstream_rights(self):
        audit = snapshot()
        rows = rows_for(audit)
        rows[1]["training_eligibility"] = "ELIGIBLE-WITH-ATTRIBUTION"
        put_rows(audit, rows)
        record = audit["datasets"][1]
        record["card_metadata"].pop("training_eligible")
        record["card_claim_excerpts"] = []
        record["provenance"]["contracts"]["status.json"]["content"]["training_suitability"] = "UNKNOWN"
        record["provenance"]["contracts"]["provenance.json"]["content"][
            "dataset_artifact_provenance"
        ]["training_suitability"] = {"state": "UNKNOWN"}
        row = report_row(self.check(audit))
        self.assertEqual(row["training_comparison"], "CONFLICT")
        self.assertIsNone(row["training_allowed"])
        self.assertNotEqual(row["training_disposition"], "ALLOWED")

    def test_all_four_current_unlisted_ids_are_unknown_not_implicitly_eligible(self):
        audit = snapshot()
        for index, repo_id in enumerate(UNREGISTERED_IDS):
            audit["datasets"].append(dataset(repo_id, format(index + 10, "040x")))
        audit["coverage"]["public_datasets_listed"] = len(audit["datasets"])
        report = self.check(audit)
        self.assertEqual(report["state"], "UNKNOWN")
        for repo_id in UNREGISTERED_IDS:
            row = report_row(report, repo_id)
            self.assertEqual(row["license_consistency"], "UNKNOWN")
            self.assertEqual(row["training_comparison"], "UNKNOWN")
            self.assertIsNot(row["training_allowed"], True)

    def test_historical_parents_need_not_equal_current_envelope_revision(self):
        audit = snapshot()
        self.assertNotEqual(HISTORICAL_PARENT, REGISTER_REVISION)
        self.assertNotEqual(HISTORICAL_PARENT, DATASET_REVISION)
        report = self.check(audit)
        self.assertEqual(report["state"], "MATCHED_METADATA")

    def test_catalog_only_records_do_not_inspect_card_or_contracts(self):
        audit = snapshot()
        record = audit["datasets"][1]
        record["scope"] = "catalog-only"
        record["card_evidence"] = {"url": "https://invalid.example/main", "http_status": 500}
        record["card_claim_excerpts"] = [{"line": 1, "text": "training_eligible: true"}]
        record["provenance"]["contracts"] = {"status.json": {"content": "not parsed JSON"}}
        report = self.check(audit)
        row = report_row(report)
        self.assertIsNot(row["training_allowed"], True)
        self.assertNotEqual(row["license_consistency"], "MATCHED_METADATA")

    def test_dataset_identity_requires_explicit_asset_type(self):
        audit = snapshot()
        for record in audit["datasets"]:
            record.pop("asset_type")
        with self.assertRaises(guard.SnapshotError):
            guard.check_snapshot(audit)

    def test_missing_or_mismatched_public_inventory_count_cannot_look_complete(self):
        for coverage in (None, {}, {"public_datasets_listed": 1}, {"public_datasets_listed": True}):
            with self.subTest(coverage=coverage):
                audit = snapshot()
                audit["coverage"] = coverage
                with self.assertRaises(guard.SnapshotError):
                    guard.check_snapshot(audit)

    def test_unknown_governance_schema_is_observed_unknown_without_inventing_pass(self):
        audit = snapshot()
        for contract in audit["datasets"][1]["provenance"]["contracts"].values():
            contract["content"]["schema"] = "unrecognized-governance-schema/v99"
        row = report_row(self.check(audit))
        self.assertEqual(row["observed_training_states"], ["UNKNOWN", "UNKNOWN"])
        self.assertIs(row["training_allowed"], False)
        self.assertEqual(row["register_eligibility"], "BANNED")

    def test_other_dataset_and_historical_prose_does_not_change_own_machine_restrictions(self):
        audit = snapshot()
        audit["datasets"][0]["card_claim_excerpts"] = [
            {"line": 10, "text": "szl-quant-sft-v1 is HELD-COUNSEL pending review."},
            {"line": 11, "text": "killinchu-osint-corpus is BANNED; do not train on that corpus."},
            {"line": 12, "text": "A historical publisher's source documents said all rights reserved."},
        ]
        row = report_row(self.check(audit), REGISTER_ID)
        self.assertEqual(set(row["restrictions"]), {"REVIEW-REQUIRED", "BLOCKED"})
        self.assertEqual(row["training_disposition"], "BLOCKED")
        self.assertEqual(row["register_eligibility"], "REVIEW-REQUIRED")

    def test_prose_only_eligibility_never_clears_missing_machine_metadata(self):
        audit = snapshot()
        rows = rows_for(audit)
        rows[1]["training_eligibility"] = ""
        put_rows(audit, rows)
        record = audit["datasets"][1]
        record["card_metadata"].pop("training_eligible")
        record["provenance"]["contracts"] = {}
        record["card_claim_excerpts"] = [
            {"line": 12, "text": "Historical marketing called this ELIGIBLE and production-ready."}
        ]
        row = report_row(self.check(audit))
        self.assertEqual(row["training_comparison"], "UNKNOWN")
        self.assertEqual(row["training_disposition"], "UNKNOWN")
        self.assertIsNone(row["training_allowed"])

    def test_all_rights_reserved_is_retained_even_with_an_apache_card_label(self):
        audit = snapshot()
        rows = rows_for(audit)
        rows[1]["training_eligibility"] = "ELIGIBLE-WITH-ATTRIBUTION"
        put_rows(audit, rows)
        record = audit["datasets"][1]
        record["card_metadata"].pop("training_eligible")
        record["card_metadata"]["license_name"] = "all-rights-reserved"
        record["provenance"]["contracts"] = {}
        row = report_row(self.check(audit))
        self.assertEqual(row["license_consistency"], "MATCHED_METADATA")
        self.assertEqual(row["training_comparison"], "CONFLICT")
        self.assertIn("RESTRICTED", row["restrictions"])
        self.assertIs(row["training_allowed"], False)

    def test_false_text_is_not_substituted_for_boolean_false(self):
        audit = snapshot()
        rows = rows_for(audit)
        rows[1]["training_eligibility"] = "ELIGIBLE-WITH-ATTRIBUTION"
        put_rows(audit, rows)
        record = audit["datasets"][1]
        record["card_metadata"]["training_eligible"] = "false"
        record["provenance"]["contracts"] = {}
        row = report_row(self.check(audit))
        self.assertEqual(row["training_comparison"], "CONFLICT")
        self.assertIsNone(row["training_allowed"])

    def test_register_only_banned_id_without_a_current_capture_is_unknown_and_restricted(self):
        audit = snapshot()
        rows = rows_for(audit)
        missing_id = "SZLHOLDINGS/uncaptured-register-fixture"
        rows.append(dict(zip(CSV_FIELDS, [missing_id, "other", "BANNED", "", "0", "2026-09-29", ""])))
        put_rows(audit, rows)
        row = report_row(self.check(audit), missing_id)
        self.assertEqual(row["license_consistency"], "UNKNOWN")
        self.assertEqual(row["training_comparison"], "UNKNOWN")
        self.assertEqual(row["register_eligibility"], "BANNED")
        self.assertIs(row["training_allowed"], False)

    def test_bound_governance_subject_cannot_belong_to_another_dataset(self):
        for filename in ("status.json", "provenance.json"):
            with self.subTest(filename=filename):
                audit = snapshot()
                audit["datasets"][1]["provenance"]["contracts"][filename]["content"][
                    "subject"
                ]["repo_id"] = REGISTER_ID
                with self.assertRaises(guard.SnapshotError):
                    guard.check_snapshot(audit)

    def test_structured_contract_digest_is_inherited_not_rehashed_from_normalized_json(self):
        audit = snapshot()
        for record in audit["datasets"]:
            for name, contract in record["provenance"]["contracts"].items():
                if name != "DATASET_LICENSE_REGISTER.csv":
                    contract["evidence"]["content_sha256"] = "7" * 64
        self.assertEqual(self.check(audit)["state"], "MATCHED_METADATA")

    def test_input_snapshot_remains_unchanged_on_validation_failure(self):
        audit = snapshot()
        audit["datasets"][1]["revision"] = "main"
        before = copy.deepcopy(audit)
        with self.assertRaises(guard.SnapshotError):
            guard.check_snapshot(audit)
        self.assertEqual(audit, before)

    def test_unknown_audit_schema_is_rejected(self):
        audit = snapshot()
        audit["schema"] = "szl.dataset-collection-evidence-audit/v99"
        with self.assertRaises(guard.SnapshotError):
            guard.check_snapshot(audit)

    def test_duplicate_dataset_ids_are_rejected(self):
        audit = snapshot()
        audit["datasets"].append(copy.deepcopy(audit["datasets"][1]))
        with self.assertRaises(guard.SnapshotError):
            guard.check_snapshot(audit)

    def test_duplicate_csv_ids_are_rejected_even_if_rows_identical(self):
        audit = snapshot()
        rows = rows_for(audit)
        rows.append(copy.deepcopy(rows[1]))
        put_rows(audit, rows)
        with self.assertRaises(guard.SnapshotError):
            guard.check_snapshot(audit)

    def test_csv_digest_mismatch_is_rejected(self):
        audit = snapshot()
        contract = audit["datasets"][0]["provenance"]["contracts"]["DATASET_LICENSE_REGISTER.csv"]
        contract["content"] += "\n"
        with self.assertRaises(guard.SnapshotError):
            guard.check_snapshot(audit)

    def test_csv_observed_row_count_drift_is_rejected(self):
        audit = snapshot()
        audit["license_register"]["observed_rows"] = 3
        with self.assertRaises(guard.SnapshotError):
            guard.check_snapshot(audit)

    def test_revisions_are_exact_lowercase_commit_shas(self):
        for bad in (None, "", "main", "a" * 39, "A" * 40, "g" * 40):
            with self.subTest(revision=bad):
                audit = snapshot()
                audit["datasets"][1]["revision"] = bad
                with self.assertRaises(guard.SnapshotError):
                    guard.check_snapshot(audit)

    def test_register_revision_must_match_model_bom_record(self):
        audit = snapshot()
        audit["license_register"]["revision"] = "d" * 40
        with self.assertRaises(guard.SnapshotError):
            guard.check_snapshot(audit)

    def test_register_source_url_cannot_be_mutable_or_another_raw_file(self):
        for bad in (
            raw_url(REGISTER_ID, "main", "DATASET_LICENSE_REGISTER.csv"),
            raw_url(REGISTER_ID, REGISTER_REVISION, "OTHER.csv"),
        ):
            with self.subTest(url=bad):
                audit = snapshot()
                audit["license_register"]["source_url"] = bad
                with self.assertRaises(guard.SnapshotError):
                    guard.check_snapshot(audit)

    def test_used_evidence_requires_matching_requested_and_server_revisions(self):
        locations = [
            (0, "DATASET_LICENSE_REGISTER.csv"), (0, "status.json"),
            (0, "provenance.json"), (1, "README.md"),
            (1, "status.json"), (1, "provenance.json"),
        ]
        for index, filename in locations:
            for fault in ("missing_head", "server_drift", "mutable_url", "wrong_path"):
                with self.subTest(index=index, filename=filename, fault=fault):
                    audit = snapshot()
                    record = audit["datasets"][index]
                    evidence = (
                        record["card_evidence"] if filename == "README.md" else
                        record["provenance"]["contracts"][filename]["evidence"]
                    )
                    if fault == "missing_head":
                        evidence.pop("server_revision")
                    elif fault == "server_drift":
                        evidence["server_revision"] = "e" * 40
                    elif fault == "mutable_url":
                        evidence["url"] = raw_url(record["id"], "main", filename)
                    else:
                        evidence["url"] = raw_url(record["id"], record["revision"], "unrelated.json")
                    with self.assertRaises(guard.SnapshotError):
                        guard.check_snapshot(audit)

    def test_used_evidence_cannot_be_failed_truncated_or_digestless(self):
        for field, value in (
            ("http_status", 500), ("error", "recorded read failure"),
            ("truncated", True), ("content_sha256", None), ("content_sha256", "z" * 64),
        ):
            with self.subTest(field=field, value=value):
                audit = snapshot()
                audit["datasets"][1]["card_evidence"][field] = value
                with self.assertRaises(guard.SnapshotError):
                    guard.check_snapshot(audit)

    def run_cli(self, audit, *, existing_report=None, same_path=False):
        with tempfile.TemporaryDirectory(dir=self.temporary_base) as temporary:
            directory = Path(temporary)
            source = directory / "audit.json"
            source_bytes = json.dumps(audit, indent=2).encode("utf-8")
            source.write_bytes(source_bytes)
            report_path = source if same_path else directory / "report.json"
            if existing_report is not None:
                report_path.write_bytes(existing_report)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = guard.main(["--snapshot", str(source), "--report", str(report_path)])
            self.assertEqual(source.read_bytes(), source_bytes)
            output = report_path.read_bytes() if report_path.exists() else None
            return result, output

    def test_cli_exit_codes_match_consistency_without_training_authority(self):
        matched = snapshot()
        conflict = snapshot()
        conflict["datasets"][0]["card_metadata"]["license"] = "apache-2.0"
        unknown = snapshot()
        unknown["datasets"].append(dataset(UNREGISTERED_IDS[0], "d" * 40))
        unknown["coverage"]["public_datasets_listed"] = len(unknown["datasets"])
        for audit, expected in ((matched, 0), (conflict, 1), (unknown, 2)):
            with self.subTest(expected=expected):
                result, output = self.run_cli(audit)
                self.assertEqual(result, expected)
                report = json.loads(output.decode("utf-8"))
                self.assertTrue(all(row["training_allowed"] is not True for row in report["assets"]))

    def test_cli_invalid_snapshot_returns_two_without_success_report(self):
        audit = snapshot()
        audit["schema"] = "unsupported"
        result, output = self.run_cli(audit)
        self.assertEqual(result, 2)
        if output is not None:
            self.assertNotEqual(json.loads(output.decode("utf-8")).get("state"), "MATCHED_METADATA")

    def test_cli_report_is_exclusive_and_never_overwrites_existing_evidence(self):
        sentinel = b"unique report evidence must survive\n"
        result, output = self.run_cli(snapshot(), existing_report=sentinel)
        self.assertEqual(result, 2)
        self.assertEqual(output, sentinel)

    def test_cli_report_cannot_overwrite_snapshot_itself(self):
        result, _output = self.run_cli(snapshot(), same_path=True)
        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
