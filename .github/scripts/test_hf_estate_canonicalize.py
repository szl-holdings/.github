#!/usr/bin/env python3
from __future__ import annotations

import importlib
import pathlib
import sys
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

estate = importlib.import_module("hf_estate_canonicalize")


class SingleA11oyEstateContractTests(unittest.TestCase):
    def test_only_canonical_space_is_retained(self) -> None:
        self.assertEqual(
            estate.RETIRED_CLONE_IDS,
            tuple(
                f"SZLHOLDINGS/a11oy-clone-{index}"
                for index in range(1, 5)
            ),
        )
        self.assertEqual(
            estate.KEEP_SPACE_IDS,
            frozenset({"SZLHOLDINGS/a11oy"}),
        )
        self.assertEqual(estate.legacy.CLONE_IDS, [])

    def test_no_clone_creation_path_remains(self) -> None:
        source = (SCRIPT_DIR / "hf_estate_canonicalize.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("duplicate_repo(", source)
        self.assertNotIn("create_repo(", source)
        self.assertNotIn("update_repo_settings", source)
        self.assertIn("delete_repo(", source)
        self.assertIn("delete-retired-clone", source)

    def test_legacy_clone_factory_is_retired(self) -> None:
        source = (SCRIPT_DIR / "hf_estate_upgrade.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("CLONE_IDS: list[str] = []", source)
        self.assertNotIn("a11oy-clone-", source)
        self.assertIn("canonical-only; no clones created", source)

    def test_workflow_is_canonical_only(self) -> None:
        workflow = (
            SCRIPT_DIR.parent / "workflows" / "hf-estate-upgrade.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("Keep one canonical A11oy Space", workflow)
        self.assertNotIn("Retain four", workflow)
        self.assertNotIn("a11oy-clone-1", workflow)

    def test_runtime_stage_normalization(self) -> None:
        class Runtime:
            stage = "SpaceStage.RUNNING"

        class Info:
            runtime = Runtime()

        self.assertEqual(estate._runtime_stage(Info()), "RUNNING")


if __name__ == "__main__":
    unittest.main()
