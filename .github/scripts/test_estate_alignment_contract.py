#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = Path(__file__).with_name("estate_alignment_contract.py")
SPEC = importlib.util.spec_from_file_location("estate_alignment_contract", MODULE_PATH)
assert SPEC and SPEC.loader
alignment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(alignment)


class EstateAlignmentContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = alignment.load_json(
            ROOT / "docs" / "ESTATE_ALIGNMENT_CONTRACT_V1.json"
        )

    def test_current_contract_and_documents_are_aligned(self) -> None:
        self.assertEqual(alignment.validate_contract(self.contract), [])
        self.assertEqual(alignment.validate_documents(ROOT, self.contract), [])

    def test_exact_taxonomy_is_not_inferred_from_counts(self) -> None:
        candidate = copy.deepcopy(self.contract)
        candidate["taxonomy"]["commercial_flagships"][0]["slug"] = "immune"
        failures = alignment.validate_contract(candidate)
        self.assertTrue(any("commercial_flagships" in row for row in failures))
        self.assertTrue(any("folded capability" in row for row in failures))

    def test_space_inventory_rejects_missing_or_unclassified_surfaces(self) -> None:
        candidate = copy.deepcopy(self.contract)
        candidate["huggingface_inventory_snapshot"]["portfolio_spaces"].pop()
        failures = alignment.validate_contract(candidate)
        self.assertTrue(any("portfolio Space" in row for row in failures))

        candidate = copy.deepcopy(self.contract)
        candidate["huggingface_inventory_snapshot"]["portfolio_spaces"][0][
            "class"
        ] = "product_because_public"
        failures = alignment.validate_contract(candidate)
        self.assertIn("unknown portfolio Space class", failures)

    def test_strict_loader_rejects_duplicate_keys_and_nonfinite_numbers(self) -> None:
        with self.assertRaisesRegex(alignment.AlignmentError, "duplicate JSON key"):
            alignment.load_json_bytes(b'{"a":1,"a":2}', label="duplicate")
        with self.assertRaisesRegex(alignment.AlignmentError, "non-finite"):
            alignment.load_json_bytes(b'{"a":NaN}', label="nonfinite")

    def test_product_contract_comparison_rejects_source_drift(self) -> None:
        product = {
            "estate": {
                "product_surface": "https://a-11-oy.com",
                "proof_surface": "https://a11oy.net",
                "artifact_organization": "SZLHOLDINGS",
            },
            "authorities": {
                "lean_kernel": {"locked_proven_ids": alignment.LOCKED_EIGHT}
            },
            "public_product_taxonomy": {
                "public_domain_bodies": alignment.EXPECTED_BODIES,
                "internal_engines": alignment.EXPECTED_ENGINES,
                "folded_into_killinchu": list(alignment.EXPECTED_FOLDS),
            },
            "verticals": [
                {
                    "slug": row["slug"],
                    "canonical_source": row["source"],
                }
                for row in self.contract["taxonomy"]["public_domain_bodies"]
            ],
        }
        self.assertEqual(
            alignment.validate_product_contract(product, self.contract), []
        )
        product["verticals"][-1]["canonical_source"] = "szl-holdings/lyte-lattice"
        failures = alignment.validate_product_contract(product, self.contract)
        self.assertTrue(any("canonical source drift for lyte" in row for row in failures))

    def test_receipt_contains_no_write_authority(self) -> None:
        receipt = alignment.build_receipt(ROOT, live=False)
        self.assertEqual(receipt["state"], "ALIGNED")
        self.assertFalse(receipt["authority"]["provider_writes"])
        self.assertFalse(receipt["authority"]["secret_values_recorded"])
        self.assertFalse(receipt["authority"]["public_effectors_enabled"])
        self.assertEqual(len(receipt["receipt_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
