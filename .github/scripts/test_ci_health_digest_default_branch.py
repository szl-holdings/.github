#!/usr/bin/env python3
"""Network-free tests for protected-default-branch CI health semantics."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import ci_health_digest_http as http
import ci_health_digest_sweep as sweep


def workflow(identifier: int, path: str, name: str = "Workflow"):
    return {
        "id": identifier,
        "name": name,
        "path": path,
        "state": "active",
    }


class DefaultBranchWorkflowTests(unittest.TestCase):
    def test_registered_branch_only_workflow_is_excluded_on_404(self):
        with patch.object(
            sweep,
            "request_json",
            side_effect=http.ApiError(
                operation="lookup",
                status=404,
                detail_class="not_found_or_hidden",
            ),
        ):
            self.assertFalse(
                sweep.workflow_exists_on_default_branch(
                    "token",
                    "repo",
                    "main",
                    workflow(1, ".github/workflows/branch-only.yml"),
                )
            )

    def test_default_branch_workflow_requires_exact_immutable_file(self):
        payload = {
            "type": "file",
            "path": ".github/workflows/ci.yml",
            "sha": "a" * 40,
        }
        with patch.object(sweep, "request_json", return_value=(200, payload)):
            self.assertTrue(
                sweep.workflow_exists_on_default_branch(
                    "token",
                    "repo",
                    "main",
                    workflow(1, ".github/workflows/ci.yml"),
                )
            )

    def test_non_404_default_branch_lookup_failure_is_terminal(self):
        with patch.object(
            sweep,
            "request_json",
            side_effect=http.ApiError(
                operation="lookup",
                status=403,
                detail_class="unauthorized",
            ),
        ):
            with self.assertRaises(http.ApiError):
                sweep.workflow_exists_on_default_branch(
                    "token",
                    "repo",
                    "main",
                    workflow(1, ".github/workflows/ci.yml"),
                )

    def test_latest_run_never_falls_back_to_another_branch(self):
        with patch.object(
            sweep,
            "request_json",
            return_value=(200, {"workflow_runs": []}),
        ) as request:
            observed = sweep.latest_run(
                "token",
                "repo",
                "main",
                workflow(1, ".github/workflows/ci.yml"),
            )
        self.assertIsNone(observed)
        request.assert_called_once()
        self.assertIn("branch=main", request.call_args.args[1])

    def test_branch_filter_escape_fails_closed(self):
        run = {
            "head_branch": "feature/not-main",
            "conclusion": "failure",
        }
        with patch.object(
            sweep,
            "request_json",
            return_value=(200, {"workflow_runs": [run]}),
        ):
            with self.assertRaisesRegex(http.DigestError, "escaped"):
                sweep.latest_run(
                    "token",
                    "repo",
                    "main",
                    workflow(1, ".github/workflows/ci.yml"),
                )

    def test_repository_counts_only_default_branch_workflows(self):
        workflows = (
            workflow(1, ".github/workflows/main.yml", "Main"),
            workflow(2, ".github/workflows/branch.yml", "Branch only"),
        )
        red = {
            "head_branch": "main",
            "conclusion": "failure",
            "run_number": 7,
            "event": "push",
            "html_url": "https://example.invalid/run/7",
        }
        with patch.object(
            sweep,
            "list_workflows",
            return_value=workflows,
        ), patch.object(
            sweep,
            "workflow_exists_on_default_branch",
            side_effect=lambda _token, _repo, _branch, item: item["id"] == 1,
        ), patch.object(sweep, "latest_run", return_value=red):
            name, reds, default_count, registered_count, excluded = (
                sweep.repository_reds(
                    "token",
                    {"name": "repo", "default_branch": "main"},
                )
            )
        self.assertEqual(name, "repo")
        self.assertEqual(len(reds), 1)
        self.assertEqual(reds[0].workflow, "Main")
        self.assertEqual(default_count, 1)
        self.assertEqual(registered_count, 2)
        self.assertEqual(excluded, 1)

    def test_coverage_reports_registry_exclusions_explicitly(self):
        repository_result = ("repo", (), 3, 5, 2)
        with patch.object(
            sweep,
            "repository_reds",
            return_value=repository_result,
        ), patch.object(
            sweep,
            "repository_floor",
            return_value=57,
        ):
            _, coverage = sweep.sweep(
                "token",
                (
                    {
                        "name": "repo",
                        "default_branch": "main",
                        "archived": False,
                    },
                ),
            )
        self.assertEqual(coverage["active_workflows"], 3)
        self.assertEqual(coverage["default_branch_workflows"], 3)
        self.assertEqual(coverage["registered_active_workflows"], 5)
        self.assertEqual(coverage["excluded_non_default_workflows"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
