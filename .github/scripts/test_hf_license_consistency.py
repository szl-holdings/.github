#!/usr/bin/env python3
"""Self-test for the HF license-consistency private-coverage safety net.

Task #383 made ``hf_license_consistency.py`` fail LOUDLY when an
``--include-private`` sweep can no longer prove it actually saw the org's
private HF repos (missing/expired token, wrong org, or a silent collapse of the
private listing to public-only). That guard is the thing standing between us and
a false-green "0 drift" report, but it had no automated test — and the most
important branch ("token validated but private_seen < the empirical floor")
cannot be exercised in CI/the sandbox because there is no live restricted token.

This test stubs the HF API surface (``_hf_token`` / ``hf_whoami`` /
``list_hf_repos``) and ``check_repo`` so it runs with NO network, and pins the
four exit-code contracts of ``main()`` so a future refactor cannot quietly
re-introduce the false-green bug:

  1. ``--include-private`` with no HF token            -> exit 1
  2. ``--include-private`` with a token that fails whoami -> exit 1
  3. ``--include-private`` + valid token but private_seen < --min-private -> exit 1
  4. healthy case (valid token, enough private repos, no drift) -> exit 0

Stdlib ``unittest`` only — no third-party test framework, so CI needs only a
github-owned ``actions/setup-python`` to run it.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "hf_license_consistency.py")

_spec = importlib.util.spec_from_file_location("hf_license_consistency", _MODULE_PATH)
assert _spec and _spec.loader
hlc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hlc)


def _run_main(argv, *, hf_token, whoami, repos):
    """Run ``hlc.main()`` with the HF API surface stubbed out (no network).

    ``hf_token``  -> what ``_hf_token()`` returns (None simulates a missing token).
    ``whoami``    -> the ``(ok, identity, err)`` tuple ``hf_whoami()`` returns.
    ``repos``     -> the repo list ``list_hf_repos()`` returns (its 2nd element,
                     the list-errors, is forced empty so we isolate the private
                     floor / preflight branches under test).
    Returns the ``main()`` exit code. Stdout/stderr are swallowed.
    """
    saved = {
        "_hf_token": hlc._hf_token,
        "_gh_token": hlc._gh_token,
        "hf_whoami": hlc.hf_whoami,
        "list_hf_repos": hlc.list_hf_repos,
        "check_repo": hlc.check_repo,
    }
    try:
        hlc._hf_token = lambda: hf_token
        # No GitHub cross-ref network even if --no-github is omitted.
        hlc._gh_token = lambda: None
        hlc.hf_whoami = lambda token: whoami
        hlc.list_hf_repos = lambda org, token, include_private: (list(repos), [])
        # A clean, network-free per-repo result so the healthy path never tries
        # to read a README; the preflight branches under test short-circuit
        # before drift matters anyway.
        hlc.check_repo = lambda repo, entry, gh_org, gh_token, use_github: {
            "repo": repo["id"], "kind": repo["kind"], "private": repo["private"],
            "hf_license": "Apache-2.0", "hf_license_norm": "Apache-2.0",
            "hf_license_name": None, "github_spdx": None, "allowlisted": False,
            "status": "OK", "errors": [], "warnings": [], "notes": [],
        }
        import sys
        saved_argv = sys.argv
        sys.argv = ["hf_license_consistency.py"] + argv
        try:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                return hlc.main()
        finally:
            sys.argv = saved_argv
    finally:
        for name, fn in saved.items():
            setattr(hlc, name, fn)


def _private_repos(n):
    return [
        {"id": f"SZLHOLDINGS/priv-{i}", "name": f"priv-{i}",
         "kind": "dataset", "private": True}
        for i in range(n)
    ]


_OK_WHOAMI = (True, {"name": "szlholdings", "orgs": []}, None)


class TestPrivateCoverageSafetyNet(unittest.TestCase):
    def test_missing_token_fails(self):
        """--include-private with no HF token must fail loudly (would otherwise
        silently list public-only and report a false green)."""
        rc = _run_main(
            ["--include-private", "--min-private", "5", "--no-github"],
            hf_token=None, whoami=(False, None, "no HF token present"),
            repos=_private_repos(5))
        self.assertEqual(rc, 1)

    def test_whoami_failure_fails(self):
        """A token that fails whoami (expired/revoked/rotated) cannot be trusted
        to unlock private listings -> exit 1."""
        rc = _run_main(
            ["--include-private", "--min-private", "5", "--no-github"],
            hf_token="tok", whoami=(False, None, "whoami-v2 returned HTTP 401"),
            repos=_private_repos(5))
        self.assertEqual(rc, 1)

    def test_valid_token_but_private_floor_unmet_fails(self):
        """THE false-green branch: token validates, but the listing returned
        fewer private repos than --min-private -> refuse to trust, exit 1."""
        rc = _run_main(
            ["--include-private", "--min-private", "5", "--no-github"],
            hf_token="tok", whoami=_OK_WHOAMI,
            repos=_private_repos(2))
        self.assertEqual(rc, 1)

    def test_healthy_case_passes(self):
        """Valid token, private floor met, no drift -> exit 0."""
        rc = _run_main(
            ["--include-private", "--min-private", "5", "--no-github"],
            hf_token="tok", whoami=_OK_WHOAMI,
            repos=_private_repos(6))
        self.assertEqual(rc, 0)

    def test_floor_exactly_met_passes(self):
        """private_seen == --min-private is sufficient (boundary is inclusive)."""
        rc = _run_main(
            ["--include-private", "--min-private", "5", "--no-github"],
            hf_token="tok", whoami=_OK_WHOAMI,
            repos=_private_repos(5))
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
