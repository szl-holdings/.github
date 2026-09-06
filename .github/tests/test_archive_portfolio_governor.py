#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline contracts for archive_portfolio_governor."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / ".github" / "scripts" / "archive_portfolio_governor.py"
SPEC = importlib.util.spec_from_file_location("archive_portfolio_governor", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def load() -> dict:
    return json.loads(
        (ROOT / "governance" / "archive-portfolio-v1.json").read_text(
            encoding="utf-8"
        )
    )


def states(value: dict, *, restored: bool = False):
    restore = set(value["restoration_wave"]["repositories"])
    return [
        module.RepoState(
            name=row["name"],
            archived=not (restored and row["name"] in restore),
            private=False,
            disabled=False,
            fork=False,
            default_branch="main",
        )
        for row in value["repositories"]
    ] + [
        module.RepoState(
            name=target,
            archived=False,
            private=False,
            disabled=False,
            fork=False,
            default_branch="main",
        )
        for target in sorted(
            {
                target
                for row in value["repositories"]
                for target in row["canonical_targets"]
            }
            - {row["name"] for row in value["repositories"]}
        )
    ]


class ManifestTests(unittest.TestCase):
    def test_manifest_is_complete_and_valid(self):
        value = load()
        module.validate_manifest(value)
        self.assertEqual(len(value["repositories"]), 34)
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

    def test_duplicate_repository_fails_closed(self):
        value = load()
        value["repositories"].append(copy.deepcopy(value["repositories"][0]))
        value["source_inventory"][
            "archived_public_repositories_observed"
        ] += 1
        with self.assertRaises(module.PortfolioError):
            module.validate_manifest(value)

    def test_restore_cannot_delegate_authority(self):
        value = load()
        row = next(
            item
            for item in value["repositories"]
            if item["disposition"] == "restore"
        )
        row["canonical_targets"] = ["a11oy"]
        with self.assertRaises(module.PortfolioError):
            module.validate_manifest(value)

    def test_historical_cannot_become_hidden_active_authority(self):
        value = load()
        row = next(
            item
            for item in value["repositories"]
            if item["disposition"] == "historical"
        )
        row["canonical_targets"] = ["a11oy"]
        with self.assertRaises(module.PortfolioError):
            module.validate_manifest(value)


class PlanTests(unittest.TestCase):
    def test_exact_restore_plan(self):
        value = load()
        plan = module.build_plan(value, states(value))
        self.assertEqual(
            plan["restore"],
            value["restoration_wave"]["repositories"],
        )
        self.assertEqual(plan["already_restored"], [])
        self.assertEqual(len(plan["retain_archived"]), 29)
        self.assertEqual(plan["unclassified_archived"], [])

    def test_post_restore_is_idempotent(self):
        value = load()
        plan = module.build_plan(value, states(value, restored=True))
        self.assertEqual(plan["restore"], [])
        self.assertEqual(
            plan["already_restored"],
            value["restoration_wave"]["repositories"],
        )
        self.assertEqual(len(plan["retain_archived"]), 29)

    def test_unclassified_archived_repository_fails_closed(self):
        value = load()
        current = states(value)
        current.append(
            module.RepoState(
                name="surprise-archive",
                archived=True,
                private=False,
                disabled=False,
                fork=False,
                default_branch="main",
            )
        )
        with self.assertRaisesRegex(
            module.PortfolioError, "unclassified public archived"
        ):
            module.build_plan(value, current)

    def test_consolidated_repo_cannot_silently_reactivate(self):
        value = load()
        current = states(value)
        chosen = next(
            row["name"]
            for row in value["repositories"]
            if row["disposition"] == "consolidate"
        )
        current = [
            module.RepoState(
                name=item.name,
                archived=False if item.name == chosen else item.archived,
                private=item.private,
                disabled=item.disabled,
                fork=item.fork,
                default_branch=item.default_branch,
            )
            for item in current
        ]
        with self.assertRaisesRegex(
            module.PortfolioError, "unexpectedly active"
        ):
            module.build_plan(value, current)

    def test_archived_canonical_target_fails_closed(self):
        value = load()
        current = states(value)
        target = next(
            target
            for row in value["repositories"]
            for target in row["canonical_targets"]
            if target not in value["restoration_wave"]["repositories"]
        )
        current = [
            module.RepoState(
                name=item.name,
                archived=True if item.name == target else item.archived,
                private=item.private,
                disabled=item.disabled,
                fork=item.fork,
                default_branch=item.default_branch,
            )
            for item in current
        ]
        with self.assertRaisesRegex(
            module.PortfolioError,
            "unclassified public archived|target defects",
        ):
            module.build_plan(value, current)


class ExecutionTests(unittest.TestCase):
    class FakeClient:
        def __init__(self, repos):
            self.repos = list(repos)
            self.calls = []

        def repositories(self, _organization):
            return list(self.repos)

        def unarchive(self, _organization, name):
            self.calls.append(name)
            updated = []
            result = None
            for item in self.repos:
                if item.name == name:
                    item = module.RepoState(
                        name=item.name,
                        archived=False,
                        private=item.private,
                        disabled=item.disabled,
                        fork=item.fork,
                        default_branch=item.default_branch,
                    )
                    result = item
                updated.append(item)
            self.repos = updated
            assert result is not None
            return result

    def test_apply_only_unarchives_manifest_restore_rows(self):
        value = load()
        client = self.FakeClient(states(value))
        report = module.execute(value, client, apply=True)
        self.assertEqual(
            client.calls,
            value["restoration_wave"]["repositories"],
        )
        self.assertEqual(report["status"], "PASS")
        self.assertFalse(report["archive_mutations"])
        self.assertFalse(report["visibility_mutations"])
        self.assertFalse(report["history_deletions"])
        self.assertEqual(report["final"]["restore"], [])

    def test_audit_performs_no_mutation(self):
        value = load()
        client = self.FakeClient(states(value))
        report = module.execute(value, client, apply=False)
        self.assertEqual(client.calls, [])
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(
            all(item["status"] == "PLANNED" for item in report["actions"])
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
