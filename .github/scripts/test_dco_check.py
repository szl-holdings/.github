#!/usr/bin/env python3
"""Network-free regression fixtures for the fail-closed DCO policy."""

from __future__ import annotations

import importlib.util
import json
import os
import urllib.error
import unittest


_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "dco_check.py")
_spec = importlib.util.spec_from_file_location("dco_check", _MODULE_PATH)
assert _spec and _spec.loader
dco = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dco)


def _commit(char, message, *, files=None):
    return {
        "sha": char * 40,
        "commit": {"message": message},
        "files": [] if files is None else files,
    }


UNSIGNED_EMPTY_COMMIT = _commit("a", "chore(ci): retrigger checks", files=[])
UNSIGNED_MERGE_COMMIT = _commit(
    "b",
    "Merge branch 'feature/dco-bypass'\n\nSubstantive unsigned merge.",
    files=["governance/policy.yml"],
)
SIGNED_MULTI_COMMIT_PR = [
    _commit(
        "c",
        "fix(ci): fail closed\n\nSigned-off-by: Example One <one@example.com>",
    ),
    _commit(
        "d",
        "test(ci): add fixtures\n\nSigned-off-by: Example Two <two@example.com>",
    ),
]


class _Response:
    status = 200

    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self._body


class DcoPolicyTests(unittest.TestCase):
    def test_api_retrieval_failure_fails_closed(self):
        def unavailable(_request, timeout):
            self.assertEqual(timeout, 30)
            raise urllib.error.URLError("offline")

        with self.assertRaisesRegex(dco.DcoContractError, "retrieval failed"):
            dco.fetch_pr_commits(
                "https://api.github.com",
                "szl-holdings/.github",
                395,
                "governed-token",
                opener=unavailable,
            )

    def test_unexpectedly_empty_api_list_fails_closed(self):
        with self.assertRaisesRegex(dco.DcoContractError, "empty commit list"):
            dco.fetch_pr_commits(
                "https://api.github.com",
                "szl-holdings/.github",
                395,
                "governed-token",
                opener=lambda _request, timeout: _Response([]),
            )

    def test_unsigned_empty_commit_is_rejected(self):
        self.assertEqual(
            dco.commits_missing_signoff([UNSIGNED_EMPTY_COMMIT]),
            ["a" * 40],
        )

    def test_unsigned_substantive_merge_prefixed_commit_is_rejected(self):
        self.assertEqual(
            dco.commits_missing_signoff([UNSIGNED_MERGE_COMMIT]),
            ["b" * 40],
        )

    def test_fully_signed_multi_commit_pr_passes(self):
        self.assertEqual(dco.commits_missing_signoff(SIGNED_MULTI_COMMIT_PR), [])

    def test_workflow_has_no_message_or_zero_file_bypass(self):
        workflow_path = os.path.join(_HERE, "..", "workflows", "dco.yml")
        with open(workflow_path, encoding="utf-8") as handle:
            workflow = handle.read()

        self.assertIn("python3 .github/scripts/dco_check.py", workflow)
        self.assertIn("python3 .github/scripts/test_dco_check.py", workflow)
        for forbidden in (
            'grep -q "^Merge "',
            "file_count=",
            "assuming OK",
            "|| echo",
        ):
            self.assertNotIn(forbidden, workflow)


if __name__ == "__main__":
    unittest.main()
