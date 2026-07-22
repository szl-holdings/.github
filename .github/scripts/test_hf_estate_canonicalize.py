#!/usr/bin/env python3
from __future__ import annotations

import importlib
import pathlib
import sys
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

single = importlib.import_module("hf_estate_canonicalize")


class SingleA11oyEstateContractTests(unittest.TestCase):
    def test_exact_historical_clone_set(self) -> None:
        self.assertEqual(
            single.HISTORICAL_CLONE_IDS,
            (
                "SZLHOLDINGS/a11oy-clone-1",
                "SZLHOLDINGS/a11oy-clone-2",
                "SZLHOLDINGS/a11oy-clone-3",
                "SZLHOLDINGS/a11oy-clone-4",
            ),
        )
        self.assertEqual(
            single.CANDIDATE_IDS,
            ("SZLHOLDINGS/a11oy", *single.HISTORICAL_CLONE_IDS),
        )

    def test_inherited_clone_creator_is_disabled(self) -> None:
        self.assertEqual(single.legacy.CLONE_IDS, [])

    def test_active_source_has_no_clone_creation_or_restoration_path(self) -> None:
        source = (SCRIPT_DIR / "hf_estate_canonicalize.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "duplicate_repo(",
            "duplicate_space(",
            "_create_missing_clone",
            "update_repo_settings",
            "clone-visibility",
            "clone-refresh",
            "MANAGED_CLONE_IDS",
            "KEEP_SPACE_IDS",
            "Retain four public",
            "restore-four-public-a11oy",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("select-newest-a11oy-source", source)
        self.assertIn("retire-a11oy-clone", source)
        self.assertIn("delete_repo(", source)

    def test_timestamp_ordering(self) -> None:
        older = single._modified_epoch("2026-07-22T01:00:00Z")
        newer = single._modified_epoch("2026-07-22T02:00:00+00:00")
        self.assertGreater(newer, older)
        self.assertEqual(single._modified_epoch("not-a-time"), 0.0)

    def test_workflow_has_one_single_space_publisher(self) -> None:
        workflow_dir = SCRIPT_DIR.parent / "workflows"
        workflow = (workflow_dir / "hf-estate-upgrade.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("sole governed A11oy Space", workflow)
        self.assertIn("hf_estate_canonicalize.py", workflow)
        self.assertNotIn("Retain four public A11oy command centers", workflow)
        self.assertNotIn("managed_clone_ids", workflow)
        self.assertNotIn("restore-public-a11oy-clones", workflow)

        publisher_hits = []
        for path in workflow_dir.glob("*.yml"):
            text = path.read_text(encoding="utf-8")
            if "hf_estate_canonicalize.py" in text:
                publisher_hits.append(path.name)
            self.assertNotIn(
                "python .github/scripts/hf_estate_upgrade.py",
                text,
                msg=f"base clone-capable publisher invoked directly in {path.name}",
            )
            self.assertNotIn(
                "restore-four-public-a11oy-command-centers",
                text,
                msg=f"stale restoration branch in {path.name}",
            )
            self.assertNotIn(
                "c2549d77d900ad3df86794b3e8b2098ad908cf97",
                text,
                msg=f"stale four-clone restore revision in {path.name}",
            )
        self.assertEqual(publisher_hits, ["hf-estate-upgrade.yml"])

    def test_no_clone_restore_workflow_exists(self) -> None:
        workflow_dir = SCRIPT_DIR.parent / "workflows"
        forbidden = (
            "restore-public-a11oy-clones.yml",
            "estate-finalization.yml",
        )
        for name in forbidden:
            self.assertFalse((workflow_dir / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
