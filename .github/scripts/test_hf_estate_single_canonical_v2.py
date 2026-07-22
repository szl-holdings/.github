#!/usr/bin/env python3
from __future__ import annotations

import importlib
import pathlib
import sys
import unittest
from dataclasses import dataclass
from unittest.mock import Mock

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

single = importlib.import_module("hf_estate_canonicalize")
v2 = importlib.import_module("hf_estate_single_canonical_v2")


@dataclass
class InventoryObject:
    id: str
    sha: str = "a" * 40
    private: bool = False
    size: int = 0
    total_files: int = 0


class FakeApi:
    def list_models(self, **kwargs):
        return [InventoryObject("SZLHOLDINGS/model")]

    def list_datasets(self, **kwargs):
        return [InventoryObject("SZLHOLDINGS/dataset")]

    def list_spaces(self, **kwargs):
        return [InventoryObject("SZLHOLDINGS/a11oy")]

    def list_collections(self, **kwargs):
        return []

    def list_buckets(self, **kwargs):
        return []


def new_upgrade(api: FakeApi):
    upgrade = object.__new__(v2.SingleCanonicalEstateUpgradeV2)
    upgrade.api = api
    upgrade.publish = False
    upgrade.inventory = {}
    upgrade.actions = []
    upgrade.collections = {}
    upgrade.http = Mock()
    upgrade.generation = "b" * 40
    return upgrade


def snapshot(
    repo_id: str,
    *,
    content_epoch: float,
    last_epoch: float,
    digest: str,
    valid: bool = True,
) -> dict:
    return {
        "repo_id": repo_id,
        "valid": valid,
        "content_modified_epoch": content_epoch,
        "last_modified_epoch": last_epoch,
        "tree_digest": digest,
        "content_commit_sha": "c" * 40,
        "sha": "d" * 40,
    }


