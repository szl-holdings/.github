#!/usr/bin/env python3
"""Self-test for the org CI health digest job.

``ci_health_digest.py`` sweeps the org's repos and upserts a rolling "CI Health
Digest" issue. Its one load-bearing safety contract is the token preflight: the
built-in Actions ``GITHUB_TOKEN`` cannot read other repos' runs, so when NO
usable token is present the digest must FAIL LOUD (exit 1) rather than silently
sweep nothing and post a false "0 actionable / 0 red" all-clear.

This stubs the GitHub/ntfy network surface so it runs offline and pins:

  1. no token (module-level TOKEN falsy)                       -> exit 1
  2. a usable token, clean sweep                               -> exit 0 (no raise)
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "ci_health_digest.py")

_spec = importlib.util.spec_from_file_location("ci_health_digest", _MODULE_PATH)
assert _spec and _spec.loader
chd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chd)


def _run_main(*, token, repos=()):
    """Run ``chd.main()`` with TOKEN forced and the network stubbed. Returns the
    exit code: 0 when main() completes (returns None), or the SystemExit code."""
    saved = {name: getattr(chd, name) for name in
             ("TOKEN", "list_repos", "repo_reds", "upsert_issue", "maybe_ntfy")}
    saved_summary = os.environ.pop("GITHUB_STEP_SUMMARY", None)
    try:
        chd.TOKEN = token
        chd.list_repos = lambda: list(repos)
        chd.repo_reds = lambda item: (item, None)
        chd.upsert_issue = lambda body: "issue upserted"
        chd.maybe_ntfy = lambda act, total: None
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            try:
                chd.main()
                return 0
            except SystemExit as e:
                return e.code if isinstance(e.code, int) else 1
    finally:
        for name, val in saved.items():
            setattr(chd, name, val)
        if saved_summary is not None:
            os.environ["GITHUB_STEP_SUMMARY"] = saved_summary


class TestCiHealthDigestGuard(unittest.TestCase):
    def test_no_token_exit_1(self):
        """No usable token -> exit 1, never a silent green all-clear digest."""
        self.assertEqual(_run_main(token=""), 1)

    def test_none_token_exit_1(self):
        self.assertEqual(_run_main(token=None), 1)

    def test_healthy_clean_sweep_passes(self):
        """A usable token with a clean sweep completes without raising."""
        self.assertEqual(_run_main(token="tok", repos=[]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
