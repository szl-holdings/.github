#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed GitHub HTTP and organization-reader selection for CI health.

A credential is selected only after it proves the complete organization
inventory against GitHub's authoritative public/private repository totals and
can read Actions metadata. Candidate values are never included in receipts.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

ORG = "szl-holdings"
TRANSIENT_HTTP = {429, 500, 502, 503, 504}
CANDIDATE_ENVIRONMENT = (
    ("github_app", "qillqaq_app_installation", "DIGEST_APP_TOKEN"),
    ("governed_pat_fallback", "ORG_REPO_WORKFLOW_TOKEN", "ORG_REPO_WORKFLOW_TOKEN"),
    ("governed_pat_fallback", "SZL_ORG_PAT", "SZL_ORG_PAT"),
    ("governed_pat_fallback", "SZL_GITHUB_PAT", "SZL_GITHUB_PAT"),
    ("governed_pat_fallback", "GH_PAT", "GH_PAT"),
    ("governed_pat_fallback", "PAT_TOKEN", "PAT_TOKEN"),
    ("governed_pat_fallback", "GITHUB_PAT", "GITHUB_PAT"),
    ("governed_pat_fallback", "GH_TOKEN", "GH_TOKEN"),
    ("governed_pat_fallback", "SZL_GITHUB_TOKEN", "SZL_GITHUB_TOKEN"),
    ("repository_token_probe", "repository_github_token", "REPOSITORY_GITHUB_TOKEN"),
)


class DigestError(RuntimeError):
    """Raised when current, complete CI-health evidence cannot be proved."""


class ReaderSelectionError(DigestError):
    def __init__(self, attempts: Sequence[Mapping[str, Any]]) -> None:
        self.attempts = tuple(dict(item) for item in attempts)
        super().__init__(
            "no governed organization reader could prove complete repository "
            "and Actions coverage"
        )


class ApiError(DigestError):
    def __init__(self, *, operation: str, status: int, detail_class: str) -> None:
        super().__init__(
            f"GitHub API operation {operation!r} failed: "
            f"HTTP {status} ({detail_class})"
        )
        self.operation = operation
        self.status = status
        self.detail_class = detail_class


@dataclass(frozen=True)
class ReaderSelection:
    mode: str
    credential_name: str
    token: str = field(repr=False)
    repositories: tuple[dict[str, Any], ...]
    attempts: tuple[dict[str, Any], ...]


def classify_http_detail(value: object) -> str:
    text = str(value or "").lower()
    if "bad credentials" in text or "requires authentication" in text:
        return "unauthenticated"
    if "resource not accessible" in text or "forbidden" in text:
        return "unauthorized"
    if "rate limit" in text:
        return "rate_limited"
    if "not found" in text:
        return "not_found_or_hidden"
    if not text:
        return "empty_error_body"
    return "api_error"


def request_json(
    token: str,
    url: str,
    *,
    method: str = "GET",
    body: Mapping[str, Any] | None = None,
    operation: str,
    expected: set[int] | None = None,
    attempts: int = 4,
) -> tuple[int, Any]:
    if not token:
        raise DigestError(f"no credential supplied for {operation}")
    expected = expected or {200}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "szl-ci-health-digest/3",
    }
    last_status = 0
    last_detail = "request_failed"
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                status = int(response.status)
                raw = response.read()
                payload = json.loads(raw) if raw else {}
                if status not in expected:
                    raise ApiError(
                        operation=operation,
                        status=status,
                        detail_class="unexpected_success_status",
                    )
                return status, payload
        except urllib.error.HTTPError as exc:
            last_status = int(exc.code)
            raw = exc.read()[:1000].decode("utf-8", errors="replace")
            last_detail = classify_http_detail(raw)
            if last_status in TRANSIENT_HTTP and attempt < attempts:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else 2 ** (attempt - 1)
                )
                time.sleep(min(delay, 15.0))
                continue
            raise ApiError(
                operation=operation,
                status=last_status,
                detail_class=last_detail,
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_status = 0
            last_detail = type(exc).__name__
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 15))
                continue
            raise ApiError(
                operation=operation,
                status=0,
                detail_class=last_detail,
            ) from exc
    raise ApiError(
        operation=operation,
        status=last_status,
        detail_class=last_detail,
    )


def repository_floor() -> int:
    value = str(os.environ.get("ORG_REPOSITORY_FLOOR") or "123").strip()
    try:
        floor = int(value)
    except ValueError as exc:
        raise DigestError(
            f"ORG_REPOSITORY_FLOOR is not an integer: {value!r}"
        ) from exc
    if floor < 1:
        raise DigestError("ORG_REPOSITORY_FLOOR must be positive")
    return floor


def _paginated_list(
    token: str,
    base_url: str,
    *,
    operation: str,
) -> tuple[dict[str, Any], ...]:
    values: list[dict[str, Any]] = []
    page = 1
    separator = "&" if "?" in base_url else "?"
    while True:
        _, payload = request_json(
            token,
            f"{base_url}{separator}per_page=100&page={page}",
            operation=f"{operation} page {page}",
        )
        if not isinstance(payload, list):
            raise DigestError(
                f"{operation} page {page} returned "
                f"{type(payload).__name__}, not a list"
            )
        for item in payload:
            if not isinstance(item, dict):
                raise DigestError(
                    f"{operation} page {page} contains a malformed entry"
                )
            values.append(item)
        if len(payload) < 100:
            return tuple(values)
        page += 1
        if page > 100:
            raise DigestError(f"{operation} exceeded 100 pages")


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DigestError(f"authoritative {label} repository total is unavailable")
    return value


