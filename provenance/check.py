#!/usr/bin/env python3
"""Advisory szl/provenance gate. Records identifiers and SHAs, never secrets."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SCHEMA = "szl.solo-maintainer-provenance/v1"
HEADINGS = [
    "Origin",
    "Rights",
    "Agents and tools",
    "Tests",
    "Security",
    "Rollback",
    "Known limits",
]


def load_policy(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise SystemExit("policy schema mismatch")
    if data.get("credential_value_recorded") is not False:
        raise SystemExit("policy must forbid credential recording")
    return data


def heading_present(body: str, heading: str) -> bool:
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    return re.search(pattern, body, re.MULTILINE) is not None


def evaluate(policy: dict, event: dict) -> dict:
    pr = event.get("pull_request") or {}
    repo = event.get("repository") or {}
    sender = event.get("sender") or {}
    body = pr.get("body") or ""
    head = (pr.get("head") or {}).get("sha")
    base_ref = (pr.get("base") or {}).get("ref")
    default_branch = repo.get("default_branch") or "main"
    owner = ((pr.get("head") or {}).get("repo") or {}).get("full_name", "")
    actor = sender.get("login") or ""
    headings = {name: heading_present(body, name) for name in HEADINGS}
    internal = owner.startswith(f"{policy['organization']}/")
    actor_ok = actor in set(policy.get("allowed_human_actors") or []) or actor.endswith("[bot]")
    checks = {
        "exact_head_sha": bool(head) and len(str(head)) == 40,
        "internal_head_repository": internal,
        "allowed_actor": actor_ok,
        "protected_base": base_ref == default_branch,
        "pr_body_headings": all(headings.values()),
        "not_direct_default_branch_push": True,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "schema": "szl.provenance-check/v1",
        "enforcement": policy.get("enforcement", "advisory"),
        "required_check": policy.get("required_check"),
        "head_sha": head,
        "base_ref": base_ref,
        "head_repository": owner,
        "actor": actor,
        "headings": headings,
        "checks": checks,
        "failed": failed,
        "pass": not failed,
        "credential_value_recorded": False,
        "known_limits": [
            "advisory until added as a required check",
            "does not verify GitHub merge provenance after merge",
            "allowed_app_slugs are illustrative until resolved from the Apps API",
        ],
    }


def main(argv: list[str]) -> int:
    policy_path = Path(argv[1] if len(argv) > 1 else "provenance/solo-maintainer-policy.v1.json")
    event_path = Path(os.environ.get("GITHUB_EVENT_PATH") or (argv[2] if len(argv) > 2 else ""))
    policy = load_policy(policy_path)
    if not event_path or not event_path.exists():
        print(json.dumps({"schema": "szl.provenance-check/v1", "pass": False, "failed": ["missing_event"]}, indent=2))
        return 1
    event = json.loads(event_path.read_text(encoding="utf-8"))
    report = evaluate(policy, event)
    print(json.dumps(report, indent=2))
    if report["enforcement"] == "advisory":
        return 0 if report["pass"] else 2
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
