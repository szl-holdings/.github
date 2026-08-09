#!/usr/bin/env python3
"""Static contract for activating the trusted multi-event DCO workflow."""

from pathlib import Path
import unittest


class DcoActivationWorkflowTests(unittest.TestCase):
    def test_workflow_static_contract(self) -> None:
        workflow = (
            Path(__file__).resolve().parents[1] / "workflows" / "dco.yml"
        ).read_text(encoding="utf-8")
        for marker in (
            "pull_request" + "_target:",
            "merge_" + "group:",
            "types: [checks_requested]",
            "persist-credentials: false",
            "format('refs/pull/{0}/head', github.event.pull_request.number)",
            "github.event.pull_request.base.sha",
            "github.event.pull_request.head.sha",
            "EXPECTED_BASE_SHA:",
            "EXPECTED_HEAD_SHA:",
            "statuses: write",
            "statuses/$EXPECTED_HEAD_SHA",
            'state="failure"',
            'exit "$dco_exit"',
            "git -C \"$GITHUB_WORKSPACE/candidate\" fetch",
            "trusted/.github/scripts/dco_check.py",
        ):
            self.assertIn(marker, workflow)
        checker = (Path(__file__).resolve().parent / "dco_check.py").read_text(
            encoding="utf-8"
        )
        for marker in (
            'group.get("base_sha")',
            'group.get("head_sha")',
            '"merge-base", "--is-ancestor"',
            '"interpret-trailers", "--parse"',
        ):
            self.assertIn(marker, checker)
        self.assertNotIn("\n  pull_request:\n", workflow)
        self.assertNotIn("workflow_" + "dispatch:", workflow)
        self.assertNotIn("github.event_name != 'pull_request'", workflow)
        release_ruleset = (
            Path(__file__).resolve().parents[2]
            / ".governance"
            / "ruleset-release.json"
        ).read_text(encoding="utf-8")
        self.assertIn('"context": "DCO sign-off check"', release_ruleset)
        self.assertIn('"integration_id": 15368', release_ruleset)


if __name__ == "__main__":
    unittest.main()
