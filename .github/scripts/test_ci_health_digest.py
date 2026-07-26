#!/usr/bin/env python3
"""Offline contract tests for the organization CI health digest."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODULE_PATH = HERE / "ci_health_digest.py"

spec = importlib.util.spec_from_file_location("ci_health_digest", MODULE_PATH)
assert spec and spec.loader
chd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chd)


def estate(*, total: int = 57, private: int = 3, archived: int = 5):
    if total < 1 or private < 0 or archived < 0 or private + archived > total:
        raise ValueError("invalid synthetic estate")
    repos = [
        {
            "full_name": "szl-holdings/.github",
            "name": ".github",
            "private": False,
            "archived": False,
        }
    ]
    for index in range(private):
        repos.append(
            {
                "full_name": f"szl-holdings/private-{index}",
                "name": f"private-{index}",
                "private": True,
                "archived": False,
            }
        )
    while len(repos) < total:
        index = len(repos)
        repos.append(
            {
                "full_name": f"szl-holdings/public-{index}",
                "name": f"public-{index}",
                "private": False,
                "archived": False,
            }
        )
    for repo in repos[-archived:]:
        repo["archived"] = True
    return repos


def identity(token: str = "secret-read-token") -> chd.ReadIdentity:
    repos = estate()
    return chd.ReadIdentity(
        mode="github_app",
        credential_name="QILLQAQ_APP_TOKEN",
        token=token,
        repositories=tuple(repos),
        total_repositories=57,
        active_repositories=52,
        archived_repositories=5,
        private_repositories=3,
        action_probes=("szl-holdings/.github", "szl-holdings/private-0"),
    )


def verified_report(*, reds=(), errors=()):
    red_items = list(reds)
    actionable = sum(item.category == "ACTIONABLE" for item in red_items)
    founder = sum(item.category == "FOUNDER_GATED" for item in red_items)
    infra = sum(item.category == "INFRA" for item in red_items)
    return {
        "schema": chd.REPORT_SCHEMA,
        "generated_at": "2026-07-26T00:00:00+00:00",
        "generation": "a" * 40,
        "organization": chd.ORG,
        "status": "VERIFIED" if not errors else "NOT_VERIFIED",
        "authentication": {
            "mode": "github_app",
            "credential_name": "QILLQAQ_APP_TOKEN",
            "authorized_endpoint_completed": True,
            "action_probes": ["szl-holdings/.github", "szl-holdings/private-0"],
            "rejected_candidates": [],
            "value_recorded": False,
            "prefix_recorded": False,
            "length_recorded": False,
            "hash_recorded": False,
        },
        "coverage": {
            "repositories": 57,
            "active": 52,
            "archived": 5,
            "private": 3,
            "repository_floor": 57,
            "active_floor": 52,
            "private_floor": 3,
            "swept_active": 52,
            "workflow_count": 100,
        },
        "summary": {
            "red": len(red_items),
            "actionable": actionable,
            "founder_gated": founder,
            "infra": infra,
            "query_errors": len(errors),
        },
        "reds": [chd.asdict(item) for item in red_items],
        "query_errors": list(errors),
        "issue": None,
        "boundaries": [],
    }


class ReadIdentityTests(unittest.TestCase):
    def test_complete_app_identity_is_accepted_and_probes_private_actions(self):
        probes = []
        observed = chd.assess_identity(
            "github_app",
            "QILLQAQ_APP_TOKEN",
            "masked-token",
            repository_loader=lambda mode, token: estate(),
            actions_probe=lambda token, repo: probes.append(repo),
        )
        self.assertEqual(observed.mode, "github_app")
        self.assertEqual(observed.total_repositories, 57)
        self.assertEqual(observed.active_repositories, 52)
        self.assertEqual(observed.private_repositories, 3)
        self.assertEqual(
            probes,
            ["szl-holdings/.github", "szl-holdings/private-0"],
        )

    def test_partial_public_only_identity_is_rejected(self):
        with self.assertRaisesRegex(chd.DigestError, "private repositories"):
            chd.assess_identity(
                "governed_pat_fallback",
                "ORG_CI_READ_TOKEN",
                "masked-token",
                repository_loader=lambda mode, token: estate(private=0),
                actions_probe=lambda token, repo: None,
            )

    def test_repository_floor_is_terminal(self):
        with self.assertRaisesRegex(chd.DigestError, "expected at least"):
            chd.assess_identity(
                "github_app",
                "QILLQAQ_APP_TOKEN",
                "masked-token",
                repository_loader=lambda mode, token: estate(total=56, private=3, archived=4),
                actions_probe=lambda token, repo: None,
            )

    def test_app_is_preferred_and_pat_is_a_bounded_fallback(self):
        fallback = identity("fallback-token")
        with patch.object(
            chd,
            "assess_identity",
            side_effect=[chd.DigestError("app unavailable"), fallback],
        ):
            selected, failures = chd.select_read_identity(
                (
                    ("github_app", "QILLQAQ_APP_TOKEN", "app-token"),
                    ("governed_pat_fallback", "ORG_CI_READ_TOKEN", "pat-token"),
                )
            )
        self.assertIs(selected, fallback)
        self.assertEqual(failures, ("QILLQAQ_APP_TOKEN: app unavailable",))

    def test_no_complete_read_identity_is_terminal(self):
        with patch.object(
            chd,
            "assess_identity",
            side_effect=chd.DigestError("unauthorized"),
        ):
            with self.assertRaisesRegex(chd.DigestError, "no complete organization"):
                chd.select_read_identity(
                    (
                        ("github_app", "QILLQAQ_APP_TOKEN", ""),
                        ("governed_pat_fallback", "ORG_CI_READ_TOKEN", ""),
                    )
                )


class ClassificationAndIssueTests(unittest.TestCase):
    def red(self, category: str) -> chd.RedRun:
        return chd.RedRun(
            repo="repo",
            workflow="workflow",
            workflow_id=1,
            run_id=2,
            run_number=3,
            conclusion="failure",
            event="push",
            created_at="2026-07-26T00:00:00Z",
            url="https://github.com/example/actions/runs/2",
            category=category,
            reason="test",
        )

    def test_issue_stays_open_for_current_actionable_failure(self):
        title, body, should_open = chd.render_issue(
            verified_report(reds=[self.red("ACTIONABLE")])
        )
        self.assertTrue(should_open)
        self.assertTrue(title.startswith("🔴"))
        self.assertIn("**1 actionable**", body)

    def test_historical_only_failures_close_the_action_queue(self):
        title, body, should_open = chd.render_issue(
            verified_report(reds=[self.red("INFRA")])
        )
        self.assertFalse(should_open)
        self.assertTrue(title.startswith("🟠"))
        self.assertIn("Historical / infrastructure", body)

    def test_incomplete_sweep_stays_open_even_without_red_runs(self):
        title, _, should_open = chd.render_issue(
            verified_report(errors=["repo: API 403"])
        )
        self.assertTrue(should_open)
        self.assertTrue(title.startswith("🔴"))

    def test_failed_issue_write_propagates(self):
        with patch.object(
            chd,
            "api_json",
            side_effect=chd.ApiError("PATCH", "/issues/158", 401, "Bad credentials"),
        ):
            with self.assertRaises(chd.ApiError):
                chd.upsert_issue("write-token", verified_report())

    def test_successful_issue_close_is_verified(self):
        with patch.object(
            chd,
            "api_json",
            return_value={
                "number": 158,
                "title": "🟢 CI Health Digest — org-wide",
                "state": "closed",
                "html_url": "https://github.com/szl-holdings/.github/issues/158",
            },
        ):
            result = chd.upsert_issue("write-token", verified_report())
        self.assertEqual(result["number"], 158)
        self.assertEqual(result["state"], "closed")
        self.assertFalse(result["value_recorded"])


class ReportAndMainTests(unittest.TestCase):
    def test_read_secret_is_not_serialized(self):
        secret = "never-persist-this-read-token"
        with patch.object(chd, "sweep_all", return_value=([], [], [])):
            report = chd.build_report(identity(secret), [])
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn(secret, rendered)
        self.assertFalse(report["authentication"]["value_recorded"])
        self.assertEqual(report["coverage"]["repositories"], 57)

    def test_main_fails_when_issue_update_fails(self):
        report = verified_report()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            chd,
            "select_read_identity",
            return_value=(identity(), ()),
        ), patch.object(chd, "build_report", return_value=report), patch.object(
            chd,
            "upsert_issue",
            side_effect=chd.DigestError("issue PATCH failed"),
        ):
            path = Path(directory) / "digest.json"
            rc = chd.main(["--report", str(path)])
            stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(rc, 2)
        self.assertEqual(stored["status"], "NOT_VERIFIED")
        self.assertIn("issue PATCH failed", stored["query_errors"][-1])

    def test_main_passes_only_after_complete_sweep_and_issue_write(self):
        report = verified_report()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            chd,
            "select_read_identity",
            return_value=(identity(), ()),
        ), patch.object(chd, "build_report", return_value=report), patch.object(
            chd,
            "upsert_issue",
            return_value={
                "number": 158,
                "state": "closed",
                "title": "🟢 CI Health Digest — org-wide",
                "url": "https://github.com/szl-holdings/.github/issues/158",
                "value_recorded": False,
            },
        ):
            path = Path(directory) / "digest.json"
            rc = chd.main(["--report", str(path)])
            stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(rc, 0)
        self.assertEqual(stored["status"], "VERIFIED")
        self.assertEqual(stored["issue"]["state"], "closed")


class WorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (
            ROOT / ".github" / "workflows" / "ci-health-digest.yml"
        ).read_text(encoding="utf-8")
        self.source = MODULE_PATH.read_text(encoding="utf-8")

    def test_pull_request_contract_is_credentialless(self):
        self.assertIn("pull_request:", self.workflow)
        self.assertIn("github.event_name != 'pull_request'", self.workflow)
        self.assertIn("test_ci_health_digest.py", self.workflow)

    def test_app_first_and_fallback_are_separate_from_issue_write_token(self):
        self.assertIn("actions/create-github-app-token@", self.workflow)
        self.assertIn("permission-actions: read", self.workflow)
        self.assertIn("QILLQAQ_TOKEN: ${{ steps.app-token.outputs.token }}", self.workflow)
        self.assertIn("ORG_CI_READ_TOKEN: ${{ secrets.ORG_CI_READ_TOKEN }}", self.workflow)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", self.workflow)
        self.assertIn("QILLQAQ_TOKEN", self.source)
        self.assertIn("ORG_CI_READ_TOKEN", self.source)
        self.assertNotIn(
            '("governed_pat_fallback", "GITHUB_TOKEN"',
            self.source,
        )

    def test_evidence_is_uploaded_and_terminal_result_enforced(self):
        self.assertIn("actions/upload-artifact@", self.workflow)
        self.assertIn("if-no-files-found: error", self.workflow)
        self.assertIn("Enforce authenticated digest result", self.workflow)
        self.assertNotIn("NTFY_BASE_URL", self.workflow)

    def test_app_manifest_has_actions_read(self):
        manifest = json.loads(
            (ROOT / ".governance" / "github-app-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["default_permissions"]["actions"], "read")


if __name__ == "__main__":
    unittest.main(verbosity=2)
