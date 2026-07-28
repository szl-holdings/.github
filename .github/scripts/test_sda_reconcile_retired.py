#!/usr/bin/env python3
"""Prevent resurrection of the completed fixed-SHA SDA reconciliation one-shot."""
# Any change to this tombstone re-runs the exact-head FORGE-9 gates and App attestation.
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
RETIRED_PATHS = (
    ".github/workflows/sda-shared-source-reconcile.yml",
    ".github/scripts/sda_shared_source_reconcile.py",
    ".github/data/sda_shared_source_reconcile.json",
)
FORBIDDEN_EXECUTABLE_MARKERS = (
    "agent/hf-space-api-route-repair-20260722",
    "agent/sda-api-contract-sync-20260722",
    "szl.sda-shared-source-reconcile/v1",
    "szl-sda-shared-source-reconcile-report",
)


class CompletedSdaReconcileRetirementTests(unittest.TestCase):
    def test_retired_paths_do_not_exist(self) -> None:
        for relative in RETIRED_PATHS:
            self.assertFalse((ROOT / relative).exists(), relative)

    def test_historical_branch_controller_markers_are_not_executable(self) -> None:
        roots = (ROOT / ".github/workflows", ROOT / ".github/scripts")
        for directory in roots:
            for path in directory.rglob("*"):
                if not path.is_file() or path == Path(__file__):
                    continue
                if path.suffix.lower() not in {".py", ".yml", ".yaml", ".json"}:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                for marker in FORBIDDEN_EXECUTABLE_MARKERS:
                    self.assertNotIn(marker, text, f"{path.relative_to(ROOT)}: {marker}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
