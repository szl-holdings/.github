#!/usr/bin/env python3
"""Verify remote reusable-workflow calls are pinned and resolvable.

GitHub accepts a syntactically valid 40-character commit SHA even when the
referenced workflow file does not exist at that commit. Such a caller fails at
workflow startup, before any job can explain the problem. This guard scans
``uses: owner/repo/.github/workflows/file.yml@ref`` entries, requires an
immutable full SHA, and verifies the exact file through the GitHub Contents API.

Exit codes:
  0 -- every remote reusable-workflow target exists at its pinned SHA
  1 -- an unpinned, malformed, or missing target was found
  2 -- target verification could not complete (network/auth/API failure)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


USES_RE = re.compile(r"^\s*(?:-\s*)?uses\s*:\s*(?P<value>.+?)\s*$")
REMOTE_REUSABLE_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9_.-]+)/"
    r"(?P<repo>[A-Za-z0-9_.-]+)/\.github/workflows/"
    r"(?P<workflow>[A-Za-z0-9_.-]+\.ya?ml)@(?P<ref>[^\s@]+)$"
)
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class WorkflowCall:
    source: Path
    line: int
    value: str
    owner: str
    repo: str
    workflow: str
    ref: str

    @property
    def target(self) -> str:
        return (
            f"{self.owner}/{self.repo}/.github/workflows/"
            f"{self.workflow}@{self.ref}"
        )

    @property
    def target_key(self) -> tuple[str, str, str, str]:
        return self.owner, self.repo, self.workflow, self.ref


@dataclass(frozen=True)
class Finding:
    source: Path
    line: int
    value: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    checked_targets: int
    violations: tuple[Finding, ...]
    unavailable: tuple[Finding, ...]

    @property
    def exit_code(self) -> int:
        if self.unavailable:
            return 2
        if self.violations:
            return 1
        return 0


class VerificationUnavailable(RuntimeError):
    """The remote target could not be classified as present or missing."""


def _uses_value(line: str) -> str | None:
    """Return a scalar ``uses`` value, excluding comments and YAML quotes."""

    if line.lstrip().startswith("#"):
        return None
    match = USES_RE.match(line)
    if not match:
        return None

    value = match.group("value").strip()
    if value.startswith(("'", '"')):
        quote_char = value[0]
        end = value.find(quote_char, 1)
        if end < 0:
            return value
        return value[1:end].strip()

    # A '#' inside a GitHub reference is invalid, so only the ordinary YAML
    # trailing-comment form needs to be preserved here.
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def scan_workflows(workflow_dir: Path) -> tuple[list[WorkflowCall], list[Finding]]:
    calls: list[WorkflowCall] = []
    findings: list[Finding] = []
    paths = sorted((*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")))

    for path in paths:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            value = _uses_value(line)
            if not value or value.startswith("./"):
                continue
            if "/.github/workflows/" not in value:
                continue

            match = REMOTE_REUSABLE_RE.fullmatch(value)
            if not match:
                findings.append(
                    Finding(
                        source=path,
                        line=line_number,
                        value=value,
                        message="Malformed remote reusable-workflow reference",
                    )
                )
                continue

            calls.append(
                WorkflowCall(
                    source=path,
                    line=line_number,
                    value=value,
                    owner=match.group("owner"),
                    repo=match.group("repo"),
                    workflow=match.group("workflow"),
                    ref=match.group("ref"),
                )
            )

    return calls, findings


def github_target_exists(
    call: WorkflowCall,
    *,
    token: str = "",
    api_base: str = "https://api.github.com",
    timeout: float = 15.0,
) -> bool:
    """Return whether the exact workflow path exists at the pinned revision."""

    workflow_path = f".github/workflows/{call.workflow}"
    url = (
        f"{api_base.rstrip('/')}/repos/{quote(call.owner, safe='')}/"
        f"{quote(call.repo, safe='')}/contents/{quote(workflow_path, safe='/')}?"
        f"{urlencode({'ref': call.ref})}"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "szl-reusable-workflow-target-check",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with urlopen(Request(url, headers=headers), timeout=timeout) as response:
            status = getattr(response, "status", response.getcode())
            if status == 200:
                return True
            raise VerificationUnavailable(f"GitHub API returned HTTP {status}")
    except HTTPError as exc:
        if exc.code == 404:
            return False
        raise VerificationUnavailable(
            f"GitHub API returned HTTP {exc.code}"
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise VerificationUnavailable(f"GitHub API request failed: {exc}") from exc


def validate_workflows(
    workflow_dir: Path,
    probe: Callable[[WorkflowCall], bool],
) -> ValidationResult:
    calls, scan_findings = scan_workflows(workflow_dir)
    violations = list(scan_findings)
    unavailable: list[Finding] = []
    unique: dict[tuple[str, str, str, str], WorkflowCall] = {}

    for call in calls:
        if not FULL_SHA_RE.fullmatch(call.ref):
            violations.append(
                Finding(
                    source=call.source,
                    line=call.line,
                    value=call.value,
                    message=(
                        "Remote reusable workflow must be pinned to a full "
                        "40-character lowercase commit SHA"
                    ),
                )
            )
            continue
        unique.setdefault(call.target_key, call)

    for call in unique.values():
        try:
            exists = probe(call)
        except VerificationUnavailable as exc:
            unavailable.append(
                Finding(
                    source=call.source,
                    line=call.line,
                    value=call.value,
                    message=f"Could not verify pinned target: {exc}",
                )
            )
            continue
        if not exists:
            violations.append(
                Finding(
                    source=call.source,
                    line=call.line,
                    value=call.value,
                    message="Reusable workflow does not exist at the pinned SHA",
                )
            )

    return ValidationResult(
        checked_targets=len(unique),
        violations=tuple(violations),
        unavailable=tuple(unavailable),
    )


def _annotation(finding: Finding) -> str:
    path = finding.source.as_posix()
    message = f"{finding.message}: {finding.value}"
    for old, new in (("%", "%25"), ("\r", "%0D"), ("\n", "%0A")):
        message = message.replace(old, new)
    return f"::error file={path},line={finding.line}::{message}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workflow-dir",
        type=Path,
        default=Path(".github/workflows"),
        help="Directory containing caller workflow YAML files",
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
        help="GitHub API base URL (defaults to GITHUB_API_URL)",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.workflow_dir.is_dir():
        print(
            f"::error::{args.workflow_dir.as_posix()} is not a workflow directory",
            file=sys.stderr,
        )
        return 2

    token = os.environ.get("GITHUB_TOKEN", "")
    result = validate_workflows(
        args.workflow_dir,
        lambda call: github_target_exists(
            call,
            token=token,
            api_base=args.api_base,
            timeout=args.timeout,
        ),
    )

    for finding in (*result.violations, *result.unavailable):
        print(_annotation(finding))

    if result.exit_code == 0:
        print(
            "PASS: Verified "
            f"{result.checked_targets} unique remote reusable-workflow "
            "target(s) at pinned SHAs."
        )
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
