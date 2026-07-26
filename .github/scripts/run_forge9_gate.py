#!/usr/bin/env python3
"""Repository-specific FORGE-9 checks for the organization governance repo."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE = ROOT / ".governance"
PINNED_ACTION = re.compile(
    r"^\s*(?:-\s+)?uses:\s*[^@\s]+@[0-9a-f]{40}(?:\s+#.*)?$"
)


def fail(message: str) -> None:
    print(f"FORGE-9 gate failed: {message}", file=sys.stderr)
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


def run_verifier() -> None:
    completed = subprocess.run(
        [sys.executable, ".github/scripts/verify_forge9_governance.py"],
        cwd=ROOT,
        check=False,
    )
    if completed.returncode:
        fail("the complete governance invariant verifier failed")


def ground_truth() -> None:
    ruleset = load_json(".governance/ruleset-main.json")
    if ruleset.get("name") != "forge9-main":
        fail("ruleset identity changed")
    if ruleset.get("bypass_actors") != []:
        fail("ruleset bypass actors are not empty")
    rules = ruleset.get("rules")
    if not isinstance(rules, list):
        fail("ruleset rules are missing")
    pull_rules = [
        item for item in rules
        if isinstance(item, dict) and item.get("type") == "pull_request"
    ]
    if len(pull_rules) != 1:
        fail("exactly one pull-request rule is required")
    parameters = pull_rules[0].get("parameters")
    if not isinstance(parameters, dict):
        fail("pull-request parameters are missing")
    if parameters.get("required_approving_review_count") != 0:
        fail("solo policy must not claim a human approval")


def labels() -> None:
    template = (ROOT / ".github/pull_request_template.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "Satisfies:",
        "Labels:",
        "Rollback:",
        "Risk:",
        "Known limitations introduced",
    ):
        if marker not in template:
            fail(f"pull-request evidence template is missing {marker!r}")


def schema() -> None:
    gates = load_json(".governance/gates.json")
    profile = load_json(".governance/repository-profile.json")
    manifest = load_json(".governance/github-app-manifest.json")
    if len(gates) != 8:
        fail("the canonical gate map must contain eight gates")
    if profile.get("operator_model") != "solo":
        fail("repository profile must declare the solo operator model")
    if manifest.get("name") != "qillqaq-attestor":
        fail("attestor manifest identity changed")


def adversarial() -> None:
    run_verifier()


def verify_all() -> None:
    run_verifier()
    for relative in (
        ".github/scripts/run_forge9_gate.py",
        ".github/scripts/verify_forge9_governance.py",
        ".governance/forge9_gate_runner.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        compile(source, relative, "exec")


def provenance() -> None:
    manifest = load_json(".governance/github-app-manifest.json")
    permissions = manifest.get("default_permissions")
    if not isinstance(permissions, dict):
        fail("App permissions are missing")
    if permissions.get("contents") != "read":
        fail("the App must not have write access to repository contents")
    if permissions.get("merge_queues") != "write":
        fail("the App requires only dedicated queue authority")
    for relative in (
        ".github/workflows/gates.yml",
        ".github/workflows/attest-and-approve.yml",
        ".github/workflows/forge9-staging.yml",
    ):
        for number, line in enumerate(
            (ROOT / relative).read_text(encoding="utf-8").splitlines(), start=1
        ):
            if "uses:" in line and not PINNED_ACTION.match(line):
                fail(f"{relative}:{number} contains an unpinned action")


def a11y_perf() -> None:
    profile = load_json(".governance/repository-profile.json")
    if profile.get("repository_class") != "organization-governance":
        fail("accessibility/performance scope is not classified")
    if profile.get("ui_surface") is not False:
        fail("a UI repository must provide real accessibility/performance checks")
    if (ROOT / "package.json").exists():
        fail("repository profile says no UI, but package.json exists")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    if "contains no" not in agents or "application code" not in agents:
        fail("the no-UI classification lacks repository-level evidence")


def lean() -> None:
    profile = load_json(".governance/repository-profile.json")
    if profile.get("lean_surface") is not True:
        fail("the repository contains Lean and must declare that surface")
    baseline = profile.get("lean_sorry_baseline")
    if not isinstance(baseline, int) or baseline < 0:
        fail("the Lean sorry baseline is missing")
    sources = list(ROOT.rglob("*.lean"))
    if not sources:
        fail("Lean surface is declared but no Lean sources exist")
    sorry_count = 0
    for path in sources:
        text = path.read_text(encoding="utf-8")
        sorry_count += len(re.findall(r"^\s*sorry\s*$", text, re.MULTILINE))
    if sorry_count > baseline:
        fail(f"Lean sorry count increased from {baseline} to {sorry_count}")
    print(f"gate/lean: sorry count {sorry_count} <= baseline {baseline}")


GATES = {
    "gate/ground-truth": ground_truth,
    "gate/labels": labels,
    "gate/schema": schema,
    "gate/adversarial": adversarial,
    "gate/verify-all": verify_all,
    "gate/provenance": provenance,
    "gate/a11y-perf": a11y_perf,
    "gate/lean": lean,
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in GATES:
        print(f"usage: {Path(sys.argv[0]).name} gate/name", file=sys.stderr)
        return 2
    gate = sys.argv[1]
    GATES[gate]()
    print(f"{gate}: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
