#!/usr/bin/env python3
from __future__ import annotations

import importlib
import inspect
import pathlib
import sys
import unittest
from dataclasses import dataclass

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

inventory = importlib.import_module("hf_official_estate_inventory")


@dataclass
class Example:
    id: str
    sha: str = "a" * 40
    private: bool = False
    owner: str | None = None


class SignatureApi:
    def list_models(self, author=None, full=None, limit=None):
        return [Example("SZLHOLDINGS/model-a"), Example("other/model")]

    def list_buckets(self, namespace=None, limit=None):
        return [Example("SZLHOLDINGS/bucket-a")]


class ResolveApi:
    def repo_exists(self, repo_id, repo_type=None):
        return repo_id == "SZLHOLDINGS/present"


class OfficialEstateInventoryContractTests(unittest.TestCase):
    def test_exact_singleton_policy(self) -> None:
        self.assertEqual(inventory.CANONICAL_SPACE, "SZLHOLDINGS/a11oy")
        self.assertEqual(
            inventory.HISTORICAL_CLONE_IDS,
            (
                "SZLHOLDINGS/a11oy-clone-1",
                "SZLHOLDINGS/a11oy-clone-2",
                "SZLHOLDINGS/a11oy-clone-3",
                "SZLHOLDINGS/a11oy-clone-4",
            ),
        )

    def test_mapping_normalizes_dataclass(self) -> None:
        observed = inventory._mapping(Example("SZLHOLDINGS/example", "d" * 40))
        self.assertEqual(observed["id"], "SZLHOLDINGS/example")
        self.assertEqual(observed["sha"], "d" * 40)
        self.assertFalse(observed["private"])

    def test_supported_invocation_filters_signature(self) -> None:
        values = inventory._invoke_supported(
            SignatureApi(),
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

    def test_collection_resolution_detects_missing_supported_repo(self) -> None:
        verifier = object.__new__(inventory.OfficialEstateInventory)
        verifier.api = ResolveApi()
        verifier.collection_resolution_errors = []
        verifier.clone_collection_references = []
        missing = verifier._resolve_collection_item(
            "SZLHOLDINGS/example-collection",
            {"item_id": "SZLHOLDINGS/missing", "item_type": "model"},
        )
        present = verifier._resolve_collection_item(
            "SZLHOLDINGS/example-collection",
            {"item_id": "SZLHOLDINGS/present", "item_type": "dataset"},
        )
        self.assertEqual(missing["resolution"], "MISSING")
        self.assertEqual(present["resolution"], "RESOLVED")
        self.assertEqual(len(verifier.collection_resolution_errors), 1)

    def test_source_uses_supported_inventory_apis_only(self) -> None:
        source = inspect.getsource(inventory)
        self.assertNotIn("/api/collections", source)
        self.assertNotIn("/api/buckets", source)
        self.assertIn('"list_collections"', source)
        self.assertIn('"get_collection"', source)
        self.assertIn('"list_buckets"', source)
        self.assertIn('"bucket_info"', source)

    def test_source_has_no_clone_or_asset_mutation_path(self) -> None:
        source = (HERE / "hf_official_estate_inventory.py").read_text(encoding="utf-8")
        for forbidden in (
            "duplicate_repo(",
            "duplicate_space(",
            "create_repo(",
            "delete_repo(",
            "update_repo_settings(",
            "CommitOperationCopy",
            "select-newest-a11oy-source",
            "canonical-content-adoption",
            "clone-refresh",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("estate/official-inventory/latest.json", source)

    def test_report_exposes_downloads_and_likes_for_showcase(self) -> None:
        view = inventory.OfficialEstateInventory._public_asset_view(
            {"id": "SZLHOLDINGS/model", "downloads": 42, "likes": 7}
        )
        self.assertEqual(view["downloads"], 42)
        self.assertEqual(view["likes"], 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
