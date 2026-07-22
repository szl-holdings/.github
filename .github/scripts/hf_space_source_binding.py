#!/usr/bin/env python3
"""Bind and verify an exact protected source revision in a Hugging Face Space.

This module is deliberately separate from file publication. The reusable deployer
already derives, pushes, and byte-attests the Dockerfile COPY set. This contract
adds the missing runtime identity plane:

1. add/update one non-secret Space variable with the exact checked-out Git SHA;
2. independently read the variable back through the supported HfApi client;
3. after deployment, GET a same-host standard build-info endpoint and require
   ``build.state=OBSERVED`` plus ``build.revision=<exact Git SHA>``.

It never changes Space hardware, visibility, sleep policy, secrets, models, or data.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

import requests
from huggingface_hub import HfApi

SHA40 = re.compile(r"^[0-9a-f]{40}$")
VARIABLE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
REPO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")
REPORT_SCHEMA = "szl.hf-space-source-binding/v1"


class SourceBindingError(RuntimeError):
    """The source-binding contract cannot be established or verified."""


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


def verify_runtime_probe(
    binding: Mapping[str, str], *, session: requests.Session | None = None
) -> dict[str, Any]:
    session = session or requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "User-Agent": "szl-hf-space-source-binding/1",
        }
    )
    url = live_origin(binding["repo_id"]) + binding["probe_path"]
    response = session.get(url, allow_redirects=False, timeout=60)
    if response.status_code != 200:
        raise SourceBindingError(
            f"source revision probe returned HTTP {response.status_code}: {url}"
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise SourceBindingError("source revision probe did not return JSON") from exc
    if not isinstance(payload, Mapping):
        raise SourceBindingError("source revision probe JSON is not an object")
    build = payload.get("build")
    if not isinstance(build, Mapping):
        raise SourceBindingError("source revision probe lacks a build object")
    observed = str(build.get("revision") or "").lower()
    state = str(build.get("state") or "").upper()
    receipt_minted = payload.get("receipt_minted")
    if observed != binding["revision"] or state != "OBSERVED" or receipt_minted is not False:
        raise SourceBindingError(
            "runtime source binding mismatch: "
            f"state={state!r}; expected={binding['revision']!r}; observed={observed!r}; "
            f"receipt_minted={receipt_minted!r}"
        )
    return {
        "url": url,
        "http_status": response.status_code,
        "content_type": response.headers.get("content-type"),
        "bytes": len(response.content),
        "build_state": state,
        "expected_revision": binding["revision"],
        "observed_revision": observed,
        "receipt_minted": False,
        "matched": True,
    }


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
    runtime = verify_runtime_probe(binding) if args.mode == "verify" else {"status": "NOT_RUN"}
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
            "Verification uses supported HfApi variable readback and one same-host GET.",
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
        write_report(args.output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1
    write_report(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
