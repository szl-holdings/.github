#!/usr/bin/env python3
"""Fail-closed DCO validation for every commit in a pull request."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


API_VERSION = "2022-11-28"
COMMITS_PER_PAGE = 100
MAX_PULL_REQUEST_COMMITS = 250
REQUEST_TIMEOUT_SECONDS = 30
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PATCH_DIVIDER_PATTERN = re.compile(r"^---(?:[ \t\r]|$)")
QUEUE_REF_PREFIX = "refs/heads/gh-readonly-queue/main/"
ALLOWED_PR_ACTIONS = {"opened", "synchronize", "reopened", "ready_for_review", "edited"}

# Audited horizontal separators: TAB, SPACE, and every Unicode Zs code point.
# Name, email, and trailer text separately reject C0/C1 controls, Unicode line
# and paragraph separators, and every Bidi_Control code point. Ordinary RTL
# letters remain valid, but invisible direction overrides cannot alter review.
HORIZONTAL_SEPARATOR_PATTERN = (
    r"[\x09\x20\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]"
)
NAME_TOKEN_PATTERN = (
    r"[^<>\x00-\x20\x7f-\x9f\u00a0\u1680\u2000-\u200a"
    r"\u061c\u200e\u200f\u2028\u2029\u202a-\u202e\u202f"
    r"\u205f\u2066-\u2069\u3000]+"
)
EMAIL_PART_PATTERN = (
    r"[^<>@\x00-\x20\x7f-\x9f\u00a0\u1680\u2000-\u200a"
    r"\u061c\u200e\u200f\u2028\u2029\u202a-\u202e\u202f"
    r"\u205f\u2066-\u2069\u3000]+"
)
SIGNED_OFF_BY_PATTERN = re.compile(
    rf"^Signed-off-by:{HORIZONTAL_SEPARATOR_PATTERN}+"
    rf"(?P<name>{NAME_TOKEN_PATTERN}(?:{HORIZONTAL_SEPARATOR_PATTERN}+"
    rf"{NAME_TOKEN_PATTERN})*){HORIZONTAL_SEPARATOR_PATTERN}+"
    rf"<(?P<email>{EMAIL_PART_PATTERN}@{EMAIL_PART_PATTERN})>"
    rf"{HORIZONTAL_SEPARATOR_PATTERN}*$",
    re.IGNORECASE,
)
HORIZONTAL_ONLY_PATTERN = re.compile(
    rf"^{HORIZONTAL_SEPARATOR_PATTERN}*$"
)
SAFE_TRAILER_TEXT_PATTERN = (
    r"[^\x00-\x08\x0a-\x1f\x7f-\x9f\u061c\u200e\u200f"
    r"\u2028\u2029\u202a-\u202e\u2066-\u2069]*"
)
BIDI_CONTROL_PATTERN = re.compile(
    r"[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]"
)
TRAILER_TOKEN_PATTERN = r"-*[A-Za-z0-9][A-Za-z0-9-]*"
TRAILER_TOKEN_FULL_PATTERN = re.compile(rf"^{TRAILER_TOKEN_PATTERN}$")
TRAILER_LINE_PATTERN = re.compile(
    rf"^(?P<token>{TRAILER_TOKEN_PATTERN})[ \t]*:"
    rf"(?P<value>{SAFE_TRAILER_TEXT_PATTERN})$"
)
CONTINUATION_LINE_PATTERN = re.compile(
    rf"^{HORIZONTAL_SEPARATOR_PATTERN}+{SAFE_TRAILER_TEXT_PATTERN}$"
)
POTENTIAL_TRAILER_LINE_PATTERN = re.compile(
    rf"^{TRAILER_TOKEN_PATTERN}(?:{HORIZONTAL_SEPARATOR_PATTERN}|"
    r"[\x00-\x08\x0a-\x1f\x7f-\x9f\u2028\u2029])*:"
)
HORIZONTAL_PREFIX_PATTERN = re.compile(
    rf"^{HORIZONTAL_SEPARATOR_PATTERN}"
)

# Git's mixed-group heuristic recognizes this exact generated prefix. Project
# DCO matching is intentionally broader and is applied only after admission.
GIT_RECOGNIZED_SIGNOFF_PREFIX = "Signed-off-by: "


class DcoContractError(RuntimeError):
    """Raised when the API response cannot prove complete DCO coverage."""


DcoError = DcoContractError


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DcoContractError(message)


def require_sha(value: object, label: str) -> str:
    require(
        isinstance(value, str) and bool(SHA_PATTERN.fullmatch(value)),
        f"{label} is invalid",
    )
    return value


def _validate_sha(value: str, *, label: str) -> str:
    if not SHA_PATTERN.fullmatch(value):
        raise DcoContractError(f"{label} was not a full lowercase commit SHA")
    return value


def _request_json(
    url: str,
    token: str,
    *,
    resource: str,
    opener: Any = None,
) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
        },
    )
    open_request = opener or urlopen

    try:
        with open_request(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", None)
            if status is None and hasattr(response, "getcode"):
                status = response.getcode()
            if status != 200:
                raise DcoContractError(
                    f"{resource} retrieval failed with HTTP status {status}"
                )
            body = response.read()
    except DcoContractError:
        raise
    except (OSError, TimeoutError, URLError) as exc:
        raise DcoContractError(f"{resource} retrieval failed: {exc}") from exc

    try:
        return json.loads(body.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DcoContractError(f"{resource} response was not valid JSON") from exc


def fetch_pr_metadata(
    api_url: str,
    repository: str,
    pr_number: int,
    token: str,
    expected_head_sha: str,
    *,
    expected_base_sha: str | None = None,
    opener: Any = None,
) -> tuple[int, str, str]:
    """Retrieve an authoritative commit count bound to the expected PR tips."""
    expected_head_sha = _validate_sha(
        expected_head_sha,
        label="expected pull-request head",
    )
    if expected_base_sha is not None:
        expected_base_sha = _validate_sha(
            expected_base_sha,
            label="expected pull-request base",
        )
    url = f"{api_url.rstrip('/')}/repos/{repository}/pulls/{pr_number}"
    payload = _request_json(
        url,
        token,
        resource="pull-request metadata",
        opener=opener,
    )

    if not isinstance(payload, dict):
        raise DcoContractError("pull-request metadata response was not an object")

    declared_count = payload.get("commits")
    if (
        isinstance(declared_count, bool)
        or not isinstance(declared_count, int)
        or declared_count <= 0
    ):
        raise DcoContractError(
            "pull-request metadata did not declare a positive integer commit count"
        )

    head = payload.get("head")
    head_sha = head.get("sha") if isinstance(head, dict) else None
    if not isinstance(head_sha, str) or not SHA_PATTERN.fullmatch(head_sha):
        raise DcoContractError(
            "pull-request metadata did not declare a valid head SHA"
        )
    if head_sha != expected_head_sha:
        raise DcoContractError(
            "pull-request head mismatch: "
            f"metadata returned {head_sha}, expected {expected_head_sha}"
        )
    base = payload.get("base")
    base_sha = base.get("sha") if isinstance(base, dict) else None
    if not isinstance(base_sha, str) or not SHA_PATTERN.fullmatch(base_sha):
        raise DcoContractError(
            "pull-request metadata did not declare a valid base SHA"
        )
    if expected_base_sha is not None and base_sha != expected_base_sha:
        raise DcoContractError(
            "pull-request base mismatch: "
            f"metadata returned {base_sha}, expected {expected_base_sha}"
        )
    if declared_count > MAX_PULL_REQUEST_COMMITS:
        raise DcoContractError(
            f"pull request declares {declared_count} commits; "
            f"the pull-request commits endpoint is capped at "
            f"{MAX_PULL_REQUEST_COMMITS}, so complete DCO coverage cannot be proven"
        )

    return declared_count, head_sha, base_sha


def fetch_pr_commits(
    api_url: str,
    repository: str,
    pr_number: int,
    token: str,
    declared_count: int,
    *,
    opener: Any = None,
) -> list[dict[str, Any]]:
    """Retrieve exactly the declared commits and prove the page boundary is empty."""
    if (
        isinstance(declared_count, bool)
        or not isinstance(declared_count, int)
        or declared_count <= 0
        or declared_count > MAX_PULL_REQUEST_COMMITS
    ):
        raise DcoContractError("declared commit count is outside the supported range")

    commits: list[dict[str, Any]] = []
    seen_shas: set[str] = set()
    page_count = (declared_count + COMMITS_PER_PAGE - 1) // COMMITS_PER_PAGE
    endpoint = f"{api_url.rstrip('/')}/repos/{repository}/pulls/{pr_number}/commits"

    for page in range(1, page_count + 1):
        payload = _request_json(
            f"{endpoint}?per_page={COMMITS_PER_PAGE}&page={page}",
            token,
            resource=f"pull-request commits page {page}",
            opener=opener,
        )
        if not isinstance(payload, list):
            raise DcoContractError(
                f"pull-request commits page {page} response was not a list"
            )

        expected_page_size = min(
            COMMITS_PER_PAGE,
            declared_count - len(commits),
        )
        if len(payload) != expected_page_size:
            raise DcoContractError(
                "pull-request commit count mismatch: "
                f"page {page} returned {len(payload)} commits, "
                f"expected {expected_page_size}"
            )
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                raise DcoContractError(
                    f"pull-request commits page {page} entry {index} was not an object"
                )
            sha = item.get("sha")
            if not isinstance(sha, str) or not SHA_PATTERN.fullmatch(sha):
                raise DcoContractError(
                    f"pull-request commits page {page} entry {index} had an invalid SHA"
                )
            if sha in seen_shas:
                raise DcoContractError(
                    f"pull-request commits response contained duplicate SHA {sha}"
                )
            seen_shas.add(sha)
            commits.append(item)

    boundary_page = page_count + 1
    boundary_payload = _request_json(
        f"{endpoint}?per_page={COMMITS_PER_PAGE}&page={boundary_page}",
        token,
        resource=f"pull-request commits boundary page {boundary_page}",
        opener=opener,
    )
    if not isinstance(boundary_payload, list):
        raise DcoContractError(
            f"pull-request commits boundary page {boundary_page} response was not a list"
        )
    if boundary_payload:
        raise DcoContractError(
            "pull-request commit count mismatch: "
            f"boundary page {boundary_page} unexpectedly returned "
            f"{len(boundary_payload)} commits"
        )
    if len(commits) != declared_count:
        raise DcoContractError(
            "pull-request commit count mismatch: "
            f"retrieved {len(commits)}, metadata declared {declared_count}"
        )

    return commits


def fetch_authoritative_pr_commits(
    api_url: str,
    repository: str,
    pr_number: int,
    token: str,
    expected_head_sha: str,
    *,
    expected_base_sha: str | None = None,
    opener: Any = None,
) -> tuple[int, list[dict[str, Any]]]:
    """Bind complete pagination to stable metadata and exact event tips."""
    expected_head_sha = _validate_sha(
        expected_head_sha,
        label="expected pull-request head",
    )
    if expected_base_sha is not None:
        expected_base_sha = _validate_sha(
            expected_base_sha,
            label="expected pull-request base",
        )
    declared_count, initial_head_sha, initial_base_sha = fetch_pr_metadata(
        api_url,
        repository,
        pr_number,
        token,
        expected_head_sha,
        expected_base_sha=expected_base_sha,
        opener=opener,
    )
    commits = fetch_pr_commits(
        api_url,
        repository,
        pr_number,
        token,
        declared_count,
        opener=opener,
    )
    final_count, final_head_sha, final_base_sha = fetch_pr_metadata(
        api_url,
        repository,
        pr_number,
        token,
        expected_head_sha,
        expected_base_sha=expected_base_sha,
        opener=opener,
    )
    if (
        final_count != declared_count
        or final_head_sha != initial_head_sha
        or final_base_sha != initial_base_sha
    ):
        raise DcoContractError(
            "pull-request metadata drifted during commit retrieval: "
            f"initial base/head/count "
            f"{initial_base_sha}/{initial_head_sha}/{declared_count}, "
            f"final base/head/count {final_base_sha}/{final_head_sha}/{final_count}"
        )
    if len(commits) != declared_count:
        raise DcoContractError(
            "pull-request commit count mismatch after retrieval: "
            f"retrieved {len(commits)}, metadata declared {declared_count}"
        )
    retrieved_head_sha = commits[-1]["sha"]
    if retrieved_head_sha != expected_head_sha:
        raise DcoContractError(
            "pull-request retrieved head mismatch: "
            f"final commit was {retrieved_head_sha}, expected {expected_head_sha}"
        )
    return declared_count, commits


def _is_horizontal_blank(line: str) -> bool:
    """Return whether a physical line is blank under the audited grammar."""
    return HORIZONTAL_ONLY_PATTERN.fullmatch(line) is not None


def _is_patch_divider(lines: list[str], index: int) -> bool:
    """Apply the audited physical-line boundary for a Git patch divider."""
    line = lines[index]
    if PATCH_DIVIDER_PATTERN.match(line) is None:
        return False
    if line != "---":
        return True

    # split("\n") leaves one terminal empty element for a final line ending;
    # that is not a physical line following the exact marker. Two line endings
    # do create a following empty physical line. A terminal exact marker must
    # remain message text so it cannot erase an invalid final postscript.
    remaining = lines[index + 1 :]
    return bool(remaining and remaining != [""])


def _final_nonblank_group(message: str) -> list[str]:
    """Return the complete final nonblank group after a body boundary."""
    lines = message.split("\n")
    divider_index = next(
        (
            index
            for index, line in enumerate(lines)
            if _is_patch_divider(lines, index)
        ),
        None,
    )
    if divider_index is not None:
        # Git starts the patch area at the first column-zero `---` followed by
        # space, tab, CR, or end-of-line; trailers there are not in the message.
        lines = lines[:divider_index]
    while lines and _is_horizontal_blank(lines[-1]):
        lines.pop()
    if not lines:
        return []

    boundary_index = next(
        (
            index
            for index in range(len(lines) - 1, -1, -1)
            if _is_horizontal_blank(lines[index])
        ),
        None,
    )
    if boundary_index is None:
        return []

    final_paragraph = lines[boundary_index + 1 :]
    if not final_paragraph:
        return []
    return final_paragraph


def _admitted_trailer_group(
    message: str,
) -> list[tuple[str, str | None, str]] | None:
    """Classify and admit the complete final group using Git's counters."""
    final_group = _final_nonblank_group(message)
    if not final_group:
        return None

    classified_lines: list[tuple[str, str | None, str]] = []
    current_token: str | None = None
    trailer_count = 0
    non_trailer_count = 0
    has_recognized_prefix = False

    for line in final_group:
        if BIDI_CONTROL_PATTERN.search(line):
            current_token = None
            non_trailer_count += 1
            classified_lines.append(("malformed", None, line))
            continue

        if CONTINUATION_LINE_PATTERN.fullmatch(line):
            if current_token is None:
                non_trailer_count += 1
                classified_lines.append(("orphan-continuation", None, line))
            else:
                classified_lines.append(("continuation", current_token, line))
            continue

        trailer_match = TRAILER_LINE_PATTERN.fullmatch(line)
        if trailer_match is not None:
            current_token = trailer_match.group("token").lower()
            trailer_count += 1
            has_recognized_prefix = (
                has_recognized_prefix
                or line.startswith(GIT_RECOGNIZED_SIGNOFF_PREFIX)
            )
            classified_lines.append(("trailer", current_token, line))
            continue

        if (
            POTENTIAL_TRAILER_LINE_PATTERN.match(line)
            or HORIZONTAL_PREFIX_PATTERN.match(line)
        ):
            current_token = None
            non_trailer_count += 1
            classified_lines.append(("malformed", None, line))
            continue

        current_token = None
        non_trailer_count += 1
        classified_lines.append(("body", None, line))

    if trailer_count == 0:
        return None
    if non_trailer_count and (
        not has_recognized_prefix
        or trailer_count * 4 < trailer_count + non_trailer_count
    ):
        return None

    return classified_lines


