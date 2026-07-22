#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

terminal = importlib.import_module("hf_release_readiness_terminal")


class TerminalReleaseReadinessTests(unittest.TestCase):
    def test_selfcheck_parser_requires_positive_evidence(self) -> None:
        self.assertTrue(terminal._selfcheck_passed(True))
        self.assertTrue(terminal._selfcheck_passed({"ok": True}))
        self.assertTrue(terminal._selfcheck_passed({"checks": {"a": True, "b": True}}))
        self.assertFalse(terminal._selfcheck_passed(False))
        self.assertFalse(terminal._selfcheck_passed({"ok": False}))
        self.assertFalse(terminal._selfcheck_passed({"checks": {"a": True, "b": False}}))
        self.assertFalse(terminal._selfcheck_passed({"checks": {}}))

    def test_issue_body_contains_machine_readable_report(self) -> None:
        report = {
            "schema": "szl.hf-release-finalization/v1",
            "generation": "a" * 40,
            "generated_at": "2026-07-22T00:00:00+00:00",
            "publish": True,
            "results": {"dataset": {"revision": "b" * 40}},
            "summary": {"ok": 1, "warning": 0, "error": 0, "dry_run": 0},
        }
        body = terminal.issue_body(report, "https://github.com/szl-holdings/.github/actions/runs/1")
        self.assertIn(terminal.ISSUE_MARKER, body)
        start = body.index("```json") + len("```json")
        end = body.index("```", start)
        parsed = json.loads(body[start:end].strip())
        self.assertEqual(parsed["schema"], "szl.hf-release-finalization/v1")
        self.assertEqual(parsed["generation"], "a" * 40)

    def test_source_does_not_use_unsupported_kernel_repo_type_or_hf_mutation(self) -> None:
        source = (HERE / "hf_release_readiness_terminal.py").read_text(encoding="utf-8")
        forbidden = (
            'repo_type="kernel"',
            "repo_type='kernel'",
            "upload_file(",
            "upload_folder(",
            "create_repo(",
            "delete_repo(",
            "duplicate_repo(",
            "restart_space(",
        )
        for token in forbidden:
            self.assertNotIn(token, source)

    def test_report_shape_matches_final_estate_reconciler_expectations(self) -> None:
        report = {
            "schema": "szl.hf-release-finalization/v1",
            "publish": True,
            "summary": {"ok": 3, "warning": 0, "error": 0, "dry_run": 0},
            "results": {
                "dataset": {
                    "revision": "b" * 40,
                    "remote_file_count": 7,
                    "viewer_http_status": 200,
                },
                "kernels": {
                    repo_id: {
                        "revision": "c" * 40,
                        "remote_file_count": 10,
                        "selfcheck": {"ok": True},
                    }
                    for repo_id in terminal.KERNEL_IDS
                },
            },
        }
        dataset = report["results"]["dataset"]
        kernels = report["results"]["kernels"]
        self.assertEqual(dataset["viewer_http_status"], 200)
        self.assertGreater(dataset["remote_file_count"], 0)
        self.assertEqual(set(kernels), set(terminal.KERNEL_IDS))
        self.assertTrue(all(terminal.SHA40.fullmatch(v["revision"]) for v in kernels.values()))
        self.assertTrue(all(terminal._selfcheck_passed(v["selfcheck"]) for v in kernels.values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
