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
drift branches require live organization-administration calls that cannot run in
credentialless pull-request CI. This test stubs the GitHub API surface
(``_token`` / ``gh_json`` / ``gh_paginate``) so it runs with no network and no
credential, and pins the exit-code contract of ``main()``:

  clean state                                    -> exit 0
  a repo detached (not enforced under canonical) -> exit 1
  a repo swapped onto a different configuration  -> exit 1
  a new uncovered repo                            -> exit 1
  default-for-new-repos changed                   -> exit 1
  canonical configuration missing                 -> exit 1
  a present-but-failing token (auth/API error)    -> exit 2
  no token configured for direct local invocation -> exit 3

The production workflow has a stronger contract: it runs source tests before it
mints a short-lived qillqaq GitHub App installation token, fails when that token
cannot be created or cannot read the organization endpoint, and writes a
normalized, source-bound evidence envelope even when a pre-check prevents the
ordinary report. It never converts a missing or stale personal token into a
neutral production result.

Stdlib ``unittest`` only — no third-party test framework.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "code_security_drift.py")
_ROOT = Path(_HERE).parents[1]

_spec = importlib.util.spec_from_file_location("code_security_drift", _MODULE_PATH)
assert _spec and _spec.loader
csd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(csd)

ORG = "szl-holdings"
CFG = csd.CANONICAL_CONFIG_ID


def _config(
    id_,
    name="SZL Holdings Managed Security",
    target_type="organization",
    enforcement="enforced",
):
    return {
        "id": id_,
        "name": name,
        "target_type": target_type,
        "enforcement": enforcement,
    }


def _repo(name, archived=False, private=False):
    return {
        "full_name": f"{ORG}/{name}",
        "archived": archived,
        "private": private,
    }


def _clean_state():
    """Canonical config exists+enforced+default; every repo enforced under it."""
    repos = [_repo("a11oy"), _repo("ouroboros", private=True), _repo("docs-site")]
    configs = [_config(CFG)]
    defaults = [{"default_for_new_repos": "all", "configuration": {"id": CFG}}]
    attachments = {CFG: [(repo["full_name"], "enforced") for repo in repos]}
    return configs, defaults, repos, attachments


def _make_fetchers(configs, defaults, repos, attachments):
    """Return API stubs that route by request path."""

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
                {"repository": {"full_name": full_name}, "status": status}
                for (full_name, status) in attachments.get(cfg_id, [])
            ]
        raise AssertionError(f"unexpected gh_paginate path: {path}")

    return gh_json, gh_paginate


def _run_main(
    configs,
    defaults,
    repos,
    attachments,
    *,
    token="tok",
    gh_json_error=None,
):
    """Run ``csd.main()`` with the GitHub API surface stubbed out."""
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
            gh_json, gh_paginate = _make_fetchers(
                configs,
                defaults,
                repos,
                attachments,
            )
            csd.gh_json = gh_json
            csd.gh_paginate = gh_paginate

        saved_argv = sys.argv
        sys.argv = [
            "code_security_drift.py",
            "--report",
            "",
            "--allowlist",
            os.path.join(_HERE, "__no_such_allowlist__.json"),
        ]
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                return csd.main()
        finally:
            sys.argv = saved_argv
    finally:
        for name, function in saved.items():
            setattr(csd, name, function)


