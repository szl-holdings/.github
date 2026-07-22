#!/usr/bin/env python3
"""Add a narrow OrganizationAdmin pull-request bypass to active review rulesets.

This utility preserves every existing rule, condition, enforcement level, and bypass
actor. It only adds an ``OrganizationAdmin`` actor with ``pull_request`` mode to
active branch rulesets that currently require one or more approving reviews for
``main`` on the exact repositories in the owner-authorized merge manifest.

The change does not disable status checks, signatures, force-push restrictions,
branch deletion protection, or any other rule.
"""
from __future__ import annotations

import argparse
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
SUFFICIENT_MODES = {"pull_request", "always", "exempt"}


class GateError(RuntimeError):
    """Fail-closed ruleset mutation error."""


def request(
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
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
            "User-Agent": "szl-org-admin-pr-bypass/1.0",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
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
        raise GateError("this bypass utility is intentionally limited to main")
    targets = data.get("targets")
    if not isinstance(targets, list) or not targets:
        raise GateError("merge manifest has no targets")
    return data


def required_review_rule(rule: dict[str, Any]) -> bool:
    if rule.get("type") != "pull_request":
        return False
    params = rule.get("parameters") or {}
    try:
        return int(params.get("required_approving_review_count") or 0) > 0
    except (TypeError, ValueError):
        raise GateError(
            f"invalid required_approving_review_count in ruleset {rule.get('ruleset_id')}"
        )


def source_endpoint(rule: dict[str, Any], fallback_repository: str) -> tuple[str, str]:
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


def actor_is_sufficient(actor: dict[str, Any]) -> bool:
    return (
        actor.get("actor_type") == "OrganizationAdmin"
        and actor.get("bypass_mode") in SUFFICIENT_MODES
    )


def stable_ruleset_state(ruleset: dict[str, Any]) -> dict[str, Any]:
    """Fields that must remain byte-semantically unchanged after bypass update."""
    return {
        "name": ruleset.get("name"),
        "target": ruleset.get("target"),
        "enforcement": ruleset.get("enforcement"),
        "conditions": ruleset.get("conditions"),
        "rules": ruleset.get("rules"),
    }


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
        "schema": "szl.organization-admin-pr-bypass-report/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execute": bool(args.execute),
        "organization": "szl-holdings",
        "repositories": [],
        "rulesets": [],
        "errors": [],
        "ok": False,
    }

    discovered: dict[str, dict[str, Any]] = {}
    try:
        for target in manifest["targets"]:
            repository = str(target["repository"])
            owner, repo = repository.split("/", 1)
            rules_path = (
                f"/repos/{urllib.parse.quote(owner, safe='')}/"
                f"{urllib.parse.quote(repo, safe='')}/rules/branches/"
                f"{urllib.parse.quote(branch, safe='')}?per_page=100"
            )
            active_rules = request(token, "GET", rules_path)
            if not isinstance(active_rules, list):
                raise GateError(f"{repository} returned a non-list branch-rule payload")

            review_rules = [rule for rule in active_rules if required_review_rule(rule)]
            if not review_rules:
                raise GateError(
                    f"{repository}@{branch} has no active ruleset review rule to amend; "
                    "refusing a broader or guessed protection change"
                )

            repo_record = {
                "repository": repository,
                "branch": branch,
                "review_rulesets": [],
            }
            for rule in review_rules:
                endpoint, key = source_endpoint(rule, repository)
                repo_record["review_rulesets"].append(
                    {
                        "key": key,
                        "ruleset_id": rule.get("ruleset_id"),
                        "source_type": rule.get("ruleset_source_type"),
                        "source": rule.get("ruleset_source"),
                        "required_approving_review_count": (
                            (rule.get("parameters") or {}).get(
                                "required_approving_review_count"
                            )
                        ),
                    }
                )
                discovered.setdefault(
                    key,
                    {
                        "endpoint": endpoint,
                        "key": key,
                        "repositories": set(),
                    },
                )["repositories"].add(repository)
            report["repositories"].append(repo_record)

        for key in sorted(discovered):
            item = discovered[key]
            endpoint = item["endpoint"]
            before = request(token, "GET", endpoint)
            if before.get("target") != "branch":
                raise GateError(f"{key} target is {before.get('target')!r}, not branch")
            if before.get("enforcement") != "active":
                raise GateError(
                    f"{key} enforcement is {before.get('enforcement')!r}, not active"
                )

            actors = list(before.get("bypass_actors") or [])
            already = any(actor_is_sufficient(actor) for actor in actors)
            action = "unchanged"
            if not already:
                actors.append(
                    {
                        "actor_id": None,
                        "actor_type": "OrganizationAdmin",
                        "bypass_mode": "pull_request",
                    }
                )
                action = "would-add" if not args.execute else "added"
                if args.execute:
                    request(token, "PUT", endpoint, {"bypass_actors": actors})

            after = request(token, "GET", endpoint) if args.execute else before
            if stable_ruleset_state(after) != stable_ruleset_state(before):
                raise GateError(f"{key} changed outside bypass_actors; refusing")
            if args.execute and not any(
                actor_is_sufficient(actor)
                for actor in list(after.get("bypass_actors") or [])
            ):
                raise GateError(f"{key} did not retain an OrganizationAdmin bypass")

            report["rulesets"].append(
                {
                    "key": key,
                    "name": before.get("name"),
                    "source_type": before.get("source_type"),
                    "source": before.get("source"),
                    "ruleset_id": before.get("id"),
                    "repositories": sorted(item["repositories"]),
                    "action": action,
                    "bypass_actors_before": before.get("bypass_actors") or [],
                    "bypass_actors_after": (
                        after.get("bypass_actors") or []
                        if args.execute
                        else actors
                    ),
                    "preserved": stable_ruleset_state(before),
                }
            )

        report["ok"] = True
        return_code = 0
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        return_code = 1
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
