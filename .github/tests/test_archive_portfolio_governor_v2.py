#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Network-free contracts for the archive portfolio governor v2."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / ".github" / "scripts" / "archive_portfolio_governor_v2.py"
SPEC = importlib.util.spec_from_file_location("archive_portfolio_governor_v2", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
MANIFEST_PATH = ROOT / "governance" / "archive-portfolio-v2.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def active(name: str, *, admin: bool = True) -> MODULE.RepoState:
    return MODULE.RepoState(
        name=name,
        archived=False,
        private=False,
        disabled=False,
        fork=False,
        default_branch="main",
        admin=admin,
    )


def archived(name: str, *, admin: bool = True) -> MODULE.RepoState:
    return MODULE.RepoState(
        name=name,
        archived=True,
        private=False,
        disabled=False,
        fork=False,
        default_branch="main",
        admin=admin,
    )


def inventory(manifest: dict, *, restored: bool = False) -> list[MODULE.RepoState]:
    names = {row["name"] for row in manifest["repositories"]}
    targets = {
        target
        for row in manifest["repositories"]
        for target in row["canonical_targets"]
    }
    restore = set(manifest["restoration_wave"]["repositories"])
    output = []
    for name in sorted(names):
        output.append(active(name) if restored and name in restore else archived(name))
    output.extend(active(name) for name in sorted(targets - names))
    return output


class ManifestContracts(unittest.TestCase):
    def test_real_manifest_validates_and_classifies_every_archive(self) -> None:
        manifest = MODULE.load_manifest(MANIFEST_PATH)
        self.assertEqual(len(manifest["repositories"]), 34)
        self.assertEqual(
            manifest["restoration_wave"]["repositories"],
            ["szl-atelier", "szl-build-env", "szl-mesh", "szl-router", "uds-bundles", "vsp-otel"],
        )

    def test_duplicate_json_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
            with self.assertRaisesRegex(MODULE.PortfolioError, "duplicate JSON key"):
                MODULE.load_manifest(path)

    def test_restore_set_cannot_expand_or_shift(self) -> None:
        manifest = load_manifest()
        candidate = copy.deepcopy(manifest)
        row = next(item for item in candidate["repositories"] if item["name"] == "cosmos")
        row["disposition"] = "restore"
        row["canonical_targets"] = []
        candidate["restoration_wave"]["repositories"] = sorted(
            candidate["restoration_wave"]["repositories"] + ["cosmos"]
        )
        candidate["restoration_wave"]["count"] = len(candidate["restoration_wave"]["repositories"])
        with self.assertRaises(MODULE.PortfolioError):
            MODULE.validate_manifest(candidate)

    def test_restore_row_cannot_delegate_authority(self) -> None:
        manifest = load_manifest()
        candidate = copy.deepcopy(manifest)
        row = next(item for item in candidate["repositories"] if item["name"] == "szl-router")
        row["canonical_targets"] = ["a11oy"]
        with self.assertRaisesRegex(MODULE.PortfolioError, "cannot delegate"):
            MODULE.validate_manifest(candidate)

    def test_historical_row_cannot_have_target(self) -> None:
        manifest = load_manifest()
        candidate = copy.deepcopy(manifest)
        row = next(
            item
            for item in candidate["repositories"]
            if item["name"] == "warhacker-demo"
        )
        row["canonical_targets"] = ["szl-constellation"]
        with self.assertRaisesRegex(MODULE.PortfolioError, "historical rows"):
            MODULE.validate_manifest(candidate)

    def test_foreign_hugging_face_showcase_is_rejected(self) -> None:
        manifest = load_manifest()
        candidate = copy.deepcopy(manifest)
        candidate["repositories"][0]["hugging_face_showcase"] = "foreign/example"
        with self.assertRaisesRegex(MODULE.PortfolioError, "inside SZLHOLDINGS"):
            MODULE.validate_manifest(candidate)


class PlanContracts(unittest.TestCase):
    def test_recovery_wave_only_restores_missing_executable_owners(self) -> None:
        manifest = load_manifest()
        recovered = {"szl-build-env", "vsp-otel"}
        values = [
            archived(value.name) if value.name in recovered else value
            for value in inventory(manifest, restored=True)
        ]
        plan = MODULE.build_plan(manifest, values)
        self.assertEqual(plan["restore"], sorted(recovered))
        self.assertEqual(len(plan["already_restored"]), 4)
        self.assertEqual(len(plan["retain_archived"]), 28)

    def test_initial_plan_restores_only_six(self) -> None:
        manifest = load_manifest()
        plan = MODULE.build_plan(manifest, inventory(manifest))
        self.assertEqual(plan["restore"], manifest["restoration_wave"]["repositories"])
        self.assertEqual(len(plan["retain_archived"]), 28)
        self.assertEqual(plan["unclassified_archived"], [])

    def test_idempotent_plan_accepts_verified_restores(self) -> None:
        manifest = load_manifest()
        plan = MODULE.build_plan(manifest, inventory(manifest, restored=True))
        self.assertEqual(plan["restore"], [])
        self.assertEqual(
            plan["already_restored"],
            manifest["restoration_wave"]["repositories"],
        )
        self.assertEqual(len(plan["retain_archived"]), 28)

    def test_unclassified_archive_fails_closed(self) -> None:
        manifest = load_manifest()
        values = inventory(manifest)
        values.append(archived("surprise-archive"))
        with self.assertRaisesRegex(MODULE.PortfolioError, "unclassified"):
            MODULE.build_plan(manifest, values)

    def test_consolidated_repository_cannot_reactivate(self) -> None:
        manifest = load_manifest()
        values = inventory(manifest)
        values = [
            active(value.name) if value.name == "counsel" else value
            for value in values
        ]
        with self.assertRaisesRegex(MODULE.PortfolioError, "unexpectedly active"):
            MODULE.build_plan(manifest, values)

    def test_archived_canonical_target_fails_closed(self) -> None:
        manifest = load_manifest()
        values = inventory(manifest)
        values = [
            archived(value.name) if value.name == "szl-formulas" else value
            for value in values
        ]
        with self.assertRaisesRegex(MODULE.PortfolioError, "unclassified|canonical target defects"):
            MODULE.build_plan(manifest, values)

    def test_private_restore_fails_closed(self) -> None:
        manifest = load_manifest()
        values = inventory(manifest)
        values = [
            MODULE.RepoState(
                name=value.name,
                archived=value.archived,
                private=True,
                disabled=value.disabled,
                fork=value.fork,
                default_branch=value.default_branch,
                admin=value.admin,
            )
            if value.name == "uds-bundles"
            else value
            for value in values
        ]
        with self.assertRaisesRegex(MODULE.PortfolioError, "became private"):
            MODULE.build_plan(manifest, values)


class ExecutionContracts(unittest.TestCase):
    def test_dry_run_never_mutates(self) -> None:
        manifest = load_manifest()
        states = inventory(manifest)

        class FakeClient:
            def repositories(self, organization: str):
                self.assert_org = organization
                return states

        report = MODULE.execute(manifest, FakeClient(), apply=False)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(all(row["status"] == "PLANNED" for row in report["actions"]))
        self.assertFalse(report["unarchive_state_mutations_attempted"])
        self.assertFalse(report["hugging_face_mutations"])

    def test_apply_is_idempotent_and_records_only_unarchives(self) -> None:
        manifest = load_manifest()
        current = {value.name: value for value in inventory(manifest)}

        class FakeClient:
            def repositories(self, organization: str):
                return list(current.values())

            def require_admin(self, organization: str, names):
                self.names = list(names)

            def unarchive(self, organization: str, name: str):
                before = current[name]
                current[name] = MODULE.RepoState(
                    name=name,
                    archived=False,
                    private=before.private,
                    disabled=before.disabled,
                    fork=before.fork,
                    default_branch=before.default_branch,
                    admin=before.admin,
                )
                return current[name]

        client = FakeClient()
        report = MODULE.execute(manifest, client, apply=True)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(client.names, manifest["restoration_wave"]["repositories"])
        self.assertEqual(report["final"]["restore"], [])
        self.assertTrue(report["unarchive_state_mutations_attempted"])
        self.assertFalse(report["archive_true_mutations"])
        self.assertFalse(report["visibility_mutations"])
        self.assertFalse(report["history_deletions"])
        self.assertFalse(report["hugging_face_mutations"])

    def test_report_rejects_credential_shaped_material(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            with self.assertRaisesRegex(MODULE.PortfolioError, "credential-shaped"):
                MODULE.write_report(
                    path,
                    {"secret": "github_pat_" + "a" * 30},
                )


if __name__ == "__main__":
    unittest.main()
