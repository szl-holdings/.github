#!/usr/bin/env python3
"""Execute the reusable workflow's real stage body with inert package managers.

No dependency install or network call is performed. Missing, malformed or empty
enabled scripts must fail before a package manager runs; its own failure must
also remain a failure. Intentional opt-outs use the existing run-* inputs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reusable-node-ci.yml"
TASKS = ("lint", "typecheck", "test", "build")


def step_body(source: str, marker: str) -> tuple[str, str]:
    step = source.split(marker, 1)[1].split("\n      - name:", 1)[0]
    return step, textwrap.dedent(step.split("        run: |\n", 1)[1])


class EnabledStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("node") or not shutil.which("bash"):
            raise RuntimeError("Node and bash are required; this contract must not silently skip")
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.step, cls.script = step_body(cls.source, "      - name: Run ${{ matrix.task }}\n")

    def run_stage(self, manifest, *, task="test", manager="npm", status=0, raw=False):
        with tempfile.TemporaryDirectory(prefix="node-ci-contract-") as directory:
            root = Path(directory)
            if manifest is not None:
                (root / "package.json").write_text(manifest if raw else json.dumps(manifest), encoding="utf-8")
            binary = root / manager
            binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$INVOCATION"\nexit "$MANAGER_STATUS"\n', encoding="utf-8")
            binary.chmod(0o755)
            invocation = root / "invocation.txt"
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                       PACKAGE_MANAGER=manager, CI_TASK=task, INVOCATION=str(invocation),
                       MANAGER_STATUS=str(status))
            result = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", self.script],
                                    cwd=root, env=env, text=True, capture_output=True, timeout=15)
            return result, invocation.read_text() if invocation.exists() else None

    def assert_rejected(self, manifest, **kwargs):
        result, invocation = self.run_stage(manifest, **kwargs)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNone(invocation, "invalid manifests must never invoke the package manager")

    def test_each_enabled_missing_stage_fails(self):
        for task in TASKS:
            with self.subTest(task=task):
                self.assert_rejected({"scripts": {}}, task=task)

    def test_absent_manifest_fails(self):
        self.assert_rejected(None)

    def test_malformed_json_fails(self):
        self.assert_rejected("{broken", raw=True)

    def test_nonobject_manifest_fails(self):
        for raw in ("null", "[]", '"text"', "17"):
            with self.subTest(raw=raw):
                self.assert_rejected(raw, raw=True)

    def test_absent_scripts_fail(self):
        self.assert_rejected({"name": "no-scripts"})

    def test_invalid_script_tables_fail(self):
        for scripts in (None, [], "test", 1, True):
            with self.subTest(scripts=scripts):
                self.assert_rejected({"scripts": scripts})

    def test_empty_or_nonstring_scripts_fail(self):
        for script in ("", " \t\n", None, False, 42, [], {}):
            with self.subTest(script=script):
                self.assert_rejected({"scripts": {"test": script}})

    def test_other_script_does_not_satisfy_enabled_stage(self):
        self.assert_rejected({"scripts": {"build": "echo build"}})

    def test_each_valid_stage_invokes_each_manager_once(self):
        for task in TASKS:
            for manager in ("npm", "pnpm", "yarn"):
                with self.subTest(task=task, manager=manager):
                    result, invocation = self.run_stage({"scripts": {task: "echo fixture"}}, task=task, manager=manager)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(invocation, f"run\n{task}\n")

    def test_package_manager_failure_is_preserved(self):
        result, invocation = self.run_stage({"scripts": {"test": "exit 37"}}, status=37)
        self.assertEqual(result.returncode, 37)
        self.assertEqual(invocation, "run\ntest\n")

    def test_disabled_stage_is_an_explicit_opt_out(self):
        self.assertIn("if: steps.skip.outputs.enabled == 'true'", self.step)
        _, script = step_body(self.source, "      - name: Skip if disabled\n")
        for task in TASKS:
            with self.subTest(task=task), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "output"
                rendered = script.replace("${{ matrix.task }}", task)
                for name in TASKS:
                    rendered = rendered.replace("${{ inputs.run-" + name + " }}", "false")
                result = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", rendered],
                                        env=dict(os.environ, GITHUB_OUTPUT=str(output)),
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output.read_text(), "enabled=false\n")


if __name__ == "__main__":
    unittest.main()
