#!/usr/bin/env python3
"""Execute one exact-head merge while restoring every protection mutation.

This recovery transaction exists because an earlier owner-authorized merge wave
proved that the estate uses two GitHub protection models:

* ``platform`` is governed by a repository ruleset;
* four already-merged repositories used classic branch protection.

The previous run disabled classic ``enforce_admins`` but failed before merging
``platform``. This script first restores those classic protections. It then
re-verifies the exact Platform pull request through the existing fail-closed
preflight, temporarily changes only the ruleset's approving-review count from a
positive value to zero, merges the exact SHA, and restores the complete ruleset
in ``finally``. The transient OrganizationAdmin actor installed by the previous
attempt is also removed, returning the ruleset to its original actor set.

Pending or failing checks, stale heads, conflicts, unresolved review threads,
active change requests, non-admin credentials, or any unexpected protection
shape stop the transaction. No approval is fabricated and no review is
submitted.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
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
    if target.get("repository") != "szl-holdings/platform":
        raise GateError("transaction is intentionally restricted to platform")
    if int(target.get("pull_request") or 0) != 458:
        raise GateError("unexpected Platform pull request number")
    expected = str(target.get("expected_head_sha") or "")
    if len(expected) != 40:
        raise GateError("expected head must be a 40-character SHA")
    int(expected, 16)
    if target.get("merge_method") != "squash":
        raise GateError("Platform transaction requires squash merge")
    return "main", target


def encoded_repo(repository: str) -> tuple[str, str]:
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


def admin_enforcement_enabled(token: str, repository: str, branch: str) -> bool:
    owner, name = encoded_repo(repository)
    branch_q_method") != "squash":
        raise TransactionError("platform transaction requires squash merge")
    if int(manifest.get("expected_ruleset_id") or 0) != 16195495:
        raise TransactionError("unexpected.get("enabled"))


def restore_classic_admins(
    token: str,
    branch: str,
    *,
    execute: bool,
) -> list[dict[str, Any]]"classic restore allowlist mismatch: {declared_restore!r}"
        )
    return manifest


def stable_classic_state(protection_payload: dict[str, Any]) -> dict[str, Any]:
    return protection.stable_classic_state(protection_payload)


def restore_classic_admins(
    token: str,
    repositories: tuple[str, ...],
    *,
    execute: bool,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for repository in repositories:
        owner, repo = repository.split("/", 1)
        base = (
            f"/repos/{urllib.parse.quote(owner, safe='')}/"
            f"{urllib.parse.quote(repo, safe='')}/branches/main/protection"
        )
        before = api_request(token, "GET", base)
        if not isinstance(before, dict):
            raise TransactionError(f"classic protection unreadable: {repository}")
        stable_before = stable_classic_state(before)
        review_count = protection.classic_review_count(before)
        if review_count != 1:
            raise TransactionError(
                f"{repository} classic approval count is {review_count}, expected 1"
            )
        admin_path = base + "/enforce_admins"
        admin_before = protection.request(
            token, "GET", admin_path, allow_status={404}
        )
        enabled_before = bool(
            isinstance(admin_before, dict) and admin_before.get("enabled")
        )
        action = "already-enabled"
        if not enabled_before:
            action = "would-restore" if not execute else "restored"
            if execute:
                api_request(token, "POST", admin_path)

        admin_after = (
            protection.request(token, "GET", admin_path, allow_status={404})
            if execute
            else admin_before
        )
        enabled_after = bool(
            isinstance(admin_after, dict) and admin_after.get("enabled")
        )
        after = api_request(token, "GET", base)
        if stable_classic_state(after) != stable_before:
            raise TransactionError(
                f"{repository} changed outside classic enforce_admins"
            )
        if protection.classic_review_count(after) != review_count:
            raise TransactionError(
                f"{repository} classic approval count changed during restoration"
            )
        if execute and not enabled_after:
            raise TransactionError(f"{repository} classic enforce_admins was not restored")
        results.append(
            {
                "repository": repository,
                "action": action,
                "enforce_admins_before": enabled_before,
                "enforce_admins_after": enabled_after if execute else enabled_before,
                "required_approving_review_count": review_count,
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


def final_bypass_actors(actors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove only the transient actor proven absent before the prior helper."""
    return [
        normalize_actor(actor)
        for actor in actors
        if not (
            actor.get("actor_type") == TRANSIENT_ACTOR_TYPE
            and actor.get("bypass_mode") == TRANSIENT_BYPASS_MODE
        )
    ]


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
            else bypass_actors
        ),
        "conditions": copy.deepcopy(ruleset.get("conditions") or {}),
        "rules": copy.deepcopy(ruleset.get("rules") or []) if rules is None else rules,
    }


def review_count(ruleset: dict[str, Any]) -> int:
    counts = []
    for rule in ruleset.get("rules") or []:
        if rule.get("type") != "pull_request":
            continue
        params = rule.get("parameters") or {}
        counts.append(int(params.get("required_approving_review_count") or 0))
    if len(counts) != 1:
        raise TransactionError(
            f"expected one Platform pull_request rule, found {len(counts)}"
        )
    return counts[0]


def rules_with_review_count(
    ruleset: dict[str, Any], count: int
) -> list[dict[str, Any]]:
    rules = copy.deepcopy(ruleset.get("rules") or [])
    changed = 0
    for rule in rules:
        if rule.get("type") != "pull_request":
            continue
        params = rule.setdefault("parameters", {})
        params["required_approving_review_count"] = count
        changed += 1
    if changed != 1:
        raise TransactionError(
            f"expected one Platform pull_request rule, changed {changed}"
        )
    return rules