def valid_dco_identities(message: str) -> set[tuple[str, str]]:
    """Return exact identities from a valid physical-line DCO trailer block."""
    classified_lines = _admitted_trailer_group(message)
    if classified_lines is None:
        return set()

    identities: set[tuple[str, str]] = set()
    current_token = None
    for line_kind, token, line in classified_lines:
        if line_kind == "body":
            current_token = None
            continue
        if line_kind in {"orphan-continuation", "malformed"}:
            return set()
        if line_kind == "continuation":
            if current_token is None or current_token == "signed-off-by":
                return set()
            continue

        current_token = token
        if current_token == "signed-off-by":
            signoff_match = SIGNED_OFF_BY_PATTERN.fullmatch(line)
            if signoff_match is None:
                return set()
            identities.add(
                (signoff_match.group("name"), signoff_match.group("email"))
            )

    return identities


def has_valid_dco_trailer(message: str) -> bool:
    """Admit Git-compatible trailers, then apply stricter project DCO rules."""
    return bool(valid_dco_identities(message))


def unsigned_commit_shas(commits: list[dict[str, Any]]) -> list[str]:
    """Return every commit that lacks a syntactically valid DCO trailer."""
    unsigned: list[str] = []

    for index, item in enumerate(commits, start=1):
        if not isinstance(item, dict):
            raise DcoContractError(f"commit entry {index} was not an object")
        sha = item.get("sha")
        commit = item.get("commit")
        if not isinstance(sha, str) or not SHA_PATTERN.fullmatch(sha):
            raise DcoContractError(f"commit entry {index} had an invalid SHA")
        if not isinstance(commit, dict) or not isinstance(commit.get("message"), str):
            raise DcoContractError(f"commit {sha} had no valid commit message")
        author = commit.get("author")
        if not isinstance(author, dict):
            raise DcoContractError(f"commit {sha} had no valid author identity")
        author_name = author.get("name")
        author_email = author.get("email")
        if not isinstance(author_name, str) or not isinstance(author_email, str):
            raise DcoContractError(f"commit {sha} had no valid author identity")
        identities = valid_dco_identities(commit["message"])
        if (author_name, author_email) not in identities:
            unsigned.append(sha)

    return unsigned


