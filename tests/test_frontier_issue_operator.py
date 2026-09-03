#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Network-free fail-closed contracts for the frontier issue operator."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / ".github" / "scripts" / "frontier_issue_operator.py"
SPEC = importlib.util.spec_from_file_location("frontier_issue_operator", MODULE_PATH)
assert SPEC and SPEC.loader
operator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = operator
SPEC.loader.exec_module(operator)


def test_exact_duplicate_fingerprint_is_whitespace_and_case_stable() -> None:
    first = operator.issue_fingerprint(
        "[Runtime] Space failed",
        "The exact runtime returned 404.  Preserve evidence and repair source parity.",
    )
    second = operator.issue_fingerprint(
        "  [runtime]   SPACE failed ",
        "The exact runtime returned 404.\nPreserve evidence and repair source parity.",
    )
    assert first is not None
    assert first == second


def test_short_or_missing_body_is_never_auto_duplicate() -> None:
    assert operator.issue_fingerprint("same title", None) is None
    assert operator.issue_fingerprint("same title", "short") is None


def test_classification_prioritizes_p0_before_provider_or_runtime() -> None:
    assert operator.classify_issue(
        "P0 unsafe model loader",
        "Hugging Face runtime uses public joblib and needs a provider token.",
    ) == "estate:p0"
    assert operator.classify_issue(
        "Cloudflare redirect",
        "Requires zone-scoped owner credential.",
    ) == "estate:blocked-external"
    assert operator.classify_issue(
        "Space source drift",
        "Runtime build-info does not equal protected main.",
    ) == "estate:runtime-drift"


def clean_pull() -> tuple[operator.GitHub, dict[str, object]]:
    api = mock.create_autospec(operator.GitHub, instance=True)
    api.apply = False
    api.repository.return_value = {"default_branch": "main"}
    api.pull.return_value = {
        "draft": False,
        "mergeable": True,
        "mergeable_state": "clean",
        "base": {"ref": "main"},
        "head": {
            "sha": "a" * 40,
            "repo": {"full_name": "szl-holdings/example"},
        },
    }
    api.checks.return_value = operator.CheckState(
        count=3,
        passed=["tests", "security", "DCO"],
        failed=[],
        active=[],
    )
    api.reviews.return_value = []
    api.unresolved_threads.return_value = 0
    api.merge.return_value = "DRY_RUN"
    item = {
        "repository_url": "https://api.github.com/repos/szl-holdings/example",
        "number": 7,
        "title": "fix: exact defect",
        "html_url": "https://github.com/szl-holdings/example/pull/7",
    }
    return api, item


def test_clean_exact_head_would_merge() -> None:
    api, item = clean_pull()
    result = operator.evaluate_pr(api, item)
    assert result.action == "WOULD_MERGE"
    assert result.blockers == []
    api.merge.assert_called_once_with(
        "szl-holdings/example", 7, "a" * 40, "fix: exact defect"
    )


def test_draft_failure_active_check_and_thread_each_block_merge() -> None:
    api, item = clean_pull()
    api.pull.return_value["draft"] = True
    api.checks.return_value = operator.CheckState(
        count=3,
        passed=["DCO"],
        failed=["tests"],
        active=["CodeQL"],
    )
    api.unresolved_threads.return_value = 1
    result = operator.evaluate_pr(api, item)
    assert result.action == "BLOCKED"
    assert "draft" in result.blockers
    assert "failed-checks" in result.blockers
    assert "active-checks" in result.blockers
    assert "unresolved-review-threads" in result.blockers
    api.merge.assert_not_called()


def test_external_fork_and_non_default_base_never_merge() -> None:
    api, item = clean_pull()
    api.pull.return_value["base"] = {"ref": "release"}
    api.pull.return_value["head"]["repo"] = {"full_name": "someone/fork"}
    result = operator.evaluate_pr(api, item)
    assert "external-fork" in result.blockers
    assert "non-default-base" in result.blockers
    api.merge.assert_not_called()


def test_no_check_evidence_never_merges() -> None:
    api, item = clean_pull()
    api.checks.return_value = operator.CheckState()
    result = operator.evaluate_pr(api, item)
    assert result.action == "BLOCKED"
    assert "no-check-evidence" in result.blockers
    api.merge.assert_not_called()


def test_token_shapes_are_redacted_recursively() -> None:
    payload = {
        "github": "github_pat_abcdefghijklmnopqrstuvwxyz0123456789",
        "hub": ["hf_abcdefghijklmnopqrstuvwxyz0123456789"],
    }
    safe = operator.redact(payload)
    text = json.dumps(safe)
    assert "github_pat_" not in text
    assert "hf_" not in text
    assert text.count("[REDACTED]") == 2


