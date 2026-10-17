#!/usr/bin/env python3
"""Event matrix for supported-kernel release finalization.

Automatic events keep the offline contract checks. Only an explicit
workflow_dispatch passes --publish. This file does not publish.
"""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "hf-release-finalization.yml"
BADGE = ROOT / ".github" / "workflows" / "hf-dataset-badge-refresh.yml"


class FinalizerPublicationEvents(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_publish_is_only_the_manual_dispatch_branch(self) -> None:
        self.assertEqual(self.text.count("--publish"), 1)
        guard = 'if [ "${GITHUB_EVENT_NAME}" = "workflow_dispatch" ]; then'
        publish = self.text.index("args+=(--publish)")
        self.assertLess(self.text.index(guard), publish)
        self.assertIn("schedule:", self.text)
        self.assertIn('cron: "3 */6 * * *"', self.text)
        self.assertIn("repository_dispatch:", self.text)
        self.assertIn("workflow_dispatch: {}", self.text)
        self.assertNotIn("github.event_name != 'pull_request'", self.text)

    def test_offline_contract_command_includes_this_file(self) -> None:
        self.assertIn(
            "python .github/scripts/test_hf_release_finalization_events.py",
            self.text,
        )

    def test_badge_schedule_is_not_part_of_this_change(self) -> None:
        badge = BADGE.read_text(encoding="utf-8")
        self.assertIn("schedule:", badge)
        self.assertNotIn("--publish", self.text.split("workflow_dispatch: {}", 1)[0])


if __name__ == "__main__":
    unittest.main()
