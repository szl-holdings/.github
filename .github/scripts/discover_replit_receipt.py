#!/usr/bin/env python3
"""Discover and validate the public Unified Control Hub deployment receipt.

The verifier is read-only.  It accepts only a complete, public HTTPS contract:
GET and HEAD must agree on immutable source/deployment revisions, the receipt
must bind itself to the expected Replit application, and test/mobile/readiness
evidence must be explicit rather than inferred from an HTTP 200.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

REPL_ID = "34870515-2d52-4ad8-9636-40cc3ced1771"
RECEIPT_PATH = "/api/szl/deployment-receipt"
RECEIPT_SCHEMA = "szl.unified-control-hub.deployment-receipt/v1"
REPORT_SCHEMA = "szl.replit-public-status/v1"
DEFAULT_ORIGINS = (
    "https://unified-control-hub--stephenlutar2.repl.co",
    "https://unified-control-hub-stephenlutar2.repl.co",
    "https://unified-control-hub-stephenlutar2.replit.app",
    "https://unified-control-hub.stephenlutar2.repl.co",
)
SOURCE_REVISION_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
DEPLOYMENT_REVISION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{6,127}$")
MAX_BODY_BYTES = 1_048_576


@dataclass(frozen=True)
class Attempt:
    origin: str
    receipt_url: str
    ok: bool
    missing: list[str]
    detail: str
    get_status: int | None = None
    head_status: int | None = None
    final_origin: str | None = None


class ContractError(RuntimeError):
    """Raised when a reachable endpoint violates the deployment contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalized_origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme.lower() != "https":
        raise ValueError("origin must use HTTPS")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("origin must contain a public hostname and no credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("origin must not contain a query or fragment")
    port = f":{parsed.port}" if parsed.port else ""
    return f"https://{parsed.hostname.lower()}{port}"


def origin_from_url(value: str) -> str:
    return normalized_origin(value)


def candidate_origins(
    explicit: Iterable[str] = (),
    *,
    environment: Mapping[str, str] | None = None,
) -> list[str]:
    environment = environment or os.environ
    values: list[str] = []
    values.extend(explicit)
    configured = environment.get("REPLIT_PRODUCTION_URL", "").strip()
    if configured:
        values.append(configured)
    configured_many = environment.get("REPLIT_ORIGINS", "").strip()
    if configured_many:
        values.extend(item.strip() for item in configured_many.split(","))
    values.extend(DEFAULT_ORIGINS)

    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        try:
            origin = normalized_origin(value)
        except (TypeError, ValueError):
            continue
        if origin not in seen:
            seen.add(origin)
            output.append(origin)
    if not output:
        raise ValueError("no valid HTTPS Replit origins were supplied")
    return output


def _read_response(response: Any, *, read_body: bool) -> tuple[int, str, dict[str, str], bytes]:
    status = int(getattr(response, "status", 0) or getattr(response, "code", 0) or 0)
    final_url = str(response.geturl())
    headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
    body = response.read(MAX_BODY_BYTES + 1) if read_body else b""
    if len(body) > MAX_BODY_BYTES:
        raise ContractError("response body exceeds 1 MiB")
    return status, final_url, headers, body


def http_request(
    opener: Any,
    method: str,
    url: str,
    *,
    timeout: float,
) -> tuple[int, str, dict[str, str], bytes]:
    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "User-Agent": "szl-replit-receipt-verifier/1",
        },
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            return _read_response(response, read_body=method != "HEAD")
    except urllib.error.HTTPError as exc:
        status, final_url, headers, body = _read_response(
            exc,
            read_body=method != "HEAD",
        )
        detail = body[:300].decode("utf-8", errors="replace")
        raise ContractError(f"{method} returned HTTP {status}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ContractError(f"{method} failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ContractError(f"{method} timed out") from exc


def _expect_object(receipt: dict[str, Any], key: str, missing: list[str]) -> dict[str, Any]:
    value = receipt.get(key)
    if not isinstance(value, dict):
        missing.append(key)
        return {}
    return value


def _validate_timestamp(value: Any, key: str, missing: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        missing.append(key)
        return
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        missing.append(key)
        return
    if parsed.tzinfo is None:
        missing.append(key)


def validate_receipt(
    receipt: Any,
    *,
    requested_origin: str,
    final_url: str,
    head_headers: Mapping[str, str],
) -> tuple[list[str], str]:
    missing: list[str] = []
    if not isinstance(receipt, dict):
        return ["JSON object"], requested_origin

    final_origin = origin_from_url(final_url)
    if receipt.get("schema") != RECEIPT_SCHEMA:
        missing.append("schema")
    if receipt.get("repl_id") != REPL_ID:
        missing.append("repl_id")

    source_revision = receipt.get("source_revision")
    if not isinstance(source_revision, str) or not SOURCE_REVISION_RE.fullmatch(
        source_revision.strip().lower()
    ):
        missing.append("source_revision")

    deployment_revision = receipt.get("deployment_revision")
    if not isinstance(deployment_revision, str) or not DEPLOYMENT_REVISION_RE.fullmatch(
        deployment_revision.strip()
    ):
        missing.append("deployment_revision")

    production_url = receipt.get("production_url")
    try:
        receipt_origin = normalized_origin(str(production_url))
    except (TypeError, ValueError):
        missing.append("production_url")
        receipt_origin = ""
    else:
        if receipt_origin != final_origin:
            missing.append("production_url binding")

    _validate_timestamp(receipt.get("generated_at"), "generated_at", missing)

    tests = _expect_object(receipt, "tests", missing)
    if str(tests.get("status", "")).lower() not in {"passed", "pass", "green"}:
        missing.append("tests.status")
    commands = tests.get("commands")
    if not isinstance(commands, list) or not commands or not all(
        isinstance(item, str) and item.strip() for item in commands
    ):
        missing.append("tests.commands")

    mobile = _expect_object(receipt, "mobile", missing)
    if str(mobile.get("status", "")).lower() not in {"passed", "pass", "green"}:
        missing.append("mobile.status")
    viewports = mobile.get("viewport_widths")
    if not isinstance(viewports, list) or not any(
        isinstance(item, int) and 280 <= item <= 480 for item in viewports
    ):
        missing.append("mobile.viewport_widths")

    readiness = _expect_object(receipt, "readiness", missing)
    if readiness.get("ok") is not True:
        missing.append("readiness.ok")
    if str(readiness.get("status", "")).lower() not in {"ready", "operational", "green"}:
        missing.append("readiness.status")
    checks = readiness.get("checks")
    if not isinstance(checks, dict) or not checks or any(value is not True for value in checks.values()):
        missing.append("readiness.checks")

    expected_source = str(source_revision or "")
    expected_deployment = str(deployment_revision or "")
    if head_headers.get("x-szl-source-revision", "") != expected_source:
        missing.append("HEAD X-SZL-Source-Revision")
    if head_headers.get("x-szl-deployment-revision", "") != expected_deployment:
        missing.append("HEAD X-SZL-Deployment-Revision")

    return sorted(set(missing)), final_origin


def probe_origin(
    origin: str,
    *,
    opener: Any | None = None,
    timeout: float = 20.0,
) -> tuple[Attempt, dict[str, Any] | None]:
    opener = opener or urllib.request.build_opener()
    origin = normalized_origin(origin)
    url = origin + RECEIPT_PATH
    get_status: int | None = None
    head_status: int | None = None
    try:
        get_status, final_url, get_headers, body = http_request(
            opener,
            "GET",
            url,
            timeout=timeout,
        )
        if get_status != 200:
            raise ContractError(f"GET returned HTTP {get_status}")
        if "application/json" not in get_headers.get("content-type", "").lower():
            raise ContractError("GET did not return application/json")
        try:
            receipt = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError(f"GET returned invalid JSON: {exc}") from exc

        head_status, head_final_url, head_headers, _ = http_request(
            opener,
            "HEAD",
            url,
            timeout=timeout,
        )
        if head_status not in {200, 204}:
            raise ContractError(f"HEAD returned HTTP {head_status}")
        if origin_from_url(head_final_url) != origin_from_url(final_url):
            raise ContractError("GET and HEAD resolved to different public origins")

        missing, final_origin = validate_receipt(
            receipt,
            requested_origin=origin,
            final_url=final_url,
            head_headers=head_headers,
        )
        if missing:
            return (
                Attempt(
                    origin=origin,
                    receipt_url=url,
                    ok=False,
                    missing=missing,
                    detail="deployment receipt is incomplete or inconsistent",
                    get_status=get_status,
                    head_status=head_status,
                    final_origin=final_origin,
                ),
                None,
            )
        return (
            Attempt(
                origin=origin,
                receipt_url=url,
                ok=True,
                missing=[],
                detail="GET/HEAD and deployment evidence contract passed",
                get_status=get_status,
                head_status=head_status,
                final_origin=final_origin,
            ),
            receipt,
        )
    except (ContractError, ValueError) as exc:
        return (
            Attempt(
                origin=origin,
                receipt_url=url,
                ok=False,
                missing=["receipt GET/HEAD or contract"],
                detail=str(exc),
                get_status=get_status,
                head_status=head_status,
            ),
            None,
        )


def discover(
    origins: Iterable[str],
    *,
    attempts: int = 3,
    interval_seconds: float = 20.0,
    timeout: float = 20.0,
    opener_factory: Callable[[], Any] = urllib.request.build_opener,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if attempts < 1:
        raise ValueError("attempts must be positive")
    if interval_seconds < 0:
        raise ValueError("interval_seconds must be non-negative")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    candidates = list(origins)
    all_attempts: list[Attempt] = []
    for cycle in range(1, attempts + 1):
        for origin in candidates:
            attempt, receipt = probe_origin(
                origin,
                opener=opener_factory(),
                timeout=timeout,
            )
            all_attempts.append(attempt)
            if attempt.ok and receipt is not None:
                return {
                    "schema": REPORT_SCHEMA,
                    "repl_id": REPL_ID,
                    "generated_at": utc_now(),
                    "ok": True,
                    "status": "OPERATIONAL",
                    "production_url": attempt.final_origin,
                    "receipt": receipt,
                    "attempts": [asdict(item) for item in all_attempts],
                    "current_blocker": None,
                }
        if cycle < attempts:
            sleep(interval_seconds)

    details = "; ".join(
        f"{item.origin}: {item.detail}" for item in all_attempts[-len(candidates) :]
    )
    return {
        "schema": REPORT_SCHEMA,
        "repl_id": REPL_ID,
        "generated_at": utc_now(),
        "ok": False,
        "status": "BLOCKED",
        "production_url": None,
        "receipt": None,
        "attempts": [asdict(item) for item in all_attempts],
        "current_blocker": (
            "No complete public Unified Control Hub deployment receipt passed "
            f"GET, HEAD, provenance, tests, mobile, and readiness validation: {details}"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        default="reports/replit-receipt-discovery-latest.json",
    )
    parser.add_argument("--origin", action="append", default=[])
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--interval-seconds", type=float, default=20.0)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = discover(
            candidate_origins(args.origin),
            attempts=args.attempts,
            interval_seconds=args.interval_seconds,
            timeout=args.timeout,
        )
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema": REPORT_SCHEMA,
            "repl_id": REPL_ID,
            "generated_at": utc_now(),
            "ok": False,
            "status": "BLOCKED",
            "production_url": None,
            "receipt": None,
            "attempts": [],
            "current_blocker": f"{type(exc).__name__}: {exc}",
        }

    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("ok") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
