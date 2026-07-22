#!/usr/bin/env python3
"""Run the SZLHOLDINGS Hub estate publisher with supported inventory APIs.

The active estate reconciler remains authoritative for publication, clone
synchronization, collection curation, kernel validation, and evidence writing.
This wrapper replaces only inventory discovery so collection and bucket counts
are obtained through the supported ``huggingface_hub`` client instead of
unstable raw endpoints.
"""
from __future__ import annotations

import argparse
import dataclasses
import inspect
import json
import os
import sys
import time
from datetime import date, datetime
from enum import Enum
from typing import Any, Iterable

import hf_estate_canonicalize as active

ORG = active.legacy.ORG


def _base_class():
    for name in ("CommandCenterEstateUpgrade", "CanonicalEstateUpgrade"):
        candidate = getattr(active, name, None)
        if isinstance(candidate, type):
            return candidate
    raise RuntimeError("active Hugging Face estate reconciler class was not found")


BaseEstateUpgrade = _base_class()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if dataclasses.is_dataclass(value):
        return {key: _json_safe(item) for key, item in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        result = dict(value)
    elif dataclasses.is_dataclass(value):
        result = dataclasses.asdict(value)
    else:
        result = {}
        raw = getattr(value, "__dict__", None)
        if isinstance(raw, dict):
            result.update({key: item for key, item in raw.items() if not key.startswith("_")})
        for name in (
            "id",
            "modelId",
            "repo_id",
            "repoId",
            "slug",
            "name",
            "owner",
            "author",
            "sha",
            "sdk",
            "private",
            "lastModified",
            "last_modified",
            "size",
            "num_files",
            "file_count",
            "bucket_id",
        ):
            if name not in result and hasattr(value, name):
                result[name] = getattr(value, name)
    result = _json_safe(result)
    if not isinstance(result, dict):
        raise TypeError(f"cannot normalize Hub object: {type(value).__name__}")
    if not result.get("id"):
        result["id"] = (
            result.get("repo_id")
            or result.get("repoId")
            or result.get("slug")
            or result.get("bucket_id")
            or result.get("name")
        )
    if not result.get("lastModified") and result.get("last_modified"):
        result["lastModified"] = result["last_modified"]
    return result


def _identifier(item: dict[str, Any]) -> str:
    return str(
        item.get("id")
        or item.get("modelId")
        or item.get("repo_id")
        or item.get("slug")
        or item.get("bucket_id")
        or item.get("name")
        or ""
    )


def _belongs_to_org(item: dict[str, Any]) -> bool:
    identifier = _identifier(item)
    owner = str(item.get("owner") or item.get("author") or "")
    return (
        identifier.upper() == ORG
        or identifier.upper().startswith(ORG + "/")
        or owner.upper() == ORG
    )


def _invoke_supported(api: Any, name: str, **preferred: Any) -> list[Any]:
    method = getattr(api, name, None)
    if not callable(method):
        raise RuntimeError(f"installed huggingface_hub lacks HfApi.{name}()")
    signature = inspect.signature(method)
    kwargs = {
        key: value
        for key, value in preferred.items()
        if key in signature.parameters and value is not None
    }
    return list(method(**kwargs))


class OfficialInventoryEstateUpgrade(BaseEstateUpgrade):
    """Active estate publisher with supported-client inventory discovery."""

    def _inventory_kind(self, kind: str, method: str, **kwargs: Any) -> list[dict[str, Any]]:
        items = [_mapping(item) for item in _invoke_supported(self.api, method, **kwargs)]
        scoped = [item for item in items if _belongs_to_org(item)]
        self.inventory[kind] = scoped
        self.record(ORG, f"inventory:{kind}", "ok", f"count={len(scoped)}; api=HfApi.{method}")
        return scoped

    def _bucket_details(self, buckets: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        info_method = getattr(self.api, "bucket_info", None)
        if not callable(info_method):
            return list(buckets)
        signature = inspect.signature(info_method)
        output: list[dict[str, Any]] = []
        for summary in buckets:
            identity = _identifier(summary)
            if not identity:
                output.append(summary)
                continue
            try:
                if "bucket_id" in signature.parameters:
                    detail = info_method(bucket_id=identity)
                elif "bucket" in signature.parameters:
                    detail = info_method(bucket=identity)
                else:
                    detail = info_method(identity)
                merged = dict(summary)
                merged.update(_mapping(detail))
                output.append(merged)
            except Exception as exc:  # retain the supported list result, fail honestly in detail
                item = dict(summary)
                item["detail_error"] = f"{type(exc).__name__}: {exc}"[:300]
                output.append(item)
        return output

    def collect_inventory(self) -> dict[str, list[dict[str, Any]]]:
        self.inventory = {}
        self._inventory_kind("models", "list_models", author=ORG, full=True, limit=None)
        self._inventory_kind("datasets", "list_datasets", author=ORG, full=True, limit=None)
        self._inventory_kind("spaces", "list_spaces", author=ORG, full=True, limit=None)
        self._inventory_kind("kernels", "list_kernels", author=ORG, owner=ORG, limit=None)
        self._inventory_kind("collections", "list_collections", owner=ORG, namespace=ORG, limit=1000)

        buckets = [_mapping(item) for item in _invoke_supported(
            self.api,
            "list_buckets",
            owner=ORG,
            namespace=ORG,
            limit=1000,
        )]
        buckets = [item for item in buckets if _belongs_to_org(item)]
        buckets = self._bucket_details(buckets)
        self.inventory["buckets"] = buckets
        self.record(
            ORG,
            "inventory:buckets",
            "ok",
            f"count={len(buckets)}; api=HfApi.list_buckets",
        )
        return self.inventory

    def report(self) -> dict[str, Any]:
        report = super().report()
        report["inventory_api"] = {
            "models": "HfApi.list_models",
            "datasets": "HfApi.list_datasets",
            "spaces": "HfApi.list_spaces",
            "kernels": "HfApi.list_kernels",
            "collections": "HfApi.list_collections",
            "buckets": "HfApi.list_buckets + HfApi.bucket_info",
        }
        report["collection_reference_count"] = sum(
            len(item.get("items") or [])
            for item in self.inventory.get("collections", [])
            if isinstance(item, dict)
        )
        report["bucket_observations"] = [
            {
                "id": _identifier(item),
                "private": item.get("private"),
                "size": item.get("size"),
                "num_files": item.get("num_files") or item.get("file_count"),
                "detail_error": item.get("detail_error"),
            }
            for item in self.inventory.get("buckets", [])
        ]
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument(
        "--generation",
        default=os.environ.get("GITHUB_SHA") or f"manual-{int(time.time())}",
    )
    args = parser.parse_args()
    token = (
        os.environ.get("HF_ORG_TOKEN")
        or os.environ.get("HF_ORG_TOKEN1")
        or os.environ.get("HF_TOKEN")
    )
    if not token:
        print("FATAL: HF_ORG_TOKEN/HF_ORG_TOKEN1/HF_TOKEN is not set.", file=sys.stderr)
        return 2
    try:
        report = OfficialInventoryEstateUpgrade(
            token=token,
            generation=args.generation,
            publish=args.publish,
        ).run()
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    summary = report.get("summary") or {}
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if int(summary.get("error") or 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
