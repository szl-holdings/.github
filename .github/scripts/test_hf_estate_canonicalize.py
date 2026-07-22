#!/usr/bin/env python3
from __future__ import annotations

import importlib
import pathlib
import sys
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

command_centers = importlib.import_module("hf_estate_canonicalize")


class CommandCenterEstateContractTests(unittest.TestCase):
    def test_exact_public_clone_keep_set(self) -> None:
        self.assertEqual(
            command_centers.MANAGED_CLONE_IDS,
            (
                "SZLHOLDINGS/a11oy-clone-1",
                "SZLHOLDINGS/a11oy-clone-2",
                "SZLHOLDINGS/a11oy-clone-3",
                "SZLHOLDINGS/a11oy-clone-4",
            ),
        )
        self.assertEqual(
            command_centers.KEEP_SPACE_IDS,
            frozenset(
                {
                    "SZLHOLDINGS/a11oy",
                    "SZLHOLDINGS/a11oy-clone-1",
                    "SZLHOLDINGS/a11oy-clone-2",
                    "SZLHOLDINGS/a11oy-clone-3",
                    "SZLHOLDINGS/a11oy-clone-4",
                }
            ),
        )

    def test_inherited_collection_builder_keeps_clones(self) -> None:
        self.assertEqual(
            command_centers.legacy.CLONE_IDS,
            list(command_centers.MANAGED_CLONE_IDS),
        )

    def test_quota_safe_clone_path(self) -> None:
        source = (SCRIPT_DIR / "hf_estate_canonicalize.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("duplicate_repo(", source)
        self.assertNotIn("duplicate_space(", source)
        self.assertIn("create_repo(", source)
        self.assertIn("update_repo_settings", source)
        self.assertIn("delete-surplus-duplicate", source)

    def test_narrow_name_match_does_not_select_unrelated_spaces(self) -> None:
        self.assertIsNotNone(
            command_centers.DUPLICATE_NAME.fullmatch(
                "SZLHOLDINGS/a11oy-copy-99"
            )
        )
        self.assertIsNotNone(
            command_centers.DUPLICATE_NAME.fullmatch(
                "SZLHOLDINGS/a11oy-duplicate-2"
            )
        )
        self.assertIsNone(
            command_centers.DUPLICATE_NAME.fullmatch(
                "SZLHOLDINGS/a11oy-research-lab"
            )
        )
        self.assertIn(
            "SZLHOLDINGS/a11oy-clone-1",
            command_centers.KEEP_SPACE_IDS,
        )

    def test_workflow_executes_command_center_reconciler(self) -> None:
        workflow = (
            SCRIPT_DIR.parent / "workflows" / "hf-estate-upgrade.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("hf_estate_canonicalize.py", workflow)
        self.assertIn("Retain four public A11oy command centers", workflow)
        self.assertNotIn("retired_clone_ids", workflow)

    def test_runtime_stage_normalization(self) -> None:
        class Runtime:
            stage = "SpaceStage.RUNNING"

        class Info:
            runtime = Runtime()

        self.assertEqual(command_centers._runtime_stage(Info()), "RUNNING")


if __name__ == "__main__":
    unittest.main()
