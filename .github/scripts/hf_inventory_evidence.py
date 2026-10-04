#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""One private inventory commit with an expected parent and immutable readback."""
from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
from pathlib import Path

from huggingface_hub import CommitOperationAdd, __version__ as HUB_VERSION

from verify_hf_inventory_source import require_protected_source

EVIDENCE_DATASET = "SZLHOLDINGS/szl-evidence"
LATEST_PATH = "estate/official-inventory/latest.json"
MAX_REPORT_BYTES = 8 * 1024 * 1024
REVIEWED_HUB_VERSION = "1.23.0"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


def _revision(value, code):
    if not isinstance(value, str) or not SHA40.fullmatch(value) or value == "0" * 40:
        raise RuntimeError(code)
    return value


def _private_dataset_revision(api):
    info = api.dataset_info(EVIDENCE_DATASET, revision="main", timeout=30)
    if getattr(info, "id", None) != EVIDENCE_DATASET or getattr(info, "private", None) is not True:
        raise RuntimeError("PRIVATE_EVIDENCE_DATASET_REQUIRED")
    return _revision(getattr(info, "sha", None), "EVIDENCE_REVISION_REQUIRED")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate inventory key")
        result[key] = value
    return result


def _finite_number(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("nonfinite inventory number")
    return number


def _validate_report(rendered, generation):
    try:
        report = json.loads(rendered, object_pairs_hook=_unique_object, parse_constant=_finite_number, parse_float=_finite_number)
    except (ValueError, UnicodeError, RecursionError):
        raise RuntimeError("EVIDENCE_REPORT_JSON_REJECTED") from None
    if not isinstance(report, dict) or report.get("organization") != "SZLHOLDINGS" or report.get("generation") != generation or report.get("schema") not in {"szl.hf-official-estate-inventory/v1", "szl.hf-official-estate-inventory/v2"}:
        raise RuntimeError("EVIDENCE_REPORT_IDENTITY_REJECTED")


def publish_report(api, rendered: bytes, *, generation: str) -> str:
    """Never retry a conflict, overwrite a history path, or certify an unread write.

    The budget is one SDK commit with exactly two bounded JSON additions. SDK
    transport requests are not equivalent to commit invocation counts. Dataset
    visibility is observed before and after; this cannot stop an independent
    administrator from changing visibility concurrently.
    """
    if HUB_VERSION != REVIEWED_HUB_VERSION:
        raise RuntimeError("EVIDENCE_SDK_VERSION_UNREVIEWED")
    generation = _revision(generation, "EVIDENCE_SOURCE_REVISION_REQUIRED")
    if type(rendered) is not bytes or not rendered or len(rendered) > MAX_REPORT_BYTES:
        raise RuntimeError("EVIDENCE_REPORT_BOUND_REJECTED")
    _validate_report(rendered, generation)
    if getattr(api, "endpoint", None) != "https://huggingface.co":
        raise RuntimeError("EVIDENCE_ORIGIN_REJECTED")
    require_protected_source(generation)
    expected_before = _private_dataset_revision(api)
    digest = hashlib.sha256(rendered).hexdigest()
    history_path = f"estate/official-inventory/history/{generation}/{digest}.json"
    exists = api.file_exists(EVIDENCE_DATASET, history_path, repo_type="dataset", revision=expected_before)
    if exists is not False:
        raise RuntimeError("EVIDENCE_HISTORY_ALREADY_EXISTS_OR_UNKNOWN")
    operations = [
        CommitOperationAdd(path_in_repo=LATEST_PATH, path_or_fileobj=rendered),
        CommitOperationAdd(path_in_repo=history_path, path_or_fileobj=rendered),
    ]
    commit = api.create_commit(
        repo_id=EVIDENCE_DATASET,
        repo_type="dataset",
        revision="main",
        parent_commit=expected_before,
        create_pr=False,
        operations=operations,
        commit_message=f"chore(estate): record verified-source inventory {generation}",
    )
    # Hub 1.23 sets this flag only after _send_commit returns. Its no-op shortcut
    # returns a current OID without submitting the expected-parent condition.
    if any(getattr(operation, "_is_committed", None) is not True for operation in operations):
        raise RuntimeError("EVIDENCE_COMMIT_NOT_SUBMITTED")
    after = _revision(getattr(commit, "oid", None), "EVIDENCE_COMMIT_RECEIPT_REJECTED")
    if after == expected_before:
        raise RuntimeError("EVIDENCE_COMMIT_DID_NOT_ADVANCE")
    # The private temporary cache is removed on success and on every failure.
    with tempfile.TemporaryDirectory(prefix="hf-inventory-readback-") as cache:
        for destination in (LATEST_PATH, history_path):
            local = api.hf_hub_download(
                repo_id=EVIDENCE_DATASET,
                repo_type="dataset",
                filename=destination,
                revision=after,
                force_download=True,
                cache_dir=cache,
            )
            path = Path(local).resolve(strict=True)
            if not path.is_relative_to(Path(cache).resolve()):
                raise RuntimeError("EVIDENCE_READBACK_CACHE_REJECTED")
            with path.open("rb") as source:
                observed = source.read(MAX_REPORT_BYTES + 1)
            if observed != rendered:
                raise RuntimeError("EVIDENCE_READBACK_MISMATCH")
    if _private_dataset_revision(api) != after:
        raise RuntimeError("EVIDENCE_HEAD_MOVED_AFTER_COMMIT")
    require_protected_source(generation)
    return after
