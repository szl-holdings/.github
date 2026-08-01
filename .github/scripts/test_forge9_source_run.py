#!/usr/bin/env python3
"""Adversarial tests for exact FORGE-9 workflow-run PR identity binding."""

from __future__ import annotations

import unittest
from pathlib import Path

from forge9_source_run import (
    SourceRunIdentityError,
    bind_source_run,
    latest_matching_run_id,
    verify_pull_request,
)


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "szl-holdings/.github"
REPOSITORY_ID = 1200488980
HEAD_SHA = "3" * 40
BASE_SHA = "a" * 40


def association(*, number: int = 381, head_repo_id: int = REPOSITORY_ID) -> dict:
    return {
        "id": 4185826009 + number,
        "number": number,
        "head": {
            "ref": f"agent/pr-{number}",
            "sha": HEAD_SHA,
            "repo": {
                "id": head_repo_id,
                "name": ".github" if head_repo_id == REPOSITORY_ID else "fork",
                "url": "https://api.github.test/head",
            },
        },
        "base": {
            "ref": "main",
            "sha": BASE_SHA,
            "repo": {
                "id": REPOSITORY_ID,
                "name": ".github",
                "url": "https://api.github.test/base",
            },
        },
    }


def workflow_run(*, run_id: int = 100, associations: list[dict] | None = None) -> dict:
    return {
        "id": run_id,
        "event": "pull_request",
        "head_sha": HEAD_SHA,
        "repository": {"id": REPOSITORY_ID, "full_name": REPOSITORY},
        "head_repository": {"id": REPOSITORY_ID, "full_name": REPOSITORY},
        "pull_requests": [association()] if associations is None else associations,
    }


def current_pull_request(source: dict | None = None) -> dict:
    source = association() if source is None else source
    return {
        "id": source["id"],
        "number": source["number"],
        "state": "open",
        "draft": False,
        "head": {
            **source["head"],
            "repo": {"id": REPOSITORY_ID, "full_name": REPOSITORY},
        },
        "base": {
            **source["base"],
            "repo": {"id": REPOSITORY_ID, "full_name": REPOSITORY},
        },
    }


