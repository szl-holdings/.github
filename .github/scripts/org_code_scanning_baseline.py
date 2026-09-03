#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Configure GitHub CodeQL default setup across eligible public repositories.

The operator is bounded to active, non-fork, public repositories in one GitHub
organization. It preserves every repository that already contains an advanced
CodeQL workflow, skips unsupported-language repositories, and changes only the
native code-scanning default-setup configuration. It never edits source,
branches, rulesets, visibility, secrets, archived state, or provider resources.

Dry-run is the default. ``--apply`` enables idempotent configuration writes.
Every run emits a secret-free receipt and reconciles one organization issue with
exact per-repository outcomes.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

API = "https://api.github.com"
SCHEMA = "szl.org-code-scanning-baseline/v1"
DEFAULT_ORG = "szl-holdings"
ISSUE_TITLE = "[security] Organization CodeQL baseline"
ISSUE_MARKER = "<!-- SZL-ORG-CODE-SCANNING-BASELINE-V1 -->"
TOKEN_RE = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._~+/=-]{12,})",
    re.IGNORECASE,
)
WORKFLOW_SUFFIXES = (".yml", ".yaml")
CODEQL_ACTION_MARKER = "github/codeql-action/"
LANGUAGE_MAP = {
    "C": "c-cpp",
    "C++": "c-cpp",
    "C#": "csharp",
    "Go": "go",
    "Java": "java-kotlin",
    "Kotlin": "java-kotlin",
    "JavaScript": "javascript-typescript",
    "TypeScript": "javascript-typescript",
    "Python": "python",
    "Ruby": "ruby",
    "Swift": "swift",
}


class BaselineError(RuntimeError):
    """Fail-closed error with secret-free text."""


@dataclass
class RepositoryResult:
    repository: str
    default_branch: str
    detected_languages: list[str] = field(default_factory=list)
    codeql_languages: list[str] = field(default_factory=list)
    advanced_workflow_paths: list[str] = field(default_factory=list)
    previous_state: str | None = None
    previous_languages: list[str] = field(default_factory=list)
    action: str = "UNASSESSED"
    final_state: str | None = None
    final_languages: list[str] = field(default_factory=list)
    error: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return TOKEN_RE.sub("[REDACTED]", value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact(item) for key, item in value.items()}
    return value


def codeql_languages(languages: Iterable[str]) -> list[str]:
    return sorted({LANGUAGE_MAP[name] for name in languages if name in LANGUAGE_MAP})


def eligible_repository(row: dict[str, Any]) -> bool:
    return (
        row.get("archived") is not True
        and row.get("disabled") is not True
        and row.get("fork") is not True
        and row.get("private") is not True
        and bool(row.get("full_name"))
        and bool(row.get("default_branch"))
    )


def normalize_default_setup(value: Any) -> tuple[str, list[str]]:
    if not isinstance(value, dict):
        return "unknown", []
    state = str(value.get("state") or "unknown").casefold()
    languages = sorted(
        item
        for item in value.get("languages") or []
        if isinstance(item, str) and item
    )
    return state, languages


def needs_configuration(
    *,
    state: str,
    current_languages: Iterable[str],
    desired_languages: Iterable[str],
) -> bool:
    current = set(current_languages)
    desired = set(desired_languages)
    return state != "configured" or not desired.issubset(current)


