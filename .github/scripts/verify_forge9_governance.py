#!/usr/bin/env python3
"""Fail-closed checks for the FORGE-9 Section 18 bootstrap pack."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE = ROOT / ".governance"

GATES = [
    "gate/ground-truth",
    "gate/labels",
    "gate/schema",
    "gate/adversarial",
    "gate/verify-all",
    "gate/provenance",
    "gate/a11y-perf",
    "gate/lean",
]
ATTESTATION_STATUS = {
    "context": "attestation/qillqaq",
    "integration_id": 4395545,
}
STAGING_STATUS = {
    "context": "deploy/staging",
    "integration_id": 15368,
}
COMMIT_MESSAGE_PATTERN = (
    r"^(feat|fix|docs|chore|refactor|test|perf|build|ci|revert)"
    r"(\([a-z0-9._/-]+\))?!?: [^\r\n]{1,100}(\r?\n(.|\r|\n)*)?$"
)

LEGACY_PATHS = [
    ".github/workflows/owner-authorized-merge-wave.yml",
    ".github/workflows/owner-authorized-zero-review-wave.yml",
    ".github/scripts/ensure_org_admin_pr_bypass.py",
    ".github/scripts/finalize_zero_review_protections.py",
    ".github/scripts/owner_authorized_merge_wave.py",
    ".github/scripts/owner_authorized_merge_wave_v2.py",
    ".github/scripts/set_exact_merge_review_count_zero.py",
    ".github/data/owner_authorized_merge_wave.json",
]

FORBIDDEN_EXECUTABLE_PATTERNS = {
    "zero required approvals": re.compile(
        r"required_approving_review_count[\"']?\s*[:=]\s*0"
    ),
    "administrator bypass helper": re.compile(
        r"(ensure_org_admin_pr_bypass|set_exact_merge_review_count_zero|"
        r"owner_authorized_merge_wave)"
    ),
    "invalid merge queue flag": re.compile(r"--merge-queue\b"),
    "privileged pull request trigger": re.compile(r"\bpull_request_target\s*:"),
}

ATTESTOR_SELF_EDIT_GUARD = (
    r"^(\.github/workflows/(attest-and-approve|gates|forge9-staging)"
    r"\.ya?ml|\.governance/)"
)
GOVERNED_BASE_FILTER = (
    '.base.ref == "main"\n'
    '                  or (.base.ref | startswith("release/"))'
)


def fail(message: str) -> None:
    print(f"FORGE-9 invariant failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"{path.relative_to(ROOT)} is not valid JSON: {exc}")


def rule(rules: list[dict[str, object]], kind: str) -> dict[str, object]:
    matches = [item for item in rules if item.get("type") == kind]
    if len(matches) != 1:
        fail(f"ruleset must contain exactly one {kind!r} rule")
    return matches[0]


def verify_ruleset() -> None:
    data = load_json(GOVERNANCE / "ruleset-main.json")
    if not isinstance(data, dict):
        fail("ruleset-main.json must contain an object")
    if data.get("name") != "forge9-main" or data.get("enforcement") != "active":
        fail("ruleset name or enforcement changed")
    if data.get("bypass_actors") != []:
        fail("bypass_actors must be an explicit empty array")

    conditions = data.get("conditions", {})
    refs = conditions.get("ref_name", {}) if isinstance(conditions, dict) else {}
    include = refs.get("include", []) if isinstance(refs, dict) else []
    if include != ["~DEFAULT_BRANCH"]:
        fail("merge-queue ruleset must target only the default branch")

    rules = data.get("rules")
    if not isinstance(rules, list):
        fail("ruleset rules must be an array")
    typed_rules = [item for item in rules if isinstance(item, dict)]
    for kind in (
        "deletion",
        "non_fast_forward",
        "required_linear_history",
        "required_signatures",
        "merge_queue",
        "commit_message_pattern",
    ):
        rule(typed_rules, kind)
    main_metadata = rule(typed_rules, "commit_message_pattern").get(
        "parameters", {}
    )
    if (
        not isinstance(main_metadata, dict)
        or main_metadata.get("pattern") != COMMIT_MESSAGE_PATTERN
    ):
        fail("main commit pattern must accept a queue-generated message body")

    pull_request = rule(typed_rules, "pull_request").get("parameters", {})
    if not isinstance(pull_request, dict):
        fail("pull_request parameters missing")
    expected_review = {
        "dismiss_stale_reviews_on_push": True,
        "require_code_owner_review": False,
        "require_last_push_approval": False,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": True,
    }
    for key, value in expected_review.items():
        if pull_request.get(key) != value:
            fail(f"pull_request.{key} must be {value!r}")
    if pull_request.get("allowed_merge_methods") != ["squash"]:
        fail("squash must be the only allowed merge method")

    checks = rule(typed_rules, "required_status_checks").get("parameters", {})
    required = checks.get("required_status_checks", []) if isinstance(checks, dict) else []
    contexts = [
        item.get("context") for item in required if isinstance(item, dict)
    ]
    if contexts != GATES + [
        STAGING_STATUS["context"],
        ATTESTATION_STATUS["context"],
    ]:
        fail("required checks must contain the gates, staging, and attestation")
    if required[-2:] != [STAGING_STATUS, ATTESTATION_STATUS]:
        fail("staging and attestation checks must be pinned to their Apps")
    if any(item.get("type") == "required_deployments" for item in typed_rules):
        fail("queue-incompatible required_deployments rule must not be present")
    if required[-1] != ATTESTATION_STATUS:
        fail("attestation status must be pinned to the qillqaq App")


def verify_manifest() -> None:
    manifest = load_json(GOVERNANCE / "github-app-manifest.json")
    if not isinstance(manifest, dict):
        fail("GitHub App manifest must contain an object")
    if manifest.get("name") != "qillqaq-attestor":
        fail("GitHub App name changed")
    permissions = manifest.get("default_permissions")
    expected = {
        "actions": "read",
        "administration": "read",
        "checks": "read",
        "commit_statuses": "write",
        "contents": "read",
        "metadata": "read",
        "pull_requests": "write",
    }
    if permissions != expected:
        fail("GitHub App permissions differ from the reviewed minimum")
    if "id_token" in permissions or "id-token" in permissions:
        fail("OIDC is a workflow permission, not an App permission")
    if "merge_queues" in permissions:
        fail("the App does not require merge-queue authority")


def verify_gate_contract() -> None:
    gate_config = load_json(GOVERNANCE / "gates.json")
    if not isinstance(gate_config, dict) or list(gate_config) != GATES:
        fail("gates.json must declare the eight gates in canonical order")
    for name, commands in gate_config.items():
        if not isinstance(commands, list) or not commands:
            fail(f"{name} commands must be a non-empty array")

    for template in (
        ".github/workflows/gates.yml",
        ".github/workflows/attest-and-approve.yml",
    ):
        path = ROOT / template
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            fail(f"missing {path.relative_to(ROOT)}: {exc}")
        for label, pattern in FORBIDDEN_EXECUTABLE_PATTERNS.items():
            if pattern.search(text):
                fail(f"{path.relative_to(ROOT)} contains {label}")
    gate_template = (ROOT / ".github/workflows/gates.yml").read_text(
        encoding="utf-8"
    )
    for gate in GATES:
        if gate not in gate_template:
            fail(f"gate template is missing {gate}")

    if not (ROOT / ".github/workflows/forge9-staging.yml").is_file():
        fail("the staging deployment workflow is not active")

    attestor_template = (
        ROOT / ".github/workflows/attest-and-approve.yml"
    ).read_text(encoding="utf-8")
    if ATTESTOR_SELF_EDIT_GUARD not in attestor_template:
        fail("attestor must refuse edits to both gate and attestor workflows")
    guard = re.compile(ATTESTOR_SELF_EDIT_GUARD)
    guarded_paths = (
        ".github/workflows/attest-and-approve.yml",
        ".github/workflows/attest-and-approve.yaml",
        ".github/workflows/gates.yml",
        ".github/workflows/gates.yaml",
        ".github/workflows/forge9-staging.yml",
        ".github/workflows/forge9-staging.yaml",
        ".governance/gates.json",
    )
    for path in guarded_paths:
        if not guard.search(path):
            fail(f"attestor self-edit guard does not cover {path}")
    if guard.search(".github/workflows/unrelated.yml"):
        fail("attestor self-edit guard overmatches unrelated workflows")

    for marker in (
        "Solo-Operator-Authorization:[[:space:]]*confirmed",
        "Risk:[[:space:]]*D[[:space:]]*[-â€”]",
    ):
        if marker not in attestor_template:
            fail(f"attestor governance authorization marker missing: {marker}")

    if GOVERNED_BASE_FILTER not in attestor_template:
        fail("attestor must resolve PRs targeting main and release/*")
    if "environment: production" in attestor_template:
        fail("the merge attestor must not consume the production deployment gate")
    if "GH_TOKEN: ${{ github.token }}" not in attestor_template:
        fail("the protected queue request must use the ephemeral workflow token")
    for marker in (
        "Publish required App attestation status",
        "context=attestation/qillqaq",
        "GH_TOKEN: ${{ steps.app-token.outputs.token }}",
        "client-id: ${{ vars.QILLQAQ_CLIENT_ID }}",
        'SOURCE_EVENT: ${{ github.event.workflow_run.event }}',
        'if [ "$SOURCE_EVENT" = "merge_group" ]; then',
        '[[ "$HEAD_BRANCH" == gh-readonly-queue/main/* ]]',
        "subject_kind: $subject_kind",
    ):
        if marker not in attestor_template:
            fail(f"attestor status publication is missing {marker!r}")
    if "app-id:" in attestor_template:
        fail("the attestor must use the supported GitHub App client-id input")
    if attestor_template.count(
        "if: steps.subject.outputs.kind == 'pull_request'"
    ) != 2:
        fail("only PR-head attestations may approve or request a queue entry")
    if 'gh pr merge "$PR" --repo "$REPOSITORY" --auto --squash' not in (
        attestor_template
    ):
        fail("the attestor must use GitHub's supported merge-queue CLI path")

    release = load_json(GOVERNANCE / "ruleset-release.json")
    if not isinstance(release, dict):
        fail("ruleset-release.json must contain an object")
    if (
        release.get("name") != "forge9-release"
        or release.get("enforcement") != "active"
    ):
        fail("release ruleset name or enforcement changed")
    if release.get("bypass_actors") != []:
        fail("release bypass_actors must be an explicit empty array")
    release_conditions = release.get("conditions", {})
    release_refs = (
        release_conditions.get("ref_name", {})
        if isinstance(release_conditions, dict)
        else {}
    )
    if (
        not isinstance(release_refs, dict)
        or release_refs.get("include") != ["refs/heads/release/*"]
    ):
        fail("release ruleset must target release/*")
    release_rules = release.get("rules")
    if not isinstance(release_rules, list):
        fail("release ruleset rules must be an array")
    typed_release_rules = [
        item for item in release_rules if isinstance(item, dict)
    ]
    if any(item.get("type") == "merge_queue" for item in typed_release_rules):
        fail("release wildcard ruleset must not contain a merge queue")
    for kind in (
        "deletion",
        "non_fast_forward",
        "required_linear_history",
        "required_signatures",
        "commit_message_pattern",
    ):
        rule(typed_release_rules, kind)
    release_metadata = rule(
        typed_release_rules, "commit_message_pattern"
    ).get("parameters", {})
    if (
        not isinstance(release_metadata, dict)
        or release_metadata.get("pattern") != COMMIT_MESSAGE_PATTERN
    ):
        fail("release commit pattern must accept a squash message body")

    release_pull_request = rule(
        typed_release_rules, "pull_request"
    ).get("parameters", {})
    if not isinstance(release_pull_request, dict):
        fail("release pull_request parameters missing")
    expected_release_review = {
        "dismiss_stale_reviews_on_push": True,
        "require_code_owner_review": False,
        "require_last_push_approval": False,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": True,
    }
    for key, value in expected_release_review.items():
        if release_pull_request.get(key) != value:
            fail(f"release pull_request.{key} must be {value!r}")
    if release_pull_request.get("allowed_merge_methods") != ["squash"]:
        fail("release ruleset must allow only squash merges")

    release_checks = rule(
        typed_release_rules, "required_status_checks"
    ).get("parameters", {})
    release_required = (
        release_checks.get("required_status_checks", [])
        if isinstance(release_checks, dict)
        else []
    )
    release_contexts = [
        item.get("context")
        for item in release_required
        if isinstance(item, dict)
    ]
    if release_contexts != GATES + [
        STAGING_STATUS["context"],
        ATTESTATION_STATUS["context"],
    ]:
        fail("release checks must contain gates, staging, and attestation")
    if release_required[-2:] != [STAGING_STATUS, ATTESTATION_STATUS]:
        fail("release staging and attestation checks must be App-pinned")
    if any(
        item.get("type") == "required_deployments"
        for item in typed_release_rules
    ):
        fail("release must use the merge-compatible staging status check")


def verify_legacy_paths_removed() -> None:
    for relative in LEGACY_PATHS:
        if (ROOT / relative).exists():
            fail(f"legacy bypass path still exists: {relative}")

    scan_roots = [ROOT / ".github" / "workflows", ROOT / ".github" / "scripts"]
    for scan_root in scan_roots:
        for path in scan_root.rglob("*"):
            if not path.is_file() or path == Path(__file__):
                continue
            if path.suffix.lower() not in {".py", ".yml", ".yaml", ".json"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for label, pattern in FORBIDDEN_EXECUTABLE_PATTERNS.items():
                if pattern.search(text):
                    fail(f"{path.relative_to(ROOT)} contains {label}")


def main() -> int:
    verify_ruleset()
    verify_manifest()
    verify_gate_contract()
    verify_legacy_paths_removed()
    print("FORGE-9 bootstrap invariants verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
