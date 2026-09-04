#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Authority-hardened runner for reconcile_agent_estate.py."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any, Mapping

MODULE_PATH = Path(__file__).with_name("reconcile_agent_estate.py")
spec = importlib.util.spec_from_file_location("szl_reconcile_agent_estate", MODULE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("unable to load estate reconciler")
reconciler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconciler)


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
    for alias in aliases:
        token = os.getenv(alias, "").strip()
        if not token:
            continue
        print(f"::add-mask::{token}")
        api = reconciler.GitHubApi(token)
        try:
            user = api.get("/user")
            login = str(user.get("login") or "")
            membership = api.get(f"/user/memberships/orgs/{reconciler.ORG}")
            central = api.get(f"/repos/{reconciler.ORG}/{reconciler.CENTRAL_REPO}")
            permissions = central.get("permissions") or {}
            active_membership = (
                str(membership.get("state") or "").lower() == "active"
                and str(membership.get("role") or "").lower() in {"admin", "member"}
            )
            central_write = bool(
                permissions.get("push")
                or permissions.get("maintain")
                or permissions.get("admin")
            )
            attempts.append(
                {
                    "alias": alias,
                    "identity": login,
                    "active": True,
                    "org_membership": membership.get("state"),
                    "org_role": membership.get("role"),
                    "central_write": central_write,
                    "admin": bool(permissions.get("admin")),
                }
            )
            if active_membership and central_write:
                return api, {
                    "state": "ACTIVE_WRITE_AUTHORITY",
                    "alias": alias,
                    "identity": login,
                    "org_membership": membership.get("state"),
                    "org_role": membership.get("role"),
                    "admin": bool(permissions.get("admin")),
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
        "reason": "No token proved active organization membership plus repository write authority",
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
            if role_write:
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
            if role_write and target_write:
                return token, {
                    "state": "ACTIVE_ORG_WRITE_AUTHORITY",
                    "alias": alias,
                    "identity": name,
                    "org_role": role,
                    "canonical_space_write": True,
                    "attempts": attempts,
                }
        except Exception as exc:
            attempts.append(
                {"alias": alias, "active": False, "error": reconciler.safe_error(exc)}
            )
    return None, {
        "state": "UNAVAILABLE",
        "reason": "No token proved active SZLHOLDINGS role and canonical Space write access",
        "attempts": attempts,
    }


reconciler.select_github_token = select_github_token
reconciler.select_hf_token = select_hf_token
raise SystemExit(reconciler.main())
