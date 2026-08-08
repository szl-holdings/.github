#!/usr/bin/env python3
"""Publish a manifest-defined static Space and verify its served source binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


SCHEMA = "szl.hf-static-publication/v1"
DEPLOYMENT_SCHEMA = "szl.hf-static-deployment/v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TOKEN_RE = re.compile(r"(?:hf_[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._-]+)", re.I)
PUBLISH_ENVIRONMENT = "production"
PUBLISH_WORKFLOW_PATH = ".github/workflows/hf-org-card-deploy.yml"
RUNTIME_TRANSFORM_MODES = {
    "hf_bootstrap_injected",
    "rendered_markdown",
}
HF_BOOTSTRAP = re.compile(
    rb'<script>window\.huggingface=\{variables:\{'
    rb'(?:(?:"[A-Z][A-Z0-9_]*":"[A-Za-z0-9._:-]{1,256}")'
    rb'(?:,(?:"[A-Z][A-Z0-9_]*":"[A-Za-z0-9._:-]{1,256}"))*)?'
    rb'\}\};</script>\r?\n?'
)


class ContractError(ValueError):
    """Raised when a publication contract is unsafe or incomplete."""


class PublicationVerificationError(ContractError):
    """Raised after a remote commit exists but live verification is incomplete."""

    def __init__(self, message: str, result: dict[str, Any]) -> None:
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class PublicationFile:
    source: Path
    destination: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ExpectedReadback:
    path: str
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
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or ":" in value
    ):
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


def load_contract(
    repo_root: Path, manifest_path: Path
) -> tuple[dict[str, Any], list[PublicationFile]]:
    contract = json.loads(manifest_path.read_text(encoding="utf-8"))
    if contract.get("schema") != SCHEMA:
        raise ContractError(f"schema must be {SCHEMA}")
    target = contract.get("target")
    if not isinstance(target, dict):
        raise ContractError("target must be an object")
    if target.get("repo_type") != "space":
        raise ContractError("only Hugging Face Spaces are supported")
    if not re.fullmatch(
        r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(target.get("repo_id", ""))
    ):
        raise ContractError("target.repo_id must be owner/name")
    if not str(target.get("live_base_url", "")).startswith("https://"):
        raise ContractError("target.live_base_url must be HTTPS")
    if not re.fullmatch(
        r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(contract.get("source_repository", ""))
    ):
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
        files.append(
            PublicationFile(source, destination, sha256_bytes(data), len(data))
        )

    transforms = contract.get("runtime_transforms", {})
    if not isinstance(transforms, dict):
        raise ContractError("runtime_transforms must be an object")
    for destination, policy in transforms.items():
        if destination not in destinations:
            raise ContractError(
                f"runtime transform targets an unpublished file: {destination!r}"
            )
        if not isinstance(policy, dict) or policy.get("mode") not in (
            RUNTIME_TRANSFORM_MODES
        ):
            raise ContractError(
                f"unsupported runtime transform policy: {destination!r}"
            )
        markers = policy.get("required_markers", [])
        if policy["mode"] == "rendered_markdown":
            if (
                not isinstance(markers, list)
                or not markers
                or any(not isinstance(marker, str) or not marker for marker in markers)
            ):
                raise ContractError(
                    f"rendered Markdown requires markers: {destination!r}"
                )
        elif markers:
            raise ContractError(
                f"markers are not supported for transform: {destination!r}"
            )

    required = {"README.md", "index.html", ".gitattributes"}
    missing = sorted(required - destinations)
    if missing:
        raise ContractError(f"missing required destinations: {', '.join(missing)}")
    smoke = contract.get("smoke")
    if not isinstance(smoke, dict) or not str(smoke.get("path", "")).startswith("/"):
        raise ContractError("smoke.path must be a same-host absolute path")
    if not str(smoke.get("required_marker", "")):
        raise ContractError("smoke.required_marker is required")
    allowed_deletions = contract.get("allowed_deletions")
    if bool(contract.get("prune")) and not isinstance(allowed_deletions, list):
        raise ContractError(
            "allowed_deletions must be an explicit array when prune is enabled"
        )
    if isinstance(allowed_deletions, list):
        normalized_deletions = [
            safe_destination(str(path)) for path in allowed_deletions
        ]
        if len(normalized_deletions) != len(set(normalized_deletions)):
            raise ContractError("allowed_deletions contains duplicates")
        contract["allowed_deletions"] = normalized_deletions
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
            "source_binding": "PENDING_LIVE_READBACK",
            "model_quality": "NOT_EVALUATED_BY_THIS_SURFACE",
            "estate_operational_status": "NOT_INFERRED",
        },
    }


def materialize(
    root: Path, files: list[PublicationFile], deployment: dict[str, Any]
) -> list[Path]:
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ContractError("materialization directory must be empty")
    root.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve()
    output: list[Path] = []
    for item in files:
        destination = (root / PurePosixPath(item.destination)).resolve()
        try:
            destination.relative_to(resolved_root)
        except ValueError as exc:
            raise ContractError(
                f"materialization destination escapes output root: {item.destination!r}"
            ) from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(item.source.read_bytes())
        output.append(destination)
    deployment_path = root / "deployment.json"
    deployment_path.write_bytes(canonical_json(deployment))
    output.append(deployment_path)
    return output


def fetch(
    url: str, timeout: float = 20.0, max_bytes: int = 2_000_000
) -> tuple[int, bytes, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "szl-static-space-verifier/1",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
        },
    )

    def bounded_read(response: Any) -> bytes:
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > max_bytes:
            raise ContractError(f"response exceeds {max_bytes} bytes")
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ContractError(f"response exceeds {max_bytes} bytes")
        return data

    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, bounded_read(response), response.geturl()
    except HTTPError as exc:
        return exc.code, bounded_read(exc), exc.geturl()


def same_origin(url: str, expected_base: str) -> bool:
    """Return whether two HTTP URLs share scheme, hostname, and effective port."""

    def origin(value: str) -> tuple[str, str, int] | None:
        try:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
            ):
                return None
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError:
            return None
        return parsed.scheme.casefold(), parsed.hostname.casefold(), port

    expected = origin(expected_base)
    return expected is not None and origin(url) == expected


def redact(message: str) -> str:
    return TOKEN_RE.sub("[REDACTED]", message)


def assert_publish_authority(
    contract: dict[str, Any], source_sha: str, environ: dict[str, str]
) -> None:
    """Refuse token-backed publication outside the protected main workflow."""

    repository = contract["source_repository"]
    required = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REF_PROTECTED": "true",
        "GITHUB_REPOSITORY": repository,
        "GITHUB_SHA": source_sha,
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKFLOW_REF": (
            f"{repository}/{PUBLISH_WORKFLOW_PATH}@refs/heads/main"
        ),
        "SZL_PUBLICATION_ENVIRONMENT": PUBLISH_ENVIRONMENT,
    }
    mismatches = [
        name
        for name, expected in required.items()
        if environ.get(name) != expected
    ]
    if not environ.get("GITHUB_TOKEN"):
        mismatches.append("GITHUB_TOKEN")
    if mismatches:
        raise ContractError(
            "publication authority mismatch: " + ", ".join(sorted(mismatches))
        )


def local_head_sha(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip()


def assert_local_source(repo_root: Path, source_sha: str) -> None:
    if local_head_sha(repo_root) != source_sha:
        raise ContractError("checked-out HEAD does not match source SHA")


def fetch_github_main_sha(repository: str, token: str) -> str:
    url = f"https://api.github.com/repos/{quote(repository, safe='/')}/commits/main"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "szl-static-space-publisher/1",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=20) as response:
        if response.status != 200 or not same_origin(response.geturl(), url):
            raise ContractError("protected main lookup left the GitHub API origin")
        payload = response.read(100_001)
    if len(payload) > 100_000:
        raise ContractError("protected main lookup response is oversized")
    sha = json.loads(payload).get("sha")
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise ContractError("protected main lookup returned an invalid SHA")
    return sha


def normalize_space_stage(stage: Any) -> str:
    """Return the Hugging Face runtime stage without enum-class decoration."""
    return str(getattr(stage, "value", stage))


def deployment_matches(live: dict[str, Any] | None, expected: dict[str, Any]) -> bool:
    """Bind verification to this publication attempt, not only its Git SHA."""
    return live == expected


def trusted_huggingface_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").casefold()
    return bool(
        parsed.scheme == "https"
        and parsed.username is None
        and parsed.password is None
        and (host == "huggingface.co" or host.endswith(".hf.co"))
    )


def canonicalize_hf_bootstrap(data: bytes) -> bytes | None:
    marker = b"<head>"
    position = data.find(marker)
    if position < 0:
        return None
    start = position + len(marker)
    match = HF_BOOTSTRAP.match(data, start)
    if not match:
        return None
    if HF_BOOTSTRAP.search(data, match.end()):
        return None
    return data[:start] + data[match.end() :]


def _readback_result(
    target: ExpectedReadback,
    url: str,
    mode: str,
    origin: str,
    markers: list[str] | None = None,
) -> dict[str, Any]:
    max_bytes = target.size + 1
    if mode == "hf_bootstrap_injected":
        max_bytes = target.size + 4096
    elif mode == "rendered_markdown":
        max_bytes = max(1_000_000, target.size * 8)
    result: dict[str, Any] = {
        "path": target.path,
        "mode": mode,
        "expected_sha256": target.sha256,
        "expected_size": target.size,
        "requested_url": url,
        "status": 0,
        "final_url": "",
        "same_origin": False,
        "trusted_huggingface_redirect": False,
        "observed_sha256": None,
        "observed_size": None,
        "canonical_sha256": None,
        "canonical_size": None,
        "matches": False,
    }
    try:
        status, data, final_url = fetch(url, max_bytes=max_bytes)
        observed_sha256 = sha256_bytes(data)
        same = same_origin(final_url, origin)
        trusted = trusted_huggingface_url(final_url)
        result.update(
            {
                "status": status,
                "final_url": final_url,
                "same_origin": same,
                "trusted_huggingface_redirect": trusted,
                "observed_sha256": observed_sha256,
                "observed_size": len(data),
            }
        )
        if mode in {"immutable_commit_exact", "runtime_exact"}:
            result["canonical_sha256"] = observed_sha256
            result["canonical_size"] = len(data)
            result["matches"] = bool(
                status == 200
                and (same or trusted)
                and observed_sha256 == target.sha256
                and len(data) == target.size
            )
        elif mode == "hf_bootstrap_injected":
            canonical = canonicalize_hf_bootstrap(data)
            if canonical is not None:
                result["canonical_sha256"] = sha256_bytes(canonical)
                result["canonical_size"] = len(canonical)
                result["matches"] = bool(
                    status == 200
                    and same
                    and result["canonical_sha256"] == target.sha256
                    and result["canonical_size"] == target.size
                )
        elif mode == "rendered_markdown":
            encoded_markers = [marker.encode() for marker in markers or []]
            result["matches"] = bool(
                status == 200
                and same
                and encoded_markers
                and all(marker in data for marker in encoded_markers)
            )
    except Exception as exc:
        result["error"] = redact(f"{type(exc).__name__}: {exc}")
    return result


def verify_hub_commit_files(
    repo_id: str,
    commit_oid: str,
    files: list[PublicationFile],
    deployment: dict[str, Any],
) -> tuple[bool, list[dict[str, Any]]]:
    if not SHA_RE.fullmatch(commit_oid):
        raise ContractError("Hugging Face commit OID must be a 40-character SHA")
    targets = [
        ExpectedReadback(item.destination, item.sha256, item.size) for item in files
    ]
    deployment_bytes = canonical_json(deployment)
    targets.append(
        ExpectedReadback(
            "deployment.json",
            sha256_bytes(deployment_bytes),
            len(deployment_bytes),
        )
    )
    origin = "https://huggingface.co"
    prefix = (
        f"{origin}/spaces/{quote(repo_id, safe='/')}/resolve/{commit_oid}/"
    )

    def inspect(target: ExpectedReadback) -> dict[str, Any]:
        url = f"{prefix}{quote(target.path, safe='/')}?download=true"
        return _readback_result(
            target, url, "immutable_commit_exact", origin
        )

    with ThreadPoolExecutor(max_workers=min(8, len(targets))) as executor:
        rows = list(executor.map(inspect, targets))
    return all(bool(row["matches"]) for row in rows), rows


def verify_served_files(
    base: str,
    files: list[PublicationFile],
    transforms: dict[str, Any] | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    """Hash every runtime response under an explicit transformation policy."""

    origin = base.rstrip("/")
    policies = transforms or {}

    def inspect(item: PublicationFile) -> dict[str, Any]:
        policy = policies.get(item.destination, {})
        mode = str(policy.get("mode", "runtime_exact"))
        markers = policy.get("required_markers", [])
        target = ExpectedReadback(
            item.destination, item.sha256, item.size
        )
        url = f"{origin}/{quote(item.destination, safe='/')}"
        return _readback_result(target, url, mode, origin, markers)

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(files)))) as executor:
        rows = list(executor.map(inspect, files))
    return all(bool(row["matches"]) for row in rows), rows


def live_source_revision(live: Any) -> str | None:
    """Read the nested live revision without losing post-commit evidence."""
    if not isinstance(live, dict):
        return None
    source = live.get("source")
    if not isinstance(source, dict):
        return None
    revision = source.get("revision")
    return revision if isinstance(revision, str) else None


def planned_deletions(
    contract: dict[str, Any], remote_files: set[str], wanted: set[str]
) -> list[str]:
    """Return only explicitly authorized prune operations."""
    if not bool(contract.get("prune")):
        return []
    candidates = sorted(remote_files - wanted)
    allowed = set(contract.get("allowed_deletions", []))
    unexpected = sorted(set(candidates) - allowed)
    if unexpected:
        raise ContractError(
            "unexpected remote paths would be pruned: " + ", ".join(unexpected)
        )
    return candidates


def publish(
    contract: dict[str, Any],
    files: list[PublicationFile],
    deployment: dict[str, Any],
    token: str,
    github_token: str,
    wait_seconds: int,
    main_sha_lookup: Callable[[str, str], str] = fetch_github_main_sha,
) -> dict[str, Any]:
    try:
        from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi
    except ImportError as exc:
        raise ContractError("huggingface_hub is required for --publish") from exc

    repo_id = contract["target"]["repo_id"]
    source_repository = contract["source_repository"]
    source_revision = deployment["source"]["revision"]
    api = HfApi(token=token)
    before = api.repo_info(repo_id=repo_id, repo_type="space")
    remote_files = set(api.list_repo_files(repo_id=repo_id, repo_type="space"))

    with tempfile.TemporaryDirectory(prefix="szl-hf-static-") as temp:
        temp_root = Path(temp)
        local_files = materialize(temp_root, files, deployment)
        wanted = {path.relative_to(temp_root).as_posix() for path in local_files}
        operations: list[Any] = [
            CommitOperationAdd(
                path_in_repo=path.relative_to(temp_root).as_posix(),
                path_or_fileobj=path,
            )
            for path in sorted(local_files)
        ]
        deleted = planned_deletions(contract, remote_files, wanted)
        operations.extend(CommitOperationDelete(path_in_repo=path) for path in deleted)
        if main_sha_lookup(source_repository, github_token) != source_revision:
            raise ContractError("protected main moved before Hugging Face commit")
        commit = api.create_commit(
            repo_id=repo_id,
            repo_type="space",
            operations=operations,
            commit_message=f"deploy: bind org card to {deployment['source']['revision'][:12]}",
            parent_commit=before.sha,
        )

    commit_oid = str(getattr(commit, "oid", ""))
    if not SHA_RE.fullmatch(commit_oid):
        raise PublicationVerificationError(
            "Hugging Face returned an invalid commit OID",
            {
                "state": "COMMIT_CREATED_UNVERIFIED",
                "hf_commit": commit_oid or None,
                "deleted_paths": deleted,
            },
        )
    deadline = time.monotonic() + wait_seconds
    live_manifest: dict[str, Any] | None = None
    stage = "UNKNOWN"
    hub_head = ""
    remote_file_set_match = False
    immutable_files_match = False
    immutable_file_readback: list[dict[str, Any]] = []
    manifest_status = 0
    manifest_final_url = ""
    manifest_same_origin = False
    manifest_bookend_match = False
    smoke_status = 0
    smoke_final_url = ""
    smoke_same_origin = False
    runtime_files_match = False
    runtime_file_readback: list[dict[str, Any]] = []
    smoke_marker = contract["smoke"]["required_marker"].encode()
    base = contract["target"]["live_base_url"].rstrip("/")
    last_error = ""
    while time.monotonic() < deadline:
        try:
            runtime = api.get_space_runtime(repo_id=repo_id)
            stage = normalize_space_stage(getattr(runtime, "stage", "UNKNOWN"))
            hub_head = str(
                getattr(api.repo_info(repo_id=repo_id, repo_type="space"), "sha", "")
            )
            commit_files = set(
                api.list_repo_files(
                    repo_id=repo_id,
                    repo_type="space",
                    revision=commit_oid,
                )
            )
            remote_file_set_match = commit_files == wanted
            if (
                hub_head == commit_oid
                and remote_file_set_match
                and not immutable_files_match
            ):
                immutable_files_match, immutable_file_readback = (
                    verify_hub_commit_files(repo_id, commit_oid, files, deployment)
                )
            manifest_status, manifest_bytes, manifest_final_url = fetch(
                f"{base}/deployment.json",
                max_bytes=len(canonical_json(deployment)) + 1,
            )
            smoke_status, smoke_bytes, smoke_final_url = fetch(
                f"{base}{contract['smoke']['path']}"
            )
            manifest_same_origin = same_origin(manifest_final_url, base)
            smoke_same_origin = same_origin(smoke_final_url, base)
            if manifest_status == 200 and manifest_same_origin:
                live_manifest = json.loads(manifest_bytes)
            else:
                live_manifest = None
            attempt_matches = deployment_matches(live_manifest, deployment)
            base_ready = bool(
                stage == "RUNNING"
                and attempt_matches
                and manifest_same_origin
                and smoke_status == 200
                and smoke_same_origin
                and smoke_marker in smoke_bytes
            )
            if base_ready and immutable_files_match:
                runtime_files_match, runtime_file_readback = verify_served_files(
                    base, files, contract.get("runtime_transforms", {})
                )
                final_status, final_bytes, final_url = fetch(
                    f"{base}/deployment.json",
                    max_bytes=len(canonical_json(deployment)) + 1,
                )
                manifest_bookend_match = bool(
                    final_status == 200
                    and same_origin(final_url, base)
                    and final_bytes == manifest_bytes
                    and json.loads(final_bytes) == deployment
                )
                hub_head = str(
                    getattr(
                        api.repo_info(repo_id=repo_id, repo_type="space"),
                        "sha",
                        "",
                    )
                )
            if (
                base_ready
                and immutable_files_match
                and runtime_files_match
                and manifest_bookend_match
                and hub_head == commit_oid
            ):
                return {
                    "state": "VERIFIED",
                    "hf_commit": commit_oid,
                    "hub_head": hub_head,
                    "runtime_stage": stage,
                    "deleted_paths": deleted,
                    "remote_file_set": sorted(commit_files),
                    "remote_file_set_match": remote_file_set_match,
                    "immutable_files_match": immutable_files_match,
                    "immutable_file_readback": immutable_file_readback,
                    "live_source_revision": source_revision,
                    "manifest_status": manifest_status,
                    "manifest_final_url": manifest_final_url,
                    "manifest_same_origin": manifest_same_origin,
                    "manifest_bookend_match": manifest_bookend_match,
                    "smoke_status": smoke_status,
                    "smoke_final_url": smoke_final_url,
                    "smoke_same_origin": smoke_same_origin,
                    "runtime_files_match": runtime_files_match,
                    "runtime_file_readback": runtime_file_readback,
                }
            last_error = (
                f"stage={stage} hub_head_matches={hub_head == commit_oid} "
                f"remote_file_set_match={remote_file_set_match} "
                f"immutable_files_match={immutable_files_match} "
                f"attempt_matches={attempt_matches} "
                f"manifest_status={manifest_status} "
                f"manifest_same_origin={manifest_same_origin} "
                f"smoke_status={smoke_status} smoke_same_origin={smoke_same_origin} "
                f"runtime_files_match={runtime_files_match} "
                f"manifest_bookend_match={manifest_bookend_match}"
            )
        except Exception as exc:
            last_error = redact(str(exc))
        time.sleep(8)
    raise PublicationVerificationError(
        f"live verification did not converge: {last_error}",
        {
            "state": "COMMIT_CREATED_UNVERIFIED",
            "hf_commit": commit_oid,
            "hub_head": hub_head,
            "runtime_stage": stage,
            "deleted_paths": deleted,
            "remote_file_set_match": remote_file_set_match,
            "immutable_files_match": immutable_files_match,
            "immutable_file_readback": immutable_file_readback,
            "live_source_revision": live_source_revision(live_manifest),
            "manifest_status": manifest_status,
            "manifest_final_url": manifest_final_url,
            "manifest_same_origin": manifest_same_origin,
            "manifest_bookend_match": manifest_bookend_match,
            "smoke_status": smoke_status,
            "smoke_final_url": smoke_final_url,
            "smoke_same_origin": smoke_same_origin,
            "runtime_files_match": runtime_files_match,
            "runtime_file_readback": runtime_file_readback,
        },
    )


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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--publish", action="store_true")
    mode.add_argument("--materialize", type=Path)
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
        manifest_path = (
            args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
        )
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
        if args.materialize:
            output_root = args.materialize.resolve()
            materialized = materialize(output_root, files, deployment)
            report.update(
                {
                    "state": "MATERIALIZED",
                    "materialized_path": str(output_root),
                    "materialized_file_count": len(materialized),
                }
            )
        if args.publish:
            assert_publish_authority(contract, args.source_sha, dict(os.environ))
            assert_local_source(repo_root, args.source_sha)
            token = os.environ.get("HF_TOKEN", "")
            if not token:
                raise ContractError("HF_TOKEN is required for --publish")
            github_token = os.environ["GITHUB_TOKEN"]
            report.update(
                publish(
                    contract,
                    files,
                    deployment,
                    token,
                    github_token,
                    args.wait_seconds,
                )
            )
        write_report(args.report, report)
        return 0
    except PublicationVerificationError as exc:
        report.update(exc.result)
        report["error"] = redact(f"{type(exc).__name__}: {exc}")
        write_report(args.report, report)
        return 1
    except Exception as exc:  # fail closed and preserve a redacted report
        report["state"] = "FAILED"
        report["error"] = redact(f"{type(exc).__name__}: {exc}")
        write_report(args.report, report)
        return 1


if __name__ == "__main__":
    sys.exit(main())
