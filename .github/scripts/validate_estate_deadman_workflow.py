#!/usr/bin/env python3
"""Validate the exact authority boundary of the estate dead-man workflow."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

WORKFLOW_PATH = Path(".github/workflows/estate-deadman.yml")
EXPECTED_PERMISSIONS = {
    "actions": "read",
    "contents": "read",
    "issues": "write",
}
SCALAR = re.compile(r"^  ([a-z][a-z0-9-]*): (read|write|none)$")
CHECKOUT_ACTION = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
EXPECTED_WORKFLOW_SHA256 = (
    "f3c14a6730617569892f56a76660babb05ab7a52c43349f6d9355d3c84d3607e"
)
EXPECTED_STEP_NAMES = (
    "Harden runner",
    "Checkout exact scheduled default-branch revision",
    "Require exact schedule authority",
    "Set up Python",
    "Re-prove dead-man contracts before live observation",
    "Mint exact read-only estate observer",
    "Observe and reconcile the critical scheduled control planes",
    "Write operator summary",
    "Upload immutable supervisor evidence",
    "Require a confirmed healthy control plane",
)
EXPECTED_ACTIONS = (
    "step-security/harden-runner@05e31511f85b41b11d1cf0ef85d0992719546e2c",
    CHECKOUT_ACTION,
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1",
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
)
EXPECTED_EXPRESSIONS = (
    "github.event.repository.default_branch",
    "github.run_attempt",
    "github.run_id",
    "github.sha",
    "github.token",
    "secrets.QILLQAQ_PRIVATE_KEY",
    "steps.reader.outputs.token",
    "vars.QILLQAQ_CLIENT_ID",
)


class WorkflowContractError(RuntimeError):
    """Raised when the scheduled workflow widens or obscures its authority."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowContractError(message)


def top_level_block(lines: list[str], name: str) -> list[str]:
    header = f"{name}:"
    indices = [index for index, line in enumerate(lines) if line == header]
    require(len(indices) == 1, f"{name} must have one exact top-level mapping")
    block: list[str] = []
    for line in lines[indices[0] + 1 :]:
        if line and not line.startswith(" "):
            break
        block.append(line)
    return block


def scalar_mapping(lines: list[str], name: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in top_level_block(lines, name):
        if not line or line.lstrip().startswith("#"):
            continue
        match = SCALAR.fullmatch(line)
        require(match is not None, f"{name} contains a nested or malformed entry")
        key, value = match.groups()
        require(key not in result, f"{name} contains a duplicate key")
        result[key] = value
    return result


def first_level_mapping_keys(lines: list[str], name: str) -> list[str]:
    keys: list[str] = []
    for line in top_level_block(lines, name):
        if not line or line.lstrip().startswith("#") or line.startswith("    "):
            continue
        require(
            line.startswith("  ") and line.endswith(":"), f"{name} entry is malformed"
        )
        key = line[2:-1]
        require(bool(re.fullmatch(r"[a-z][a-z0-9_-]*", key)), f"{name} key is invalid")
        require(key not in keys, f"{name} contains a duplicate key")
        keys.append(key)
    return keys


def named_step_block(lines: list[str], name: str) -> list[str]:
    marker = f"      - name: {name}"
    indices = [index for index, line in enumerate(lines) if line == marker]
    require(len(indices) == 1, f"step {name!r} must exist exactly once")
    block = [marker]
    for line in lines[indices[0] + 1 :]:
        if line.startswith("      - ") or (line and not line.startswith(" ")):
            break
        block.append(line)
    return block


def workflow_step_names(lines: list[str]) -> tuple[str, ...]:
    names: list[str] = []
    for line in lines:
        if line.startswith("      - "):
            require(
                line.startswith("      - name: "),
                "every workflow step must have one explicit exact name",
            )
            names.append(line.removeprefix("      - name: "))
    require(len(names) == len(set(names)), "workflow step names must be unique")
    return tuple(names)


def workflow_actions(lines: list[str]) -> tuple[str, ...]:
    actions: list[str] = []
    for line in lines:
        if line.lstrip().startswith("uses:"):
            require(line.startswith("        uses: "), "action use is outside a step")
            actions.append(line[14:].split(" # ", 1)[0])
    return tuple(actions)


def step_scalar_mapping(block: list[str], name: str) -> dict[str, str]:
    header = f"        {name}:"
    indices = [index for index, line in enumerate(block) if line == header]
    require(len(indices) == 1, f"step mapping {name!r} must exist exactly once")
    result: dict[str, str] = {}
    for line in block[indices[0] + 1 :]:
        if line and len(line) - len(line.lstrip()) <= 8:
            break
        if not line or line.lstrip().startswith("#"):
            continue
        require(line.startswith("          "), f"step mapping {name!r} is malformed")
        content = line[10:]
        require(
            ": " in content and not content.startswith("#"),
            f"step mapping {name!r} entry is malformed",
        )
        key, value = content.split(": ", 1)
        require(
            bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key)),
            f"step mapping {name!r} key is invalid",
        )
        require(key not in result, f"step mapping {name!r} contains a duplicate key")
        result[key] = value
    return result