def git(
    repo: Path,
    *args: str,
    input_text: str | None = None,
    check: bool = True,
) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo,
            input=input_text,
            text=True,
            encoding="utf-8",
            errors="strict",
            capture_output=True,
            check=False,
            timeout=30,
        )
    except UnicodeError as exc:
        raise DcoContractError("git output was not valid UTF-8") from exc
    if check and completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise DcoContractError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def git_bytes(repo: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=False,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode:
        raise DcoContractError(f"git {args[0]} failed")
    return completed.stdout


def commit_record(repo: Path, sha: str) -> tuple[list[str], str, str, str]:
    require_sha(sha, "commit SHA")
    raw_bytes = git_bytes(repo, "cat-file", "commit", sha)
    try:
        raw = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise DcoContractError("commit object was not valid UTF-8") from exc

    headers, separator, message = raw.partition("\n\n")
    require(bool(separator), f"commit object is incomplete for {sha}")
    message = message.replace("\r\n", "\n")
    require("\r" not in message, f"commit message has unsupported line endings for {sha}")

    parents: list[str] = []
    author: tuple[str, str] | None = None
    tree_seen = False
    committer_seen = False
    encoding_seen = False
    current_header: str | None = None
    for line in headers.split("\n"):
        if line.startswith(" "):
            require(current_header is not None, f"commit headers are malformed for {sha}")
            continue

        key, delimiter, value = line.partition(" ")
        require(bool(delimiter and key and value), f"commit headers are malformed for {sha}")
        current_header = key
        if key == "tree":
            require(not tree_seen, f"commit has duplicate tree headers for {sha}")
            require_sha(value, "commit tree SHA")
            tree_seen = True
        elif key == "parent":
            parents.append(require_sha(value, "commit parent SHA"))
        elif key == "author":
            require(author is None, f"commit has duplicate author headers for {sha}")
            match = re.fullmatch(
                r"(?P<name>.+) <(?P<email>[^<>]+)> -?[0-9]+ [+-][0-9]{4}",
                value,
            )
            require(match is not None, f"commit author header is malformed for {sha}")
            author = (match.group("name"), match.group("email"))
        elif key == "committer":
            require(not committer_seen, f"commit has duplicate committer headers for {sha}")
            committer_seen = True
        elif key == "encoding":
            require(not encoding_seen, f"commit has duplicate encoding headers for {sha}")
            require(value.casefold() == "utf-8", "commit encoding must be UTF-8")
            encoding_seen = True

    require(tree_seen, f"commit has no tree header for {sha}")
    require(author is not None, f"commit has no author header for {sha}")
    require(committer_seen, f"commit has no committer header for {sha}")
    return parents, author[0], author[1], message


def validate_commit(
    repo: Path,
    sha: str,
    *,
    allow_merge_commit: bool = False,
) -> None:
    parents, author_name, author_email, message = commit_record(repo, sha)
    allowed_parent_counts = {1, 2} if allow_merge_commit else {1}
    require(
        len(parents) in allowed_parent_counts,
        f"{sha} has an unsupported parent count: {len(parents)}",
    )
    identities = valid_dco_identities(message)
    require(identities, f"{sha} has no valid terminal Signed-off-by trailer")
    require(
        (author_name, author_email) in identities,
        f"{sha} Signed-off-by does not exactly match the commit author",
    )


def checked_out_head(repo: Path) -> str:
    return require_sha(git(repo, "rev-parse", "HEAD").strip(), "checked-out HEAD")


def validate_commits(
    repo: Path,
    shas: list[str],
    expected_head: str,
    *,
    allow_merge_commits: bool = False,
    checked_out_head_sha: str | None = None,
) -> int:
    require(shas, "candidate commit set is empty")
    require(len(shas) == len(set(shas)), "candidate commit set contains duplicate SHAs")
    require(shas[-1] == expected_head, "last candidate commit does not match expected head")
    expected_checkout = checked_out_head_sha or expected_head
    require(
        checked_out_head(repo) == expected_checkout,
        "checked-out HEAD does not match expected head",
    )
    for sha in shas:
        validate_commit(repo, sha, allow_merge_commit=allow_merge_commits)
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
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    request = Request(
        api_url + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "szl-dco-attestor/2",
            "X-GitHub-Api-Version": API_VERSION,
        },
    )
    with urlopen(request, timeout=20) as response:
        require(response.status == 200, f"GitHub API returned HTTP {response.status}")
        require(response.geturl().startswith(api_url + "/"), "GitHub API redirected")
        data = response.read(2_000_001)
    require(len(data) <= 2_000_000, "GitHub API response is too large")
    return json.loads(data)


