#!/usr/bin/env python3
# Copyright 2026 SZL Holdings — SPDX-License-Identifier: Apache-2.0
"""Network-free contract tests for szl_admission_checks.py (synthetic fixtures only)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("szl_admission_checks.py")
SPEC = importlib.util.spec_from_file_location("szl_admission_checks", MODULE_PATH)
assert SPEC and SPEC.loader
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)


def msg(user: str, assistant: str = "ok") -> dict:
    return {"messages": [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]}


class DuplicateRateTests(unittest.TestCase):
    def test_flags_inflated_curriculum(self) -> None:
        rows = [{"text": "q1"}] * 19 + [{"text": "q2"}]
        r = A.duplicate_rate(rows)
        self.assertEqual(r["status"], "FAIL")
        self.assertEqual(r["unique"], 2)
        self.assertEqual(r["max_multiplicity"], 19)

    def test_passes_clean(self) -> None:
        self.assertEqual(A.duplicate_rate([{"text": f"q{i}"} for i in range(50)])["status"], "PASS")


class SplitOverlapTests(unittest.TestCase):
    def test_cross_version_overlap_detected(self) -> None:
        train = [msg(f"formula {i}") for i in range(10)]
        evals = [msg("formula 3"), msg("  FORMULA   4 "), msg("new item")]
        r = A.split_overlap(train, evals, "v3_validation")
        self.assertEqual(r["status"], "FAIL")
        self.assertEqual(r["indices"], [0, 1])

    def test_benchmark_embedded_in_train_needs_containment(self) -> None:
        bench = [{"scenario": "A mutation is requested but the governing policy cannot be loaded."}]
        train = [msg("Preamble. Case: a mutation is requested but the governing policy cannot be loaded. Decide.")]
        self.assertEqual(A.split_overlap(train, bench, "bench")["status"], "PASS")
        self.assertEqual(A.split_overlap(train, bench, "bench", mode="contains")["status"], "FAIL")


class ReceiptHashTests(unittest.TestCase):
    def test_undeclared_canonicalization_is_unknown(self) -> None:
        rows = [{"text": "a"}, {"text": "b"}]
        raw = json.dumps(rows, indent=1).encode()
        rec = {"data_sha256": hashlib.sha256(json.dumps(rows).encode()).hexdigest()}
        r = A.receipt_hash(raw, rec)
        self.assertEqual(r["status"], "UNKNOWN")
        self.assertEqual(r["matched"], ["python-json-dumps-default"])

    def test_declared_pass_and_tamper_fail(self) -> None:
        raw = json.dumps([{"text": "a"}]).encode()
        rec = {"data_sha256": hashlib.sha256(raw).hexdigest(), "hash_canonicalization": "raw-bytes"}
        self.assertEqual(A.receipt_hash(raw, rec)["status"], "PASS")
        self.assertEqual(A.receipt_hash(json.dumps([{"text": "b"}]).encode(), rec)["status"], "FAIL")


class LicenseAndTermsTests(unittest.TestCase):
    def test_nvidia_derivative_relabelled_permissive_fails(self) -> None:
        self.assertEqual(A.license_inheritance("apache-2.0", "other", "nvidia-open-model-license", False)["status"], "FAIL")
        self.assertEqual(A.license_inheritance("other", "other", "nvidia-open-model-license", True)["status"], "PASS")

    def test_permissive_base_ok(self) -> None:
        self.assertEqual(A.license_inheritance("apache-2.0", "apache-2.0", None, False)["status"], "PASS")

    def test_public_no_redistribution_source_fails(self) -> None:
        self.assertEqual(A.source_terms("Source: Coinbase Exchange public API", public=True)["status"], "FAIL")
        self.assertEqual(A.source_terms("Source: Coinbase Exchange public API", public=False)["status"], "PASS_PRIVATE_ONLY")


class AdmitTests(unittest.TestCase):
    def test_fail_closed(self) -> None:
        self.assertEqual(A.admit([{"status": "PASS"}, {"status": "UNKNOWN"}]), "HOLD")
        self.assertEqual(A.admit([{"status": "PASS"}, {"status": "FAIL"}]), "BLOCKED")
        self.assertEqual(A.admit([{"status": "PASS"}]), "ADMIT_CANDIDATE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
