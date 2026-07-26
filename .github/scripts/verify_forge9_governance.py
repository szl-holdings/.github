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
    if include != ["~DEFAULT_BRANCH", "refs/heads/release/*"]:
        fail("ruleset must target the default branch and release/*")

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
        "required_deployments",
        "commit_message_pattern",
    ):
        rule(typed_rules, kind)

    pull_request = rule(typed_rules, "pull_request").get("parameters", {})
    if not isinstance(pull_request, dict):
        fail("pull_request parameters missing")
    expected_review = {
        "dismiss_stale_reviews_on_push": True,
        "require_code_owner_review": False,
        "require_last_push_approval": True,
        "required_approving_review_count": 1,
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
    if contexts != GATES:
        fail("required status checks do not match the eight canonical gates")

    deployments = rule(typed_rules, "required_deployments").get("parameters", {})
    if not isinstance(deployments, dict):
        fail("required_deployments parameters missing")
    if deployments.get("required_deployment_environments") != ["staging"]:
        fail("staging must be the required deployment")


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
        "commit_statuses": "read",
        "contents": "read",
        "merge_queues": "write",
        "metadata": "read",
        "pull_requests": "write",
    }
    if permissions != expected:
        fail("GitHub App permissions differ from the reviewed minimum")
    if "id_token" in permissions or "id-token" in permissions:
        fail("OIDC is a workflow permission, not an App permission")


def verify_gate_contract() -> None:
    gate_config = load_json(GOVERNANCE / "gates.json")
    if not isinstance(gate_config, dict) or list(gate_config) != GATES:
        fail("gates.json must declare the eight gates in canonical order")
    for name, commands in gate_config.items():
        if not isinstance(commands, list):
            fail(f"{name} commands must be an array")

    for template in ("templates/gates.yml", "templates/attest-and-approve.yml"):
        path = GOVERNANCE / template
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            fail(f"missing {path.relative_to(ROOT)}: {exc}")
        for label, pattern in FORBIDDEN_EXECUTABLE_PATTERNS.items():
            if pattern.search(text):
                fail(f"{path.relative_to(ROOT)} contains {label}")
    gate_template = (GOVERNANCE / "templates/gates.yml").read_text(
        encoding="utf-8"
    )
    for gate in GATES:
        if gate not in gate_template:
            fail(f"gate template is missing {gate}")


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
