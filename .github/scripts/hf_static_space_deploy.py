#!/usr/bin/env python3
"""Publish a manifest-defined static Space and verify its served source binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SCHEMA = "szl.hf-static-publication/v1"
DEPLOYMENT_SCHEMA = "szl.hf-static-deployment/v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TOKEN_RE = re.compile(r"(?:hf_[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._-]+)", re.I)


class ContractError(ValueError):
    """Raised when a publication contract is unsafe or incomplete."""


@dataclass(frozen=True)
class PublicationFile:
    source: Path
    destination: str
    sha256: str
    size: int


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_destination(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ContractError(f"unsafe destination: {value!r}")
    normalized = str(path)
    if normalized in {".", "deployment.json"}:
        raise ContractError(f"reserved destination: {value!r}")
    return normalized


def resolve_source(repo_root: Path, value: str) -> Path:
    candidate = (repo_root / value).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ContractError(f"source escapes repository: {value!r}") from exc
    if not candidate.is_file():
        raise ContractError(f"source file does not exist: {value!r}")
    return candidate


def load_contract(repo_root: Path, manifest_path: Path) -> tuple[dict[str, Any], list[PublicationFile]]:
    contract = json.loads(manifest_path.read_text(encoding="utf-8"))
    if contract.get("schema") != SCHEMA:
        raise ContractError(f"schema must be {SCHEMA}")
    target = contract.get("target")
    if not isinstance(target, dict):
        raise ContractError("target must be an object")
    if target.get("repo_type") != "space":
        raise ContractError("only Hugging Face Spaces are supported")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(target.get("repo_id", ""))):
        raise ContractError("target.repo_id must be owner/name")
    if not str(target.get("live_base_url", "")).startswith("https://"):
        raise ContractError("target.live_base_url must be HTTPS")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(contract.get("source_repository", ""))):
        raise ContractError("source_repository must be owner/name")

    rows = contract.get("files")
    if not isinstance(rows, list) or not rows:
        raise ContractError("files must be a non-empty array")
    destinations: set[str] = set()
    files: list[PublicationFile] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ContractError("each file entry must be an object")
        destination = safe_destination(str(row.get("destination", "")))
        if destination in destinations:
            raise ContractError(f"duplicate destination: {destination}")
        destinations.add(destination)
        source = resolve_source(repo_root, str(row.get("source", "")))
        data = source.read_bytes()
        files.append(PublicationFile(source, destination, sha256_bytes(data), len(data)))

    required = {"README.md", "index.html", ".gitattributes"}
    missing = sorted(required - destinations)
    if missing:
        raise ContractError(f"missing required destinations: {', '.join(missing)}")
    smoke = contract.get("smoke")
    if not isinstance(smoke, dict) or not str(smoke.get("path", "")).startswith("/"):
        raise ContractError("smoke.path must be a same-host absolute path")
    if not str(smoke.get("required_marker", "")):
        raise ContractError("smoke.required_marker is required")
    return contract, sorted(files, key=lambda item: item.destination)


def build_deployment(
    contract: dict[str, Any],
    files: list[PublicationFile],
    source_sha: str,
    observed_at: str,
) -> dict[str, Any]:
    if not SHA_RE.fullmatch(source_sha):
        raise ContractError("source SHA must be an exact lowercase 40-character commit")
    return {
        "schema": DEPLOYMENT_SCHEMA,
        "source": {
            "repository": contract["source_repository"],
            "revision": source_sha,
            "manifest": "huggingface/org-card.manifest.json",
        },
        "target": contract["target"],
        "published_at": observed_at,
        "files": [
            {"path": item.destination, "sha256": item.sha256, "size": item.size}
            for item in files
        ],
        "claims": {
            "source_binding": "MEASURED_AFTER_LIVE_READBACK",
            "model_quality": "NOT_EVALUATED_BY_THIS_SURFACE",
            "estate_operational_status": "NOT_INFERRED",
        },
    }


def materialize(root: Path, files: list[PublicationFile], deployment: dict[str, Any]) -> list[Path]:
    output: list[Path] = []
    for item in files:
        destination = root / PurePosixPath(item.destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(item.source.read_bytes())
        output.append(destination)
    deployment_path = root / "deployment.json"
    deployment_path.write_bytes(canonical_json(deployment))
    output.append(deployment_path)
    return output


def fetch(url: str, timeout: float = 20.0) -> tuple[int, bytes, str]:
    request = Request(url, headers={"User-Agent": "szl-static-space-verifier/1"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), response.geturl()
    except HTTPError as exc:
        return exc.code, exc.read(), exc.geturl()


def redact(message: str) -> str:
    return TOKEN_RE.sub("[REDACTED]", message)


def normalize_space_stage(stage: Any) -> str:
    """Return the Hugging Face runtime stage without enum-class decoration."""
    return str(getattr(stage, "value", stage))


def deployment_matches(live: dict[str, Any] | None, expected: dict[str, Any]) -> bool:
    """Bind verification to this publication attempt, not only its Git SHA."""
    return live == expected


def publish(
    contract: dict[str, Any],
    files: list[PublicationFile],
    deployment: dict[str, Any],
    token: str,
    wait_seconds: int,
) -> dict[str, Any]:
    try:
        from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi
    except ImportError as exc:
        raise ContractError("huggingface_hub is required for --publish") from exc

    repo_id = contract["target"]["repo_id"]
    api = HfApi(token=token)
    before = api.repo_info(repo_id=repo_id, repo_type="space")
    remote_files = set(api.list_repo_files(repo_id=repo_id, repo_type="space"))

    with tempfile.TemporaryDirectory(prefix="szl-hf-static-") as temp:
        temp_root = Path(temp)
        local_files = materialize(temp_root, files, deployment)
        wanted = {path.relative_to(temp_root).as_posix() for path in local_files}
        operations: list[Any] = [
            CommitOperationAdd(path_in_repo=path.relative_to(temp_root).as_posix(), path_or_fileobj=path)
            for path in sorted(local_files)
        ]
        deleted: list[str] = []
        if bool(contract.get("prune")):
            deleted = sorted(remote_files - wanted)
            operations.extend(CommitOperationDelete(path_in_repo=path) for path in deleted)
        commit = api.create_commit(
            repo_id=repo_id,
            repo_type="space",
            operations=operations,
            commit_message=f"deploy: bind org card to {deployment['source']['revision'][:12]}",
            parent_commit=before.sha,
        )

    deadline = time.monotonic() + wait_seconds
    live_manifest: dict[str, Any] | None = None
    smoke_status = 0
    smoke_final_url = ""
    smoke_marker = contract["smoke"]["required_marker"].encode()
    base = contract["target"]["live_base_url"].rstrip("/")
    last_error = ""
    while time.monotonic() < deadline:
        try:
            runtime = api.get_space_runtime(repo_id=repo_id)
            stage = normalize_space_stage(getattr(runtime, "stage", "UNKNOWN"))
            manifest_status, manifest_bytes, _ = fetch(f"{base}/deployment.json")
            smoke_status, smoke_bytes, smoke_final_url = fetch(f"{base}{contract['smoke']['path']}")
            if manifest_status == 200:
                live_manifest = json.loads(manifest_bytes)
            attempt_matches = deployment_matches(live_manifest, deployment)
            if stage == "RUNNING" and attempt_matches and smoke_status == 200 and smoke_marker in smoke_bytes:
                return {
                    "state": "VERIFIED",
                    "hf_commit": getattr(commit, "oid", None),
                    "runtime_stage": stage,
                    "deleted_paths": deleted,
                    "live_source_revision": deployment["source"]["revision"],
                    "smoke_status": smoke_status,
                    "smoke_final_url": smoke_final_url,
                }
            last_error = f"stage={stage} attempt_matches={attempt_matches} smoke_status={smoke_status}"
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = redact(str(exc))
        time.sleep(8)
    raise ContractError(f"live verification did not converge: {last_error}")


def write_report(path: Path | None, report: dict[str, Any]) -> None:
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if path:
        path.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=600)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    observed_at = utc_now()
    report: dict[str, Any] = {
        "schema": "szl.hf-static-deploy-report/v1",
        "state": "FAILED",
        "observed_at": observed_at,
    }
    try:
        repo_root = args.repo_root.resolve()
        manifest_path = args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
        contract, files = load_contract(repo_root, manifest_path)
        deployment = build_deployment(contract, files, args.source_sha, observed_at)
        report.update(
            {
                "state": "CHECKED",
                "source_revision": args.source_sha,
                "target": contract["target"],
                "file_count": len(files) + 1,
                "files": deployment["files"],
            }
        )
        if args.publish:
            token = os.environ.get("HF_TOKEN", "")
            if not token:
                raise ContractError("HF_TOKEN is required for --publish")
            report.update(publish(contract, files, deployment, token, args.wait_seconds))
        write_report(args.report, report)
        return 0
    except Exception as exc:  # fail closed and preserve a redacted report
        report["error"] = redact(f"{type(exc).__name__}: {exc}")
        write_report(args.report, report)
        return 1


if __name__ == "__main__":
    sys.exit(main())
