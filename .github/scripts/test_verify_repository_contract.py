#!/usr/bin/env python3
"""Negative controls for the root repository verification contract."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from verify_repository_contract import SCHEMA, validate


class RepositoryVerificationContractTests(unittest.TestCase):
    def make_repo(self, root: Path) -> None:
        for path in (
            ".github/scripts",
            ".github/tests",
            ".github/workflows",
            "tests",
            "config",
            "requirements",
        ):
            (root / path).mkdir(parents=True, exist_ok=True)
        (root / ".python-version").write_text("3.12.14\n", encoding="utf-8")
        (root / "requirements/fixture.lock").write_text("fixture==1 --hash=sha256:00\n", encoding="utf-8")
        (root / ".github/scripts/test_direct.py").write_text(
            "import test_helper\n", encoding="utf-8"
        )
        (root / ".github/scripts/test_helper.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / ".github/workflows/tests.yml").write_text(
            "python-version: '3.12.14'\n"
            "run: python3 .github/scripts/test_direct.py --require-hashes "
            "-r requirements/fixture.lock\n",
            encoding="utf-8",
        )
        (root / "Makefile").write_text(
            "verify:\n\tpython3 -I -P .github/scripts/verify_repository_contract.py\n",
            encoding="utf-8",
        )
        contract = {
            "schema": SCHEMA,
            "python_version": "3.12.14",
            "test_roots": [".github/scripts", ".github/tests", "tests"],
            "indirect_tests": [{
                "path": ".github/scripts/test_helper.py",
                "loaded_by": ".github/scripts/test_direct.py",
                "reason": "fixture loader",
            }],
            "dependency_contracts": [{
                "path": "requirements/fixture.lock",
                "consumer_workflow": ".github/workflows/tests.yml",
                "required_tokens": ["--require-hashes", "-r requirements/fixture.lock"],
                "scope": "fixture",
            }],
        }
        (root / "config/repository-verification.json").write_text(
            json.dumps(contract), encoding="utf-8"
        )

    def mutate_contract(self, root: Path, callback) -> None:
        path = root / "config/repository-verification.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        callback(value)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_complete_contract_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_repo(root)
            self.assertTrue(validate(root)["ok"])

    def test_uncovered_test_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_repo(root)
            (root / "tests/test_orphan.py").write_text("pass\n", encoding="utf-8")
            result = validate(root)
            self.assertFalse(result["ok"])
            self.assertIn("test has no workflow execution path: tests/test_orphan.py", result["errors"])

    def test_path_trigger_is_not_an_execution_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_repo(root)
            (root / "tests/test_trigger_only.py").write_text("pass\n", encoding="utf-8")
            workflow = root / ".github/workflows/tests.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8")
                + "paths:\n  - tests/test_trigger_only.py\n",
                encoding="utf-8",
            )
            result = validate(root)
            self.assertFalse(result["ok"])
            self.assertIn(
                "test has no workflow execution path: tests/test_trigger_only.py",
                result["errors"],
            )

    def test_unittest_discovery_pattern_is_an_execution_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_repo(root)
            (root / "tests/test_pattern_contract.py").write_text("pass\n", encoding="utf-8")
            workflow = root / ".github/workflows/tests.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8")
                + "run: >-\n"
                + "  python3 -m unittest discover\n"
                + "  -s tests\n"
                + "  -p 'test_pattern*.py'\n",
                encoding="utf-8",
            )
            self.assertTrue(validate(root)["ok"])

    def test_toolchain_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_repo(root)
            (root / ".python-version").write_text("3.12.13\n", encoding="utf-8")
            result = validate(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any(".python-version mismatch" in error for error in result["errors"]))

    def test_runtime_toolchain_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_repo(root)
            result = validate(root, runtime_version="3.12.13")
            self.assertFalse(result["ok"])
            self.assertIn(
                "runtime Python mismatch: contract='3.12.14' runtime='3.12.13'",
                result["errors"],
            )

    def test_stale_indirect_entry_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_repo(root)
            workflow = root / ".github/workflows/tests.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8")
                + "run: python3 .github/scripts/test_helper.py\n",
                encoding="utf-8",
            )
            result = validate(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("must not be allowlisted as indirect" in error for error in result["errors"]))

    def test_missing_dependency_token_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_repo(root)
            workflow = root / ".github/workflows/tests.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace("--require-hashes ", ""),
                encoding="utf-8",
            )
            result = validate(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("missing token '--require-hashes'" in error for error in result["errors"]))

    def test_indirect_loader_must_import_module(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_repo(root)
            (root / ".github/scripts/test_direct.py").write_text("pass\n", encoding="utf-8")
            result = validate(root)
            self.assertFalse(result["ok"])
            self.assertTrue(any("does not import test_helper" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
