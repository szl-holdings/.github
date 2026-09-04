#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Authority runner accepting either org membership or complete enumerated write access."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Mapping

MODULE_PATH = Path(__file__).with_name("reconcile_agent_estate.py")
spec = importlib.util.spec_from_file_location("szl_reconcile_agent_estate", MODULE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("unable to load estate reconciler")
reconciler = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reconciler
spec.loader.exec_module(reconciler)


def _write_permission(repo: Mapping[str, Any]) -> bool:
    permissions = repo.get("permissions") or {}
    return bool(
        permissions.get("push")
        or permissions.get("maintain")
        or permissions.get("admin")
    )


def select_github_token() -> tuple[Any | None, dict[str, Any]]:
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
        api = reconciler.GitHubApi(token)
        try:
            user = api.get("/user")
            login = str(user.get("login") or "")
            repos = api.paginate(
                f"/orgs/{reconciler.ORG}/repos?type=all&sort=updated&direction=desc"
            )
            active = [
                repo
                for repo in repos
                if not repo.get("archived") and not repo.get("disabled")
            ]
            writable = [repo for repo in active if _write_permission(repo)]
            writable_names = {str(repo.get("name") or "") for repo in writable}
            missing = sorted(
                str(repo.get("name") or "")
                for repo in active
                if not _write_permission(repo)
            )
            membership_state = None
            membership_role = None
            membership_error = None
            try:
                membership = api.get(
                    f"/user/memberships/orgs/{reconciler.ORG}"
                )
                membership_state = membership.get("state")
                membership_role = membership.get("role")
            except Exception as exc:
                membership_error = reconciler.safe_error(exc)
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
            attempt = {
                "alias": alias,
                "identity": login,
                "active": True,
                "repositories_enumerated": len(active),
                "repositories_writable": len(writable),
                "missing_write_count": len(missing),
                "missing_write_names_sha256": (
                    reconciler.sha256_json(missing) if missing else None
                ),
                "key_repositories_writable": key_write,
                "org_membership": membership_state,
                "org_role": membership_role,
                "membership_error": membership_error,
                "complete_enumerated_write": complete_enumerated_write,
                "accepted": accepted,
            }
            attempts.append(attempt)
            if accepted:
                return api, {
                    "state": "ACTIVE_WRITE_AUTHORITY",
                    "alias": alias,
                    "identity": login,
                    "authority_basis": (
                        "COMPLETE_ENUMERATED_REPOSITORY_WRITE"
                        if complete_enumerated_write
                        else "ACTIVE_MEMBERSHIP_AND_KEY_REPOSITORY_WRITE"
                    ),
                    "repositories_enumerated": len(active),
                    "repositories_writable": len(writable),
                    "org_membership": membership_state,
                    "org_role": membership_role,
                    "attempts": attempts,
                }
        except Exception as exc:
            attempts.append(
                {"alias": alias, "active": False, "error": reconciler.safe_error(exc)}
            )

    fallback = os.getenv("REPOSITORY_TOKEN", "").strip()
    if fallback:
        print(f"::add-mask::{fallback}")
        attempts.append(
            {
                "alias": "REPOSITORY_TOKEN",
                "active": True,
                "authority": "CURRENT_REPOSITORY_ONLY",
                "accepted_for_org_reconciliation": False,
            }
        )
    return None, {
        "state": "UNAVAILABLE",
        "reason": (
            "No token proved write authority across the active repository estate "
            "or active org membership plus the three key repositories"
        ),
        "attempts": attempts,
    }


def select_hf_token() -> tuple[str | None, dict[str, Any]]:
    aliases = (
        "HF_ORG_TOKEN",
        "HF_ORG_TOKEN1",
        "HF_WRITE_TOKEN",
        "HF_TOKEN",
        "HUGGINGFACE_TOKEN",
        "HUGGING_FACE_HUB_TOKEN",
    )
    attempts: list[dict[str, Any]] = []
    try:
        from huggingface_hub import HfApi
    except Exception as exc:
        return None, {
            "state": "CLIENT_UNAVAILABLE",
            "error": reconciler.safe_error(exc),
            "attempts": attempts,
        }

    for alias in aliases:
        token = os.getenv(alias, "").strip()
        if not token:
            continue
        print(f"::add-mask::{token}")
        try:
            api = HfApi(token=token)
            identity = api.whoami()
            name = identity.get("name") if isinstance(identity, Mapping) else None
            orgs = identity.get("orgs") if isinstance(identity, Mapping) else []
            role = None
            for org in orgs or []:
                if str(org.get("name") or "").casefold() == reconciler.HF_ORG.casefold():
                    role = org.get("roleInOrg") or org.get("role")
                    break
            role_write = str(role or "").lower() in {
                "admin",
                "write",
                "contributor",
            }
            target_write = False
            target_error = None
            try:
                api.auth_check(
                    repo_id=f"{reconciler.HF_ORG}/a11oy",
                    repo_type="space",
                    write=True,
                )
                target_write = True
            except Exception as exc:
                target_error = reconciler.safe_error(exc)
            attempts.append(
                {
                    "alias": alias,
                    "identity": name,
                    "active": True,
                    "org_role": role,
                    "role_write": role_write,
                    "canonical_space_write": target_write,
                    "target_error": target_error,
                }
            )
            if target_write and (role_write or role is None):
                return token, {
                    "state": "ACTIVE_ORG_WRITE_AUTHORITY",
                    "alias": alias,
                    "identity": name,
                    "org_role": role,
                    "authority_basis": (
                        "ORG_ROLE_AND_CANONICAL_SPACE_WRITE"
                        if role_write
                        else "CANONICAL_SPACE_WRITE_FINE_GRAINED"
                    ),
                    "canonical_space_write": True,
                    "attempts": attempts,
                }
        except Exception as exc:
            attempts.append(
                {"alias": alias, "active": False, "error": reconciler.safe_error(exc)}
            )
    return None, {
        "state": "UNAVAILABLE",
        "reason": "No token proved canonical SZLHOLDINGS/a11oy Space write authority",
        "attempts": attempts,
    }


reconciler.select_github_token = select_github_token
reconciler.select_hf_token = select_hf_token
raise SystemExit(reconciler.main())
