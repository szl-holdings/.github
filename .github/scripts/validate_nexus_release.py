#!/usr/bin/env python3
# Copyright 2026 SZL Holdings - SPDX-License-Identifier: Apache-2.0
"""Read-only admission for an exact, owner-requested Nexus release.

This validates supplied context and observed Git revisions, not environment
approval or authentication. GitHub enforces the fixed production environment
on the dependent publish job. No provider credentials or network are used here.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence

WORKFLOW_REF = (
    "szl-holdings/.github/.github/workflows/publish-nexus-space.yml@refs/heads/main"
)
_SHA = re.compile(r"[0-9a-f]{40}", re.ASCII)


class ReleaseError(ValueError):
    """A release request is absent, unbound, or no longer current."""


def exact_sha(value: str, label: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise ReleaseError(f"{label} must be exactly 40 lowercase hexadecimal characters")
    return value


def validate_request(
    context: Mapping[str, str], requested_sha: str, policy_sha: str
) -> str:
    required = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REPOSITORY": "szl-holdings/.github",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_PROTECTED": "true",
        "GITHUB_WORKFLOW_REF": WORKFLOW_REF,
    }
    for key, expected in required.items():
        if context.get(key) != expected:
            raise ReleaseError(f"{key} is outside the protected manual release boundary")
    expected_policy = exact_sha(context.get("GITHUB_SHA", ""), "policy event SHA")
    if (
        exact_sha(context.get("GITHUB_WORKFLOW_SHA", ""), "workflow SHA")
        != expected_policy
        or exact_sha(policy_sha, "checked-out policy SHA") != expected_policy
    ):
        raise ReleaseError("publisher policy must equal the exact workflow/event SHA")
    return exact_sha(requested_sha, "source_sha")


def validate_source(requested_sha: str, checkout_sha: str, main_sha: str) -> None:
    requested_sha = exact_sha(requested_sha, "source_sha")
    if exact_sha(checkout_sha, "checked-out Nexus SHA") != requested_sha:
        raise ReleaseError("checked-out Nexus source differs from the requested SHA")
    if exact_sha(main_sha, "current Nexus main SHA") != requested_sha:
        raise ReleaseError("stale release: Nexus main no longer equals the requested SHA")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--policy-sha", required=True)
    parser.add_argument("--checkout-sha")
    parser.add_argument("--main-sha")
    args = parser.parse_args(argv)
    try:
        source = validate_request(os.environ, args.source_sha, args.policy_sha)
        if args.checkout_sha is not None or args.main_sha is not None:
            if args.checkout_sha is None or args.main_sha is None:
                raise ReleaseError("checkout SHA and current main SHA must be supplied together")
            validate_source(source, args.checkout_sha, args.main_sha)
    except ReleaseError as exc:
        print(f"Nexus release blocked: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "schema": "szl.nexus-release-request/v1",
        "source_repository": "szl-holdings/nexus",
        "source_sha": source,
        "current_tip_checked": args.main_sha is not None,
        "scope": "READ_ONLY_REQUEST_VALIDATION_NOT_RELEASE_APPROVAL",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
