#!/usr/bin/env python3
# Copyright 2026 SZL Holdings — SPDX-License-Identifier: Apache-2.0
"""Observe a fixed public frontier without importing the operational controller.

Only the pure configuration module is loaded. All network requests are anonymous
GETs to the exact public resources below; redirects, retries, credentials, SDKs,
provider mutations, and native workflow dispatches are unavailable here.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import importlib.util
import json
import signal
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterator, Mapping


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / ".github/scripts/frontier_payload/config.py"
_SPEC = importlib.util.spec_from_file_location("frontier_readonly_config", CONFIG_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("PUBLIC_CONFIGURATION_UNAVAILABLE")
CONFIG = importlib.util.module_from_spec(_SPEC)
# dataclasses resolves annotations through the defining module. Register only
# this module, without importing the package or its operational helpers.
sys.modules[_SPEC.name] = CONFIG
_SPEC.loader.exec_module(CONFIG)

MAX_BYTES = 2_000_000
REQUEST_SECONDS = 30.0
TOTAL_SECONDS = 600.0
REPORT_LIMIT = 65_536
SUMMARY_LIMIT = 16_384
SCHEMA = "szl.frontier-payload-readonly/v1"
MAIN_URL = "https://api.github.com/repos/szl-holdings/a11oy/commits/main"
VESSELS_PUBLIC_URL = "https://huggingface.co/spaces/SZLHOLDINGS/vessels/raw/main/README.md"
METADATA_URLS = {
    repository: "https://api.github.com/repos/" + repository
    for repository in CONFIG.REPOSITORY_METADATA
}
PUBLIC_URLS = frozenset(
    [MAIN_URL, CONFIG.VESSELS_CARD_URL, VESSELS_PUBLIC_URL]
    + list(METADATA_URLS.values())
    + [probe.url for probe in CONFIG.PROBES]
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an observation failure, not authority for another URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# Disable proxy inheritance as well as redirects; no ambient proxy credential
# or additional destination may enter this fixed anonymous request boundary.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


class ReadDeadlineExceeded(TimeoutError):
    """Raised by the native wall-clock timer during a public read."""


@contextlib.contextmanager
def _bounded_request(seconds: float) -> Iterator[None]:
    """Cover DNS, connect, headers, and body with one Linux wall-clock limit."""
    if seconds <= 0:
        raise ReadDeadlineExceeded()
    prior_handler = signal.getsignal(signal.SIGALRM)
    prior_timer = signal.getitimer(signal.ITIMER_REAL)
    if prior_timer != (0.0, 0.0):
        raise RuntimeError("READ_TIMER_ALREADY_ACTIVE")

    def timeout(_signum, _frame):
        raise ReadDeadlineExceeded()

    signal.signal(signal.SIGALRM, timeout)
    try:
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, prior_handler)


def request_public(url: str, *, deadline: float) -> dict[str, Any]:
    """Perform at most one allowlisted anonymous GET and retain no error body."""
    started = time.monotonic()
    result: dict[str, Any] = {"status": None, "body": b"", "error": None}
    if url not in PUBLIC_URLS:
        result["error"] = "PUBLIC_URL_NOT_ADMITTED"
    elif deadline <= started:
        result["error"] = "TOTAL_DEADLINE_EXCEEDED"
    else:
        remaining = min(REQUEST_SECONDS, deadline - started)
        request = urllib.request.Request(
            url, method="GET",
            headers={
                "User-Agent": "SZL-Frontier-Public-ReadOnly/1.0",
                "Accept": "application/json, text/plain, text/html",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with _bounded_request(remaining):
                with OPENER.open(request, timeout=remaining) as response:
                    result["status"] = int(response.status)
                    if response.geturl() != url:
                        result["error"] = "HTTP_REDIRECT_HELD"
                    elif result["status"] != 200:
                        result["error"] = "HTTP_STATUS"
                    else:
                        body = response.read(MAX_BYTES + 1)
                        if len(body) > MAX_BYTES:
                            result["error"] = "RESPONSE_TOO_LARGE"
                        else:
                            result["body"] = body
            if time.monotonic() >= deadline:
                result.update(body=b"", error="TOTAL_DEADLINE_EXCEEDED")
        except urllib.error.HTTPError as exc:
            result["status"] = int(exc.code)
            result["error"] = "HTTP_REDIRECT_HELD" if 300 <= exc.code < 400 else "HTTP_STATUS"
            exc.close()
        except ReadDeadlineExceeded:
            result.update(body=b"", error="READ_DEADLINE_EXCEEDED")
        except TimeoutError:
            result.update(body=b"", error="READ_TIMEOUT")
        except Exception:
            # Provider exception strings and bodies are not report material.
            result.update(body=b"", error="PUBLIC_READ_FAILED")
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)
    return result


def _json_body(observed: Mapping[str, Any]) -> dict[str, Any] | None:
    if observed.get("status") != 200 or observed.get("error"):
        return None
    try:
        value = json.loads(bytes(observed.get("body") or b"").decode("utf-8"))
    except (ValueError, UnicodeError, TypeError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(CONFIG.SHA40_RE.fullmatch(value)) and set(value) != {"0"}


def _source_revision(value: Mapping[str, Any]) -> str | None:
    candidates = [value.get(key) for key in (
        "observed_source_revision", "source_revision", "git_sha", "revision", "sha",
    )]
    for name in ("build", "source", "deployment", "runtime"):
        nested = value.get(name)
        if isinstance(nested, dict):
            candidates.extend(nested.get(key) for key in (
                "observed_source_revision", "source_revision", "git_sha", "revision", "sha",
            ))
    for candidate in candidates:
        if isinstance(candidate, str) and _valid_sha(candidate.strip()):
            return candidate.strip().lower()
    return None


def _probe(contract, *, deadline: float) -> dict[str, Any]:
    observed = request_public(contract.url, deadline=deadline)
    body = bytes(observed.get("body") or b"")
    text = body.decode("utf-8", "replace")
    literals = {literal: literal.casefold() in text.casefold() for literal in contract.required_literals}
    value = _json_body(observed)
    contract_ok = True
    evidence: dict[str, Any] = {}
    if contract.json_contract == "livez":
        contract_ok = value is not None and str(value.get("status") or "").upper() == "LIVE"
        evidence = {"live": contract_ok}
    elif contract.json_contract == "controller":
        contract_ok = value is not None and value.get("organ") == "a11oy" and value.get("locked_formula_count") == 8
        evidence = {"organ_matches": bool(value and value.get("organ") == "a11oy"), "formula_count_matches": bool(value and value.get("locked_formula_count") == 8)}
    elif contract.json_contract == "build-info":
        revision = _source_revision(value) if value is not None else None
        contract_ok = revision is not None
        evidence = {"source_revision": revision}
    elif contract.json_contract is not None:
        contract_ok = False
        evidence = {"error": "JSON_CONTRACT_NOT_ADMITTED"}
    return {
        "name": contract.name, "url": contract.url, "critical": contract.critical,
        "http_status": observed.get("status"), "bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest() if body else None,
        "required_literals": literals, "contract": contract.json_contract,
        "contract_evidence": evidence, "elapsed_ms": observed["elapsed_ms"],
        "verified": bool(observed.get("status") == 200 and not observed.get("error") and all(literals.values()) and contract_ok),
        "error": observed.get("error"),
    }


def collect_report(*, deadline: float) -> dict[str, Any]:
    """Observe all fixed resources; unavailable or mismatched evidence stays red."""
    metadata = []
    for repository, desired in CONFIG.REPOSITORY_METADATA.items():
        observed = request_public(METADATA_URLS[repository], deadline=deadline)
        value = _json_body(observed)
        matches = {key: value is not None and type(value.get(key)) is type(expected) and value.get(key) == expected for key, expected in desired.items()}
        verified = all(matches.values())
        metadata.append({
            "repository": repository, "desired": dict(desired), "field_matches": matches,
            "state": "VERIFIED" if verified else "NOT_VERIFIED", "verified": verified,
            "http_status": observed.get("status"),
            "error": observed.get("error") or ("INVALID_METADATA_JSON" if value is None else None),
        })

    source = request_public(CONFIG.VESSELS_CARD_URL, deadline=deadline)
    card = request_public(VESSELS_PUBLIC_URL, deadline=deadline)
    source_body, card_body = bytes(source.get("body") or b""), bytes(card.get("body") or b"")
    required = (
        "# Vessels — consolidated into Killinchu", "Status: CONSOLIDATED",
        "SZLHOLDINGS/killinchu", "No live AIS feed is claimed",
    )
    try:
        valid_source = all(marker in source_body.decode("utf-8", "strict") for marker in required)
    except UnicodeError:
        valid_source = False
    card_verified = bool(source.get("status") == 200 and card.get("status") == 200 and not source.get("error") and not card.get("error") and valid_source and source_body == card_body)
    vessels = {
        "repo_id": "SZLHOLDINGS/vessels", "source_url": CONFIG.VESSELS_CARD_URL,
        "public_url": VESSELS_PUBLIC_URL, "state": "VERIFIED" if card_verified else "NOT_VERIFIED",
        "verified": card_verified, "source_http_status": source.get("status"),
        "readback_http_status": card.get("status"), "source_markers_valid": valid_source,
        "source_sha256": hashlib.sha256(source_body).hexdigest() if source_body else None,
        "readback_sha256": hashlib.sha256(card_body).hexdigest() if card_body else None,
        "source_bytes": len(source_body), "readback_bytes": len(card_body),
        "source_error": source.get("error"), "readback_error": card.get("error"),
        "provider_write_performed": False,
    }

    rows = [_probe(contract, deadline=deadline) for contract in CONFIG.PROBES]
    main_read = request_public(MAIN_URL, deadline=deadline)
    main = _json_body(main_read)
    expected_sha = main.get("sha") if main else None
    expected_sha = expected_sha.lower() if _valid_sha(expected_sha) else None
    build = next(row for row in rows if row["name"] == "a11oy-space-build-info")
    observed_sha = build["contract_evidence"].get("source_revision")
    revision_matches = bool(expected_sha and observed_sha == expected_sha)
    build.update(expected_source_revision=expected_sha, source_revision_matches=revision_matches)
    build["verified"] = bool(build["verified"] and revision_matches)
    critical = [row for row in rows if row["critical"]]
    ready = bool(critical) and all(row["verified"] for row in critical)
    public = {
        "expected_a11oy_main_sha": expected_sha, "observed_runtime_sha": observed_sha,
        "expected_sha_error": main_read.get("error") or ("INVALID_MAIN_REVISION" if expected_sha is None else None),
        "revision_matches": revision_matches, "checks": rows,
        "critical_verified": sum(row["verified"] for row in critical), "critical_total": len(critical),
        "advisory_verified": sum(row["verified"] for row in rows if not row["critical"]),
        "advisory_total": sum(not row["critical"] for row in rows), "ready": ready,
    }
    # Preserve the original critical/advisory distinction in the public report,
    # while the overall success state requires every observed check to pass.
    verified = bool(metadata) and all(row["verified"] for row in metadata) and card_verified and ready and all(row["verified"] for row in rows)
    return {
        "schema": SCHEMA, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "payload_sha256": CONFIG.PAYLOAD_SHA256,
        "status": "READ_ONLY_VERIFIED" if verified else "NOT_YET_CONVERGED",
        "operational_effects": "HELD", "apply": False, "dispatch_controls_requested": False,
        "credentials_used": False, "token_values_recorded": False,
        "github_token_available": False, "hf_token_available": False,
        "credential_availability_observed": False,
        "private_space_visibility_mutated": False, "branch_protection_mutated": False,
        "secrets_mutated": False, "cloudflare_mutated_by_this_controller": False,
        "nemo_signature_attempted": False, "nemo_queue_mutated": False,
        "repository_metadata": metadata, "vessels_card": vessels, "public_estate": public,
        "private_spaces": [{"repo_id": "SZLHOLDINGS/" + name, "state": "UNOBSERVED", "publication_authorized": False, "visibility_mutated": False} for name in CONFIG.PRIVATE_SPACES],
        "workflow_controls": [{"repository": item["repository"], "workflow": item["workflow"], "state": "HELD", "dispatched": False} for item in CONFIG.WORKFLOW_CONTROLS],
        "bounds": {"anonymous_get_sites": 14, "max_response_bytes": MAX_BYTES, "request_seconds": REQUEST_SECONDS, "total_seconds": TOTAL_SECONDS, "redirects": False, "retries": False},
    }


def render_summary(report: Mapping[str, Any]) -> str:
    public = report["public_estate"]
    lines = [
        "## Frontier public read-only verification", "",
        f"- Status: **{report['status']}**",
        "- Operational effects: **HELD**",
        f"- Public critical checks: {public['critical_verified']}/{public['critical_total']}",
        f"- Public advisory checks: {public['advisory_verified']}/{public['advisory_total']}",
        f"- A11oy source parity: {public['revision_matches']}",
        f"- Vessels card verified: {report['vessels_card']['verified']}",
        "- Credentials, provider writes, dispatches, messages, and private-space reads: none.",
        "",
    ]
    lines.extend(f"- {row['repository']}: {row['state']}" for row in report["repository_metadata"])
    lines.append("")
    return "\n".join(lines)


def write_report(report_path: Path, summary_path: Path, report: Mapping[str, Any]) -> None:
    summary = render_summary(report)
    value = dict(report)
    value["summary_sha256"] = hashlib.sha256(summary.encode("utf-8")).hexdigest()
    encoded = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    if len(encoded) > REPORT_LIMIT or len(summary.encode("utf-8")) > SUMMARY_LIMIT:
        raise ValueError("REPORT_SIZE_EXCEEDED")
    for path in (report_path, summary_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(encoded)
    summary_path.write_text(summary, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the fixed public frontier; operational effects remain held.")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.report.resolve() == args.summary.resolve():
        parser.error("report and summary must name different files")
    report = collect_report(deadline=time.monotonic() + TOTAL_SECONDS)
    write_report(args.report, args.summary, report)
    print(report["status"])
    return 0 if report["status"] == "READ_ONLY_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
