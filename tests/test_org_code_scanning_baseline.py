#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Network-free contracts for the bounded organization CodeQL operator."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / ".github" / "scripts" / "org_code_scanning_baseline.py"
SPEC = importlib.util.spec_from_file_location("org_code_scanning_baseline", MODULE_PATH)
assert SPEC and SPEC.loader
baseline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = baseline
SPEC.loader.exec_module(baseline)


class FakeGitHub:
    def __init__(self, *, apply: bool = False) -> None:
        self.apply = apply
        self.language_rows: dict[str, list[str]] = {}
        self.advanced_rows: dict[str, list[str]] = {}
        self.setup_rows: dict[str, dict[str, object]] = {}
        self.configured: list[tuple[str, list[str]]] = []
        self.fail_on: set[str] = set()

    def languages(self, repository: str) -> list[str]:
        if repository in self.fail_on:
            raise baseline.BaselineError("GitHub HTTP 403: denied")
        return list(self.language_rows.get(repository, []))

    def advanced_codeql_workflows(self, repository: str, default_branch: str) -> list[str]:
        del default_branch
        return list(self.advanced_rows.get(repository, []))

    def default_setup(self, repository: str) -> dict[str, object]:
        return dict(
            self.setup_rows.get(
                repository,
                {"state": "not-configured", "languages": []},
            )
        )

    def configure_default_setup(self, repository: str, languages: list[str]) -> dict[str, object]:
        self.configured.append((repository, list(languages)))
        return {
            "state": "configured",
            "languages": list(languages),
            "query_suite": "extended",
            "runner_type": "standard",
        }


def repo(name: str = "szl-holdings/example", **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "full_name": name,
        "default_branch": "main",
        "archived": False,
        "disabled": False,
        "fork": False,
        "private": False,
    }
    row.update(overrides)
    return row


def test_language_mapping_deduplicates_codeql_families() -> None:
    assert baseline.codeql_languages(
        ["JavaScript", "TypeScript", "Python", "C", "C++", "HTML"]
    ) == ["c-cpp", "javascript-typescript", "python"]


def test_only_active_public_nonfork_repositories_are_eligible() -> None:
    assert baseline.eligible_repository(repo()) is True
    for override in (
        {"archived": True},
        {"disabled": True},
        {"fork": True},
        {"private": True},
        {"full_name": ""},
        {"default_branch": ""},
    ):
        assert baseline.eligible_repository(repo(**override)) is False


def test_configuration_is_needed_for_missing_state_or_languages() -> None:
    assert baseline.needs_configuration(
        state="not-configured",
        current_languages=[],
        desired_languages=["python"],
    ) is True
    assert baseline.needs_configuration(
        state="configured",
        current_languages=["python"],
        desired_languages=["python"],
    ) is False
    assert baseline.needs_configuration(
        state="configured",
        current_languages=["python"],
        desired_languages=["python", "javascript-typescript"],
    ) is True


def test_unsupported_repository_is_skipped_without_write() -> None:
    api = FakeGitHub()
    api.language_rows["szl-holdings/example"] = ["HTML", "CSS"]
    result = baseline.assess_repository(api, repo())
    assert result.action == "SKIPPED_NO_SUPPORTED_LANGUAGE"
    assert result.final_state == "not-applicable"
    assert api.configured == []


def test_existing_advanced_setup_is_preserved_byte_for_byte() -> None:
    api = FakeGitHub()
    api.language_rows["szl-holdings/example"] = ["Python"]
    api.advanced_rows["szl-holdings/example"] = [
        ".github/workflows/security-analysis.yml"
    ]
    result = baseline.assess_repository(api, repo())
    assert result.action == "PRESERVED_ADVANCED_SETUP"
    assert result.final_state == "advanced"
    assert result.advanced_workflow_paths == [
        ".github/workflows/security-analysis.yml"
    ]
    assert api.configured == []


