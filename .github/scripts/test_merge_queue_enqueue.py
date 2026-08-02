#!/usr/bin/env python3
"""Source contract for the protected merge-queue enqueue controller."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/merge-queue-enqueue.yml"


class MergeQueueEnqueueContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_runs_only_from_trusted_default_branch_gate_completion(self) -> None:
        required = (
            "workflow_run:",
            "FORGE-9 gates",
            "github.event.workflow_run.conclusion == 'success'",
            "github.event.workflow_run.event == 'pull_request'",
            "ref: ${{ github.event.repository.default_branch }}",
            "Checkout trusted controller source",
        )
        for marker in required:
            self.assertIn(marker, self.source, marker)
        self.assertNotRegex(self.source, re.compile(r"^\s+pull_request:\s*$", re.M))
        self.assertNotIn("github.event.pull_request.head.sha", self.source)

    def test_write_token_never_reaches_checkout_or_contract_test(self) -> None:
        secret = "GH_TOKEN: ${{ secrets.SZL_GITHUB_TOKEN }}"
        self.assertEqual(self.source.count(secret), 1)
        secret_offset = self.source.index(secret)
        self.assertGreater(secret_offset, self.source.index("Checkout trusted controller source"))
        self.assertGreater(secret_offset, self.source.index("Verify the enqueue-only source contract"))
        self.assertNotIn(secret, self.source.split("steps:", 1)[0])

    def test_uses_only_the_queue_mutation(self) -> None:
        self.assertIn("enqueuePullRequest", self.source)
        self.assertIn("dequeuePullRequest", self.source)
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

    def test_requires_exact_generation_head_body_and_app_provenance(self) -> None:
        required = (
            "SOURCE_GATE_RUN_ID",
            "LATEST_GATE_RUN_ID",
            "PR body sha256:",
            "Gate run:",
            "CURRENT_BODY_SHA256",
            "GRAPH_BODY_SHA256",
            "CURRENT_BASE_REF",
            "CURRENT_BASE_SHA",
            "baseRefName",
            "ref(qualifiedName:$base){target{oid}}",
            ".data.repository.ref.target.oid",
            "Base: $CURRENT_BASE_REF@$CURRENT_BASE_SHA",
            "--paginate --slurp",
            "attestation/qillqaq",
            "qillqaq-attestor[bot]",
            '.creator.type == "Bot"',
            '.user.type == "Bot"',
            "commit_id == $head",
            "CURRENT_HEAD",
            "EXPECTED_HEAD",
            "headRefOid",
            "isDraft",
            "GRAPH_STATE",
            "CURRENT_STATE",
            "'OPEN'",
            "queue-postcheck.json",
            "queue-after-dequeue.json",
            "queue absence verified",
        )
        for marker in required:
            self.assertIn(marker, self.source, marker)

    def test_draft_deferral_is_complete_and_fail_closed(self) -> None:
        guard = re.compile(
            r'if \[ "\$CURRENT_DRAFT" = \'true\' \]; then\s+'
            r'echo "Gate run .* queue request deferred"\s+'
            r'exit 0\s+fi\s+'
            r'\[ "\$CURRENT_DRAFT" = \'false\' \]',
            re.S,
        )
        self.assertRegex(self.source, guard)

    def test_is_same_repository_only_and_does_not_expose_token(self) -> None:
        required = (
            '.head.repo.full_name == $repository',
            "trusted_default_branch_controller",
            "direct_merge_attempted",
            "bypass_used",
            "token_value_recorded",
        )
        for marker in required:
            self.assertIn(marker, self.source, marker)
        self.assertNotIn("set -x", self.source)
        self.assertNotIn("echo $GH_TOKEN", self.source)
        self.assertNotIn('echo "$GH_TOKEN"', self.source)

    def test_receipt_is_retained_and_never_claims_a_merge(self) -> None:
        self.assertIn("retention-days: 90", self.source)
        self.assertIn("merge-queue-enqueue-${{ github.run_id }}", self.source)
        self.assertIn("merge_performed", self.source)
        self.assertIn("false", self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
