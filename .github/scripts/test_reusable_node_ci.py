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


class PackageManagerInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def run_body(self, name, manager, *, lock=False, status=0):
        step, body = step_body(self.source, f"      - name: {name}\n")
        self.assertIn("PACKAGE_MANAGER: ${{ inputs.package-manager }}", step)
        self.assertNotIn("${{ inputs.package-manager }}", body)
        with tempfile.TemporaryDirectory(prefix="node-ci-input-") as directory:
            root = Path(directory)
            for binary_name in ("npm", "pnpm", "yarn"):
                binary = root / binary_name
                binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$INVOCATION"\nexit "$MANAGER_STATUS"\n', encoding="utf-8")
                binary.chmod(0o755)
            if lock:
                for filename in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock"):
                    (root / filename).touch()
            invocation, output, marker = (root / name for name in ("invocation", "output", "injected"))
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"],
                       PACKAGE_MANAGER=manager, HAS_LOCKFILE=str(lock).lower(),
                       MANAGER_STATUS=str(status), INVOCATION=str(invocation),
                       GITHUB_OUTPUT=str(output), INJECTION_MARKER=str(marker))
            result = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", body],
                                    cwd=root, env=env, text=True, capture_output=True, timeout=15)
            return (result, invocation.read_text() if invocation.exists() else None,
                    output.read_text() if output.exists() else None, marker.exists())

    def test_validation_precedes_installation_and_checkout(self):
        position = self.source.index("      - name: Validate package manager\n")
        for name in ("Harden runner", "Checkout", "Detect lockfile", "Install dependencies"):
            self.assertLess(position, self.source.index(f"      - name: {name}\n"))
        step, _ = step_body(self.source, "      - name: Validate package manager\n")
        self.assertIn("if: steps.skip.outputs.enabled == 'true'", step)

    def test_supported_managers_are_accepted(self):
        for manager in ("npm", "pnpm", "yarn"):
            with self.subTest(manager=manager):
                result, invocation, _, marker = self.run_body("Validate package manager", manager)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIsNone(invocation)
                self.assertFalse(marker)

    def test_unsupported_managers_are_rejected_without_shell_execution(self):
        for manager in ("", "bun", "/bin/true", "npm --version", "NPM",
                        '$(touch "$INJECTION_MARKER")', '`touch "$INJECTION_MARKER"`',
                        'npm"; touch "$INJECTION_MARKER"; #'):
            with self.subTest(manager=manager):
                result, invocation, _, marker = self.run_body("Validate package manager", manager)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(invocation)
                self.assertFalse(marker)

    def test_detection_and_installation_treat_input_as_data(self):
        for step in ("Detect lockfile", "Install dependencies"):
            for manager in ('$(touch "$INJECTION_MARKER")', '`touch "$INJECTION_MARKER"`',
                            'npm"; touch "$INJECTION_MARKER"; #'):
                with self.subTest(step=step, manager=manager):
                    _, invocation, _, marker = self.run_body(step, manager)
                    self.assertIsNone(invocation)
                    self.assertFalse(marker)

    def test_lockfile_detection_preserves_manager_mapping(self):
        for manager, filename in (("npm", "package-lock.json"), ("pnpm", "pnpm-lock.yaml"), ("yarn", "yarn.lock")):
            for lock in (False, True):
                with self.subTest(manager=manager, lock=lock):
                    result, invocation, output, marker = self.run_body("Detect lockfile", manager, lock=lock)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(output, f"found=true\nfile={filename}\n" if lock else "found=false\n")
                    self.assertIsNone(invocation)
                    self.assertFalse(marker)

    def test_install_modes_and_failures_are_preserved(self):
        for manager, locked_args, unlocked_args in (("npm", "ci\n", "install\n--no-package-lock\n"),
                                                  ("pnpm", "install\n--frozen-lockfile\n", "install\n--no-frozen-lockfile\n"),
                                                  ("yarn", "install\n--frozen-lockfile\n", "install\n")):
            for lock in (False, True):
                for status in (0, 37):
                    with self.subTest(manager=manager, lock=lock, status=status):
                        result, invocation, _, marker = self.run_body("Install dependencies", manager, lock=lock, status=status)
                        self.assertEqual(result.returncode, status, result.stderr)
                        self.assertEqual(invocation, locked_args if lock else unlocked_args)
                        self.assertFalse(marker)


if __name__ == "__main__":
    unittest.main()
