#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Network-free contracts for organization CodeQL baseline v2."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / ".github" / "scripts" / "org_code_scanning_baseline_v2.py"
SPEC = importlib.util.spec_from_file_location("org_code_scanning_baseline_v2", MODULE_PATH)
assert SPEC and SPEC.loader
codeql = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = codeql
SPEC.loader.exec_module(codeql)


class FakeGitHub:
    def __init__(self, *, apply: bool = False) -> None:
        self.apply = apply
        self.language_rows: dict[str, list[str]] = {}
        self.setup_rows: dict[str, dict[str, object]] = {}
        self.analysis_rows: dict[str, dict[str, object] | None] = {}
        self.configured: list[tuple[str, list[str]]] = []
        self.fail: set[str] = set()

    def languages(self, repository: str) -> list[str]:
        if repository in self.fail:
            raise codeql.BaselineError("GitHub HTTP 403: denied")
        return list(self.language_rows.get(repository, []))

    def default_setup(self, repository: str) -> dict[str, object]:
        return dict(
            self.setup_rows.get(
                repository,
                {"state": "not-configured", "languages": []},
            )
        )

    def latest_analysis(self, repository: str) -> dict[str, object] | None:
        value = self.analysis_rows.get(repository)
        return dict(value) if value else None

    def configure_default_setup(
        self, repository: str, desired_languages: list[str]
    ) -> dict[str, object]:
        self.configured.append((repository, list(desired_languages)))
        return {
            "state": "configured",
            "languages": list(desired_languages),
            "query_suite": "extended",
            "runner_type": "standard",
        }


def repository(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "full_name": "szl-holdings/example",
        "default_branch": "main",
        "archived": False,
        "disabled": False,
        "fork": False,
        "private": False,
    }
    row.update(overrides)
    return row


def test_supported_languages_collapse_to_codeql_families() -> None:
    assert codeql.codeql_languages(
        ["C", "C++", "JavaScript", "TypeScript", "Python", "HTML"]
    ) == ["c-cpp", "javascript-typescript", "python"]


def test_only_active_public_nonfork_repositories_are_eligible() -> None:
    assert codeql.eligible_repository(repository()) is True
    for override in (
        {"archived": True},
        {"disabled": True},
        {"fork": True},
        {"private": True},
        {"full_name": ""},
        {"default_branch": ""},
    ):
        assert codeql.eligible_repository(repository(**override)) is False


def test_unsupported_language_repo_is_skipped() -> None:
    api = FakeGitHub()
    api.language_rows["szl-holdings/example"] = ["HTML", "CSS"]
    result = codeql.assess_repository(api, repository())
    assert result.action == "SKIPPED_NO_SUPPORTED_LANGUAGE"
    assert api.configured == []


def test_complete_default_setup_is_idempotent() -> None:
    api = FakeGitHub()
    api.language_rows["szl-holdings/example"] = ["Python", "TypeScript"]
    api.setup_rows["szl-holdings/example"] = {
        "state": "configured",
        "languages": ["python", "javascript-typescript"],
    }
    result = codeql.assess_repository(api, repository())
    assert result.action == "ALREADY_CONFIGURED"
    assert result.final_languages == ["javascript-typescript", "python"]
    assert api.configured == []


def test_existing_analysis_is_preserved_instead_of_replaced() -> None:
    api = FakeGitHub(apply=True)
    api.language_rows["szl-holdings/example"] = ["Python"]
    api.analysis_rows["szl-holdings/example"] = {
        "id": 5,
        "tool": "CodeQL",
        "ref": "refs/heads/main",
        "commit_sha": "a" * 40,
    }
    result = codeql.assess_repository(api, repository())
    assert result.action == "PRESERVED_EXISTING_ANALYSIS"
    assert result.final_state == "existing-analysis"
    assert result.existing_analysis == api.analysis_rows["szl-holdings/example"]
    assert api.configured == []


def test_missing_analysis_and_setup_are_configured() -> None:
    api = FakeGitHub(apply=True)
    api.language_rows["szl-holdings/example"] = ["Go", "Java", "Kotlin"]
    result = codeql.assess_repository(api, repository())
    assert result.action == "CONFIGURED"
    assert result.final_state == "configured"
    assert api.configured == [
        ("szl-holdings/example", ["go", "java-kotlin"])
    ]


