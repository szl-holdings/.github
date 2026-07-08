#!/usr/bin/env python3
"""Self-test for the managed-security-configuration drift checker.

Task #387 created ``code_security_drift.py`` — the safety net that proves every
non-archived repo in the org stays attached + enforced under the canonical
"SZL Holdings Managed Security" code-security configuration (id 252588), that
the config still exists/org-scoped/enforced, and that it is still the default
for new repos. If that checker were ever weakened — an edit that makes it always
return exit 0, or one that swallows an auth/API failure as a pass — drift would
go undetected and the org would *look* protected when it isn't.

The most important branch ("auth/API failure must be exit 2, never 0") and the
drift branches require live org-admin calls that can't run in CI/the sandbox.
This test stubs the GitHub API surface (``_token`` / ``gh_json`` /
``gh_paginate``) so it runs with NO network and NO PAT, and pins the exit-code
contract of ``main()`` so a future refactor cannot quietly regress it:

  clean state                                   -> exit 0
  a repo detached (not enforced under canonical)-> exit 1
  a repo swapped onto a different configuration  -> exit 1
  a new uncovered repo                           -> exit 1
  default-for-new-repos changed                  -> exit 1
  canonical configuration missing                -> exit 1
  a present-but-failing token (auth/API error)   -> exit 2  (never a silent 0)
  NO token configured at all                     -> exit 3  (neutral skip:
                                                    not 0/pass, not 1/red)

The exit-2 vs exit-3 split is the honest-degrade contract (task #176/#158): a
MISSING secret is a neutral skip (the check could not run — CI surfaces it as a
skipped/neutral status, not a red failure), while a token that IS present but
fails auth/API stays a loud error. Neither is ever a silent pass.

Stdlib ``unittest`` only — no third-party test framework, so CI needs only a
github-owned ``actions/setup-python`` to run it.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "code_security_drift.py")

_spec = importlib.util.spec_from_file_location("code_security_drift", _MODULE_PATH)
assert _spec and _spec.loader
csd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(csd)

ORG = "szl-holdings"
CFG = csd.CANONICAL_CONFIG_ID  # 252588


# --------------------------------------------------------------------------- #
# Synthetic-state builders (shapes mirror the real GitHub API responses).

def _config(id_, name="SZL Holdings Managed Security",
            target_type="organization", enforcement="enforced"):
    return {"id": id_, "name": name, "target_type": target_type,
            "enforcement": enforcement}


def _repo(name, archived=False, private=False):
    return {"full_name": f"{ORG}/{name}", "archived": archived, "private": private}


def _clean_state():
    """Canonical config exists+enforced+default; every repo enforced under it."""
    repos = [_repo("a11oy"), _repo("ouroboros", private=True), _repo("docs-site")]
    configs = [_config(CFG)]
    defaults = [{"default_for_new_repos": "all", "configuration": {"id": CFG}}]
    attachments = {CFG: [(r["full_name"], "enforced") for r in repos]}
    return configs, defaults, repos, attachments


def _make_fetchers(configs, defaults, repos, attachments):
    """Return (gh_json, gh_paginate) stubs that route by request path."""
    def gh_json(path, token):
        if path.endswith("/code-security/configurations/defaults"):
            return defaults
        if path.endswith("/code-security/configurations"):
            return configs
        raise AssertionError(f"unexpected gh_json path: {path}")

    def gh_paginate(path, token):
        if "/repos?type=all" in path:
            return repos
        if path.endswith("/repositories"):
            cfg_id = int(path.rstrip("/").split("/")[-2])
            return [
                {"repository": {"full_name": fn}, "status": st}
                for (fn, st) in attachments.get(cfg_id, [])
            ]
        raise AssertionError(f"unexpected gh_paginate path: {path}")

    return gh_json, gh_paginate


def _run_main(configs, defaults, repos, attachments, *,
              token="tok", gh_json_error=None):
    """Run ``csd.main()`` with the GitHub API surface stubbed out (no network).

    ``token``          -> what ``_token()`` returns (None simulates a missing
                          token, which the real ``_token()`` turns into a
                          MissingTokenError -> exit 3 neutral skip).
    ``gh_json_error``  -> if set, the first ``gh_json`` call raises this
                          exception, simulating an auth/permission/API failure.
    Returns the ``main()`` exit code. Stdout/stderr are swallowed.
    """
    saved = {
        "_token": csd._token,
        "gh_json": csd.gh_json,
        "gh_paginate": csd.gh_paginate,
    }
    try:
        if token is None:
            def _no_token():
                raise csd.MissingTokenError("No GitHub token configured (test).")
            csd._token = _no_token
        else:
            csd._token = lambda: token

        if gh_json_error is not None:
            def _raise(path, tok):
                raise gh_json_error
            csd.gh_json = _raise
            csd.gh_paginate = lambda path, tok: []
        else:
            gj, gp = _make_fetchers(configs, defaults, repos, attachments)
            csd.gh_json = gj
            csd.gh_paginate = gp

        saved_argv = sys.argv
        # Empty --report skips file writes; the allowlist path is absent so the
        # checker falls back to its built-in defaults (no allowlisting).
        sys.argv = [
            "code_security_drift.py",
            "--report", "",
            "--allowlist", os.path.join(_HERE, "__no_such_allowlist__.json"),
        ]
        try:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                return csd.main()
        finally:
            sys.argv = saved_argv
    finally:
        for name, fn in saved.items():
            setattr(csd, name, fn)


class TestDriftCheckerExitContract(unittest.TestCase):
    def test_clean_state_passes(self):
        """Config present+enforced+default and every repo enforced -> exit 0."""
        rc = _run_main(*_clean_state())
        self.assertEqual(rc, 0)

    def test_detached_repo_fails(self):
        """A repo no longer enforced under the canonical config is drift -> 1."""
        configs, defaults, repos, attachments = _clean_state()
        # Drop docs-site's enforcement (detached/removed from the config).
        attachments[CFG] = [(fn, st) for (fn, st) in attachments[CFG]
                            if not fn.endswith("/docs-site")]
        rc = _run_main(configs, defaults, repos, attachments)
        self.assertEqual(rc, 1)

    def test_repo_on_different_config_fails(self):
        """A repo swapped onto a different (legacy) configuration is drift -> 1."""
        configs, defaults, repos, attachments = _clean_state()
        configs.append(_config(999, name="Legacy Enterprise Default"))
        repos.append(_repo("legacy-repo"))
        # Not under canonical; attached+enforced under the legacy config instead.
        attachments[999] = [(f"{ORG}/legacy-repo", "enforced")]
        rc = _run_main(configs, defaults, repos, attachments)
        self.assertEqual(rc, 1)

    def test_new_uncovered_repo_fails(self):
        """A brand-new repo not attached to any config is drift -> exit 1."""
        configs, defaults, repos, attachments = _clean_state()
        repos.append(_repo("freshly-created"))  # absent from all attachments
        rc = _run_main(configs, defaults, repos, attachments)
        self.assertEqual(rc, 1)

    def test_default_for_new_repos_changed_fails(self):
        """If the org default-for-new-repos no longer covers all repos -> 1."""
        configs, defaults, repos, attachments = _clean_state()
        defaults[0]["default_for_new_repos"] = "none"
        rc = _run_main(configs, defaults, repos, attachments)
        self.assertEqual(rc, 1)

    def test_default_entry_missing_fails(self):
        """If nothing is set as the default for new repos -> exit 1."""
        configs, defaults, repos, attachments = _clean_state()
        rc = _run_main(configs, [], repos, attachments)
        self.assertEqual(rc, 1)

    def test_canonical_config_missing_fails(self):
        """If the canonical configuration vanished from the org -> exit 1."""
        configs, defaults, repos, attachments = _clean_state()
        configs = [_config(999, name="Some Other Config")]  # no CFG present
        rc = _run_main(configs, defaults, repos, attachments)
        self.assertEqual(rc, 1)

    def test_missing_token_is_neutral_skip_not_pass_not_red(self):
        """No token configured -> exit 3 (neutral skip).

        Honest degrade: a missing secret must NOT look like a pass (exit 0) and
        must NOT look like drift/failure (exit 1). It is a distinct neutral code
        so CI can render it as a skipped status.
        """
        rc = _run_main(*_clean_state(), token=None)
        self.assertEqual(rc, csd.EXIT_NO_TOKEN)
        self.assertEqual(rc, 3)
        self.assertNotEqual(rc, 0)  # never a fake pass
        self.assertNotEqual(rc, 1)  # never a false "drift" red

    def test_present_but_failing_token_is_exit_2_not_0(self):
        """A present token that hits an auth/API failure stays a loud error.

        Distinct from a MISSING token (exit 3): a configured-but-broken token is
        a real misconfiguration and must be exit 2, never swallowed to 0.
        """
        rc = _run_main(
            *_clean_state(),
            gh_json_error=csd.CheckError("GitHub API 403 (simulated auth failure)"),
        )
        self.assertEqual(rc, csd.EXIT_ERROR)
        self.assertEqual(rc, 2)

    def test_archived_uncovered_repo_passes(self):
        """Archived repos are reported but never fail the check -> exit 0."""
        configs, defaults, repos, attachments = _clean_state()
        repos.append(_repo("old-thing", archived=True))  # not attached anywhere
        rc = _run_main(configs, defaults, repos, attachments)
        self.assertEqual(rc, 0)

    def test_transitional_status_warns_not_fails(self):
        """A briefly-in-flight 'attaching' status warns (re-check) -> exit 0."""
        configs, defaults, repos, attachments = _clean_state()
        attachments[CFG] = [
            (fn, "attaching" if fn.endswith("/docs-site") else st)
            for (fn, st) in attachments[CFG]
        ]
        rc = _run_main(configs, defaults, repos, attachments)
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
