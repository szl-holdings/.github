#!/usr/bin/env python3
"""Verify a PR against the immutable source-bound live Hugging Face baseline.

A manually committed GitHub/Hugging Face lock can become stale after a successful
protected deployment. A source-bound Space already exposes stronger current
identity planes:

* Hugging Face metadata supplies exact repository and running-runtime SHAs;
* a same-host, read-only build-info route supplies the exact protected Git SHA;
* Dockerfile-managed bytes can be compared at those two immutable revisions.

This verifier observes both live planes more than once with cache bypass, requires
stable exact values, proves the observed Git source is an ancestor of the pull
request base, compares the exact deployed pair without an allowlist, and reports
the candidate's managed-file delta without deploying it. It performs no mutation.
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
from typing import Any, Mapping

import hf_module_drift_check as drift

REPORT_SCHEMA = 1
HF_REPO_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$"
)
PROBE_OBSERVATIONS = 2
PROBE_HEADERS = {
    "Accept": "application/json",
    "Cache-Control": "no-cache, no-store, max-age=0",
    "Pragma": "no-cache",
    "User-Agent": "hf-source-bound-baseline/1",
}


class SourceBaselineError(RuntimeError):
    """The source-bound live baseline cannot be verified."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def require_probe_path(value: str) -> str:
    raw = str(value or "").strip()
    parsed = urllib.parse.urlsplit(raw)
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
        or parsed.fragment
    ):
        raise ValueError(
            "source-probe-path must be a same-host absolute path without a fragment"
        )
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def space_origin(hf_repo: str) -> str:
    repo = str(hf_repo or "").strip()
    if HF_REPO_RE.fullmatch(repo) is None:
        raise ValueError(f"invalid Hugging Face Space id: {repo!r}")
    owner, name = repo.split("/", 1)
    host = re.sub(r"[^a-z0-9-]+", "-", f"{owner}-{name}".lower()).strip("-")
    if not host:
        raise ValueError(f"Space id has no usable app hostname: {repo!r}")
    return f"https://{host}.hf.space"


def _cache_busted_url(origin: str, probe_path: str, ordinal: int) -> str:
    parsed = urllib.parse.urlsplit(origin + probe_path)
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    pairs.append(("cache_bust", f"{time.time_ns()}-{os.getpid()}-{ordinal}"))
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(pairs), "")
    )


