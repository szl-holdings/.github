#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Restore only the four source owners admitted by archive-portfolio-v2.json."""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

API = "https://api.github.com"
SCHEMA = "szl.archive-portfolio/v2"
DISPOSITIONS = {"restore", "consolidate", "historical"}
EXACT_RESTORES = {"szl-atelier", "szl-mesh", "szl-router", "uds-bundles"}
TOKEN_RE = re.compile(r"(?:github_pat_|gh[pousr]_|hf_)[A-Za-z0-9_]{12,}")
MAX_BYTES = 1_000_000


class PortfolioError(RuntimeError):
    pass


@dataclass(frozen=True)
class RepoState:
    name: str
    archived: bool
    private: bool
    disabled: bool
    fork: bool
    default_branch: str | None
    admin: bool

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "RepoState":
        permissions = value.get("permissions")
        return cls(
            name=str(value.get("name") or ""),
            archived=bool(value.get("archived")),
            private=bool(value.get("private")),
            disabled=bool(value.get("disabled")),
            fork=bool(value.get("fork")),
            default_branch=str(value["default_branch"]) if value.get("default_branch") else None,
            admin=bool(permissions.get("admin")) if isinstance(permissions, dict) else False,
        )


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe(value: Any) -> str:
    return TOKEN_RE.sub("[REDACTED]", str(value).replace("\r", " ").replace("\n", " ")[:1000])


def duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise PortfolioError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def reject_nonfinite(value: str) -> None:
    raise PortfolioError(f"non-finite JSON value: {value}")


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=duplicate_guard,
            parse_constant=reject_nonfinite,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PortfolioError(f"manifest unreadable: {safe(exc)}") from exc
    if not isinstance(value, dict):
        raise PortfolioError("manifest root must be an object")
    validate_manifest(value)
    return value


