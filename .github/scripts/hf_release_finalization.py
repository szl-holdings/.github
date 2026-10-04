#!/usr/bin/env python3
"""Finalize merged SZLHOLDINGS Hugging Face releases with fail-closed evidence.

This release lane performs two bounded publications and one read-only verification:

* ``szl-holdings/szl-lake`` -> ``SZLHOLDINGS/szl-lake`` closed-tree verification;
* ``szl-holdings/szl-energy-attest`` -> the existing first-class
  ``SZLHOLDINGS/governed-inference-meter`` kernel card/contract;
* ``szl-holdings/szl-lambda-gate`` -> the existing first-class
  ``SZLHOLDINGS/szl-governed-norm`` kernel card/contract.

It never rebuilds or replaces kernel binaries, model weights, dataset receipt
contents, visibility, or hardware. Existing kernel builds remain intact; only
reviewed README/contract files are updated after the corresponding Hub repo is
proved to be an existing first-class kernel repository.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import requests
from huggingface_hub import HfApi, hf_hub_download
from pyarrow import parquet

ORG = "SZLHOLDINGS"
DATASET_ID = f"{ORG}/szl-lake"
EVIDENCE_DATASET = f"{ORG}/szl-evidence"
LAKE_SOURCE_REPOSITORY = "szl-holdings/szl-lake"
LAKE_INDEX_PATH = "lake_index.json"
LAKE_INDEX_SCHEMA = "szl.lake.index/v2"
LAKE_INDEX_ORIGINS = frozenset(
    {
        "SOURCE_CONTROLLED",
        "PRESERVED_REMOTE_AT_IMMUTABLE_REVISION",
        "HF_REPOSITORY_INFRASTRUCTURE_AT_IMMUTABLE_REVISION",
    }
)
LAKE_INDEX_ENTRY_FIELDS = frozenset(
    {"path", "bytes", "sha256", "origin", "binding_revision"}
)
LAKE_SOURCE_INDEX_CONTRACT = {
    "index_path": LAKE_INDEX_PATH,
    "self_reference": "EXCLUDED_TO_AVOID_HASH_FIXED_POINT",
    "publication_generated_exclusions": {
        "DATASET_PROVENANCE.json": (
            "EXCLUDED_BECAUSE_BYTES_BIND_THE_FINAL_SOURCE_REVISION"
        )
    },
    "scope": "SOURCE_CONTROLLED_STATIC_PAYLOAD",
}
LAKE_METADATA = {
    "name": "SZL Holdings Data Lake",
    "doctrine": "v11 LOCKED 749/14/163",
    "lambda": "Conjecture 1 (open)",
    "concept_doi": "10.5281/zenodo.19944926",
    "umbrella_doi": "10.5281/zenodo.20434276",
    "license": "CC-BY-4.0",
}
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
FULL_SHA256 = re.compile(r"^[0-9a-f]{64}$")
RECEIPT_PATH = re.compile(r"^khipu/([a-z0-9_]+)_receipts\.(ndjson|parquet)$")
MAX_LAKE_FILES = 10_000
MAX_LAKE_FILE_BYTES = 128 * 1024 * 1024
MAX_LAKE_INDEX_BYTES = 8 * 1024 * 1024
MAX_LAKE_TOTAL_BYTES = 512 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
PROVIDER_SCOPE_BOUNDARY = (
    "Provider-level exclusion of Lake write capability is UNKNOWN until a dedicated "
    "repository-scoped finalizer token is configured."
)
VIEWER_URL = (
    "https://datasets-server.huggingface.co/first-rows"
    "?dataset=SZLHOLDINGS%2Fszl-lake&config=receipts&split=train"
)
KERNEL_SPECS = {
    f"{ORG}/governed-inference-meter": {
        "source_root": "energy",
        "source_dir": "hf-kernels/governed-inference-meter",
    },
    f"{ORG}/szl-governed-norm": {
        "source_root": "lambda-gate",
        "source_dir": "hf-kernels/szl-governed-norm",
    },
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def exact_revision(value: object, *, label: str) -> str:
    revision = str(value).lower()
    if FULL_SHA.fullmatch(revision) is None:
        raise RuntimeError(f"{label} must be an exact 40-character Git SHA")
    return revision


def validated_repo_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError("repository path must be a non-empty string")
    if value.startswith("/") or "\\" in value or ":" in value:
        raise RuntimeError(f"repository path is not relative POSIX syntax: {value!r}")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise RuntimeError(f"repository path contains a control character: {value!r}")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise RuntimeError(f"repository path contains an unsafe segment: {value!r}")
    return value


def strict_json(payload: bytes, *, label: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise RuntimeError(f"{label} contains duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} is not UTF-8 JSON: {exc}") from exc


def require_lake_source_lineage(
    *, lake_root: Path, source_revision: object, checkout_revision: object
) -> tuple[str, str]:
    """Require the publication binding to be an ancestor of the exact checkout."""
    source_revision = exact_revision(source_revision, label="lake source revision")
    checkout_revision = exact_revision(
        checkout_revision, label="checked-out lake source revision"
    )
    head = subprocess.run(
        ["git", "-C", str(lake_root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if head.returncode != 0:
        raise RuntimeError("checked-out lake source revision is unreadable")
    observed = exact_revision(head.stdout.strip(), label="lake checkout HEAD")
    if observed != checkout_revision:
        raise RuntimeError(
            "checked-out lake source does not match the workflow binding"
        )
    ancestor = subprocess.run(
        [
            "git",
            "-C",
            str(lake_root),
            "merge-base",
            "--is-ancestor",
            source_revision,
            checkout_revision,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if ancestor.returncode != 0:
        raise RuntimeError(
            "published lake source revision is not an ancestor of the reviewed checkout"
        )
    return source_revision, checkout_revision


def _bounded_lake_source_payloads(
    payloads: dict[str, bytes], *, label: str
) -> dict[str, bytes]:
    if len(payloads) < 3 or len(payloads) > MAX_LAKE_FILES:
        raise RuntimeError(f"{label} has an invalid file count")
    total = 0
    for path, body in payloads.items():
        validated_repo_path(path)
        if not isinstance(body, bytes) or len(body) > MAX_LAKE_FILE_BYTES:
            raise RuntimeError(f"{label} exceeds the file safety bound: {path}")
        total += len(body)
        if total > MAX_LAKE_TOTAL_BYTES:
            raise RuntimeError(f"{label} exceeds the aggregate safety bound")
    return payloads


def _git_lake_source_projection(
    *, lake_root: Path, source_revision: str
) -> tuple[dict[str, bytes], bytes]:
    tree = subprocess.run(
        [
            "git",
            "-C",
            str(lake_root),
            "ls-tree",
            "-r",
            "-l",
            "-z",
            source_revision,
            "--",
            "LICENSE",
            "huggingface/README.md",
            "data",
        ],
        check=False,
        capture_output=True,
        timeout=60,
    )
    if tree.returncode != 0:
        raise RuntimeError("bound lake source tree is unreadable")
    objects: list[tuple[str, str, str, int]] = []
    total = 0
    for record in tree.stdout.split(b"\0"):
        if not record:
            continue
        try:
            metadata, encoded_path = record.split(b"\t", 1)
            mode, object_type, object_id, encoded_size = metadata.decode(
                "ascii"
            ).split()
            git_path = encoded_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError(
                "bound lake source tree contains invalid metadata"
            ) from exc
        if mode == "120000":
            raise RuntimeError(f"bound lake source contains a symlink: {git_path}")
        if object_type != "blob" or FULL_SHA.fullmatch(object_id) is None:
            raise RuntimeError(f"bound lake source path is not a Git blob: {git_path}")
        try:
            object_size = int(encoded_size)
        except ValueError as exc:
            raise RuntimeError(
                f"bound lake source size is invalid: {git_path}"
            ) from exc
        if object_size < 0 or object_size > MAX_LAKE_FILE_BYTES:
            raise RuntimeError(
                f"bound lake source exceeds the file safety bound: {git_path}"
            )
        total += object_size
        if total > MAX_LAKE_TOTAL_BYTES:
            raise RuntimeError("bound lake source exceeds the aggregate safety bound")
        if git_path == "LICENSE":
            relative = "LICENSE"
        elif git_path == "huggingface/README.md":
            relative = "README.md"
        elif git_path.startswith("data/"):
            relative = validated_repo_path(git_path.removeprefix("data/"))
            if relative == LAKE_INDEX_PATH:
                relative = ""
            elif "__pycache__" in relative.split("/") or relative.endswith(".pyc"):
                continue
        else:
            continue
        if not relative and object_size > MAX_LAKE_INDEX_BYTES:
            raise RuntimeError("bound lake source index exceeds the safety bound")
        objects.append((relative, git_path, object_id, object_size))
    if not objects or len(objects) > MAX_LAKE_FILES:
        raise RuntimeError("bound lake source projection has an invalid file count")
    batch = subprocess.run(
        ["git", "-C", str(lake_root), "cat-file", "--batch"],
        input=("\n".join(item[2] for item in objects) + "\n").encode("ascii"),
        check=False,
        capture_output=True,
        timeout=120,
    )
    if batch.returncode != 0:
        raise RuntimeError("bound lake source blobs are unreadable")
    payloads: dict[str, bytes] = {}
    checked_index: bytes | None = None
    offset = 0
    for relative, git_path, object_id, object_size in objects:
        header_end = batch.stdout.find(b"\n", offset)
        if header_end < 0:
            raise RuntimeError(f"bound lake source batch is truncated: {git_path}")
        try:
            observed_id, observed_type, observed_size = (
                batch.stdout[offset:header_end].decode("ascii").split()
            )
            observed_size = int(observed_size)
        except (UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError(
                f"bound lake source batch is invalid: {git_path}"
            ) from exc
        if (
            observed_id != object_id
            or observed_type != "blob"
            or observed_size != object_size
        ):
            raise RuntimeError(f"bound lake source batch metadata changed: {git_path}")
        body_start = header_end + 1
        body_end = body_start + object_size
        if batch.stdout[body_end : body_end + 1] != b"\n":
            raise RuntimeError(f"bound lake source batch body is truncated: {git_path}")
        body = batch.stdout[body_start:body_end]
        offset = body_end + 1
        if not relative:
            checked_index = body
            continue
        if relative in payloads:
            raise RuntimeError(f"bound lake source path is duplicated: {relative}")
        payloads[relative] = body
    if offset != len(batch.stdout):
        raise RuntimeError("bound lake source batch returned unexpected trailing bytes")
    if (
        checked_index is None
        or "README.md" not in payloads
        or "LICENSE" not in payloads
    ):
        raise RuntimeError("bound lake source projection is incomplete")
    return (
        _bounded_lake_source_payloads(payloads, label="bound lake source payload"),
        checked_index,
    )


def _validate_checked_source_index(
    *, payloads: dict[str, bytes], index_body: bytes, label: str
) -> list[dict[str, Any]]:
    if len(index_body) > MAX_LAKE_INDEX_BYTES:
        raise RuntimeError(f"{label} exceeds the safety bound")
    source_entries = [
        {"path": path, "bytes": len(body), "sha256": sha256_bytes(body)}
        for path, body in sorted(payloads.items())
    ]
    source_index = strict_json(index_body, label=label)
    expected_index = {
        "schema": "szl.lake.source-index/v2",
        **LAKE_METADATA,
        "contract": LAKE_SOURCE_INDEX_CONTRACT,
        "indexed_file_count": len(source_entries),
        "indexed_bytes": sum(item["bytes"] for item in source_entries),
        "entries_sha256": sha256_bytes(canonical_json(source_entries)),
        "files": source_entries,
    }
    if source_index != expected_index or index_body != canonical_json(expected_index):
        raise RuntimeError(f"{label} does not match its source tree")
    return source_entries


def expected_lake_source_payloads(
    *, lake_root: Path, source_revision: object, checkout_revision: object
) -> dict[str, bytes]:
    """Project exact bound bytes and reject drift from the reviewed checkout."""
    source_revision, _ = require_lake_source_lineage(
        lake_root=lake_root,
        source_revision=source_revision,
        checkout_revision=checkout_revision,
    )
    bound_payloads, bound_index = _git_lake_source_projection(
        lake_root=lake_root,
        source_revision=source_revision,
    )
    current_payloads, current_index = _git_lake_source_projection(
        lake_root=lake_root,
        source_revision=exact_revision(
            checkout_revision,
            label="checked-out lake source revision",
        ),
    )
    source_entries = _validate_checked_source_index(
        payloads=bound_payloads,
        index_body=bound_index,
        label="bound lake source index",
    )
    _validate_checked_source_index(
        payloads=current_payloads,
        index_body=current_index,
        label="checked lake source index",
    )
    if current_payloads != bound_payloads:
        changed = sorted(
            path
            for path in set(current_payloads) | set(bound_payloads)
            if current_payloads.get(path) != bound_payloads.get(path)
        )
        raise RuntimeError(
            "reviewed lake source payload differs from the publication binding: "
            f"{changed[:3]}"
        )

    provenance = {
        "schema": "szl.dataset-source-attestation/v2",
        "dataset": DATASET_ID,
        "source": {
            "repository": LAKE_SOURCE_REPOSITORY,
            "revision": source_revision,
            "relation": "CANONICAL_SOURCE_CONTROLLED_PAYLOAD",
        },
        "license": {
            "spdx": "CC-BY-4.0",
            "file": "LICENSE",
            "sha256": sha256_bytes(bound_payloads["LICENSE"]),
            "scope": "source-controlled dataset payload",
        },
        "payload": {
            "files": source_entries,
            "file_count": len(source_entries),
            "bytes": sum(item["bytes"] for item in source_entries),
        },
        "claims": {
            "source_binding": "EXACT_GIT_REVISION",
            "publication_readback": "REQUIRED_BEFORE_SUCCESS",
            "receipt_signature_validity": "SEPARATE_PER_RECEIPT_VERIFIERS",
            "receipt_truth_or_accuracy": "NOT_CLAIMED",
            "reproducible_dataset_bytes": "EXACT_FROM_SOURCE_REVISION",
        },
    }
    bound_payloads["DATASET_PROVENANCE.json"] = canonical_json(provenance)
    if sum(len(body) for body in bound_payloads.values()) > MAX_LAKE_TOTAL_BYTES:
        raise RuntimeError("lake source payload exceeds the aggregate safety bound")
    return bound_payloads


def immutable_repo_file_sizes(info: object) -> dict[str, int]:
    """Return an exact, bounded path-to-size map from immutable Hub metadata."""
    siblings = getattr(info, "siblings", None)
    if not isinstance(siblings, list) or not siblings:
        raise RuntimeError("immutable lake metadata lacks a closed file list")
    if len(siblings) > MAX_LAKE_FILES:
        raise RuntimeError("immutable lake tree exceeds the file safety bound")
    sizes: dict[str, int] = {}
    total = 0
    for sibling in siblings:
        raw_path = (
            sibling.get("rfilename")
            if isinstance(sibling, dict)
            else getattr(sibling, "rfilename", None)
        )
        raw_size = (
            sibling.get("size")
            if isinstance(sibling, dict)
            else getattr(sibling, "size", None)
        )
        path = validated_repo_path(raw_path)
        if path in sizes:
            raise RuntimeError(
                f"immutable lake metadata contains duplicate path: {path}"
            )
        if (
            not isinstance(raw_size, int)
            or isinstance(raw_size, bool)
            or raw_size < 0
            or raw_size > MAX_LAKE_FILE_BYTES
        ):
            raise RuntimeError(f"immutable lake metadata has invalid size: {path}")
        if path == LAKE_INDEX_PATH and raw_size > MAX_LAKE_INDEX_BYTES:
            raise RuntimeError("lake publication index exceeds the safety bound")
        sizes[path] = raw_size
        total += raw_size
        if total > MAX_LAKE_TOTAL_BYTES:
            raise RuntimeError("immutable lake tree exceeds the aggregate safety bound")
    return sizes


def verify_immediate_hf_predecessor(
    *, api: HfApi, revision: object, predecessor_revision: object
) -> None:
    """Require the index predecessor to be the publication commit's direct parent."""
    revision = exact_revision(revision, label="Hugging Face dataset revision")
    predecessor_revision = exact_revision(
        predecessor_revision, label="lake Hub predecessor revision"
    )
    if predecessor_revision == revision:
        raise RuntimeError("lake publication revision cannot be its own predecessor")
    commits = api.list_repo_commits(
        DATASET_ID,
        repo_type="dataset",
        revision=revision,
    )
    commit_ids = [
        exact_revision(getattr(commit, "commit_id", None), label="lake Hub commit")
        for commit in commits[:2]
    ]
    if commit_ids != [revision, predecessor_revision]:
        raise RuntimeError(
            "lake publication index predecessor is not the immutable revision's direct parent"
        )


