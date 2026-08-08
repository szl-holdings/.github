#!/usr/bin/env python3
"""Fail-closed DCO validation for every commit returned by the PR API."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


class DcoContractError(RuntimeError):
    """The authoritative PR commit set could not be validated safely."""


_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SIGNOFF_RE = re.compile(
    r"^Signed-off-by:\s+.+\s+<[^<>\s]+@[^<>\s]+>\s*$",
    re.MULTILINE,
)


def _required_environment(env):
    api_url = str(env.get("GITHUB_API_URL") or "").rstrip("/")
    repository = str(env.get("GITHUB_REPOSITORY") or "")
    token = str(env.get("GITHUB_TOKEN") or "")
    pr_number = str(env.get("PR_NUMBER") or "")

    parsed = urllib.parse.urlsplit(api_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise DcoContractError("GITHUB_API_URL must be an absolute HTTPS origin")
    if not _REPOSITORY_RE.fullmatch(repository):
        raise DcoContractError("GITHUB_REPOSITORY must be exactly <owner>/<repo>")
    if not token:
        raise DcoContractError("GITHUB_TOKEN is required")
    if not pr_number.isdigit() or int(pr_number) < 1:
        raise DcoContractError("PR_NUMBER must be a positive integer")
    return api_url, repository, int(pr_number), token


def fetch_pr_commits(api_url, repository, pr_number, token, *, opener=None):
    """Return every authoritative PR commit or fail closed."""
    if opener is None:
        opener = urllib.request.urlopen

    encoded_repo = urllib.parse.quote(repository, safe="/")
    commits = []
    for page in range(1, 101):
        url = (
            f"{api_url}/repos/{encoded_repo}/pulls/{pr_number}/commits"
            f"?per_page=100&page={page}"
        )
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "szl-dco-check/1.0",
            },
        )
        try:
            with opener(request, timeout=30) as response:
                status = getattr(response, "status", 200)
                raw = response.read()
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise DcoContractError(
                f"PR commit API retrieval failed on page {page}: {type(exc).__name__}"
            ) from exc

        if status != 200:
            raise DcoContractError(
                f"PR commit API returned HTTP {status} on page {page}"
            )
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DcoContractError(
                f"PR commit API returned invalid JSON on page {page}"
            ) from exc
        if not isinstance(payload, list):
            raise DcoContractError(
                f"PR commit API returned a non-list payload on page {page}"
            )
        if not payload:
            if page == 1:
                raise DcoContractError("PR commit API returned an empty commit list")
            break

        commits.extend(payload)
        if len(payload) < 100:
            break
    else:
        raise DcoContractError("PR commit API exceeded the bounded pagination limit")

    if not commits:
        raise DcoContractError("PR commit API returned an empty commit list")
    return commits


def commits_missing_signoff(commits):
    """Return commit SHAs without a valid Signed-off-by trailer."""
    if not isinstance(commits, list) or not commits:
        raise DcoContractError("DCO validation requires a non-empty commit list")

    missing = []
    for index, item in enumerate(commits, start=1):
        if not isinstance(item, dict):
            raise DcoContractError(f"commit {index} is not an object")
        sha = str(item.get("sha") or "").lower()
        commit = item.get("commit")
        message = commit.get("message") if isinstance(commit, dict) else None
        if not _SHA_RE.fullmatch(sha):
            raise DcoContractError(f"commit {index} has no exact SHA")
        if not isinstance(message, str) or not message:
            raise DcoContractError(f"commit {sha} has no commit message")
        if not _SIGNOFF_RE.search(message):
            missing.append(sha)
    return missing


def main(env=None, *, opener=None):
    env = os.environ if env is None else env
    try:
        api_url, repository, pr_number, token = _required_environment(env)
        commits = fetch_pr_commits(
            api_url,
            repository,
            pr_number,
            token,
            opener=opener,
        )
        missing = commits_missing_signoff(commits)
    except DcoContractError as exc:
        print(f"::error title=DCO contract::{exc}")
        return 2

    if missing:
        for sha in missing:
            print(f"::error title=DCO sign-off missing::{sha}")
        print(
            f"FAIL: {len(missing)} of {len(commits)} PR commits "
            "lack a valid Signed-off-by trailer."
        )
        return 1

    print(f"OK: all {len(commits)} PR commits carry Signed-off-by trailers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
