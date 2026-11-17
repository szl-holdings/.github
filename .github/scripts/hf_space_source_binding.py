#!/usr/bin/env python3
"""Bind and verify an exact protected source revision in a Hugging Face Space.

This module is deliberately separate from file publication. The reusable deployer
already derives, pushes, and byte-attests the Dockerfile COPY set. This contract
adds the missing runtime identity plane:

1. add/update one non-secret Space variable with the exact checked-out Git SHA;
2. independently read the variable back through the supported HfApi client;
3. after deployment, GET a same-host standard build-info endpoint and require
   ``build.state=OBSERVED`` plus ``build.revision=<exact Git SHA>``.

Runtime probes always use the caller's canonical path verbatim. Retry identity and
cache-control signals travel in request headers, never in synthetic query
parameters. This avoids changing application routing while preserving bounded,
independently attributable convergence attempts.

It never changes Space hardware, visibility, sleep policy, secrets, models, or data.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

import requests
from huggingface_hub import HfApi

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ATTESTATION_ID = re.compile(r"^[0-9]+$")
VARIABLE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
REPO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
REPORT_SCHEMA = "szl.hf-space-source-binding/v1"
PROBE_SOURCE_HEADER = "X-SZL-Source-Revision"
PROBE_ATTEMPT_HEADER = "X-SZL-Probe-Attempt"


class SourceBindingError(RuntimeError):
    """The source-binding contract cannot be established or verified."""

    def __init__(self, message: str, *, evidence: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.evidence = dict(evidence) if evidence is not None else None


def normalize_binding(repo_id: str, variable: str, revision: str, probe_path: str) -> dict[str, str]:
    repo = str(repo_id or "").strip()
    key = str(variable or "").strip()
    sha = str(revision or "").strip().lower()
    raw_path = str(probe_path or "").strip()
    if REPO_ID.fullmatch(repo) is None:
        raise SourceBindingError(f"invalid Hugging Face Space id: {repo!r}")
    if VARIABLE.fullmatch(key) is None:
        raise SourceBindingError(f"invalid source revision variable: {key!r}")
    if SHA40.fullmatch(sha) is None:
        raise SourceBindingError(f"source revision must be an exact 40-character SHA: {sha!r}")
    parsed = urlsplit(raw_path)
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
        or parsed.fragment
    ):
        raise SourceBindingError(
            "source revision probe must be a same-host absolute path without a fragment"
        )
    path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    return {"repo_id": repo, "variable": key, "revision": sha, "probe_path": path}


def live_origin(repo_id: str) -> str:
    binding = normalize_binding(repo_id, "SOURCE_SHA", "0" * 40, "/api/build-info")
    owner, name = binding["repo_id"].split("/", 1)
    host = re.sub(r"[^a-z0-9-]+", "-", f"{owner}-{name}".lower()).strip("-")
    if not host:
        raise SourceBindingError(f"Space id has no usable app hostname: {repo_id!r}")
    return f"https://{host}.hf.space"


_HF_API = "https://huggingface.co/api"
RUNTIME_JSON_MAX_BYTES = 1024 * 1024
JWT_JSON_MAX_BYTES = 64 * 1024
ERROR_BODY_MAX_BYTES = 16 * 1024
TOKEN_MAX_CHARS = 8192


class _ReadBoundaryError(SourceBindingError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("source identity read rejected: " + code)


def _read_origin(url: str) -> tuple[str, str, int]:
    try:
        if (not isinstance(url, str) or not url
                or any(ord(char) <= 32 or ord(char) == 127 for char in url)
                or "\\" in url):
            raise ValueError
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if (parsed.scheme != "https" or parsed.username is not None
                or parsed.password is not None or parsed.fragment
                or parsed.port not in (None, 443) or not host.isascii()
                or not re.fullmatch(r"[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?", host)):
            raise ValueError
        return "https", host, 443
    except (ValueError, TypeError, AttributeError):
        raise _ReadBoundaryError("UNTRUSTED_ORIGIN") from None


def _bearer(value: Any) -> str:
    if (not isinstance(value, str) or not value or len(value) > TOKEN_MAX_CHARS
            or any(ord(char) <= 32 or ord(char) >= 127 for char in value)):
        raise _ReadBoundaryError("INVALID_BEARER")
    return value


def _read_target(url: str) -> tuple[str, str]:
    """Use the same pure URL preparation as Requests before binding path/query."""
    try:
        prepared = requests.Request("GET", url).prepare()
        parsed = urlsplit(prepared.url)
        return parsed.path, parsed.query
    except Exception:
        raise _ReadBoundaryError("INVALID_TARGET") from None


class _ScopedReadAuth:
    """Override netrc/default auth without disabling proxy or CA environment trust."""

    def __init__(self, url: str, credential: str = "", *, hub_jwt: bool = False) -> None:
        self.origin = _read_origin(url)
        self.hub_path = urlsplit(url).path if hub_jwt else None
        if hub_jwt:
            parts = urlsplit(url).path.split("/")
            if (self.origin != ("https", "huggingface.co", 443)
                    or urlsplit(url).query or len(parts) != 6
                    or parts[:3] != ["", "api", "spaces"] or parts[-1] != "jwt"
                    or REPO_ID.fullmatch("/".join(parts[3:5])) is None):
                raise _ReadBoundaryError("UNTRUSTED_ORIGIN")
        elif re.fullmatch(r"[a-z0-9][a-z0-9-]*\.hf\.space", self.origin[1]) is None:
            raise _ReadBoundaryError("UNTRUSTED_ORIGIN")
        self.target = _read_target(url)
        self.credential = _bearer(credential) if credential else ""

    def __call__(self, request: Any) -> Any:
        if (request.method != "GET" or _read_origin(request.url) != self.origin
                or _read_target(request.url) != self.target):
            raise _ReadBoundaryError("CREDENTIAL_SCOPE")
        # Requests applies cookies before request auth. Explicit auth also prevents
        # its netrc fallback. Proxy credentials remain in the configured proxy
        # adapter path; an ambient origin-bound Proxy-Authorization is removed.
        for name in list(request.headers):
            if name.lower() in {"authorization", "cookie", "proxy-authorization", "host"}:
                del request.headers[name]
        if self.credential:
            request.headers["Authorization"] = "Bearer " + self.credential
        return request


class _ReadSession(requests.Session):
    def resolve_redirects(self, *args: Any, **kwargs: Any) -> Any:
        # Even allow_redirects=False normally prepares Response.next in Requests.
        # That preparation consumes a redirect body and can consult netrc. Do
        # neither: the bounded caller observes and rejects the original 3xx.
        return iter(())


def _remaining(deadline: float, monotonic: Callable[[], float], maximum: float) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise _ReadBoundaryError("DEADLINE_EXCEEDED")
    return min(maximum, remaining)


def _bounded_json_get(
    url: str, *, session: requests.Session, headers: Mapping[str, str],
    deadline: float, monotonic: Callable[[], float], body_limit: int,
    credential: str = "", hub_jwt: bool = False, maximum_timeout: float = 60.0,
) -> dict[str, Any]:
    """Bound bytes and admission time; socket/DNS time is not a hard wall deadline.

    Requests retains configured proxies and CA trust. No timeout worker is
    launched. A blocking DNS/socket operation may finish after the acceptance
    deadline, but its response cannot then be admitted.
    """
    auth = _ScopedReadAuth(url, credential, hub_jwt=hub_jwt)
    request_headers = dict(headers)
    request_headers["Accept-Encoding"] = "identity"
    response = None
    try:
        response = session.get(
            url, headers=request_headers, auth=auth, allow_redirects=False,
            stream=True, timeout=_remaining(deadline, monotonic, maximum_timeout),
        )
        _remaining(deadline, monotonic, maximum_timeout)
        if _read_origin(response.url) != auth.origin:
            raise _ReadBoundaryError("RESPONSE_ORIGIN")
        if _read_target(response.url) != auth.target:
            raise _ReadBoundaryError("RESPONSE_TARGET")
        status = response.status_code
        if type(status) is not int or not 100 <= status <= 599:
            raise _ReadBoundaryError("INVALID_STATUS")
        limit = body_limit if status == 200 else ERROR_BODY_MAX_BYTES
        header_items = list(response.headers.items())
        lengths = [value for name, value in header_items if name.lower() == "content-length"]
        encodings = [value for name, value in header_items if name.lower() == "content-encoding"]
        if (len(encodings) > 1 or (encodings and
                str(encodings[0]).strip().lower() not in {"", "identity"})):
            raise _ReadBoundaryError("CONTENT_ENCODING")
        declared = None
        if lengths:
            if (len(lengths) != 1 or not isinstance(lengths[0], str)
                    or re.fullmatch(r"[0-9]{1,20}", lengths[0].strip()) is None):
                raise _ReadBoundaryError("CONTENT_LENGTH")
            declared = int(lengths[0].strip())
            if declared > limit:
                raise _ReadBoundaryError("BODY_LIMIT")
        body = bytearray()
        while True:
            _remaining(deadline, monotonic, maximum_timeout)
            chunk = response.raw.read(min(16384, limit + 1 - len(body)))
            _remaining(deadline, monotonic, maximum_timeout)
            if not isinstance(chunk, bytes):
                raise _ReadBoundaryError("INVALID_BODY")
            if not chunk:
                break
            if len(body) + len(chunk) > limit:
                raise _ReadBoundaryError("BODY_LIMIT")
            body.extend(chunk)
        if declared is not None and len(body) != declared:
            raise _ReadBoundaryError("BODY_LENGTH_MISMATCH")
        payload = None
        if status == 200:
            try:
                payload = json.loads(bytes(body).decode("utf-8"))
            except (UnicodeError, ValueError):
                raise _ReadBoundaryError("INVALID_JSON") from None
        _remaining(deadline, monotonic, maximum_timeout)
        return {"http_status": status, "content_type": response.headers.get("content-type"),
                "bytes": len(body), "payload": payload}
    except _ReadBoundaryError:
        raise
    except Exception:
        # Provider exception text, URLs, headers and bodies may contain secrets.
        raise _ReadBoundaryError("TRANSPORT_UNAVAILABLE") from None
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass


def _space_jwt(
    repo_id: str, *, session: requests.Session, deadline: float,
    monotonic: Callable[[], float], cache: dict[str, str],
) -> str:
    """Read a capability for source identity, without asserting public availability."""
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        return ""
    if repo_id in cache:
        return cache[repo_id]
    result = _bounded_json_get(
        f"{_HF_API}/spaces/{repo_id}/jwt", session=session,
        headers={"Accept": "application/json", "User-Agent": "szl-hf-space-source-binding/1"},
        deadline=deadline, monotonic=monotonic, body_limit=JWT_JSON_MAX_BYTES,
        credential=token, hub_jwt=True, maximum_timeout=20.0,
    )
    if result["http_status"] != 200:
        raise _ReadBoundaryError("JWT_HTTP_" + str(result["http_status"]))
    payload = result["payload"]
    jwt = _bearer(payload.get("token") if isinstance(payload, Mapping) else None)
    cache[repo_id] = jwt
    return jwt


def _variable_value(value: Any) -> str | None:
    if isinstance(value, Mapping):
        observed = value.get("value")
    else:
        observed = getattr(value, "value", None)
    return str(observed) if observed is not None else None


def verify_variable(api: HfApi, binding: Mapping[str, str]) -> dict[str, Any]:
    values = api.get_space_variables(binding["repo_id"])
    if not isinstance(values, Mapping):
        raise SourceBindingError("HfApi.get_space_variables() did not return a mapping")
    item = values.get(binding["variable"])
    observed = _variable_value(item)
    if observed != binding["revision"]:
        raise SourceBindingError(
            f"Space variable readback mismatch for {binding['variable']}: "
            f"expected {binding['revision']!r}, observed {observed!r}"
        )
    return {
        "key": binding["variable"],
        "expected": binding["revision"],
        "observed": observed,
        "matched": True,
    }


def bind_variable(api: HfApi, binding: Mapping[str, str]) -> dict[str, Any]:
    api.add_space_variable(
        repo_id=binding["repo_id"],
        key=binding["variable"],
        value=binding["revision"],
        description=(
            "Exact protected GitHub source revision serving this Space. "
            "The reusable deployment contract fails closed on readback or runtime drift."
        ),
    )
    return verify_variable(api, binding)


def _probe_headers(binding: Mapping[str, str], attempt: int) -> dict[str, str]:
    """Return per-attempt transport identity without changing application routing."""
    return {
        "Accept": "application/json",
        "Cache-Control": "no-cache, no-store, max-age=0",
        "Pragma": "no-cache",
        "User-Agent": "szl-hf-space-source-binding/1",
        PROBE_SOURCE_HEADER: binding["revision"],
        PROBE_ATTEMPT_HEADER: str(attempt),
    }


def _reported_receipt_status(
    payload: Mapping[str, Any], expected_revision: str
) -> dict[str, Any]:
    """Validate a read-only receipt observation without requiring absence.

    A GET probe must never mint a receipt, but it may observe a release
    attestation that the runtime loaded at startup. An asserted receipt is
    admitted only when it is exact-source bound and has a canonical GitHub
    OIDC attestation reference.
    """

    minted = payload.get("receipt_minted")
    if minted is False:
        return {
            "minted": False,
            "valid": True,
            "state": "NOT_REPORTED_AS_MINTED",
        }
    if minted is not True:
        return {
            "minted": minted,
            "valid": False,
            "state": "INVALID_RECEIPT_FLAG",
        }

    receipt = payload.get("release_receipt")
    if not isinstance(receipt, Mapping):
        return {
            "minted": True,
            "valid": False,
            "state": "MISSING_RELEASE_RECEIPT",
        }

    source_revision = str(receipt.get("source_revision") or "").lower()
    subject = str(receipt.get("subject") or "")
    digest = str(receipt.get("subject_sha256") or "").lower()
    attestation_id = str(receipt.get("attestation_id") or "")
    attestation_url = str(receipt.get("attestation_url") or "")
    parsed = urlsplit(attestation_url)
    parts = [part for part in parsed.path.split("/") if part]
    canonical_url = (
        parsed.scheme == "https"
        and parsed.netloc == "github.com"
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and len(parts) == 4
        and parts[2] == "attestations"
        and parts[3] == attestation_id
    )
    valid = (
        str(receipt.get("state") or "").upper() == "GITHUB_OIDC_ATTESTED"
        and source_revision == expected_revision
        and subject == "hf-deploy-manifest.json"
        and SHA256.fullmatch(digest) is not None
        and ATTESTATION_ID.fullmatch(attestation_id) is not None
        and canonical_url
    )
    return {
        "minted": True,
        "valid": valid,
        "state": "GITHUB_OIDC_ATTESTED" if valid else "INVALID_RELEASE_RECEIPT",
    }


def _runtime_probe_observation(
    binding: Mapping[str, str], *, session: requests.Session, attempt: int,
    deadline: float, monotonic: Callable[[], float], jwt_cache: dict[str, str],
) -> dict[str, Any]:
    canonical_url = live_origin(binding["repo_id"]) + binding["probe_path"]
    observation: dict[str, Any] = {
        "attempt": attempt,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "url": canonical_url,
        "expected_revision": binding["revision"],
        "request_identity": "headers",
        "authentication": "anonymous",
        "availability_scope": "not_evaluated",
        "matched": False,
    }
    probe_headers = _probe_headers(binding, attempt)
    try:
        result = _bounded_json_get(
            canonical_url, session=session, headers=probe_headers, deadline=deadline,
            monotonic=monotonic, body_limit=RUNTIME_JSON_MAX_BYTES,
        )
        observation["anonymous_http_status"] = result["http_status"]
        if result["http_status"] in (401, 404):
            # An auth challenge is not proof of private visibility. A read JWT
            # may establish identity, never anonymous/public availability.
            jwt = _space_jwt(binding["repo_id"], session=session, deadline=deadline,
                             monotonic=monotonic, cache=jwt_cache)
            if jwt:
                observation["authentication"] = "space_read_jwt"
                result = _bounded_json_get(
                    canonical_url, session=session, headers=probe_headers,
                    deadline=deadline, monotonic=monotonic,
                    body_limit=RUNTIME_JSON_MAX_BYTES, credential=jwt,
                )
    except _ReadBoundaryError as exc:
        observation.update({"error_type": type(exc).__name__, "error_code": exc.code,
                            "error": "source revision probe read failed"})
        return observation

    observation.update({key: result[key] for key in ("http_status", "content_type", "bytes")})
    if result["http_status"] != 200:
        observation["error"] = "source revision probe did not return HTTP 200"
        return observation
    payload = result["payload"]
    if not isinstance(payload, Mapping):
        observation["error"] = "source revision probe JSON is not an object"
        return observation
    build = payload.get("build")
    if not isinstance(build, Mapping):
        observation["error"] = "source revision probe lacks a build object"
        return observation
    observed = str(build.get("revision") or "").lower()
    state = str(build.get("state") or "").upper()
    receipt = _reported_receipt_status(payload, binding["revision"])
    matched = (observed == binding["revision"] and state == "OBSERVED"
               and receipt["valid"] is True)
    observation.update({
        "build_state": state, "observed_revision": observed,
        "receipt_minted": receipt["minted"], "receipt_state": receipt["state"],
        "receipt_valid": receipt["valid"], "matched": matched,
    })
    if not matched:
        observation["error"] = "runtime source binding mismatch"
    return observation


def verify_runtime_probe(
    binding: Mapping[str, str], *, session: requests.Session | None = None,
    timeout_seconds: float = 180.0, interval_seconds: float = 5.0,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if not 0 <= timeout_seconds <= 900:
        raise SourceBindingError("runtime probe timeout must be between 0 and 900 seconds")
    if not 0 < interval_seconds <= 60:
        raise SourceBindingError("runtime probe interval must be greater than 0 and at most 60 seconds")
    if session is not None and not isinstance(session, _ReadSession):
        raise SourceBindingError("source identity requires a redirect-blocking read session")
    owned_session = session is None
    session = session if session is not None else _ReadSession()
    started = monotonic()
    # Preserve timeout=0 as one immediate attempt, with at most a one-second
    # acceptance budget shared by all of that attempt's requests.
    deadline = started + (timeout_seconds if timeout_seconds > 0 else 1.0)
    observations: list[dict[str, Any]] = []
    jwt_cache: dict[str, str] = {}  # no capability survives this verification call
    try:
        while True:
            observation = _runtime_probe_observation(
                binding, session=session, attempt=len(observations) + 1,
                deadline=deadline, monotonic=monotonic, jwt_cache=jwt_cache,
            )
            elapsed = max(0.0, monotonic() - started)
            if monotonic() >= deadline:
                observation.update({"matched": False, "error_code": "DEADLINE_EXCEEDED",
                                    "error": "source revision probe acceptance deadline exceeded"})
            observations.append(observation)
            if observation["matched"]:
                return {
                    "url": live_origin(binding["repo_id"]) + binding["probe_path"],
                    "expected_revision": binding["revision"],
                    "attempt_count": len(observations),
                    "converged_after_seconds": round(elapsed, 3),
                    "observations": observations,
                    "availability_scope": "not_evaluated",
                    "matched": True,
                }
            remaining = deadline - monotonic()
            if timeout_seconds == 0 or remaining <= 0:
                evidence = {
                    "url": live_origin(binding["repo_id"]) + binding["probe_path"],
                    "expected_revision": binding["revision"],
                    "attempt_count": len(observations),
                    "elapsed_seconds": round(elapsed, 3),
                    "timeout_seconds": timeout_seconds,
                    "interval_seconds": interval_seconds,
                    "observations": observations,
                    "availability_scope": "not_evaluated",
                    "matched": False,
                }
                last = observations[-1]
                raise SourceBindingError(
                    "runtime source binding did not converge before the bounded deadline: "
                    f"expected={binding['revision']!r}; "
                    f"observed={last.get('observed_revision')!r}; "
                    f"state={last.get('build_state')!r}; attempts={len(observations)}",
                    evidence=evidence,
                )
            sleep(min(interval_seconds, remaining))
    finally:
        if owned_session:
            session.close()


def write_report(path: str, report: Mapping[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    binding = normalize_binding(args.repo_id, args.variable, args.revision, args.probe_path)
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SourceBindingError("HF_TOKEN is required for Space variable bind/readback")
    api = HfApi(token=token)
    variable = bind_variable(api, binding) if args.mode == "bind" else verify_variable(api, binding)
    runtime = (
        verify_runtime_probe(
            binding,
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.interval_seconds,
        )
        if args.mode == "verify"
        else {"status": "NOT_RUN"}
    )
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "repo_id": binding["repo_id"],
        "source_revision": binding["revision"],
        "source_revision_variable": binding["variable"],
        "probe_path": binding["probe_path"],
        "variable_readback": variable,
        "runtime_probe": runtime,
        "ok": True,
        "boundaries": [
            "Only one non-secret Space variable may be added or updated.",
            "Verification uses supported HfApi variable readback and bounded same-host GET convergence.",
            "Probe retries preserve the canonical application URL and carry attempt identity only in headers.",
            "No Space hardware, visibility, sleep policy, secret, model, dataset, or branch state is changed.",
            "Authenticated source identity is reported separately from anonymous public availability; visibility is never inferred or changed.",
            "Runtime and JWT JSON reads share byte and acceptance-time bounds while preserving configured proxy and CA trust.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("bind", "verify"), required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--variable", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--probe-path", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    args = parser.parse_args()
    try:
        report = run(args)
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema": REPORT_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": args.mode,
            "repo_id": args.repo_id,
            "source_revision": args.revision,
            "source_revision_variable": args.variable,
            "probe_path": args.probe_path,
            "ok": False,
            "fatal": f"{type(exc).__name__}: {exc}",
        }
        if isinstance(exc, SourceBindingError) and exc.evidence is not None:
            report["runtime_probe"] = exc.evidence
        write_report(args.output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1
    write_report(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
