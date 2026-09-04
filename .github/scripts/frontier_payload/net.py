# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

from .config import (
    GITHUB_API, MAX_BYTES, SHA40_RE, TOKEN_RE, USER_AGENT,
    FrontierError, ProbeContract,
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return TOKEN_RE.sub("[REDACTED]", value)
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact(item) for key, item in value.items()}
    return value


def request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: Mapping[str, Any] | None = None,
    accept: str = "application/json, text/plain, text/html, */*",
    timeout: float = 30.0,
) -> dict[str, Any]:
    body = None
    headers = {"User-Agent": USER_AGENT, "Accept": accept, "Cache-Control": "no-cache"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    started = time.monotonic()
    try:
        with OPENER.open(req, timeout=timeout) as response:
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise FrontierError(f"response exceeded {MAX_BYTES} bytes")
            return {
                "status": int(response.status),
                "headers": {k.lower(): v for k, v in response.headers.items()},
                "body": raw,
                "url": response.geturl(),
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read(MAX_BYTES + 1)[:MAX_BYTES]
        return {
            "status": int(exc.code),
            "headers": {k.lower(): v for k, v in exc.headers.items()},
            "body": raw,
            "url": exc.geturl(),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
            "error": f"HTTPError: {exc.reason}",
        }
    except Exception as exc:
        return {
            "status": None,
            "headers": {},
            "body": b"",
            "url": url,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
            "error": f"{type(exc).__name__}: {redact(str(exc))}",
        }


def decode_json(result: Mapping[str, Any]) -> Any:
    try:
        return json.loads(bytes(result.get("body") or b"").decode())
    except Exception:
        return None


def source_revision(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    candidates: list[Any] = [payload.get(key) for key in (
        "observed_source_revision", "source_revision", "git_sha", "revision", "sha",
    )]
    for name in ("build", "source", "deployment", "runtime"):
        container = payload.get(name)
        if isinstance(container, dict):
            candidates.extend(container.get(key) for key in (
                "observed_source_revision", "source_revision", "git_sha", "revision", "sha",
            ))
    for candidate in candidates:
        if isinstance(candidate, str) and SHA40_RE.fullmatch(candidate.strip()):
            return candidate.strip().lower()
    return None


def validate_json_contract(contract: str, value: Any) -> tuple[bool, dict[str, Any]]:
    if not isinstance(value, dict):
        return False, {"reason": "response is not a JSON object"}
    if contract == "livez":
        status = str(value.get("status") or "").upper()
        return status == "LIVE", {"observed_status": status or None}
    if contract == "controller":
        organ, locked = value.get("organ"), value.get("locked_formula_count")
        return organ == "a11oy" and locked == 8, {
            "organ": organ, "locked_formula_count": locked,
        }
    if contract == "build-info":
        revision = source_revision(value)
        return revision is not None, {"source_revision": revision}
    raise FrontierError(f"unknown JSON contract: {contract}")


def probe(contract: ProbeContract) -> dict[str, Any]:
    observed = request("GET", contract.url)
    raw = bytes(observed.get("body") or b"")
    text = raw.decode("utf-8", "replace")
    literals = {item: item.casefold() in text.casefold() for item in contract.required_literals}
    contract_ok, evidence = True, {}
    if contract.json_contract:
        contract_ok, evidence = validate_json_contract(contract.json_contract, decode_json(observed))
    verified = observed.get("status") == 200 and all(literals.values()) and contract_ok
    return {
        "name": contract.name,
        "url": contract.url,
        "critical": contract.critical,
        "http_status": observed.get("status"),
        "bytes": len(raw),
        "content_type": (observed.get("headers") or {}).get("content-type"),
        "required_literals": literals,
        "contract": contract.json_contract,
        "contract_evidence": evidence,
        "elapsed_ms": observed.get("elapsed_ms"),
        "verified": verified,
        "error": observed.get("error"),
    }


class GitHub:
    def __init__(self, token: str | None, *, apply: bool) -> None:
        self.token = (token or "").strip()
        self.apply = apply

    def call(self, method: str, path: str, payload=None, *, expected=(200,)) -> Any:
        result = request(
            method,
            path if path.startswith("https://") else GITHUB_API + path,
            token=self.token or None,
            payload=payload,
            accept="application/vnd.github+json",
            timeout=45,
        )
        if result.get("status") not in expected:
            detail = bytes(result.get("body") or b"").decode("utf-8", "replace")[:1200]
            raise FrontierError(
                f"GitHub HTTP {result.get('status')} for {method} {path}: "
                f"{redact(detail or result.get('error'))}"
            )
        if not result.get("body"):
            return None
        value = decode_json(result)
        if value is None:
            raise FrontierError(f"GitHub returned non-JSON for {method} {path}")
        return value

    def main_sha(self, repository: str) -> str:
        value = self.call("GET", f"/repos/{repository}/commits/main")
        sha = str((value or {}).get("sha") or "").lower()
        if not SHA40_RE.fullmatch(sha):
            raise FrontierError(f"{repository} main did not resolve to a full SHA")
        return sha

    def file_text(self, repository: str, path: str, ref: str = "main") -> str:
        encoded = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
        value = self.call(
            "GET", f"/repos/{repository}/contents/{encoded}?ref={urllib.parse.quote(ref, safe='')}"
        )
        if not isinstance(value, dict) or value.get("encoding") != "base64":
            raise FrontierError(f"invalid contents response: {repository}/{path}")
        return base64.b64decode(str(value.get("content") or ""), validate=False).decode()

    def repository(self, repository: str) -> dict[str, Any]:
        value = self.call("GET", f"/repos/{repository}")
        if not isinstance(value, dict):
            raise FrontierError(f"invalid repository metadata: {repository}")
        return value

    def patch_repository(self, repository: str, desired: Mapping[str, Any]) -> dict[str, Any]:
        if not self.apply:
            return {"dry_run": True, **desired}
        value = self.call("PATCH", f"/repos/{repository}", desired)
        if not isinstance(value, dict):
            raise FrontierError(f"invalid repository PATCH readback: {repository}")
        return value

    def dispatch(self, repository: str, workflow: str, inputs: Mapping[str, str]) -> None:
        if self.apply:
            self.call(
                "POST",
                f"/repos/{repository}/actions/workflows/{workflow}/dispatches",
                {"ref": "main", "inputs": dict(inputs)},
                expected=(204,),
            )
