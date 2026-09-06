#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Manifest-bound archived-repository restoration controller.

This controller can only change ``archived`` from true to false for repositories
whose manifest disposition is ``restore``. It never archives a repository,
changes visibility, deletes history, rewrites a ref, changes a default branch,
or mutates Hugging Face. Consolidated and historical repositories remain
read-only tombstones until their reusable source has been migrated through a
separate reviewed pull request.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "szl.archive-portfolio/v1"
API = "https://api.github.com"
ALLOWED_DISPOSITIONS = frozenset({"restore", "consolidate", "historical"})


class PortfolioError(RuntimeError):
    """Fail-closed portfolio validation or provider error."""


@dataclass(frozen=True)
class RepoState:
    name: str
    archived: bool
    private: bool
    disabled: bool
    fork: bool
    default_branch: str | None

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "RepoState":
        return cls(
            name=str(value.get("name") or ""),
            archived=bool(value.get("archived")),
            private=bool(value.get("private")),
            disabled=bool(value.get("disabled")),
            fork=bool(value.get("fork")),
            default_branch=(
                str(value.get("default_branch"))
                if value.get("default_branch")
                else None
            ),
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PortfolioError(f"manifest unreadable: {exc}") from exc
    validate_manifest(value)
    return value


def validate_manifest(value: Mapping[str, Any]) -> None:
    if value.get("schema") != SCHEMA:
        raise PortfolioError(f"unsupported schema: {value.get('schema')!r}")
    organization = value.get("organization")
    if not isinstance(organization, str) or not organization:
        raise PortfolioError("organization must be a non-empty string")
    rows = value.get("repositories")
    if not isinstance(rows, list) or not rows:
        raise PortfolioError("repositories must be a non-empty list")

    names: set[str] = set()
    restore_names: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise PortfolioError(f"repositories[{index}] must be an object")
        name = row.get("name")
        if (
            not isinstance(name, str)
            or not name
            or "/" in name
            or name in {".", ".."}
        ):
            raise PortfolioError(f"invalid repository name at row {index}")
        if name in names:
            raise PortfolioError(f"duplicate repository: {name}")
        names.add(name)

        disposition = row.get("disposition")
        if disposition not in ALLOWED_DISPOSITIONS:
            raise PortfolioError(
                f"{name}: invalid disposition {disposition!r}"
            )
        targets = row.get("canonical_targets")
        if not isinstance(targets, list) or any(
            not isinstance(item, str) or not item or "/" in item
            for item in targets
        ):
            raise PortfolioError(f"{name}: canonical_targets must be repo names")
        if disposition == "restore":
            if targets:
                raise PortfolioError(
                    f"{name}: restore rows cannot delegate canonical authority"
                )
            restore_names.add(name)
        elif disposition == "consolidate" and not targets:
            raise PortfolioError(
                f"{name}: consolidate rows require canonical_targets"
            )
        elif disposition == "historical" and targets:
            raise PortfolioError(
                f"{name}: historical rows cannot declare an active authority"
            )

        for field in (
            "rationale",
            "hugging_face_showcase",
            "backend_frontend_upgrade",
        ):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise PortfolioError(f"{name}: missing {field}")

    restoration = value.get("restoration_wave")
    if not isinstance(restoration, dict):
        raise PortfolioError("restoration_wave must be an object")
    declared = restoration.get("repositories")
    if not isinstance(declared, list):
        raise PortfolioError(
            "restoration_wave.repositories must be a list"
        )
    if declared != sorted(restore_names):
        raise PortfolioError(
            "restoration_wave.repositories does not match restore rows"
        )
    if restoration.get("count") != len(restore_names):
        raise PortfolioError("restoration_wave.count is inconsistent")

    source = value.get("source_inventory")
    if not isinstance(source, dict):
        raise PortfolioError("source_inventory must be an object")
    if source.get("archived_public_repositories_observed") != len(rows):
        raise PortfolioError(
            "source inventory count must equal classified repository rows"
        )
    if source.get("fail_closed_on_unclassified_archived") is not True:
        raise PortfolioError(
            "manifest must fail closed on unclassified archived repositories"
        )


def build_plan(
    manifest: Mapping[str, Any],
    repositories: list[RepoState],
) -> dict[str, Any]:
    by_name = {repo.name: repo for repo in repositories}
    rows = {
        str(row["name"]): row
        for row in manifest["repositories"]
    }
    missing = sorted(set(rows) - set(by_name))
    if missing:
        raise PortfolioError(
            "manifest repositories absent from organization: "
            + ", ".join(missing)
        )

    public_archived = {
        repo.name
        for repo in repositories
        if repo.archived and not repo.private
    }
    unclassified = sorted(public_archived - set(rows))
    if unclassified:
        raise PortfolioError(
            "unclassified public archived repositories: "
            + ", ".join(unclassified)
        )

    restore: list[str] = []
    already_restored: list[str] = []
    retained: list[str] = []
    unexpected_active: list[str] = []
    invalid_restore: list[str] = []
    target_defects: list[str] = []
    restore_set = {
        item["name"]
        for item in manifest["repositories"]
        if item["disposition"] == "restore"
    }

    for name, row in sorted(rows.items()):
        state = by_name[name]
        disposition = row["disposition"]
        if disposition == "restore":
            if state.private or state.disabled or state.fork or not state.default_branch:
                invalid_restore.append(name)
            elif state.archived:
                restore.append(name)
            else:
                already_restored.append(name)
        elif state.archived:
            retained.append(name)
        else:
            unexpected_active.append(name)

        for target in row["canonical_targets"]:
            target_state = by_name.get(target)
            if target_state is None:
                target_defects.append(f"{name}->{target}:missing")
            elif target_state.archived and target not in restore_set:
                target_defects.append(f"{name}->{target}:archived")

    if invalid_restore:
        raise PortfolioError(
            "restore rows are not eligible active-source repositories: "
            + ", ".join(invalid_restore)
        )
    if unexpected_active:
        raise PortfolioError(
            "consolidated/historical tombstones unexpectedly active: "
            + ", ".join(unexpected_active)
        )
    if target_defects:
        raise PortfolioError(
            "canonical target defects: " + ", ".join(target_defects)
        )

    return {
        "schema": "szl.archive-portfolio-plan/v1",
        "organization": manifest["organization"],
        "classified_count": len(rows),
        "public_archived_count": len(public_archived),
        "restore": restore,
        "already_restored": already_restored,
        "retain_archived": retained,
        "unclassified_archived": unclassified,
        "unexpected_active_tombstones": unexpected_active,
        "generated_at": utc_now(),
    }


class GitHubClient:
    def __init__(self, token: str, *, attempts: int = 4) -> None:
        self.token = token
        self.attempts = max(1, attempts)

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        body = (
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
            if payload is not None
            else None
        )
        request = urllib.request.Request(
            f"{API}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "szl-archive-portfolio-governor-v1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        for attempt in range(1, self.attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    raw = response.read()
                    if response.status not in expected:
                        raise PortfolioError(
                            f"{method} {path} returned {response.status}"
                        )
                    return (
                        json.loads(raw.decode("utf-8"))
                        if raw
                        else None
                    )
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:1000]
                if (
                    exc.code in {429, 500, 502, 503, 504}
                    and attempt < self.attempts
                ):
                    time.sleep(min(2**attempt, 12))
                    continue
                raise PortfolioError(
                    f"GitHub {method} {path} failed with {exc.code}: {detail}"
                ) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < self.attempts:
                    time.sleep(min(2**attempt, 12))
                    continue
                raise PortfolioError(
                    f"GitHub {method} {path} transport failure: {exc}"
                ) from exc
        raise AssertionError("unreachable")

    def repositories(self, organization: str) -> list[RepoState]:
        output: list[RepoState] = []
        for page in range(1, 20):
            query = urllib.parse.urlencode(
                {
                    "type": "all",
                    "sort": "full_name",
                    "per_page": 100,
                    "page": page,
                }
            )
            values = self.request(
                "GET",
                f"/orgs/{urllib.parse.quote(organization, safe='')}/repos?{query}",
            )
            if not isinstance(values, list):
                raise PortfolioError("GitHub repository response is not a list")
            output.extend(RepoState.from_api(item) for item in values)
            if len(values) < 100:
                return output
        raise PortfolioError("repository pagination exceeded safety bound")

    def unarchive(self, organization: str, name: str) -> RepoState:
        value = self.request(
            "PATCH",
            f"/repos/{urllib.parse.quote(organization, safe='')}/"
            f"{urllib.parse.quote(name, safe='')}",
            {"archived": False},
            expected=(200,),
        )
        state = RepoState.from_api(value)
        if state.archived:
            raise PortfolioError(f"{name}: provider readback remains archived")
        return state


def execute(
    manifest: Mapping[str, Any],
    client: GitHubClient,
    *,
    apply: bool,
) -> dict[str, Any]:
    before = client.repositories(str(manifest["organization"]))
    plan = build_plan(manifest, before)
    actions: list[dict[str, Any]] = []

    for name in plan["restore"]:
        if not apply:
            actions.append({"repository": name, "status": "PLANNED"})
            continue
        state = client.unarchive(str(manifest["organization"]), name)
        actions.append(
            {
                "repository": name,
                "status": "UNARCHIVED_READBACK_VERIFIED",
                "default_branch": state.default_branch,
            }
        )

    after = (
        client.repositories(str(manifest["organization"]))
        if apply
        else before
    )
    final_plan = build_plan(manifest, after)
    failures = [
        action
        for action in actions
        if action["status"] not in {
            "PLANNED",
            "UNARCHIVED_READBACK_VERIFIED",
        }
    ]
    if apply and final_plan["restore"]:
        failures.append(
            {
                "status": "RESTORE_REMAINED_ARCHIVED",
                "repositories": final_plan["restore"],
            }
        )

    return {
        "schema": "szl.archive-portfolio-execution/v1",
        "organization": manifest["organization"],
        "mode": "apply" if apply else "audit",
        "started_from": plan,
        "actions": actions,
        "final": final_plan,
        "failures": failures,
        "provider_mutations": apply,
        "archive_mutations": False,
        "visibility_mutations": False,
        "history_deletions": False,
        "secrets_recorded": False,
        "completed_at": utc_now(),
        "status": "PASS" if not failures else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("governance/archive-portfolio-v1.json"),
    )
    parser.add_argument(
        "--mode",
        choices=("validate", "audit", "apply"),
        default="validate",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("/tmp/archive-portfolio-v1.json"),
    )
    args = parser.parse_args()

    try:
        manifest = load_manifest(args.manifest)
        if args.mode == "validate":
            report = {
                "schema": "szl.archive-portfolio-validation/v1",
                "status": "PASS",
                "classified_count": len(manifest["repositories"]),
                "restore_count": manifest["restoration_wave"]["count"],
                "validated_at": utc_now(),
            }
        else:
            token = os.environ.get("SZL_REPO_ADMIN_TOKEN", "")
            if not token:
                raise PortfolioError(
                    "SZL_REPO_ADMIN_TOKEN is unavailable; repository "
                    "administration mutation is blocked"
                )
            report = execute(
                manifest,
                GitHubClient(token),
                apply=args.mode == "apply",
            )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report.get("status") == "PASS" else 1
    except PortfolioError as exc:
        report = {
            "schema": "szl.archive-portfolio-execution/v1",
            "status": "BLOCKED",
            "error": str(exc),
            "secrets_recorded": False,
            "completed_at": utc_now(),
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
