#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fine-grained authority wrapper for recover_agent_work.py."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Mapping

MODULE_PATH = Path(__file__).with_name("recover_agent_work.py")
spec = importlib.util.spec_from_file_location("szl_recover_agent_work", MODULE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("unable to load agent-work recovery")
recovery = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = recovery
spec.loader.exec_module(recovery)


def _write_permission(repo: Mapping[str, Any]) -> bool:
    permissions = repo.get("permissions") or {}
    return bool(
        permissions.get("push")
        or permissions.get("maintain")
        or permissions.get("admin")
    )


def select_token() -> tuple[str | None, dict[str, Any]]:
    aliases = (
        "GH_ORG_ADMIN_TOKEN",
        "ORG_ADMIN_TOKEN",
        "GH_ADMIN_TOKEN",
        "SZL_GITHUB_TOKEN",
        "GITHUB_PAT",
        "GH_PAT",
        "GH_TOKEN_SECRET",
    )
    attempts: list[dict[str, Any]] = []
    key_repositories = {".github", "a11oy", "szl-forge"}
    for alias in aliases:
        token = os.getenv(alias, "").strip()
        if not token:
            continue
        print(f"::add-mask::{token}")
        api = recovery.GitHub(token)
        try:
            user = api.get("/user")
            repos = api.pages(
                f"/orgs/{recovery.ORG}/repos?type=all&sort=updated&direction=desc"
            )
            active = [
                repo
                for repo in repos
                if not repo.get("archived") and not repo.get("disabled")
            ]
            writable = [repo for repo in active if _write_permission(repo)]
            writable_names = {str(repo.get("name") or "") for repo in writable}
            membership_state = None
            membership_role = None
            membership_error = None
            try:
                membership = api.get(f"/user/memberships/orgs/{recovery.ORG}")
                membership_state = membership.get("state")
                membership_role = membership.get("role")
            except Exception as exc:
                membership_error = recovery.error(exc)
            active_membership = (
                str(membership_state or "").lower() == "active"
                and str(membership_role or "").lower() in {"admin", "member"}
            )
            complete_enumerated_write = bool(active) and len(writable) == len(active)
            key_write = key_repositories.issubset(writable_names)
            accepted = bool(
                key_write
                and (
                    complete_enumerated_write
                    or (active_membership and len(writable) >= 3)
                )
            )
            attempts.append(
                {
                    "alias": alias,
                    "identity": user.get("login"),
                    "repositories_enumerated": len(active),
                    "repositories_writable": len(writable),
                    "key_repositories_writable": key_write,
                    "complete_enumerated_write": complete_enumerated_write,
                    "org_membership": membership_state,
                    "org_role": membership_role,
                    "membership_error": membership_error,
                    "accepted": accepted,
                }
            )
            if accepted:
                return token, {
                    "state": "ACTIVE_ORG_WRITE_AUTHORITY",
                    "alias": alias,
                    "identity": user.get("login"),
                    "authority_basis": (
                        "COMPLETE_ENUMERATED_REPOSITORY_WRITE"
                        if complete_enumerated_write
                        else "ACTIVE_MEMBERSHIP_AND_KEY_REPOSITORY_WRITE"
                    ),
                    "repositories_enumerated": len(active),
                    "repositories_writable": len(writable),
                    "attempts": attempts,
                }
        except Exception as exc:
            attempts.append({"alias": alias, "error": recovery.error(exc)})
    return None, {
        "state": "UNAVAILABLE",
        "reason": "No token proved cross-repository write authority",
        "attempts": attempts,
    }


recovery.select_token = select_token
raise SystemExit(recovery.main())
