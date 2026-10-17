"""Event matrix for the Adaptive Theatre finalizer.

Push and pull_request run the network-free contract only. The apply job
runs only for a manual dispatch with its apply input set. The default
input stays false.
"""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "finalize-hf-adaptive-theatre-v3.yml"


class TheatreFinalizerEvents(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.contract, self.finalize = self.text.split("\n  finalize:\n", 1)

    def test_automatic_events_do_not_apply(self):
        self.assertNotIn("--apply", self.contract)
        self.assertNotIn("ORG_ADMIN_TOKEN", self.contract)
        self.assertNotIn("github.event_name == 'push'", self.text)
        self.assertIn("pull_request:", self.text)
        self.assertIn("push:", self.text)

    def test_manual_apply_is_separate_and_defaults_off(self):
        self.assertIn(
            "if: ${{ github.event_name == 'workflow_dispatch' && inputs.apply }}",
            self.finalize,
        )
        self.assertEqual(self.text.count("--apply"), 1)
        self.assertIn("--apply", self.finalize)
        self.assertIn("default: false", self.text)
        self.assertNotIn("default: true", self.text)

    def test_publication_consequences(self):
        self.assertIn("Merge exact green application PRs", self.finalize)
        self.assertNotIn("restart_space", self.text)
        self.assertNotIn("visibility", self.text.lower())
        self.assertIn("contents: read", self.text)


if __name__ == "__main__":
    unittest.main()