def _fetch_json_no_redirect(url: str) -> tuple[int, Mapping[str, Any], dict[str, str]]:
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, headers=PROBE_HEADERS, method="GET")
    try:
        with opener.open(request, timeout=60) as response:
            status = int(getattr(response, "status", 0) or 0)
            body = response.read()
            headers = {str(key).lower(): str(value) for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raise SourceBaselineError(
            f"source probe returned HTTP {exc.code} without redirect acceptance: {url}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceBaselineError(f"source probe request failed: {url}: {exc}") from exc
    if status != 200:
        raise SourceBaselineError(f"source probe returned HTTP {status}: {url}")
    if "application/json" not in headers.get("content-type", "").lower():
        raise SourceBaselineError("source probe did not return application/json")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SourceBaselineError("source probe returned invalid JSON") from exc
    if not isinstance(payload, Mapping):
        raise SourceBaselineError("source probe JSON is not an object")
    return status, payload, headers


def source_probe_state(
    hf_repo: str,
    probe_path: str,
    observation_count: int = PROBE_OBSERVATIONS,
) -> dict[str, Any]:
    if observation_count < 2:
        raise ValueError("source probe requires at least two observations")
    path = require_probe_path(probe_path)
    origin = space_origin(hf_repo)
    observations: list[dict[str, Any]] = []
    for ordinal in range(1, observation_count + 1):
        url = _cache_busted_url(origin, path, ordinal)
        observed_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        try:
            status, payload, headers = _fetch_json_no_redirect(url)
            build = payload.get("build")
            revision = (
                str(build.get("revision") or "").lower()
                if isinstance(build, Mapping)
                else ""
            )
            state = (
                str(build.get("state") or "").upper()
                if isinstance(build, Mapping)
                else ""
            )
            observations.append(
                {
                    "ordinal": ordinal,
                    "status": "observed",
                    "observed_utc": observed_utc,
                    "http_status": status,
                    "source_revision": revision,
                    "build_state": state,
                    "receipt_minted": payload.get("receipt_minted"),
                    "content_type": headers.get("content-type"),
                }
            )
        except SourceBaselineError as exc:
            observations.append(
                {
                    "ordinal": ordinal,
                    "status": "unavailable",
                    "observed_utc": observed_utc,
                    "detail": str(exc),
                }
            )

    observed = [item for item in observations if item.get("status") == "observed"]
    identities = {
        (
            item.get("source_revision"),
            item.get("build_state"),
            item.get("receipt_minted"),
        )
        for item in observed
    }
    stable = (
        len(observed) == observation_count
        and len(identities) == 1
        and drift.FULL_SHA_RE.fullmatch(str(observed[0].get("source_revision") or ""))
        is not None
        and observed[0].get("build_state") == "OBSERVED"
        and observed[0].get("receipt_minted") is False
    )
    if stable:
        observation_status = "stable"
        source_revision = str(observed[0]["source_revision"])
    elif len(observed) == observation_count:
        observation_status = "inconsistent"
        source_revision = None
    else:
        observation_status = "unavailable"
        source_revision = None
    return {
        "observation_status": observation_status,
        "observation_count": observation_count,
        "required_observation_count": observation_count,
        "source_revision": source_revision,
        "probe_path": path,
        "origin": origin,
        "observations": observations,
    }


def _minimal_pair_report(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "status": "drift",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "github_repo": args.github_repo,
        "hf_repo": args.hf_repo,
        "ref": args.ref,
        "github_ref": None,
        "hf_ref": None,
        "dockerfile_path": args.dockerfile_path,
        "copy_sources": 0,
        "files_compared": 0,
        "error_count": 0,
        "warn_count": 0,
        "findings": [],
    }


def source_bound_baseline_compare(args: argparse.Namespace):
    trusted_base_ref = drift.require_full_sha(
        args.trusted_base_ref, "trusted base GitHub SHA"
    )
    candidate_ref = (
        drift.require_full_sha(args.candidate_ref, "candidate GitHub SHA")
        if args.candidate_ref
        else ""
    )
    probe_path = require_probe_path(args.source_probe_path)
    live_state = drift.hf_space_state(args.hf_repo)
    probe_state = source_probe_state(args.hf_repo, probe_path)

    contract_errors: list[dict[str, Any]] = []
    live_stable = live_state.get("observation_status") == "stable"
    live_head = str(live_state.get("head_sha") or "")
    live_runtime = str(live_state.get("runtime_sha") or "")
    live_stage = str(live_state.get("runtime_stage") or "")
    if not live_stable:
        contract_errors.append(
            {
                "path": "(hf-metadata)",
                "kind": "live-hf-metadata-not-stable",
                "severity": "error",
                "detail": (
                    "live Hugging Face repository/runtime identity did not produce "
                    "two stable cache-bypassed observations"
                ),
            }
        )
    if drift.FULL_SHA_RE.fullmatch(live_head) is None:
        contract_errors.append(
            {
                "path": "(hf-head)",
                "kind": "live-hf-head-not-immutable",
                "severity": "error",
                "actual": live_head or None,
                "detail": "live Hugging Face head is not an exact 40-character SHA",
            }
        )
    if drift.FULL_SHA_RE.fullmatch(live_runtime) is None:
        contract_errors.append(
            {
                "path": "(hf-runtime)",
                "kind": "live-hf-runtime-not-immutable",
                "severity": "error",
                "actual": live_runtime or None,
                "detail": "running Space revision is not an exact 40-character SHA",
            }
        )
    if live_head and live_runtime and live_head != live_runtime:
        contract_errors.append(
            {
                "path": "(hf-runtime)",
                "kind": "live-hf-head-runtime-split",
                "severity": "error",
                "head_sha": live_head,
                "runtime_sha": live_runtime,
                "detail": "Space runtime does not serve the current repository head",
            }
        )
    if live_stage != "RUNNING":
        contract_errors.append(
            {
                "path": "(hf-runtime)",
                "kind": "live-hf-runtime-not-running",
                "severity": "error",
                "expected": "RUNNING",
                "actual": live_stage or None,
                "detail": "Space is not RUNNING at the observed immutable revision",
            }
        )

    source_sha = str(probe_state.get("source_revision") or "")
    if probe_state.get("observation_status") != "stable":
        contract_errors.append(
            {
                "path": "(source-probe)",
                "kind": "source-probe-not-stable",
                "severity": "error",
                "detail": (
                    "build-info did not produce two stable, read-only exact-source "
                    "observations"
                ),
            }
        )
    ancestry_status = None
    if drift.FULL_SHA_RE.fullmatch(source_sha) is not None:
        is_ancestor, ancestry_status = drift.github_ref_is_ancestor(
            args.github_repo, source_sha, trusted_base_ref
        )
        if not is_ancestor:
            contract_errors.append(
                {
                    "path": "(source-probe)",
                    "kind": "observed-source-not-ancestor",
                    "severity": "error",
                    "observed_source_sha": source_sha,
                    "trusted_base_ref": trusted_base_ref,
                    "detail": (
                        "live build-info source is not an ancestor of the exact pull "
                        "request base"
                    ),
                }
            )
    else:
        contract_errors.append(
            {
                "path": "(source-probe)",
                "kind": "observed-source-not-immutable",
                "severity": "error",
                "actual": source_sha or None,
                "detail": "build-info source is not an exact 40-character Git SHA",
            }
        )

    pair_report = _minimal_pair_report(args)
    drift_errors: list[dict[str, Any]] = []
    warns: list[dict[str, Any]] = []
    can_compare = (
        live_stable
        and drift.FULL_SHA_RE.fullmatch(live_head) is not None
        and live_head == live_runtime
        and live_stage == "RUNNING"
        and probe_state.get("observation_status") == "stable"
        and drift.FULL_SHA_RE.fullmatch(source_sha) is not None
        and not any(error["kind"] == "observed-source-not-ancestor" for error in contract_errors)
    )
    if can_compare:
        baseline_args = argparse.Namespace(**vars(args))
        baseline_args.ref = source_sha
        baseline_args.github_ref = source_sha
        baseline_args.hf_ref = live_head
        baseline_args.github_remote = True
        baseline_args.allow = ""
        baseline_args.siblings = []
        pair_report, drift_errors, warns = drift.compare(
            baseline_args, allow={}, include_dockerfile=True
        )

    candidate_report = None
    if candidate_ref and drift.FULL_SHA_RE.fullmatch(source_sha) is not None:
        candidate_report = drift.candidate_managed_delta(
            args.github_repo,
            source_sha,
            candidate_ref,
            args.dockerfile_path,
        )
        for source in candidate_report["new_unresolved_sources"]:
            contract_errors.append(
                {
                    "path": source,
                    "kind": "candidate-unresolved-copy-source",
                    "severity": "error",
                    "detail": (
                        "candidate Dockerfile introduces a managed source that does "
                        "not resolve at the exact candidate revision"
                    ),
                }
            )

    errors = contract_errors + drift_errors
    findings = errors + warns
    findings.sort(
        key=lambda entry: (
            entry.get("severity") != "error",
            entry.get("path", ""),
        )
    )
    pair_report.update(
        {
            "mode": "source-bound-live-baseline",
            "status": "drift" if errors else "ok",
            "trusted_base_ref": trusted_base_ref,
            "candidate_ref": candidate_ref or None,
            "source_probe": probe_state,
            "observed_source_sha": source_sha or None,
            "observed_source_ancestry_status": ancestry_status,
            "live_hf": live_state,
            "allowlist_used": False,
            "candidate_plan_status": (
                candidate_report["status"] if candidate_report else "not-requested"
            ),
            "error_count": len(errors),
            "warn_count": len(warns),
            "findings": findings,
        }
    )
    return pair_report, errors, warns, candidate_report


def write_report(path: str, report: Mapping[str, Any] | None) -> None:
    if not path or report is None:
        return
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-repo", required=True)
    parser.add_argument("--hf-repo", required=True)
    parser.add_argument("--trusted-base-ref", required=True)
    parser.add_argument("--candidate-ref", default="")
    parser.add_argument("--dockerfile-path", default="Dockerfile")
    parser.add_argument("--source-probe-path", default="/api/build-info")
    parser.add_argument("--report-out", default="")
    parser.add_argument("--candidate-report-out", default="")
    args = parser.parse_args()
    args.repo_root = "."
    args.ref = "main"
    args.github_ref = ""
    args.hf_ref = ""
    args.github_remote = True
    args.allow = ""
    args.siblings = []
    try:
        report, errors, warns, candidate_report = source_bound_baseline_compare(args)
    except (
        OSError,
        RuntimeError,
        ValueError,
        json.JSONDecodeError,
        drift.TransientHTTPError,
    ) as exc:
        report = {
            "schema": REPORT_SCHEMA,
            "mode": "source-bound-live-baseline",
            "status": "error",
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "github_repo": args.github_repo,
            "hf_repo": args.hf_repo,
            "trusted_base_ref": args.trusted_base_ref,
            "candidate_ref": args.candidate_ref or None,
            "allowlist_used": False,
            "error_count": 1,
            "warn_count": 0,
            "findings": [
                {
                    "path": "(source-bound-baseline)",
                    "kind": "source-bound-contract-error",
                    "severity": "error",
                    "detail": str(exc),
                }
            ],
        }
        write_report(args.report_out, report)
        print(f"::error title=Source-bound HF baseline::{exc}")
        return 1

    drift.print_pair(report, errors, warns, args.github_repo, args.hf_repo, "main")
    drift.print_candidate_plan(candidate_report)
    write_report(args.report_out, report)
    write_report(args.candidate_report_out, candidate_report)
    if errors:
        print(
            "\nFAIL: the immutable source-bound live baseline or candidate deploy "
            "plan violated its contract. The candidate was not deployed."
        )
        return 1
    print(
        "\nOK: stable live HF metadata, read-only exact source identity, and the "
        "byte-identical deployed pair were verified; candidate changes were reported "
        "without deployment."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
