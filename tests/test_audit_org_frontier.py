from __future__ import annotations

import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_org_frontier.py"
spec = importlib.util.spec_from_file_location("audit_org_frontier", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

AUTHORITY = {
    "vision": "one fabric",
    "locked_formula_ids": ["F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22"],
    "lambda_status": "CONJECTURE_1_ADVISORY",
    "canonical_control_planes": {"action": "a11oy"},
    "verticals": [
        {
            "slug": "lyte",
            "brand": "Lyte",
            "canonical_repositories": ["lyte-lattice"],
            "runtime_surfaces": ["SZLHOLDINGS/lyte"],
            "product_routes": ["https://a-11-oy.com/lyte"],
            "formula_binding": "complete_locked_eight_via_shared_anatomy",
        }
    ],
    "audit_policy": {
        "stale_after_days": 180,
        "max_workflow_files_per_repository": 40,
        "required_community_files": ["readme", "license", "security"],
        "duplicate_description_prefix": "ARCHIVED duplicate/hologram. Canonical:",
    },
}


def repo(name: str, **overrides):
    value = {
        "name": name,
        "private": False,
        "archived": False,
        "description": "purpose",
        "homepage": "https://a-11-oy.com",
        "license": "Apache-2.0",
        "pushed_at": "2026-09-01T00:00:00Z",
        "community_files": {"readme": True, "security": True},
        "workflow_sources": [],
        "workflow_files_truncated": False,
        "default_branch_protected": True,
    }
    value.update(overrides)
    return value


class AuditContract(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc)

    def test_exact_formula_and_lambda_contract(self):
        snapshot = {"organization": "szl-holdings", "repositories": [repo("a11oy"), repo("lyte-lattice")]}
        result = module.analyze(snapshot, AUTHORITY, now=self.now)
        self.assertEqual(result["locked_formula_ids"], AUTHORITY["locked_formula_ids"])
        self.assertEqual(result["lambda_status"], "CONJECTURE_1_ADVISORY")
        broken = json.loads(json.dumps(AUTHORITY))
        broken["locked_formula_ids"][-1] = "F99"
        with self.assertRaisesRegex(module.AuditError, "locked-eight"):
            module.analyze(snapshot, broken, now=self.now)

    def test_census_duplicate_private_and_stale_findings(self):
        snapshot = {
            "organization": "szl-holdings",
            "repositories": [
                repo("a11oy"),
                repo("lyte-lattice"),
                repo(
                    "old-hologram",
                    archived=False,
                    description="ARCHIVED duplicate/hologram. Canonical: https://github.com/szl-holdings/a11oy",
                    pushed_at="2025-01-01T00:00:00Z",
                ),
                repo("secret-source", private=True),
            ],
        }
        result = module.analyze(snapshot, AUTHORITY, now=self.now)
        self.assertEqual(result["counts"]["repositories"], 4)
        self.assertEqual(result["counts"]["private"], 1)
        self.assertEqual(result["counts"]["duplicates"], 1)
        codes = {(row["repository"], row["code"]) for row in result["findings"]}
        self.assertIn(("old-hologram", "DUPLICATE_NOT_ARCHIVED"), codes)
        self.assertIn(("old-hologram", "STALE_ACTIVE_REPOSITORY"), codes)
        self.assertIn(("secret-source", "PRIVATE_REPOSITORY"), codes)

    def test_unpinned_third_party_actions_are_high_findings(self):
        snapshot = {
            "organization": "szl-holdings",
            "repositories": [
                repo("a11oy", workflow_sources=[{"path": ".github/workflows/ci.yml", "text": "steps:\n  - uses: actions/checkout@v4\n  - uses: ./local\n  - uses: actions/setup-python@0123456789012345678901234567890123456789\n"}]),
                repo("lyte-lattice"),
            ],
        }
        result = module.analyze(snapshot, AUTHORITY, now=self.now)
        findings = [row for row in result["findings"] if row["code"] == "UNPINNED_THIRD_PARTY_ACTION"]
        self.assertEqual(len(findings), 1)
        observed = result["repositories"][0]["unpinned_action_uses"]
        self.assertEqual(observed, [{"path": ".github/workflows/ci.yml", "action": "actions/checkout", "ref": "v4"}])

    def test_missing_vertical_source_is_critical(self):
        snapshot = {"organization": "szl-holdings", "repositories": [repo("a11oy")]}
        result = module.analyze(snapshot, AUTHORITY, now=self.now)
        self.assertEqual(result["counts"]["critical"], 1)
        self.assertFalse(result["verticals"][0]["ready_for_runtime_proof"])

    def test_markdown_preserves_interpretation_boundary(self):
        snapshot = {"organization": "szl-holdings", "repositories": [repo("a11oy"), repo("lyte-lattice")]}
        result = module.analyze(snapshot, AUTHORITY, now=self.now)
        text = module.render_markdown(result)
        self.assertIn("not a claim that a website, Space, model", text)
        self.assertIn("Locked formulas", text)
        self.assertIn("Lyte", text)


if __name__ == "__main__":
    unittest.main()
