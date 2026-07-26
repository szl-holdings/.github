#!/usr/bin/env python3
from __future__ import annotations

import os
import pathlib
import sys
import unittest
from unittest.mock import patch

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from final_estate_reconciliation_v5 import evaluate_upstream_readiness


class FinalEstateUpstreamTests(unittest.TestCase):
    def test_successful_readiness_workflow_passes(self) -> None:
        with patch.dict(
            os.environ,
            {
                "UPSTREAM_WORKFLOW": "HF Release Readiness Terminal",
                "UPSTREAM_CONCLUSION": "success",
                "UPSTREAM_RUN_URL": "https://github.com/example/actions/runs/1",
            },
            clear=False,
        ):
            gate = evaluate_upstream_readiness()
        self.assertTrue(gate.ok)
        self.assertTrue(gate.evidence["workflow_run_bound"])
        self.assertEqual(gate.evidence["conclusion"], "success")

    def test_failed_or_missing_readiness_conclusion_fails_closed(self) -> None:
        for conclusion in ("failure", "cancelled", ""):
            with self.subTest(conclusion=conclusion):
                with patch.dict(
                    os.environ,
                    {
                        "UPSTREAM_WORKFLOW": "HF Release Readiness Terminal",
                        "UPSTREAM_CONCLUSION": conclusion,
                    },
                    clear=False,
                ):
                    gate = evaluate_upstream_readiness()
                self.assertFalse(gate.ok)

    def test_direct_manual_evaluation_keeps_issue_evidence_authoritative(self) -> None:
        clean = dict(os.environ)
        clean.pop("UPSTREAM_WORKFLOW", None)
        clean.pop("UPSTREAM_CONCLUSION", None)
        clean.pop("UPSTREAM_RUN_URL", None)
        with patch.dict(os.environ, clean, clear=True):
            gate = evaluate_upstream_readiness()
        self.assertTrue(gate.ok)
        self.assertFalse(gate.evidence["workflow_run_bound"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
