#!/usr/bin/env python3
from __future__ import annotations

import importlib
import inspect
import pathlib
import sys
import unittest
from dataclasses import dataclass

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

inventory = importlib.import_module("hf_estate_official_inventory")


@dataclass
class Example:
    id: str
    sha: str
    private: bool = False


class Api:
    def list_models(self, author=None, full=None, limit=None):
        return [Example("SZLHOLDINGS/model-a", "a" * 40), Example("other/model", "b" * 40)]

    def list_buckets(self, namespace=None, limit=None):
        return [Example("SZLHOLDINGS/bucket-a", "c" * 40)]


class OfficialInventoryContractTests(unittest.TestCase):
    def test_active_reconciler_is_reused(self) -> None:
        self.assertTrue(issubclass(inventory.OfficialInventoryEstateUpgrade, inventory.BaseEstateUpgrade))

    def test_mapping_normalizes_dataclass(self) -> None:
        observed = inventory._mapping(Example("SZLHOLDINGS/example", "d" * 40))
        self.assertEqual(observed["id"], "SZLHOLDINGS/example")
        self.assertEqual(observed["sha"], "d" * 40)
        self.assertFalse(observed["private"])

    def test_supported_invocation_filters_signature(self) -> None:
        values = inventory._invoke_supported(
            Api(),
            "list_models",
            author="SZLHOLDINGS",
            full=True,
            limit=None,
            unsupported="must-not-pass",
        )
        self.assertEqual(len(values), 2)

    def test_org_filter_is_fail_closed(self) -> None:
        self.assertTrue(inventory._belongs_to_org({"id": "SZLHOLDINGS/a11oy"}))
        self.assertTrue(inventory._belongs_to_org({"name": "asset", "owner": "SZLHOLDINGS"}))
        self.assertFalse(inventory._belongs_to_org({"id": "other/a11oy"}))

    def test_source_contains_no_invalid_raw_inventory_endpoint(self) -> None:
        source = inspect.getsource(inventory)
        self.assertNotIn("/api/collections", source)
        self.assertNotIn("/api/buckets", source)
        self.assertIn('"list_collections"', source)
        self.assertIn('"list_buckets"', source)
        self.assertIn('os.environ.get("HF_ORG_TOKEN1")', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
