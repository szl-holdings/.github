#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Network-free contracts for organization CodeQL baseline v2."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest import mock

import pytest

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


WORKFLOW_PATH = ROOT / ".github/workflows/org-code-scanning-baseline.yml"
CONTRACT_PATH = ROOT / ".github/workflows/org-code-scanning-baseline-contract.yml"


def run_workflow_contract(source: str, directory: Path) -> subprocess.CompletedProcess[str]:
    """Execute the exact CI assertion against an isolated, credential-free fixture."""
    contract = CONTRACT_PATH.read_text(encoding="utf-8")
    step = "      - name: Validate the workflow authority and mutation boundary\n"
    assert contract.count(step) == 1
    program = contract.split(step, 1)[1].split("          python - <<'PY'\n", 1)[1]
    program = textwrap.dedent(program.split("          PY\n", 1)[0])
    target = directory / ".github/workflows/org-code-scanning-baseline.yml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.encode("utf-8"))
    return subprocess.run(
        [sys.executable, "-I", "-c", program],
        cwd=directory,
        env={"PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_workflow_contract_accepts_existing_job_scoped_authority(tmp_path: Path) -> None:
    result = run_workflow_contract(WORKFLOW_PATH.read_text(encoding="utf-8"), tmp_path)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("old", "new"),
    [
        pytest.param("permissions: read-all", "permissions: write-all", id="root-write-all"),
        pytest.param(
            "permissions: read-all",
            "permissions:\n  contents: read\n  issues: write\n  security-events: write",
            id="root-write-mapping",
        ),
        pytest.param("permissions: read-all", "permissions: read-all\npermissions: write-all", id="duplicate-root-grant"),
        pytest.param("      contents: read", "      contents: write", id="contents-write"),
        *[
            pytest.param(
                "      contents: read",
                f"      contents: read\n      {scope}: write",
                id=f"extra-{scope}",
            )
            for scope in ("actions", "id-token", "packages", "pull-requests")
        ],
        *[
            pytest.param(f"      {scope}: {grant}\n", "", id=f"missing-{scope}")
            for scope, grant in (("contents", "read"), ("issues", "write"), ("security-events", "write"))
        ],
        *[
            pytest.param(f"      {scope}: {grant}", f"      {scope}: none", id=f"downgraded-{scope}")
            for scope, grant in (("contents", "read"), ("issues", "write"), ("security-events", "write"))
        ],
        pytest.param("      issues: write", "      issues: write\n      issues: none", id="duplicate-grant"),
        pytest.param("    permissions:", "    permissions: write-all\n    permissions:", id="duplicate-job-grant"),
        pytest.param("jobs:\n", "jobs: {}\njobs:\n", id="duplicate-jobs"),
        pytest.param("  converge:\n", "  converge: {}\n  converge:\n", id="duplicate-converge"),
        pytest.param("  converge:\n", "  extra:\n    permissions: write-all\n  converge:\n", id="additional-job"),
        pytest.param("permissions: read-all", '"permissions": read-all', id="quoted-root-key"),
        pytest.param("    permissions:", '    "permissions":', id="quoted-job-key"),
        pytest.param("    permissions:", '    "\\x70ermissions":', id="escaped-job-key"),
        pytest.param("jobs:\n", '"jobs":\n', id="quoted-jobs-key"),
        pytest.param("  converge:\n", '  "converge":\n', id="quoted-converge-key"),
        pytest.param("      issues: write", '      "issues": write', id="quoted-grant-key"),
        pytest.param("      issues: write", '      issues: "write"', id="quoted-grant-value"),
        pytest.param("    permissions:", "    permissions: {contents: read, issues: write, security-events: write}", id="flow-mapping"),
        pytest.param("    permissions:", "    permissions: &grants", id="anchor"),
        pytest.param("    permissions:", "    permissions: *grants", id="alias"),
        pytest.param("      issues: write", "      <<: *grants\n      issues: write", id="merge-key"),
        pytest.param("    permissions:", "    ? permissions\n    :", id="explicit-key"),
        pytest.param("    permissions:", "    permissions: !!map", id="tag"),
        pytest.param("      issues: write", "      issues: ${{ 'write' }}", id="expression-grant"),
        pytest.param("      issues: write", "      issues: >\n        write", id="folded-grant"),
        pytest.param("      issues: write", "      issues:\n        nested: write", id="nested-grant"),
        pytest.param("      issues: write", "    issues: write", id="wrong-scope"),
        pytest.param("permissions: read-all", "# permissions: read-all", id="commented-root"),
        pytest.param("    permissions:", "    # permissions:", id="commented-job"),
        pytest.param("      issues: write", "      # issues: write", id="commented-grant"),
        pytest.param("permissions: read-all", 'description: "permissions: read-all"', id="quoted-root-decoy"),
        pytest.param("permissions: read-all", 'description: "continued\npermissions: read-all\n  end"', id="multiline-root-decoy"),
        pytest.param("permissions: read-all", "---\npermissions: read-all", id="document-start"),
        pytest.param("permissions: read-all", "%YAML 1.2\npermissions: read-all", id="directive"),
        pytest.param("    steps:\n", "    steps: |\n", id="noncanonical-boundary"),
        pytest.param("    steps:\n", "    steps:\n    steps:\n", id="duplicate-boundary"),
    ],
)
def test_workflow_contract_rejects_authority_prefix_mutations(
    tmp_path: Path, old: str, new: str
) -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert source.count(old) == 1
    result = run_workflow_contract(source.replace(old, new, 1), tmp_path)
    assert result.returncode != 0, (old, new, result.stdout)


@pytest.mark.parametrize(
    "suffix",
    [
        pytest.param("\npermissions: write-all\n", id="late-root-grant"),
        pytest.param("\n    permissions: write-all\n", id="late-job-grant"),
        pytest.param("\n  extra:\n    permissions: write-all\n", id="late-extra-job"),
        pytest.param("\njobs:\n  converge:\n    permissions: write-all\n", id="late-duplicate-jobs"),
        pytest.param('\n"permissions": write-all\n', id="late-quoted-root"),
        pytest.param('\n    "\\x70ermissions": write-all\n', id="late-escaped-job"),
        pytest.param("\n    <<: *grants\n", id="late-job-merge"),
        pytest.param("\n    ? permissions\n    : write-all\n", id="late-explicit-key"),
        pytest.param("\n---\npermissions: write-all\n", id="late-document-start"),
        pytest.param("\n...\n", id="late-document-end"),
        pytest.param("\n%YAML 1.2\n", id="late-directive"),
        pytest.param("\n# harmless comment\npermissions: write-all\n", id="comment-hides-dedent"),
        pytest.param('      - name: "continued\npermissions: write-all\n        end"\n', id="multiline-string-dedent"),
        pytest.param("      - run: |\npermissions: write-all\n", id="literal-block-dedent"),
        *[
            pytest.param(f"      # comment{separator}permissions: write-all\n", id=f"unicode-line-{ord(separator):x}")
            for separator in ("\x85", "\u2028", "\u2029")
        ],
        pytest.param("\n      # carriage return\r\n", id="carriage-return"),
        pytest.param("\n      # tab\t\n", id="tab"),
        pytest.param("\n      # nul\0\n", id="nul"),
    ],
)
def test_workflow_contract_rejects_suffix_authority_and_control_characters(
    tmp_path: Path, suffix: str
) -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    result = run_workflow_contract(source + suffix, tmp_path)
    assert result.returncode != 0, (suffix, result.stdout)


@pytest.mark.parametrize(
    "decoy",
    [
        "\n      # permissions: read-all\n",
        "\n      - env:\n          DECOY: 'permissions: read-all'\n",
        "\n      - run: |\n          permissions: read-all\n",
    ],
    ids=("comment", "env-string", "run-literal"),
)
def test_workflow_contract_rejects_permissions_present_only_in_decoys(
    tmp_path: Path, decoy: str
) -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8").replace("permissions: read-all\n", "", 1)
    result = run_workflow_contract(source + decoy, tmp_path)
    assert result.returncode != 0, result.stdout


def test_workflow_contract_allows_step_comments_and_action_pin_changes(tmp_path: Path) -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    references = list(re.finditer(
        r"(?m)^        uses: step-security/harden-runner@([0-9a-f]{40})(?: #.*)?$",
        source,
    ))
    assert len(references) == 1
    reference = references[0]
    original_sha = reference.group(1)
    changed_sha = ("0" if original_sha[0] != "0" else "1") + original_sha[1:]
    changed = source[:reference.start(1)] + changed_sha + source[reference.end(1):]
    assert changed != source
    source = changed
    source += "\n# A comment cannot redefine authority.\n      # Step-local documentation.\n"
    result = run_workflow_contract(source, tmp_path)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "token",
    [
        "python .github/scripts/org_code_scanning_baseline_v2.py",
        "--apply",
        "if-no-files-found: error",
        "org-code-scanning-baseline-${{ github.run_id }}-${{ github.run_attempt }}",
        "secrets.SZL_ORG_ADMIN_TOKEN || secrets.ORG_ADMIN_TOKEN || secrets.SZL_GITHUB_TOKEN || secrets.GH_PAT || github.token",
    ],
)
@pytest.mark.parametrize("mutation", ("missing", "repeated"))
def test_workflow_contract_preserves_required_markers(
    tmp_path: Path, token: str, mutation: str
) -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert source.count(token) == 1
    if mutation == "missing":
        source = source.replace(token, "omitted-contract-marker", 1)
    else:
        source += f"\n      # {token}\n"
    result = run_workflow_contract(source, tmp_path)
    assert result.returncode != 0, (token, mutation, result.stdout)


@pytest.mark.parametrize(
    "token",
    ("continue-on-error: true", "|| true", "contents: write", "pull-requests: write"),
)
def test_workflow_contract_preserves_forbidden_markers(tmp_path: Path, token: str) -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8") + f"\n      # {token}\n"
    result = run_workflow_contract(source, tmp_path)
    assert result.returncode != 0, result.stdout
    assert "forbidden CodeQL workflow weakening:" in result.stderr
