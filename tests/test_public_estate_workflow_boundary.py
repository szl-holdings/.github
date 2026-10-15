# Copyright 2026 SZL Holdings — SPDX-License-Identifier: Apache-2.0
"""Offline controls for exact source admission and non-executable result input."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/public-estate-convergence.yml"
SHA = "a" * 40


def shell_step(name: str) -> str:
    source = WORKFLOW.read_text(encoding="utf-8")
    marker = "      - name: " + name + "\n"
    if source.count(marker) != 1:
        raise AssertionError("expected one workflow step: " + name)
    block = source.split(marker, 1)[1].split("\n      - name:", 1)[0]
    return textwrap.dedent(block.split("        run: |\n", 1)[1])


class ProtectedSourceTests(unittest.TestCase):
    def run_guard(self, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            log = folder / "calls.jsonl"
            for name in ("git", "gh"):
                script = folder / name
                script.write_text(
                    "#!" + sys.executable + "\n"
                    "import json, os, pathlib, sys\n"
                    "name = pathlib.Path(sys.argv[0]).name\n"
                    "with open(os.environ['CALL_LOG'], 'a') as output:\n"
                    "    output.write(json.dumps([name] + sys.argv[1:]) + '\\n')\n"
                    "if name == 'gh' and os.environ.get('API_FAIL') == '1':\n"
                    "    raise SystemExit(2)\n"
                    "print(os.environ['CHECKOUT_SHA' if name == 'git' else 'MAIN_SHA'])\n",
                    encoding="utf-8",
                )
                script.chmod(0o700)
            env = {
                "PATH": str(folder) + os.pathsep + "/usr/bin:/bin",
                "GITHUB_REPOSITORY": "szl-holdings/.github",
                "GITHUB_REF": "refs/heads/main",
                "GITHUB_SHA": SHA,
                "CHECKOUT_SHA": SHA,
                "MAIN_SHA": SHA,
                "CALL_LOG": str(log),
                **overrides,
            }
            result = subprocess.run(
                ["/bin/bash", "-c", shell_step("Require exact protected main source")],
                cwd=folder, env=env, capture_output=True, text=True, check=False,
            )
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result.returncode, calls

    def test_exact_current_main_uses_one_read_only_ref_lookup(self):
        code, calls = self.run_guard()
        self.assertEqual(code, 0)
        self.assertEqual(calls, [
            ["git", "rev-parse", "--verify", "HEAD"],
            ["gh", "api", "repos/szl-holdings/.github/git/ref/heads/main", "--jq", ".object.sha"],
        ])

    def test_foreign_nonmain_and_malformed_event_fail_before_lookup(self):
        for overrides in (
            {"GITHUB_REPOSITORY": "foreign/repository"},
            {"GITHUB_REF": "refs/heads/candidate"},
            {"GITHUB_SHA": "main"},
            {"GITHUB_SHA": "A" * 40},
        ):
            with self.subTest(overrides=overrides):
                code, calls = self.run_guard(**overrides)
                self.assertNotEqual(code, 0)
                self.assertEqual(calls, [])

    def test_wrong_checkout_fails_before_remote_lookup(self):
        code, calls = self.run_guard(CHECKOUT_SHA="b" * 40)
        self.assertNotEqual(code, 0)
        self.assertEqual(calls, [["git", "rev-parse", "--verify", "HEAD"]])

    def test_stale_main_and_unavailable_readback_fail_closed(self):
        for overrides in ({"MAIN_SHA": "b" * 40}, {"MAIN_SHA": ""}, {"API_FAIL": "1"}):
            with self.subTest(overrides=overrides):
                code, calls = self.run_guard(**overrides)
                self.assertNotEqual(code, 0)
                self.assertEqual(len(calls), 2)


class ExitResultTests(unittest.TestCase):
    def test_result_is_data_and_only_known_terminal_codes_are_accepted(self):
        script = shell_step("Enforce canonical origins")
        self.assertNotIn("${{", script)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for value, expected in (
                ("0", 0), ("1", 1), ("2", 2), ("", 1), ("00", 1), ("256", 1),
                ("0; touch injected", 1), ("$(touch injected)", 1), ("0\nexit 0", 1),
            ):
                with self.subTest(value=value):
                    result = subprocess.run(
                        ["/bin/bash", "-c", script], cwd=folder,
                        env={"CONVERGENCE_EXIT_CODE": value}, capture_output=True,
                        text=True, check=False,
                    )
                    self.assertEqual(result.returncode, expected)
                    self.assertFalse((folder / "injected").exists())

    def test_existing_reconciliation_and_repair_authority_are_preserved(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        for marker in (
            "  issues: write", "default: true", "args+=(--repair)",
            "gh issue comment", "gh issue close", "gh issue create",
            "name: public-estate-convergence-v2\n",
            "ref: ${{ github.event.pull_request.head.sha || github.event.merge_group.head_sha || github.sha }}",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("          ref: main\n", source)

    def test_always_effects_cannot_run_after_source_admission_fails(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        for name in (
            "Publish exact origin summary", "Upload immutable convergence evidence",
            "Reconcile the public-origin drift issue",
        ):
            self.assertIn(
                "      - name: " + name + "\n"
                "        if: always() && steps.source.outcome == 'success'\n",
                source,
            )


if __name__ == "__main__":
    unittest.main()
