#!/usr/bin/env python3
"""Fail-closed invocation contract for the dedicated ayllu Space publisher."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping


SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SMOKE_PATHS = [
    "/healthz",
    "/",
    "/counsel",
    "/psyche",
    "/health",
    "/readyz",
    "/api/v1/ayllu/roster",
    "/api/v1/ayllu/manifest",
    "/api/v1/counsel/allodial",
    "/api/v1/psyche/health"
]


def validate(env: Mapping[str, str]) -> str:
    """Admit only the exact caller/main/target or a read-only local witness."""

    def need(field: str, expected: str) -> None:
        if env.get(field) != expected:
            raise ValueError(f"AYLLU_PUBLISHER_INVOCATION_REJECTED:{field}")

    need("WORKFLOW_REPOSITORY", "szl-holdings/.github")
    for field in ("WORKFLOW_SHA", "EVENT_SHA"):
        if SHA40.fullmatch(env.get(field, "")) is None:
            raise ValueError(f"AYLLU_PUBLISHER_INVOCATION_REJECTED:{field}")

    contract_only = env.get("CONTRACT_ONLY")
    if contract_only == "true":
        need("CALLER_REPOSITORY", "szl-holdings/.github")
        need("EVENT_NAME", "push")
        need("EVENT_SHA", env["WORKFLOW_SHA"])
        need("HF_REPO", "")
        need("DEPLOY_REF", "main")
        need("REQUIRE_TIP", "false")
        need("SOURCE_REVISION_FILE", "")
        need("SOURCE_VARIABLE", "")
        need("SOURCE_PROBE", "")
        return "READ_ONLY_AYLLU_EXACT_SOURCE_CONTRACT"
    if contract_only != "false":
        raise ValueError("AYLLU_PUBLISHER_INVOCATION_REJECTED:CONTRACT_ONLY")

    need("CALLER_REPOSITORY", "szl-holdings/ayllu")
    need("CALLER_WORKFLOW_REF", "szl-holdings/ayllu/.github/workflows/hf-space.yml@refs/heads/main")
    need("EVENT_REF", "refs/heads/main")
    if env.get("EVENT_NAME") not in {"push", "workflow_dispatch"}:
        raise ValueError("AYLLU_PUBLISHER_INVOCATION_REJECTED:EVENT_NAME")
    need("DEPLOY_REF", env["EVENT_SHA"])
    need("HF_REPO", "SZLHOLDINGS/ayllu")
    need("REQUIRE_TIP", "true")
    need("DOCKERFILE", "Dockerfile")
    need("SOURCE_REVISION_FILE", "")
    need("SOURCE_VARIABLE", "")
    need("SOURCE_PROBE", "")
    need("INCLUDE_README", "true")
    need("PRUNE", "true")
    need("RESTART", "false")
    need("WAIT_RUNNING", "900")
    try:
        paths = json.loads(env.get("SMOKE_PATHS", ""))
    except json.JSONDecodeError as exc:
        raise ValueError("AYLLU_PUBLISHER_INVOCATION_REJECTED:SMOKE_PATHS") from exc
    if paths != SMOKE_PATHS:
        raise ValueError("AYLLU_PUBLISHER_INVOCATION_REJECTED:SMOKE_PATHS")
    return "CANONICAL_AYLLU_PUBLICATION"


if __name__ == "__main__":
    try:
        print(validate(os.environ))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
