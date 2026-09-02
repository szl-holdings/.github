#!/usr/bin/env python3
"""Network-free contracts for the green-only Adaptive Theatre finalizer."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "finalize_hf_adaptive_theatre_v3.py"
spec = importlib.util.spec_from_file_location("finalizer", SCRIPT)
assert spec and spec.loader
finalizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finalizer)


def sample_pr(**overrides):
    value = {
        "number": 7,
        "title": finalizer.TITLE,
        "draft": False,
        "mergeable": True,
        "mergeable_state": "clean",
        "html_url": "https://github.com/szl-holdings/demo/pull/7",
        "head": {
            "ref": finalizer.HEAD_BRANCH,
            "sha": "a" * 40,
            "repo": {"full_name": "szl-holdings/demo"},
        },
        "base": {"ref": "main", "repo": {"name": "demo"}},
    }
    value.update(overrides)
    return value


class FinalizerContract(unittest.TestCase):
    def test_missing_token_is_explicit_and_secret_free(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            argv = [str(SCRIPT), "--report", str(report)]
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch("sys.argv", argv):
                self.assertEqual(finalizer.main(), 2)
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "UNAVAILABLE")
            self.assertFalse(payload["token_recorded"])
            self.assertNotIn("Bearer", report.read_text(encoding="utf-8"))

    def test_search_accepts_only_exact_title_branch_and_same_repo(self) -> None:
        exact = sample_pr()
        wrong_title = sample_pr(title="other")
        wrong_branch = sample_pr(head={"ref": "other", "sha": "b" * 40, "repo": {"full_name": "szl-holdings/demo"}})
        wrong_repo = sample_pr(head={"ref": finalizer.HEAD_BRANCH, "sha": "c" * 40, "repo": {"full_name": "someone/demo"}})
        items = [
            {"number": 7, "repository_url": "https://api.github.com/repos/szl-holdings/demo"},
            {"number": 8, "repository_url": "https://api.github.com/repos/szl-holdings/demo"},
            {"number": 9, "repository_url": "https://api.github.com/repos/szl-holdings/demo"},
            {"number": 10, "repository_url": "https://api.github.com/repos/szl-holdings/demo"},
        ]
        responses = [{"items": items}, exact, wrong_title, wrong_branch, wrong_repo]
        with mock.patch.object(finalizer, "request_json", side_effect=responses):
            rows = finalizer.search_generated_prs("token")
        self.assertEqual(rows, [exact])

    def test_evaluate_requires_green_checks_and_resolved_threads(self) -> None:
        checks = [{"name": "verify", "status": "completed", "conclusion": "success", "html_url": "u"}]
        with (
            mock.patch.object(finalizer, "list_check_runs", return_value=checks),
            mock.patch.object(finalizer, "list_statuses", return_value=[]),
            mock.patch.object(finalizer, "latest_review_states", return_value={}),
            mock.patch.object(finalizer, "review_threads", return_value={"available": True, "unresolved": 0, "truncated": False}),
            mock.patch.object(finalizer, "repository_has_workflows", return_value=True),
        ):
            row = finalizer.evaluate("token", sample_pr())
        self.assertEqual(row["reason"], "READY")

    def test_failed_check_and_change_request_never_become_ready(self) -> None:
        failed = [{"name": "verify", "status": "completed", "conclusion": "failure", "html_url": "u"}]
        with (
            mock.patch.object(finalizer, "list_check_runs", return_value=failed),
            mock.patch.object(finalizer, "list_statuses", return_value=[]),
            mock.patch.object(finalizer, "latest_review_states", return_value={"reviewer": "CHANGES_REQUESTED"}),
            mock.patch.object(finalizer, "review_threads", return_value={"available": True, "unresolved": 0, "truncated": False}),
            mock.patch.object(finalizer, "repository_has_workflows", return_value=True),
        ):
            row = finalizer.evaluate("token", sample_pr())
        self.assertEqual(row["reason"], "CHECKS_FAILED")
        self.assertEqual(row["changes_requested_by"], ["reviewer"])

    def test_unresolved_or_unavailable_thread_state_fails_closed(self) -> None:
        checks = [{"name": "verify", "status": "completed", "conclusion": "success", "html_url": "u"}]
        common = (
            mock.patch.object(finalizer, "list_check_runs", return_value=checks),
            mock.patch.object(finalizer, "list_statuses", return_value=[]),
            mock.patch.object(finalizer, "latest_review_states", return_value={}),
            mock.patch.object(finalizer, "repository_has_workflows", return_value=True),
        )
        with common[0], common[1], common[2], common[3], mock.patch.object(finalizer, "review_threads", return_value={"available": True, "unresolved": 1, "truncated": False}):
            unresolved = finalizer.evaluate("token", sample_pr())
        self.assertEqual(unresolved["reason"], "UNRESOLVED_THREADS")

        with (
            mock.patch.object(finalizer, "list_check_runs", return_value=checks),
            mock.patch.object(finalizer, "list_statuses", return_value=[]),
            mock.patch.object(finalizer, "latest_review_states", return_value={}),
            mock.patch.object(finalizer, "repository_has_workflows", return_value=True),
            mock.patch.object(finalizer, "review_threads", return_value={"available": False, "unresolved": None, "truncated": None}),
        ):
            unavailable = finalizer.evaluate("token", sample_pr())
        self.assertEqual(unavailable["reason"], "THREAD_STATE_UNAVAILABLE")

    def test_merge_uses_exact_head_and_signed_message(self) -> None:
        row = {
            "repository": "szl-holdings/demo",
            "number": 7,
            "url": "https://github.com/szl-holdings/demo/pull/7",
            "head_sha": "a" * 40,
        }
        with (
            mock.patch.object(finalizer, "preferred_merge_method", return_value="squash"),
            mock.patch.object(finalizer, "request_json", return_value={"merged": True, "sha": "b" * 40, "message": "merged"}) as request,
        ):
            result = finalizer.merge_ready("token", row)
        payload = request.call_args.kwargs["payload"]
        self.assertEqual(payload["sha"], "a" * 40)
        self.assertEqual(payload["merge_method"], "squash")
        self.assertIn("Signed-off-by: Stephen Lutar", payload["commit_message"])
        self.assertEqual(result["merge_commit_sha"], "b" * 40)


if __name__ == "__main__":
    unittest.main()
