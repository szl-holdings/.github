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
    binding: Mapping[str, str],
    *,
    session: requests.Session,
    attempt: int,
    request_timeout_seconds: float,
) -> dict[str, Any]:
    canonical_url = live_origin(binding["repo_id"]) + binding["probe_path"]
    observation: dict[str, Any] = {
        "attempt": attempt,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "url": canonical_url,
        "expected_revision": binding["revision"],
        "request_identity": "headers",
        "matched": False,
    }
    try:
        response = session.get(
            canonical_url,
            allow_redirects=False,
            timeout=request_timeout_seconds,
            headers=_probe_headers(binding, attempt),
        )
    except Exception as exc:  # noqa: BLE001 - preserve a bounded transport observation
        observation.update(
            {
                "error_type": type(exc).__name__,
                "error": "source revision probe transport failure",
            }
        )
        return observation

    observation.update(
        {
            "http_status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "bytes": len(response.content),
        }
    )
    if response.status_code != 200:
        observation["error"] = "source revision probe did not return HTTP 200"
        return observation
    try:
        payload = response.json()
    except ValueError:
        observation["error"] = "source revision probe did not return JSON"
        return observation
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
    matched = (
        observed == binding["revision"]
        and state == "OBSERVED"
        and receipt["valid"] is True
    )
    observation.update(
        {
            "build_state": state,
            "observed_revision": observed,
            "receipt_minted": receipt["minted"],
            "receipt_state": receipt["state"],
            "receipt_valid": receipt["valid"],
            "matched": matched,
        }
    )
    if not matched:
        observation["error"] = "runtime source binding mismatch"
    return observation


def verify_runtime_probe(
    binding: Mapping[str, str],
    *,
    session: requests.Session | None = None,
    timeout_seconds: float = 180.0,
    interval_seconds: float = 5.0,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if not 0 <= timeout_seconds <= 900:
        raise SourceBindingError("runtime probe timeout must be between 0 and 900 seconds")
    if not 0 < interval_seconds <= 60:
        raise SourceBindingError("runtime probe interval must be greater than 0 and at most 60 seconds")
    session = session or requests.Session()
    started = monotonic()
    deadline = started + timeout_seconds
    observations: list[dict[str, Any]] = []
    while True:
        now = monotonic()
        remaining = max(0.0, deadline - now)
        observation = _runtime_probe_observation(
            binding,
            session=session,
            attempt=len(observations) + 1,
            request_timeout_seconds=max(1.0, min(60.0, remaining or 1.0)),
        )
        observations.append(observation)
        elapsed = max(0.0, monotonic() - started)
        if observation["matched"]:
            return {
                "url": live_origin(binding["repo_id"]) + binding["probe_path"],
                "expected_revision": binding["revision"],
                "attempt_count": len(observations),
                "converged_after_seconds": round(elapsed, 3),
                "observations": observations,
                "matched": True,
            }
        remaining = deadline - monotonic()
        if remaining <= 0:
            evidence = {
                "url": live_origin(binding["repo_id"]) + binding["probe_path"],
                "expected_revision": binding["revision"],
                "attempt_count": len(observations),
                "elapsed_seconds": round(elapsed, 3),
                "timeout_seconds": timeout_seconds,
                "interval_seconds": interval_seconds,
                "observations": observations,
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