def collect_pr_commits(
    repository: str,
    number: int,
    expected_base: str,
    expected_head: str,
    api_get: Callable[[str], Any],
    *,
    allow_draft: bool = False,
) -> list[str]:
    expected_base = require_sha(expected_base, "pull-request base SHA")
    expected_head = require_sha(expected_head, "pull-request head SHA")
    encoded_repo = quote(repository, safe="/")
    metadata_path = f"/repos/{encoded_repo}/pulls/{number}"

    def stable_metadata() -> int:
        current = api_get(metadata_path)
        require(isinstance(current, dict), "pull-request metadata is not an object")
        base = current.get("base")
        head = current.get("head")
        require(isinstance(base, dict) and isinstance(head, dict), "pull-request refs are missing")
        require(base.get("sha") == expected_base, "pull-request base moved during validation")
        require(head.get("sha") == expected_head, "pull-request head moved during validation")
        declared = current.get("commits")
        require(
            isinstance(declared, int)
            and not isinstance(declared, bool)
            and 0 < declared <= MAX_PULL_REQUEST_COMMITS,
            "pull-request commit count is outside the supported range",
        )
        draft = current.get("draft")
        require(isinstance(draft, bool), "pull-request draft state is not boolean")
        require(allow_draft or not draft, "draft pull requests cannot satisfy DCO")
        return declared

    declared_count = stable_metadata()
    rows: list[dict[str, Any]] = []
    page_count = (declared_count + COMMITS_PER_PAGE - 1) // COMMITS_PER_PAGE
    endpoint = f"/repos/{encoded_repo}/pulls/{number}/commits"
    for page in range(1, page_count + 1):
        batch = api_get(f"{endpoint}?per_page={COMMITS_PER_PAGE}&page={page}")
        require(isinstance(batch, list), "pull-request commit page is not an array")
        expected_size = min(COMMITS_PER_PAGE, declared_count - len(rows))
        require(
            len(batch) == expected_size,
            "pull-request commit page differs from the declared count",
        )
        require(all(isinstance(item, dict) for item in batch), "commit page row is invalid")
        rows.extend(batch)
    boundary = api_get(
        f"{endpoint}?per_page={COMMITS_PER_PAGE}&page={page_count + 1}"
    )
    require(
        isinstance(boundary, list) and not boundary,
        "pull-request commit boundary page was not empty",
    )
    require(
        stable_metadata() == declared_count,
        "pull-request commit count changed during validation",
    )
    shas = [require_sha(item.get("sha"), "pull-request commit SHA") for item in rows]
    require(len(shas) == len(set(shas)), "retrieved commits contain duplicate SHAs")
    require(shas and shas[-1] == expected_head, "retrieved commits do not end at expected head")
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
    require(
        head_sha == require_sha(github_sha, "GITHUB_SHA"),
        "merge_group head differs from GITHUB_SHA",
    )
    return base_sha, head_sha


