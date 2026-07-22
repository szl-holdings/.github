#!/usr/bin/env python3
"""Transactionally restore protections and merge exact Platform PR #458.

An earlier owner-authorized run disabled classic ``enforce_admins`` on four
repositories, then stopped when Platform's repository ruleset still rejected the
merge. This recovery transaction:

1. restores classic admin enforcement on the four exact repositories;
2. re-runs the existing exact-SHA/green-check/thread/change-request preflight;
3. snapshots Platform's complete active ruleset;
4. temporarily changes only required_approving_review_count from 1 to 0;
5. merges exact head 9798feff... with squash;
6. restores the complete Platform ruleset in ``finally`` and removes only the
   transient OrganizationAdmin pull_request actor introduced by the failed run;
7. re-verifies all classic protections.

No review is fabricated or submitted. Any stale head, non-green check, conflict,
unresolved thread, active change request, unexpected ruleset shape, or failed
restoration makes the transaction fail closed.
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

import owner_authorized_merge_wave as wave

API = "https://api.github.com"
API_VERSION = "2022-11-28"
OBSOLETE_CHECKRUN_SELECTION = "                    app { slug }\n"
PLATFORM_REPOSITORY = "szl-holdings/platform"
PLATFORM_PULL_REQUEST = 458
PLATFORM_RULESET_ID = 16195495
CLASSIC_RESTORE_REPOSITORIES = (
    "szl-holdings/szl-energy-attest",
    "szl-holdings/szl-lambda-gate",
    "szl-holdings/szl-lake",
    "szl-holdings/david-leads",
)
TRANSIENT_ACTOR_TYPE = "OrganizationAdmin"
TRANSIENT_BYPASS_MODE = "pull_request"


class GateError(RuntimeError):
    """Fail-closed transaction error."""


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
            "User-Agent": "szl-transactional-owner-merge/1.0",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if allow_status and exc.code in allow_status:
            return None
        detail = exc.read().decode("utf-8", "replace")[:6000]
        raise GateError(
            f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise GateError(
            f"GitHub API {method} {path} failed: {type(exc).__name__}: {exc}"
        ) from exc
    return json.loads(raw.decode("utf-8")) if raw else None


def load_manifest(path: Path) -> tuple[str, dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "szl.owner-authorized-merge-wave/v1":
        raise GateError("unexpected manifest schema")
    if manifest.get("base_branch") != "main":
        raise GateError("transaction is intentionally restricted to main")
    targets = manifest.get("targets")
    if not isinstance(targets, list) or len(targets) != 1:
        raise GateError("transaction requires exactly one target")
    target = targets[0]
    if target.get("repository") != PLATFORM_REPOSITORY:
        raise GateError("transaction is intentionally restricted to Platform")
    if int(target.get("pull_request") or 0) != PLATFORM_PULL_REQUEST:
        raise GateError("unexpected Platform pull request")
    expected = str(target.get("expected_head_sha") or "")
    if len(expected) != 40:
        raise GateError("expected head must be a 40-character SHA")
    int(expected, 16)
    if target.get("merge_method") != "squash":
        raise GateError("Platform transaction requires squash merge")
    return "main", target


def repo_parts(repository: str) -> tuple[str, str]:
    owner, name = repository.split("/", 1)
    return urllib.parse.quote(owner, safe=""), urllib.parse.quote(name, safe="")


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
    return {key: protection.get(key) for key in keys}


def classic_review_count(protection: dict[str, Any]) -> int:
    reviews = protection.get("required_pull_request_reviews")
    if not isinstance(reviews, dict):
        return 0
    return int(reviews.get("required_approving_review_count") or 0)


def restore_classic_admins(
    token: str,
    branch: str,
    *,
    execute: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for repository in CLASSIC_RESTORE_REPOSITORIES:
        owner, name = repo_parts(repository)
        branch_q = urllib.parse.quote(branch, safe="")
        protection_path = f"/repos/{owner}/{name}/branches/{branch_q}/protection"
        before = request(token, "GET", protection_path)
        if not isinstance(before, dict):
            raise GateError(f"classic protection is unreadable: {repository}")
        stable_before = stable_classic_state(before)
        count_before = classic_review_count(before)
        if count_before != 1:
            raise GateError(
                f"{repository} approval count is {count_before}, expected exactly 1"
            )

        admin_path = protection_path + "/enforce_admins"
        admin_before = request(token, "GET", admin_path, allow_status={404})
        enabled_before = bool(
            isinstance(admin_before, dict) and admin_before.get("enabled")
        )
        action = "already-enabled"
        if not enabled_before:
            action = "would-restore" if not execute else "restored"
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
        after = request(token, "GET", protection_path)
        if stable_classic_state(after) != stable_before:
            raise GateError(f"{repository} changed outside classic enforce_admins")
        if classic_review_count(after) != count_before:
            raise GateError(f"{repository} approval count changed during restoration")
        if execute and not enabled_after:
            raise GateError(f"{repository} enforce_admins was not restored")

        results.append(
            {
                "repository": repository,
                "action": action,
                "enforce_admins_before": enabled_before,
                "enforce_admins_after": enabled_after if execute else enabled_before,
                "required_approving_review_count": count_before,
                "preserved": stable_before,
            }
        )
    return results


def normalize_actor(actor: dict[str, Any]) -> dict[str, Any]:
    return {
        "actor_id": actor.get("actor_id"),
        "actor_type": actor.get("actor_type"),
        "bypass_mode": actor.get("bypass_mode"),
    }


def actors_without_transient(actors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    transient = [
        actor
        for actor in actors
        if actor.get("actor_type") == TRANSIENT_ACTOR_TYPE
        and actor.get("bypass_mode") == TRANSIENT_BYPASS_MODE
    ]
    if len(transient) != 1:
        raise GateError(
            "expected exactly one transient OrganizationAdmin pull_request actor, "
            f"found {len(transient)}"
        )
    return [normalize_actor(actor) for actor in actors if actor not in transient]


def ruleset_payload(
    ruleset: dict[str, Any],
    *,
    rules: list[dict[str, Any]] | None = None,
    bypass_actors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "name": ruleset["name"],
        "target": ruleset["target"],
        "enforcement": ruleset["enforcement"],
        "bypass_actors": (
            [normalize_actor(actor) for actor in ruleset.get("bypass_actors") or []]
            if bypass_actors is None
            else copy.deepcopy(bypass_actors)
        ),
        "conditions": copy.deepcopy(ruleset.get("conditions") or {}),
        "rules": (
            copy.deepcopy(ruleset.get("rules") or [])
            if rules is None
            else copy.deepcopy(rules)
        ),
    }


def pull_request_rule_indexes(ruleset: dict[str, Any]) -> list[int]:
    return [
        index
        for index, rule in enumerate(ruleset.get("rules") or [])
        if rule.get("type") == "pull_request"
    ]


def review_count(ruleset: dict[str, Any]) -> int:
    indexes = pull_request_rule_indexes(ruleset)
    if len(indexes) != 1:
        raise GateError(f"expected one Platform pull_request rule, found {len(indexes)}")
    params = ruleset["rules"][indexes[0]].get("parameters") or {}
    return int(params.get("required_approving_review_count") or 0)


def rules_with_review_count(ruleset: dict[str, Any], count: int) -> list[dict[str, Any]]:
    rules = copy.deepcopy(ruleset.get("rules") or [])
    indexes = [
        index for index, rule in enumerate(rules) if rule.get("type") == "pull_request"
    ]
    if len(indexes) != 1:
        raise GateError(f"expected one Platform pull_request rule, found {len(indexes)}")
    rules[indexes[0]].setdefault("parameters", {})[
        "required_approving_review_count"
    ] = count
    return rules


def state_without_review_count(ruleset: dict[str, Any]) -> dict[str, Any]:
    state = ruleset_payload(ruleset)
    indexes = [
        index
        for index, rule in enumerate(state["rules"])
        if rule.get("type") == "pull_request"
    ]
    if len(indexes) != 1:
        raise GateError(f"expected one Platform pull_request rule, found {len(indexes)}")
    state["rules"][indexes[0]].setdefault("parameters", {}).pop(
        "required_approving_review_count", None
    )
    return state


def find_platform_ruleset(token: str) -> tuple[str, dict[str, Any]]:
    active = request(
        token,
        "GET",
        "/repos/szl-holdings/platform/rules/branches/main?per_page=100",
    )
    if not isinstance(active, list):
        raise GateError("Platform active branch rules are not a list")
    matches = [
        rule
        for rule in active
        if rule.get("ruleset_id") == PLATFORM_RULESET_ID
        and rule.get("type") == "pull_request"
        and int(
            (rule.get("parameters") or {}).get("required_approving_review_count")
            or 0
        )
        > 0
    ]
    if len(matches) != 1:
        raise GateError(
            f"expected one active Platform review ruleset, found {len(matches)}"
        )
    endpoint = f"/repos/szl-holdings/platform/rulesets/{PLATFORM_RULESET_ID}"
    ruleset = request(token, "GET", endpoint)
    if ruleset.get("id") != PLATFORM_RULESET_ID:
        raise GateError("Platform ruleset id changed")
    if ruleset.get("target") != "branch":
        raise GateError("Platform ruleset target is not branch")
    if ruleset.get("enforcement") != "active":
        raise GateError("Platform ruleset is not active")
    if review_count(ruleset) != 1:
        raise GateError("Platform approval count is not exactly one")
    return endpoint, ruleset


def put_ruleset(token: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    result = request(token, "PUT", endpoint, payload)
    if not isinstance(result, dict):
        raise GateError("ruleset update returned a non-object payload")
    return result


def patch_preflight_query() -> None:
    if OBSOLETE_CHECKRUN_SELECTION in wave.PR_QUERY:
        wave.PR_QUERY = wave.PR_QUERY.replace(OBSOLETE_CHECKRUN_SELECTION, "")
    if "app { slug }" in wave.PR_QUERY:
        raise GateError("obsolete CheckRun.app selection remains")


def preflight_platform(
    token: str,
    identity: str,
    target: dict[str, Any],
    branch: str,
) -> dict[str, Any]:
    patch_preflight_query()
    verified = wave.preflight_target(token, identity, target, branch)
    if not verified.get("admin_override_required"):
        raise GateError("Platform is not blocked solely by the approval requirement")
    return verified


def get_pr(token: str, number: int) -> dict[str, Any]:
    return request(token, "GET", f"/repos/szl-holdings/platform/pulls/{number}")


def merge_exact_platform(token: str, target: dict[str, Any]) -> dict[str, Any]:
    number = int(target["pull_request"])
    expected_head = str(target["expected_head_sha"])
    result = request(
        token,
        "PUT",
        f"/repos/szl-holdings/platform/pulls/{number}/merge",
        {
            "sha": expected_head,
            "merge_method": "squash",
            "commit_title": "fix(sda): use canonical receipt verifier (#458)",
            "commit_message": (
                "Repair the public SDA verifier against the canonical A11oy "
                "receipt API while preserving fail-closed honesty states.\n\n"
                "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
            ),
        },
    )
    if not result.get("merged"):
        raise GateError(f"Platform merge endpoint did not merge: {result!r}")
    pr = get_pr(token, number)
    if not pr.get("merged_at"):
        raise GateError("Platform merge endpoint returned success but PR is unmerged")
    if (pr.get("head") or {}).get("sha") != expected_head:
        raise GateError("merged Platform PR does not match the expected head")
    return {
        "repository": PLATFORM_REPOSITORY,
        "pull_request": number,
        "expected_head_sha": expected_head,
        "status": "merged",
        "merged_at": pr.get("merged_at"),
        "merge_commit_sha": pr.get("merge_commit_sha"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    report: dict[str, Any] = {
        "schema": "szl.transactional-owner-merge-report/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execute": bool(args.execute),
        "ok": False,
        "identity": None,
        "classic_restoration": [],
        "platform_preflight": None,
        "platform_ruleset": None,
        "merge": None,
        "protection_restoration": None,
        "errors": [],
    }
    token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    branch = "main"
    endpoint: str | None = None
    original_ruleset: dict[str, Any] | None = None
    restore_payload: dict[str, Any] | None = None
    temporary_applied = False
    exit_code = 1

    try:
        if not token:
            raise GateError("SZL_GITHUB_TOKEN is not configured")
        branch, target = load_manifest(args.manifest)
        identity_payload = request(token, "GET", "/user")
        identity = str(identity_payload.get("login") or "")
        if not identity:
            raise GateError("authenticated identity has no login")
        report["identity"] = identity

        report["classic_restoration"] = restore_classic_admins(
            token, branch, execute=args.execute
        )

        permission = request(
            token,
            "GET",
            "/repos/szl-holdings/platform/collaborators/"
            + urllib.parse.quote(identity, safe="")
            + "/permission",
        ).get("permission")
        if permission != "admin":
            raise GateError(
                f"{identity} has Platform permission {permission!r}, not admin"
            )

        pr = get_pr(token, int(target["pull_request"]))
        needs_merge = not bool(pr.get("merged_at"))
        if not needs_merge:
            if (pr.get("head") or {}).get("sha") != target["expected_head_sha"]:
                raise GateError("Platform was merged from an unexpected head")
            report["merge"] = {
                "status": "already-merged",
                "merge_commit_sha": pr.get("merge_commit_sha"),
                "merged_at": pr.get("merged_at"),
                "expected_head_sha": target["expected_head_sha"],
            }
        else:
            report["platform_preflight"] = preflight_platform(
                token, identity, target, branch
            )

        endpoint, original_ruleset = find_platform_ruleset(token)
        current_actors = [
            normalize_actor(actor)
            for actor in original_ruleset.get("bypass_actors") or []
        ]
        final_actors = actors_without_transient(current_actors)
        restore_payload = ruleset_payload(
            original_ruleset, bypass_actors=final_actors
        )
        temporary_payload = ruleset_payload(
            original_ruleset,
            rules=rules_with_review_count(original_ruleset, 0),
        )
        report["platform_ruleset"] = {
            "ruleset_id": PLATFORM_RULESET_ID,
            "review_count_before": 1,
            "review_count_temporary": 0,
            "transient_actor_removed_on_restore": True,
        }

        if args.execute and needs_merge:
            temporary = put_ruleset(token, endpoint, temporary_payload)
            temporary_applied = True
            if state_without_review_count(temporary) != state_without_review_count(
                original_ruleset
            ):
                raise GateError("Platform ruleset changed outside approval count")
            if review_count(temporary) != 0:
                raise GateError("temporary Platform approval count is not zero")
            report["merge"] = merge_exact_platform(token, target)
        elif not args.execute and needs_merge:
            report["merge"] = {
                "status": "dry-run",
                "expected_head_sha": target["expected_head_sha"],
            }

        report["ok"] = True
        exit_code = 0
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        report["ok"] = False
        exit_code = 1
    finally:
        restoration_errors: list[str] = []
        if args.execute:
            if endpoint and restore_payload:
                try:
                    restored = put_ruleset(token, endpoint, restore_payload)
                    if ruleset_payload(restored) != restore_payload:
                        raise GateError("Platform ruleset did not restore exactly")
                    if review_count(restored) != 1:
                        raise GateError(
                            "Platform approval count did not restore to one"
                        )
                    report["protection_restoration"] = {
                        "platform_ruleset": "restored",
                        "classic_enforce_admins": "verifying",
                    }
                except Exception as exc:  # noqa: BLE001
                    restoration_errors.append(
                        "Platform ruleset restoration failed: "
                        f"{type(exc).__name__}: {exc}"
                    )
            elif temporary_applied:
                restoration_errors.append(
                    "temporary Platform ruleset was applied without a restore payload"
                )
            try:
                final_classic = restore_classic_admins(
                    token, branch, execute=True
                )
                report["classic_final_verification"] = final_classic
                if report.get("protection_restoration") is None:
                    report["protection_restoration"] = {}
                report["protection_restoration"][
                    "classic_enforce_admins"
                ] = "restored"
            except Exception as exc:  # noqa: BLE001
                restoration_errors.append(
                    "classic protection restoration failed: "
                    f"{type(exc).__name__}: {exc}"
                )

        if restoration_errors:
            report["errors"].extend(restoration_errors)
            report["ok"] = False
            exit_code = 1

        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
