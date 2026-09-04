#!/usr/bin/env python3
"""Deep, read-only census of the SZL Holdings GitHub organization.

The collector reads repository metadata, community health, workflow inventories,
workflow source, rulesets and default-branch protection. The analyzer maps those
observations to the Living Command Fabric authority manifest and emits bounded
JSON/Markdown evidence. It never mutates a repository.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

API = "https://api.github.com"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)\s*(?:#.*)?$", re.MULTILINE)
CANONICAL_IN_DESCRIPTION = re.compile(r"Canonical:\s*https://github\.com/[^/]+/([^\s/]+)", re.I)


class AuditError(RuntimeError):
    """Bounded collection or contract failure."""


class GitHubClient:
    def __init__(self, token: str, api: str = API) -> None:
        self.token = token
        self.api = api

    def _request(self, path: str) -> tuple[Any, dict[str, str]]:
        request = urllib.request.Request(
            self.api + path,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "szl-org-frontier-audit/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8")), dict(response.headers)
        except urllib.error.HTTPError as exc:
            if exc.code in {403, 404}:
                return None, {"x-audit-http-status": str(exc.code)}
            text = exc.read().decode("utf-8", "replace")[:1000]
            raise AuditError(f"GitHub HTTP {exc.code} for {path}: {text}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AuditError(f"GitHub request failed for {path}: {type(exc).__name__}") from exc

    def get(self, path: str) -> Any:
        value, _ = self._request(path)
        return value

    def paginate(self, path: str) -> list[Any]:
        rows: list[Any] = []
        page = 1
        separator = "&" if "?" in path else "?"
        while True:
            value = self.get(f"{path}{separator}per_page=100&page={page}")
            if value is None:
                return rows
            if not isinstance(value, list):
                raise AuditError(f"Expected list from {path}")
            rows.extend(value)
            if len(value) < 100:
                return rows
            page += 1


def _decode_content(value: Any) -> str:
    if not isinstance(value, dict) or value.get("type") != "file":
        return ""
    encoded = value.get("content")
    if not isinstance(encoded, str):
        return ""
    try:
        return base64.b64decode(encoded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""


def _repo_paths(org: str, name: str) -> str:
    return f"/repos/{urllib.parse.quote(org)}/{urllib.parse.quote(name)}"


def collect_live(client: GitHubClient, org: str, authority: dict[str, Any]) -> dict[str, Any]:
    repos = client.paginate(f"/orgs/{urllib.parse.quote(org)}/repos?type=all&sort=full_name&direction=asc")
    if not repos:
        raise AuditError(f"No repositories returned for {org}")

    max_workflows = int(authority["audit_policy"]["max_workflow_files_per_repository"])
    observed: list[dict[str, Any]] = []
    for repo in repos:
        name = str(repo["name"])
        base = _repo_paths(org, name)
        default_branch = str(repo.get("default_branch") or "main")
        community = client.get(f"{base}/community/profile") or {}
        workflows_payload = client.get(f"{base}/actions/workflows?per_page=100") or {}
        workflow_rows = workflows_payload.get("workflows", []) if isinstance(workflows_payload, dict) else []
        directory = client.get(
            f"{base}/contents/.github/workflows?ref={urllib.parse.quote(default_branch, safe='')}"
        )
        workflow_files = [
            row for row in (directory or [])
            if isinstance(row, dict) and str(row.get("name", "")).lower().endswith((".yml", ".yaml"))
        ]
        workflow_files.sort(key=lambda row: str(row.get("path") or ""))
        truncated = len(workflow_files) > max_workflows
        workflow_sources: list[dict[str, Any]] = []
        for row in workflow_files[:max_workflows]:
            path = str(row["path"])
            content = client.get(
                f"{base}/contents/{urllib.parse.quote(path, safe='/')}?ref={urllib.parse.quote(default_branch, safe='')}"
            )
            workflow_sources.append({"path": path, "text": _decode_content(content)})

        rulesets = client.get(f"{base}/rulesets?includes_parents=false")
        protection = client.get(
            f"{base}/branches/{urllib.parse.quote(default_branch, safe='')}/protection"
        )
        files = community.get("files", {}) if isinstance(community, dict) else {}
        observed.append(
            {
                "name": name,
                "private": bool(repo.get("private")),
                "visibility": repo.get("visibility") or ("private" if repo.get("private") else "public"),
                "archived": bool(repo.get("archived")),
                "disabled": bool(repo.get("disabled")),
                "description": repo.get("description") or "",
                "homepage": repo.get("homepage") or "",
                "language": repo.get("language") or "",
                "license": (repo.get("license") or {}).get("spdx_id"),
                "default_branch": default_branch,
                "pushed_at": repo.get("pushed_at"),
                "updated_at": repo.get("updated_at"),
                "open_issues_count": int(repo.get("open_issues_count") or 0),
                "topics": repo.get("topics") or [],
                "community_health_percentage": community.get("health_percentage") if isinstance(community, dict) else None,
                "community_files": {key: bool(value) for key, value in files.items()},
                "workflow_count": len(workflow_rows),
                "workflow_files_seen": len(workflow_sources),
                "workflow_files_truncated": truncated,
                "workflow_sources": workflow_sources,
                "ruleset_count": len(rulesets) if isinstance(rulesets, list) else None,
                "default_branch_protected": isinstance(protection, dict),
            }
        )

    return {
        "schema": "szl.org-frontier-snapshot/v1",
        "organization": org,
        "collected_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "repositories": observed,
    }


def _parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def _uses_findings(sources: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for source in sources:
        path = str(source.get("path") or "")
        text = str(source.get("text") or "")
        for raw in USES.findall(text):
            action = raw.strip().strip('"\'')
            if action.startswith("./") or "@" not in action:
                continue
            target, ref = action.rsplit("@", 1)
            if not FULL_SHA.fullmatch(ref.lower()):
                findings.append({"path": path, "action": target, "ref": ref})
    return findings


def analyze(snapshot: dict[str, Any], authority: dict[str, Any], *, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    repos = snapshot.get("repositories")
    if not isinstance(repos, list):
        raise AuditError("snapshot.repositories must be a list")

    locked = authority.get("locked_formula_ids")
    expected = ["F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22"]
    if locked != expected:
        raise AuditError("authority must preserve the exact ordered locked-eight set")
    if authority.get("lambda_status") != "CONJECTURE_1_ADVISORY":
        raise AuditError("Lambda must remain CONJECTURE_1_ADVISORY")

    canonical = set(authority.get("canonical_control_planes", {}).values())
    for vertical in authority.get("verticals", []):
        canonical.update(vertical.get("canonical_repositories", []))
    names = {str(repo.get("name")) for repo in repos}
    stale_days = int(authority["audit_policy"]["stale_after_days"])
    duplicate_prefix = str(authority["audit_policy"]["duplicate_description_prefix"])

    findings: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    for repo in sorted(repos, key=lambda row: str(row.get("name") or "")):
        name = str(repo.get("name") or "")
        description = str(repo.get("description") or "")
        duplicate_match = CANONICAL_IN_DESCRIPTION.search(description)
        duplicate_target = duplicate_match.group(1) if duplicate_match else None
        is_duplicate = description.startswith(duplicate_prefix)
        pushed = _parse_time(repo.get("pushed_at"))
        age_days = (now - pushed).days if pushed else None
        unpinned = _uses_findings(repo.get("workflow_sources") or [])
        role = "canonical" if name in canonical else "supporting"
        if is_duplicate:
            role = "duplicate_hologram"
        elif repo.get("archived"):
            role = "archived"

        row = {
            **{key: value for key, value in repo.items() if key != "workflow_sources"},
            "role": role,
            "duplicate_target": duplicate_target,
            "age_days_since_push": age_days,
            "unpinned_action_uses": unpinned,
        }
        normalized.append(row)

        def add(code: str, severity: str, detail: str) -> None:
            findings.append({"repository": name, "code": code, "severity": severity, "detail": detail})

        if repo.get("private"):
            add("PRIVATE_REPOSITORY", "INFO", "GitHub source visibility is private; this is separate from Hugging Face Space visibility.")
        if not description:
            add("MISSING_DESCRIPTION", "MEDIUM", "Repository has no public purpose statement.")
        if not repo.get("homepage") and role == "canonical":
            add("CANONICAL_MISSING_HOMEPAGE", "MEDIUM", "Canonical repository has no product, proof or runtime homepage.")
        if not repo.get("license") and not repo.get("private"):
            add("PUBLIC_MISSING_LICENSE", "HIGH", "Public source lacks a detected SPDX license.")
        community = repo.get("community_files") or {}
        if not community.get("readme"):
            add("MISSING_README", "HIGH", "Default branch has no detected README.")
        if role == "canonical" and not community.get("security"):
            add("CANONICAL_MISSING_SECURITY", "MEDIUM", "Canonical repository has no detected security policy.")
        if age_days is not None and age_days > stale_days and not repo.get("archived"):
            add("STALE_ACTIVE_REPOSITORY", "MEDIUM", f"No push observed for {age_days} days; classify, revive or archive.")
        if is_duplicate:
            if not repo.get("archived"):
                add("DUPLICATE_NOT_ARCHIVED", "HIGH", "Description declares a duplicate/hologram but repository remains active.")
            if not duplicate_target:
                add("DUPLICATE_TARGET_UNPARSEABLE", "HIGH", "Duplicate description does not expose a parseable canonical repository.")
            elif duplicate_target not in names:
                add("DUPLICATE_TARGET_MISSING", "HIGH", f"Declared canonical target {duplicate_target!r} is absent from the census.")
        if unpinned:
            add("UNPINNED_THIRD_PARTY_ACTION", "HIGH", f"Found {len(unpinned)} third-party action reference(s) not pinned to full commit SHAs.")
        if repo.get("workflow_files_truncated"):
            add("WORKFLOW_AUDIT_TRUNCATED", "INFO", "Workflow file count exceeded the bounded per-repository inspection limit.")
        if role == "canonical" and repo.get("default_branch_protected") is False:
            add("CANONICAL_DEFAULT_BRANCH_UNPROTECTED", "HIGH", "No classic default-branch protection was readable; inspect rulesets before promotion.")

    vertical_status: list[dict[str, Any]] = []
    for vertical in authority.get("verticals", []):
        declared = vertical.get("canonical_repositories", [])
        missing = [name for name in declared if name not in names]
        formula_ok = vertical.get("formula_binding") == "complete_locked_eight_via_shared_anatomy"
        vertical_status.append(
            {
                "slug": vertical.get("slug"),
                "brand": vertical.get("brand"),
                "canonical_repositories": declared,
                "missing_repositories": missing,
                "runtime_surfaces": vertical.get("runtime_surfaces", []),
                "product_routes": vertical.get("product_routes", []),
                "formula_binding_valid": formula_ok,
                "ready_for_runtime_proof": not missing and formula_ok,
            }
        )
        if missing:
            findings.append({"repository": "<vertical-map>", "code": "VERTICAL_CANONICAL_SOURCE_MISSING", "severity": "CRITICAL", "detail": f"{vertical.get('slug')}: {', '.join(missing)}"})
        if not formula_ok:
            findings.append({"repository": "<vertical-map>", "code": "VERTICAL_FORMULA_BINDING_INVALID", "severity": "CRITICAL", "detail": str(vertical.get("slug"))})

    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "INFO": 3}
    findings.sort(key=lambda row: (severity_order.get(row["severity"], 9), row["repository"], row["code"]))
    counts = {
        "repositories": len(normalized),
        "public": sum(not row.get("private") for row in normalized),
        "private": sum(bool(row.get("private")) for row in normalized),
        "active": sum(not row.get("archived") for row in normalized),
        "archived": sum(bool(row.get("archived")) for row in normalized),
        "canonical": sum(row.get("role") == "canonical" for row in normalized),
        "duplicates": sum(row.get("role") == "duplicate_hologram" for row in normalized),
        "findings": len(findings),
        "critical": sum(row["severity"] == "CRITICAL" for row in findings),
        "high": sum(row["severity"] == "HIGH" for row in findings),
        "medium": sum(row["severity"] == "MEDIUM" for row in findings),
    }
    return {
        "schema": "szl.org-frontier-audit/v1",
        "organization": snapshot.get("organization"),
        "collected_at": snapshot.get("collected_at"),
        "analyzed_at": now.replace(microsecond=0).isoformat(),
        "vision": authority.get("vision"),
        "locked_formula_ids": locked,
        "lambda_status": authority.get("lambda_status"),
        "counts": counts,
        "verticals": vertical_status,
        "findings": findings,
        "repositories": normalized,
    }


def render_markdown(audit: dict[str, Any]) -> str:
    counts = audit["counts"]
    lines = [
        "# SZL Holdings organization frontier audit",
        "",
        f"Generated: `{audit.get('analyzed_at')}`",
        "",
        f"> {audit.get('vision')}",
        "",
        "## Census",
        "",
        "| Repositories | Public | Private | Active | Archived | Canonical | Duplicates | Findings |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| {counts['repositories']} | {counts['public']} | {counts['private']} | {counts['active']} | {counts['archived']} | {counts['canonical']} | {counts['duplicates']} | {counts['findings']} |",
        "",
        f"Locked formulas: `{{{','.join(audit['locked_formula_ids'])}}}`. `Λ = Conjecture 1` remains advisory.",
        "",
        "## Domain bodies",
        "",
        "| Body | Canonical source | Runtime surfaces | Formula binding | Source present |",
        "|---|---|---|---|---|",
    ]
    for row in audit["verticals"]:
        lines.append(
            "| {brand} | `{sources}` | `{runtimes}` | {formula} | {present} |".format(
                brand=row["brand"],
                sources=", ".join(row["canonical_repositories"]),
                runtimes=", ".join(row["runtime_surfaces"]),
                formula="LOCKED-8" if row["formula_binding_valid"] else "INVALID",
                present="YES" if not row["missing_repositories"] else "NO",
            )
        )
    lines.extend(["", "## Highest-priority findings", ""])
    important = [row for row in audit["findings"] if row["severity"] in {"CRITICAL", "HIGH"}]
    if not important:
        lines.append("No CRITICAL or HIGH findings were observed in this bounded run.")
    else:
        lines.extend(["| Severity | Repository | Code | Detail |", "|---|---|---|---|"])
        for row in important[:200]:
            detail = str(row["detail"]).replace("|", "\\|")
            lines.append(f"| {row['severity']} | `{row['repository']}` | `{row['code']}` | {detail} |")
        if len(important) > 200:
            lines.append(f"\n{len(important) - 200} additional HIGH/CRITICAL findings remain in the JSON artifact.")
    lines.extend([
        "",
        "## Interpretation boundary",
        "",
        "This is repository and workflow evidence, not a claim that a website, Space, model, data feed or vertical is operational. Runtime readiness requires an exact source revision, live health/domain probes, claim-label checks and a separate deployment receipt.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default="szl-holdings")
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--offline-fixture", type=Path)
    args = parser.parse_args()

    authority = json.loads(args.authority.read_text(encoding="utf-8"))
    if args.offline_fixture:
        snapshot = json.loads(args.offline_fixture.read_text(encoding="utf-8"))
    else:
        token = os.environ.get("GH_TOKEN", "").strip()
        if not token:
            raise AuditError("GH_TOKEN is required for a live census")
        snapshot = collect_live(GitHubClient(token), args.org, authority)

    audit = analyze(snapshot, authority)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown.write_text(render_markdown(audit), encoding="utf-8")
    print(json.dumps(audit["counts"], sort_keys=True))
    return 1 if audit["counts"]["critical"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
