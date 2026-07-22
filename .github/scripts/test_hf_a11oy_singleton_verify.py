#!/usr/bin/env python3
from __future__ import annotations

import importlib
import pathlib
import sys
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

verifier = importlib.import_module("hf_a11oy_singleton_verify")


class A11oySingletonVerifierContractTests(unittest.TestCase):
    def test_exact_absence_set_and_one_canonical_space(self) -> None:
        self.assertEqual(verifier.CANONICAL_SPACE, "SZLHOLDINGS/a11oy")
        self.assertEqual(
            verifier.HISTORICAL_CLONE_IDS,
            (
                "SZLHOLDINGS/a11oy-clone-1",
                "SZLHOLDINGS/a11oy-clone-2",
                "SZLHOLDINGS/a11oy-clone-3",
                "SZLHOLDINGS/a11oy-clone-4",
            ),
        )

    def test_verifier_has_no_clone_creation_adoption_or_deletion_path(self) -> None:
        source = (SCRIPT_DIR / "hf_a11oy_singleton_verify.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "duplicate_repo(",
            "duplicate_space(",
            "create_repo(",
            "CommitOperationCopy",
            "canonical-content-adoption",
            "select-newest-a11oy-source",
            "delete_repo(",
            "update_repo_settings",
            "clone-refresh",
            "last_modified_epoch",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("clone-absence", source)
        self.assertIn("canonical-route", source)
        self.assertIn("collection-remove-stale-clone", source)

    def test_critical_routes_bind_build_identity_and_brain(self) -> None:
        paths = [path for path, _ in verifier.IMPORTANT_ROUTES]
        self.assertIn("/api/build-info", paths)
        self.assertIn("/api/a11oy/v1/brain/capabilities", paths)
        self.assertIn("/api/a11oy/readyz", paths)
        self.assertIn("/holographic", paths)
        self.assertEqual(len(paths), len(set(paths)))

    def test_recursive_revision_match(self) -> None:
        expected = "a" * 40
        payload = {"build": {"revision": expected}, "other": [1, 2]}
        self.assertTrue(verifier.contains_value(payload, expected))
        self.assertFalse(verifier.contains_value(payload, "b" * 40))

    def test_workflow_invokes_only_post_migration_verifier(self) -> None:
        workflow = (
            SCRIPT_DIR.parent / "workflows" / "hf-estate-upgrade.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("hf_a11oy_singleton_verify.py", workflow)
        self.assertIn("Verify one canonical A11oy Space", workflow)
        self.assertIn("hf_module_drift_check.py", workflow)
        self.assertNotIn("hf_estate_canonicalize.py", workflow)
        self.assertNotIn("select newest", workflow.lower())
        self.assertNotIn("delete all clones", workflow.lower())
        self.assertNotIn("duplicate_repo(", workflow)

    def test_historical_clone_publishers_are_removed(self) -> None:
        self.assertFalse((SCRIPT_DIR / "hf_estate_upgrade.py").exists())
        self.assertFalse((SCRIPT_DIR / "hf_estate_canonicalize.py").exists())
        self.assertFalse((SCRIPT_DIR / "test_hf_estate_canonicalize.py").exists())


if __name__ == "__main__":
    unittest.main()