def require_dataset_head(api: HfApi, expected_revision: object, *, phase: str) -> str:
    expected_revision = exact_revision(
        expected_revision, label="expected Hugging Face dataset revision"
    )
    observed = exact_revision(
        api.dataset_info(DATASET_ID).sha,
        label=f"Hugging Face dataset head during {phase}",
    )
    if observed != expected_revision:
        raise RuntimeError(
            f"Hugging Face dataset head changed during {phase}: "
            f"expected {expected_revision}, observed {observed}"
        )
    return observed


def receipt_count_evidence(path: str, body: bytes) -> tuple[str, int] | None:
    match = RECEIPT_PATH.fullmatch(path)
    if match is None:
        return None
    if match.group(2) == "parquet":
        try:
            count = parquet.read_metadata(io.BytesIO(body)).num_rows
        except Exception as exc:
            raise RuntimeError(
                f"lake receipt file is not valid Parquet: {path}"
            ) from exc
    else:
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError(f"lake receipt file is not UTF-8: {path}") from exc
        count = 0
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                receipt = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"lake receipt file has invalid JSON at {path}:{number}"
                ) from exc
            if not isinstance(receipt, dict):
                raise RuntimeError(f"lake receipt is not an object at {path}:{number}")
            count += 1
    return match.group(1), count