class SingleCanonicalV2Tests(unittest.TestCase):
    def test_clone_creator_is_disabled_in_both_layers(self) -> None:
        self.assertEqual(single.legacy.CLONE_IDS, [])
        self.assertEqual(v2.legacy.CLONE_IDS, [])
        self.assertEqual(
            single.HISTORICAL_CLONE_IDS,
            (
                "SZLHOLDINGS/a11oy-clone-1",
                "SZLHOLDINGS/a11oy-clone-2",
                "SZLHOLDINGS/a11oy-clone-3",
                "SZLHOLDINGS/a11oy-clone-4",
            ),
        )

    def test_identical_trees_prefer_canonical(self) -> None:
        snapshots = {
            "SZLHOLDINGS/a11oy": snapshot(
                "SZLHOLDINGS/a11oy",
                content_epoch=1,
                last_epoch=1,
                digest="same",
            ),
            "SZLHOLDINGS/a11oy-clone-1": snapshot(
                "SZLHOLDINGS/a11oy-clone-1",
                content_epoch=2,
                last_epoch=2,
                digest="same",
            ),
        }
        selected = v2.choose_newest_candidate(snapshots)
        self.assertEqual(selected["repo_id"], "SZLHOLDINGS/a11oy")

    def test_newer_divergent_clone_is_selected_for_adoption(self) -> None:
        snapshots = {
            "SZLHOLDINGS/a11oy": snapshot(
                "SZLHOLDINGS/a11oy",
                content_epoch=1,
                last_epoch=1,
                digest="canonical",
            ),
            "SZLHOLDINGS/a11oy-clone-1": snapshot(
                "SZLHOLDINGS/a11oy-clone-1",
                content_epoch=2,
                last_epoch=2,
                digest="newer",
            ),
        }
        selected = v2.choose_newest_candidate(snapshots)
        self.assertEqual(selected["repo_id"], "SZLHOLDINGS/a11oy-clone-1")

    def test_equally_recent_divergent_trees_fail_closed(self) -> None:
        snapshots = {
            "SZLHOLDINGS/a11oy": snapshot(
                "SZLHOLDINGS/a11oy",
                content_epoch=2,
                last_epoch=2,
                digest="canonical",
            ),
            "SZLHOLDINGS/a11oy-clone-1": snapshot(
                "SZLHOLDINGS/a11oy-clone-1",
                content_epoch=2,
                last_epoch=2,
                digest="different",
            ),
        }
        with self.assertRaisesRegex(RuntimeError, "Equally recent"):
            v2.choose_newest_candidate(snapshots)

    def test_route_contract_requires_json_object_and_keys(self) -> None:
        ok, reason = v2.evaluate_route_response(
            200,
            "application/json; charset=utf-8",
            {"status": "ok"},
            ("status",),
        )
        self.assertTrue(ok, reason)

        ok, reason = v2.evaluate_route_response(
            200,
            "text/html",
            {"status": "ok"},
            ("status",),
        )
        self.assertFalse(ok)
        self.assertIn("non-JSON", reason)

        ok, reason = v2.evaluate_route_response(
            200,
            "application/json",
            {},
            ("status",),
        )
        self.assertFalse(ok)
        self.assertIn("missing keys", reason)

    def test_supported_api_inventory_with_kernel_fallback(self) -> None:
        upgrade = new_upgrade(FakeApi())
        upgrade._paginate = Mock(
            return_value=[{"id": "SZLHOLDINGS/kernel", "sha": "e" * 40}]
        )

        inventory = upgrade.collect_inventory()

        self.assertEqual(
            set(inventory),
            {"models", "datasets", "spaces", "kernels", "collections", "buckets"},
        )
        self.assertEqual(inventory["models"][0]["id"], "SZLHOLDINGS/model")
        self.assertEqual(inventory["spaces"][0]["id"], "SZLHOLDINGS/a11oy")
        upgrade._paginate.assert_called_once()
        self.assertTrue(all(action.status != "error" for action in upgrade.actions))

    def test_active_sources_contain_no_clone_creation_path(self) -> None:
        for path in (
            SCRIPT_DIR / "hf_estate_canonicalize.py",
            SCRIPT_DIR / "hf_estate_single_canonical_v2.py",
        ):
            source = path.read_text(encoding="utf-8")
            for forbidden in (
                "duplicate_repo(",
                "duplicate_space(",
                "def _create_missing_clone",
                "update_repo_settings(",
                '"clone-visibility"',
                '"clone-refresh"',
                "Retain four public",
            ):
                self.assertNotIn(forbidden, source, f"{forbidden} found in {path}")
        self.assertIn("delete_repo(", (SCRIPT_DIR / "hf_estate_canonicalize.py").read_text())

    def test_no_workflow_can_recreate_a11oy_clones(self) -> None:
        workflow_dir = SCRIPT_DIR.parent / "workflows"
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")))
        )
        self.assertNotIn("hf_estate_command_centers_v2.py", combined)
        self.assertNotIn("Retain four public A11oy command centers", combined)
        self.assertNotIn("python .github/scripts/hf_estate_upgrade.py", combined)
        self.assertNotIn("duplicate_repo(", combined)
        active = (workflow_dir / "hf-estate-upgrade.yml").read_text(encoding="utf-8")
        self.assertIn("hf_estate_single_canonical_v2.py", active)
        self.assertIn("sole governed A11oy", active)
        self.assertIn("HF_ORG_TOKEN1", active)

    def test_only_safe_get_routes_are_probed(self) -> None:
        self.assertTrue(v2.SAFE_ROUTE_CHECKS)
        for path, required in v2.SAFE_ROUTE_CHECKS:
            self.assertTrue(path.startswith("/"))
            self.assertTrue(required)

    def test_one_time_finalizer_is_absent(self) -> None:
        self.assertFalse(
            (SCRIPT_DIR.parent / "workflows" / "estate-finalization.yml").exists()
        )


if __name__ == "__main__":
    unittest.main()
