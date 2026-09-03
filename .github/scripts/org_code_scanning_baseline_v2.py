#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Converge native code scanning across eligible SZL public repositories.

The operator changes only GitHub CodeQL *default setup*. It preserves any
repository that already has a code-scanning analysis, whether produced by an
advanced CodeQL workflow or another SARIF publisher. It excludes private,
archived, disabled, and fork repositories, skips unsupported languages, verifies
every configuration write by provider readback, and records blockers without
weakening repository source or protection.

Dry-run is the default. ``--apply`` enables the bounded default-setup writes.
"""
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
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

API = "https://api.github.com"
SCHEMA = "szl.org-code-scanning-baseline/v2"
DEFAULT_ORG = "szl-holdings"
ISSUE_TITLE = "[security] Organization CodeQL baseline"
ISSUE_MARKER = "<!-- SZL-ORG-CODE-SCANNING-BASELINE-V2 -->"
TOKEN_RE = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+[A-Za-z0-9._~+/=-]{12,})",
    re.IGNORECASE,
)
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
    """Fail-closed provider or contract error."""


@dataclass
class RepositoryResult:
    repository: str
    default_branch: str
    detected_languages: list[str] = field(default_factory=list)
    codeql_languages: list[str] = field(default_factory=list)
    previous_state: str | None = None
    previous_languages: list[str] = field(default_factory=list)
    existing_analysis: dict[str, Any] | None = None
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


def normalize_setup(value: Any) -> tuple[str, list[str]]:
    if not isinstance(value, dict):
        return "unknown", []
    state = str(value.get("state") or "unknown").casefold()
    languages = sorted(
        value
        for value in value.get("languages") or []
        if isinstance(value, str) and value
    )
    return state, languages


def needs_configuration(
    state: str, current_languages: Iterable[str], desired_languages: Iterable[str]
) -> bool:
    return state != "configured" or not set(desired_languages).issubset(
        set(current_languages)
    )


def compact_analysis(value: dict[str, Any]) -> dict[str, Any]:
    tool = value.get("tool") or {}
    return {
        "id": value.get("id"),
        "ref": value.get("ref"),
        "commit_sha": value.get("commit_sha"),
        "analysis_key": value.get("analysis_key"),
        "category": value.get("category"),
        "environment": value.get("environment"),
        "created_at": value.get("created_at"),
        "tool": tool.get("name") if isinstance(tool, dict) else None,
    }


class GitHub:
    def __init__(self, token: str, *, apply: bool) -> None:
        if apply and not token.strip():
            raise BaselineError("apply mode requires an organization-capable GitHub token")
        self.apply = apply
        self.token = token.strip()
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-code-scanning-baseline-v2/1.0",
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
            raise BaselineError(f"GitHub HTTP {exc.code}: {redact(detail)}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise BaselineError(f"GitHub request failed: {redact(str(exc))}") from exc
        if status not in expected:
            raise BaselineError(f"unexpected GitHub status {status} for {method} {path}")
        return value

    def repositories(self, org: str, *, limit: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page = 1
        while len(rows) < limit and page <= 20:
            per_page = min(100, limit - len(rows))
            value = self.request(
                "GET",
                f"/orgs/{org}/repos?type=all&sort=full_name&direction=asc&per_page={per_page}&page={page}",
            )
            if not isinstance(value, list):
                raise BaselineError("organization repository inventory is not an array")
            rows.extend(row for row in value if isinstance(row, dict))
            if len(value) < per_page:
                break
            page += 1
        if page > 20:
            raise BaselineError("repository inventory exceeded the bounded page limit")
        return rows[:limit]

    def languages(self, repository: str) -> list[str]:
        value = self.request("GET", f"/repos/{repository}/languages")
        if not isinstance(value, dict):
            raise BaselineError(f"language inventory is not an object: {repository}")
        return sorted(str(name) for name, size in value.items() if size)

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

    def latest_analysis(self, repository: str) -> dict[str, Any] | None:
        try:
            value = self.request(
                "GET",
                f"/repos/{repository}/code-scanning/analyses?per_page=1&sort=created&direction=desc",
            )
        except BaselineError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise
        if not isinstance(value, list) or not value:
            return None
        first = value[0]
        return compact_analysis(first) if isinstance(first, dict) else None

    def configure_default_setup(
        self, repository: str, desired_languages: list[str]
    ) -> dict[str, Any]:
        if not self.apply:
            return {
                "state": "configured",
                "languages": desired_languages,
                "query_suite": "extended",
                "runner_type": "standard",
            }
        self.request(
            "PATCH",
            f"/repos/{repository}/code-scanning/default-setup",
            {
                "state": "configured",
                "languages": desired_languages,
                "query_suite": "extended",
                "runner_type": "standard",
            },
            expected=(200, 201, 202),
        )
        last: dict[str, Any] = {}
        for attempt in range(12):
            last = self.default_setup(repository)
            state, languages = normalize_setup(last)
            if state == "configured" and set(desired_languages).issubset(
                set(languages)
            ):
                return last
            if attempt < 11:
                time.sleep(min(5, attempt + 1))
        raise BaselineError(
            "default setup write did not converge to configured readback: "
            + json.dumps(redact(last), sort_keys=True)[:1000]
        )

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
        current = self.exact_issue(org)
        if not self.apply:
            return str((current or {}).get("html_url") or "DRY_RUN")
        if current:
            value = self.request(
                "PATCH",
                f"/repos/{org}/.github/issues/{current['number']}",
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

        current = api.default_setup(repository)
        result.previous_state, result.previous_languages = normalize_setup(current)
        if not needs_configuration(
            result.previous_state,
            result.previous_languages,
            result.codeql_languages,
        ):
            result.action = "ALREADY_CONFIGURED"
            result.final_state = "configured"
            result.final_languages = result.previous_languages
            return result

        result.existing_analysis = api.latest_analysis(repository)
        if result.previous_state != "configured" and result.existing_analysis:
            result.action = "PRESERVED_EXISTING_ANALYSIS"
            result.final_state = "existing-analysis"
            result.final_languages = result.codeql_languages
            return result

        configured = api.configure_default_setup(
            repository, result.codeql_languages
        )
        state, languages = normalize_setup(configured)
        if state != "configured":
            raise BaselineError(
                f"default setup did not return configured state: {state}"
            )
        if not set(result.codeql_languages).issubset(set(languages)):
            raise BaselineError(
                "configured readback omitted one or more detected CodeQL languages"
            )
        result.action = "CONFIGURED" if api.apply else "WOULD_CONFIGURE"
        result.final_state = state
        result.final_languages = languages
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
    counts = Counter(result.action for result in results)
    blocked = [result for result in results if result.action == "BLOCKED"]
    lines = [
        ISSUE_MARKER,
        "# Organization CodeQL baseline",
        "",
        f"Generated: `{generated_at}`",
        f"Mode: `{'APPLY' if apply else 'DRY_RUN'}`",
        f"Organization: `{org}`",
        "",
        "Native CodeQL default setup is configured only for active public repositories with supported languages and no existing code-scanning analysis. Existing advanced CodeQL or third-party SARIF rails are preserved.",
        "",
        "## Results",
        "",
    ]
    for action, count in sorted(counts.items()):
        lines.append(f"- `{action}`: **{count}**")
    if blocked:
        lines += ["", "## Exact blockers", ""]
        for result in blocked:
            lines.append(
                f"- `{result.repository}` — `{redact(result.error or 'UNKNOWN')}`"
            )
    lines += [
        "",
        "## Mutation boundary",
        "",
        "- Existing code-scanning analyses are never replaced.",
        "- Private, archived, disabled, fork, and unsupported-language repositories are skipped.",
        "- Source, branches, rulesets, protections, visibility, secrets, archive state, provider resources, and billing remain unchanged.",
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
    parser.add_argument("--report", type=Path, default=Path("org-code-scanning-baseline-v2.json"))
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
        blocked = sum(result.action == "BLOCKED" for result in results)
        payload = {
            "schema": SCHEMA,
            "status": "COMPLETE" if blocked == 0 else "PARTIAL",
            "mode": "APPLY" if args.apply else "DRY_RUN",
            "organization": args.org,
            "started_at": started,
            "finished_at": generated,
            "token_value_recorded": False,
            "inventory_count": len(inventory),
            "eligible_public_repository_count": len(eligible),
            "results": [asdict(result) for result in results],
            "summary": dict(Counter(result.action for result in results)),
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
    return 1 if args.apply and payload["status"] == "PARTIAL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
