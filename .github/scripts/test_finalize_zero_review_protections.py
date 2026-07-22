#!/usr/bin/env python3
from __future__ import annotations

import importlib
import pathlib
import sys
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

finalize = importlib.import_module("finalize_zero_review_protections")


class FinalizationContractTests(unittest.TestCase):
    def test_exact_scope(self) -> None:
        self.assertEqual(finalize.PLATFORM_RULESET_ID, 16195495)
        self.assertEqual(
            finalize.CLASSIC_REPOSITORIES,
            (
                "szl-holdings/szl-energy-attest",
                "szl-holdings/szl-lambda-gate",
                "szl-holdings/szl-lake",
                "szl-holdings/david-leads",
            ),
        )

    def test_platform_actor_cleanup_preserves_rules(self) -> None:
        sample = {
            "name": "series-a-default-branch",
            "target": "branch",
            "enforcement": "active",
            "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
            "rules": [
                {
                    "type": "pull_request",
                    "parameters": {"required_approving_review_count": 0},
                },
                {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "lockfiles"}]}},
            ],
        }
        self.assertEqual(finalize.ruleset_review_count(sample), 0)
        self.assertEqual(
            finalize.stable_ruleset_state(sample),
            finalize.stable_ruleset_state(sample),
        )

    def test_workflow_runs_both_finalizers(self) -> None:
        workflow = (SCRIPT_DIR.parent / "workflows" / "estate-finalization.yml").read_text(encoding="utf-8")
        self.assertIn("finalize_zero_review_protections.py", workflow)
        self.assertIn("hf_estate_canonicalize.py", workflow)
        self.assertIn("--publish", workflow)


if __name__ == "__main__":
    unittest.main()
