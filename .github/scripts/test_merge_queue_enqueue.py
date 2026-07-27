#!/usr/bin/env python3
"""Source contract for the protected merge-queue enqueue controller."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/merge-queue-enqueue.yml"


class MergeQueueEnqueueContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_uses_only_the_queue_mutation(self) -> None:
        self.assertIn("enqueuePullRequest", self.source)
        self.assertIn("expectedHeadOid", self.source)
        forbidden = (
            "mergePullRequest",
            "gh pr merge",
            "--admin",
            "/merge\"",
            "updatePullRequestBranch",
            "updateRef",
            "force=true",
        )
        for marker in forbidden:
            self.assertNotIn(marker, self.source, marker)

    def test_requires_exact_head_attestation_and_app_approval(self) -> None:
        required = (
            "attestation/qillqaq",
            "qillqaq-attestor[bot]",
            "commit_id == $head",
            "CURRENT_HEAD",
            "EXPECTED_HEAD",
            "headRefOid",
            "isDraft",
            "GRAPH_STATE",
            "CURRENT_STATE",
            "'OPEN'",
        )
        for marker in required:
            self.assertIn(marker, self.source, marker)

    def test_is_same_repository_only_and_does_not_expose_token(self) -> None:
        required = (
            "github.event.pull_request.head.repo.full_name == github.repository",
            "secrets.SZL_GITHUB_TOKEN",
            "direct_merge_attempted",
            "bypass_used",
            "token_value_recorded",
        )
        for marker in required:
            self.assertIn(marker, self.source, marker)
        self.assertNotIn("set -x", self.source)
        self.assertNotIn("echo $GH_TOKEN", self.source)
        self.assertNotIn("echo \"$GH_TOKEN\"", self.source)

    def test_receipt_is_retained_and_never_claims_a_merge(self) -> None:
        self.assertIn("retention-days: 90", self.source)
        self.assertIn("merge-queue-enqueue-${{ github.run_id }}", self.source)
        self.assertIn("merge_performed", self.source)
        self.assertIn("false", self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
