#!/usr/bin/env python3
"""Hugging Face estate command-center reconciler using supported Hub APIs.

This second-generation entrypoint retains the canonical A11oy production Space
and four public CPU-basic recovery/showcase command centers while removing the
two known inventory blind spots in the legacy publisher:

* Collections are listed with ``HfApi.list_collections`` rather than an invalid
  raw ``/api/collections?namespace=...`` request.
* Buckets are listed and validated with ``HfApi.list_buckets`` and
  ``HfApi.bucket_info`` rather than the obsolete raw ``/api/buckets`` path.

Free CPU Basic Spaces use Hugging Face's platform-managed sleep policy; this
entrypoint never submits a custom sleep time for CPU Basic. All existing safety
boundaries from ``hf_estate_canonicalize.CommandCenterEstateUpgrade`` remain in
force.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Iterable

import hf_estate_canonicalize as command_centers

legacy = command_centers.legacy


def _record_from_object(value: Any) -> dict[str, Any]:
    """Convert Hub dataclasses into a small stable inventory record."""
    if isinstance(value, dict):
        return dict(value)
    record: dict[str, Any] = {}
    for field in (
        "id",
        "slug",
        "title",
        "name",
        "private",
        "sha",
        "size",
        "total_files",
        "created_at",
        "last_modified",
    ):
        item = getattr(value, field, None)
        if item is not None:
            record[field] = item.isoformat() if hasattr(item, "isoformat") else item
    identifier = record.get("id") or record.get("slug") or record.get("name")
    if identifier is not None:
        record["id"] = str(identifier)
    return record


def _records(values: Iterable[Any]) -> list[dict[str, Any]]:
    return [_record_from_object(value) for value in values]


class CommandCenterEstateUpgradeV2(command_centers.CommandCenterEstateUpgrade):
    """Full estate maintenance with official Collections and Buckets APIs."""

    def collect_inventory(self) -> dict[str, list[dict[str, Any]]]:
        endpoints = {
            "models": f"{legacy.HF_BASE}/api/models?author={legacy.ORG}&limit=1000&full=true",
            "datasets": f"{legacy.HF_BASE}/api/datasets?author={legacy.ORG}&limit=1000&full=true",
            "spaces": f"{legacy.HF_BASE}/api/spaces?author={legacy.ORG}&limit=1000&full=true",
            "kernels": f"{legacy.HF_BASE}/api/kernels?author={legacy.ORG}&limit=1000",
        }
        for kind, endpoint in endpoints.items():
            try:
                self.inventory[kind] = self._paginate(endpoint)
                self.record(
                    legacy.ORG,
                    f"inventory:{kind}",
                    "ok",
                    f"count={len(self.inventory[kind])}",
                )
            except Exception as exc:  # noqa: BLE001
                self.inventory[kind] = []
                self.record(legacy.ORG, f"inventory:{kind}", "error", repr(exc)[:300])

        try:
            self.inventory["collections"] = _records(
                self.api.list_collections(owner=legacy.ORG, limit=1000)
            )
            self.record(
                legacy.ORG,
                "inventory:collections",
                "ok",
                f"count={len(self.inventory['collections'])}",
            )
        except Exception as exc:  # noqa: BLE001
            self.inventory["collections"] = []
            self.record(legacy.ORG, "inventory:collections", "error", repr(exc)[:300])

        try:
            self.inventory["buckets"] = _records(
                self.api.list_buckets(namespace=legacy.ORG)
            )
            self.record(
                legacy.ORG,
                "inventory:buckets",
                "ok",
                f"count={len(self.inventory['buckets'])}",
            )
        except Exception as exc:  # noqa: BLE001
            self.inventory["buckets"] = []
            self.record(legacy.ORG, "inventory:buckets", "error", repr(exc)[:300])
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

    def validate_collections(self) -> None:
        """Read back every managed collection and verify all repository items resolve."""
        for title, slug in self.collections.items():
            try:
                collection = self.api.get_collection(slug)
                unresolved: list[str] = []
                checked = 0
                for item in collection.items:
                    item_type = str(item.item_type)
                    item_id = str(item.item_id)
                    if item_type not in {"model", "dataset", "space"}:
                        continue
                    checked += 1
                    try:
                        exists = self.api.repo_exists(item_id, repo_type=item_type)
                    except Exception:  # noqa: BLE001
                        exists = False
                    if not exists:
                        unresolved.append(f"{item_type}:{item_id}")
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
                        f"title={title}; resolving_items={checked}",
                    )
            except Exception as exc:  # noqa: BLE001
                self.record(slug, "collection-resolution", "error", repr(exc)[:300])

    def validate_buckets(self) -> None:
        """Read back visibility, size, and file count for every organization bucket."""
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
                self.record(
                    bucket_id,
                    "bucket-contract",
                    "validated",
                    f"private={private}; size={size}; total_files={total_files}",
                )
            except Exception as exc:  # noqa: BLE001
                self.record(bucket_id, "bucket-contract", "error", repr(exc)[:300])

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
        os.environ.get("HF_ORG_TOKEN")
        or os.environ.get("HF_ORG_TOKEN1")
        or os.environ.get("HF_TOKEN")
    )
    if not token:
        print(
            "FATAL: HF_ORG_TOKEN/HF_ORG_TOKEN1/HF_TOKEN is not set.",
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
