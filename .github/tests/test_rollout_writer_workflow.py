#!/usr/bin/env python3
"""Network-free contract for governed cross-repository rollout credentials."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "rollout-holographic-space-fabric-v2.yml"


class RolloutWriterWorkflowContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_all_governed_writer_candidates_are_available(self) -> None:
        for name in (
            "SZL_ORG_GITHUB_TOKEN",
            "SZL_GITHUB_TOKEN",
            "ORG_ADMIN_TOKEN",
            "GH_ADMIN_TOKEN",
            "ORG_REPO_WORKFLOW_TOKEN",
            "SZL_ORG_PAT",
            "SZL_GITHUB_PAT",
            "GH_PAT",
            "GITHUB_PAT",
            "PAT_TOKEN",
            "FRONTIER_TOKEN",
            "GH_TOKEN",
        ):
            self.assertIn(
                f"WRITER_{name}: ${{{{ secrets.{name} }}}}",
                self.source,
            )
        self.assertNotIn("|| github.token", self.source)

    def test_writer_is_measured_before_apply(self) -> None:
        self.assertIn("Resolve governed cross-repository writer", self.source)
        self.assertIn('permissions.get("push") is True', self.source)
        self.assertIn("SZL_GITHUB_TOKEN={selected_token}", self.source)
        self.assertLess(
            self.source.index("Resolve governed cross-repository writer"),
            self.source.index(
                "Discover, refresh, review, and merge through repository gates"
            ),
        )

    def test_every_previous_403_repository_is_probed(self) -> None:
        for repository in (
            "szl-holdings/ayllu",
            "szl-holdings/david-leads",
            "szl-holdings/immune",
            "szl-holdings/killinchu",
            "szl-holdings/lyte-services",
            "szl-holdings/platform",
            "szl-holdings/szl-command-lab",
            "szl-holdings/szl-constellation",
            "szl-holdings/yarqa",
        ):
            self.assertIn(repository, self.source)

    def test_receipt_is_secret_free_and_uploaded(self) -> None:
        self.assertIn("szl.public-experience-rollout-writer/v1", self.source)
        self.assertIn('"selected_credential": selected_name', self.source)
        self.assertIn('"secret_values_recorded": False', self.source)
        self.assertIn("${{ env.WRITER_RECEIPT }}", self.source)
        self.assertNotIn('"selected_token":', self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
