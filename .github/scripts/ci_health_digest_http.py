#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed GitHub HTTP and organization-reader selection for CI health."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

ORG = "szl-holdings"
CANONICAL_CONFIG_ID = 252588
TRANSIENT_HTTP = {429, 500, 502, 503, 504}


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
    token: str
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
        "User-Agent": "szl-ci-health-digest/2",
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
    value = str(os.environ.get("ORG_REPOSITORY_FLOOR") or "57").strip()
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


def validate_canonical_inventory(
    token: str,
    repositories: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    _, configurations = request_json(
        token,
        f"https://api.github.com/orgs/{ORG}/code-security/configurations",
        operation="read organization code-security configurations",
    )
    if not isinstance(configurations, list):
        raise DigestError("code-security configuration inventory is malformed")
    canonical = next(
        (
            item
            for item in configurations
            if isinstance(item, dict)
            and item.get("id") == CANONICAL_CONFIG_ID
        ),
        None,
    )
    if canonical is None:
        raise DigestError(
            f"canonical code-security configuration {CANONICAL_CONFIG_ID} is missing"
        )
    if canonical.get("target_type") != "organization":
        raise DigestError(
            "canonical code-security configuration is not organization-scoped"
        )
    if canonical.get("enforcement") != "enforced":
        raise DigestError(
            "canonical code-security configuration is not enforced"
        )

    attachments = _paginated_list(
        token,
        (
            f"https://api.github.com/orgs/{ORG}/code-security/"
            f"configurations/{CANONICAL_CONFIG_ID}/repositories"
        ),
        operation="read canonical code-security repository inventory",
    )
    attached_status: dict[str, str | None] = {}
    for item in attachments:
        repository = item.get("repository") or {}
        full_name = str(repository.get("full_name") or "").strip()
        if not full_name:
            raise DigestError(
                "canonical code-security repository entry has no full name"
            )
        if full_name in attached_status:
            raise DigestError(
                f"canonical repository inventory contains duplicate {full_name}"
            )
        attached_status[full_name] = (
            str(item.get("status")) if item.get("status") is not None else None
        )

    observed_names = {
        str(item.get("full_name") or f"{ORG}/{item.get('name')}")
        for item in repositories
    }
    attached_names = set(attached_status)
    if observed_names != attached_names:
        missing_from_org_listing = sorted(attached_names - observed_names)
        missing_from_canonical = sorted(observed_names - attached_names)
        raise DigestError(
            "organization repository inventory does not match canonical "
            "code-security inventory: "
            f"missing_from_org_listing={missing_from_org_listing}; "
            f"missing_from_canonical={missing_from_canonical}"
        )
    return {
        "configuration_id": CANONICAL_CONFIG_ID,
        "configuration_name": canonical.get("name"),
        "repository_count": len(attached_names),
        "inventory_match": True,
        "status_counts": {
            status or "missing": sum(
                1 for value in attached_status.values() if value == status
            )
            for status in set(attached_status.values())
        },
    }


def list_repositories(token: str) -> tuple[dict[str, Any], ...]:
    repositories = list(
        _paginated_list(
            token,
            f"https://api.github.com/orgs/{ORG}/repos?type=all",
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
    validate_canonical_inventory(token, repositories)
    return tuple(repositories)


def select_reader() -> ReaderSelection:
    candidates = (
        (
            "github_app",
            "qillqaq_app_installation",
            os.environ.get("DIGEST_APP_TOKEN") or "",
        ),
        (
            "governed_pat_fallback",
            "SZL_GITHUB_TOKEN",
            os.environ.get("SZL_GITHUB_TOKEN") or "",
        ),
    )
    attempts: list[dict[str, Any]] = []
    for mode, name, token in candidates:
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
                "canonical_inventory_match": True,
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
