#!/usr/bin/env python3
"""Self-test for the managed-security-configuration drift checker.

The network-facing checker is stubbed so this suite can lock its exit-code and
workflow-authentication contracts without receiving any organization credential.
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

_FORGE9_PATH = os.path.join(_HERE, "verify_forge9_governance.py")
_forge9_spec = importlib.util.spec_from_file_location(
    "verify_forge9_governance",
    _FORGE9_PATH,
)
assert _forge9_spec and _forge9_spec.loader
forge9 = importlib.util.module_from_spec(_forge9_spec)
_forge9_spec.loader.exec_module(forge9)

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
    repos = [_repo("a11oy"), _repo("ouroboros", private=True), _repo("docs-site")]
    configs = [_config(CFG)]
    defaults = [{"default_for_new_repos": "all", "configuration": {"id": CFG}}]
    attachments = {CFG: [(repo["full_name"], "enforced") for repo in repos]}
    return configs, defaults, repos, attachments


def _make_fetchers(configs, defaults, repos, attachments):
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
                configs, defaults, repos, attachments
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
        self.assertEqual(_run_main(*_clean_state()), csd.EXIT_OK)

    def test_detached_repo_fails(self):
        configs, defaults, repos, attachments = _clean_state()
        attachments[CFG] = [
            (full_name, status)
            for (full_name, status) in attachments[CFG]
            if not full_name.endswith("/docs-site")
        ]
        self.assertEqual(
            _run_main(configs, defaults, repos, attachments),
            csd.EXIT_DRIFT,
        )

    def test_repo_on_different_config_fails(self):
        configs, defaults, repos, attachments = _clean_state()
        configs.append(_config(999, name="Legacy Enterprise Default"))
        repos.append(_repo("legacy-repo"))
        attachments[999] = [(f"{ORG}/legacy-repo", "enforced")]
        self.assertEqual(
            _run_main(configs, defaults, repos, attachments),
            csd.EXIT_DRIFT,
        )

    def test_new_uncovered_repo_fails(self):
        configs, defaults, repos, attachments = _clean_state()
        repos.append(_repo("freshly-created"))
        self.assertEqual(
            _run_main(configs, defaults, repos, attachments),
            csd.EXIT_DRIFT,
        )

    def test_default_for_new_repos_changed_fails(self):
        configs, defaults, repos, attachments = _clean_state()
        defaults[0]["default_for_new_repos"] = "none"
        self.assertEqual(
            _run_main(configs, defaults, repos, attachments),
            csd.EXIT_DRIFT,
        )

    def test_default_entry_missing_fails(self):
        configs, _, repos, attachments = _clean_state()
        self.assertEqual(
            _run_main(configs, [], repos, attachments),
            csd.EXIT_DRIFT,
        )

    def test_canonical_config_missing_fails(self):
        _, defaults, repos, attachments = _clean_state()
        configs = [_config(999, name="Some Other Config")]
        self.assertEqual(
            _run_main(configs, defaults, repos, attachments),
            csd.EXIT_DRIFT,
        )

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
        self.assertEqual(
            _run_main(configs, defaults, repos, attachments),
            csd.EXIT_OK,
        )

    def test_transitional_status_warns_not_fails(self):
        configs, defaults, repos, attachments = _clean_state()
        attachments[CFG] = [
            (
                full_name,
                "attaching" if full_name.endswith("/docs-site") else status,
            )
            for (full_name, status) in attachments[CFG]
        ]
        self.assertEqual(
            _run_main(configs, defaults, repos, attachments),
            csd.EXIT_OK,
        )


class TestProductionWorkflowAuthContract(unittest.TestCase):
    def setUp(self):
        self.workflow_path = _ROOT / ".github/workflows/code-security-drift.yml"
        self.workflow = self.workflow_path.read_text(encoding="utf-8")

    def test_prefers_short_lived_app_and_has_governed_migration_fallback(self):
        self.assertIn(
            "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1",
            self.workflow,
        )
        self.assertIn("continue-on-error: true", self.workflow)
        self.assertIn(
            "permission-organization-administration: read",
            self.workflow,
        )
        self.assertIn(
            "SZL_GITHUB_TOKEN: ${{ secrets.SZL_GITHUB_TOKEN }}",
            self.workflow,
        )
        self.assertIn('auth_mode="github_app"', self.workflow)
        self.assertIn('auth_mode="governed_pat_fallback"', self.workflow)

    def test_source_tests_precede_any_credential_use(self):
        compile_index = self.workflow.index("Compile and self-test the drift contract")
        self.assertLess(
            compile_index,
            self.workflow.index("Mint preferred qillqaq organization token"),
        )
        self.assertLess(
            compile_index,
            self.workflow.index(
                "Check managed-security-config coverage across the organization"
            ),
        )

    def test_missing_or_invalid_credential_cannot_be_neutral(self):
        self.assertNotIn("name: Token preflight", self.workflow)
        self.assertNotIn("has_token:", self.workflow)
        self.assertIn('case "${CHECK_EXIT:-3}"', self.workflow)
        self.assertIn("SZL_GITHUB_TOKEN is missing or unavailable", self.workflow)
        self.assertIn(
            "credential was present but the organization drift check could not complete",
            self.workflow,
        )

    def test_every_outcome_gets_normalized_secret_free_evidence(self):
        ensure = self.workflow.index(
            "Normalize or create bounded evidence for every outcome"
        )
        upload = self.workflow.index("Upload immutable drift evidence")
        evidence = self.workflow[ensure:upload]
        self.assertLess(ensure, upload)
        self.assertIn("if: always()", evidence)
        self.assertIn('"schema": "szl.code-security-drift/v2"', evidence)
        self.assertIn('"credential_name": credential_name', evidence)
        self.assertIn('"value_recorded": False', evidence)
        self.assertIn('"status": "NOT_VERIFIED"', evidence)
        self.assertNotIn("selected_token", evidence)

    def test_report_is_immutable_artifact_not_direct_main_push(self):
        self.assertIn(
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
            self.workflow,
        )
        self.assertIn("if-no-files-found: error", self.workflow)
        self.assertNotIn("contents: write", self.workflow)
        self.assertNotIn("git push", self.workflow)
        self.assertIn("persist-credentials: false", self.workflow)

    def test_requested_app_permission_remains_explicitly_separate(self):
        manifest = json.loads(
            (_ROOT / ".governance/github-app-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        permissions = manifest["default_permissions"]
        self.assertEqual(permissions["organization_administration"], "read")
        self.assertEqual(permissions["administration"], "read")
        self.assertEqual(permissions["secrets"], "read")
        self.assertNotIn("organization_secrets", permissions)

    def test_every_app_token_mint_has_exact_permission_contract(self):
        self.assertEqual(
            forge9.APP_TOKEN_PERMISSION_CONTRACTS,
            {
                ".github/workflows/attest-and-approve.yml": (
                    {
                        "permission-administration": "read",
                        "permission-checks": "read",
                        "permission-contents": "read",
                        "permission-metadata": "read",
                        "permission-pull-requests": "write",
                        "permission-statuses": "write",
                    },
                ),
                ".github/workflows/ci-health-digest.yml": (
                    {
                        "permission-actions": "read",
                        "permission-contents": "read",
                        "permission-organization-administration": "read",
                    },
                ),
                ".github/workflows/code-security-drift.yml": (
                    {
                        "permission-organization-administration": "read",
                    },
                ),
                ".github/workflows/organization-control-sweep.yml": (
                    {
                        "permission-actions": "read",
                        "permission-contents": "read",
                        "permission-organization-administration": "read",
                    },
                ),
                ".github/workflows/secret-health.yml": (
                    {
                        "permission-metadata": "read",
                        "permission-secrets": "read",
                    },
                ),
            },
        )
        forge9.verify_app_token_permissions()

    def test_secret_permissions_are_isolated_to_secret_health(self):
        secret_workflow = ".github/workflows/secret-health.yml"
        for relative, blocks in forge9.APP_TOKEN_PERMISSION_CONTRACTS.items():
            for permissions in blocks:
                self.assertNotIn("permission-organization-secrets", permissions)
                if relative == secret_workflow:
                    self.assertEqual(
                        permissions,
                        {
                            "permission-metadata": "read",
                            "permission-secrets": "read",
                        },
                    )
                else:
                    self.assertNotIn("permission-secrets", permissions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