class GitHub:
    def __init__(self, token: str, *, apply: bool) -> None:
        if apply and not token.strip():
            raise BaselineError("apply mode requires an organization-capable GitHub token")
        self.token = token.strip()
        self.apply = apply
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-org-code-scanning-baseline/1.0",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        *,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        body = None
        headers = dict(self.headers)
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            path if path.startswith("https://") else API + path,
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
                value = json.loads(raw) if raw else None
                status = response.status
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:3000]
            raise BaselineError(
                f"GitHub HTTP {exc.code}: {redact(detail)}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise BaselineError(f"GitHub request failed: {redact(str(exc))}") from exc
        if status not in expected:
            raise BaselineError(f"unexpected GitHub status {status} for {method} {path}")
        return value

    def repositories(self, org: str, *, limit: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page = 1
        while len(rows) < limit:
            per_page = min(100, limit - len(rows))
            result = self.request(
                "GET",
                f"/orgs/{org}/repos?type=all&sort=full_name&direction=asc&per_page={per_page}&page={page}",
            )
            if not isinstance(result, list):
                raise BaselineError("organization repository inventory is not an array")
            rows.extend(item for item in result if isinstance(item, dict))
            if len(result) < per_page:
                break
            page += 1
            if page > 20:
                raise BaselineError("repository pagination exceeded the bounded page limit")
        return rows[:limit]

    def languages(self, repository: str) -> list[str]:
        value = self.request("GET", f"/repos/{repository}/languages")
        if not isinstance(value, dict):
            raise BaselineError(f"language inventory is not an object: {repository}")
        return sorted(str(name) for name in value if value.get(name))

    def workflow_entries(self, repository: str, default_branch: str) -> list[dict[str, Any]]:
        encoded = urllib.parse.quote(default_branch, safe="")
        try:
            value = self.request(
                "GET",
                f"/repos/{repository}/contents/.github/workflows?ref={encoded}",
            )
        except BaselineError as exc:
            if "HTTP 404" in str(exc):
                return []
            raise
        return value if isinstance(value, list) else []

    def file_text(self, repository: str, path: str, default_branch: str) -> str:
        encoded_path = urllib.parse.quote(path, safe="/")
        encoded_ref = urllib.parse.quote(default_branch, safe="")
        value = self.request(
            "GET",
            f"/repos/{repository}/contents/{encoded_path}?ref={encoded_ref}",
        )
        if not isinstance(value, dict) or value.get("type") != "file":
            raise BaselineError(f"workflow content is not a file: {repository}:{path}")
        content = value.get("content")
        if not isinstance(content, str):
            raise BaselineError(f"workflow content is unavailable: {repository}:{path}")
        try:
            return base64.b64decode(content, validate=True).decode("utf-8", "strict")
        except (ValueError, UnicodeDecodeError) as exc:
            raise BaselineError(
                f"workflow is not strict UTF-8/base64: {repository}:{path}"
            ) from exc

    def advanced_codeql_workflows(self, repository: str, default_branch: str) -> list[str]:
        found: list[str] = []
        for row in self.workflow_entries(repository, default_branch):
            path = str(row.get("path") or "")
            if not path.casefold().endswith(WORKFLOW_SUFFIXES):
                continue
            text = self.file_text(repository, path, default_branch)
            if CODEQL_ACTION_MARKER in text:
                found.append(path)
        return sorted(found)

    def default_setup(self, repository: str) -> dict[str, Any]:
        try:
            value = self.request(
                "GET", f"/repos/{repository}/code-scanning/default-setup"
            )
        except BaselineError as exc:
            if "HTTP 404" in str(exc):
                return {"state": "not-configured", "languages": []}
            raise
        return value if isinstance(value, dict) else {}

    def configure_default_setup(
        self, repository: str, languages: list[str]
    ) -> dict[str, Any]:
        if not self.apply:
            return {
                "state": "configured",
                "languages": languages,
                "query_suite": "extended",
                "runner_type": "standard",
            }
        value = self.request(
            "PATCH",
            f"/repos/{repository}/code-scanning/default-setup",
            {
                "state": "configured",
                "languages": languages,
                "query_suite": "extended",
                "runner_type": "standard",
            },
            expected=(200, 201, 202),
        )
        return value if isinstance(value, dict) else {}

    def exact_issue(self, org: str) -> dict[str, Any] | None:
        query = urllib.parse.quote(
            f'repo:{org}/.github is:issue in:title "{ISSUE_TITLE}"'
        )
        value = self.request("GET", f"/search/issues?q={query}&per_page=20")
        rows = value.get("items", []) if isinstance(value, dict) else []
        exact = [
            row
            for row in rows
            if row.get("title") == ISSUE_TITLE
            and ISSUE_MARKER in str(row.get("body") or "")
        ]
        return max(exact, key=lambda row: int(row.get("number") or 0)) if exact else None

    def upsert_issue(self, org: str, body: str) -> str:
        existing = self.exact_issue(org)
        if not self.apply:
            return str((existing or {}).get("html_url") or "DRY_RUN")
        if existing:
            value = self.request(
                "PATCH",
                f"/repos/{org}/.github/issues/{existing['number']}",
                {"body": body, "state": "open"},
            )
        else:
            value = self.request(
                "POST",
                f"/repos/{org}/.github/issues",
                {"title": ISSUE_TITLE, "body": body},
                expected=(201,),
            )
        return str((value or {}).get("html_url") or "UNKNOWN")


def assess_repository(api: GitHub, row: dict[str, Any]) -> RepositoryResult:
    repository = str(row["full_name"])
    default_branch = str(row["default_branch"])
    result = RepositoryResult(repository=repository, default_branch=default_branch)
    try:
        result.detected_languages = api.languages(repository)
        result.codeql_languages = codeql_languages(result.detected_languages)
        if not result.codeql_languages:
            result.action = "SKIPPED_NO_SUPPORTED_LANGUAGE"
            result.final_state = "not-applicable"
            return result

        result.advanced_workflow_paths = api.advanced_codeql_workflows(
            repository, default_branch
        )
        if result.advanced_workflow_paths:
            result.action = "PRESERVED_ADVANCED_SETUP"
            result.final_state = "advanced"
            result.final_languages = result.codeql_languages
            return result

        current = api.default_setup(repository)
        result.previous_state, result.previous_languages = normalize_default_setup(current)
        if not needs_configuration(
            state=result.previous_state,
            current_languages=result.previous_languages,
            desired_languages=result.codeql_languages,
        ):
            result.action = "ALREADY_CONFIGURED"
            result.final_state = "configured"
            result.final_languages = result.previous_languages
            return result

        configured = api.configure_default_setup(repository, result.codeql_languages)
        final_state, final_languages = normalize_default_setup(configured)
        if final_state != "configured":
            raise BaselineError(
                f"default setup did not return configured state: {final_state}"
            )
        if not set(result.codeql_languages).issubset(set(final_languages)):
            raise BaselineError(
                "default setup response omitted one or more detected CodeQL languages"
            )
        result.action = "WOULD_CONFIGURE" if not api.apply else "CONFIGURED"
        result.final_state = final_state
        result.final_languages = final_languages
    except Exception as exc:
        result.action = "BLOCKED"
        result.error = str(redact(str(exc)))
    return result


def issue_body(
    *,
    org: str,
    apply: bool,
    results: list[RepositoryResult],
    generated_at: str,
) -> str:
    counts = Counter(row.action for row in results)
    blocked = [row for row in results if row.action == "BLOCKED"]
    lines = [
        ISSUE_MARKER,
        "# Organization CodeQL baseline",
        "",
        f"Generated: `{generated_at}`",
        f"Mode: `{'APPLY' if apply else 'DRY_RUN'}`",
        f"Organization: `{org}`",
        "",
        "This controller configures GitHub native CodeQL default setup only for active public repositories that have supported source languages and no advanced CodeQL workflow. Existing advanced setups are preserved.",
        "",
        "## Results",
        "",
    ]
    for action, count in sorted(counts.items()):
        lines.append(f"- `{action}`: **{count}**")
    if blocked:
        lines += ["", "## Managed prerequisites or repository-specific blockers", ""]
        for row in blocked:
            lines.append(
                f"- `{row.repository}` — `{redact(row.error or 'UNKNOWN')}`"
            )
    lines += [
        "",
        "## Boundaries",
        "",
        "- Archived, disabled, private, and fork repositories are excluded.",
        "- Existing advanced CodeQL workflows are never replaced.",
        "- Source, branches, rulesets, visibility, secrets, archive state, provider resources, and billing are unchanged.",
        "- Token values are neither printed nor persisted.",
    ]
    return "\n".join(lines) + "\n"


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(redact(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default=DEFAULT_ORG)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-repositories", type=int, default=500)
    parser.add_argument("--report", type=Path, default=Path("org-code-scanning-baseline.json"))
    args = parser.parse_args(argv)

    token = (
        os.environ.get("SZL_ORG_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    )
    started = utc_now()
    try:
        api = GitHub(token, apply=args.apply)
        inventory = api.repositories(args.org, limit=args.max_repositories)
        eligible = [row for row in inventory if eligible_repository(row)]
        results = [assess_repository(api, row) for row in eligible]
        generated = utc_now()
        body = issue_body(
            org=args.org,
            apply=args.apply,
            results=results,
            generated_at=generated,
        )
        issue_url = api.upsert_issue(args.org, body)
        payload = {
            "schema": SCHEMA,
            "status": "COMPLETE",
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "organization": args.org,
            "started_at": started,
            "finished_at": generated,
            "token_value_recorded": False,
            "inventory_count": len(inventory),
            "eligible_public_repository_count": len(eligible),
            "results": [asdict(row) for row in results],
            "summary": dict(Counter(row.action for row in results)),
            "issue_url": issue_url,
        }
    except Exception as exc:
        payload = {
            "schema": SCHEMA,
            "status": "BLOCKED_MANAGED_PREREQUISITE",
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "organization": args.org,
            "started_at": started,
            "finished_at": utc_now(),
            "token_value_recorded": False,
            "error": str(redact(str(exc))),
        }
        write_report(args.report, payload)
        print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
        return 2

    write_report(args.report, payload)
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
