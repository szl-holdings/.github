#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import pathlib
import sys
import unittest

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

transaction = importlib.import_module("transactional_owner_merge")


class TransactionContractTests(unittest.TestCase):
    def test_exact_recovery_scope(self) -> None:
        self.assertEqual(transaction.PLATFORM_REPOSITORY, "szl-holdings/platform")
        self.assertEqual(transaction.PLATFORM_PULL_REQUEST, 458)
        self.assertEqual(transaction.PLATFORM_RULESET_ID, 16195495)
        self.assertEqual(
            transaction.CLASSIC_RESTORE_REPOSITORIES,
            (
                "szl-holdings/szl-energy-attest",
                "szl-holdings/szl-lambda-gate",
                "szl-holdings/szl-lake",
                "szl-holdings/david-leads",
            ),
        )

    def test_review_count_is_the_only_temporary_rule_change(self) -> None:
        sample = {
            "name": "series-a-default-branch",
            "target": "branch",
            "enforcement": "active",
            "bypass_actors": [
                {
                    "actor_id": 5,
                    "actor_type": "RepositoryRole",
                    "bypass_mode": "always",
                },
                {
                    "actor_id": None,
                    "actor_type": "OrganizationAdmin",
                    "bypass_mode": "pull_request",
                },
            ],
            "conditions": {
                "ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}
            },
            "rules": [
                {"type": "deletion"},
                {"type": "non_fast_forward"},
                {
                    "type": "pull_request",
                    "parameters": {
                        "required_approving_review_count": 1,
                        "required_review_thread_resolution": True,
                        "allowed_merge_methods": ["squash", "rebase"],
                    },
                },
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "required_status_checks": [{"context": "lockfiles"}]
                    },
                },
            ],
        }
        temporary = {
            **sample,
            "rules": transaction.rules_with_review_count(sample, 0),
        }
        self.assertEqual(transaction.review_count(temporary), 0)
        self.assertEqual(
            transaction.state_without_review_count(temporary),
            transaction.state_without_review_count(sample),
        )
        final_actors = transaction.actors_without_transient(
            sample["bypass_actors"]
        )
        self.assertEqual(
            final_actors,
            [
                {
                    "actor_id": 5,
                    "actor_type": "RepositoryRole",
                    "bypass_mode": "always",
                }
            ],
        )

    def test_manifest_is_exactly_platform_458(self) -> None:
        manifest_path = SCRIPT_DIR.parent / "data" / "owner_authorized_merge_wave.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["targets"]), 1)
        target = manifest["targets"][0]
        self.assertEqual(target["repository"], "szl-holdings/platform")
        self.assertEqual(target["pull_request"], 458)
        self.assertEqual(
            target["expected_head_sha"],
            "9798feff9af3d6b0d8737abd70f71a1db1755a65",
        )

    def test_workflow_uses_transaction_not_legacy_one_way_helper(self) -> None:
        workflow = (
            SCRIPT_DIR.parent / "workflows" / "owner-authorized-merge-wave.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("transactional_owner_merge.py", workflow)
        self.assertNotIn("--execute\n          code=$?", workflow.split("transactional_owner_merge.py")[0])


if __name__ == "__main__":
    unittest.main()
