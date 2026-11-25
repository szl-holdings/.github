"""Regression: missing Hub runtime metadata must not masquerade as a stopped Space."""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_sibling(name):
    """Load the exact checked-out script without relaxing Python isolation."""
    path = Path(__file__).resolve().with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


governance_scorecard = _load_sibling("governance_scorecard")
hf_space_prober = _load_sibling("hf_space_prober")


class SpaceRuntimeEvidenceTests(unittest.TestCase):
    def test_unknown_is_separate_from_confirmed_nonrunning_without_greenwashing(self):
        assets = [
            {"id": "SZLHOLDINGS/no-stage", "private": False},
            {"id": "SZLHOLDINGS/paused", "private": False, "runtime": {"stage": "PAUSED"}},
            {"id": "SZLHOLDINGS/healthy", "private": False, "runtime": {"stage": "RUNNING"}},
            {"id": "SZLHOLDINGS/private", "private": True},
        ]
        with patch.object(hf_space_prober, "list_repos", return_value=(assets, 200)):
            rows, summary = hf_space_prober.probe("spaces", "SZLHOLDINGS", None, False)
        self.assertEqual(len(rows), 4)
        self.assertEqual(summary["public_not_running"], 2)  # existing fail-closed gate
        self.assertEqual(summary["public_runtime_unknown"], 1)
        self.assertEqual(summary["public_confirmed_not_running"], 1)
        self.assertIn("1 UNKNOWN, 1 confirmed non-RUNNING",
                      governance_scorecard.space_runtime_detail(summary))
        board = governance_scorecard.Board()
        board.add("hf.public_spaces_running", "huggingface",
                  summary["public_not_running"] == 0, governance_scorecard.MEASURED,
                  governance_scorecard.space_runtime_detail(summary))
        self.assertEqual(board.findings[0]["state"], "FAIL")

    def test_all_unknown_still_fails_closed(self):
        with patch.object(hf_space_prober, "list_repos", return_value=(
            [{"id": "SZLHOLDINGS/unknown", "private": False}], 200)):
            _, summary = hf_space_prober.probe("spaces", "SZLHOLDINGS", None, False)
        self.assertEqual(summary["public_not_running"], 1)
        self.assertEqual(summary["public_runtime_unknown"], 1)
        self.assertEqual(summary["public_confirmed_not_running"], 0)
        self.assertIn("not confirmed RUNNING",
                      governance_scorecard.space_runtime_detail(summary))

    def test_legacy_report_fallback_never_claims_stopped(self):
        self.assertEqual(
            governance_scorecard.space_runtime_detail({"public_not_running": 78}),
            "78 public Spaces not confirmed RUNNING (stage breakdown unavailable)",
        )


if __name__ == "__main__":
    unittest.main()
