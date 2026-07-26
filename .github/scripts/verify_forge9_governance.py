#!/usr/bin/env python3
"""Fail-closed checks for the FORGE-9 governance controls."""

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

REMOVED_PATHS = [
    ".github/workflows/attest-and-approve.yml",
    ".github/workflows/owner-authorized-merge-wave.yml",
    ".github/workflows/owner-authorized-zero-review-wave.yml",
    ".github/scripts/ensure_org_admin_pr_bypass.py",
    ".github/scripts/finalize_zero_review_protections.py",
    ".github/scripts/owner_authorized_merge_wave.py",
    ".github/scripts/owner_authorized_merge_wave_v2.py",
    ".github/scripts/set_exact_merge_review_count_zero.py",
    ".github/data/owner_authorized_merge_wave.json",
    ".governance/github-app-manifest.json",
    ".governance/solo-operator-policy.md",
]

FORBIDDEN_EXECUTABLE_PATTERNS = {
    "zero required approvals": re.compile(
        r"required_approving_review_count[\"']?\s*[:=]\s*0"
    ),
    "administrator bypass helper": re.compile(
        r"(ensure_org_admin_pr_bypass|set_exact_merge_review_count_zero|"
        r"owner_authorized_merge_wave)"
    ),
    "privileged pull request trigger": re.compile(r"\bpull_request_target\s*:"),
    "automated approving review": re.compile(
        r"(event\s*=\s*APPROVE|event=APPROVE|pulls/.+/reviews)"
    ),
    "automated merge request": re.compile(
        r"(enqueuePullRequest|\bgh\s+pr\s+merge\b)"
    ),
}

PINNED_ACTION = re.compile(
    r"^\s*(?:-\s+)?uses:\s*[^@\s]+@[0-9a-f]{40}(?:\s+#.*)?$"
)


def fail(message: str) -> None:
    print(f"FORGE-9 invariant failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(relative: str) -> dict[str, object]:
    path = ROOT / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"{relative} is not valid JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{relative} must contain an object")
    return value


def one_rule(rules: list[dict[str, object]], kind: str) -> dict[str, object]:
    matches = [item for item in rules if item.get("type") == kind]
    if len(matches) != 1:
        fail(f"ruleset must contain exactly one {kind!r} rule")
    return matches[0]


def verify_ruleset(
    relative: str,
    name: str,
    include: list[str],
    *,
    merge_queue: bool,
) -> None:
    data = load_json(relative)
    if data.get("name") != name or data.get("enforcement") != "active":
        fail(f"{relative} name or enforcement changed")
    if data.get("bypass_actors") != []:
        fail(f"{relative} bypass_actors must be an explicit empty array")

    conditions = data.get("conditions")
    refs = conditions.get("ref_name") if isinstance(conditions, dict) else None
    if not isinstance(refs, dict) or refs.get("include") != include:
        fail(f"{relative} ref scope is not exact")

    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list):
        fail(f"{relative} rules must be an array")
    rules = [item for item in raw_rules if isinstance(item, dict)]
    for kind in (
        "deletion",
        "non_fast_forward",
        "required_linear_history",
        "required_signatures",
        "pull_request",
        "required_status_checks",
        "required_deployments",
        "commit_message_pattern",
    ):
        one_rule(rules, kind)

    queue_count = sum(item.get("type") == "merge_queue" for item in rules)
    if queue_count != int(merge_queue):
        fail(f"{relative} merge-queue scope is invalid")

    review = one_rule(rules, "pull_request").get("parameters")
    expected_review = {
        "dismiss_stale_reviews_on_push": True,
        "require_code_owner_review": False,
        "require_last_push_approval": True,
        "required_approving_review_count": 1,
        "required_review_thread_resolution": True,
    }
    if not isinstance(review, dict):
        fail(f"{relative} pull-request parameters are missing")
    for key, value in expected_review.items():
        if review.get(key) != value:
            fail(f"{relative} pull_request.{key} must be {value!r}")
    if review.get("allowed_merge_methods") != ["squash"]:
        fail(f"{relative} must allow only squash merges")

    status = one_rule(rules, "required_status_checks").get("parameters")
    required = (
        status.get("required_status_checks", [])
        if isinstance(status, dict)
        else []
    )
    contexts = [
        item.get("context") for item in required if isinstance(item, dict)
    ]
    if contexts != GATES:
        fail(f"{relative} required checks do not match the canonical gates")

    deployment = one_rule(rules, "required_deployments").get("parameters")
    environments = (
        deployment.get("required_deployment_environments")
        if isinstance(deployment, dict)
        else None
    )
    if environments != ["staging"]:
        fail(f"{relative} must require the staging deployment")


def verify_gate_contract() -> None:
    gates = load_json(".governance/gates.json")
    if list(gates) != GATES:
        fail("gates.json must declare the eight gates in canonical order")
    for name, commands in gates.items():
        if not isinstance(commands, list) or not commands:
            fail(f"{name} commands must be a non-empty array")

    for relative in (
        ".github/workflows/gates.yml",
        ".github/workflows/forge9-staging.yml",
    ):
        path = ROOT / relative
        if not path.is_file():
            fail(f"required workflow is missing: {relative}")
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if "uses:" in line and not PINNED_ACTION.match(line):
                fail(f"{relative}:{number} contains an unpinned action")

    gate_workflow = (ROOT / ".github/workflows/gates.yml").read_text(
        encoding="utf-8"
    )
    for gate in GATES:
        if gate not in gate_workflow:
            fail(f"gate workflow is missing {gate}")


def verify_review_policy() -> None:
    profile = load_json(".governance/repository-profile.json")
    if profile.get("operator_model") != "single-human-blocked":
        fail("repository profile must expose the one-human review blocker")

    policy = GOVERNANCE / "independent-review-policy.md"
    if not policy.is_file():
        fail("independent-review-policy.md is missing")
    text = policy.read_text(encoding="utf-8")
    normalized = text.lower()
    for marker in (
        "second human owner",
        "latest push requires one approving review",
        "no workflow may submit an approving review",
    ):
        if marker not in normalized:
            fail(f"independent-review policy is missing {marker!r}")


def verify_removed_paths_and_executables() -> None:
    for relative in REMOVED_PATHS:
        if (ROOT / relative).exists():
            fail(f"retired self-approval or bypass path still exists: {relative}")

    for scan_root in (ROOT / ".github/workflows", ROOT / ".github/scripts"):
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
    verify_ruleset(
        ".governance/ruleset-main.json",
        "forge9-main",
        ["~DEFAULT_BRANCH"],
        merge_queue=True,
    )
    verify_ruleset(
        ".governance/ruleset-release.json",
        "forge9-release",
        ["refs/heads/release/*"],
        merge_queue=False,
    )
    verify_gate_contract()
    verify_review_policy()
    verify_removed_paths_and_executables()
    print("FORGE-9 governance invariants verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
