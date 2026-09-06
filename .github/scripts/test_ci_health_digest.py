#!/usr/bin/env python3
"""Network-free self-tests for the fail-closed CI health digest."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import ci_health_digest as chd
import ci_health_digest_http as http


def repositories(count: int, *, archived: int = 0, private: int = 0):
    values = []
    private_start = max(0, count - private)
    for index in range(count):
        is_private = index >= private_start and private > 0
        values.append(
            {
                "name": f"repo-{index:03d}",
                "full_name": f"szl-holdings/repo-{index:03d}",
                "default_branch": "main",
                "archived": index < archived,
                "private": is_private,
                "visibility": "private" if is_private else "public",
            }
        )
    return tuple(values)


def empty_reader_environment(**overrides: str) -> dict[str, str]:
    values = {
        environment_name: ""
        for _, _, environment_name in http.CANDIDATE_ENVIRONMENT
    }
    values.update(overrides)
    return values


class ReaderSelectionTests(unittest.TestCase):
    def test_prefers_verified_short_lived_app_reader(self):
        estate = repositories(123, archived=5, private=3)
        environment = empty_reader_environment(
            DIGEST_APP_TOKEN="app",
            ORG_REPO_WORKFLOW_TOKEN="fallback",
        )
        with patch.dict(os.environ, environment, clear=False), patch.object(
            http, "list_repositories", return_value=estate
        ), patch.object(
            http,
            "request_json",
            return_value=(200, {"workflows": []}),
        ):
            selected = http.select_reader()
        self.assertEqual(selected.mode, "github_app")
        self.assertEqual(selected.credential_name, "qillqaq_app_installation")
        self.assertEqual(len(selected.repositories), 123)
        self.assertEqual(selected.attempts[-1]["result"], "selected")
        self.assertNotIn("app", repr(selected))

    def test_falls_back_only_after_app_reader_is_rejected(self):
        estate = repositories(123, archived=5, private=3)

        def inventory(token):
            if token == "app":
                raise http.ApiError(
                    operation="inventory",
                    status=403,
                    detail_class="unauthorized",
                )
            return estate

        environment = empty_reader_environment(
            DIGEST_APP_TOKEN="app",
            ORG_REPO_WORKFLOW_TOKEN="complete",
        )
        with patch.dict(os.environ, environment, clear=False), patch.object(
            http, "list_repositories", side_effect=inventory
        ), patch.object(
            http,
            "request_json",
            return_value=(200, {"workflows": []}),
        ):
            selected = http.select_reader()
        self.assertEqual(selected.mode, "governed_pat_fallback")
        self.assertEqual(selected.credential_name, "ORG_REPO_WORKFLOW_TOKEN")
        self.assertEqual(selected.attempts[0]["result"], "rejected")
        self.assertEqual(selected.attempts[0]["failure_class"], "unauthorized")
        self.assertFalse(
            any("token" in key.lower() for key in selected.attempts[0])
        )

    def test_stale_named_pat_cannot_mask_later_valid_alias(self):
        estate = repositories(123, private=3)

        def inventory(token):
            if token == "stale":
                raise http.ApiError(
                    operation="inventory",
                    status=401,
                    detail_class="unauthenticated",
                )
            return estate

        environment = empty_reader_environment(
            ORG_REPO_WORKFLOW_TOKEN="stale",
            SZL_ORG_PAT="complete",
        )
        with patch.dict(os.environ, environment, clear=False), patch.object(
            http, "list_repositories", side_effect=inventory
        ), patch.object(
            http,
            "request_json",
            return_value=(200, {"workflows": []}),
        ):
            selected = http.select_reader()
        self.assertEqual(selected.credential_name, "SZL_ORG_PAT")
        self.assertEqual(selected.attempts[1]["failure_class"], "unauthenticated")

    def test_duplicate_secret_values_are_probed_once(self):
        calls: list[str] = []

        def inventory(token):
            calls.append(token)
            raise http.DigestError("rejected")

        environment = empty_reader_environment(
            ORG_REPO_WORKFLOW_TOKEN="same",
            SZL_GITHUB_TOKEN="same",
        )
        with patch.dict(os.environ, environment, clear=False), patch.object(
            http, "list_repositories", side_effect=inventory
        ):
            with self.assertRaises(http.ReaderSelectionError):
                http.select_reader()
        self.assertEqual(calls, ["same"])

    def test_no_reader_is_a_typed_terminal_failure(self):
        with patch.dict(
            os.environ,
            empty_reader_environment(),
            clear=False,
        ):
            with self.assertRaises(http.ReaderSelectionError) as context:
                http.select_reader()
        self.assertEqual(
            len(context.exception.attempts),
            len(http.CANDIDATE_ENVIRONMENT),
        )
        self.assertTrue(
            all(
                item["result"] == "not_configured"
                for item in context.exception.attempts
            )
        )


class RepositoryCoverageTests(unittest.TestCase):
    def test_present_token_with_zero_repositories_fails_closed(self):
        with patch.dict(
            os.environ, {"ORG_REPOSITORY_FLOOR": "123"}, clear=False
        ), patch.object(
            http,
            "request_json",
            return_value=(200, []),
        ), patch.object(http, "validate_authoritative_inventory"):
            with self.assertRaisesRegex(http.DigestError, "below reviewed floor"):
                http.list_repositories("present-token")

    def test_partial_repository_listing_fails_closed(self):
        with patch.dict(
            os.environ, {"ORG_REPOSITORY_FLOOR": "123"}, clear=False
        ), patch.object(
            http,
            "request_json",
            return_value=(200, list(repositories(122, private=3))),
        ), patch.object(http, "validate_authoritative_inventory"):
            with self.assertRaisesRegex(
                http.DigestError, "observed=122 floor=123"
            ):
                http.list_repositories("present-token")

    def test_complete_repository_listing_passes(self):
        estate = repositories(123, archived=5, private=3)
        with patch.dict(
            os.environ, {"ORG_REPOSITORY_FLOOR": "123"}, clear=False
        ), patch.object(
            http,
            "request_json",
            return_value=(200, list(estate)),
        ), patch.object(
            http, "validate_authoritative_inventory"
        ) as authoritative:
            observed = http.list_repositories("present-token")
        self.assertEqual(len(observed), 123)
        self.assertEqual(sum(bool(item["archived"]) for item in observed), 5)
        authoritative.assert_called_once()


class AuthoritativeInventoryTests(unittest.TestCase):
    def test_exact_public_private_inventory_match_passes(self):
        estate = repositories(123, private=3)
        with patch.dict(
            os.environ, {"ORG_REPOSITORY_FLOOR": "123"}, clear=False
        ), patch.object(
            http,
            "request_json",
            return_value=(
                200,
                {"public_repos": 120, "total_private_repos": 3},
            ),
        ):
            result = http.validate_authoritative_inventory("token", estate)
        self.assertTrue(result["inventory_match"])
        self.assertEqual(result["repository_count"], 123)
        self.assertEqual(result["private_repositories"], 3)

    def test_missing_authoritative_private_total_fails(self):
        with patch.dict(
            os.environ, {"ORG_REPOSITORY_FLOOR": "123"}, clear=False
        ), patch.object(
            http,
            "request_json",
            return_value=(200, {"public_repos": 123}),
        ):
            with self.assertRaisesRegex(
                http.DigestError, "private repository total is unavailable"
            ):
                http.validate_authoritative_inventory(
                    "token", repositories(123, private=3)
                )

    def test_partial_listing_cannot_match_authoritative_total(self):
        with patch.dict(
            os.environ, {"ORG_REPOSITORY_FLOOR": "123"}, clear=False
        ), patch.object(
            http,
            "request_json",
            return_value=(
                200,
                {"public_repos": 120, "total_private_repos": 3},
            ),
        ):
            with self.assertRaisesRegex(
                http.DigestError, "listed=122 authoritative=123"
            ):
                http.validate_authoritative_inventory(
                    "token", repositories(122, private=2)
                )

    def test_private_listing_must_match_authoritative_private_total(self):
        with patch.dict(
            os.environ, {"ORG_REPOSITORY_FLOOR": "123"}, clear=False
        ), patch.object(
            http,
            "request_json",
            return_value=(
                200,
                {"public_repos": 120, "total_private_repos": 3},
            ),
        ):
            with self.assertRaisesRegex(
                http.DigestError, "private repository listing"
            ):
                http.validate_authoritative_inventory(
                    "token", repositories(123, private=2)
                )


class IssueAndReportTests(unittest.TestCase):
    def test_all_clear_closes_the_existing_rolling_issue(self):
        calls = []

        def request(token, url, **kwargs):
            calls.append((url, kwargs))
            if "?state=all" in url:
                return 200, [
                    {
                        "number": 158,
                        "title": chd.ISSUE_TITLE,
                        "state": "open",
                    }
                ]
            return 200, {
                "number": 158,
                "state": kwargs["body"]["state"],
                "html_url": "https://github.com/szl-holdings/.github/issues/158",
                "updated_at": "2026-09-06T00:00:00Z",
            }

        with patch.object(chd, "_issue_token", return_value="issue-token"), patch.object(
            chd,
            "_request_json",
            side_effect=request,
        ):
            result = chd.upsert_issue("all clear", red_total=0)
        self.assertEqual(result["state"], "closed")
        mutation = calls[-1][1]["body"]
        self.assertEqual(mutation["state"], "closed")
        self.assertEqual(mutation["state_reason"], "completed")

    def test_red_digest_reopens_the_existing_issue(self):
        calls = []

        def request(token, url, **kwargs):
            calls.append((url, kwargs))
            if "?state=all" in url:
                return 200, [
                    {
                        "number": 158,
                        "title": chd.ISSUE_TITLE,
                        "state": "closed",
                    }
                ]
            return 200, {
                "number": 158,
                "state": kwargs["body"]["state"],
                "html_url": "https://github.com/szl-holdings/.github/issues/158",
                "updated_at": "2026-09-06T00:00:00Z",
            }

        with patch.object(chd, "_issue_token", return_value="issue-token"), patch.object(
            chd,
            "_request_json",
            side_effect=request,
        ):
            result = chd.upsert_issue("red", red_total=1)
        self.assertEqual(result["state"], "open")
        self.assertEqual(calls[-1][1]["body"], {"body": "red", "state": "open"})

    def test_failed_reader_writes_not_verified_receipt_and_exits_two(self):
        attempts = (
            {
                "mode": "github_app",
                "credential_name": "qillqaq_app_installation",
                "result": "rejected",
                "value_recorded": False,
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            with patch.object(
                chd,
                "select_reader",
                side_effect=chd.ReaderSelectionError(attempts),
            ), patch.object(
                chd,
                "upsert_issue",
                return_value={"number": 158, "state": "open"},
            ):
                code = chd.main(["--report", str(report_path)])
            report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "NOT_VERIFIED")
        self.assertEqual(report["authentication"]["attempts"], list(attempts))
        self.assertEqual(report["issue"]["state"], "open")

    def test_complete_sweep_writes_verified_receipt(self):
        estate = repositories(123, archived=5, private=3)
        selected = http.ReaderSelection(
            mode="governed_pat_fallback",
            credential_name="ORG_REPO_WORKFLOW_TOKEN",
            token="never-recorded",
            repositories=estate,
            attempts=(
                {
                    "mode": "governed_pat_fallback",
                    "credential_name": "ORG_REPO_WORKFLOW_TOKEN",
                    "result": "selected",
                    "value_recorded": False,
                },
            ),
        )
        coverage = {
            "organization_repositories": 123,
            "active_repositories": 118,
            "archived_repositories": 5,
            "queried_active_repositories": 118,
            "active_workflows": 100,
            "repository_floor": 123,
        }
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            with patch.object(chd, "select_reader", return_value=selected), patch.object(
                chd,
                "sweep",
                return_value=({}, coverage),
            ), patch.object(
                chd,
                "upsert_issue",
                return_value={"number": 158, "state": "closed"},
            ), patch.object(
                chd,
                "maybe_notify",
                return_value={"attempted": False, "result": "not_configured"},
            ):
                code = chd.main(["--report", str(report_path)])
            report_text = report_path.read_text(encoding="utf-8")
            report = json.loads(report_text)
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "VERIFIED")
        self.assertEqual(report["coverage"]["queried_active_repositories"], 118)
        self.assertEqual(report["summary"]["red_total"], 0)
        self.assertNotIn("never-recorded", report_text)


class WorkflowContractTests(unittest.TestCase):
    def test_production_workflow_is_app_first_fail_closed_and_evidence_bound(self):
        workflow = (ROOT / ".github/workflows/ci-health-digest.yml").read_text(
            encoding="utf-8"
        )
        required = (
            "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1",
            "if: vars.QILLQAQ_CLIENT_ID != ''",
            "permission-actions: read",
            "permission-contents: read",
            "permission-organization-administration: read",
            "DIGEST_APP_TOKEN: ${{ steps.app-token.outputs.token }}",
            "ORG_REPO_WORKFLOW_TOKEN: ${{ secrets.ORG_REPO_WORKFLOW_TOKEN }}",
            "SZL_ORG_PAT: ${{ secrets.SZL_ORG_PAT }}",
            "SZL_GITHUB_PAT: ${{ secrets.SZL_GITHUB_PAT }}",
            "GH_PAT: ${{ secrets.GH_PAT }}",
            "PAT_TOKEN: ${{ secrets.PAT_TOKEN }}",
            "GITHUB_PAT: ${{ secrets.GITHUB_PAT }}",
            "GH_TOKEN: ${{ secrets.GH_TOKEN }}",
            "SZL_GITHUB_TOKEN: ${{ secrets.SZL_GITHUB_TOKEN }}",
            "REPOSITORY_GITHUB_TOKEN: ${{ github.token }}",
            "CI_DIGEST_ISSUE_TOKEN: ${{ github.token }}",
            'ORG_REPOSITORY_FLOOR: "123"',
            "test_ci_health_digest_reader_inventory.py",
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
            "if-no-files-found: error",
            "Enforce complete authenticated coverage",
        )
        for marker in required:
            self.assertIn(marker, workflow)
        self.assertNotIn("secrets.ORG_CI_READ_TOKEN", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("git push", workflow)
        self.assertIn("persist-credentials: false", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