def validate_authoritative_inventory(
    token: str,
    repositories: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Prove exact public/private inventory equality without admin-only coupling."""

    _, metadata = request_json(
        token,
        f"https://api.github.com/orgs/{ORG}",
        operation="read authoritative organization repository totals",
    )
    if not isinstance(metadata, dict):
        raise DigestError("organization metadata payload is malformed")

    public_total = _nonnegative_integer(metadata.get("public_repos"), "public")
    private_value = metadata.get("total_private_repos")
    if private_value is None:
        private_value = metadata.get("owned_private_repos")
    private_total = _nonnegative_integer(private_value, "private")
    authoritative_total = public_total + private_total
    floor = repository_floor()
    if authoritative_total < floor:
        raise DigestError(
            "authoritative organization total below reviewed floor: "
            f"observed={authoritative_total} floor={floor}"
        )

    identities: list[str] = []
    observed_private = 0
    for item in repositories:
        full_name = str(item.get("full_name") or "").strip()
        if not full_name.startswith(f"{ORG}/"):
            raise DigestError(
                f"organization inventory contains foreign or empty identity: {full_name!r}"
            )
        identities.append(full_name)
        if item.get("private") is True or item.get("visibility") in {
            "private",
            "internal",
        }:
            observed_private += 1

    if len(identities) != len(set(identities)):
        raise DigestError("organization inventory contains duplicate repositories")
    if len(repositories) != authoritative_total:
        raise DigestError(
            "organization repository listing does not match authoritative totals: "
            f"listed={len(repositories)} authoritative={authoritative_total}"
        )
    if observed_private != private_total:
        raise DigestError(
            "organization private repository listing does not match authoritative total: "
            f"listed={observed_private} authoritative={private_total}"
        )

    return {
        "public_repositories": public_total,
        "private_repositories": private_total,
        "repository_count": authoritative_total,
        "inventory_match": True,
    }


def list_repositories(token: str) -> tuple[dict[str, Any], ...]:
    repositories = list(
        _paginated_list(
            token,
            f"https://api.github.com/orgs/{ORG}/repos?type=all&sort=full_name&direction=asc",
            operation="list organization repositories",
        )
    )
    seen: set[str] = set()
    for item in repositories:
        name = str(item.get("name") or "").strip()
        full_name = str(item.get("full_name") or f"{ORG}/{name}").strip()
        if not name or not full_name:
            raise DigestError("organization repository entry has no identity")
        if full_name in seen:
            raise DigestError(
                f"duplicate repository returned by GitHub: {full_name}"
            )
        seen.add(full_name)

    floor = repository_floor()
    if len(repositories) < floor:
        raise DigestError(
            "organization repository coverage below reviewed floor: "
            f"observed={len(repositories)} floor={floor}"
        )
    active = [item for item in repositories if not item.get("archived")]
    if not active:
        raise DigestError("organization listing contains no active repositories")
    for item in active:
        if not str(item.get("default_branch") or "").strip():
            raise DigestError(
                f"active repository {item.get('name')!r} lacks a default branch"
            )
    validate_authoritative_inventory(token, repositories)
    return tuple(repositories)


def _candidate_values() -> tuple[tuple[str, str, str], ...]:
    values: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for mode, name, environment_name in CANDIDATE_ENVIRONMENT:
        token = str(os.environ.get(environment_name) or "").strip()
        if not token:
            values.append((mode, name, ""))
            continue
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        values.append((mode, name, token))
    return tuple(values)


def select_reader() -> ReaderSelection:
    attempts: list[dict[str, Any]] = []
    for mode, name, token in _candidate_values():
        if not token:
            attempts.append(
                {
                    "mode": mode,
                    "credential_name": name,
                    "present": False,
                    "result": "not_configured",
                    "value_recorded": False,
                }
            )
            continue
        try:
            repositories = list_repositories(token)
            active_probe = next(
                item for item in repositories if not item.get("archived")
            )
            _, actions_payload = request_json(
                token,
                (
                    f"https://api.github.com/repos/{ORG}/"
                    f"{active_probe['name']}/actions/workflows?per_page=1"
                ),
                operation=(
                    "probe Actions-read capability for "
                    f"{active_probe['name']}"
                ),
            )
            if not isinstance(actions_payload, dict) or not isinstance(
                actions_payload.get("workflows"), list
            ):
                raise DigestError(
                    "Actions-read capability probe returned a malformed payload"
                )
        except Exception as exc:  # noqa: BLE001
            attempts.append(
                {
                    "mode": mode,
                    "credential_name": name,
                    "present": True,
                    "result": "rejected",
                    "failure_type": type(exc).__name__,
                    "failure_class": (
                        exc.detail_class
                        if isinstance(exc, ApiError)
                        else "coverage_or_shape_failure"
                    ),
                    "value_recorded": False,
                }
            )
            continue
        attempts.append(
            {
                "mode": mode,
                "credential_name": name,
                "present": True,
                "result": "selected",
                "repository_count": len(repositories),
                "authoritative_inventory_match": True,
                "value_recorded": False,
            }
        )
        return ReaderSelection(
            mode=mode,
            credential_name=name,
            token=token,
            repositories=repositories,
            attempts=tuple(attempts),
        )
    raise ReaderSelectionError(attempts)