def test_configured_setup_missing_new_language_is_extended() -> None:
    api = FakeGitHub(apply=True)
    api.language_rows["szl-holdings/example"] = ["Python", "TypeScript"]
    api.setup_rows["szl-holdings/example"] = {
        "state": "configured",
        "languages": ["python"],
    }
    result = codeql.assess_repository(api, repository())
    assert result.action == "CONFIGURED"
    assert api.configured == [
        (
            "szl-holdings/example",
            ["javascript-typescript", "python"],
        )
    ]


def test_provider_permission_failure_remains_blocked() -> None:
    api = FakeGitHub(apply=True)
    api.fail.add("szl-holdings/example")
    result = codeql.assess_repository(api, repository())
    assert result.action == "BLOCKED"
    assert "403" in (result.error or "")


def test_incomplete_provider_readback_is_rejected() -> None:
    api = FakeGitHub(apply=True)
    api.language_rows["szl-holdings/example"] = ["Python", "TypeScript"]

    def incomplete(
        repository_name: str, desired_languages: list[str]
    ) -> dict[str, object]:
        api.configured.append((repository_name, list(desired_languages)))
        return {"state": "configured", "languages": ["python"]}

    api.configure_default_setup = incomplete  # type: ignore[method-assign]
    result = codeql.assess_repository(api, repository())
    assert result.action == "BLOCKED"
    assert "omitted" in (result.error or "")


def test_compact_analysis_drops_provider_noise() -> None:
    result = codeql.compact_analysis(
        {
            "id": 17,
            "ref": "refs/heads/main",
            "commit_sha": "b" * 40,
            "analysis_key": ".github/workflows/codeql.yml:analyze",
            "category": "/language:python",
            "environment": "{}",
            "created_at": "2026-09-02T20:00:00Z",
            "tool": {"name": "CodeQL", "version": "99", "guid": "ignored"},
            "results_count": 100,
        }
    )
    assert result == {
        "id": 17,
        "ref": "refs/heads/main",
        "commit_sha": "b" * 40,
        "analysis_key": ".github/workflows/codeql.yml:analyze",
        "category": "/language:python",
        "environment": "{}",
        "created_at": "2026-09-02T20:00:00Z",
        "tool": "CodeQL",
    }


def test_issue_body_records_actions_blockers_and_boundaries() -> None:
    body = codeql.issue_body(
        org="szl-holdings",
        apply=True,
        generated_at="2026-09-02T20:00:00Z",
        results=[
            codeql.RepositoryResult(
                repository="szl-holdings/green",
                default_branch="main",
                action="CONFIGURED",
            ),
            codeql.RepositoryResult(
                repository="szl-holdings/blocked",
                default_branch="main",
                action="BLOCKED",
                error="GitHub HTTP 403: denied",
            ),
        ],
    )
    assert codeql.ISSUE_MARKER in body
    assert "`CONFIGURED`: **1**" in body
    assert "`BLOCKED`: **1**" in body
    assert "Existing code-scanning analyses are never replaced" in body
    assert "protections" in body
    assert "Token values are neither printed nor persisted" in body


def test_token_shapes_are_redacted() -> None:
    payload = {
        "github": "github_pat_abcdefghijklmnopqrstuvwxyz0123456789",
        "authorization": "Bearer abcdefghijklmnopqrstuvwxyz",
    }
    encoded = json.dumps(codeql.redact(payload))
    assert "github_pat_" not in encoded
    assert "Bearer abc" not in encoded
    assert encoded.count("[REDACTED]") == 2


def test_apply_without_token_fails_closed_with_secret_free_receipt() -> None:
    with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
        os.environ, {}, clear=True
    ):
        report = Path(directory) / "report.json"
        return_code = codeql.main(["--apply", "--report", str(report)])
        payload = json.loads(report.read_text(encoding="utf-8"))
    assert return_code == 2
    assert payload["status"] == "BLOCKED_MANAGED_PREREQUISITE"
    assert payload["token_value_recorded"] is False


def test_source_can_change_only_native_default_setup_and_command_issue() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert '"PATCH",\n            f"/repos/{repository}/code-scanning/default-setup"' in source
    for forbidden in (
        "/branches/main/protection",
        "/rulesets",
        "/git/refs",
        "actions/secrets",
        "dependabot/secrets",
        "codespaces/secrets",
        '"visibility":',
        '"private":',
        '"archived":',
    ):
        assert forbidden not in source