def validate_manifest(value: Mapping[str, Any]) -> None:
    if value.get("schema") != SCHEMA or value.get("organization") != "szl-holdings":
        raise PortfolioError("schema or organization mismatch")
    policy = value.get("policy")
    if not isinstance(policy, dict):
        raise PortfolioError("policy must be an object")
    for key in (
        "github_is_source_authority",
        "hugging_face_is_generated_artifact_registry",
        "one_canonical_writer_per_hugging_face_target",
    ):
        if policy.get(key) is not True:
            raise PortfolioError(f"policy.{key} must be true")

    rows = value.get("repositories")
    if not isinstance(rows, list) or len(rows) != 34:
        raise PortfolioError("repositories must classify exactly 34 entries")
    names: set[str] = set()
    restores: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise PortfolioError(f"row {index} must be an object")
        name = row.get("name")
        if not isinstance(name, str) or not name or "/" in name or name in names:
            raise PortfolioError(f"invalid or duplicate repository at row {index}")
        names.add(name)
        disposition = row.get("disposition")
        targets = row.get("canonical_targets")
        if disposition not in DISPOSITIONS:
            raise PortfolioError(f"{name}: invalid disposition")
        if not isinstance(targets, list) or any(
            not isinstance(target, str) or not target or "/" in target for target in targets
        ):
            raise PortfolioError(f"{name}: invalid canonical targets")
        if len(targets) != len(set(targets)):
            raise PortfolioError(f"{name}: duplicate canonical target")
        if disposition == "restore":
            if targets:
                raise PortfolioError(f"{name}: restore rows cannot delegate authority")
            restores.add(name)
        elif disposition == "consolidate" and not targets:
            raise PortfolioError(f"{name}: consolidation target required")
        elif disposition == "historical" and targets:
            raise PortfolioError(f"{name}: historical rows cannot declare a target")
        for field in ("rationale", "hugging_face_showcase", "backend_frontend_upgrade"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise PortfolioError(f"{name}: missing {field}")
        if not row["hugging_face_showcase"].startswith("SZLHOLDINGS/"):
            raise PortfolioError(f"{name}: showcase must remain inside SZLHOLDINGS")

    source = value.get("source_inventory")
    if not isinstance(source, dict) or source.get("archived_public_repositories_observed") != 34:
        raise PortfolioError("source inventory count mismatch")
    if source.get("fail_closed_on_unclassified_archived") is not True:
        raise PortfolioError("unclassified archives must fail closed")

    wave = value.get("restoration_wave")
    if not isinstance(wave, dict):
        raise PortfolioError("restoration_wave must be an object")
    if wave.get("repositories") != sorted(restores) or wave.get("count") != len(restores):
        raise PortfolioError("restoration wave mismatch")
    if wave.get("maximum_restore_count") != 4 or len(restores) > 4:
        raise PortfolioError("restoration wave exceeds bounded maximum")
    if restores != EXACT_RESTORES:
        raise PortfolioError("restore set must be exactly " + ", ".join(sorted(EXACT_RESTORES)))
    if wave.get("automatic_on_protected_main") is not True:
        raise PortfolioError("protected-main execution must be explicit")

    boundary = value.get("mutation_boundary")
    if not isinstance(boundary, dict) or boundary.get("allowed") != [
        "archived:true->false for restoration_wave repositories"
    ]:
        raise PortfolioError("only exact unarchives may be authorized")


def build_plan(manifest: Mapping[str, Any], repositories: list[RepoState]) -> dict[str, Any]:
    by_name = {repo.name: repo for repo in repositories}
    rows = {row["name"]: row for row in manifest["repositories"]}
    missing = sorted(set(rows) - set(by_name))
    if missing:
        raise PortfolioError("manifest repositories missing: " + ", ".join(missing))

    public_archived = {
        repo.name for repo in repositories if repo.archived and not repo.private
    }
    unclassified = sorted(public_archived - set(rows))
    if unclassified:
        raise PortfolioError("unclassified public archived repositories: " + ", ".join(unclassified))

    restore: list[str] = []
    already: list[str] = []
    retained: list[str] = []
    active_tombstones: list[str] = []
    target_defects: list[str] = []
    for name, row in sorted(rows.items()):
        state = by_name[name]
        if state.private:
            raise PortfolioError(f"{name}: classified public source became private")
        if row["disposition"] == "restore":
            if state.disabled or state.fork or state.default_branch != "main":
                raise PortfolioError(f"{name}: restore preconditions invalid")
            (restore if state.archived else already).append(name)
        elif state.archived:
            retained.append(name)
        else:
            active_tombstones.append(name)
        for target in row["canonical_targets"]:
            candidate = by_name.get(target)
            if candidate is None:
                target_defects.append(f"{name}->{target}:missing")
            elif candidate.private:
                target_defects.append(f"{name}->{target}:private")
            elif candidate.archived:
                target_defects.append(f"{name}->{target}:archived")
            elif candidate.disabled:
                target_defects.append(f"{name}->{target}:disabled")
    if active_tombstones:
        raise PortfolioError("consolidated or historical repositories unexpectedly active: " + ", ".join(active_tombstones))
    if target_defects:
        raise PortfolioError("canonical target defects: " + ", ".join(target_defects))
    return {
        "schema": "szl.archive-portfolio-plan/v2",
        "organization": manifest["organization"],
        "classified_count": len(rows),
        "current_public_archived_count": len(public_archived),
        "restore": restore,
        "already_restored": already,
        "retain_archived": retained,
        "unclassified_archived": unclassified,
        "unexpected_active_tombstones": active_tombstones,
        "generated_at": now(),
    }


class GitHubClient:
    def __init__(self, token: str):
        if not token:
            raise PortfolioError("repository-administration credential unavailable")
        self.token = token

    def request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> Any:
        data = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode() if payload is not None else None
        request = urllib.request.Request(
            API + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "szl-archive-portfolio-governor-v2",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    raw = response.read(MAX_BYTES + 1)
                    if len(raw) > MAX_BYTES:
                        raise PortfolioError(f"{method} {path}: response too large")
                    return json.loads(raw.decode()) if raw else None
            except urllib.error.HTTPError as exc:
                detail = safe(exc.read(MAX_BYTES + 1).decode("utf-8", "replace"))
                if exc.code in {408, 425, 429, 500, 502, 503, 504} and attempt < 3:
                    time.sleep(min(2 ** (attempt + 1), 12))
                    continue
                raise PortfolioError(f"GitHub {method} {path} failed with {exc.code}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                if attempt < 3:
                    time.sleep(min(2 ** (attempt + 1), 12))
                    continue
                raise PortfolioError(f"GitHub {method} {path} transport failure: {safe(exc)}") from exc
        raise AssertionError("unreachable")

    def repositories(self, organization: str) -> list[RepoState]:
        output: list[RepoState] = []
        for page in range(1, 10):
            query = urllib.parse.urlencode({"type": "all", "sort": "full_name", "per_page": 100, "page": page})
            values = self.request("GET", f"/orgs/{organization}/repos?{query}")
            if not isinstance(values, list):
                raise PortfolioError("repository inventory is not an array")
            output.extend(RepoState.from_api(item) for item in values)
            if len(values) < 100:
                return output
        raise PortfolioError("repository pagination exceeded safety bound")

    def repository(self, organization: str, name: str) -> RepoState:
        value = self.request("GET", f"/repos/{organization}/{name}")
        if not isinstance(value, dict):
            raise PortfolioError(f"{name}: repository response is not an object")
        return RepoState.from_api(value)

    def require_admin(self, organization: str, names: list[str]) -> None:
        defects = [name for name in names if not self.repository(organization, name).admin]
        if defects:
            raise PortfolioError("credential lacks repository administration for: " + ", ".join(defects))

    def unarchive(self, organization: str, name: str) -> RepoState:
        before = self.repository(organization, name)
        if not before.archived:
            return before
        if before.private or before.disabled or before.fork or before.default_branch != "main":
            raise PortfolioError(f"{name}: precondition changed before unarchive")
        response = self.request("PATCH", f"/repos/{organization}/{name}", {"archived": False})
        immediate = RepoState.from_api(response if isinstance(response, dict) else {})
        after = self.repository(organization, name)
        for observed in (immediate, after):
            if observed.archived:
                raise PortfolioError(f"{name}: provider readback remains archived")
            if (
                observed.private != before.private
                or observed.disabled != before.disabled
                or observed.fork != before.fork
                or observed.default_branch != before.default_branch
            ):
                raise PortfolioError(f"{name}: non-archive state drifted")
        return after


def execute(manifest: Mapping[str, Any], client: GitHubClient, apply: bool) -> dict[str, Any]:
    organization = str(manifest["organization"])
    plan = build_plan(manifest, client.repositories(organization))
    actions: list[dict[str, Any]] = []
    if apply and plan["restore"]:
        client.require_admin(organization, plan["restore"])
    for name in plan["restore"]:
        if not apply:
            actions.append({"repository": name, "status": "PLANNED"})
            continue
        try:
            state = client.unarchive(organization, name)
            actions.append({"repository": name, "status": "UNARCHIVED_READBACK_VERIFIED", "default_branch": state.default_branch})
        except PortfolioError as exc:
            actions.append({"repository": name, "status": "BLOCKED", "error": safe(exc)})
    final = build_plan(manifest, client.repositories(organization))
    failures = [row for row in actions if row["status"] == "BLOCKED"]
    if apply and final["restore"]:
        failures.append({"status": "RESTORE_REMAINED_ARCHIVED", "repositories": final["restore"]})
    return {
        "schema": "szl.archive-portfolio-execution/v2",
        "organization": organization,
        "mode": "apply" if apply else "audit",
        "source_revision": os.environ.get("GITHUB_SHA") or "UNAVAILABLE",
        "started_from": plan,
        "actions": actions,
        "final": final,
        "failures": failures,
        "unarchive_state_mutations_attempted": bool(apply and plan["restore"]),
        "archive_true_mutations": False,
        "visibility_mutations": False,
        "history_deletions": False,
        "default_branch_mutations": False,
        "protection_or_ruleset_mutations": False,
        "hugging_face_mutations": False,
        "secrets_recorded": False,
        "completed_at": now(),
        "status": "PASS" if not failures else "FAIL",
    }


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if TOKEN_RE.search(text):
        raise PortfolioError("credential-shaped material detected in report")
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("governance/archive-portfolio-v2.json"))
    parser.add_argument("--mode", choices=("validate", "audit", "apply"), default="validate")
    parser.add_argument("--report", type=Path, default=Path("/tmp/archive-portfolio-v2.json"))
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        if args.mode == "validate":
            report: dict[str, Any] = {
                "schema": "szl.archive-portfolio-validation/v2",
                "status": "PASS",
                "classified_count": 34,
                "restore_count": 4,
                "restore_set": sorted(EXACT_RESTORES),
                "secrets_recorded": False,
                "validated_at": now(),
            }
        else:
            report = execute(
                manifest,
                GitHubClient(os.environ.get("SZL_REPO_ADMIN_TOKEN", "")),
                args.mode == "apply",
            )
        write_report(args.report, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "PASS" else 1
    except PortfolioError as exc:
        report = {
            "schema": "szl.archive-portfolio-execution/v2",
            "status": "BLOCKED",
            "mode": args.mode,
            "error": safe(exc),
            "archive_true_mutations": False,
            "visibility_mutations": False,
            "history_deletions": False,
            "default_branch_mutations": False,
            "protection_or_ruleset_mutations": False,
            "hugging_face_mutations": False,
            "secrets_recorded": False,
            "completed_at": now(),
        }
        try:
            write_report(args.report, report)
        except PortfolioError:
            pass
        print(json.dumps(report, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
