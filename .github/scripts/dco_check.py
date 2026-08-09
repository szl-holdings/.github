#!/usr/bin/env python3
"""Fail-closed DCO validation for trusted PR, merge-group, and push events."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote
from urllib.request import Request, urlopen


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SIGNOFF_RE = re.compile(r"^\s*(.+?)\s*<([^<>\s]+@[^<>\s]+)>\s*$")
QUEUE_REF_PREFIX = "refs/heads/gh-readonly-queue/main/"
ALLOWED_PR_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review"}
MAX_API_PAGES = 20


class DcoError(ValueError):
    """Raised when event identity, history, or DCO evidence is invalid."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DcoError(message)


def require_sha(value: object, label: str) -> str:
    require(isinstance(value, str) and bool(SHA_RE.fullmatch(value)), f"{label} is invalid")
    return value


def git(
    repo: Path,
    *args: str,
    input_text: str | None = None,
    check: bool = True,
) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if check and completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise DcoError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def normalized_identity(name: str, email: str) -> tuple[str, str]:
    return " ".join(name.split()).casefold(), email.strip().casefold()


def commit_record(repo: Path, sha: str) -> tuple[list[str], str, str, str]:
    require_sha(sha, "commit SHA")
    raw = git(repo, "show", "-s", "--format=%P%x00%an%x00%ae%x00%B", sha)
    fields = raw.split("\x00", 3)
    require(len(fields) == 4, f"commit metadata is incomplete for {sha}")
    parents = fields[0].strip().split()
    return parents, fields[1], fields[2], fields[3]


def terminal_signoffs(repo: Path, message: str) -> list[tuple[str, str]]:
    parsed = git(repo, "interpret-trailers", "--parse", input_text=message)
    signoffs: list[tuple[str, str]] = []
    for line in parsed.splitlines():
        key, separator, value = line.partition(":")
        if not separator or key.strip().casefold() != "signed-off-by":
            continue
        match = SIGNOFF_RE.fullmatch(value)
        if match:
            signoffs.append(normalized_identity(match.group(1), match.group(2)))
    return signoffs


def validate_commit(repo: Path, sha: str) -> None:
    parents, author_name, author_email, message = commit_record(repo, sha)
    require(len(parents) == 1, f"{sha} must have exactly one parent")
    author = normalized_identity(author_name, author_email)
    signoffs = terminal_signoffs(repo, message)
    require(signoffs, f"{sha} has no valid terminal Signed-off-by trailer")
    require(author in signoffs, f"{sha} Signed-off-by does not match the commit author")


def checked_out_head(repo: Path) -> str:
    return require_sha(git(repo, "rev-parse", "HEAD").strip(), "checked-out HEAD")


def validate_commits(repo: Path, shas: list[str], expected_head: str) -> int:
    require(shas, "candidate commit set is empty")
    require(len(shas) == len(set(shas)), "candidate commit set contains duplicate SHAs")
    require(shas[-1] == expected_head, "last candidate commit does not match expected head")
    require(checked_out_head(repo) == expected_head, "checked-out HEAD does not match expected head")
    for sha in shas:
        validate_commit(repo, sha)
    return len(shas)


def validate_range(repo: Path, base_sha: str, head_sha: str) -> int:
    base_sha = require_sha(base_sha, "base SHA")
    head_sha = require_sha(head_sha, "head SHA")
    require(checked_out_head(repo) == head_sha, "checked-out HEAD does not match event head")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, head_sha],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    require(ancestor.returncode == 0, "base SHA is not an ancestor of head SHA")
    shas = [
        line.strip()
        for line in git(repo, "rev-list", "--reverse", f"{base_sha}..{head_sha}").splitlines()
        if line.strip()
    ]
    return validate_commits(repo, shas, head_sha)


