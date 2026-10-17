"""Event matrix for the LLM Router flagship workflow.

Automatic events may validate the card. Only a manual workflow_dispatch
runs the apply job. This file does not grant a publish, a restart, or a
visibility change.
"""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "enforce-llm-router-flagship-card.yml"


class FlagshipPublicationEvents(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.validate, self.enforce = self.text.split("\n  enforce:\n", 1)

    def test_automatic_events_only_validate(self):
        self.assertIn("if: github.event_name != 'workflow_dispatch'", self.validate)
        self.assertNotIn("--apply", self.validate)
        self.assertNotIn("HF_TOKEN", self.validate)
        self.assertNotIn("restart_space", self.validate)
        self.assertNotIn("update_repo_settings", self.validate)
        self.assertIn("schedule:", self.text)
        self.assertIn('cron: "17 8 * * *"', self.text)

    def test_manual_dispatch_is_the_only_apply_job(self):
        self.assertIn("if: github.event_name == 'workflow_dispatch'", self.enforce)
        self.assertEqual(self.text.count("--apply"), 1)
        self.assertIn("--apply", self.enforce)
        self.assertIn("HF_TOKEN", self.enforce)
        self.assertNotIn("github.event_name != 'pull_request'", self.text)

    def test_publication_consequences_stay_in_the_manual_job(self):
        self.assertIn("--wait-seconds 900", self.enforce)
        self.assertNotIn("--wait-seconds 900", self.validate)
        self.assertIn("contents: read", self.text)


if __name__ == "__main__":
    unittest.main()
