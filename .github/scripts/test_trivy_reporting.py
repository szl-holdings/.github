#!/usr/bin/env python3
"""Exercise missing, failed, and authentic empty scanner reports offline."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("trivy_reporting.py")
WORKFLOW = Path(__file__).resolve().parents[1] / "workflows" / "trivy.yml"


class TrivyReportingTests(unittest.TestCase):
    def run_report(self, outcome, content, expected):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "trivy-results.sarif"
            if content is not None:
                report.write_bytes(content)
            env = {
                **os.environ,
                "TRIVY_SCAN_OUTCOME": outcome,
                "GITHUB_OUTPUT": str(root / "output"),
                "GITHUB_STEP_SUMMARY": str(root / "summary"),
            }
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "report"], cwd=root, env=env,
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "output").read_text(), f"available={str(expected).lower()}\n")
            self.assertEqual(report.read_bytes() if report.exists() else None, content)
            if expected:
                self.assertIn("**available**", (root / "summary").read_text())
                self.assertNotIn("::warning::", result.stdout)
            else:
                self.assertIn("**unavailable**", (root / "summary").read_text())
                self.assertIn("::warning::", result.stdout)

    def test_failed_scan_without_output_stays_unavailable(self):
        self.run_report("failure", None, False)

    def test_failed_scan_with_partial_output_is_not_uploaded(self):
        self.run_report("failure", b'{"version":"2.1.0","runs":[]}', False)

    def test_success_without_output_stays_unavailable(self):
        self.run_report("success", None, False)

    def test_skipped_scan_does_not_reuse_existing_file(self):
        self.run_report("skipped", b'{"version":"2.1.0","runs":[]}', False)

    def test_successful_empty_findings_are_preserved(self):
        payload = {"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "Trivy"}}, "results": []}]}
        self.run_report("success", json.dumps(payload).encode(), True)

    def test_successful_findings_are_preserved(self):
        payload = {"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "Trivy"}}, "results": [{"ruleId": "test-finding"}]}]}
        self.run_report("success", json.dumps(payload).encode(), True)

    def test_invalid_or_empty_file_is_not_an_authentic_report(self):
        for content in (b"", b"partial", b"{}", b"[]", b'{"version":"2.1.0","runs":null}'):
            with self.subTest(content=content):
                self.run_report("success", content, False)

    def test_prepare_removes_stale_result_before_scanning(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "trivy-results.sarif"
            report.write_text("stale")
            subprocess.run([sys.executable, str(SCRIPT), "prepare"], cwd=directory, check=True)
            self.assertFalse(report.exists())
            subprocess.run([sys.executable, str(SCRIPT), "prepare"], cwd=directory, check=True)

    def test_workflow_keeps_authoritative_gate_and_gates_upload(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        upload = text.split("      - name: Upload SARIF to Code Scanning\n", 1)[1].split("      - name:", 1)[0]
        self.assertIn("if: always() && steps.sarif-report.outputs.available == 'true'", upload)
        gate = text.split("      - name: Trivy fail gate (CRITICAL+HIGH)\n", 1)[1]
        self.assertIn("if: always()", gate)
        self.assertIn("exit-code: '1'", gate)
        self.assertNotIn("continue-on-error", gate)
        self.assertLess(text.index("trivy_reporting.py prepare"), text.index("id: sarif-scan"))


if __name__ == "__main__":
    unittest.main()