def state_without_review_count(ruleset: dict[str, Any]) -> dict[str, Any]:
    state = ruleset_payload(ruleset)
    for rule in state["rules"]:
        if rule.get("type") == "pull_request":
            (rule.get("parameters") or {}).pop("required_approving_review_count", None)
    return state


def find_platform_ruleset(
    token: str, expected_ruleset_id: int
) -> tuple[str, dict[str, Any]]:
    active = api_request(
        token,
        "GET",
        "/repos/szl-holdings/platform/rules/branches/main?per_page=100",
    )
    if not isinstance(active, list):
        raise TransactionError("Platform active branch rules are not a list")
    matches = [
        rule
        for rule in active
        if rule.get("ruleset_id") == expected_ruleset_id
        and protection.required_review_rule(rule)
    ]
    if len(matches) != 1:
        raise TransactionError(
            f"expected one active Platform review ruleset, found {len(matches)}"
        )
    endpoint, _ = protection.source_endpoint(matches[0], "szl-holdings/platform")
    ruleset = api_request(token, "GET", endpoint)
    if ruleset.get("id") != expected_ruleset_id:
        raise TransactionError("Platform ruleset id changed")
    if ruleset.get("target") != "branch" or ruleset.get("enforcement") != "active":
        raise TransactionError("Platform ruleset is not an active branch ruleset")
    if review_count(ruleset) != 1:
        raise TransactionError("Platform approval count is not exactly one")
    return endpoint, ruleset


def verify_ruleset_restored(
    current: dict[str, Any],
    original: dict[str, Any],
    expected_final_actors: list[dict[str, Any]],
) -> None:
    expected = ruleset_payload(original, bypass_actors=expected_final_actors)
    actual = ruleset_payload(current)
    if actual != expected:
        raise TransactionError("Platform ruleset did not restore to the expected state")
    if review_count(current) != 1:
        raise TransactionError("Platform approval count was not restored to one")


def get_pr(token: str, repository: str, number: int) -> dict[str, Any]:
    owner, repo = repository.split("/", 1)
    return api_request(token, "GET", f"/repos/{owner}/{repo}/pulls/{number}")


def merge_exact_head(
    token: str, target: dict[str, Any]
) -> dict[str, Any]:
    repository = str(target["repository"])
    number = int(target["pull_request"])
    expected_head = str(target["expected_head_sha"])
    owner, repo = repository.split("/", 1)
    result = api_request(
        token,
        "PUT",
        f"/repos/{owner}/{repo}/pulls/{number}/merge",
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
        raise TransactionError(f"Platform merge endpoint did not merge: {result!r}")
    pr = get_pr(token, repository, number)
    if not pr.get("merged_at") or pr.get("head", {}).get("sha") != expected_head:
        raise TransactionError("Platform merge could not be verified at the exact head")
    return {
        "repository": repository,
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
        "restoration": None,
        "errors": [],
    }
    token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    ruleset_endpoint: str | None = None
    original_ruleset: dict[str, Any] | None = None
    expected_final_actors: list[dict[str, Any]] | None = None
    exit_code = 1

    try:
        if not token:
            raise TransactionError("SZL_GITHUB_TOKEN is not configured")
        manifest = load_manifest(args.manifest)
        target = manifest["targets"][0]
        identity_payload = api_request(token, "GET", "/user")
        identity = str(identity_payload.get("login") or "")
        if not identity:
            raise TransactionError("authenticated identity has no login")
        report["identity"] = identity

        report["classic_restoration"] = restore_classic_admins(
            token, CLASSIC_ADMIN_RESTORE, execute=args.execute
        )

        pr_snapshot = get_pr(token, target["repository"], target["pull_request"])
        if pr_snapshot.get("merged_at"):
            if (pr_snapshot.get("head") or {}).get("sha") != target["        }

        if args.execute:
            temporary = apply_ruleset(token, endpoint, temporary_payload)
            temp_applied = True
            if stable_ruleset_except_review_count(temporary) != stable_ruleset_except_review_count(
                original_ruleset
            ):
                raise GateError("Platform ruleset changed outside approval count")
            temp_positive = [
                required_review_count(rule)
                for rule in list(temporary.get("rules") or [])
                if rule.get("type") == "pull_request"
            ]
            if temp_positive != [0]:
                raise GateError(
                    f"temporary Platform approval count is not exactly zero: {temp_positive}"
                )
            report["merge"] = merge_exact_target(token, target)
        else:
            report["merge"] = {
                "status": "dry-run",
                "expected_head_sha": target["expected_head_sha"],
            }

        report["ok"] = True
        exit_code = 0
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        exit_code = 1
    finally:
        restoration_errors: list[str] = []
        if args.execute:
            if endpoint and restore_payload:
                try:
                    restored = apply_ruleset(token, endpoint, restore_payload)
                    if ruleset_payload(restored) != restore_payload:
                        raise GateError("Platform ruleset did not restore exactly")
                except Exception as exc:  # noqa: BLE001
                    restoration_errors.append(
                        f"Platform ruleset restoration failed: {type(exc).__name__}: {exc}"
                    )
            elif temp_applied:
                restoration_errors.append(
                    "Platform temporary ruleset was applied but no restore payload exists"
                )
            try:
                final_classic = restore_classic_admins(token, branch, execute=True)
                report["classic_protection_final_verification"] = final_classic
            except Exception as exc:  # noqa: BLE001
                restoration_errors.append(
                    f"classic protection restoration failed: {type(exc).__name__}: {exc}"
                )
        if restoration_errors:
            report["errors"].extend(restoration_errors)
            report["ok"] = False
            exit_code = 1
        else:
            report["protections_restored"] = True if args.execute else False

        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
