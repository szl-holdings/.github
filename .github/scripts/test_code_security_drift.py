#!/usr/bin/env python3
"""Network-free tests for code-security drift and credential selection."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


csd = load_module("code_security_drift", "code_security_drift.py")
selector = load_module(
    "run_code_security_drift_with_fallback",
    "run_code_security_drift_with_fallback.py",
)

ORG = "szl-holdings"
CFG = csd.CANONICAL_CONFIG_ID


def config(
    config_id: int,
    *,
    name: str = "SZL Holdings Managed Security",
    target_type: str = "organization",
    enforcement: str = "enforced",
) -> dict:
    return {
        "id": config_id,
        "name": name,
        "target_type": target_type,
        "enforcement": enforcement,
    }


def repo(name: str, *, archived: bool = False, private: bool = False) -> dict:
    return {
        "full_name": f"{ORG}/{name}",
        "archived": archived,
        "private": private,
    }


def clean_state():
    repositories = [repo("a11oy"), repo("ouroboros", private=True), repo("docs-site")]
    configurations = [config(CFG)]
    defaults = [{"default_for_new_repos": "all", "configuration": {"id": CFG}}]
    attachments = {
        CFG: [(item["full_name"], "enforced") for item in repositories]
    }
    return configurations, defaults, repositories, attachments


def make_fetchers(configurations, defaults, repositories, attachments):
    def gh_json(path, token):
        del token
        if path.endswith("/code-security/configurations/defaults"):
            return defaults
        if path.endswith("/code-security/configurations"):
            return configurations
        raise AssertionError(f"unexpected gh_json path: {path}")

    def gh_paginate(path, token):
        del token
        if "/repos?type=all" in path:
            return repositories
        if path.endswith("/repositories"):
            config_id = int(path.rstrip("/").split("/")[-2])
            return [
                {"repository": {"full_name": full_name}, "status": status}
                for full_name, status in attachments.get(config_id, [])
            ]
        raise AssertionError(f"unexpected gh_paginate path: {path}")

    return gh_json, gh_paginate


def run_checker_main(
    configurations,
    defaults,
    repositories,
    attachments,
    *,
    token: str | None = "token",
    gh_json_error: Exception | None = None,
) -> int:
    saved = {
        "_token": csd._token,
        "gh_json": csd.gh_json,
        "gh_paginate": csd.gh_paginate,
    }
    argv = sys.argv
    try:
        if token is None:
            def no_token():
                raise csd.MissingTokenError("missing token (test)")
            csd._token = no_token
        else:
            csd._token = lambda: token

        if gh_json_error is not None:
            def fail_json(path, candidate):
                del path, candidate
                raise gh_json_error
            csd.gh_json = fail_json
            csd.gh_paginate = lambda path, candidate: []
        else:
            csd.gh_json, csd.gh_paginate = make_fetchers(
                configurations,
                defaults,
                repositories,
                attachments,
            )

        sys.argv = [
            "code_security_drift.py",
            "--report",
            "",
            "--allowlist",
            str(HERE / "__missing_allowlist__.json"),
        ]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            return csd.main()
    finally:
        sys.argv = argv
        for name, value in saved.items():
            setattr(csd, name, value)


class DriftCheckerExitContractTests(unittest.TestCase):
    def test_clean_state_passes(self):
        self.assertEqual(run_checker_main(*clean_state()), csd.EXIT_OK)

    def test_detached_repository_fails(self):
        configurations, defaults, repositories, attachments = clean_state()
        attachments[CFG] = [
            item for item in attachments[CFG] if not item[0].endswith("/docs-site")
        ]
        self.assertEqual(
            run_checker_main(configurations, defaults, repositories, attachments),
            csd.EXIT_DRIFT,
        )

    def test_repository_on_other_configuration_fails(self):
        configurations, defaults, repositories, attachments = clean_state()
        configurations.append(config(999, name="Legacy"))
        repositories.append(repo("legacy-repo"))
        attachments[999] = [(f"{ORG}/legacy-repo", "enforced")]
        self.assertEqual(
            run_checker_main(configurations, defaults, repositories, attachments),
            csd.EXIT_DRIFT,
        )

    def test_new_uncovered_repository_fails(self):
        configurations, defaults, repositories, attachments = clean_state()
        repositories.append(repo("new-repo"))
        self.assertEqual(
            run_checker_main(configurations, defaults, repositories, attachments),
            csd.EXIT_DRIFT,
        )

    def test_default_change_fails(self):
        configurations, defaults, repositories, attachments = clean_state()
        defaults[0]["default_for_new_repos"] = "none"
        self.assertEqual(
            run_checker_main(configurations, defaults, repositories, attachments),
            csd.EXIT_DRIFT,
        )

    def test_missing_canonical_configuration_fails(self):
        _, defaults, repositories, attachments = clean_state()
        self.assertEqual(
            run_checker_main(
                [config(999, name="Other")],
                defaults,
                repositories,
                attachments,
            ),
            csd.EXIT_DRIFT,
        )

    def test_missing_token_is_not_a_pass(self):
        result = run_checker_main(*clean_state(), token=None)
        self.assertEqual(result, csd.EXIT_NO_TOKEN)
        self.assertNotEqual(result, csd.EXIT_OK)

    def test_present_but_unauthorized_token_is_error(self):
        result = run_checker_main(
            *clean_state(),
            gh_json_error=csd.CheckError("403 simulated"),
        )
        self.assertEqual(result, csd.EXIT_ERROR)
        self.assertNotEqual(result, csd.EXIT_OK)

    def test_archived_uncovered_repository_is_ignored(self):
        configurations, defaults, repositories, attachments = clean_state()
        repositories.append(repo("archive", archived=True))
        self.assertEqual(
            run_checker_main(configurations, defaults, repositories, attachments),
            csd.EXIT_OK,
        )

    def test_transitional_attachment_warns_without_false_drift(self):
        configurations, defaults, repositories, attachments = clean_state()
        attachments[CFG] = [
            (full_name, "attaching" if full_name.endswith("/docs-site") else status)
            for full_name, status in attachments[CFG]
        ]
        self.assertEqual(
            run_checker_main(configurations, defaults, repositories, attachments),
            csd.EXIT_OK,
        )


class GovernedCredentialSelectorTests(unittest.TestCase):
    def setUp(self):
        self.environment = mock.patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_prefers_authorized_app_token(self):
        os.environ["QILLQAQ_ORG_TOKEN"] = "app-token"
        os.environ["SZL_GITHUB_TOKEN"] = "fallback-token"
        with mock.patch.object(
            selector,
            "_probe",
            return_value={
                "http_status": 200,
                "classification": "authorized",
                "authorized": True,
                "response_shape": "list",
            },
        ) as probe:
            selected, token, records = selector._select()
        self.assertEqual(selected, "qillqaq_app")
        self.assertEqual(token, "app-token")
        self.assertEqual(len(records), 1)
        probe.assert_called_once_with("app-token")

    def test_falls_back_only_after_app_is_rejected(self):
        os.environ["QILLQAQ_ORG_TOKEN"] = "app-token"
        os.environ["SZL_GITHUB_TOKEN"] = "fallback-token"
        with mock.patch.object(
            selector,
            "_probe",
            side_effect=[
                {
                    "http_status": 403,
                    "classification": "unauthorized",
                    "authorized": False,
                    "response_shape": None,
                },
                {
                    "http_status": 200,
                    "classification": "authorized",
                    "authorized": True,
                    "response_shape": "list",
                },
            ],
        ):
            selected, token, records = selector._select()
        self.assertEqual(selected, "szl_github_token")
        self.assertEqual(token, "fallback-token")
        self.assertEqual([item["classification"] for item in records], [
            "unauthorized",
            "authorized",
        ])

    def test_no_authorized_candidate_fails_closed(self):
        os.environ["SZL_GITHUB_TOKEN"] = "fallback-token"
        with mock.patch.object(
            selector,
            "_probe",
            return_value={
                "http_status": 401,
                "classification": "unauthenticated",
                "authorized": False,
                "response_shape": None,
            },
        ):
            with self.assertRaises(selector.CredentialSelectionError):
                selector._select()

    def test_failure_report_contains_no_token_material(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            selector._bounded_failure_report(
                path,
                [
                    {
                        "credential": "qillqaq_app",
                        "configured": False,
                        "authorized": False,
                    }
                ],
                "no credential",
            )
            text = path.read_text(encoding="utf-8")
            report = json.loads(text)
        self.assertEqual(report["status"], "NOT_VERIFIED")
        self.assertIsNone(report["credential_selection"]["selected"])
        self.assertNotIn("token", json.dumps(report).lower().replace("credential", ""))


class ProductionWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (
            ROOT / ".github/workflows/code-security-drift.yml"
        ).read_text(encoding="utf-8")

    def test_app_is_preferred_but_failure_does_not_skip_fallback(self):
        self.assertIn(
            "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1",
            self.workflow,
        )
        self.assertIn("permission-organization-administration: read", self.workflow)
        self.assertIn("continue-on-error: true", self.workflow)
        self.assertIn(
            "QILLQAQ_ORG_TOKEN: ${{ steps.app-token.outputs.token }}",
            self.workflow,
        )

    def test_fallback_is_explicit_and_never_neutral(self):
        self.assertIn(
            "SZL_GITHUB_TOKEN: ${{ secrets.SZL_GITHUB_TOKEN }}",
            self.workflow,
        )
        self.assertIn("run_code_security_drift_with_fallback.py", self.workflow)
        self.assertNotIn("name: Token preflight", self.workflow)
        self.assertNotIn("has_token:", self.workflow)
        self.assertIn("fail-closed, not a neutral skip", self.workflow)

    def test_tests_precede_credential_use(self):
        self.assertLess(
            self.workflow.index("Compile and self-test the drift and credential contracts"),
            self.workflow.index("Mint preferred qillqaq organization token"),
        )

    def test_report_is_immutable_and_main_is_not_pushed(self):
        self.assertIn(
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
            self.workflow,
        )
        self.assertIn("if-no-files-found: error", self.workflow)
        self.assertNotIn("contents: write", self.workflow)
        self.assertNotIn("git push", self.workflow)
        self.assertIn("persist-credentials: false", self.workflow)

    def test_manifest_keeps_separate_org_and_repo_admin_permissions(self):
        manifest = json.loads(
            (ROOT / ".governance/github-app-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        permissions = manifest["default_permissions"]
        self.assertEqual(permissions["organization_administration"], "read")
        self.assertEqual(permissions["administration"], "read")


if __name__ == "__main__":
    unittest.main(verbosity=2)
