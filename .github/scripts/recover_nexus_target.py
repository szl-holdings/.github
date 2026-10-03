#!/usr/bin/env python3
"""Explicit, fail-closed recovery of the one Nexus provider projection.

Run only from the protected central workflow. A Hub 404 is ambiguous: a Space
may be absent or private and inaccessible. Creation uses the exact occupied
name with ``exist_ok=False`` and never changes visibility on an existing Space.
The separate one-target bootstrap grant defaults to disabled. The lifecycle
reconciler's ``create: false`` boundary remains unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping


TARGET = "SZLHOLDINGS/nexus"
TOKEN_SOURCES = (
    ("HF_ORG_TOKEN", "HF_ORG_TOKEN_CANDIDATE"),
    ("HF_ORG_TOKEN1", "HF_ORG_TOKEN1_CANDIDATE"),
    ("HF_WRITE_TOKEN", "HF_WRITE_TOKEN_CANDIDATE"),
    ("HF_TOKEN", "HF_TOKEN_CANDIDATE"),
)
TOKEN_SHAPE = re.compile(r"hf_[A-Za-z0-9._-]+\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class RecoveryError(RuntimeError):
    """The requested recovery has no verified authority or result."""


def check_context(
    environment: Mapping[str, str], policy_path: Path, grant_path: Path
) -> None:
    if (
        environment.get("GITHUB_REPOSITORY") != "szl-holdings/.github"
        or environment.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or environment.get("GITHUB_REF") != "refs/heads/main"
        or not SHA40.fullmatch(environment.get("GITHUB_SHA") or "")
    ):
        raise RecoveryError("exact central main dispatch is required")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    matches = [
        row for row in policy.get("targets", [])
        if isinstance(row, dict) and row.get("repo_id") == TARGET
    ]
    if (
        policy.get("schema") != "szl.hf.space-lifecycle-policy.v2"
        or policy.get("organization") != "SZLHOLDINGS"
        or policy.get("token_authority", {}).get("required_org_role") != "admin"
        or len(matches) != 1
        or matches[0].get("desired_visibility") != "public"
        or matches[0].get("role") != "bound-service"
        or policy.get("boundaries", {}).get("create") is not False
    ):
        raise RecoveryError("protected lifecycle policy does not authorize this target")
    grant = json.loads(grant_path.read_text(encoding="utf-8"))
    expected_grant = {
        "schema": "szl.hf.nexus-target-bootstrap-authorization.v1",
        "target": TARGET,
        "repo_type": "space",
        "space_sdk": "docker",
        "visibility": "public",
        "scope": "one-time-create-if-absent",
        "lifecycle_create_boundary": "preserved-false",
        "enabled": True,
    }
    if grant != expected_grant:
        raise RecoveryError("protected exact-target bootstrap grant is absent or disabled")


def _admin(identity: Mapping[str, object]) -> bool:
    return any(
        isinstance(org, dict)
        and str(org.get("name") or "").casefold() == "szlholdings"
        and org.get("roleInOrg") == "admin"
        for org in (identity.get("orgs") or [])
    )


def _exact_public(info: object) -> bool:
    return (
        getattr(info, "id", None) == TARGET
        and getattr(info, "private", None) is False
    )


def _attempt(source: str, phase: str, error: BaseException) -> dict:
    return {
        "source": source,
        "phase": phase,
        "error_type": type(error).__name__,
        "status_code": getattr(getattr(error, "response", None), "status_code", None),
    }


def recover(
    environment: Mapping[str, str],
    *,
    api_factory: Callable[..., object] | None = None,
) -> dict:
    if api_factory is None:
        from huggingface_hub import HfApi

        api_factory = HfApi
    attempts: list[dict] = []
    for source, variable in TOKEN_SOURCES:
        token = str(environment.get(variable) or "").strip()
        if not TOKEN_SHAPE.fullmatch(token):
            continue
        try:
            api = api_factory(token=token)
            identity = api.whoami()
            if not isinstance(identity, dict) or not identity.get("name"):
                raise RecoveryError("identity was not confirmed")
        except Exception as error:
            attempts.append(_attempt(source, "identity", error))
            if attempts[-1]["status_code"] in (401, 403) or isinstance(error, RecoveryError):
                continue
            return {"state": "BLOCKED_AUTHORITY_UNCERTAIN", "attempts": attempts}

        try:
            api.auth_check(repo_id=TARGET, repo_type="space", write=True)
        except Exception as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            if status != 404:
                attempts.append(_attempt(source, "write_check", error))
                if status in (401, 403):
                    continue
                return {"state": "BLOCKED_AUTHORITY_UNCERTAIN", "attempts": attempts}
            if not _admin(identity):
                attempts.append({
                    "source": source,
                    "phase": "org_admin_check",
                    "error_type": "OrgAdminUnverified",
                    "status_code": None,
                })
                continue
            try:
                api.create_repo(
                    repo_id=TARGET,
                    repo_type="space",
                    space_sdk="docker",
                    private=False,
                    exist_ok=False,
                )
            except Exception as create_error:
                attempts.append(_attempt(source, "create", create_error))
                if attempts[-1]["status_code"] in (401, 403, 409):
                    continue
                return {"state": "UNKNOWN_AFTER_ATTEMPT", "attempts": attempts}
            try:
                api.auth_check(repo_id=TARGET, repo_type="space", write=True)
                info = api.repo_info(repo_id=TARGET, repo_type="space")
                if not _exact_public(info):
                    raise RecoveryError("exact public target readback failed")
            except Exception as verify_error:
                attempts.append(_attempt(source, "post_create_readback", verify_error))
                return {"state": "UNKNOWN_AFTER_ATTEMPT", "attempts": attempts}
            attempts.append({"source": source, "phase": "create_readback", "status_code": 200})
            return {"state": "CREATED_PUBLIC_WRITE_CONFIRMED", "attempts": attempts}

        try:
            info = api.repo_info(repo_id=TARGET, repo_type="space")
            if not _exact_public(info):
                raise RecoveryError("existing target does not match public policy")
        except Exception as error:
            attempts.append(_attempt(source, "existing_readback", error))
            return {"state": "BLOCKED_EXISTING_TARGET_MISMATCH", "attempts": attempts}
        attempts.append({"source": source, "phase": "existing_readback", "status_code": 200})
        return {"state": "EXISTING_PUBLIC_WRITE_CONFIRMED", "attempts": attempts}
    return {"state": "BLOCKED_NO_TARGET_WRITER", "attempts": attempts}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--grant", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args(argv)
    result: dict = {"state": "BLOCKED_BOUNDARY", "attempts": []}
    try:
        check_context(os.environ, args.policy, args.grant)
        result = (
            {"state": "AUTHORIZED_TARGET_BOOTSTRAP_PENDING", "attempts": []}
            if args.preflight else recover(os.environ)
        )
    except Exception as error:
        result = {
            "state": "BLOCKED_BOUNDARY",
            "attempts": [_attempt("none", "context", error)],
        }
    report = {
        "schema": "szl.nexus-target-recovery/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": {"repo_id": TARGET, "repo_type": "space", "visibility": "public"},
        **result,
        "token_recorded": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"Nexus target recovery: {result['state']}")
    return 0 if result["state"] in (
        "AUTHORIZED_TARGET_BOOTSTRAP_PENDING",
        "CREATED_PUBLIC_WRITE_CONFIRMED",
        "EXISTING_PUBLIC_WRITE_CONFIRMED",
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
