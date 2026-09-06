#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline lifecycle contracts for scripts/build_attic_index.py."""
from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "build_attic_index.py"
SPEC = importlib.util.spec_from_file_location("build_attic_index", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def manifest() -> dict:
    return module.load_portfolio(ROOT / "governance" / "archive-portfolio-v1.json")


def repositories(value: dict, *, restored: bool = False) -> list[dict]:
    restore = set(value["restoration_wave"]["repositories"])
    rows = [
        {
            "name": row["name"],
            "description": "",
            "isArchived": not (restored and row["name"] in restore),
            "isPrivate": False,
            "url": f"https://github.com/szl-holdings/{row['name']}",
        }
        for row in value["repositories"]
    ]
    existing = {row["name"] for row in rows}
    targets = sorted(
        {
            target
            for row in value["repositories"]
            for target in row["canonical_targets"]
        }
        - existing
    )
    rows.extend(
        {
            "name": target,
            "description": "",
            "isArchived": False,
            "isPrivate": False,
            "url": f"https://github.com/szl-holdings/{target}",
        }
        for target in targets
    )
    return rows


class PortfolioContractTests(unittest.TestCase):
    def test_manifest_has_exact_reviewed_shape(self):
        value = manifest()
        self.assertEqual(len(value["repositories"]), 34)
        counts = {
            disposition: sum(
                row["disposition"] == disposition
                for row in value["repositories"]
            )
            for disposition in ("restore", "consolidate", "historical")
        }
        self.assertEqual(
            counts,
            {"restore": 5, "consolidate": 23, "historical": 6},
        )
        self.assertEqual(
            value["restoration_wave"]["repositories"],
            [
                "docs-site",
                "szl-atelier",
                "szl-mesh",
                "szl-router",
                "uds-bundles",
            ],
        )

    def test_all_archived_state_is_reported_without_fabricated_restoration(self):
        value = manifest()
        result = module.analyse(repositories(value), value)
        self.assertEqual(len(result["pending_restore"]), 5)
        self.assertEqual(result["restored"], [])
        self.assertEqual(len(result["consolidated"]), 23)
        self.assertEqual(len(result["historical"]), 6)
        self.assertEqual(result["defects"], [])

    def test_provider_readback_moves_only_restore_rows_to_active(self):
        value = manifest()
        result = module.analyse(repositories(value, restored=True), value)
        self.assertEqual(result["pending_restore"], [])
        self.assertEqual(len(result["restored"]), 5)
        self.assertEqual(len(result["consolidated"]), 23)
        self.assertEqual(len(result["historical"]), 6)
        self.assertEqual(result["defects"], [])
        self.assertEqual(result["archived"], 29)

    def test_unclassified_archive_fails_closed(self):
        value = manifest()
        repos = repositories(value)
        repos.append(
            {
                "name": "surprise-archive",
                "description": "",
                "isArchived": True,
                "isPrivate": False,
                "url": "https://github.com/szl-holdings/surprise-archive",
            }
        )
        result = module.analyse(repos, value)
        self.assertIn(
            "UNCLASSIFIED_ARCHIVE",
            {row["code"] for row in result["defects"]},
        )

    def test_consolidation_tombstone_cannot_silently_reactivate(self):
        value = manifest()
        chosen = next(
            row["name"]
            for row in value["repositories"]
            if row["disposition"] == "consolidate"
        )
        repos = repositories(value)
        for repo in repos:
            if repo["name"] == chosen:
                repo["isArchived"] = False
        result = module.analyse(repos, value)
        self.assertIn(
            "CONSOLIDATION_TOMBSTONE_ACTIVE",
            {row["code"] for row in result["defects"]},
        )

    def test_historical_record_cannot_silently_reactivate(self):
        value = manifest()
        chosen = next(
            row["name"]
            for row in value["repositories"]
            if row["disposition"] == "historical"
        )
        repos = repositories(value)
        for repo in repos:
            if repo["name"] == chosen:
                repo["isArchived"] = False
        result = module.analyse(repos, value)
        self.assertIn(
            "HISTORICAL_RECORD_ACTIVE",
            {row["code"] for row in result["defects"]},
        )

    def test_missing_or_archived_canonical_target_is_terminal(self):
        value = manifest()
        row = next(
            item
            for item in value["repositories"]
            if item["disposition"] == "consolidate"
        )
        target = row["canonical_targets"][0]
        repos = [repo for repo in repositories(value) if repo["name"] != target]
        result = module.analyse(repos, value)
        self.assertIn(
            "CANONICAL_TARGET_MISSING",
            {item["code"] for item in result["defects"]},
        )

    def test_hugging_face_links_preserve_surface_kind(self):
        self.assertEqual(
            module._hf("SZLHOLDINGS/szl-constellation"),
            "[`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation)",
        )
        self.assertEqual(
            module._hf("SZLHOLDINGS/szl-kernels"),
            "[`SZLHOLDINGS/szl-kernels`](https://huggingface.co/SZLHOLDINGS/szl-kernels)",
        )

    def test_render_never_calls_pending_restoration_active(self):
        value = manifest()
        body = module.render(module.analyse(repositories(value), value))
        self.assertIn("PENDING_ADMIN_AUTHORITY", body)
        self.assertNotIn("RESTORED_READBACK_VERIFIED", body)
        self.assertIn("Consolidation tombstones", body)
        self.assertIn("Immutable historical evidence", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
