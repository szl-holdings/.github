#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pure public inventory projection. Never forward operator counters or errors."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

ORG = "SZLHOLDINGS"
KINDS = ("models", "datasets", "spaces", "kernels")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
ASSET_ID = re.compile(r"SZLHOLDINGS/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z", re.IGNORECASE)
SDK = frozenset(("docker", "gradio", "static", "streamlit"))
STAGES = frozenset(("RUNNING", "BUILDING", "APP_STARTING", "RUNNING_BUILDING", "RUNNING_APP_STARTING", "SLEEPING", "PAUSED", "STOPPED", "NO_APP_FILE", "CONFIG_ERROR", "BUILD_ERROR", "RUNTIME_ERROR", "DELETING", "UNKNOWN"))


def _timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        return None


def _sha(value: Any) -> str | None:
    return value if isinstance(value, str) and SHA40.fullmatch(value) and value != "0" * 40 else None


def _count(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= 2**53 - 1 else None


def _asset(item: dict[str, Any]) -> dict[str, Any]:
    identity = item.get("id")
    if not isinstance(identity, str) or not ASSET_ID.fullmatch(identity):
        raise ValueError("PUBLIC_ASSET_ID_REJECTED")
    sdk = item.get("sdk")
    return {
        "id": identity,
        "sha": _sha(item.get("sha")),
        "private": False,
        "sdk": sdk if isinstance(sdk, str) and sdk in SDK else None,
        "downloads": _count(item.get("downloads")),
        "likes": _count(item.get("likes")),
        "last_modified": _timestamp(item.get("last_modified")),
    }


def public_report(report: dict[str, Any]) -> dict[str, Any]:
    """Missing coverage stays unknown; only explicitly public repository rows pass.

    Aggregate operator counts and arbitrary error strings are not public data.
    The success/failure of the inventory job itself is still externally observable.
    This function does not establish completeness, source admission or runtime health.
    """
    if not isinstance(report, dict):
        raise ValueError("OPERATOR_REPORT_SHAPE_REJECTED")
    assets = report.get("assets", {})
    operator_counts = report.get("counts", {})
    if not isinstance(assets, dict) or not isinstance(operator_counts, dict):
        raise ValueError("OPERATOR_CATEGORIES_REJECTED")
    public_assets: dict[str, list[dict[str, Any]]] = {}
    counts: dict[str, int | None] = {}
    coverage: dict[str, str] = {}
    for kind in KINDS:
        if kind not in assets or ("counts" in report and operator_counts.get(kind) is None):
            counts[kind] = None
            coverage[kind] = "UNKNOWN"
            continue
        rows = assets[kind]
        if not isinstance(rows, list) or len(rows) > 10_000:
            raise ValueError("OPERATOR_CATEGORY_BOUND_REJECTED")
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in rows:
            if not isinstance(item, dict):
                raise ValueError("OPERATOR_ASSET_SHAPE_REJECTED")
            # Unknown visibility must not be interpreted as public.
            if item.get("private") is not False:
                continue
            row = _asset(item)
            key = row["id"].casefold()
            if key in seen:
                raise ValueError("PUBLIC_ASSET_DUPLICATE")
            seen.add(key)
            output.append(row)
        public_assets[kind] = sorted(output, key=lambda row: row["id"].casefold())
        counts[kind] = len(output)
        coverage[kind] = "OBSERVED_PUBLIC_ONLY"
    canonical = report.get("canonical_a11oy")
    public_canonical = None
    if isinstance(canonical, dict) and canonical.get("repo_id") == f"{ORG}/a11oy" and canonical.get("private") is False:
        sdk, stage = canonical.get("sdk"), canonical.get("stage")
        public_canonical = {
            "repo_id": f"{ORG}/a11oy", "sha": _sha(canonical.get("sha")),
            "sdk": sdk if isinstance(sdk, str) and sdk in SDK else None,
            "private": False,
            "stage": stage if isinstance(stage, str) and stage in STAGES else "UNKNOWN",
            "file_count": _count(canonical.get("file_count")),
        }
    return {
        "schema": "szl.hf-official-estate-public-projection/v1",
        "organization": ORG,
        "generated_at": _timestamp(report.get("generated_at")),
        "generation": _sha(report.get("generation")),
        "scope": "Observed public repository metadata only; private details withheld; not ORG_COMPLETE or runtime qualification.",
        "counts": counts,
        "coverage": coverage,
        "canonical_a11oy": public_canonical,
        "assets": public_assets,
        "summary": {
            "public_assets_observed": sum(value for value in counts.values() if value is not None),
            "categories_observed": sum(value is not None for value in counts.values()),
            "categories_unknown": sum(value is None for value in counts.values()),
        },
        # Deliberately fixed vocabulary, not a provider-supplied exception name.
        "error_class": "INVENTORY_FAILED" if report.get("error_class") or report.get("fatal") else None,
    }
