#!/usr/bin/env python3
"""Bounded invocation contract for this new canonical A11oy publisher version."""
import os
import re


def validate(env):
    def need(condition):
        if not condition:
            raise ValueError("CANONICAL_PUBLISHER_INVOCATION_REJECTED")
    need(env.get("WORKFLOW_REPOSITORY") == "szl-holdings/.github")
    need(bool(re.fullmatch(r"[0-9a-f]{40}", env.get("WORKFLOW_SHA", ""))))
    need(bool(re.fullmatch(r"[0-9a-f]{40}", env.get("EVENT_SHA", ""))))
    contract = env.get("CONTRACT_ONLY")
    need(contract in {"true", "false"})
    if contract == "true":
        need(env.get("CALLER_REPOSITORY") == "szl-holdings/.github")
        need(env["WORKFLOW_SHA"] == env["EVENT_SHA"])
        need(env.get("RUNTIME_IDENTITY") == "false")
        return "READ_ONLY_EXACT_SOURCE_CONTRACT"
    need(env.get("CALLER_REPOSITORY") == "szl-holdings/a11oy")
    need(env.get("EVENT_REF") == "refs/heads/main")
    need(env.get("EVENT_NAME") in {"push", "workflow_dispatch"})
    need(env.get("DEPLOY_REF") == env["EVENT_SHA"])
    need(env.get("HF_REPO") == "SZLHOLDINGS/a11oy")
    need(env.get("RUNTIME_IDENTITY") == env.get("REQUIRE_TIP") == "true")
    need(env.get("DOCKERFILE") == "Dockerfile" and env.get("SOURCE_REVISION_FILE") == "")
    need(env.get("SOURCE_VARIABLE") == "SZL_GIT_SHA" and env.get("SOURCE_PROBE") == "/api/build-info")
    need(env.get("INCLUDE_README") == "true")
    need(env.get("PRUNE") in {"true", "false"} and env.get("RESTART") in {"true", "false"})
    wait = env.get("WAIT_RUNNING", "")
    need(bool(re.fullmatch(r"[0-9]{1,4}", wait)) and 0 <= int(wait) <= 1200)
    return "CANONICAL_A11OY_PUBLICATION"


if __name__ == "__main__":
    try:
        print(validate(os.environ))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
