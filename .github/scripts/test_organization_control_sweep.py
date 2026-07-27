#!/usr/bin/env python3
"""Source contract for the protected-main organization control sweep."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/organization-control-sweep.yml"


class OrganizationControlSweepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_runs_sweeps_only_outside_pull_requests(self) -> None:
        self.assertIn("github.event_name != 'pull_request'", self.source)
        self.assertIn("branches: [main]", self.source)
        self.assertIn("workflow_dispatch: {}", self.source)

    def test_executes_all_four_canonical_controls(self) -> None:
        required = (
            ".github/scripts/ci_health_digest.py",
            ".github/scripts/license_consistency.py",
            ".github/scripts/hf_license_consistency.py",
            ".github/scripts/public_repo_link_check.py",
            "--include-private",
            "--min-private 1",
            "--min-private 5",
            "--scan-docs",
            "--check-deep-links",
            "--fail-on-missing",
        )
        for marker in required:
            self.assertIn(marker, self.source, marker)

    def test_reports_are_immutable_and_not_pushed(self) -> None:
        self.assertIn("retention-days: 90", self.source)
        self.assertNotIn("git push", self.source)
        self.assertNotIn("git commit", self.source)
        self.assertNotIn("createPullRequest", self.source)

    def test_private_coverage_and_fail_closed_tokens_remain_explicit(self) -> None:
        required = (
            "secrets.SZL_GITHUB_TOKEN",
            "secrets.HF_ORG_TOKEN",
            "QILLQAQ_CLIENT_ID",
            "QILLQAQ_PRIVATE_KEY",
            "Enforce organization-health result",
            "Enforce GitHub-license result",
            "Enforce Hugging Face-license result",
            "Enforce public-link result",
        )
        for marker in required:
            self.assertIn(marker, self.source, marker)


if __name__ == "__main__":
    unittest.main(verbosity=2)
