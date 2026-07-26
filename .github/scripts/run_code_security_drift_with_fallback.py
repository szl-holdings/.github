#!/usr/bin/env python3
"""Run organization code-security drift with bounded credential selection.

The short-lived qillqaq GitHub App token is preferred. Until the organization
approves the tracked ``organization_administration: read`` permission for that
installation, the existing governed ``SZL_GITHUB_TOKEN`` secret is an explicit
fallback. Every candidate is probed against the exact read-only endpoint before
use. A missing, expired, under-scoped, or unreachable credential is never a
neutral production result.

No token value, length, prefix, hash, identity, header, or response body is
recorded or printed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_SCHEMA = "szl.code-security-drift/v2"
ENDPOINT = (
    "https://api.github.com/orgs/szl-holdings/"
    "code-security/configurations?per_page=1"
)
CANDIDATES = (
    ("qillqaq_app", "QILLQAQ_ORG_TOKEN"),
    ("szl_github_token", "SZL_GITHUB_TOKEN"),
)


class CredentialSelectionError(RuntimeError):
    """Raised when no configured candidate can read the exact endpoint."""


def _classify(status: int | None, error: BaseException | None) -> str:
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


def _probe(token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        ENDPOINT,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-code-security-credential-selector",
        },
    )
    status: int | None = None
    error: BaseException | None = None
    response_shape: str | None = None
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(response.status)
            payload = json.loads(response.read().decode("utf-8"))
            response_shape = "list" if isinstance(payload, list) else type(payload).__name__
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        error = exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        error = exc
    return {
        "http_status": status,
        "classification": _classify(status, error),
        "authorized": status == 200,
        "response_shape": response_shape if status == 200 else None,
    }


def _bounded_failure_report(
    path: Path,
    candidates: list[dict[str, Any]],
    detail: str,
) -> None:
    report = {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation": os.environ.get("GITHUB_SHA"),
        "organization": os.environ.get("GITHUB_REPOSITORY_OWNER"),
        "status": "NOT_VERIFIED",
        "credential_selection": {
            "selected": None,
            "candidates": candidates,
        },
        "summary": {"ok": 0, "warning": 0, "error": 1},
        "detail": detail,
        "boundaries": [
            "No credential value, length, prefix, hash, identity, header, or response body is recorded.",
            "Only the exact organization code-security configurations read endpoint is probed.",
            "Credential failure is terminal; no neutral production skip exists.",
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _select() -> tuple[str, str, list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    for label, env_name in CANDIDATES:
        token = os.environ.get(env_name) or ""
        record: dict[str, Any] = {
            "credential": label,
            "configured": bool(token),
        }
        if not token:
            record.update(
                {
                    "http_status": None,
                    "classification": "not_configured",
                    "authorized": False,
                    "response_shape": None,
                }
            )
            records.append(record)
            continue
        record.update(_probe(token))
        records.append(record)
        if record["authorized"]:
            return label, token, records
    raise CredentialSelectionError(
        "no configured governed credential can read the exact organization endpoint"
    )


def _run_checker(selected: str, token: str, report_path: Path) -> int:
    checker = Path(__file__).resolve().parent / "code_security_drift.py"
    env = dict(os.environ)
    env["SZL_GITHUB_TOKEN"] = token
    env.pop("QILLQAQ_ORG_TOKEN", None)
    env.pop("GH_TOKEN", None)
    env.pop("GITHUB_TOKEN", None)
    process = subprocess.run(
        [
            sys.executable,
            str(checker),
            "--report",
            str(report_path),
        ],
        check=False,
        text=True,
        env=env,
    )
    if not report_path.is_file() or not report_path.stat().st_size:
        raise RuntimeError(
            f"code-security checker returned {process.returncode} without a report"
        )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.setdefault("schema", REPORT_SCHEMA)
    report.setdefault("generation", os.environ.get("GITHUB_SHA"))
    report.setdefault(
        "organization",
        report.get("org") or os.environ.get("GITHUB_REPOSITORY_OWNER"),
    )
    report["credential_selection"] = {
        "selected": selected,
        "fallback_used": selected == "szl_github_token",
    }
    report["status"] = "DRIFT_DETECTED" if report.get("errors") else "VERIFIED"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return int(process.returncode)


def main() -> int:
    report_path = Path(
        os.environ.get("REPORT_PATH", "reports/code-security-drift.json")
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    candidates: list[dict[str, Any]] = []
    try:
        selected, token, candidates = _select()
        print(f"Selected governed credential class: {selected}")
        return _run_checker(selected, token, report_path)
    except CredentialSelectionError as exc:
        # Rebuild the complete candidate inventory for evidence because _select
        # returns only on success and does not expose partial internals on error.
        candidates = []
        for label, env_name in CANDIDATES:
            token = os.environ.get(env_name) or ""
            record: dict[str, Any] = {
                "credential": label,
                "configured": bool(token),
            }
            if token:
                record.update(_probe(token))
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
        _bounded_failure_report(report_path, candidates, str(exc))
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        _bounded_failure_report(
            report_path,
            candidates,
            f"{type(exc).__name__}: {exc}",
        )
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
