#!/usr/bin/env python3
"""Network-free tests for reusable_workflow_target_check.py."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
from io import BytesIO, StringIO
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError


_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "reusable_workflow_target_check.py")
_SPEC = importlib.util.spec_from_file_location("reusable_workflow_target_check", _SCRIPT)
assert _SPEC and _SPEC.loader
check = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = check
_SPEC.loader.exec_module(check)


PIN = "a" * 40


class TestReusableWorkflowTargetCheck(unittest.TestCase):
    @contextmanager
    def workflow_dir(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in files.items():
                (root / name).write_text(content, encoding="utf-8")
            yield root

    def test_valid_pinned_target_passes_and_is_probed_once(self):
        target = f"szl-holdings/.github/.github/workflows/doctrine-check.yml@{PIN}"
        with self.workflow_dir(
            {
                "one.yml": f"jobs:\n  check:\n    uses: {target}\n",
                "two.yaml": f"jobs:\n  check:\n    uses: \"{target}\" # pinned\n",
            }
        ) as root:
            probed = []
            result = check.validate_workflows(
                root, lambda call: probed.append(call.target) or True
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.checked_targets, 1)
        self.assertEqual(probed, [target])

    def test_branch_ref_fails_without_network_probe(self):
        target = "szl-holdings/.github/.github/workflows/doctrine-check.yml@main"
        with self.workflow_dir({"caller.yml": f"jobs:\n  check:\n    uses: {target}\n"}) as root:
            result = check.validate_workflows(
                root, lambda _call: self.fail("unpinned ref must not be probed")
            )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("40-character", result.violations[0].message)

    def test_missing_target_fails_at_pinned_sha(self):
        target = f"szl-holdings/.github/.github/workflows/missing.yml@{PIN}"
        with self.workflow_dir({"caller.yml": f"jobs:\n  check:\n    uses: {target}\n"}) as root:
            result = check.validate_workflows(root, lambda _call: False)

        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.checked_targets, 1)
        self.assertIn("does not exist", result.violations[0].message)

    def test_api_failure_is_unavailable_not_missing(self):
        target = f"szl-holdings/.github/.github/workflows/check.yml@{PIN}"

        def unavailable(_call):
            raise check.VerificationUnavailable("HTTP 403")

        with self.workflow_dir({"caller.yml": f"jobs:\n  check:\n    uses: {target}\n"}) as root:
            result = check.validate_workflows(root, unavailable)

        self.assertEqual(result.exit_code, 2)
        self.assertFalse(result.violations)
        self.assertIn("HTTP 403", result.unavailable[0].message)

    def test_ordinary_actions_local_calls_and_comments_are_ignored(self):
        content = f"""
jobs:
  check:
    # uses: szl-holdings/.github/.github/workflows/ignored.yml@{PIN}
    steps:
      - uses: actions/checkout@{PIN}
  local:
    uses: ./.github/workflows/local.yml
"""
        with self.workflow_dir({"caller.yml": content}) as root:
            result = check.validate_workflows(
                root, lambda _call: self.fail("no remote target should be probed")
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.checked_targets, 0)

    def test_malformed_remote_workflow_reference_fails(self):
        value = f"szl-holdings/.github/.github/workflows/nested/check.yml@{PIN}"
        with self.workflow_dir({"caller.yml": f"jobs:\n  check:\n    uses: {value}\n"}) as root:
            result = check.validate_workflows(root, lambda _call: True)

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Malformed", result.violations[0].message)

    def test_contents_api_maps_404_to_missing_and_other_errors_to_unavailable(self):
        call = check.WorkflowCall(
            source=Path("caller.yml"),
            line=3,
            value="unused",
            owner="szl-holdings",
            repo=".github",
            workflow="doctrine-check.yml",
            ref=PIN,
        )
        not_found = HTTPError("https://api.github.com", 404, "Not Found", {}, BytesIO())
        forbidden = HTTPError("https://api.github.com", 403, "Forbidden", {}, BytesIO())

        with mock.patch.object(check, "urlopen", side_effect=not_found):
            self.assertFalse(check.github_target_exists(call))
        with mock.patch.object(check, "urlopen", side_effect=forbidden):
            with self.assertRaises(check.VerificationUnavailable):
                check.github_target_exists(call)

    def test_successful_cli_output_is_ascii_safe(self):
        with self.workflow_dir({}) as root:
            output = StringIO()
            with redirect_stdout(output):
                exit_code = check.main(["--workflow-dir", str(root)])

        self.assertEqual(exit_code, 0)
        self.assertIn("PASS: Verified 0", output.getvalue())
        output.getvalue().encode("ascii")


if __name__ == "__main__":
    unittest.main()
