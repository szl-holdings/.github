#!/usr/bin/env python3
"""Network-free tests for the CI-health public publication boundary."""
from __future__ import annotations

import json
import unittest
from dataclasses import asdict

import ci_health_digest_public as public
import ci_health_digest_sweep as sweep
from ci_health_digest_http import DigestError


PRIVATE_MARKER = "private-fixture-do-not-publish"
PRIVATE_WORKFLOW = "private-workflow-do-not-publish"
PRIVATE_URL = "https://example.invalid/private-run-do-not-publish"


def red(repository: str, workflow: str, url: str | None = None) -> sweep.RedRun:
    return sweep.RedRun(
        repository=repository,
        workflow=workflow,
        provenance="protected_default_branch",
        conclusion="failure",
        run_id=101,
        run_attempt=1,
        run_number=7,
        event="push",
        url=url,
    )


class PublicProjectionTests(unittest.TestCase):
    def repositories(self):
        return (
            {
                "name": "public-fixture",
                "private": False,
                "visibility": "public",
                "archived": False,
                "default_branch": "main",
            },
            {
                "name": PRIVATE_MARKER,
                "private": True,
                "visibility": "private",
                "archived": False,
                "default_branch": "main",
            },
            {
                "name": "archived-public-fixture",
                "private": False,
                "visibility": "public",
                "archived": True,
                "default_branch": "main",
            },
        )

    def test_private_identity_workflow_url_and_run_detail_are_not_projected(self):
        reds = {
            "public-fixture": (
                red("public-fixture", "Public CI", "https://example.invalid/public"),
            ),
            PRIVATE_MARKER: (
                red(PRIVATE_MARKER, PRIVATE_WORKFLOW, PRIVATE_URL),
            ),
        }
        projected, publication = public.public_projection(
            self.repositories(),
            reds,
        )
        self.assertEqual(set(projected), {"public-fixture"})
        self.assertEqual(
            projected["public-fixture"][0].provenance,
            "default_branch_source",
        )
        self.assertFalse(publication["private_repository_identities_persisted"])
        self.assertFalse(publication["private_workflow_details_persisted"])
        self.assertEqual(publication["private_red_workflows_withheld"], 1)
        serialized = json.dumps(
            {
                "red_runs": {
                    name: [asdict(item) for item in items]
                    for name, items in projected.items()
                },
                "publication": publication,
            },
            sort_keys=True,
        )
        self.assertNotIn(PRIVATE_MARKER, serialized)
        self.assertNotIn(PRIVATE_WORKFLOW, serialized)
        self.assertNotIn(PRIVATE_URL, serialized)

    def test_public_body_discloses_boundary_without_private_marker(self):
        reds = {
            "public-fixture": (
                red("public-fixture", "Public CI", "https://example.invalid/public"),
            ),
            PRIVATE_MARKER: (
                red(PRIVATE_MARKER, PRIVATE_WORKFLOW, PRIVATE_URL),
            ),
        }
        projected, publication = public.public_projection(
            self.repositories(),
            reds,
        )
        body, actionable, total, dispositions = public.build_public_body(
            projected,
            coverage={
                "active_workflows": 4,
                "default_branch_workflows": 3,
                "github_managed_dynamic_workflows": 1,
                "registered_active_workflows": 5,
                "excluded_non_default_workflows": 1,
            },
            publication=publication,
            authentication_mode="fixture-reader",
        )
        self.assertEqual(actionable, 1)
        self.assertEqual(total, 1)
        self.assertEqual(dispositions["ACTIONABLE"], 1)
        self.assertIn("public repositories only", body)
        self.assertIn("default_branch_source", body)
        self.assertIn("does **not** prove branch protection", body)
        self.assertNotIn("protected_default_branch", body)
        self.assertNotIn(PRIVATE_MARKER, body)
        self.assertNotIn(PRIVATE_WORKFLOW, body)
        self.assertNotIn(PRIVATE_URL, body)

    def test_zero_public_reds_is_not_a_whole_org_all_clear(self):
        publication = {
            "public_active_repositories": 1,
        }
        body, actionable, total, _ = public.build_public_body(
            {},
            coverage={
                "active_workflows": 0,
                "default_branch_workflows": 0,
                "github_managed_dynamic_workflows": 0,
                "registered_active_workflows": 0,
                "excluded_non_default_workflows": 0,
            },
            publication=publication,
            authentication_mode="fixture-reader",
        )
        self.assertEqual(actionable, 0)
        self.assertEqual(total, 0)
        self.assertIn("not a whole-organization all-clear", body)

    def test_visibility_metadata_conflict_fails_closed(self):
        with self.assertRaisesRegex(DigestError, "contradictory"):
            public.repository_visibility(
                {"name": "fixture", "private": False, "visibility": "private"}
            )
        with self.assertRaisesRegex(DigestError, "unavailable"):
            public.repository_visibility(
                {"name": "fixture", "visibility": "public"}
            )

    def test_unknown_sweep_repository_fails_closed_without_publishing_name(self):
        with self.assertRaisesRegex(DigestError, "unknown repository"):
            public.public_projection(
                self.repositories(),
                {
                    "unbound-fixture": (
                        red("unbound-fixture", "CI"),
                    )
                },
            )

    def test_authentication_attempts_drop_repository_cardinality(self):
        sanitized = public.sanitized_attempts(
            (
                {
                    "mode": "fixture",
                    "credential_name": "fixture-reader",
                    "present": True,
                    "result": "selected",
                    "repository_count": 999,
                    "authoritative_inventory_match": True,
                    "value_recorded": False,
                },
            )
        )
        text = json.dumps(sanitized, sort_keys=True)
        self.assertNotIn("repository_count", text)
        self.assertIn("authoritative_inventory_match", text)

    def test_private_detail_sink_is_explicitly_unavailable_not_invented(self):
        projected, publication = public.public_projection(
            self.repositories(),
            {
                PRIVATE_MARKER: (
                    red(PRIVATE_MARKER, PRIVATE_WORKFLOW, PRIVATE_URL),
                )
            },
        )
        self.assertEqual(projected, {})
        self.assertEqual(
            publication["private_detail_sink"],
            "UNAVAILABLE_IN_PUBLIC_WORKFLOW",
        )
        self.assertFalse(publication["branch_protection_inferred"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
