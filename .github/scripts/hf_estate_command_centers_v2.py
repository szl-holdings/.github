#!/usr/bin/env python3
"""Hugging Face estate command-center reconciler using supported Hub APIs.

This second-generation entrypoint retains the canonical A11oy production Space
and four public CPU-basic recovery/showcase command centers while closing the
legacy inventory blind spots:

* models, datasets, Spaces, and collections use ``HfApi`` list methods;
* buckets use ``HfApi.list_buckets`` and ``HfApi.bucket_info``;
* kernel inventory uses ``HfApi.list_kernels`` when available and a bounded Hub
  API fallback otherwise;
* every item in every managed collection is read back by its native Hub API;
* every organization bucket is read back with metadata and a bounded tree probe.

Free CPU Basic Spaces use Hugging Face's platform-managed sleep policy. This
entrypoint never submits a custom sleep time for CPU Basic. All deletion,
visibility, clone synchronization, model/dataset marker, collection, kernel,
and evidence-report boundaries from
``hf_estate_canonicalize.CommandCenterEstateUpgrade`` remain in force.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from itertools import islice
from typing import Any, Iterable

import hf_estate_canonicalize as command_centers

legacy = command_centers.legacy

_REPO_ITEM_TYPES = {"model", "dataset", "space"}
_ITEM_TYPE_ALIASES = {
    "models": "model",
    "datasets": "dataset",
    "spaces": "space",
    "buckets": "bucket",
    "collections": "collection",
    "papers": "paper",
}


def _json_scalar(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _record_from_object(value: Any) -> dict[str, Any]:
    """Convert Hub dataclasses into a small stable inventory record."""
    if isinstance(value, dict):
        return {str(key): _json_scalar(item) for key, item in value.items()}
    record: dict[str, Any] = {}
    for field in (
        "id",
        "slug",
        "title",
        "name",
        "author",
        "private",
        "sha",
        "sdk",
        "gated",
        "disabled",
        "downloads",
        "likes",
        "size",
        "total_files",
        "created_at",
        "last_modified",
    ):
        item = getattr(value, field, None)
        if item is not None:
            record[field] = _json_scalar(item)
    identifier = record.get("id") or record.get("slug") or record.get("name")
    if identifier is not None:
        record["id"] = str(identifier)
    return record


def _records(values: Iterable[Any]) -> list[dict[str, Any]]:
    return [_record_from_object(value) for value in values]


def _normalize_item_type(value: Any) -> str:
    item_type = str(value or "").strip().lower()
    return _ITEM_TYPE_ALIASES.get(item_type, item_type)


class CommandCenterEstateUpgradeV2(command_centers.CommandCenterEstateUpgrade):
    """Full estate maintenance with official Collections and Buckets APIs."""

    def _inventory_call(
        self,
        kind: str,
        method_name: str,
        *,
        fallback_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        try:
            method = getattr(self.api, method_name, None)
            if callable(method):
                values = method(**kwargs)
                source = f"HfApi.{method_name}"
                self.inventory[kind] = _records(values)
            elif fallback_url:
                source = "Hub REST fallback"
                self.inventory[kind] = self._paginate(fallback_url)
            else:
                raise RuntimeError(f"HfApi.{method_name} is unavailable")
            self.record(
                legacy.ORG,
                f"inventory:{kind}",
                "ok",
                f"count={len(self.inventory[kind])}; source={source}",
            )
        except Exception as exc:  # noqa: BLE001
            self.inventory[kind] = []
            self.record(legacy.ORG, f"inventory:{kind}", "error", repr(exc)[:300])

    def collect_inventory(self) -> dict[str, list[dict[str, Any]]]:
        self._inventory_call(
            "models",
            "list_models",
            author=legacy.ORG,
            full=True,
            limit=None,
        )
        self._inventory_call(
            "datasets",
            "list_datasets",
            author=legacy.ORG,
            full=True,
            limit=None,
        )
        self._inventory_call(
            "spaces",
            "list_spaces",
            author=legacy.ORG,
            full=True,
            limit=None,
        )
        self._inventory_call(
            "kernels",
            "list_kernels",
            fallback_url=f"{legacy.HF_BASE}/api/kernels?author={legacy.ORG}&limit=1000",
            author=legacy.ORG,
            limit=None,
        )
        self._inventory_call(
            "collections",
            "list_collections",
            owner=legacy.ORG,
            limit=1000,
        )
        self._inventory_call(
            "buckets",
            "list_buckets",
            namespace=legacy.ORG,
        )
        return self.inventory

    def _create_missing_clone(self, clone_id: str) -> None:
        if not self.publish:
            self.record(
                clone_id,
                "flagship-clone",
                "dry-run",
                "would create public CPU Basic Space with platform-managed sleep",
            )
            return
        self.api.create_repo(
            repo_id=clone_id,
            repo_type="space",
            private=False,
            exist_ok=True,
            space_sdk="docker",
            space_hardware="cpu-basic",
        )
        if not self.api.repo_exists(clone_id, repo_type="space"):
            raise RuntimeError(f"Clone creation did not produce repository: {clone_id}")
        self.record(
            clone_id,
            "flagship-clone",
            "created",
            "public CPU Basic; platform-managed free-hardware sleep policy",
        )

    def _collection_item_resolves(self, item_type: str, item_id: str) -> None:
        if item_type in _REPO_ITEM_TYPES:
            if not self.api.repo_exists(item_id, repo_type=item_type):
                raise RuntimeError(f"{item_type} repository does not resolve")
            return
        if item_type == "bucket":
            self.api.bucket_info(item_id)
            return
        if item_type == "collection":
            self.api.get_collection(item_id)
            return
        if item_type == "paper":
            self.api.paper_info(item_id)
            return
        raise RuntimeError(f"unsupported collection item type {item_type!r}")

    def validate_collections(self) -> None:
        """Read back every collection and verify every item by its native Hub API."""
        self.collection_validation: dict[str, dict[str, Any]] = {}
        for summary in self.inventory.get("collections", []):
            slug = str(summary.get("slug") or summary.get("id") or "")
            title = str(summary.get("title") or slug)
            if not slug:
                self.record(
                    legacy.ORG,
                    "collection-resolution",
                    "error",
                    "collection inventory record has no slug",
                )
                continue
            unresolved: list[str] = []
            resolved = 0
            try:
                collection = self.api.get_collection(slug)
                items = list(collection.items)
                for item in items:
                    item_type = _normalize_item_type(item.item_type)
                    item_id = str(item.item_id)
                    try:
                        self._collection_item_resolves(item_type, item_id)
                        resolved += 1
                    except Exception as exc:  # noqa: BLE001
                        unresolved.append(
                            f"{item_type}:{item_id}:{type(exc).__name__}:{exc}"
                        )
                snapshot = {
                    "title": title,
                    "total_items": len(items),
                    "resolved_items": resolved,
                    "unresolved_items": unresolved,
                    "private": getattr(collection, "private", None),
                    "theme": getattr(collection, "theme", None),
                }
                self.collection_validation[slug] = snapshot
                if unresolved:
                    self.record(
                        slug,
                        "collection-resolution",
                        "error",
                        f"title={title}; unresolved={unresolved[:20]}",
                    )
                else:
                    self.record(
                        slug,
                        "collection-resolution",
                        "validated",
                        f"title={title}; resolving_items={resolved}",
                    )
            except Exception as exc:  # noqa: BLE001
                self.collection_validation[slug] = {
                    "title": title,
                    "unresolved_items": [f"{type(exc).__name__}:{exc}"],
                }
                self.record(slug, "collection-resolution", "error", repr(exc)[:300])

    def validate_buckets(self) -> None:
        """Read back metadata and a bounded tree sample for every organization bucket."""
        self.bucket_snapshots: dict[str, dict[str, Any]] = {}
        for item in self.inventory.get("buckets", []):
            bucket_id = str(item.get("id") or item.get("name") or "")
            if not bucket_id:
                self.record(legacy.ORG, "bucket-contract", "error", "bucket without id")
                continue
            try:
                info = self.api.bucket_info(bucket_id)
                size = getattr(info, "size", None)
                total_files = getattr(info, "total_files", None)
                private = getattr(info, "private", None)
                if not isinstance(private, bool):
                    raise RuntimeError(f"bucket private flag is not boolean: {private!r}")
                if not isinstance(size, int) or size < 0:
                    raise RuntimeError(f"bucket size is invalid: {size!r}")
                if not isinstance(total_files, int) or total_files < 0:
                    raise RuntimeError(
                        f"bucket total_files is invalid: {total_files!r}"
                    )
                sample = list(
                    islice(
                        self.api.list_bucket_tree(bucket_id, recursive=True),
                        5,
                    )
                )
                snapshot = {
                    "private": private,
                    "size": size,
                    "total_files": total_files,
                    "sample_entries": len(sample),
                }
                self.bucket_snapshots[bucket_id] = snapshot
                self.record(
                    bucket_id,
                    "bucket-contract",
                    "validated",
                    (
                        f"private={private}; size={size}; total_files={total_files}; "
                        f"sample_entries={len(sample)}"
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                self.bucket_snapshots[bucket_id] = {
                    "error": f"{type(exc).__name__}: {exc}"
                }
                self.record(bucket_id, "bucket-contract", "error", repr(exc)[:300])

    def report(self) -> dict[str, Any]:
        report = super().report()
        report["schema"] = "szl.hf-estate-upgrade-report/v2"
        report["inventory_contract"] = "huggingface_hub-supported-api/v2"
        report["collection_validation"] = getattr(
            self, "collection_validation", {}
        )
        report["bucket_snapshots"] = getattr(self, "bucket_snapshots", {})
        report["boundaries"] = [
            *report.get("boundaries", []),
            (
                "Collections and buckets are inventoried and read back through "
                "supported huggingface_hub APIs."
            ),
            (
                "Every collection item is resolved by its native model, dataset, "
                "Space, bucket, collection, or paper API."
            ),
        ]
        return report

    def run(self) -> dict[str, Any]:
        self.authenticate()
        self.collect_inventory()
        self.upgrade_models_and_datasets()
        self.upgrade_spaces()
        self.create_or_refresh_clones()
        self.upgrade_collections()
        self.validate_collections()
        self.validate_kernels()
        self.validate_buckets()
        report = self.report()
        self.publish_report(report)
        report = self.report()
        with open("reports/hf-estate-upgrade-latest.json", "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
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
        os.environ.get("HF_ORG_TOKEN1")
        or os.environ.get("HF_ORG_TOKEN")
        or os.environ.get("HF_TOKEN")
    )
    if not token:
        print(
            "FATAL: HF_ORG_TOKEN1/HF_ORG_TOKEN/HF_TOKEN is not set.",
            file=sys.stderr,
        )
        return 2

    try:
        report = CommandCenterEstateUpgradeV2(
            token=token,
            generation=args.generation,
            publish=args.publish,
        ).run()
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {exc!r}", file=sys.stderr)
        return 2

    summary = report["summary"]
    print(json.dumps(summary, indent=2))
    return 1 if summary["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
