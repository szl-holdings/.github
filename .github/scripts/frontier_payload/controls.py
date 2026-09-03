# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .config import (
    HF_API, PRIVATE_SPACES, REPOSITORY_METADATA, VESSELS_CARD_URL,
    VESSELS_SPACE, WORKFLOW_CONTROLS, FrontierError,
)
from .net import GitHub, decode_json, redact, request


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def a11oy_alias_source_ready(api: GitHub) -> dict[str, Any]:
    try:
        source = api.file_text(
            "szl-holdings/a11oy", "cloudflare/a11oy-product-root-worker.mjs"
        )
        required = (
            '"/spectral": "/static/3d/holographic.html"',
            '"/controller": "/api/a11oy/v1/honest"',
            "READ_ONLY_METHODS",
        )
        missing = [marker for marker in required if marker not in source]
        return {
            "ready": not missing,
            "missing_markers": missing,
            "main_sha": api.main_sha("szl-holdings/a11oy"),
        }
    except Exception as exc:
        return {"ready": False, "missing_markers": [], "error": str(redact(str(exc)))}


def converge_repository_metadata(api: GitHub) -> list[dict[str, Any]]:
    rows = []
    for repository, desired in REPOSITORY_METADATA.items():
        row: dict[str, Any] = {
            "repository": repository,
            "desired": dict(desired),
            "mutation_boundary": sorted(desired),
        }
        try:
            before = api.repository(repository)
            row["before"] = {
                "description": before.get("description"),
                "archived": before.get("archived"),
                "visibility": before.get("visibility"),
            }
            changes = {key: value for key, value in desired.items() if before.get(key) != value}
            row["planned_changes"] = changes
            if changes:
                api.patch_repository(repository, changes)
            after = api.repository(repository) if api.apply and changes else before
            row["after"] = {
                "description": after.get("description"),
                "archived": after.get("archived"),
                "visibility": after.get("visibility"),
            }
            verified = all(after.get(key) == value for key, value in desired.items())
            row["state"] = (
                "VERIFIED" if verified else "WOULD_PATCH"
                if not api.apply and changes else "DRIFT"
            )
            row["verified"] = verified
        except Exception as exc:
            row.update(state="BLOCKED", verified=False, error=str(redact(str(exc))))
        rows.append(row)
    return rows


def validate_vessels_card(card: bytes) -> None:
    text = card.decode("utf-8", "strict")
    required = (
        "# Vessels — consolidated into Killinchu",
        "Status: CONSOLIDATED",
        "SZLHOLDINGS/killinchu",
        "No live AIS feed is claimed",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise FrontierError(f"reviewed Vessels card is missing markers: {missing}")


def _anonymous_hf_readback() -> bytes:
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        repo_id=VESSELS_SPACE,
        repo_type="space",
        filename="README.md",
        token=False,
        force_download=True,
    )
    return Path(path).read_bytes()


def converge_vessels_card(hf_token: str | None, *, apply: bool) -> dict[str, Any]:
    row: dict[str, Any] = {
        "repo_id": VESSELS_SPACE,
        "source_url": VESSELS_CARD_URL,
        "visibility_mutated": False,
        "hardware_mutated": False,
    }
    source = request("GET", VESSELS_CARD_URL, timeout=30)
    if source.get("status") != 200:
        row.update(
            state="BLOCKED_SOURCE",
            verified=False,
            error=f"source HTTP {source.get('status')}: {source.get('error')}",
        )
        return row
    card = bytes(source.get("body") or b"")
    try:
        validate_vessels_card(card)
    except Exception as exc:
        row.update(state="BLOCKED_SOURCE", verified=False, error=str(exc))
        return row
    row.update(source_sha256=digest(card), source_bytes=len(card))

    if apply:
        if not hf_token:
            row.update(
                state="BLOCKED_NO_WRITE_TOKEN",
                verified=False,
                error="HF write token was not available to the production job",
            )
            return row
        try:
            from huggingface_hub import HfApi

            commit = HfApi(token=hf_token).upload_file(
                path_or_fileobj=card,
                path_in_repo="README.md",
                repo_id=VESSELS_SPACE,
                repo_type="space",
                commit_message="docs: mark vessels consolidated into killinchu",
            )
            row["provider_commit"] = str(commit)
        except Exception as exc:
            row.update(state="BLOCKED_WRITE", verified=False, error=str(redact(str(exc))))
            return row

    try:
        observed = _anonymous_hf_readback()
        row.update(readback_status=200, readback_sha256=digest(observed))
    except Exception as exc:
        observed = b""
        row.update(
            readback_status=None,
            readback_sha256=None,
            readback_error=str(redact(str(exc))),
        )
    verified = observed == card
    row["verified"] = verified
    if verified:
        row["state"] = "VERIFIED"
    elif apply:
        row.update(
            state="READBACK_MISMATCH",
            error="anonymous Vessels README did not match reviewed source bytes",
        )
    else:
        row["state"] = "WOULD_UPDATE"
    return row


def review_private_spaces(hf_token: str | None) -> list[dict[str, Any]]:
    rows = []
    for name in PRIVATE_SPACES:
        repo_id = f"SZLHOLDINGS/{name}"
        row: dict[str, Any] = {
            "repo_id": repo_id,
            "publication_authorized": False,
            "visibility_mutated": False,
            "guardrail": "hold private until build completeness and claim honesty are reviewed",
        }
        if not hf_token:
            row["state"] = "UNOBSERVED_NO_TOKEN"
            rows.append(row)
            continue
        observed = request("GET", f"{HF_API}/spaces/{repo_id}", token=hf_token)
        value = decode_json(observed)
        if observed.get("status") != 200 or not isinstance(value, dict):
            row.update(
                state="BLOCKED_METADATA_READ",
                http_status=observed.get("status"),
                error=str(redact(observed.get("error") or "non-object metadata")),
            )
            rows.append(row)
            continue
        runtime = value.get("runtime") if isinstance(value.get("runtime"), dict) else {}
        card = value.get("cardData") if isinstance(value.get("cardData"), dict) else {}
        row.update(
            state="HELD_PRIVATE_PENDING_REVIEW",
            private=value.get("private"),
            sha=value.get("sha"),
            sdk=value.get("sdk") or card.get("sdk"),
            runtime_stage=runtime.get("stage"),
        )
        rows.append(row)
    return rows


def dispatch_controls(api: GitHub, *, enabled: bool) -> list[dict[str, Any]]:
    alias_source = a11oy_alias_source_ready(api)
    rows = []
    for control in WORKFLOW_CONTROLS:
        row = {
            "name": control["name"],
            "repository": control["repository"],
            "workflow": control["workflow"],
            "inputs": dict(control["inputs"]),
        }
        if control["precondition"] == "a11oy-alias-source" and not alias_source.get("ready"):
            row.update(
                state="BLOCKED_SOURCE_NOT_MERGED",
                dispatched=False,
                precondition=alias_source,
            )
        elif not enabled:
            row.update(state="OBSERVE_ONLY", dispatched=False)
        else:
            try:
                api.dispatch(control["repository"], control["workflow"], control["inputs"])
                row.update(
                    state="DISPATCHED" if api.apply else "WOULD_DISPATCH",
                    dispatched=api.apply,
                )
            except Exception as exc:
                row.update(state="BLOCKED", dispatched=False, error=str(redact(str(exc))))
        rows.append(row)
    return rows
