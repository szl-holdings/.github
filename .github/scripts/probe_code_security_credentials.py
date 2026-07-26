#!/usr/bin/env python3
"""Probe governed credentials against the exact code-security endpoint.

Only capability outcomes are recorded. Token values, lengths, prefixes, hashes,
identities, headers, scopes, and response bodies are never written or printed.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "szl.code-security-credential-probe/v1"
ENDPOINT = (
    "https://api.github.com/orgs/szl-holdings/"
    "code-security/configurations?per_page=1"
)
CANDIDATES = (
    "SZL_GITHUB_TOKEN",
    "GH_NOTIFICATIONS_TOKEN",
)


def classify(status: int | None, error: BaseException | None) -> str:
    if status == 200:
        return "authorized"
    if status == 401:
        return "unauthenticated"
    if status == 403:
        return "unauthorized"
    if status == 404:
        return "not_found_or_hidden"
    if status is not None:
        return "unexpected_http"
    if isinstance(error, urllib.error.URLError):
        return "network_error"
    return "other_error"


def probe(token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        ENDPOINT,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-code-security-credential-probe",
        },
    )
    status: int | None = None
    error: BaseException | None = None
    response_shape = "unread"
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(response.status)
            data = json.loads(response.read().decode("utf-8"))
            response_shape = "list" if isinstance(data, list) else type(data).__name__
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        error = exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        error = exc
    return {
        "http_status": status,
        "classification": classify(status, error),
        "authorized": status == 200,
        "response_shape": response_shape if status == 200 else None,
    }


def main() -> int:
    candidates: list[dict[str, Any]] = []
    for name in CANDIDATES:
        token = os.environ.get(name) or ""
        record: dict[str, Any] = {
            "secret_name": name,
            "present": bool(token),
        }
        if token:
            record.update(probe(token))
        else:
            record.update(
                {
                    "http_status": None,
                    "classification": "not_configured",
                    "authorized": False,
                    "response_shape": None,
                }
            )
        candidates.append(record)

    authorized = [item["secret_name"] for item in candidates if item["authorized"]]
    report = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation": os.environ.get("GITHUB_SHA"),
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "endpoint_class": "organization_code_security_configurations_read",
        "status": "AUTHORIZED_AVAILABLE" if authorized else "NOT_AUTHORIZED",
        "authorized_secret_names": authorized,
        "candidates": candidates,
        "boundaries": [
            "No token value, length, prefix, hash, identity, scope header, request header, or response body is recorded.",
            "Only the exact organization code-security configurations read endpoint is probed.",
            "No GitHub resource is mutated.",
        ],
    }
    path = Path(
        os.environ.get(
            "REPORT_PATH",
            "reports/code-security-credential-probe.json",
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if authorized else 1


if __name__ == "__main__":
    raise SystemExit(main())
