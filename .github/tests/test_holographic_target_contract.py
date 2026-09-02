#!/usr/bin/env python3
"""Network-free tests for generated target-repository experience gates."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / ".github" / "scripts" / "holographic_target_contract.py"
spec = importlib.util.spec_from_file_location("holographic_target_contract_test", MODULE)
assert spec and spec.loader
targets = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = targets
spec.loader.exec_module(targets)


class TargetContractTests(unittest.TestCase):
    def test_contract_is_validly_scoped_local_and_responsive(self) -> None:
        workflow = targets.target_contract("app.py")
        self.assertIn("name: SZL Public Experience v3 Contract", workflow)
        self.assertIn('SZL_HOLO_ENTRYPOINT: "app.py"', workflow)
        self.assertIn("node', '--check", workflow)
        self.assertIn("py_compile.compile", workflow)
        for marker in (
            "SZL Public Experience v3",
            "--szl-touch-target",
            "100dvh",
            "safe-area-inset",
            "overflow-x: clip",
            "max-width: 479px",
            "min-width: 768px",
            "min-width: 1440px",
            "min-width: 1920px",
            "min-width: 2560px",
            "prefers-reduced-motion",
            "prefers-contrast",
            "forced-colors",
            "git diff --check",
        ):
            self.assertIn(marker, workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("curl ", workflow)
        self.assertNotIn("wget ", workflow)

    def test_entrypoint_is_json_escaped(self) -> None:
        workflow = targets.target_contract('path/with"quote.py')
        self.assertIn('SZL_HOLO_ENTRYPOINT: "path/with\\"quote.py"', workflow)

    def test_install_wraps_exactly_once(self) -> None:
        class Change:
            def __init__(self, path, content):
                self.path = path
                self.content = content

        calls = []

        def original(*args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(status="planned", entrypoint="app.py", changes=[])

        core = SimpleNamespace(plan_repository=original, Change=Change)
        targets.install(core)
        first = core.plan_repository("x")
        self.assertEqual(len(first.changes), 1)
        self.assertEqual(first.changes[0].path, ".github/workflows/szl-holographic-space-v2.yml")
        targets.install(core)
        second = core.plan_repository("y")
        self.assertEqual(len(second.changes), 1)
        self.assertEqual(len(calls), 2)

    def test_existing_workflow_is_replaced_not_duplicated(self) -> None:
        class Change:
            def __init__(self, path, content):
                self.path = path
                self.content = content

        path = ".github/workflows/szl-holographic-space-v2.yml"
        core = SimpleNamespace(
            plan_repository=lambda *args, **kwargs: SimpleNamespace(
                status="planned",
                entrypoint=None,
                changes=[Change(path, "old")],
            ),
            Change=Change,
        )
        targets.install(core)
        plan = core.plan_repository()
        self.assertEqual([change.path for change in plan.changes], [path])
        self.assertIn("SZL Public Experience v3 Contract", plan.changes[0].content)

    def test_nonplanned_repository_is_not_modified(self) -> None:
        class Change:
            def __init__(self, path, content):
                self.path = path
                self.content = content

        core = SimpleNamespace(
            plan_repository=lambda *args, **kwargs: SimpleNamespace(
                status="report-only", entrypoint=None, changes=[]
            ),
            Change=Change,
        )
        targets.install(core)
        plan = core.plan_repository()
        self.assertEqual(plan.changes, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
