#!/usr/bin/env python3
"""Static contract for protected solo-builder provenance validation."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "solo-builder-provenance.yml"


class SoloBuilderProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_protected_exact_head_contract(self) -> None:
        for marker in (
            "name: Required solo-builder provenance",
            "pull_request" + "_target:",
            "merge_group:",
            "permissions: {}",
            "pull-request-provenance:",
            "merge-group-provenance:",
            "EXPECTED_BASE_REPOSITORY:",
            "EXPECTED_BASE_SHA:",
            "EXPECTED_HEAD_REPOSITORY:",
            "EXPECTED_HEAD_SHA:",
            "szl-holdings/*",
            '.state == "open"',
            ".draft == false",
            ".base.sha == $base_sha",
            ".head.sha == $head_sha",
            "git/ref/heads/$EXPECTED_BASE_REF",
            "merge_base_commit.sha == $base",
            "gh-readonly-queue/main/pr-",
        ):
            self.assertIn(marker, self.text)

    def test_candidate_code_and_credentials_are_never_consumed(self) -> None:
        self.assertNotRegex(self.text, r"(?m)^\s*(?:-\s*)?uses:\s")
        for forbidden in (
            "actions/checkout",
            "persist-credentials",
            "GITHUB_WORKSPACE",
            "secrets.",
            "contents: write",
            "statuses: write",
            "id-token:",
            "workflow_dispatch:",
            "\n  push:\n",
            "Signed-" + "off-by",
        ):
            self.assertNotIn(forbidden, self.text)

    def test_only_governed_bases_and_events_are_admitted(self) -> None:
        self.assertIn("main|release/*", self.text)
        self.assertIn('test "$EXPECTED_BASE_REF" = "refs/heads/main"', self.text)
        self.assertIn('test "$EXPECTED_ACTION" = "checks_requested"', self.text)
        self.assertEqual(self.text.count("pull_request" + "_target:"), 1)
        self.assertEqual(self.text.count("merge_group:"), 1)


if __name__ == "__main__":
    unittest.main()
