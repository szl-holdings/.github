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

    def test_source_contains_no_clone_creation_or_publication_path(self) -> None:
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
            "Retain four public",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("select-newest-a11oy-source", source)
        self.assertIn("retire-a11oy-clone", source)
        self.assertIn("delete_repo(", source)

    def test_timestamp_ordering(self) -> None:
        older = single._parse_modified("2026-07-22T01:00:00Z")
        newer = single._parse_modified("2026-07-22T02:00:00+00:00")
        self.assertGreater(newer, older)
        self.assertEqual(single._parse_modified("not-a-time"), 0.0)

    def test_workflow_is_single_canonical_space_only(self) -> None:
        workflow = (
            SCRIPT_DIR.parent / "workflows" / "hf-estate-upgrade.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("sole governed A11oy Space", workflow)
        self.assertIn("hf_estate_canonicalize.py", workflow)
        self.assertNotIn("Retain four public A11oy command centers", workflow)
        self.assertNotIn("managed_clone_ids", workflow)
        self.assertNotIn("create four", workflow.lower())

    def test_no_secondary_hf_or_clone_restoration_lane(self) -> None:
        workflows = SCRIPT_DIR.parent / "workflows"
        self.assertFalse((workflows / "estate-finalization.yml").exists())
        self.assertFalse((workflows / "restore-public-a11oy-clones.yml").exists())
        rendered = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(workflows.glob("*.yml"))
        )
        for forbidden in (
            "Restore four public A11oy command centers",
            "fix/restore-four-public-a11oy-command-centers",
            "RESTORE_REVISION: c2549d77d900ad3df86794b3e8b2098ad908cf97",
        ):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