def validate_merge_group(repo: Path, base_sha: str, head_sha: str) -> int:
    base_sha = require_sha(base_sha, "merge-group base SHA")
    head_sha = require_sha(head_sha, "merge-group head SHA")
    require(checked_out_head(repo) == head_sha, "checked-out HEAD does not match merge-group head")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_sha, head_sha],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    require(ancestor.returncode == 0, "merge-group base SHA is not an ancestor of head SHA")
    range_shas = [
        line.strip()
        for line in git(repo, "rev-list", "--reverse", f"{base_sha}..{head_sha}").splitlines()
        if line.strip()
    ]
    require(range_shas and range_shas[-1] == head_sha, "merge-group range does not end at head")
    require(
        len(range_shas) == len(set(range_shas)),
        "merge-group range contains duplicate SHAs",
    )
    previous_sha = base_sha
    for sha in range_shas:
        parents, _, author_email, message = commit_record(repo, sha)
        require(
            parents == [previous_sha],
            "merge-group range is not a linear single-parent squash sequence",
        )
        identities = valid_dco_identities(message)
        require(
            identities,
            f"{sha} has no valid terminal Signed-off-by trailer",
        )
        # GitHub creates merge-queue squash commits on a protected temporary
        # ref and can canonicalize the account display name independently of
        # the exact source-commit author name. The source commits retain the
        # stricter name-and-email check above; only this provider-generated
        # merge_group path accepts an exact, case-sensitive author-email match.
        require(
            any(identity_email == author_email for _, identity_email in identities),
            f"{sha} Signed-off-by email does not exactly match "
            "the merge-group commit author email",
        )
        previous_sha = sha
    return len(range_shas)


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
    *,
    expected_base_sha: str | None = None,
    expected_head_sha: str | None = None,
    allow_draft: bool = False,
) -> int:
    require(payload.get("action") in ALLOWED_PR_ACTIONS, "pull-request action is unsupported")
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
    base_ref = base.get("ref")
    require(
        base_ref == "main"
        or (
            isinstance(base_ref, str)
            and base_ref.startswith("release/")
            and len(base_ref) > len("release/")
            and "/" not in base_ref[len("release/") :]
        ),
        "pull-request base ref is not governed",
    )
    base_sha = require_sha(base.get("sha"), "pull-request base SHA")
    head_sha = require_sha(head.get("sha"), "pull-request head SHA")
    if expected_base_sha is not None:
        require(
            base_sha == require_sha(expected_base_sha, "expected pull-request base SHA"),
            "pull-request base differs from EXPECTED_BASE_SHA",
        )
    if expected_head_sha is not None:
        require(
            head_sha == require_sha(expected_head_sha, "expected pull-request head SHA"),
            "pull-request head differs from EXPECTED_HEAD_SHA",
        )
    number = pr.get("number") or payload.get("number")
    require(isinstance(number, int) and number > 0, "pull-request number is invalid")
    require(bool(token), "GITHUB_TOKEN is required for trusted PR validation")
    getter = api_get or (lambda path: github_get(path, token))
    shas = collect_pr_commits(
        repository,
        number,
        base_sha,
        head_sha,
        getter,
        allow_draft=allow_draft,
    )
    require(checked_out_head(repo) == head_sha, "checked-out HEAD does not match event head")
    merge_base = require_sha(
        git(repo, "merge-base", base_sha, head_sha).strip(),
        "pull-request merge base",
    )
    local_shas = [
        line.strip()
        for line in git(repo, "rev-list", "--reverse", f"{merge_base}..{head_sha}").splitlines()
        if line.strip()
    ]
    require(
        local_shas == shas,
        "pull-request API commit set differs from the checked-out history",
    )
    return validate_commits(repo, shas, head_sha, allow_merge_commits=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--event-path", type=Path, required=True)
    parser.add_argument(
        "--allow-draft",
        action="store_true",
        help="validate DCO on draft PRs when GitHub cannot dispatch ready_for_review",
    )
    return parser.parse_args()


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise DcoContractError(f"required environment variable {name} is empty")
    return value


def main() -> int:
    try:
        args = parse_args()
        payload = json.loads(args.event_path.read_text(encoding="utf-8"))
        require(isinstance(payload, dict), "event payload must be an object")
        event_name = _required_environment("GITHUB_EVENT_NAME")
        github_sha = _required_environment("GITHUB_SHA")
        repository = _required_environment("GITHUB_REPOSITORY")
        repo = args.repo_root.resolve()

        if event_name in {"pull_request_target", "pull_request"}:
            count = validate_pull_request_target(
                repo,
                payload,
                repository,
                _required_environment("GITHUB_TOKEN"),
                expected_base_sha=_required_environment("EXPECTED_BASE_SHA"),
                expected_head_sha=_required_environment("EXPECTED_HEAD_SHA"),
                allow_draft=args.allow_draft,
            )
        elif event_name == "merge_group":
            base_sha, head_sha = merge_group_subject(payload, github_sha)
            count = validate_merge_group(repo, base_sha, head_sha)
        elif event_name == "push":
            base_sha, head_sha = push_subject(payload, github_sha)
            count = validate_range(repo, base_sha, head_sha)
        else:
            raise DcoContractError(f"unsupported event: {event_name!r}")

        print(f"DCO OK: validated {count} exact commit(s) for {event_name}")
        return 0
    except (DcoContractError, json.JSONDecodeError, OSError) as exc:
        print(f"DCO FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