class SourceRunBindingTests(unittest.TestCase):
    profiles = {
        "attestor": {"allowed_bases": ("main",), "allowed_base_prefixes": ("release/",)},
        "queue": {"allowed_bases": ("main",), "allowed_base_prefixes": ()},
    }

    def bind(self, run: dict, profile: str = "attestor") -> dict:
        return bind_source_run(
            run,
            expected_run_id=100,
            expected_repository=REPOSITORY,
            expected_head_sha=HEAD_SHA,
            **self.profiles[profile],
        )

    def test_valid_same_repository_association_binds_for_both_consumers(self) -> None:
        for profile in self.profiles:
            with self.subTest(profile=profile):
                binding = self.bind(workflow_run(), profile)
                self.assertEqual(binding["pull_request_number"], 381)
                self.assertEqual(binding["head_repository_id"], REPOSITORY_ID)
                verify_pull_request(binding, current_pull_request())

    def test_empty_and_multiple_associations_fail_closed_for_both(self) -> None:
        invalid = ([], [association(), association(number=382)])
        for profile in self.profiles:
            for associations in invalid:
                with self.subTest(profile=profile, count=len(associations)):
                    with self.assertRaises(SourceRunIdentityError):
                        self.bind(workflow_run(associations=associations), profile)

    def test_run_id_event_and_head_sha_mismatches_fail_closed(self) -> None:
        mutations = {
            "id": 101,
            "event": "push",
            "head_sha": "4" * 40,
        }
        for profile in self.profiles:
            for field, value in mutations.items():
                run = workflow_run()
                run[field] = value
                with self.subTest(profile=profile, field=field):
                    with self.assertRaises(SourceRunIdentityError):
                        self.bind(run, profile)

    def test_fork_source_with_shared_public_sha_cannot_select_same_repo_pr(self) -> None:
        fork_association = association(number=999, head_repo_id=999999)
        for profile in self.profiles:
            run = workflow_run(associations=[fork_association])
            run["head_repository"] = {
                "id": 999999,
                "full_name": "outsider/fork",
            }
            with self.subTest(profile=profile):
                with self.assertRaises(SourceRunIdentityError):
                    self.bind(run, profile)

    def test_other_source_pr_number_never_remaps_to_same_sha_candidate(self) -> None:
        source = association(number=999)
        for profile in self.profiles:
            with self.subTest(profile=profile):
                binding = self.bind(workflow_run(associations=[source]), profile)
                self.assertEqual(binding["pull_request_number"], 999)
                with self.assertRaises(SourceRunIdentityError):
                    verify_pull_request(binding, current_pull_request(association(number=381)))

    def test_base_repository_ref_and_sha_mismatches_fail_closed(self) -> None:
        for profile in self.profiles:
            for field, value in (
                ("repo", {"id": 999999, "name": "other", "url": "x"}),
                ("sha", "b" * 40),
            ):
                source = association()
                source["base"][field] = value
                if field == "sha":
                    binding = self.bind(workflow_run(associations=[source]), profile)
                    pr = current_pull_request()
                    with self.subTest(profile=profile, field=field):
                        with self.assertRaises(SourceRunIdentityError):
                            verify_pull_request(binding, pr)
                else:
                    with self.subTest(profile=profile, field=field):
                        with self.assertRaises(SourceRunIdentityError):
                            self.bind(workflow_run(associations=[source]), profile)

        release = association()
        release["base"]["ref"] = "release/2026.08"
        self.bind(workflow_run(associations=[release]), "attestor")
        with self.assertRaises(SourceRunIdentityError):
            self.bind(workflow_run(associations=[release]), "queue")

    def test_current_pr_number_head_and_base_mismatches_fail_closed(self) -> None:
        binding = self.bind(workflow_run())
        mutations = (
            ("number", 999),
            ("head.sha", "5" * 40),
            ("head.repo", {"id": 999999, "full_name": "outsider/fork"}),
            ("base.ref", "release/other"),
            ("base.sha", "b" * 40),
            ("base.repo", {"id": 999999, "full_name": "outsider/base"}),
        )
        for dotted, value in mutations:
            pr = current_pull_request()
            target = pr
            parts = dotted.split(".")
            for part in parts[:-1]:
                target = target[part]
            target[parts[-1]] = value
            with self.subTest(field=dotted):
                with self.assertRaises(SourceRunIdentityError):
                    verify_pull_request(binding, pr)

    def test_latest_generation_filters_by_exact_pr_association(self) -> None:
        binding = self.bind(workflow_run())
        valid_newer = workflow_run(run_id=103)
        foreign_newer = workflow_run(
            run_id=104,
            associations=[association(number=999, head_repo_id=999999)],
        )
        foreign_newer["head_repository"] = {
            "id": 999999,
            "full_name": "outsider/fork",
        }
        other_pr = workflow_run(run_id=105, associations=[association(number=999)])
        payload = {"workflow_runs": [workflow_run(), valid_newer, foreign_newer, other_pr]}
        self.assertEqual(latest_matching_run_id(payload, binding), 103)

    def test_latest_generation_fails_when_no_exact_association_remains(self) -> None:
        binding = self.bind(workflow_run())
        payload = {"workflow_runs": [workflow_run(associations=[])]}
        with self.assertRaises(SourceRunIdentityError):
            latest_matching_run_id(payload, binding)


class WorkflowSourceBindingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.attestor = (
            ROOT / ".github/workflows/attest-and-approve.yml"
        ).read_text(encoding="utf-8")
        cls.queue = (
            ROOT / ".github/workflows/merge-queue-enqueue.yml"
        ).read_text(encoding="utf-8")

    def test_both_consumers_use_exact_run_binding_and_current_pr_verification(self) -> None:
        for name, source in (("attestor", self.attestor), ("queue", self.queue)):
            with self.subTest(controller=name):
                self.assertIn("actions/runs/$SOURCE_GATE_RUN_ID", source)
                self.assertIn("forge9_source_run.py bind", source)
                self.assertIn("forge9_source_run.py verify-pr", source)
                self.assertIn("forge9_source_run.py latest", source)
                self.assertNotRegex(source, r"commits/\$(?:HEAD_SHA|EXPECTED_HEAD)/pulls")

    def test_queue_accepts_only_main_while_attestor_preserves_release(self) -> None:
        self.assertIn("--allowed-base-prefix release/", self.attestor)
        self.assertNotIn("--allowed-base-prefix release/", self.queue)
        self.assertIn("--allowed-base main", self.attestor)
        self.assertIn("--allowed-base main", self.queue)


if __name__ == "__main__":
    unittest.main(verbosity=2)