def github_get(path: str, token: str) -> Any:
    request = Request(
        "https://api.github.com" + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "szl-dco-attestor/1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=20) as response:
        require(response.status == 200, f"GitHub API returned HTTP {response.status}")
        require(response.geturl().startswith("https://api.github.com/"), "GitHub API redirected")
        data = response.read(2_000_001)
    require(len(data) <= 2_000_000, "GitHub API response is too large")
    return json.loads(data)


def collect_pr_commits(
    repository: str,
    number: int,
    expected_base: str,
    expected_head: str,
    api_get: Callable[[str], Any],
) -> list[str]:
    encoded_repo = quote(repository, safe="/")
    rows: list[dict[str, Any]] = []
    for page in range(1, MAX_API_PAGES + 1):
        batch = api_get(
            f"/repos/{encoded_repo}/pulls/{number}/commits?per_page=100&page={page}"
        )
        require(isinstance(batch, list), "pull-request commit page is not an array")
        require(all(isinstance(item, dict) for item in batch), "commit page row is invalid")
        rows.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise DcoError("pull-request commit pagination exceeded the bounded limit")

    shas = [require_sha(item.get("sha"), "pull-request commit SHA") for item in rows]
    require(shas and shas[-1] == expected_head, "retrieved commits do not end at expected head")
    require(len(shas) == len(set(shas)), "retrieved commits contain duplicate SHAs")

    current = api_get(f"/repos/{encoded_repo}/pulls/{number}")
    require(isinstance(current, dict), "pull-request metadata is not an object")
    base = current.get("base")
    head = current.get("head")
    require(isinstance(base, dict) and isinstance(head, dict), "pull-request refs are missing")
    require(base.get("sha") == expected_base, "pull-request base moved during validation")
    require(head.get("sha") == expected_head, "pull-request head moved during validation")
    require(current.get("commits") == len(shas), "pull-request commit count changed during validation")
    require(current.get("draft") is False, "draft pull requests cannot satisfy DCO")
    return shas


def merge_group_subject(payload: dict[str, Any], github_sha: str) -> tuple[str, str]:
    require(payload.get("action") == "checks_requested", "merge_group action is not checks_requested")
    group = payload.get("merge_group")
    require(isinstance(group, dict), "merge_group payload is missing")
    require(group.get("base_ref") == "refs/heads/main", "merge_group base_ref is not main")
    head_ref = group.get("head_ref")
    require(
        isinstance(head_ref, str) and head_ref.startswith(QUEUE_REF_PREFIX),
        "merge_group head_ref is outside the protected queue namespace",
    )
    base_sha = require_sha(group.get("base_sha"), "merge_group base SHA")
    head_sha = require_sha(group.get("head_sha"), "merge_group head SHA")
    require(head_sha == require_sha(github_sha, "GITHUB_SHA"), "merge_group head differs from GITHUB_SHA")
    return base_sha, head_sha


def push_subject(payload: dict[str, Any], github_sha: str) -> tuple[str, str]:
    require(payload.get("ref") == "refs/heads/main", "push ref is not main")
    base_sha = require_sha(payload.get("before"), "push before SHA")
    head_sha = require_sha(payload.get("after"), "push after SHA")
    require(head_sha == require_sha(github_sha, "GITHUB_SHA"), "push head differs from GITHUB_SHA")
    return base_sha, head_sha


def validate_pull_request_target(
    repo: Path,
    payload: dict[str, Any],
    repository: str,
    token: str,
    api_get: Callable[[str], Any] | None = None,
) -> int:
    require(payload.get("action") in ALLOWED_PR_ACTIONS, "pull_request_target action is unsupported")
    require(
        isinstance(payload.get("repository"), dict)
        and payload["repository"].get("full_name") == repository,
        "event repository does not match GITHUB_REPOSITORY",
    )
    pr = payload.get("pull_request")
    require(isinstance(pr, dict), "pull_request payload is missing")
    base = pr.get("base")
    head = pr.get("head")
    require(isinstance(base, dict) and isinstance(head, dict), "pull-request refs are missing")
    require(base.get("ref") == "main", "pull-request base ref is not main")
    base_sha = require_sha(base.get("sha"), "pull-request base SHA")
    head_sha = require_sha(head.get("sha"), "pull-request head SHA")
    number = pr.get("number") or payload.get("number")
    require(isinstance(number, int) and number > 0, "pull-request number is invalid")
    require(bool(token), "GITHUB_TOKEN is required for trusted PR validation")
    getter = api_get or (lambda path: github_get(path, token))
    shas = collect_pr_commits(repository, number, base_sha, head_sha, getter)
    return validate_commits(repo, shas, head_sha)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--event-path", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = json.loads(args.event_path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), "event payload must be an object")
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    github_sha = os.environ.get("GITHUB_SHA", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    repo = args.repo_root.resolve()

    if event_name == "pull_request_target":
        count = validate_pull_request_target(
            repo,
            payload,
            repository,
            os.environ.get("GITHUB_TOKEN", ""),
        )
    elif event_name == "merge_group":
        base_sha, head_sha = merge_group_subject(payload, github_sha)
        count = validate_range(repo, base_sha, head_sha)
    elif event_name == "push":
        base_sha, head_sha = push_subject(payload, github_sha)
        count = validate_range(repo, base_sha, head_sha)
    else:
        raise DcoError(f"unsupported event: {event_name!r}")

    print(f"DCO OK: validated {count} exact commit(s) for {event_name}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DcoError, json.JSONDecodeError, OSError) as exc:
        print(f"DCO FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
