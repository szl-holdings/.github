#!/usr/bin/env python3
"""Fail closed unless one live GitHub PR still has the exact admitted pair."""

from __future__ import annotations

import http.client
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
MAX_RESPONSE_BYTES = 1024 * 1024


class LivePRPairError(RuntimeError):
    """The live pull-request identity cannot satisfy exact admission."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LivePRPairError(f"GitHub API redirect is forbidden: HTTP {code}")


def _required(environment: dict[str, str], name: str) -> str:
    value = str(environment.get(name) or "")
    if not value:
        raise LivePRPairError(f"required environment variable is empty: {name}")
    return value


def _canonical_repository(value: str) -> str:
    parts = str(value or "").split("/")
    if (
        len(parts) != 2
        or any(part in {"", ".", ".."} for part in parts)
        or any(REPOSITORY_SEGMENT_RE.fullmatch(part) is None for part in parts)
    ):
        raise LivePRPairError("GITHUB_REPOSITORY is not a canonical owner/repository")
    return "/".join(parts)


def _reject_json_constant(value: str) -> None:
    del value
    raise LivePRPairError("GitHub API response contains an invalid JSON constant")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LivePRPairError("GitHub API response has a duplicate object key")
        result[key] = value
    return result


def _field(mapping: Any, *path: str) -> Any:
    current = mapping
    for component in path:
        if not isinstance(current, dict) or component not in current:
            raise LivePRPairError(
                "GitHub API response is missing required field: " + ".".join(path)
            )
        current = current[component]
    return current


def validate_live_pr_pair(
    environment: dict[str, str],
    *,
    opener: Any | None = None,
) -> dict[str, Any]:
    api_url = _required(environment, "GITHUB_API_URL").rstrip("/")
    if api_url != "https://api.github.com":
        raise LivePRPairError("GITHUB_API_URL must be exactly https://api.github.com")
    repository = _canonical_repository(_required(environment, "GITHUB_REPOSITORY"))
    token = _required(environment, "GITHUB_TOKEN")
    pr_number = _required(environment, "PR_NUMBER")
    if not pr_number.isascii() or not pr_number.isdecimal() or int(pr_number) <= 0:
        raise LivePRPairError("PR_NUMBER must be a positive decimal integer")
    if str(int(pr_number)) != pr_number:
        raise LivePRPairError("PR_NUMBER must use canonical decimal form")

    expected_base_repo = _required(environment, "EXPECTED_BASE_REPO")
    expected_head_repo = _required(environment, "EXPECTED_HEAD_REPO")
    expected_base_ref = _required(environment, "EXPECTED_BASE_REF")
    expected_base_sha = _required(environment, "EXPECTED_BASE_SHA")
    expected_head_sha = _required(environment, "EXPECTED_HEAD_SHA")
    if expected_base_repo != repository or expected_head_repo != repository:
        raise LivePRPairError("expected PR repositories must equal GITHUB_REPOSITORY")
    for label, value in (
        ("EXPECTED_BASE_SHA", expected_base_sha),
        ("EXPECTED_HEAD_SHA", expected_head_sha),
    ):
        if SHA_RE.fullmatch(value) is None:
            raise LivePRPairError(f"{label} must be an exact lowercase Git SHA")

    request = urllib.request.Request(
        f"{api_url}/repos/{repository}/pulls/{pr_number}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "szl-hf-candidate-plan-live-pair/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    client = opener or urllib.request.build_opener(_NoRedirect())
    try:
        with client.open(request, timeout=20) as response:
            status = getattr(response, "status", response.getcode())
            if type(status) is not int:
                raise LivePRPairError("GitHub API returned a non-integer HTTP status")
            if status != 200:
                raise LivePRPairError(
                    f"GitHub API returned unexpected HTTP status: {status}"
                )
            content_type = str(response.headers.get("Content-Type") or "")
            media_type = content_type.partition(";")[0].strip().casefold()
            if media_type != "application/json":
                raise LivePRPairError("GitHub API returned a non-JSON content type")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except LivePRPairError:
        raise
    except urllib.error.HTTPError as exc:
        raise LivePRPairError(
            f"GitHub API request failed closed: HTTP {int(exc.code)}"
        ) from exc
    except urllib.error.URLError as exc:
        raise LivePRPairError(
            "GitHub API request failed closed: transport error"
        ) from exc
    except http.client.HTTPException as exc:
        raise LivePRPairError(
            "GitHub API request failed closed: HTTP protocol error"
        ) from exc
    except OSError as exc:
        raise LivePRPairError("GitHub API request failed closed: I/O error") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise LivePRPairError("GitHub API response exceeds the 1 MiB bound")
    try:
        text = raw.decode("utf-8")
        payload = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LivePRPairError("GitHub API response is not strict UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise LivePRPairError("GitHub API response root must be an object")

    actual = {
        "number": _field(payload, "number"),
        "state": _field(payload, "state"),
        "merged": _field(payload, "merged"),
        "base_repo": _field(payload, "base", "repo", "full_name"),
        "head_repo": _field(payload, "head", "repo", "full_name"),
        "base_ref": _field(payload, "base", "ref"),
        "base_sha": _field(payload, "base", "sha"),
        "head_sha": _field(payload, "head", "sha"),
    }
    expected = {
        "number": int(pr_number),
        "state": "open",
        "merged": False,
        "base_repo": expected_base_repo,
        "head_repo": expected_head_repo,
        "base_ref": expected_base_ref,
        "base_sha": expected_base_sha,
        "head_sha": expected_head_sha,
    }
    expected_types = {
        "number": int,
        "state": str,
        "merged": bool,
        "base_repo": str,
        "head_repo": str,
        "base_ref": str,
        "base_sha": str,
        "head_sha": str,
    }
    for key, expected_value in expected.items():
        if type(actual[key]) is not expected_types[key]:
            raise LivePRPairError(f"live pull-request field has the wrong type: {key}")
        if actual[key] != expected_value:
            raise LivePRPairError(f"live pull-request field mismatch: {key}")
    return actual


def main() -> int:
    try:
        actual = validate_live_pr_pair(dict(os.environ))
    except LivePRPairError:
        print(
            "::error title=HF candidate live PR binding::"
            "live pull-request identity revalidation failed closed",
            file=sys.stderr,
        )
        return 1
    print(
        "Live pull-request pair is exact: "
        f"#{actual['number']} {actual['base_sha']} -> {actual['head_sha']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
