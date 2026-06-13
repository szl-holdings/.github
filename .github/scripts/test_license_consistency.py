#!/usr/bin/env python3
"""Self-test for the org license-claim consistency guard.

``license_consistency.py`` is a safety net: it fails the run when a public (or,
with ``--include-private``, private) repo's detected SPDX license drifts from
what its README/CITATION badge claims. Like its HF sibling it has a
false-green hazard — an ``--include-private`` sweep can silently collapse to
public-only and still report "0 drift" — plus the ordinary drift path itself
could be quietly weakened into a no-op by a refactor.

This stubs the GitHub API surface (``gh_whoami`` / ``gh_org_membership`` /
``list_org_repos`` / ``check_repo``) so it runs with NO network, and pins the
exit-code contract of ``main()``:

  1. no GitHub token at all                                     -> exit 2
  2. --include-private but the token fails whoami               -> exit 1
  3. --include-private + valid token but private_seen < floor   -> exit 1
  4. a real license-claim drift (an ERROR result)               -> exit 1
  5. healthy case (token ok, floor met, no drift)               -> exit 0

Stdlib ``unittest`` only — CI needs just a github-owned setup-python.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "license_consistency.py")

_spec = importlib.util.spec_from_file_location("license_consistency", _MODULE_PATH)
assert _spec and _spec.loader
lc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lc)

_TOKEN_ENV = ("GITHUB_TOKEN", "GH_TOKEN", "SZL_GITHUB_TOKEN")


def _ok_check(repo_obj, token, allow_entry):
    return {
        "repo": f"szl-holdings/{repo_obj['name']}", "status": "OK",
        "detected_spdx": "Apache-2.0", "allowlisted": False,
        "archived": bool(repo_obj.get("archived")), "errors": [], "warnings": [],
    }


def _err_check(repo_obj, token, allow_entry):
    r = _ok_check(repo_obj, token, allow_entry)
    r["status"] = "ERROR"
    r["errors"] = ["README badge claims MIT but detected SPDX is Apache-2.0"]
    return r


def _public_repos(n):
    return [{"name": f"pub-{i}", "private": False, "archived": False}
            for i in range(n)]


def _private_repos(n):
    return [{"name": f"priv-{i}", "private": True, "archived": False}
            for i in range(n)]


def _run_main(argv, *, token, whoami, membership, repos, list_errors=None,
              check=_ok_check):
    """Run ``lc.main()`` with the network surface stubbed. Returns the exit
    code (an int) or, when ``_token()`` aborts on a missing token, re-raises the
    ``SystemExit`` so the caller can assert its code."""
    saved = {name: getattr(lc, name) for name in
             ("gh_whoami", "gh_org_membership", "list_org_repos", "check_repo")}
    saved_env = {k: os.environ.get(k) for k in _TOKEN_ENV}
    saved_argv = sys.argv
    try:
        for k in _TOKEN_ENV:
            os.environ.pop(k, None)
        if token is not None:
            os.environ["GITHUB_TOKEN"] = token
        lc.gh_whoami = lambda t: whoami
        lc.gh_org_membership = lambda t, org: membership
        lc.list_org_repos = lambda org, t, inc_arch, inc_priv: (
            list(repos), list(list_errors or []))
        lc.check_repo = check
        sys.argv = ["license_consistency.py"] + argv
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return lc.main()
    finally:
        for name, fn in saved.items():
            setattr(lc, name, fn)
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.argv = saved_argv


_OK_WHOAMI = (True, {"login": "szl-bot"}, None)
_ALLOW = ["--allowlist", os.path.join(_HERE, "does-not-exist.json")]


class TestLicenseConsistencyGuard(unittest.TestCase):
    def test_missing_token_aborts_exit_2(self):
        """No token in any env var -> the guard must abort loudly (exit 2),
        never proceed token-less and report a meaningless green."""
        with self.assertRaises(SystemExit) as cm:
            _run_main(_ALLOW, token=None, whoami=_OK_WHOAMI,
                      membership=("active", None), repos=_public_repos(2))
        self.assertEqual(cm.exception.code, 2)

    def test_include_private_whoami_failure_fails(self):
        """--include-private with a token that fails whoami cannot be trusted to
        unlock private listings -> exit 1 (false-green prevention)."""
        rc = _run_main(
            _ALLOW + ["--include-private", "--min-private", "3"],
            token="tok", whoami=(False, None, "/user returned HTTP 401"),
            membership=("active", None), repos=_private_repos(5))
        self.assertEqual(rc, 1)

    def test_include_private_floor_unmet_fails(self):
        """THE false-green branch: token validates but the listing returned
        fewer private repos than --min-private -> refuse to trust, exit 1."""
        rc = _run_main(
            _ALLOW + ["--include-private", "--min-private", "5"],
            token="tok", whoami=_OK_WHOAMI, membership=("active", None),
            repos=_private_repos(2) + _public_repos(3))
        self.assertEqual(rc, 1)

    def test_license_drift_fails(self):
        """A genuine license-claim drift (an ERROR result) -> exit 1. If a
        refactor turned the drift check into a no-op this would wrongly pass."""
        rc = _run_main(
            _ALLOW, token="tok", whoami=_OK_WHOAMI, membership=("active", None),
            repos=_public_repos(2), check=_err_check)
        self.assertEqual(rc, 1)

    def test_list_error_fails(self):
        """A dropped listing page (list_errors non-empty) silently shrinks the
        sweep -> must surface as loud drift (exit 1), not a smaller green."""
        rc = _run_main(
            _ALLOW, token="tok", whoami=_OK_WHOAMI, membership=("active", None),
            repos=_public_repos(2),
            list_errors=["failed to list org repos (page 2): HTTP 502"])
        self.assertEqual(rc, 1)

    def test_healthy_public_passes(self):
        """Token present, no drift -> exit 0 (public scope)."""
        rc = _run_main(
            _ALLOW, token="tok", whoami=_OK_WHOAMI, membership=("active", None),
            repos=_public_repos(3))
        self.assertEqual(rc, 0)

    def test_healthy_private_floor_met_passes(self):
        """--include-private, floor met, no drift -> exit 0."""
        rc = _run_main(
            _ALLOW + ["--include-private", "--min-private", "3"],
            token="tok", whoami=_OK_WHOAMI, membership=("active", None),
            repos=_private_repos(4) + _public_repos(2))
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