def literal_run_lines(block: list[str]) -> list[str]:
    indices = [index for index, line in enumerate(block) if line == "        run: |"]
    require(len(indices) == 1, "authority step must contain one literal run block")
    script: list[str] = []
    for line in block[indices[0] + 1 :]:
        if line and len(line) - len(line.lstrip()) <= 8:
            break
        if not line:
            script.append("")
            continue
        require(
            line.startswith("          "), "authority run block indentation is invalid"
        )
        script.append(line[10:])
    return script


def validate_workflow_source(source: str) -> dict[str, object]:
    require("\r" not in source, "workflow must use canonical LF bytes")
    workflow_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
    require(
        workflow_sha256 == EXPECTED_WORKFLOW_SHA256,
        "workflow bytes do not match the independently reviewed authority contract",
    )
    require(
        re.search(r"\\(?:u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|x[0-9A-Fa-f]{2})", source)
        is None,
        "workflow must not contain escaped semantic YAML characters",
    )
    lines = source.splitlines()
    advanced_yaml = (
        re.compile(r"^\s*\?"),
        re.compile(r"^\s*!"),
        re.compile(r"^\s*%"),
        re.compile(r"^\s*(?:---|\.\.\.)\s*$"),
        re.compile(r"^\s*<<\s*:"),
        re.compile(r"^\s*[&*]"),
        re.compile(r":\s*[&*][A-Za-z0-9_-]+(?:\s|$)"),
    )
    for line in lines:
        require(
            "!!" not in line
            and not any(pattern.search(line) for pattern in advanced_yaml),
            "workflow uses unsupported advanced YAML authority syntax",
        )
    require(
        lines.count("name: Estate dead-man supervisor") == 1,
        "workflow name is not exact",
    )
    permission_headers = [
        line for line in lines if re.match(r"^\s*['\"]?permissions['\"]?\s*:", line)
    ]
    require(
        permission_headers == ["permissions:"],
        "permissions must exist once at top level with no job override",
    )
    permissions = scalar_mapping(lines, "permissions")
    require(permissions == EXPECTED_PERMISSIONS, "workflow permissions are not exact")
    events = first_level_mapping_keys(lines, "on")
    require(events == ["schedule"], "workflow event authority is not schedule-only")
    require(
        [line for line in top_level_block(lines, "on") if line]
        == ["  schedule:", '    - cron: "7,22,37,52 * * * *"'],
        "workflow schedule is not exact",
    )
    require(
        first_level_mapping_keys(lines, "jobs") == ["supervise"],
        "workflow must contain only the admitted supervisor job",
    )
    require(
        workflow_step_names(lines) == EXPECTED_STEP_NAMES,
        "workflow step sequence is not exact",
    )
    require(
        workflow_actions(lines) == EXPECTED_ACTIONS,
        "workflow action sequence is not exact",
    )
    control_flow_keys = [
        line
        for line in lines
        if re.match(r"^\s*['\"]?(?:if|continue-on-error)['\"]?\s*:", line)
    ]
    require(
        control_flow_keys == ["        if: always()", "        if: always()"],
        "workflow step control flow is not exact",
    )

    checkout = named_step_block(
        lines, "Checkout exact scheduled default-branch revision"
    )
    uses = [line for line in checkout if line.startswith("        uses: ")]
    require(len(uses) == 1, "checkout action must exist exactly once")
    checkout_action = uses[0][14:].split(" # ", 1)[0]
    require(checkout_action == CHECKOUT_ACTION, "checkout action is not exact")
    checkout_with = step_scalar_mapping(checkout, "with")
    require(
        checkout_with
        == {
            "ref": "${{ github.sha }}",
            "persist-credentials": "false",
            "fetch-depth": "1",
        },
        "checkout inputs are not exact",
    )

    authority = named_step_block(lines, "Require exact schedule authority")
    require(
        [line for line in authority if line.startswith("        shell: ")]
        == ["        shell: bash"],
        "authority shell is not exact",
    )
    authority_env = step_scalar_mapping(authority, "env")
    require(
        authority_env
        == {"DEFAULT_BRANCH": "${{ github.event.repository.default_branch }}"},
        "authority environment is not exact",
    )
    authority_script = [line for line in literal_run_lines(authority) if line]
    require(
        authority_script
        == [
            "set -euo pipefail",
            'test "$GITHUB_REF_NAME" = "$DEFAULT_BRANCH"',
            'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
            'test "$(git status --porcelain)" = ""',
        ],
        "authority checkout proof is not exact",
    )

    reprove = named_step_block(
        lines, "Re-prove dead-man contracts before live observation"
    )
    require(
        step_scalar_mapping(reprove, "env") == {"PYTHONDONTWRITEBYTECODE": '"1"'},
        "runtime contract environment is not exact",
    )
    reprove_script = [line for line in literal_run_lines(reprove) if line]
    require(
        reprove_script
        == [
            "set -euo pipefail",
            "python -m unittest discover -s tests -p 'test_estate_deadman.py' -v",
            "python .github/scripts/validate_estate_deadman_workflow.py",
            "python .github/scripts/estate_deadman.py \\",
            "  --offline-contract-only \\",
            '  --output "$RUNNER_TEMP/estate-deadman-contract.json"',
            "git diff --check",
            'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
            'test "$(git status --porcelain --untracked-files=all)" = ""',
            "mkdir -p reports",
            'cp "$RUNNER_TEMP/estate-deadman-contract.json" reports/estate-deadman-contract.json',
        ],
        "runtime contract proof script is not exact",
    )

    reader = named_step_block(lines, "Mint exact read-only estate observer")
    require(
        step_scalar_mapping(reader, "with")
        == {
            "client-id": "${{ vars.QILLQAQ_CLIENT_ID }}",
            "private-key": "${{ secrets.QILLQAQ_PRIVATE_KEY }}",
            "owner": "szl-holdings",
            "repositories": '".github,szl-org-health,a11oy"',
            "permission-actions": "read",
            "permission-contents": "read",
        },
        "estate reader App scope is not exact",
    )

    supervisor = named_step_block(
        lines, "Observe and reconcile the critical scheduled control planes"
    )
    require(
        step_scalar_mapping(supervisor, "env")
        == {
            "ESTATE_READ_TOKEN": "${{ steps.reader.outputs.token }}",
            "GITHUB_TOKEN": "${{ github.token }}",
        },
        "supervisor token environment is not exact",
    )
    supervisor_script = [line for line in literal_run_lines(supervisor) if line]
    require(
        supervisor_script
        == [
            "set +e",
            "python .github/scripts/estate_deadman.py \\",
            "  --output reports/estate-deadman.json",
            "rc=$?",
            'echo "exit_code=$rc" >> "$GITHUB_OUTPUT"',
            "exit 0",
        ],
        "supervisor execution script is not exact",
    )

    final_gate = named_step_block(lines, "Require a confirmed healthy control plane")
    require(
        [line for line in literal_run_lines(final_gate) if line]
        == [
            "set -euo pipefail",
            "receipt_sha=\"$(sha256sum reports/estate-deadman.json | cut -d' ' -f1)\"",
            "expected_sha=\"$(tr -d '\\r\\n' < reports/estate-deadman.json.sha256)\"",
            'test "$receipt_sha" = "$expected_sha"',
            "jq -e '.schema == \"szl.estate-deadman-receipt/v1\"' reports/estate-deadman.json >/dev/null",
            "jq -e '.secret_values_recorded == false' reports/estate-deadman.json >/dev/null",
            "jq -e '.authority.controller_tip_reverified == true' reports/estate-deadman.json >/dev/null",
            "jq -e '.authority.workflow_mutation == false and .authority.deployment_mutation == false' reports/estate-deadman.json >/dev/null",
            "jq -e '.incident.ok == true' reports/estate-deadman.json >/dev/null",
            "jq -e '.confirmed_healthy == true' reports/estate-deadman.json >/dev/null",
        ],
        "terminal health gate script is not exact",
    )

    expressions = sorted(
        match.group(1).strip()
        for match in re.finditer(r"\$\{\{\s*([^}]+?)\s*\}\}", source)
    )
    require(
        tuple(expressions) == EXPECTED_EXPRESSIONS,
        "workflow expression authority is not exact",
    )

    required = (
        "persist-credentials: false",
        "ref: ${{ github.sha }}",
        "github.event.repository.default_branch",
        "cancel-in-progress: false",
    )
    for marker in required:
        require(marker in source, f"missing workflow contract marker: {marker}")
    forbidden = (
        "pull_request_target",
        "contents: write",
        "actions: write",
        "deployments: write",
        "packages: write",
        "id-token: write",
        "statuses: write",
        "pull-requests: write",
        "continue-on-error",
        "self-hosted",
    )
    for marker in forbidden:
        require(marker not in source, f"forbidden workflow authority: {marker}")
    return {
        "schema": "szl.estate-deadman-workflow-contract/v1",
        "events": events,
        "permissions": permissions,
        "checkout_action": CHECKOUT_ACTION,
        "workflow_sha256": workflow_sha256,
        "valid": True,
    }


def main() -> int:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")
    print(json.dumps(validate_workflow_source(source), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
