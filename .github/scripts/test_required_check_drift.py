#!/usr/bin/env python3
"""Self-test for the required-status-check drift guard.

``required_check_drift.py`` is the thing that notices when a repo silently loses
a REQUIRED status check (the lockfile-registry context, or the overclaim-honesty
context) from main-branch protection — at which point a bad change could be
merged past the merge block. It must fail LOUD: exit 2 when it cannot even read
rulesets/protection (auth/API), and exit 1 when a wired repo has actually
drifted. A refactor that returned 0 in either case would re-open the merge hole
while still looking green.

This stubs every network/config call (``_token`` / ``load_config`` /
``load_allowlist`` / ``gh_json`` / ``ruleset_contexts`` / ``classic_contexts``)
so it runs with NO network, and pins:

  1. no token (CheckError out of _token)                       -> exit 2
  2. a wired repo no longer requires the context (DRIFT)       -> exit 1
  3. context required via ruleset (or classic)                 -> exit 0
  4. an allowlisted repo never counts as drift                 -> exit 0
  5. multi-check config, all contexts required                 -> exit 0
  6. multi-check config, one check's repo drifted              -> exit 1
  7. check_groups normalizes both config shapes
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "required_check_drift.py")

_spec = importlib.util.spec_from_file_location("required_check_drift", _MODULE_PATH)
assert _spec and _spec.loader
rcd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rcd)

_TOKEN_ENV = ("SZL_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
_CTX = "lockfiles / No lockfile references a Replit-internal registry host"
_CTX2 = "overclaim / Governed surfaces are honest (Theorem U citation rule)"


def _run_main(*, token, config, allowlist=None, ruleset=(set(), []),
              classic=(set(), False)):
    """Run ``rcd.main()`` with the network surface stubbed; returns exit code."""
    saved = {name: getattr(rcd, name) for name in
             ("_token", "load_config", "load_allowlist", "gh_json",
              "ruleset_contexts", "classic_contexts")}
    saved_env = {k: os.environ.get(k) for k in _TOKEN_ENV}
    saved_argv = sys.argv
    tmp = tempfile.mkdtemp(prefix="rcd-test-")
    try:
        for k in _TOKEN_ENV:
            os.environ.pop(k, None)
        if token is None:
            # Exercise the REAL _token() so the CheckError->exit 2 path is genuine.
            pass
        else:
            rcd._token = lambda: token
        rcd.load_config = lambda path: dict(config)
        rcd.load_allowlist = lambda path: dict(allowlist or {"ignore_repos": []})
        rcd.gh_json = lambda path, tok, **kw: {"default_branch": "main"}
        rcd.ruleset_contexts = lambda org, repo, tok: ruleset
        rcd.classic_contexts = lambda org, repo, db, tok: classic
        sys.argv = [
            "required_check_drift.py",
            "--report", os.path.join(tmp, "report.json"),
        ]
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return rcd.main()
    finally:
        for name, fn in saved.items():
            setattr(rcd, name, fn)
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.argv = saved_argv
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


_CONFIG = {"org": "szl-holdings", "required_context": _CTX,
           "repos": {"a11oy": {"mechanism": "ruleset"}}}

_MULTI_CONFIG = {
    "org": "szl-holdings",
    "checks": [
        {"id": "lockfile-registry", "required_context": _CTX,
         "repos": {"a11oy": {"mechanism": "ruleset"}}},
        {"id": "overclaim-honesty", "required_context": _CTX2,
         "repos": {"lutar-lean": {"mechanism": "classic"},
                   "szl-papers": {"mechanism": "classic"}}},
    ],
}


class TestRequiredCheckDriftGuard(unittest.TestCase):
    def test_no_token_exit_2(self):
        """No token of any kind -> _token() raises CheckError -> exit 2 (never a
        silent 0 that would imply 'all checks still required')."""
        rc = _run_main(token=None, config=_CONFIG)
        self.assertEqual(rc, 2)

    def test_drift_fails(self):
        """The required context is no longer enforced via ruleset OR classic
        protection -> DRIFT -> exit 1. This is the merge-hole alarm."""
        rc = _run_main(token="tok", config=_CONFIG,
                       ruleset=(set(), []), classic=(set(), False))
        self.assertEqual(rc, 1)

    def test_required_via_ruleset_passes(self):
        """Context required via an active ruleset -> exit 0."""
        rc = _run_main(token="tok", config=_CONFIG,
                       ruleset=({_CTX}, [{"id": 1}]), classic=(set(), False))
        self.assertEqual(rc, 0)

    def test_required_via_classic_passes(self):
        """Context required via classic branch protection -> exit 0."""
        rc = _run_main(token="tok", config=_CONFIG,
                       ruleset=(set(), []), classic=({_CTX}, True))
        self.assertEqual(rc, 0)

    def test_allowlisted_repo_not_drift(self):
        """An allowlisted repo is skipped and never produces drift -> exit 0."""
        rc = _run_main(token="tok", config=_CONFIG,
                       allowlist={"ignore_repos": ["a11oy"]},
                       ruleset=(set(), []), classic=(set(), False))
        self.assertEqual(rc, 0)

    def test_multi_check_all_required_passes(self):
        """Multi-check config where BOTH contexts are required (via classic here)
        on their repos -> exit 0. Proves the watcher unions all check groups."""
        rc = _run_main(token="tok", config=_MULTI_CONFIG,
                       ruleset=(set(), []), classic=({_CTX, _CTX2}, True))
        self.assertEqual(rc, 0)

    def test_multi_check_one_context_drifts(self):
        """Multi-check config where only the lockfile context is still required
        and the overclaim context has been dropped -> DRIFT -> exit 1. A second
        merge block silently vanishing must still alarm."""
        rc = _run_main(token="tok", config=_MULTI_CONFIG,
                       ruleset=(set(), []), classic=({_CTX}, True))
        self.assertEqual(rc, 1)

    def test_check_groups_normalizes_both_shapes(self):
        """check_groups() must yield one group for the legacy shape and one per
        entry for the multi shape, so run_check iterates them uniformly."""
        legacy = rcd.check_groups(_CONFIG)
        self.assertEqual(len(legacy), 1)
        self.assertEqual(legacy[0]["required_context"], _CTX)
        multi = rcd.check_groups(_MULTI_CONFIG)
        self.assertEqual(len(multi), 2)
        self.assertEqual({g["id"] for g in multi},
                         {"lockfile-registry", "overclaim-honesty"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
