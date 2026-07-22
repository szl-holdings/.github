#!/usr/bin/env python3
from __future__ import annotations

import importlib
import pathlib
import sys
import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import Mock

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

v2 = importlib.import_module("hf_estate_command_centers_v2")


@dataclass
class InventoryObject:
    id: str
    sha: str = "a" * 40
    private: bool = False
    size: int = 0
    total_files: int = 0


class FakeApi:
    def __init__(self) -> None:
        self.created_repo_kwargs: dict[str, object] | None = None
        self.repo_exists_result = True
        self.collection_items: list[SimpleNamespace] = []
        self.collection_slugs = ["SZLHOLDINGS/estate-collection"]
        self.bucket_ids = ["SZLHOLDINGS/estate-bucket"]

    def list_models(self, **kwargs):
        return [InventoryObject("SZLHOLDINGS/model")]

    def list_datasets(self, **kwargs):
        return [InventoryObject("SZLHOLDINGS/dataset")]

    def list_spaces(self, **kwargs):
        return [InventoryObject("SZLHOLDINGS/space")]

    def list_collections(self, **kwargs):
        return [
            SimpleNamespace(
                id=slug,
                slug=slug,
                title="Estate",
                private=False,
            )
            for slug in self.collection_slugs
        ]

    def list_buckets(self, **kwargs):
        return [
            InventoryObject(
                bucket_id,
                private=True,
                size=17,
                total_files=2,
            )
            for bucket_id in self.bucket_ids
        ]

    def create_repo(self, **kwargs):
        self.created_repo_kwargs = kwargs

    def repo_exists(self, repo_id, repo_type=None):
        return self.repo_exists_result

    def get_collection(self, slug):
        return SimpleNamespace(
            items=list(self.collection_items),
            private=False,
            theme="blue",
        )

    def bucket_info(self, bucket_id):
        return InventoryObject(
            bucket_id,
            private=True,
            size=17,
            total_files=2,
        )

    def list_bucket_tree(self, bucket_id, recursive=False):
        return iter(
            [
                SimpleNamespace(path="README.md"),
                SimpleNamespace(path="data/part-000.parquet"),
            ]
        )

    def paper_info(self, paper_id):
        return SimpleNamespace(id=paper_id)


def new_upgrade(api: FakeApi, *, publish: bool = False):
    upgrade = object.__new__(v2.CommandCenterEstateUpgradeV2)
    upgrade.api = api
    upgrade.publish = publish
    upgrade.inventory = {}
    upgrade.actions = []
    upgrade.collections = {}
    upgrade.http = Mock()
    upgrade.generation = "b" * 40
    return upgrade


class OfficialApiEstateTests(unittest.TestCase):
    def test_inventory_uses_supported_methods_and_kernel_fallback(self) -> None:
        api = FakeApi()
        upgrade = new_upgrade(api)
        upgrade._paginate = Mock(
            return_value=[{"id": "SZLHOLDINGS/kernel", "sha": "c" * 40}]
        )

        inventory = upgrade.collect_inventory()

        self.assertEqual(set(inventory), {
            "models",
            "datasets",
            "spaces",
            "kernels",
            "collections",
            "buckets",
        })
        self.assertEqual(inventory["models"][0]["id"], "SZLHOLDINGS/model")
        self.assertEqual(inventory["collections"][0]["id"], api.collection_slugs[0])
        self.assertEqual(inventory["buckets"][0]["id"], api.bucket_ids[0])
        upgrade._paginate.assert_called_once()
        self.assertTrue(all(action.status != "error" for action in upgrade.actions))

    def test_clone_creation_uses_no_custom_sleep_time(self) -> None:
        api = FakeApi()
        upgrade = new_upgrade(api, publish=True)

        upgrade._create_missing_clone("SZLHOLDINGS/a11oy-clone-1")

        self.assertIsNotNone(api.created_repo_kwargs)
        assert api.created_repo_kwargs is not None
        self.assertEqual(api.created_repo_kwargs["space_hardware"], "cpu-basic")
        self.assertNotIn("space_sleep_time", api.created_repo_kwargs)

    def test_every_collection_item_type_is_read_back(self) -> None:
        api = FakeApi()
        api.collection_items = [
            SimpleNamespace(item_type="model", item_id="SZLHOLDINGS/model"),
            SimpleNamespace(item_type="dataset", item_id="SZLHOLDINGS/dataset"),
            SimpleNamespace(item_type="space", item_id="SZLHOLDINGS/space"),
            SimpleNamespace(item_type="bucket", item_id=api.bucket_ids[0]),
            SimpleNamespace(
                item_type="collection",
                item_id=api.collection_slugs[0],
            ),
            SimpleNamespace(item_type="paper", item_id="2601.15621"),
        ]
        upgrade = new_upgrade(api)
        upgrade.inventory["collections"] = [
            {
                "id": api.collection_slugs[0],
                "slug": api.collection_slugs[0],
                "title": "Estate",
            }
        ]

        upgrade.validate_collections()

        snapshot = upgrade.collection_validation[api.collection_slugs[0]]
        self.assertEqual(snapshot["total_items"], 6)
        self.assertEqual(snapshot["resolved_items"], 6)
        self.assertEqual(snapshot["unresolved_items"], [])
        self.assertTrue(all(action.status != "error" for action in upgrade.actions))

    def test_unresolved_collection_item_fails_closed(self) -> None:
        api = FakeApi()
        api.repo_exists_result = False
        api.collection_items = [
            SimpleNamespace(item_type="model", item_id="SZLHOLDINGS/missing")
        ]
        upgrade = new_upgrade(api)
        upgrade.inventory["collections"] = [
            {
                "id": api.collection_slugs[0],
                "slug": api.collection_slugs[0],
                "title": "Estate",
            }
        ]

        upgrade.validate_collections()

        self.assertTrue(any(action.status == "error" for action in upgrade.actions))
        self.assertTrue(
            upgrade.collection_validation[api.collection_slugs[0]][
                "unresolved_items"
            ]
        )

    def test_bucket_contract_reads_metadata_and_tree(self) -> None:
        api = FakeApi()
        upgrade = new_upgrade(api)
        upgrade.inventory["buckets"] = [{"id": api.bucket_ids[0]}]

        upgrade.validate_buckets()

        self.assertEqual(
            upgrade.bucket_snapshots[api.bucket_ids[0]],
            {
                "private": True,
                "size": 17,
                "total_files": 2,
                "sample_entries": 2,
            },
        )
        self.assertTrue(all(action.status != "error" for action in upgrade.actions))

    def test_workflow_executes_v2_publisher(self) -> None:
        workflow = (
            SCRIPT_DIR.parent / "workflows" / "hf-estate-upgrade.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("hf_estate_command_centers_v2.py", workflow)
        self.assertIn("test_hf_estate_command_centers_v2.py", workflow)
        self.assertIn("HF_ORG_TOKEN1", workflow)
        self.assertIn('"huggingface_hub>=1.10,<2"', workflow)


if __name__ == "__main__":
    unittest.main()
