#!/usr/bin/env python3
"""Assert the active PR rule parameters before exact PR #325 enqueue."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import enqueue_pr325_required_checks_only as controller
import request_exact_clean_merge_queue as preflight


def validate_pull_request_rule(rules: Any) -> dict[str, Any]:
    if not isinstance(rules, list):
        raise controller.AdmissionError("active rules response is not a list")
    candidates = [
        item.get("parameters") or {}
        for item in rules
        if isinstance(item, dict) and item.get("type") == "pull_request"
    ]
    matching = [
        parameters
        for parameters in candidates
        if parameters.get("required_review_thread_resolution") is True
        and int(parameters.get("required_approving_review_count") or 0) == 0
        and "squash" in (parameters.get("allowed_merge_methods") or [])
    ]
    if not matching:
        raise controller.AdmissionError(
            "active pull_request rule does not preserve "
            "required_review_thread_resolution=true, zero mandatory approvals, "
            "and squash admission"
        )
    return matching[-1]


def select_rule_read_credential() -> tuple[str, str]:
    for name in controller.CANDIDATE_ENV_NAMES:
        token = os.environ.get(name) or ""
        if not token:
            continue
        capability = controller.capability_probe(token)
        if (
            capability.get("user_api_authenticated") is True
            and capability.get("repository_api_authenticated") is True
            and capability.get("graphql_authenticated") is True
            and capability.get("viewer_permission")
            in controller.ALLOWED_VIEWER_PERMISSIONS
        ):
            return name, token
    raise controller.AdmissionError(
        "no governed credential can read the active PR admission rule"
    )


def main() -> int:
    secret_name, token = select_rule_read_credential()
    with controller.credential(token):
        rules = preflight._rest(controller.REPOSITORY, "rules/branches/main")
        parameters = validate_pull_request_rule(rules)
    # The underlying controller independently reselects and probes a governed
    # credential, then verifies zero unresolved threads, exact required checks,
    # signature, linear history, immutable head/base, and the
    # enqueuePullRequest(expectedHeadOid, jump=false) mutation envelope.
    print(
        "Active pull_request admission rule verified with governed credential "
        f"{secret_name}: required_review_thread_resolution="
        f"{parameters.get('required_review_thread_resolution')}"
    )
    return controller.main()


if __name__ == "__main__":
    raise SystemExit(main())
