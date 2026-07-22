#!/usr/bin/env python3
"""Finalize the owner's zero-review policy without weakening other protections.

Required approving review counts intentionally remain zero. This utility repairs
only the non-review state left by the earlier merge wave:

* re-enable classic ``enforce_admins`` on four exact repositories so admins are
  again subject to status checks, signatures, linear history, force-push/deletion
  restrictions, and every other classic branch protection;
* remove the single transient ``OrganizationAdmin`` ``pull_request`` bypass actor
  from Platform ruleset 16195495.

All protection payloads are read back and compared. Any unexpected approval
count, actor shape, permission, or collateral state change fails closed.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API = "https://api.github.com"
API_VERSION = "2022-11-28"
PLATFORM_REPOSITORY = "szl-holdings/platform"
PLATFORM_RULESET_ID = 16195495
CLASSIC_REPOSITORIES = (
    "szl-holdings/szl-energy-attest",
    "szl-holdings/szl-lambda-gate",
    "szl-holdings/szl-lake",
    "szl-holdings/david-leads",
)


class GateError(RuntimeError):
    """Fail-closed cleanup error."""


def request(
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    allow_status: set[int] | None = None,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "szl-finalize-zero-review-protections/1.0",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if allow_status and exc.code in allow_status:
            return None
        detail = exc.read().decode("utf-8", "replace")[:5000]
        raise GateError(
            f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise GateError(
            f"GitHub API {method} {path} failed: {type(exc).__name__}: {exc}"
        ) from exc
    return json.loads(raw.decode("utf-8")) if raw else None


def encode_repo(repository: str) -> tuple[str, str]:
    owner, name = repository.split("/", 1)
    return urllib.parse.quote(owner, safe=""), urllib.parse.quote(name, safe="")


def assert_admin(token: str, identity: str, repository: str) -> None:
    owner, name = encode_repo(repository)
    permission = request(
        token,
        "GET",
        f"/repos/{owner}/{name}/collaborators/"
        f"{urllib.parse.quote(identity, safe='')}/permission",
    ).get("permission")
    if permission != "admin":
        raise GateError(
            f"{identity} has permission {permission!r}, not admin, on {repository}"
        )


def classic_count(protection: dict[str, Any]) -> int:
    reviews = protection.get("required_pull_request_reviews")
    if not isinstance(reviews, dict):
        raise GateError("classic review protection is missing")
    return int(reviews.get("required_approving_review_count") or 0)


def stable_classic_state(protection: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "required_status_checks",
        "required_pull_request_reviews",
        "restrictions",
        "required_linear_history",
        "allow_force_pushes",
        "allow_deletions",
        "block_creations",
        "required_conversation_resolution",
        "lock_branch",
        "allow_fork_syncing",
    )
    return {key: copy.deepcopy(protection.get(key)) for key in keys}


def finalize_classic(
    token: str,
    repository: str,
    *,
    execute: bool,
) -> dict[str, Any]:
    owner, name = encode_repo(repository)
    path = f"/repos/{owner}/{name}/branches/main/protection"
    before = request(token, "GET", path)
    if not isinstance(before, dict):
        raise GateError(f"classic protection unreadable: {repository}")
    if classic_count(before) != 0:
        raise GateError(
            f"{repository} required approval count is {classic_count(before)}, expected 0"
        )
    stable_before = stable_classic_state(before)
    admin_path = path + "/enforce_admins"
    admin_before = request(token, "GET", admin_path, allow_status={404})
    enabled_before = bool(
        isinstance(admin_before, dict) and admin_before.get("enabled")
    )
    action = "already-enabled"
    if not enabled_before:
        action = "would-enable" if not execute else "enabled"
        if execute:
            request(token, "POST", admin_path)

    admin_after = (
        request(token, "GET", admin_path, allow_status={404})
        if execute
        else admin_before
    )
    enabled_after = bool(
        isinstance(admin_after, dict) and admin_after.get("enabled")
    )
    after = request(token, "GET", path)
    if stable_classic_state(after) != stable_before:
        raise GateError(f"{repository} changed outside enforce_admins")
    if classic_count(after) != 0:
        raise GateError(f"{repository} zero-review policy changed")
    if execute and not enabled_after:
        raise GateError(f"{repository} enforce_admins was not enabled")

    return {
        "repository": repository,
        "action": action,
        "required_approving_review_count": 0,
        "enforce_admins_before": enabled_before,
        "enforce_admins_after": enabled_after if execute else enabled_before,
        "preserved": stable_before,
    }


def normalize_actor(actor: dict[str, Any]) -> dict[str, Any]:
    return {
        "actor_id": actor.get("actor_id"),
        "actor_type": actor.get("actor_type"),
        "bypass_mode": actor.get("bypass_mode"),
    }


def ruleset_review_count(ruleset: dict[str, Any]) -> int:
    pull_rules = [
        rule
        for rule in ruleset.get("rules") or []
        if rule.get("type") == "pull_request"
    ]
    if len(pull_rules) != 1:
        raise GateError(
            f"expected one Platform pull_request rule, found {len(pull_rules)}"
        )
    return int(
        (pull_rules[0].get("parameters") or {}).get(
            "required_approving_review_count"
        )
        or 0
    )


def stable_ruleset_state(ruleset: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": ruleset.get("name"),
        "target": ruleset.get("target"),
        "enforcement": ruleset.get("enforcement"),
        "conditions": copy.deepcopy(ruleset.get("conditions") or {}),
        "rules": copy.deepcopy(ruleset.get("rules") or []),
    }


def finalize_platform_ruleset(
    token: str,
    *,
    execute: bool,
) -> dict[str, Any]:
    endpoint = f"/repos/szl-holdings/platform/rulesets/{PLATFORM_RULESET_ID}"
    before = request(token, "GET", endpoint)
    if before.get("id") != PLATFORM_RULESET_ID:
        raise GateError("Platform ruleset id changed")
    if before.get("target") != "branch" or before.get("enforcement") != "active":
        raise GateError("Platform ruleset is not an active branch ruleset")
    if ruleset_review_count(before) != 0:
        raise GateError(
            f"Platform required approval count is {ruleset_review_count(before)}, expected 0"
        )

    actors_before = [
        normalize_actor(actor) for actor in before.get("bypass_actors") or []
    ]
    transient = [
        actor
        for actor in actors_before
        if actor.get("actor_type") == "OrganizationAdmin"
        and actor.get("bypass_mode") == "pull_request"
    ]
    if len(transient) > 1:
        raise GateError(
            f"multiple transient Platform OrganizationAdmin actors found: {len(transient)}"
        )
    actors_after = [actor for actor in actors_before if actor not in transient]
    action = "already-absent"
    if transient:
        action = "would-remove" if not execute else "removed"
        if execute:
            request(token, "PUT", endpoint, {"bypass_actors": actors_after})

    after = request(token, "GET", endpoint) if execute else before
    if stable_ruleset_state(after) != stable_ruleset_state(before):
        raise GateError("Platform ruleset changed outside bypass_actors")
    if ruleset_review_count(after) != 0:
        raise GateError("Platform zero-review policy changed")
    actual_actors = [
        normalize_actor(actor) for actor in after.get("bypass_actors") or []
    ]
    expected_actors = actors_after if execute else actors_before
    if actual_actors != expected_actors:
        raise GateError("Platform bypass actor readback differs from expected")
    if execute and any(
        actor.get("actor_type") == "OrganizationAdmin"
        and actor.get("bypass_mode") == "pull_request"
        for actor in actual_actors
    ):
        raise GateError("transient Platform OrganizationAdmin actor remains")

    return {
        "repository": PLATFORM_REPOSITORY,
        "ruleset_id": PLATFORM_RULESET_ID,
        "action": action,
        "required_approving_review_count": 0,
        "bypass_actors_before": actors_before,
        "bypass_actors_after": actual_actors if execute else actors_before,
        "preserved": stable_ruleset_state(before),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    report: dict[str, Any] = {
        "schema": "szl.zero-review-protection-finalization/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execute": bool(args.execute),
        "identity": None,
        "classic": [],
        "platform": None,
        "ok": False,
        "errors": [],
    }
    token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    try:
        if not token:
            raise GateError("SZL_GITHUB_TOKEN is not configured")
        identity = str(request(token, "GET", "/user").get("login") or "")
        if not identity:
            raise GateError("authenticated identity has no login")
        report["identity"] = identity
        for repository in (*CLASSIC_REPOSITORIES, PLATFORM_REPOSITORY):
            assert_admin(token, identity, repository)

        report["classic"] = [
            finalize_classic(token, repository, execute=args.execute)
            for repository in CLASSIC_REPOSITORIES
        ]
        report["platform"] = finalize_platform_ruleset(
            token, execute=args.execute
        )
        report["ok"] = True
        code = 0
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        code = 1
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
