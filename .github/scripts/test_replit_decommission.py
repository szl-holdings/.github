#!/usr/bin/env python3
"""Lock Replit Unified Control Hub outside the active executable estate."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
DECOMMISSIONED_PATHS = (
    ".github/workflows/discover-replit-receipt-main.yml",
    ".github/scripts/discover_replit_receipt.py",
    ".github/scripts/test_discover_replit_receipt.py",
)
FORBIDDEN_EXECUTABLE_MARKERS = (
    "REPLIT_PRODUCTION_URL",
    "szl.replit-public-status/v1",
    "unified-control-hub--stephenlutar2",
    "Discover Unified Control Hub Receipt",
)


class ReplitDecommissionTests(unittest.TestCase):
    def test_discovery_lane_is_physically_absent(self) -> None:
        for relative in DECOMMISSIONED_PATHS:
            self.assertFalse(
                (ROOT / relative).exists(),
                f"decommissioned Replit executable returned: {relative}",
            )

    def test_no_executable_reintroduces_replit_receipt_discovery(self) -> None:
        self_path = Path(__file__).resolve()
        roots = (
            ROOT / ".github/workflows",
            ROOT / ".github/scripts",
        )
        for scan_root in roots:
            for path in scan_root.rglob("*"):
                if (
                    not path.is_file()
                    or path.resolve() == self_path
                    or path.suffix.lower() not in {".py", ".yml", ".yaml", ".sh", ".json"}
                ):
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                for marker in FORBIDDEN_EXECUTABLE_MARKERS:
                    self.assertNotIn(
                        marker,
                        text,
                        f"{path.relative_to(ROOT)} reintroduced {marker!r}",
                    )

    def test_active_estate_keeps_explicit_decommission_boundary(self) -> None:
        reconciler = (
            ROOT / ".github/scripts/final_estate_reconciliation_v5.py"
        ).read_text(encoding="utf-8")
        self.assertIn("DECOMMISSIONED_NOT_IN_ACTIVE_ESTATE", reconciler)
        self.assertIn('"operational_claim": False', reconciler)
        self.assertIn(
            "Replit Unified Control Hub is decommissioned from the active estate",
            reconciler,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