def test_complete_default_setup_is_idempotent() -> None:
    api = FakeGitHub()
    api.language_rows["szl-holdings/example"] = ["Python", "TypeScript"]
    api.setup_rows["szl-holdings/example"] = {
        "state": "configured",
        "languages": ["python", "javascript-typescript"],
    }
    result = baseline.assess_repository(api, repo())
    assert result.action == "ALREADY_CONFIGURED"
    assert result.final_languages == ["javascript-typescript", "python"]
    assert api.configured == []


def test_missing_setup_is_configured_with_all_detected_languages() -> None:
    api = FakeGitHub(apply=True)
    api.language_rows["szl-holdings/example"] = ["Go", "Java", "Kotlin"]
    result = baseline.assess_repository(api, repo())
    assert result.action == "CONFIGURED"
    assert result.final_state == "configured"
    assert api.configured == [
        ("szl-holdings/example", ["go", "java-kotlin"])
    ]


def test_permission_or_provider_failure_stays_blocked() -> None:
    api = FakeGitHub(apply=True)
    api.fail_on.add("szl-holdings/example")
    result = baseline.assess_repository(api, repo())
    assert result.action == "BLOCKED"
    assert "403" in (result.error or "")
    assert api.configured == []


def test_configuration_readback_missing_language_fails_closed() -> None:
    api = FakeGitHub(apply=True)
    api.language_rows["szl-holdings/example"] = ["Python", "TypeScript"]

    def incomplete(repository: str, languages: list[str]) -> dict[str, object]:
        api.configured.append((repository, list(languages)))
        return {"state": "configured", "languages": ["python"]}

    api.configure_default_setup = incomplete  # type: ignore[method-assign]
    result = baseline.assess_repository(api, repo())
    assert result.action == "BLOCKED"
    assert "omitted" in (result.error or "")


def test_issue_body_reports_blockers_and_nonmutation_boundaries() -> None:
    results = [
        baseline.RepositoryResult(
            repository="szl-holdings/green",
            default_branch="main",
            action="CONFIGURED",
        ),
        baseline.RepositoryResult(
            repository="szl-holdings/blocked",
            default_branch="main",
            action="BLOCKED",
            error="GitHub HTTP 403: denied",
        ),
    ]
    body = baseline.issue_body(
        org="szl-holdings",
        apply=True,
        results=results,
        generated_at="2026-09-02T20:00:00Z",
    )
    assert baseline.ISSUE_MARKER in body
    assert "`CONFIGURED`: **1**" in body
    assert "`BLOCKED`: **1**" in body
    assert "szl-holdings/blocked" in body
    assert "Existing advanced CodeQL workflows are never replaced" in body
    assert "visibility" in body
    assert "Token values are neither printed nor persisted" in body


def test_token_shapes_are_redacted() -> None:
    payload = {
        "github": "github_pat_abcdefghijklmnopqrstuvwxyz0123456789",
        "authorization": "Bearer abcdefghijklmnopqrstuvwxyz",
    }
    text = json.dumps(baseline.redact(payload))
    assert "github_pat_" not in text
    assert "Bearer abc" not in text
    assert text.count("[REDACTED]") == 2


def test_apply_without_token_fails_closed_and_emits_receipt() -> None:
    with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
        os.environ, {}, clear=True
    ):
        report = Path(directory) / "report.json"
        code = baseline.main(["--apply", "--report", str(report)])
        payload = json.loads(report.read_text(encoding="utf-8"))
    assert code == 2
    assert payload["status"] == "BLOCKED_MANAGED_PREREQUISITE"
    assert payload["token_value_recorded"] is False
    assert "token" in payload["error"].casefold()


def test_source_contains_no_source_protection_visibility_or_secret_mutation() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "/contents/",
        "/git/refs",
        "/branches/main/protection",
        "/rulesets",
        "actions/secrets",
        "dependabot/secrets",
        "codespaces/secrets",
        '"visibility":',
        '"private":',
        '"archived":',
    ):
        assert forbidden not in source
    assert "/code-scanning/default-setup" in source
