#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Publish the exact SZL Vertical Frontier source to one Hugging Face Space.

The publisher owns a single source/target pair:

    szl-holdings/vertical-services/frontier
        -> SZLHOLDINGS/vertical-frontier

It validates and materializes a bounded file closure, verifies the current
GitHub default-branch tip immediately before each provider mutation, creates the
public Docker Space only on an exact 404, commits only changed bytes, binds the
source revision as a Space variable, restarts the runtime, verifies every byte,
and exercises the public no-execution routes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, Iterable, Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SOURCE_REPOSITORY: Final = "szl-holdings/vertical-services"
TARGET_REPOSITORY: Final = "SZLHOLDINGS/vertical-frontier"
DEFAULT_RUNTIME_URL: Final = "https://szlholdings-vertical-frontier.hf.space"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
MAX_HTTP_BYTES: Final = 4 * 1024 * 1024
REQUIRED_SOURCE_FILES: Final = (
    "app.py",
    "runtime.py",
    "model_gateway.py",
    "kernel_engine.py",
    "verticals.json",
    "README.md",
    "Dockerfile.runtime",
    ".dockerignore",
    "static/index.html",
    "static/base.css",
    "static/themes.css",
    "static/app.js",
)
SPACE_FRONTMATTER: Final = """---
title: SZL Vertical Frontier
emoji: 🧬
colorFrom: gray
colorTo: indigo
sdk: docker
app_port: 7860
pinned: true
license: apache-2.0
short_description: Eight original governed AI command systems.
tags:
  - governed-ai
  - ai-governance
  - provenance
  - vertical-ai
  - evidence
  - human-in-the-loop
  - szl-holdings
---
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_sha(value: str, label: str) -> str:
    normalized = value.strip().lower()
    if not SHA40.fullmatch(normalized):
        raise ValueError(f"{label} must be an exact 40-character commit SHA")
    return normalized


def source_files(root: Path) -> list[Path]:
    files = [root / relative for relative in REQUIRED_SOURCE_FILES]
    missing = [str(path.relative_to(root)) for path in files if not path.is_file()]
    if missing:
        raise ValueError(f"missing Vertical Frontier source files: {missing!r}")
    return files


def validate_source(root: Path) -> dict[str, Any]:
    root = root.resolve()
    files = source_files(root)
    registry = json.loads((root / "verticals.json").read_text(encoding="utf-8"))
    if registry.get("schema") != "szl.vertical-frontier.v1":
        raise ValueError("unexpected vertical registry schema")
    verticals = registry.get("verticals")
    if not isinstance(verticals, list) or len(verticals) != 8:
        raise ValueError("Vertical Frontier must expose exactly eight verticals")
    slugs = [row.get("slug") for row in verticals if isinstance(row, dict)]
    expected = {"a11oy", "killinchu", "lyte", "sentra", "terra", "puriq", "prism", "anatomy"}
    if set(slugs) != expected or len(slugs) != len(set(slugs)):
        raise ValueError(f"unexpected vertical slug set: {slugs!r}")
    authority = registry.get("authority")
    if not isinstance(authority, dict):
        raise ValueError("authority contract is missing")
    required_authority = {
        "model_may_authorize": False,
        "kernel_may_authorize": False,
        "human_binding_required": True,
        "public_effectors_enabled": False,
        "lambda_uniqueness": "CONJECTURE_1_OPEN",
    }
    for key, expected_value in required_authority.items():
        if authority.get(key) != expected_value:
            raise ValueError(f"authority contract drift: {key}")

    dockerfile = (root / "Dockerfile.runtime").read_text(encoding="utf-8")
    required_docker = (
        "FROM mirror.gcr.io/library/python:3.12-slim",
        "USER 10001:10001",
        'ENV PYTHONDONTWRITEBYTECODE=1',
        "SZL_INFERENCE_MODE=route_only",
        'CMD ["python", "-I", "-P", "runtime.py"]',
    )
    missing_docker = [fragment for fragment in required_docker if fragment not in dockerfile]
    if missing_docker:
        raise ValueError(f"runtime Dockerfile contract drift: {missing_docker!r}")

    app_text = (root / "app.py").read_text(encoding="utf-8")
    runtime_text = (root / "runtime.py").read_text(encoding="utf-8")
    gateway_text = (root / "model_gateway.py").read_text(encoding="utf-8")
    kernel_text = (root / "kernel_engine.py").read_text(encoding="utf-8")
    static_html = (root / "static/index.html").read_text(encoding="utf-8")
    static_css = (root / "static/base.css").read_text(encoding="utf-8")
    theme_css = (root / "static/themes.css").read_text(encoding="utf-8")
    static_js = (root / "static/app.js").read_text(encoding="utf-8")

    required_code = {
        "app": (
            '"authorization": "NONE"',
            '"execution_performed": False',
            '"public_effectors_enabled": False',
        ),
        "runtime": (
            "szl.vertical-decision-receipt.v2",
            '"model_inference_attempted"',
            '"human_operator_binding_still_required": True',
        ),
        "gateway": (
            '"tools": []',
            "MODEL_TOOL_CALLS_REFUSED",
            "SZL_INFERENCE_ALLOWED_HOSTS",
        ),
        "kernel": (
            "EMBEDDED_REFERENCE_ONLY",
            "CONJECTURE_1_OPEN",
            '"external_kernel_artifact_loaded": False',
        ),
        "html": (
            'href="#content"',
            'aria-label="Primary"',
            'aria-live="polite"',
        ),
        "css": ("prefers-reduced-motion", "forced-colors", "min-height: 2.85rem"),
        "themes": (
            ".decision-ribbon",
            ".theater-map",
            ".signal-waterfall",
            ".exposure-field",
            ".parcel-scene",
            ".research-terminal",
            ".citation-scene",
            ".anatomy-scene",
        ),
        "javascript": (
            "renderDecisionRibbon",
            "renderTheaterMap",
            "renderSignalWaterfall",
            "renderExposureGraph",
            "renderParcelStack",
            "renderResearchTerminal",
            "renderCitationRail",
            "renderOrganBody",
        ),
    }
    documents = {
        "app": app_text,
        "runtime": runtime_text,
        "gateway": gateway_text,
        "kernel": kernel_text,
        "html": static_html,
        "css": static_css,
        "themes": theme_css,
        "javascript": static_js,
    }
    missing_code = {
        name: [fragment for fragment in fragments if fragment not in documents[name]]
        for name, fragments in required_code.items()
    }
    missing_code = {name: values for name, values in missing_code.items() if values}
    if missing_code:
        raise ValueError(f"Vertical Frontier source contract drift: {missing_code!r}")

    return {
        "schema": "szl.vertical-frontier-source-validation.v1",
        "state": "VERIFIED",
        "root": str(root),
        "verticals": slugs,
        "files": {
            str(path.relative_to(root)): {
                "bytes": path.stat().st_size,
                "sha256": sha256_bytes(path.read_bytes()),
            }
            for path in files
        },
        "registry_sha256": sha256_bytes(canonical_json(registry)),
        "authority": required_authority,
    }


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def materialize(
    *,
    source_root: Path,
    destination: Path,
    source_sha: str,
    publisher_sha: str,
) -> dict[str, Any]:
    source_sha = require_sha(source_sha, "source SHA")
    publisher_sha = require_sha(publisher_sha, "publisher SHA")
    validation = validate_source(source_root)
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("materialization destination must be empty")
    destination.mkdir(parents=True, exist_ok=True)

    mapping = {
        "Dockerfile.runtime": "Dockerfile",
        ".dockerignore": ".dockerignore",
        "app.py": "app.py",
        "runtime.py": "runtime.py",
        "model_gateway.py": "model_gateway.py",
        "kernel_engine.py": "kernel_engine.py",
        "verticals.json": "verticals.json",
        "static/index.html": "static/index.html",
        "static/base.css": "static/base.css",
        "static/themes.css": "static/themes.css",
        "static/app.js": "static/app.js",
    }
    for source_name, target_name in mapping.items():
        _copy_file(source_root / source_name, destination / target_name)

    readme = (source_root / "README.md").read_text(encoding="utf-8")
    if readme.startswith("---\n"):
        end = readme.find("\n---\n", 4)
        if end < 0:
            raise ValueError("source README frontmatter is malformed")
        readme = readme[end + 5 :].lstrip("\n")
    (destination / "README.md").write_text(SPACE_FRONTMATTER + "\n" + readme, encoding="utf-8")

    deployment = {
        "schema": "szl.vertical-frontier-deployment.v1",
        "source_repository": SOURCE_REPOSITORY,
        "source_subdirectory": "frontier",
        "source_revision": source_sha,
        "publisher_repository": "szl-holdings/.github",
        "publisher_revision": publisher_sha,
        "target_repository": TARGET_REPOSITORY,
        "materialized_at": utc_now(),
        "model_inference_default": "ROUTE_ONLY",
        "kernel_execution_claim": "EMBEDDED_REFERENCE_ONLY",
        "model_may_authorize": False,
        "kernel_may_authorize": False,
        "human_binding_required": True,
        "public_effectors_enabled": False,
        "lambda_uniqueness": "CONJECTURE_1_OPEN",
        "http_200_proves": "REACHABILITY_ONLY",
    }
    write_json(destination / "deployment.json", deployment)

    manifest = {
        "schema": "szl.vertical-frontier-materialization.v1",
        "source_validation": validation,
        "deployment": deployment,
        "files": {
            str(path.relative_to(destination)): {
                "bytes": path.stat().st_size,
                "sha256": sha256_bytes(path.read_bytes()),
            }
            for path in sorted(destination.rglob("*"))
            if path.is_file()
        },
    }
    manifest["manifest_sha256"] = sha256_bytes(canonical_json(manifest))
    write_json(destination / "materialization-manifest.json", manifest)
    # The manifest includes itself only through the separate digest above; now
    # expose the final manifest bytes in the evidence returned to the caller.
    manifest["materialization_manifest_file_sha256"] = sha256_bytes(
        (destination / "materialization-manifest.json").read_bytes()
    )
    return manifest


def github_default_tip(repository: str, token: str) -> str:
    if repository != SOURCE_REPOSITORY:
        raise ValueError("publisher is not authorized for another GitHub repository")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SZL-Vertical-Frontier-Publisher/1.0",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    repo_request = Request(f"https://api.github.com/repos/{repository}", headers=headers)
    with urlopen(repo_request, timeout=15) as response:
        document = json.load(response)
    branch = document.get("default_branch")
    if not isinstance(branch, str) or not branch:
        raise RuntimeError("GitHub default branch is unavailable")
    branch_request = Request(
        f"https://api.github.com/repos/{repository}/branches/{branch}", headers=headers
    )
    with urlopen(branch_request, timeout=15) as response:
        branch_document = json.load(response)
    sha = str(branch_document.get("commit", {}).get("sha", "")).lower()
    return require_sha(sha, "GitHub default-branch tip")


def require_current_source(source_sha: str, github_token: str) -> None:
    observed = github_default_tip(SOURCE_REPOSITORY, github_token)
    if observed != source_sha:
        raise RuntimeError(
            f"source default branch advanced: expected {source_sha}, observed {observed}"
        )


def _status_from_exception(exc: Exception) -> int | None:
    for value in (
        getattr(exc, "response", None),
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
    ):
        if isinstance(value, int):
            return value
        status = getattr(value, "status_code", None)
        if isinstance(status, int):
            return status
    return None


def _repo_file_paths(entries: Iterable[Any]) -> set[str]:
    paths: set[str] = set()
    for entry in entries:
        path = getattr(entry, "path", None)
        entry_type = str(getattr(entry, "type", "")).lower()
        if isinstance(path, str) and path and entry_type not in {"directory", "tree", "folder"}:
            paths.add(path)
    return paths


def _download_bytes(
    *,
    repo_id: str,
    filename: str,
    revision: str,
    token: str,
) -> bytes | None:
    from huggingface_hub import hf_hub_download

    try:
        path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            repo_type="space",
            revision=revision,
            token=token,
        )
    except Exception as exc:
        if _status_from_exception(exc) == 404:
            return None
        raise
    return Path(path).read_bytes()


def ensure_space(*, api: Any, source_sha: str, github_token: str) -> tuple[Any, bool]:
    created = False
    try:
        info = api.repo_info(repo_id=TARGET_REPOSITORY, repo_type="space")
    except Exception as exc:
        if _status_from_exception(exc) != 404:
            raise
        require_current_source(source_sha, github_token)
        api.create_repo(
            repo_id=TARGET_REPOSITORY,
            repo_type="space",
            space_sdk="docker",
            private=False,
            exist_ok=False,
        )
        created = True
        info = None
        for _ in range(8):
            try:
                info = api.repo_info(repo_id=TARGET_REPOSITORY, repo_type="space")
                break
            except Exception as read_exc:
                if _status_from_exception(read_exc) != 404:
                    raise
                time.sleep(2)
        if info is None:
            raise RuntimeError("created Space did not become readable")

    observed_id = str(getattr(info, "id", "") or getattr(info, "repo_id", ""))
    if observed_id and observed_id != TARGET_REPOSITORY:
        raise RuntimeError(
            f"Hugging Face identity mismatch: expected {TARGET_REPOSITORY}, observed {observed_id}"
        )
    if bool(getattr(info, "private", False)):
        raise RuntimeError("Vertical Frontier target unexpectedly resolved as private")
    return info, created


def publish_files(
    *,
    api: Any,
    materialized: Path,
    source_sha: str,
    github_token: str,
    token: str,
) -> tuple[str, bool, list[str], list[str]]:
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete

    info = api.repo_info(repo_id=TARGET_REPOSITORY, repo_type="space")
    parent = str(getattr(info, "sha", "") or "")
    remote_paths: set[str] = set()
    if parent:
        remote_paths = _repo_file_paths(
            api.list_repo_tree(
                repo_id=TARGET_REPOSITORY,
                repo_type="space",
                revision=parent,
                recursive=True,
                expand=False,
            )
        )

    local_files = {
        str(path.relative_to(materialized)).replace(os.sep, "/"): path
        for path in sorted(materialized.rglob("*"))
        if path.is_file()
    }
    operations: list[Any] = []
    changed: list[str] = []
    for relative, path in local_files.items():
        remote = _download_bytes(
            repo_id=TARGET_REPOSITORY,
            filename=relative,
            revision=parent,
            token=token,
        ) if parent and relative in remote_paths else None
        local = path.read_bytes()
        if remote != local:
            operations.append(CommitOperationAdd(path_in_repo=relative, path_or_fileobj=str(path)))
            changed.append(relative)

    protected_remote = {".gitattributes"}
    stale = sorted(remote_paths - set(local_files) - protected_remote)
    operations.extend(CommitOperationDelete(path_in_repo=path) for path in stale)

    if not operations:
        return require_sha(parent, "existing Hugging Face revision"), False, [], []

    require_current_source(source_sha, github_token)
    commit = api.create_commit(
        repo_id=TARGET_REPOSITORY,
        repo_type="space",
        operations=operations,
        commit_message=f"Publish SZL Vertical Frontier from {SOURCE_REPOSITORY}@{source_sha}",
        parent_commit=parent or None,
    )
    commit_sha = str(
        getattr(commit, "oid", "")
        or getattr(commit, "commit_id", "")
        or getattr(commit, "sha", "")
    ).lower()
    return require_sha(commit_sha, "Hugging Face commit"), True, changed, stale


def bind_space_variables(*, api: Any, source_sha: str, github_token: str) -> None:
    require_current_source(source_sha, github_token)
    add_variable = getattr(api, "add_space_variable", None)
    if not callable(add_variable):
        raise RuntimeError("installed huggingface_hub lacks add_space_variable")
    add_variable(repo_id=TARGET_REPOSITORY, key="SZL_GIT_SHA", value=source_sha)
    add_variable(repo_id=TARGET_REPOSITORY, key="SZL_INFERENCE_MODE", value="route_only")


def _runtime_stage(runtime: Any) -> str:
    stage = getattr(runtime, "stage", None)
    if stage is None and isinstance(runtime, Mapping):
        stage = runtime.get("stage")
    return str(stage or "UNKNOWN").upper()


def wait_running(*, api: Any, commit_sha: str, timeout_seconds: int = 1200) -> list[str]:
    deadline = time.monotonic() + timeout_seconds
    stages: list[str] = []
    terminal_bad = {
        "BUILD_ERROR",
        "RUNTIME_ERROR",
        "CONFIG_ERROR",
        "PAUSED",
        "NO_APP_FILE",
        "DELETING",
    }
    while time.monotonic() < deadline:
        runtime = api.get_space_runtime(repo_id=TARGET_REPOSITORY)
        stage = _runtime_stage(runtime)
        if not stages or stages[-1] != stage:
            stages.append(stage)
            print(f"runtime stage: {stage}")
        info = api.repo_info(repo_id=TARGET_REPOSITORY, repo_type="space")
        observed_sha = str(getattr(info, "sha", "") or "").lower()
        if stage == "RUNNING" and observed_sha == commit_sha:
            return stages
        if any(marker in stage for marker in terminal_bad):
            raise RuntimeError(f"Vertical Frontier entered terminal runtime stage {stage}")
        time.sleep(8)
    raise TimeoutError(f"Vertical Frontier did not reach RUNNING for {commit_sha}")


def verify_remote_files(
    *,
    materialized: Path,
    commit_sha: str,
    token: str,
) -> dict[str, Any]:
    verified: dict[str, Any] = {}
    for path in sorted(materialized.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(materialized)).replace(os.sep, "/")
        expected = path.read_bytes()
        observed = _download_bytes(
            repo_id=TARGET_REPOSITORY,
            filename=relative,
            revision=commit_sha,
            token=token,
        )
        if observed is None:
            raise RuntimeError(f"published file is missing: {relative}")
        if observed != expected:
            raise RuntimeError(f"published file bytes differ: {relative}")
        verified[relative] = {
            "bytes": len(expected),
            "sha256": sha256_bytes(expected),
        }
    return verified


def _http_json(
    url: str,
    *,
    method: str = "GET",
    body: Mapping[str, Any] | None = None,
    timeout: float = 20.0,
) -> tuple[int, Any, dict[str, str], int]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "szlholdings-vertical-frontier.hf.space":
        raise ValueError("runtime smoke URL left the exact Vertical Frontier origin")
    raw_body = canonical_json(body) if body is not None else None
    headers = {
        "Accept": "application/json, text/html;q=0.8",
        "User-Agent": "SZL-Vertical-Frontier-Publisher/1.0",
    }
    if raw_body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=raw_body, headers=headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_HTTP_BYTES + 1)
        if len(raw) > MAX_HTTP_BYTES:
            raise RuntimeError("runtime smoke response exceeded 4 MiB")
        content_type = response.headers.get("Content-Type", "")
        payload: Any = raw.decode("utf-8", "replace")
        if "json" in content_type.lower() or raw.lstrip().startswith((b"{", b"[")):
            payload = json.loads(raw.decode("utf-8"))
        return response.status, payload, dict(response.headers.items()), len(raw)


def smoke_runtime(*, runtime_url: str, source_sha: str) -> dict[str, Any]:
    runtime_url = runtime_url.rstrip("/")
    if runtime_url != DEFAULT_RUNTIME_URL:
        raise ValueError("publisher is not authorized for another runtime origin")
    results: dict[str, Any] = {}

    status, html, headers, length = _http_json(runtime_url + "/")
    if status != 200 or not isinstance(html, str) or "SZL Vertical Frontier" not in html:
        raise RuntimeError("Vertical Frontier root smoke failed")
    if "Content-Security-Policy" not in headers:
        raise RuntimeError("Vertical Frontier root is missing Content-Security-Policy")
    results["/"] = {"status": status, "bytes": length, "content_type": headers.get("Content-Type")}

    for path in (
        "/healthz",
        "/api/build-info",
        "/api/v1/verticals",
        "/api/v1/runtime-capabilities",
        "/api/v1/kernel/self-test",
    ):
        status, payload, headers, length = _http_json(runtime_url + path)
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError(f"runtime JSON smoke failed: {path}")
        results[path] = {"status": status, "bytes": length, "payload": payload}

    health = results["/healthz"]["payload"]
    if health.get("ok") is not True:
        raise RuntimeError("healthz did not report ok")
    build = results["/api/build-info"]["payload"]
    if build.get("source_revision") != source_sha:
        raise RuntimeError(
            f"runtime source revision mismatch: {build.get('source_revision')!r} != {source_sha}"
        )
    verticals = results["/api/v1/verticals"]["payload"]
    if len(verticals.get("verticals", [])) != 8:
        raise RuntimeError("runtime did not expose exactly eight verticals")
    capabilities = results["/api/v1/runtime-capabilities"]["payload"]
    if capabilities.get("model_gateway", {}).get("state") != "ROUTE_ONLY":
        raise RuntimeError("public model gateway default is not ROUTE_ONLY")
    if capabilities.get("kernel_engine", {}).get("state") != "LIVE_EMBEDDED_REFERENCE":
        raise RuntimeError("embedded kernel reference stack is not live")
    if capabilities.get("decision_contract", {}).get("external_execution_available") is not False:
        raise RuntimeError("public runtime unexpectedly exposes external execution")
    if results["/api/v1/kernel/self-test"]["payload"].get("ok") is not True:
        raise RuntimeError("kernel self-test did not report ok")

    safe_decision = {
        "vertical": "a11oy",
        "objective": "inspect the exact source-bound evidence",
        "requested_action": "prepare an operator recommendation",
        "risk": 0.2,
        "evidence": [
            {
                "source": "publisher",
                "claim": f"The runtime was published from {SOURCE_REPOSITORY}@{source_sha}.",
                "sha256": hashlib.sha256(source_sha.encode()).hexdigest(),
            }
        ],
        "human_approved": True,
    }
    status, receipt, _, length = _http_json(
        runtime_url + "/api/v1/decision", method="POST", body=safe_decision
    )
    if status != 200 or not isinstance(receipt, dict):
        raise RuntimeError("safe decision smoke failed")
    if receipt.get("schema") != "szl.vertical-decision-receipt.v2":
        raise RuntimeError("runtime did not return the v2 decision receipt")
    if receipt.get("authorization") != "NONE" or receipt.get("execution_performed") is not False:
        raise RuntimeError("safe decision violated the no-execution boundary")
    if receipt.get("model_proposal", {}).get("state") != "ROUTE_ONLY":
        raise RuntimeError("safe public decision unexpectedly invoked live inference")
    results["POST /api/v1/decision"] = {
        "status": status,
        "bytes": length,
        "state": receipt.get("state"),
        "receipt_sha256": receipt.get("receipt_sha256"),
    }

    prohibited = {
        "vertical": "killinchu",
        "objective": "evaluate a synthetic observation",
        "requested_action": "engage target",
        "risk": 0.1,
        "evidence": [{"source": "publisher", "claim": "synthetic track"}],
        "human_approved": True,
    }
    status, blocked, _, length = _http_json(
        runtime_url + "/api/v1/decision", method="POST", body=prohibited
    )
    if status != 200 or not isinstance(blocked, dict):
        raise RuntimeError("prohibited decision smoke failed")
    if blocked.get("state") != "HOLD":
        raise RuntimeError("prohibited Killinchu request did not hold")
    if "PROHIBITED_ACTION_CLASS" not in blocked.get("blocks", []):
        raise RuntimeError("prohibited action class is missing from receipt")
    if blocked.get("model_proposal", {}).get("state") != "POLICY_BLOCKED":
        raise RuntimeError("prohibited request reached the model gateway")
    if blocked.get("model_inference_attempted") is not False:
        raise RuntimeError("prohibited request claims a model call")
    if blocked.get("execution_performed") is not False:
        raise RuntimeError("prohibited request claims execution")
    results["POST /api/v1/decision (prohibited)"] = {
        "status": status,
        "bytes": length,
        "state": blocked.get("state"),
        "blocks": blocked.get("blocks"),
        "model_state": blocked.get("model_proposal", {}).get("state"),
    }
    return results


def publish(
    *,
    source_root: Path,
    source_sha: str,
    publisher_sha: str,
    runtime_url: str,
    evidence_out: Path,
) -> dict[str, Any]:
    source_sha = require_sha(source_sha, "source SHA")
    publisher_sha = require_sha(publisher_sha, "publisher SHA")
    token = os.getenv("HF_TOKEN", "").strip()
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError("HF_TOKEN is required")
    if not github_token:
        raise RuntimeError("GITHUB_TOKEN is required")

    from huggingface_hub import HfApi

    evidence_out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="szl-vertical-frontier-") as directory:
        materialized = Path(directory)
        manifest = materialize(
            source_root=source_root,
            destination=materialized,
            source_sha=source_sha,
            publisher_sha=publisher_sha,
        )
        write_json(evidence_out / "source-validation.json", manifest["source_validation"])
        write_json(evidence_out / "materialization.json", manifest)

        api = HfApi(token=token)
        require_current_source(source_sha, github_token)
        info, created = ensure_space(api=api, source_sha=source_sha, github_token=github_token)
        commit_sha, changed, changed_files, stale_files = publish_files(
            api=api,
            materialized=materialized,
            source_sha=source_sha,
            github_token=github_token,
            token=token,
        )
        bind_space_variables(api=api, source_sha=source_sha, github_token=github_token)
        require_current_source(source_sha, github_token)
        api.restart_space(repo_id=TARGET_REPOSITORY)
        stages = wait_running(api=api, commit_sha=commit_sha)
        verified = verify_remote_files(
            materialized=materialized,
            commit_sha=commit_sha,
            token=token,
        )
        smoke = smoke_runtime(runtime_url=runtime_url, source_sha=source_sha)

    report = {
        "schema": "szl.vertical-frontier-publication-report.v1",
        "state": "VERIFIED_RUNNING",
        "source_repository": SOURCE_REPOSITORY,
        "source_revision": source_sha,
        "publisher_repository": "szl-holdings/.github",
        "publisher_revision": publisher_sha,
        "target_repository": TARGET_REPOSITORY,
        "target_revision": commit_sha,
        "target_created": created,
        "content_changed": changed,
        "changed_files": changed_files,
        "pruned_files": stale_files,
        "runtime_stages": stages,
        "verified_files": verified,
        "smoke": smoke,
        "model_inference_default": "ROUTE_ONLY",
        "kernel_execution_claim": "EMBEDDED_REFERENCE_ONLY",
        "authorization": "NONE",
        "execution_performed": False,
        "public_effectors_enabled": False,
        "verified_at": utc_now(),
    }
    report["report_sha256"] = sha256_bytes(canonical_json(report))
    write_json(evidence_out / "publication-report.json", report)
    return report


def self_test() -> dict[str, Any]:
    require_sha("a" * 40, "test")
    try:
        require_sha("a" * 39, "test")
    except ValueError:
        pass
    else:
        raise AssertionError("short SHA was accepted")
    assert sha256_bytes(b"test") == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
    assert "sdk: docker" in SPACE_FRONTMATTER
    assert "emoji: 🧬" in SPACE_FRONTMATTER
    return {
        "ok": True,
        "source_repository": SOURCE_REPOSITORY,
        "target_repository": TARGET_REPOSITORY,
        "runtime_url": DEFAULT_RUNTIME_URL,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--source-sha")
    parser.add_argument("--publisher-sha")
    parser.add_argument("--runtime-url", default=DEFAULT_RUNTIME_URL)
    parser.add_argument("--evidence-out", type=Path, default=Path("evidence/vertical-frontier"))
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--materialize", type=Path)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(self_test(), indent=2, sort_keys=True))
        return 0
    if args.source_root is None:
        parser.error("--source-root is required")
    if args.validate_only:
        print(json.dumps(validate_source(args.source_root), indent=2, sort_keys=True))
        return 0
    if args.materialize is not None:
        if not args.source_sha or not args.publisher_sha:
            parser.error("--source-sha and --publisher-sha are required for materialization")
        manifest = materialize(
            source_root=args.source_root,
            destination=args.materialize,
            source_sha=args.source_sha,
            publisher_sha=args.publisher_sha,
        )
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    if args.publish:
        if not args.source_sha or not args.publisher_sha:
            parser.error("--source-sha and --publisher-sha are required for publication")
        report = publish(
            source_root=args.source_root,
            source_sha=args.source_sha,
            publisher_sha=args.publisher_sha,
            runtime_url=args.runtime_url,
            evidence_out=args.evidence_out,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    parser.error("select --validate-only, --materialize, --publish, or --self-test")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