def test_apply_without_token_fails_closed_and_records_no_value() -> None:
    with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
        os.environ, {}, clear=True
    ), mock.patch(
        "sys.argv",
        [
            str(MODULE_PATH),
            "--apply",
            "--report",
            str(Path(directory) / "report.json"),
        ],
    ):
        assert operator.main() == 2
        report = json.loads(
            (Path(directory) / "report.json").read_text(encoding="utf-8")
        )
    assert report["status"] == "BLOCKED_MANAGED_PREREQUISITE"
    assert report["token_value_recorded"] is False


def test_duplicate_closure_is_exact_and_leaves_pointer() -> None:
    api = mock.create_autospec(operator.GitHub, instance=True)
    api.apply = True
    api.search.return_value = [
        {
            "repository_url": "https://api.github.com/repos/szl-holdings/example",
            "number": 1,
            "title": "Same defect",
            "body": "This is a sufficiently long exact duplicate issue body for testing.",
            "html_url": "https://github.com/szl-holdings/example/issues/1",
            "updated_at": "2026-09-01T00:00:00Z",
            "labels": [],
        },
        {
            "repository_url": "https://api.github.com/repos/szl-holdings/example",
            "number": 2,
            "title": "Same defect",
            "body": "This is a sufficiently long exact duplicate issue body for testing.",
            "html_url": "https://github.com/szl-holdings/example/issues/2",
            "updated_at": "2026-09-02T00:00:00Z",
            "labels": [],
        },
    ]
    rows = operator.reconcile_issues(api, "szl-holdings", limit=10)
    assert rows[0].action == "CLOSED_EXACT_DUPLICATE"
    assert rows[0].duplicate_of.endswith("/issues/2")
    api.close_duplicate.assert_called_once_with(
        "szl-holdings/example",
        1,
        "https://github.com/szl-holdings/example/issues/2",
    )
    assert rows[1].action == "CLASSIFIED"


def test_nonidentical_issue_bodies_are_only_classified() -> None:
    api = mock.create_autospec(operator.GitHub, instance=True)
    api.apply = True
    api.search.return_value = [
        {
            "repository_url": "https://api.github.com/repos/szl-holdings/example",
            "number": 1,
            "title": "Same title",
            "body": "First materially distinct long body with one implementation contract.",
            "html_url": "https://github.com/szl-holdings/example/issues/1",
            "updated_at": "2026-09-01T00:00:00Z",
            "labels": [],
        },
        {
            "repository_url": "https://api.github.com/repos/szl-holdings/example",
            "number": 2,
            "title": "Same title",
            "body": "Second materially distinct long body with another implementation contract.",
            "html_url": "https://github.com/szl-holdings/example/issues/2",
            "updated_at": "2026-09-02T00:00:00Z",
            "labels": [],
        },
    ]
    rows = operator.reconcile_issues(api, "szl-holdings", limit=10)
    assert all(row.action == "CLASSIFIED" for row in rows)
    api.close_duplicate.assert_not_called()
    assert api.set_classification.call_count == 2


def test_source_contains_no_protection_visibility_archive_or_secret_mutation() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "/branches/main/protection",
        "/rulesets",
        '"private":',
        '"visibility":',
        '"archived":',
        "actions/secrets",
        "dependabot/secrets",
        "codespaces/secrets",
    )
    for token in forbidden:
        assert token not in source



def test_identical_issues_in_different_repositories_are_not_closed() -> None:
    api = mock.create_autospec(operator.GitHub, instance=True)
    api.apply = True
    body = "This exact long issue text is valid independently for two repository components."
    api.search.return_value = [
        {
            "repository_url": "https://api.github.com/repos/szl-holdings/alpha",
            "number": 1,
            "title": "Same component defect",
            "body": body,
            "html_url": "https://github.com/szl-holdings/alpha/issues/1",
            "updated_at": "2026-09-01T00:00:00Z",
            "labels": [],
        },
        {
            "repository_url": "https://api.github.com/repos/szl-holdings/beta",
            "number": 1,
            "title": "Same component defect",
            "body": body,
            "html_url": "https://github.com/szl-holdings/beta/issues/1",
            "updated_at": "2026-09-02T00:00:00Z",
            "labels": [],
        },
    ]
    rows = operator.reconcile_issues(api, "szl-holdings", limit=10)
    assert all(row.action == "CLASSIFIED" for row in rows)
    api.close_duplicate.assert_not_called()
    assert api.set_classification.call_count == 2


def test_classification_replaces_stale_estate_labels_and_preserves_human_labels() -> None:
    api = operator.GitHub("test-token", apply=True)
    api.ensure_label = mock.Mock()
    api.request = mock.Mock(return_value=({}, {}, 200))
    api.set_classification(
        "szl-holdings/example",
        9,
        "estate:runtime-drift",
        ["bug", "estate:backlog", "estate:code-actionable"],
    )
    api.ensure_label.assert_called_once_with(
        "szl-holdings/example", "estate:runtime-drift"
    )
    api.request.assert_called_once_with(
        "PATCH",
        "/repos/szl-holdings/example/issues/9",
        {"labels": ["bug", "estate:runtime-drift"]},
        expected=(200,),
    )
