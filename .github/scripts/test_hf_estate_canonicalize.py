#!/usr/bin/env python3
from __future__ import annotations

import importlib
import pathlib
import sys
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

canonical = importlib.import_module("hf_estate_canonicalize")


class CanonicalEstateContractTests(unittest.TestCase):
    def test_exact_retired_clone_allowlist(self) -> None:
        self.assertEqual(
            canonical.RETIRED_CLONE_IDS,
            (
                "SZLHOLDINGS/a11oy-clone-1",
                "SZLHOLDINGS/a11oy-clone-2",
                "SZLHOLDINGS/a11oy-clone-3",
                "SZLHOLDINGS/a11oy-clone-4",
            ),
        )

    def test_inherited_clone_additions_are_disabled(self) -> None:
        self.assertEqual(canonical.legacy.CLONE_IDS, [])

    def test_wrapper_contains_no_clone_creation_api(self) -> None:
        source = (SCRIPT_DIR / "hf_estate_canonicalize.py").read_text(encoding="utf-8")
        self.assertNotIn("duplicate_repo(", source)
        self.assertNotIn("duplicate_space(", source)
        self.assertIn("delete_repo(", source)
        self.assertIn("canonical-space-preflight", source)

    def test_workflow_executes_canonical_reconciler_only(self) -> None:
        workflow = (
            SCRIPT_DIR.parent / "workflows" / "hf-estate-upgrade.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("hf_estate_canonicalize.py", workflow)
        self.assertNotIn("python .github/scripts/hf_estate_upgrade.py", workflow)

    def test_runtime_stage_normalization(self) -> None:
        class Runtime:
            stage = "SpaceStage.RUNNING"

        class Info:
            runtime = Runtime()

        self.assertEqual(canonical._runtime_stage(Info()), "RUNNING")


if __name__ == "__main__":
    unittest.main()
