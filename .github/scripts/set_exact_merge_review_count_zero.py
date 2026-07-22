#!/usr/bin/env python3
"""Set required approval count to zero for the exact owner-authorized merge wave.

This is intentionally narrower than disabling branch protection. For each exact
repository in ``owner_authorized_merge_wave.json`` and only for ``main``:

* active rulesets keep every rule and parameter unchanged except
  ``pull_request.required_approving_review_count`` becomes ``0``;
* classic branch protection keeps the pull-request review protection object and
  changes only ``required_approving_review_count`` to ``0``.

Status checks, signed-commit requirements, linear history, force-push and branch
-deletion restrictions, review-thread resolution, code-owner settings, stale-
review behavior, and all other controls are preserved and verified by readback.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API = "https://api.github.com"
API_VERSION = "2022-11-28"


class GateError(RuntimeError):
    """Fail-closed protection mutation error."""


def request(
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
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
            "User-Agent": "szl-zero-review-count/1.0",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if allow_status and exc.code in allow_status:
            return None
        detail = exc.read().decode("utf-8", "replace")[:4000]
        raise GateError(
            f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise GateError(
            f"GitHub API {method} {path} failed: {type(exc).__name__}: {exc}"
        ) from exc
    return json.loads(raw.decode("utf-8")) if raw else None


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != "szl.owner-authorized-merge-wave/v1":
        raise GateError("unexpected merge manifest schema")
    if data.get("base_branch") != "main":
        raise GateError("this utility is intentionally limited to main")
    targets = data.get("targets")
    if not isinstance(targets, list) or not targets:
        raise GateError("merge manifest has no targets")
    return data


def approval_count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError) as exc:
        raise GateError(f"invalid required approval count: {value!r}") from exc


def active_review_rules(active_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for rule in active_rules:
        if rule.get("type") != "pull_request":
            continue
        params = rule.get("parameters") or {}
        if approval_count(params.get("required_approving_review_count")) > 0:
            result.append(rule)
    return result


def ruleset_endpoint(rule: dict[str, Any], fallback_repository: str) -> tuple[str, str]:
    source_type = str(rule.get("ruleset_source_type") or "")
    ruleset_id = rule.get("ruleset_id")
    if not isinstance(ruleset_id, int):
        raise GateError(f"missing integer ruleset_id: {rule!r}")

    if source_type == "Organization":
        source = str(rule.get("ruleset_source") or fallback_repository.split("/", 1)[0])
        org = source.split("/", 1)[0]
        return (
            f"/orgs/{urllib.parse.quote(org, safe='')}/rulesets/{ruleset_id}",
            f"Organization:{org}:{ruleset_id}",
        )
    if source_type == "Repository":
        source = str(rule.get("ruleset_source") or fallback_repository)
        if "/" not in source:
            source = fallback_repository
        owner, repo = source.split("/", 1)
        return (
            f"/repos/{urllib.parse.quote(owner, safe='')}/"
            f"{urllib.parse.quote(repo, safe='')}/rulesets/{ruleset_id}",
            f"Repository:{owner}/{repo}:{ruleset_id}",
        )
    raise GateError(
        f"unsupported ruleset source type {source_type!r} for ruleset {ruleset_id}"
    )


def ruleset_non_rule_state(ruleset: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": ruleset.get("name"),
        "target": ruleset.get("target"),
        "enforcement": ruleset.get("enforcement"),
        "conditions": ruleset.get("conditions"),
        "bypass_actors": ruleset.get("bypass_actors") or [],
    }


def zero_ruleset_review_counts(rules: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    expected = copy.deepcopy(rules)
    changed = 0
    for rule in expected:
        if rule.get("type") != "pull_request":
            continue
        params = rule.setdefault("parameters", {})
        current = approval_count(params.get("required_approving_review_count"))
        if current > 0:
            params["required_approving_review_count"] = 0
            changed += 1
    return expected, changed


def classic_non_review_state(protection: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "required_status_checks",
        "enforce_admins",
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


def classic_review_state_without_count(protection: dict[str, Any]) -> dict[str, Any]:
    review = protection.get("required_pull_request_reviews")
    if not isinstance(review, dict):
        raise GateError("classic pull-request review protection is missing")
    return {
        key: value
        for key, value in review.items()
        if key not in {"required_approving_review_count", "url"}
    }


def classic_count(protection: dict[str, Any]) -> int:
    review = protection.get("required_pull_request_reviews")
    if not isinstance(review, dict):
        return 0
    return approval_count(review.get("required_approving_review_count"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    if not token:
        raise GateError("SZL_GITHUB_TOKEN is not configured")

    manifest = load_manifest(args.manifest)
    branch = manifest["base_branch"]
    report: dict[str, Any] = {
        "schema": "szl.exact-merge-review-count-report/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execute": bool(args.execute),
        "organization": "szl-holdings",
        "repositories": [],
        "rulesets": [],
        "classic_protections": [],
        "errors": [],
        "ok": False,
    }

    discovered: dict[str, dict[str, Any]] = {}
    classic: list[dict[str, Any]] = []
    try:
        for target in manifest["targets"]:
            repository = str(target["repository"])
            owner, repo = repository.split("/", 1)
            encoded_owner = urllib.parse.quote(owner, safe="")
            encoded_repo = urllib.parse.quote(repo, safe="")
            encoded_branch = urllib.parse.quote(branch, safe="")
            rules_path = (
                f"/repos/{encoded_owner}/{encoded_repo}/rules/branches/"
                f"{encoded_branch}?per_page=100"
            )
            active = request(token, "GET", rules_path)
            if not isinstance(active, list):
                raise GateError(f"{repository} returned a non-list branch-rule payload")
            review_rules = active_review_rules(active)
            record: dict[str, Any] = {
                "repository": repository,
                "branch": branch,
                "protection_model": None,
            }
            if review_rules:
                record["protection_model"] = "ruleset"
                record["rulesets"] = []
                for rule in review_rules:
                    endpoint, key = ruleset_endpoint(rule, repository)
                    record["rulesets"].append(key)
                    discovered.setdefault(
                        key,
                        {
                            "endpoint": endpoint,
                            "repositories": set(),
                        },
                    )["repositories"].add(repository)
            else:
                protection_path = (
                    f"/repos/{encoded_owner}/{encoded_repo}/branches/"
                    f"{encoded_branch}/protection"
                )
                protection = request(token, "GET", protection_path, allow_status={404})
                if not isinstance(protection, dict):
                    raise GateError(
                        f"{repository}@{branch} has neither a review ruleset nor "
                        "readable classic branch protection"
                    )
                count = classic_count(protection)
                if count <= 0:
                    raise GateError(
                        f"{repository}@{branch} does not currently require an approval"
                    )
                record["protection_model"] = "classic"
                record["required_approving_review_count_before"] = count
                classic.append(
                    {
                        "repository": repository,
                        "protection_path": protection_path,
                    }
                )
            report["repositories"].append(record)

        for key in sorted(discovered):
            item = discovered[key]
            endpoint = item["endpoint"]
            before = request(token, "GET", endpoint)
            if before.get("target") != "branch" or before.get("enforcement") != "active":
                raise GateError(f"{key} is not an active branch ruleset")
            expected_rules, changed = zero_ruleset_review_counts(before.get("rules") or [])
            if changed <= 0:
                raise GateError(f"{key} exposed no positive review count at update time")
            if args.execute:
                request(token, "PUT", endpoint, {"rules": expected_rules})
                time.sleep(1)
            after = request(token, "GET", endpoint) if args.execute else before
            if ruleset_non_rule_state(after) != ruleset_non_rule_state(before):
                raise GateError(f"{key} changed outside rules")
            if args.execute and after.get("rules") != expected_rules:
                raise GateError(f"{key} rules readback differs from the exact expected mutation")
            report["rulesets"].append(
                {
                    "key": key,
                    "repositories": sorted(item["repositories"]),
                    "action": "set-review-count-zero" if args.execute else "would-set-review-count-zero",
                    "rules_before": before.get("rules") or [],
                    "rules_after": expected_rules,
                    "preserved": ruleset_non_rule_state(before),
                }
            )

        for item in classic:
            repository = item["repository"]
            protection_path = item["protection_path"]
            before = request(token, "GET", protection_path)
            count_before = classic_count(before)
            if count_before <= 0:
                raise GateError(f"{repository} approval count moved before mutation")
            non_review_before = classic_non_review_state(before)
            review_before = classic_review_state_without_count(before)
            review_path = protection_path + "/required_pull_request_reviews"
            if args.execute:
                request(
                    token,
                    "PATCH",
                    review_path,
                    {"required_approving_review_count": 0},
                )
                time.sleep(1)
            after = request(token, "GET", protection_path) if args.execute else before
            if args.execute:
                if classic_count(after) != 0:
                    raise GateError(f"{repository} approval count did not become zero")
                if classic_non_review_state(after) != non_review_before:
                    raise GateError(f"{repository} changed outside review protection")
                if classic_review_state_without_count(after) != review_before:
                    raise GateError(
                        f"{repository} changed review settings beyond the approval count"
                    )
            report["classic_protections"].append(
                {
                    "repository": repository,
                    "branch": branch,
                    "action": "set-review-count-zero" if args.execute else "would-set-review-count-zero",
                    "required_approving_review_count_before": count_before,
                    "required_approving_review_count_after": 0,
                    "preserved_non_review_state": non_review_before,
                    "preserved_review_state": review_before,
                }
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