class TestDriftCheckerExitContract(unittest.TestCase):
    def test_clean_state_passes(self):
        rc = _run_main(*_clean_state())
        self.assertEqual(rc, csd.EXIT_OK)

    def test_detached_repo_fails(self):
        configs, defaults, repos, attachments = _clean_state()
        attachments[CFG] = [
            (full_name, status)
            for (full_name, status) in attachments[CFG]
            if not full_name.endswith("/docs-site")
        ]
        rc = _run_main(configs, defaults, repos, attachments)
        self.assertEqual(rc, csd.EXIT_DRIFT)

    def test_repo_on_different_config_fails(self):
        configs, defaults, repos, attachments = _clean_state()
        configs.append(_config(999, name="Legacy Enterprise Default"))
        repos.append(_repo("legacy-repo"))
        attachments[999] = [(f"{ORG}/legacy-repo", "enforced")]
        rc = _run_main(configs, defaults, repos, attachments)
        self.assertEqual(rc, csd.EXIT_DRIFT)

    def test_new_uncovered_repo_fails(self):
        configs, defaults, repos, attachments = _clean_state()
        repos.append(_repo("freshly-created"))
        rc = _run_main(configs, defaults, repos, attachments)
        self.assertEqual(rc, csd.EXIT_DRIFT)

    def test_default_for_new_repos_changed_fails(self):
        configs, defaults, repos, attachments = _clean_state()
        defaults[0]["default_for_new_repos"] = "none"
        rc = _run_main(configs, defaults, repos, attachments)
        self.assertEqual(rc, csd.EXIT_DRIFT)

    def test_default_entry_missing_fails(self):
        configs, _, repos, attachments = _clean_state()
        rc = _run_main(configs, [], repos, attachments)
        self.assertEqual(rc, csd.EXIT_DRIFT)

    def test_canonical_config_missing_fails(self):
        _, defaults, repos, attachments = _clean_state()
        configs = [_config(999, name="Some Other Config")]
        rc = _run_main(configs, defaults, repos, attachments)
        self.assertEqual(rc, csd.EXIT_DRIFT)

    def test_missing_token_is_distinct_from_a_pass(self):
        rc = _run_main(*_clean_state(), token=None)
        self.assertEqual(rc, csd.EXIT_NO_TOKEN)
        self.assertNotEqual(rc, csd.EXIT_OK)

    def test_present_but_failing_token_is_exit_2_not_0(self):
        rc = _run_main(
            *_clean_state(),
            gh_json_error=csd.CheckError("GitHub API 403 (simulated auth failure)"),
        )
        self.assertEqual(rc, csd.EXIT_ERROR)
        self.assertNotEqual(rc, csd.EXIT_OK)

    def test_archived_uncovered_repo_passes(self):
        configs, defaults, repos, attachments = _clean_state()
        repos.append(_repo("old-thing", archived=True))
        rc = _run_main(configs, defaults, repos, attachments)
        self.assertEqual(rc, csd.EXIT_OK)

    def test_transitional_status_warns_not_fails(self):
        configs, defaults, repos, attachments = _clean_state()
        attachments[CFG] = [
            (
                full_name,
                "attaching" if full_name.endswith("/docs-site") else status,
            )
            for (full_name, status) in attachments[CFG]
        ]
        rc = _run_main(configs, defaults, repos, attachments)
        self.assertEqual(rc, csd.EXIT_OK)


class TestProductionWorkflowAuthContract(unittest.TestCase):
    def setUp(self):
        self.workflow_path = _ROOT / ".github/workflows/code-security-drift.yml"
        self.workflow = self.workflow_path.read_text(encoding="utf-8")

    def test_uses_short_lived_least_privilege_app_token(self):
        self.assertIn(
            "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1",
            self.workflow,
        )
        self.assertIn("client-id: ${{ vars.QILLQAQ_CLIENT_ID }}", self.workflow)
        self.assertIn(
            "private-key: ${{ secrets.QILLQAQ_PRIVATE_KEY }}",
            self.workflow,
        )
        self.assertIn("owner: ${{ github.repository_owner }}", self.workflow)
        self.assertIn(
            "permission-organization-administration: read",
            self.workflow,
        )
        self.assertNotIn("permission-administration: read", self.workflow)
        self.assertIn("GH_TOKEN: ${{ steps.app-token.outputs.token }}", self.workflow)

    def test_source_tests_precede_credential_minting(self):
        self.assertLess(
            self.workflow.index("Compile and self-test the drift contract"),
            self.workflow.index("Mint least-privilege qillqaq organization token"),
        )

    def test_has_no_personal_token_or_neutral_production_skip(self):
        self.assertNotIn("secrets.SZL_GITHUB_TOKEN", self.workflow)
        self.assertNotIn("name: Token preflight", self.workflow)
        self.assertNotIn("has_token:", self.workflow)
        self.assertIn("fail-closed, not a neutral skip", self.workflow)

    def test_every_outcome_gets_normalized_evidence_before_upload(self):
        ensure = self.workflow.index(
            "Normalize or create bounded evidence for every outcome"
        )
        upload = self.workflow.index("Upload immutable drift evidence")
        evidence = self.workflow[ensure:upload]
        self.assertLess(ensure, upload)
        self.assertIn("if: always()", evidence)
        self.assertIn('"schema": "szl.code-security-drift/v2"', evidence)
        self.assertIn('report.setdefault("generation"', evidence)
        self.assertIn('report["workflow"] = workflow', evidence)
        self.assertIn('"app_token_outcome"', evidence)
        self.assertIn('"status": "NOT_VERIFIED"', evidence)

    def test_report_is_immutable_artifact_not_direct_main_push(self):
        self.assertIn(
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
            self.workflow,
        )
        self.assertIn("if-no-files-found: error", self.workflow)
        self.assertNotIn("contents: write", self.workflow)
        self.assertNotIn("git push", self.workflow)
        self.assertIn("persist-credentials: false", self.workflow)

    def test_app_manifest_separates_org_and_repo_administration(self):
        manifest = json.loads(
            (_ROOT / ".governance/github-app-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        permissions = manifest["default_permissions"]
        self.assertEqual(permissions["organization_administration"], "read")
        self.assertEqual(permissions["administration"], "read")


if __name__ == "__main__":
    unittest.main(verbosity=2)
