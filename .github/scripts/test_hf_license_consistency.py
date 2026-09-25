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
import json
import os
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "hf_license_consistency.py")

_spec = importlib.util.spec_from_file_location("hf_license_consistency", _MODULE_PATH)
assert _spec and _spec.loader
hlc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hlc)
_REAL_CHECK_REPO = hlc.check_repo


def _run_main(argv, *, hf_token, whoami, repos, check_repo=None, stdout=None):
    """Run ``hlc.main()`` with the HF API surface stubbed out (no network).

    ``hf_token``  -> what ``_hf_token()`` returns (None simulates a missing token).
    ``whoami``    -> the ``(ok, identity, err)`` tuple ``hf_whoami()`` returns.
    ``repos``     -> the repo list ``list_hf_repos()`` returns (its 2nd element,
                     the list-errors, is forced empty so we isolate the private
                     floor / preflight branches under test).
    ``check_repo`` -> optional replacement for the default all-OK stub.
    ``stdout``    -> optional StringIO that receives stdout and stderr.
    Returns the ``main()`` exit code. Stdout/stderr are swallowed by default.
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
        hlc.check_repo = check_repo or (lambda repo, entry, gh_org, gh_token, use_github: {
            "repo": repo["id"], "kind": repo["kind"], "private": repo["private"],
            "hf_license": "Apache-2.0", "hf_license_norm": "Apache-2.0",
            "hf_license_name": None, "github_spdx": None, "allowlisted": False,
            "status": "OK", "errors": [], "warnings": [], "notes": [],
        })
        import sys
        saved_argv = sys.argv
        sys.argv = ["hf_license_consistency.py"] + argv
        sink = stdout if stdout is not None else io.StringIO()
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
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


_PUBLIC_REPO = {"id": "SZLHOLDINGS/pub-0", "name": "pub-0",
                "kind": "dataset", "private": False}


def _error_stub(repo, entry, gh_org, gh_token, use_github):
    return {
        "repo": repo["id"], "kind": repo["kind"], "private": repo["private"],
        "hf_license": None, "hf_license_norm": None, "hf_license_name": None,
        "github_spdx": None, "allowlisted": False, "status": "ERROR",
        "errors": ["no 'license:' in README front-matter"], "warnings": [], "notes": [],
    }


class TestPublicOnlyOutput(unittest.TestCase):
    """The report is committed to, and uploaded from, a public repository, and
    stdout is a public CI log: private repos may appear only as counts."""

    def _run(self, extra_argv=(), check_repo=None):
        # These cases model a local run; the CI refusal of --show-private is
        # covered by TestShowPrivateIsLocalOnly.
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, env, clear=True):
            report_path = os.path.join(tmp, "report.json")
            out = io.StringIO()
            rc = _run_main(
                ["--include-private", "--min-private", "5", "--no-github",
                 "--report", report_path, *extra_argv],
                hf_token="tok", whoami=_OK_WHOAMI,
                repos=_private_repos(5) + [_PUBLIC_REPO],
                check_repo=check_repo, stdout=out)
            with open(report_path, encoding="utf-8") as fh:
                text = fh.read()
        return rc, json.loads(text), text, out.getvalue()

    def test_report_lists_public_repos_only(self):
        rc, report, text, log = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual([x["repo"] for x in report["results"]], ["SZLHOLDINGS/pub-0"])
        self.assertTrue(report["private_results_redacted"])
        self.assertEqual(report["private_summary"],
                         {"checked": 5, "ok": 5, "warn": 0, "error": 0})
        self.assertEqual(report["summary"]["checked"], 6)
        self.assertNotIn("priv-", text)
        self.assertNotIn("priv-", log)
        self.assertIn("SZLHOLDINGS/pub-0", log)

    def test_show_private_prints_ids_but_report_stays_public_only(self):
        rc, report, text, log = self._run(["--show-private"])
        self.assertEqual(rc, 0)
        self.assertIn("SZLHOLDINGS/priv-0", log)
        self.assertNotIn("priv-", text)

    def test_private_drift_still_fails_without_naming_the_repo(self):
        rc, report, text, log = self._run(check_repo=_error_stub)
        self.assertEqual(rc, 1)
        self.assertEqual(report["private_summary"]["error"], 5)
        self.assertNotIn("priv-", text)
        self.assertNotIn("priv-", log)
        self.assertIn("--show-private", log)

    def test_committed_report_lists_no_private_repo(self):
        path = os.path.join(_HERE, "..", "data", "hf_license_consistency_report.json")
        with open(path, encoding="utf-8") as fh:
            report = json.load(fh)
        self.assertTrue(report.get("private_results_redacted"))
        self.assertEqual([x["repo"] for x in report["results"] if x.get("private")], [])


class TestPrivateReposKeepErrorSemantics(unittest.TestCase):
    """Keeping private ids out of the public outputs must not relax the check:
    a private repo with no allowlist entry of its own and no license
    front-matter is still an ERROR that fails the run."""

    @staticmethod
    def _readme(repo, token):
        if repo["private"]:
            return "# card without front-matter\n"
        return "---\nlicense: apache-2.0\n---\n# card\n"

    def _run_real_check(self, allowlist_doc=None):
        saved = hlc.hf_readme
        hlc.hf_readme = self._readme
        try:
            with tempfile.TemporaryDirectory() as tmp:
                report_path = os.path.join(tmp, "report.json")
                argv = ["--include-private", "--min-private", "5", "--no-github",
                        "--report", report_path]
                if allowlist_doc is not None:
                    allow = os.path.join(tmp, "allow.json")
                    with open(allow, "w", encoding="utf-8") as fh:
                        json.dump(allowlist_doc, fh)
                    argv += ["--allowlist", allow]
                out = io.StringIO()
                rc = _run_main(argv, hf_token="tok", whoami=_OK_WHOAMI,
                               repos=_private_repos(5) + [_PUBLIC_REPO],
                               check_repo=_REAL_CHECK_REPO, stdout=out)
                with open(report_path, encoding="utf-8") as fh:
                    text = fh.read()
        finally:
            hlc.hf_readme = saved
        return rc, json.loads(text), text, out.getvalue()

    def test_committed_allowlist_keeps_private_missing_license_an_error(self):
        rc, report, text, log = self._run_real_check()
        self.assertEqual(rc, 1)
        self.assertEqual(report["private_summary"],
                         {"checked": 5, "ok": 0, "warn": 0, "error": 5})
        self.assertEqual([(x["repo"], x["status"]) for x in report["results"]],
                         [("SZLHOLDINGS/pub-0", "OK")])
        self.assertNotIn("priv-", text)
        self.assertNotIn("priv-", log)

    def test_top_level_private_key_grants_no_exemption(self):
        rc, report, text, log = self._run_real_check(
            {"repos": {}, "private_repos": {"license_optional": True},
             "ignore_repos": []})
        self.assertEqual(rc, 1)
        self.assertEqual(report["private_summary"]["error"], 5)
        self.assertEqual(report["private_summary"]["warn"], 0)


class TestShowPrivateIsLocalOnly(unittest.TestCase):
    def test_show_private_is_refused_in_github_actions(self):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            rc = _run_main(
                ["--include-private", "--min-private", "5", "--no-github",
                 "--show-private"],
                hf_token="tok", whoami=_OK_WHOAMI,
                repos=_private_repos(5) + [_PUBLIC_REPO], stdout=out)
        self.assertEqual(rc, 2)
        self.assertNotIn("priv-", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
