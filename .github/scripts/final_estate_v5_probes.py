#!/usr/bin/env python3
"""Contract-aware public probes for active-estate reconciliation v5."""
from __future__ import annotations

from typing import Any, Mapping

import requests

from final_estate_v5_core import (
    A11OY_BRANCH,
    A11OY_REPOSITORY,
    SHA40,
    Gate,
    GitHubClient,
    ProbeSpec,
    https_origin,
)


def _json_contract_ok(
    name: str,
    spec: ProbeSpec,
    payload: Mapping[str, Any],
    expected_source_sha: str | None,
    evidence: dict[str, Any],
) -> bool:
    required_ok = all(key in payload for key in spec.required_keys)
    schema_ok = spec.expected_schema is None or payload.get("schema") == spec.expected_schema
    status = str(payload.get("status") or payload.get("overall_status") or "").upper()
    statuses_ok = not spec.expected_statuses or status in {
        value.upper() for value in spec.expected_statuses
    }
    evidence.update(
        {
            "json_keys": sorted(str(key) for key in payload)[:100],
            "schema": payload.get("schema"),
            "status": payload.get("status") or payload.get("overall_status"),
            "required_keys_present": required_ok,
        }
    )
    ok = required_ok and schema_ok and statuses_ok
    if name == "a11oy_livez":
        return ok and payload.get("receipt_minted") is False
    if name == "a11oy_build_info":
        build = payload.get("build")
        revision = build.get("revision") if isinstance(build, Mapping) else None
        state = str(build.get("state") or "").upper() if isinstance(build, Mapping) else ""
        source_bound = (
            SHA40.fullmatch(str(revision or "")) is not None
            and bool(expected_source_sha)
            and revision == expected_source_sha
        )
        evidence.update(
            {
                "observed_source_revision": revision,
                "expected_source_revision": expected_source_sha,
                "source_bound": source_bound,
                "build_state": state,
            }
        )
        return (
            ok
            and payload.get("receipt_minted") is False
            and state == "OBSERVED"
            and source_bound
        )
    if name == "a11oy_brain_capabilities":
        return (
            ok
            and isinstance(payload.get("capabilities"), list)
            and isinstance(payload.get("claim_policy"), Mapping)
            and isinstance(payload.get("summary"), Mapping)
        )
    if name == "a11oy_readiness":
        return (
            ok
            and payload.get("honest") is True
            and payload.get("view") == "summary"
            and isinstance(payload.get("matrix_available"), bool)
            and isinstance(payload.get("probe_verdict_available"), bool)
        )
    return ok


def safe_probe(
    name: str,
    spec: ProbeSpec,
    expected_source_sha: str | None,
    *,
    session: requests.Session | None = None,
) -> Gate:
    session = session or requests.Session()
    session.headers.update(
        {
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "User-Agent": "szl-final-estate-reconciliation/5",
        }
    )
    try:
        head = session.head(spec.url, allow_redirects=True, timeout=45)
        response = session.get(spec.url, allow_redirects=True, timeout=60)
        head_ok = not spec.require_head or 200 <= head.status_code < 400
        get_ok = 200 <= response.status_code < 400
        content_type = str(response.headers.get("content-type") or "").lower()
        media_ok = (
            "application/json" in content_type
            if spec.media_type == "json"
            else "text/html" in content_type
        )
        ok = (
            head_ok
            and get_ok
            and https_origin(response.url) is not None
            and len(response.content) > 0
            and media_ok
        )
        evidence: dict[str, Any] = {
            "url": spec.url,
            "head_required": spec.require_head,
            "head_http_status": head.status_code,
            "get_http_status": response.status_code,
            "final_url": response.url,
            "content_type": response.headers.get("content-type"),
            "bytes": len(response.content),
            "media_ok": media_ok,
        }
        if spec.media_type == "json":
            try:
                payload = response.json()
            except ValueError as exc:
                payload = None
                evidence["json_error"] = str(exc)
            if isinstance(payload, Mapping):
                ok = ok and _json_contract_ok(
                    name,
                    spec,
                    payload,
                    expected_source_sha if spec.source_bound else None,
                    evidence,
                )
            else:
                ok = False
        return Gate(
            f"probe:{name}",
            ok,
            (
                f"HEAD={head.status_code}{' required' if spec.require_head else ' observed'}; "
                f"GET={response.status_code}; media={spec.media_type}; "
                f"final={response.url}; bytes={len(response.content)}"
            ),
            evidence,
        )
    except Exception as exc:  # noqa: BLE001
        return Gate(
            f"probe:{name}",
            False,
            f"{type(exc).__name__}: {exc}",
            {"url": spec.url, "head_required": spec.require_head},
        )


def evaluate_a11oy_source(client: GitHubClient) -> tuple[Gate, str | None]:
    try:
        revision = client.branch_head(A11OY_REPOSITORY, A11OY_BRANCH)
        return (
            Gate(
                "source:a11oy_protected_main",
                True,
                f"repository={A11OY_REPOSITORY}; branch={A11OY_BRANCH}; revision={revision}",
                {
                    "repository": A11OY_REPOSITORY,
                    "branch": A11OY_BRANCH,
                    "revision": revision,
                },
            ),
            revision,
        )
    except Exception as exc:  # noqa: BLE001
        return Gate(
            "source:a11oy_protected_main",
            False,
            f"{type(exc).__name__}: {exc}",
            {},
        ), None


def evaluate_open_public_prs(client: GitHubClient) -> Gate:
    try:
        values = client.open_public_pull_requests()
        evidence = [
            {
                "repository_url": item.get("repository_url"),
                "number": item.get("number"),
                "title": item.get("title"),
                "url": item.get("html_url"),
                "draft": item.get("draft"),
                "updated_at": item.get("updated_at"),
            }
            for item in values
        ]
        return Gate(
            "public_estate_open_prs",
            len(values) == 0,
            f"public_open_pull_requests={len(values)}",
            {"visibility_scope": "public", "open_pull_requests": evidence},
        )
    except Exception as exc:  # noqa: BLE001
        return Gate(
            "public_estate_open_prs", False, f"{type(exc).__name__}: {exc}", {}
        )