def validated_nonnegative_count(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RuntimeError(f"{label} must be a non-negative integer")
    return value


def validated_count_map(value: object, *, label: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be an object")
    result: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or not key:
            raise RuntimeError(f"{label} contains an invalid key")
        result[key] = validated_nonnegative_count(
            count,
            label=f"{label} value for {key}",
        )
    return result


def verify_closed_lake_index(
    *,
    index_body: bytes,
    revision: object,
    remote_sizes: dict[str, int],
    source_payloads_for_revision: Callable[[str], dict[str, bytes]],
    verify_predecessor: Callable[[str, str], None],
    predecessor_sizes_for_revision: Callable[[str], dict[str, int]],
    read_path: Callable[[str, int], bytes],
    read_predecessor_path: Callable[[str, str, int], bytes],
) -> dict[str, Any]:
    """Verify the immutable Hub tree against the source-owned closed index."""
    revision = exact_revision(revision, label="Hugging Face dataset revision")
    normalized_remote_sizes: dict[str, int] = {}
    remote_total = 0
    for raw_path, raw_size in remote_sizes.items():
        path = validated_repo_path(raw_path)
        if path in normalized_remote_sizes:
            raise RuntimeError(f"Hugging Face dataset returned duplicate path: {path}")
        if (
            not isinstance(raw_size, int)
            or isinstance(raw_size, bool)
            or raw_size < 0
            or raw_size > MAX_LAKE_FILE_BYTES
        ):
            raise RuntimeError(f"Hugging Face dataset returned invalid size: {path}")
        if path == LAKE_INDEX_PATH and raw_size > MAX_LAKE_INDEX_BYTES:
            raise RuntimeError("lake publication index exceeds the safety bound")
        normalized_remote_sizes[path] = raw_size
        remote_total += raw_size
    if len(normalized_remote_sizes) > MAX_LAKE_FILES:
        raise RuntimeError("Hugging Face dataset exceeds the file safety bound")
    if remote_total > MAX_LAKE_TOTAL_BYTES:
        raise RuntimeError("Hugging Face dataset exceeds the aggregate safety bound")
    if normalized_remote_sizes.get(LAKE_INDEX_PATH) != len(index_body):
        raise RuntimeError(
            "lake publication index size does not match immutable metadata"
        )
    if len(index_body) > MAX_LAKE_INDEX_BYTES:
        raise RuntimeError("lake publication index exceeds the safety bound")

    index = strict_json(index_body, label="lake publication index")
    if not isinstance(index, dict) or index.get("schema") != LAKE_INDEX_SCHEMA:
        raise RuntimeError(
            f"lake publication index must use schema {LAKE_INDEX_SCHEMA}"
        )

    bindings = index.get("bindings")
    if not isinstance(bindings, dict):
        raise RuntimeError("lake publication index bindings must be an object")
    if bindings.get("source_repository") != LAKE_SOURCE_REPOSITORY:
        raise RuntimeError("lake publication index has the wrong source repository")
    if bindings.get("hf_repository") != DATASET_ID:
        raise RuntimeError("lake publication index has the wrong Hub repository")
    source_revision = exact_revision(
        bindings.get("source_revision"), label="lake source revision"
    )
    predecessor_revision = exact_revision(
        bindings.get("hf_predecessor_revision"),
        label="lake Hub predecessor revision",
    )
    verify_predecessor(revision, predecessor_revision)
    predecessor_sizes = predecessor_sizes_for_revision(predecessor_revision)
    normalized_predecessor_sizes: dict[str, int] = {}
    predecessor_total = 0
    for raw_path, raw_size in predecessor_sizes.items():
        path = validated_repo_path(raw_path)
        if path in normalized_predecessor_sizes:
            raise RuntimeError(f"lake predecessor returned duplicate path: {path}")
        if (
            not isinstance(raw_size, int)
            or isinstance(raw_size, bool)
            or raw_size < 0
            or raw_size > MAX_LAKE_FILE_BYTES
        ):
            raise RuntimeError(f"lake predecessor returned invalid size: {path}")
        if path == LAKE_INDEX_PATH and raw_size > MAX_LAKE_INDEX_BYTES:
            raise RuntimeError("lake predecessor index exceeds the safety bound")
        normalized_predecessor_sizes[path] = raw_size
        predecessor_total += raw_size
    if (
        not normalized_predecessor_sizes
        or len(normalized_predecessor_sizes) > MAX_LAKE_FILES
    ):
        raise RuntimeError("lake predecessor has an invalid file count")
    if predecessor_total > MAX_LAKE_TOTAL_BYTES:
        raise RuntimeError("lake predecessor exceeds the aggregate safety bound")
    expected_source_payloads = source_payloads_for_revision(source_revision)
    normalized_source_payloads: dict[str, bytes] = {}
    for raw_path, body in expected_source_payloads.items():
        path = validated_repo_path(raw_path)
        if path == LAKE_INDEX_PATH or path in normalized_source_payloads:
            raise RuntimeError(f"reviewed lake source projection is invalid: {path}")
        if not isinstance(body, bytes):
            raise RuntimeError(f"reviewed lake source payload is not bytes: {path}")
        normalized_source_payloads[path] = body

    closure = index.get("closure")
    if not isinstance(closure, dict):
        raise RuntimeError("lake publication index closure must be an object")
    if closure.get("status") != "EXACT_POST_COMMIT_TREE_REQUIRED":
        raise RuntimeError("lake publication index does not require exact tree closure")
    self_reference = index.get("self_reference")
    if not isinstance(self_reference, dict):
        raise RuntimeError("lake publication index self-reference must be an object")
    if self_reference.get("path") != LAKE_INDEX_PATH:
        raise RuntimeError("lake publication index self-reference path is invalid")
    if self_reference.get("status") != "EXCLUDED_TO_AVOID_HASH_FIXED_POINT":
        raise RuntimeError("lake publication index self-reference contract is invalid")

    files = index.get("files")
    if not isinstance(files, list) or not files:
        raise RuntimeError("lake publication index files must be a non-empty list")
    if len(files) > MAX_LAKE_FILES:
        raise RuntimeError("lake publication index exceeds the file safety bound")

    normalized_entries: list[tuple[str, int, str, str]] = []
    paths: list[str] = []
    path_set: set[str] = set()
    source_paths: set[str] = set()
    predecessor_entries: list[tuple[str, int, str]] = []
    indexed_bytes = 0
    origin_counts: Counter[str] = Counter()
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != LAKE_INDEX_ENTRY_FIELDS:
            raise RuntimeError(
                "lake publication index entry has unknown or missing fields"
            )
        path = validated_repo_path(entry.get("path"))
        if path == LAKE_INDEX_PATH:
            raise RuntimeError("lake publication index cannot hash itself")
        if path in path_set:
            raise RuntimeError(
                f"lake publication index contains duplicate path: {path}"
            )
        expected_bytes = entry.get("bytes")
        if (
            not isinstance(expected_bytes, int)
            or isinstance(expected_bytes, bool)
            or expected_bytes < 0
            or expected_bytes > MAX_LAKE_FILE_BYTES
        ):
            raise RuntimeError(f"lake publication index has invalid byte count: {path}")
        expected_sha256 = entry.get("sha256")
        if (
            not isinstance(expected_sha256, str)
            or FULL_SHA256.fullmatch(expected_sha256) is None
        ):
            raise RuntimeError(f"lake publication index has invalid SHA-256: {path}")
        origin = entry.get("origin")
        if origin not in LAKE_INDEX_ORIGINS:
            raise RuntimeError(f"lake publication index has invalid origin: {path}")
        binding_revision = exact_revision(
            entry.get("binding_revision"), label=f"lake binding revision for {path}"
        )
        expected_binding = (
            source_revision if origin == "SOURCE_CONTROLLED" else predecessor_revision
        )
        if binding_revision != expected_binding:
            raise RuntimeError(f"lake publication index has mismatched binding: {path}")
        if normalized_remote_sizes.get(path) != expected_bytes:
            raise RuntimeError(
                f"lake publication payload size differs from immutable metadata: {path}"
            )
        if origin == "SOURCE_CONTROLLED":
            source_body = normalized_source_payloads.get(path)
            if source_body is None:
                raise RuntimeError(
                    f"lake publication has an unreviewed source-controlled path: {path}"
                )
            if (
                len(source_body) != expected_bytes
                or sha256_bytes(source_body) != expected_sha256
            ):
                raise RuntimeError(
                    f"lake publication source bytes do not match the reviewed checkout: {path}"
                )
            source_paths.add(path)
        else:
            if normalized_predecessor_sizes.get(path) != expected_bytes:
                raise RuntimeError(
                    "lake publication predecessor does not contain the preserved path: "
                    f"{path}"
                )
            predecessor_entries.append((path, expected_bytes, expected_sha256))
        paths.append(path)
        path_set.add(path)
        indexed_bytes += expected_bytes
        origin_counts[origin] += 1
        normalized_entries.append((path, expected_bytes, expected_sha256, origin))

    if paths != sorted(paths):
        raise RuntimeError("lake publication index paths are not sorted")
    if source_paths != set(normalized_source_payloads):
        missing = sorted(set(normalized_source_payloads) - source_paths)
        raise RuntimeError(
            f"lake publication omits reviewed source-controlled paths: {missing[:3]}"
        )
    indexed_predecessor_paths = {path for path, _size, _digest in predecessor_entries}
    required_predecessor_paths = (
        set(normalized_predecessor_sizes)
        - {LAKE_INDEX_PATH}
        - set(normalized_source_payloads)
    )
    if indexed_predecessor_paths != required_predecessor_paths:
        missing = sorted(required_predecessor_paths - indexed_predecessor_paths)
        unexpected = sorted(indexed_predecessor_paths - required_predecessor_paths)
        raise RuntimeError(
            "lake publication does not preserve the predecessor tree "
            f"(missing={missing[:3]}, unexpected={unexpected[:3]})"
        )
    expected_tree = sorted([*paths, LAKE_INDEX_PATH])
    if sorted(normalized_remote_sizes) != expected_tree:
        missing = sorted(set(expected_tree) - set(normalized_remote_sizes))
        unexpected = sorted(set(normalized_remote_sizes) - set(expected_tree))
        raise RuntimeError(
            "lake publication tree is not closed "
            f"(missing={missing[:3]}, unexpected={unexpected[:3]})"
        )
    if validated_nonnegative_count(
        closure.get("indexed_file_count"),
        label="lake publication indexed file count",
    ) != len(files):
        raise RuntimeError("lake publication index file count is inconsistent")
    if validated_nonnegative_count(
        closure.get("published_file_count_including_index"),
        label="lake publication published file count",
    ) != len(expected_tree):
        raise RuntimeError(
            "lake publication index published file count is inconsistent"
        )
    if (
        validated_nonnegative_count(
            closure.get("indexed_bytes"),
            label="lake publication indexed bytes",
        )
        != indexed_bytes
    ):
        raise RuntimeError("lake publication index byte count is inconsistent")
    if closure.get("entries_sha256") != sha256_bytes(canonical_json(files)):
        raise RuntimeError("lake publication index entry digest is inconsistent")
    if validated_count_map(
        closure.get("origin_counts"),
        label="lake publication origin counts",
    ) != dict(sorted(origin_counts.items())):
        raise RuntimeError("lake publication index origin counts are inconsistent")

    predecessor_bytes_verified = 0
    for path, expected_bytes, expected_sha256 in predecessor_entries:
        try:
            predecessor_body = read_predecessor_path(
                path,
                predecessor_revision,
                expected_bytes,
            )
        except Exception as exc:
            raise RuntimeError(
                f"lake predecessor payload is unreadable: {path}"
            ) from exc
        if (
            not isinstance(predecessor_body, bytes)
            or len(predecessor_body) != expected_bytes
            or sha256_bytes(predecessor_body) != expected_sha256
        ):
            raise RuntimeError(
                f"lake publication payload was not preserved from its predecessor: {path}"
            )
        predecessor_bytes_verified += len(predecessor_body)

    organ_counts: Counter[str] = Counter()
    receipt_file_counts: dict[str, int] = {}
    for path, expected_bytes, expected_sha256, _origin in normalized_entries:
        try:
            body = read_path(path, expected_bytes)
        except Exception as exc:
            raise RuntimeError(
                f"lake publication payload is unreadable: {path}"
            ) from exc
        if not isinstance(body, bytes):
            raise RuntimeError(f"lake publication payload is not bytes: {path}")
        if len(body) != expected_bytes or sha256_bytes(body) != expected_sha256:
            raise RuntimeError(
                f"lake publication payload does not match the index: {path}"
            )
        receipt_evidence = receipt_count_evidence(path, body)
        if receipt_evidence is not None:
            organ, count = receipt_evidence
            organ_counts[organ] += count
            receipt_file_counts[path] = count
    expected_organ_counts = dict(sorted(organ_counts.items()))
    if (
        validated_count_map(
            index.get("khipu_receipt_counts"),
            label="lake publication organ receipt counts",
        )
        != expected_organ_counts
    ):
        raise RuntimeError("lake publication organ receipt counts are inconsistent")
    if validated_count_map(
        index.get("khipu_receipt_file_counts"),
        label="lake publication receipt file counts",
    ) != dict(sorted(receipt_file_counts.items())):
        raise RuntimeError("lake publication receipt file counts are inconsistent")
    if validated_nonnegative_count(
        index.get("total_khipu_receipts"),
        label="lake publication total receipt count",
    ) != sum(organ_counts.values()):
        raise RuntimeError("lake publication total receipt count is inconsistent")

    return {
        "revision": revision,
        "source_revision": source_revision,
        "predecessor_revision": predecessor_revision,
        "files_verified": len(expected_tree),
        "bytes_verified": remote_total,
        "predecessor_files_verified": len(predecessor_entries),
        "predecessor_bytes_verified": predecessor_bytes_verified,
        "index_sha256": sha256_bytes(index_body),
        "card_sha256": sha256_bytes(normalized_source_payloads["README.md"]),
    }


@dataclass
class Action:
    target: str
    action: str
    status: str
    detail: str = ""


class Finalizer:
    def __init__(
        self,
        *,
        token: str,
        publish: bool,
        generation: str,
        lake_root: Path,
        energy_root: Path,
        lambda_root: Path,
    ) -> None:
        self.token = token
        self.publish = publish
        self.generation = generation
        self.roots = {
            "lake": lake_root,
            "energy": energy_root,
            "lambda-gate": lambda_root,
        }
        self.api = HfApi(token=token)
        self.actions: list[Action] = []
        self.results: dict[str, Any] = {}

    def record(self, target: str, action: str, status: str, detail: str = "") -> None:
        self.actions.append(Action(target, action, status, detail))
        print(f"[{status:>10}] {action}: {target}" + (f" — {detail}" if detail else ""))

    @staticmethod
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def authenticate(self) -> None:
        who = self.api.whoami()
        orgs = who.get("orgs") or []
        match = next(
            (
                item
                for item in orgs
                if str(item.get("name") or item.get("fullname") or "").upper() == ORG
            ),
            None,
        )
        if match is None:
            raise RuntimeError(f"authenticated identity is not a member of {ORG}")
        role = str(match.get("roleInOrg") or match.get("role") or "").lower()
        if role and role not in {"admin", "write", "contributor"}:
            raise RuntimeError(f"authenticated role is not write-capable: {role}")
        self.record(
            ORG,
            "authenticate",
            "validated",
            f"identity={who.get('name')}; role={role or 'unknown'}",
        )

    def _download_verified(
        self,
        repo_id: str,
        filename: str,
        repo_type: str,
        revision: str | None = None,
    ) -> bytes:
        local = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            repo_type=repo_type,
            revision=revision,
            token=self.token,
            force_download=True,
        )
        return Path(local).read_bytes()

    def _download_dataset_path(
        self,
        *,
        filename: str,
        revision: str,
        expected_bytes: int,
    ) -> bytes:
        """Stream an immutable public dataset path with a hard byte cutoff."""
        filename = validated_repo_path(filename)
        revision = exact_revision(revision, label="Hugging Face dataset revision")
        if (
            not isinstance(expected_bytes, int)
            or isinstance(expected_bytes, bool)
            or expected_bytes < 0
            or expected_bytes > MAX_LAKE_FILE_BYTES
        ):
            raise RuntimeError(f"invalid immutable dataset size for {filename}")
        if filename == LAKE_INDEX_PATH and expected_bytes > MAX_LAKE_INDEX_BYTES:
            raise RuntimeError("lake publication index exceeds the safety bound")
        url = (
            f"https://huggingface.co/datasets/{DATASET_ID}/resolve/"
            f"{revision}/{quote(filename, safe='/')}"
        )
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        response = requests.get(
            url,
            headers=headers,
            allow_redirects=True,
            stream=True,
            timeout=(30, 90),
        )
        try:
            response.raise_for_status()
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    advertised = int(content_length)
                except ValueError as exc:
                    raise RuntimeError(
                        f"immutable dataset returned an invalid Content-Length: {filename}"
                    ) from exc
                if advertised > expected_bytes:
                    raise RuntimeError(
                        f"immutable dataset response exceeds the indexed size: {filename}"
                    )
            body = bytearray()
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
                if not chunk:
                    continue
                if len(body) + len(chunk) > expected_bytes:
                    raise RuntimeError(
                        f"immutable dataset response exceeds the indexed size: {filename}"
                    )
                body.extend(chunk)
            if len(body) != expected_bytes:
                raise RuntimeError(
                    f"immutable dataset response size does not match metadata: {filename}"
                )
            return bytes(body)
        finally:
            response.close()

    def _immutable_dataset_sizes(self, revision: object) -> dict[str, int]:
        revision = exact_revision(revision, label="Hugging Face dataset revision")
        info = self.api.dataset_info(
            DATASET_ID,
            files_metadata=True,
            revision=revision,
        )
        observed = exact_revision(
            info.sha,
            label="immutable Hugging Face dataset revision",
        )
        if observed != revision:
            raise RuntimeError("immutable lake lookup returned a different revision")
        return immutable_repo_file_sizes(info)

    def finalize_dataset(self) -> None:
        root = self.roots["lake"]
        card = root / "huggingface" / "README.md"
        data = root / "data"
        if not card.is_file() or not data.is_dir():
            raise RuntimeError("szl-lake checkout is missing card or data directory")

        required = [
            data / "khipu" / "amaru_receipts.parquet",
            data / "khipu" / "sentra_receipts.parquet",
            data / "khipu" / "a11oy_receipts.parquet",
            data / "khipu" / "rosie_receipts.parquet",
            data / "khipu" / "killinchu_receipts.parquet",
            data / "khipu" / "EMPTY_CHAIN_MANIFEST.json",
        ]
        missing = [
            str(path.relative_to(root)) for path in required if not path.is_file()
        ]
        if missing:
            raise RuntimeError(f"szl-lake viewer payload is incomplete: {missing}")

        checkout_revision = exact_revision(
            os.environ.get("SZL_LAKE_SHA"),
            label="checked-out lake source revision",
        )
        revision = exact_revision(
            self.api.dataset_info(DATASET_ID).sha,
            label="Hugging Face dataset revision",
        )
        remote_sizes = self._immutable_dataset_sizes(revision)
        if LAKE_INDEX_PATH not in remote_sizes:
            raise RuntimeError("immutable lake tree is missing the publication index")
        index_body = self._download_dataset_path(
            filename=LAKE_INDEX_PATH,
            revision=revision,
            expected_bytes=remote_sizes[LAKE_INDEX_PATH],
        )
        closure = verify_closed_lake_index(
            index_body=index_body,
            revision=revision,
            remote_sizes=remote_sizes,
            source_payloads_for_revision=lambda source_revision: (
                expected_lake_source_payloads(
                    lake_root=root,
                    source_revision=source_revision,
                    checkout_revision=checkout_revision,
                )
            ),
            verify_predecessor=lambda observed, predecessor: (
                verify_immediate_hf_predecessor(
                    api=self.api,
                    revision=observed,
                    predecessor_revision=predecessor,
                )
            ),
            predecessor_sizes_for_revision=self._immutable_dataset_sizes,
            read_path=lambda path, expected_bytes: self._download_dataset_path(
                filename=path,
                revision=revision,
                expected_bytes=expected_bytes,
            ),
            read_predecessor_path=lambda path, predecessor, expected_bytes: (
                self._download_dataset_path(
                    filename=path,
                    revision=predecessor,
                    expected_bytes=expected_bytes,
                )
            ),
        )
        self.record(
            DATASET_ID,
            "dataset-publication-authority",
            "validated",
            "read-only; writer=szl-holdings/szl-lake/.github/workflows/hf-sync.yml",
        )

        for expected in (
            "khipu/amaru_receipts.parquet",
            "khipu/sentra_receipts.parquet",
            "khipu/a11oy_receipts.parquet",
            "khipu/rosie_receipts.parquet",
            "khipu/killinchu_receipts.parquet",
            "khipu/EMPTY_CHAIN_MANIFEST.json",
        ):
            if expected not in remote_sizes:
                raise RuntimeError(f"published dataset is missing {expected}")

        require_dataset_head(self.api, revision, phase="pre-Viewer exact-head check")
        response = requests.get(VIEWER_URL, timeout=90)
        if response.status_code != 200:
            raise RuntimeError(
                f"Dataset Viewer contract did not return HTTP 200: {response.status_code} "
                f"{response.text[:300]}"
            )
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("error"):
            raise RuntimeError(f"Dataset Viewer returned an error payload: {payload}")
        require_dataset_head(self.api, revision, phase="post-Viewer exact-head check")
        self.record(
            DATASET_ID,
            "dataset-verify",
            "validated",
            f"revision={revision}; files={len(remote_sizes)}; "
            f"closed_index={closure['index_sha256']}; "
            "viewer=HTTP-200-MUTABLE-HEAD-STABLE-DURING-PROBE",
        )
        self.results["dataset"] = {
            "repo_id": DATASET_ID,
            "before_sha": revision,
            "after_sha": revision,
            "revision": revision,
            "changed": False,
            "publication_authority": (
                "szl-holdings/szl-lake/.github/workflows/hf-sync.yml"
            ),
            "card_sha256": closure["card_sha256"],
            "index_sha256": closure["index_sha256"],
            "source_revision": closure["source_revision"],
            "hf_predecessor_revision": closure["predecessor_revision"],
            "files_verified": closure["files_verified"],
            "bytes_verified": closure["bytes_verified"],
            "predecessor_files_verified": closure["predecessor_files_verified"],
            "predecessor_bytes_verified": closure["predecessor_bytes_verified"],
            "viewer_http_status": response.status_code,
            "viewer_evidence_class": "MUTABLE_HEAD_STABLE_DURING_PROBE",
            "remote_file_count": len(remote_sizes),
        }

    def _kernel_selfcheck(self, repo_id: str, revision: str) -> Any:
        from kernels import get_kernel

        module = get_kernel(
            repo_id,
            revision=revision,
            trust_remote_code=True,
        )
        check = getattr(module, "selfcheck", None)
        if not callable(check):
            raise RuntimeError(f"{repo_id}@{revision} does not expose selfcheck()")
        result = check()
        if result is False:
            raise RuntimeError(f"{repo_id}@{revision} selfcheck returned false")
        if isinstance(result, dict) and result.get("ok") is False:
            raise RuntimeError(f"{repo_id}@{revision} selfcheck failed: {result}")
        return result

    def finalize_kernel(self, repo_id: str, spec: dict[str, str]) -> None:
        source_root = self.roots[spec["source_root"]]
        source_dir = source_root / spec["source_dir"]
        card = source_dir / "README.md"
        contract = source_dir / "contract.json"
        if not card.is_file() or not contract.is_file():
            raise RuntimeError(f"kernel source contract is incomplete: {source_dir}")
        contract_payload = json.loads(contract.read_text(encoding="utf-8"))
        if not isinstance(contract_payload, dict):
            raise RuntimeError(f"kernel contract is not an object: {contract}")

        before_info = self.api.kernel_info(repo_id)
        before = str(getattr(before_info, "sha", "") or "")
        if len(before) != 40:
            raise RuntimeError(f"kernel repository lacks immutable revision: {repo_id}")
        remote_files_before = set(self.api.list_repo_files(repo_id, repo_type="kernel"))
        if not any(path.startswith("build/") for path in remote_files_before):
            raise RuntimeError(
                f"first-class kernel repository lacks build variants: {repo_id}"
            )
        self.record(
            repo_id,
            "kernel-preflight",
            "validated",
            f"before={before}; builds_present=true",
        )

        if self.publish:
            for source, destination in (
                (card, "README.md"),
                (contract, "contract.json"),
            ):
                self.api.upload_file(
                    repo_id=repo_id,
                    repo_type="kernel",
                    path_or_fileobj=str(source),
                    path_in_repo=destination,
                    commit_message=(
                        "release(card): publish reviewed kernel contract "
                        f"{self.generation[:12]}"
                    ),
                    commit_description=(
                        "Card/contract-only publication from the canonical GitHub owner. "
                        "Existing first-class kernel build variants are preserved."
                    ),
                )
            self.record(repo_id, "kernel-card-publish", "updated")
        else:
            self.record(repo_id, "kernel-card-publish", "dry-run")

        after_info = self.api.kernel_info(repo_id)
        after = str(getattr(after_info, "sha", "") or "")
        if len(after) != 40:
            raise RuntimeError(f"published kernel lacks immutable revision: {repo_id}")
        for source, filename in ((card, "README.md"), (contract, "contract.json")):
            observed = self._download_verified(repo_id, filename, "kernel", after)
            if observed != source.read_bytes():
                raise RuntimeError(
                    f"published kernel file differs from reviewed source: {repo_id}/{filename}"
                )
        remote_files_after = set(self.api.list_repo_files(repo_id, repo_type="kernel"))
        if not any(path.startswith("build/") for path in remote_files_after):
            raise RuntimeError(f"kernel publication removed build variants: {repo_id}")
        selfcheck = self._kernel_selfcheck(repo_id, after)
        self.record(
            repo_id,
            "kernel-verify",
            "validated",
            f"after={after}; selfcheck=passed; files={len(remote_files_after)}",
        )
        self.results.setdefault("kernels", {})[repo_id] = {
            "before_sha": before,
            "after_sha": after,
            "card_sha256": self.digest(card),
            "contract_sha256": self.digest(contract),
            "remote_file_count": len(remote_files_after),
            "selfcheck": selfcheck,
        }

    def report(self) -> dict[str, Any]:
        statuses = [action.status for action in self.actions]
        return {
            "schema": "szl.hf-release-finalization/v1",
            "organization": ORG,
            "generation": self.generation,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "publish": self.publish,
            "sources": {
                "szl_lake": os.environ.get("SZL_LAKE_SHA"),
                "szl_energy_attest": os.environ.get("SZL_ENERGY_ATTEST_SHA"),
                "szl_lambda_gate": os.environ.get("SZL_LAMBDA_GATE_SHA"),
            },
            "results": self.results,
            "actions": [asdict(action) for action in self.actions],
            "summary": {
                "ok": sum(
                    status in {"validated", "updated", "ok"} for status in statuses
                ),
                "warning": sum(status == "warning" for status in statuses),
                "error": sum(status == "error" for status in statuses),
                "dry_run": sum(status == "dry-run" for status in statuses),
            },
            "boundaries": [
                "Lake publication is source-owned by szl-holdings/szl-lake; this controller performs read-only immutable closure verification.",
                PROVIDER_SCOPE_BOUNDARY,
                "Only reviewed README.md and contract.json files are updated in existing first-class kernel repositories.",
                "Kernel build variants, visibility, and hardware are preserved.",
                "Kernel selfcheck is executed at the exact post-publication immutable revision.",
                "No model weights are trained, merged, relabeled, or promoted.",
            ],
        }

    def publish_evidence(self, report: dict[str, Any]) -> None:
        rendered = (
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"
        ).encode()
        output = Path("reports/hf-release-finalization-latest.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(rendered)
        self.record(str(output), "local-report", "updated")
        if not self.publish:
            return
        self.api.create_repo(
            repo_id=EVIDENCE_DATASET,
            repo_type="dataset",
            private=True,
            exist_ok=True,
        )
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for destination in (
            "release-finalization/latest.json",
            f"release-finalization/history/{timestamp}.json",
        ):
            self.api.upload_file(
                repo_id=EVIDENCE_DATASET,
                repo_type="dataset",
                path_or_fileobj=io.BytesIO(rendered),
                path_in_repo=destination,
                commit_message=f"release(evidence): record Hub finalization {timestamp}",
            )
        self.record(EVIDENCE_DATASET, "evidence-publish", "updated")

    def run(self) -> dict[str, Any]:
        self.authenticate()
        self.finalize_dataset()
        for repo_id, spec in KERNEL_SPECS.items():
            self.finalize_kernel(repo_id, spec)
        report = self.report()
        self.publish_evidence(report)
        report = self.report()
        Path("reports/hf-release-finalization-latest.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--generation", required=True)
    parser.add_argument("--lake-root", default="lake")
    parser.add_argument("--energy-root", default="energy")
    parser.add_argument("--lambda-root", default="lambda-gate")
    args = parser.parse_args()

    token = (
        os.environ.get("HF_ORG_TOKEN")
        or os.environ.get("HF_ORG_TOKEN1")
        or os.environ.get("HF_TOKEN")
    )
    if not token:
        print(
            "FATAL: no supported Hugging Face token is configured", file=os.sys.stderr
        )
        return 2

    try:
        report = Finalizer(
            token=token,
            publish=args.publish,
            generation=args.generation,
            lake_root=Path(args.lake_root),
            energy_root=Path(args.energy_root),
            lambda_root=Path(args.lambda_root),
        ).run()
    except Exception as exc:  # fail closed with an explicit local report when possible
        Path("reports").mkdir(exist_ok=True)
        failure = {
            "schema": "szl.hf-release-finalization/v1",
            "generation": args.generation,
            "publish": args.publish,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fatal": f"{type(exc).__name__}: {exc}",
            "summary": {"ok": 0, "warning": 0, "error": 1, "dry_run": 0},
        }
        Path("reports/hf-release-finalization-latest.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"FATAL: {exc!r}", file=os.sys.stderr)
        return 2

    summary = report["summary"]
    print(json.dumps(summary, indent=2))
    return 1 if summary["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
