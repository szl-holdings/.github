#!/usr/bin/env python3
"""Inventory the SZLHOLDINGS Hugging Face estate through supported HfApi calls.

This verifier is deliberately separate from the retired clone publisher. It is
read-only for models, datasets, Spaces, kernels, collections, and buckets. Its
only write is an immutable JSON evidence report in the private szl-evidence
dataset when publish mode is enabled.
"""
from __future__ import annotations

import argparse
import dataclasses
import inspect
import io
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from huggingface_hub import HfApi

ORG = "SZLHOLDINGS"
CANONICAL_SPACE = f"{ORG}/a11oy"
EVIDENCE_DATASET = f"{ORG}/szl-evidence"
HISTORICAL_CLONE_IDS = tuple(f"{ORG}/a11oy-clone-{index}" for index in range(1, 5))
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SUPPORTED_COLLECTION_REPO_TYPES = {
    "model": None,
    "dataset": "dataset",
    "space": "space",
}


@dataclass(frozen=True)
class Action:
    target: str
    action: str
    status: str
    detail: str = ""


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
            "title",
            "name",
            "owner",
            "author",
            "sha",
            "sdk",
            "private",
            "lastModified",
            "last_modified",
            "downloads",
            "likes",
            "size",
            "num_files",
            "file_count",
            "bucket_id",
            "item_id",
            "item_type",
            "item_object_id",
            "position",
            "note",
        ):
            if name not in result and hasattr(value, name):
                result[name] = getattr(value, name)
    normalized = _json_safe(result)
    if not isinstance(normalized, dict):
        raise TypeError(f"cannot normalize Hub object: {type(value).__name__}")
    if not normalized.get("id"):
        normalized["id"] = (
            normalized.get("repo_id")
            or normalized.get("repoId")
            or normalized.get("slug")
            or normalized.get("bucket_id")
            or normalized.get("item_id")
            or normalized.get("name")
        )
    if not normalized.get("lastModified") and normalized.get("last_modified"):
        normalized["lastModified"] = normalized["last_modified"]
    return normalized


def _identifier(item: dict[str, Any]) -> str:
    return str(
        item.get("id")
        or item.get("modelId")
        or item.get("repo_id")
        or item.get("repoId")
        or item.get("slug")
        or item.get("bucket_id")
        or item.get("item_id")
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


def _stage(info: Any) -> str:
    runtime = getattr(info, "runtime", None)
    raw = getattr(runtime, "stage", None)
    raw = getattr(raw, "value", raw)
    return str(raw or "UNKNOWN").split(".")[-1].upper()


class OfficialEstateInventory:
    def __init__(self, *, token: str, generation: str, publish: bool) -> None:
        self.token = token
        self.generation = generation
        self.publish = publish
        self.api = HfApi(token=token)
        self.actions: list[Action] = []
        self.inventory: dict[str, Any] = {}
        self.collection_reference_count = 0
        self.collection_resolution_errors: list[str] = []
        self.clone_collection_references: list[str] = []

    def record(self, target: str, action: str, status: str, detail: str = "") -> None:
        self.actions.append(Action(target, action, status, detail))
        print(f"[{status:>10}] {action}: {target}" + (f" — {detail}" if detail else ""))

    def authenticate(self) -> None:
        who = self.api.whoami()
        match = next(
            (
                item
                for item in (who.get("orgs") or [])
                if str(item.get("name") or item.get("fullname") or "").upper() == ORG
            ),
            None,
        )
        if match is None:
            raise RuntimeError(f"authenticated identity is not a member of {ORG}")
        role = str(match.get("roleInOrg") or match.get("role") or "").lower()
        if role and role not in {"admin", "write", "contributor"}:
            raise RuntimeError(f"authenticated role is not write-capable: {role}")
        self.record(ORG, "authenticate", "validated", f"role={role or 'unknown'}")

    def _inventory_kind(self, kind: str, method: str, **kwargs: Any) -> None:
        values = [_mapping(item) for item in _invoke_supported(self.api, method, **kwargs)]
        scoped = [item for item in values if _belongs_to_org(item)]
        scoped.sort(key=_identifier)
        self.inventory[kind] = scoped
        self.record(
            ORG,
            f"inventory:{kind}",
            "validated",
            f"count={len(scoped)}; api=HfApi.{method}",
        )

    def inventory_repositories(self) -> None:
        self._inventory_kind("models", "list_models", author=ORG, full=True, limit=None)
        self._inventory_kind("datasets", "list_datasets", author=ORG, full=True, limit=None)
        self._inventory_kind("spaces", "list_spaces", author=ORG, full=True, limit=None)
        self._inventory_kind("kernels", "list_kernels", author=ORG, owner=ORG, limit=None)

    def verify_canonical_and_clones(self) -> None:
        info = self.api.space_info(CANONICAL_SPACE)
        revision = str(getattr(info, "sha", "") or "")
        sdk = str(getattr(info, "sdk", "") or "").lower()
        private = getattr(info, "private", None)
        stage = _stage(info)
        files = set(self.api.list_repo_files(CANONICAL_SPACE, repo_type="space"))
        if not SHA40.fullmatch(revision):
            raise RuntimeError(f"canonical A11oy lacks an immutable revision: {revision!r}")
        if sdk != "docker" or private is not False or stage != "RUNNING":
            raise RuntimeError(
                f"canonical A11oy is not public Docker RUNNING: sdk={sdk}; "
                f"private={private}; stage={stage}"
            )
        if "Dockerfile" not in files:
            raise RuntimeError("canonical A11oy is missing Dockerfile")
        self.inventory["canonical_a11oy"] = {
            "repo_id": CANONICAL_SPACE,
            "sha": revision,
            "sdk": sdk,
            "private": private,
            "stage": stage,
            "file_count": len(files),
        }
        self.record(
            CANONICAL_SPACE,
            "canonical-a11oy",
            "validated",
            f"sha={revision}; stage={stage}; files={len(files)}",
        )

        clone_absence = {}
        for clone_id in HISTORICAL_CLONE_IDS:
            exists = bool(self.api.repo_exists(clone_id, repo_type="space"))
            clone_absence[clone_id] = not exists
            if exists:
                raise RuntimeError(f"historical A11oy clone reappeared: {clone_id}")
            self.record(clone_id, "clone-absence", "validated", "absent")
        self.inventory["clone_absence"] = clone_absence

    def _resolve_collection_item(self, collection_slug: str, item: dict[str, Any]) -> dict[str, Any]:
        item_id = str(item.get("item_id") or item.get("id") or "")
        item_type = str(item.get("item_type") or "").lower()
        result = {
            "item_id": item_id,
            "item_type": item_type,
            "item_object_id": item.get("item_object_id"),
            "position": item.get("position"),
            "note": item.get("note"),
            "resolution": "NOT_APPLICABLE",
        }
        if not item_id or not item_type:
            result["resolution"] = "MALFORMED"
            self.collection_resolution_errors.append(
                f"{collection_slug}: malformed collection item {item!r}"
            )
            return result

        if item_id in HISTORICAL_CLONE_IDS:
            self.clone_collection_references.append(f"{collection_slug}:{item_id}")

        if item_type in SUPPORTED_COLLECTION_REPO_TYPES:
            repo_type = SUPPORTED_COLLECTION_REPO_TYPES[item_type]
            try:
                exists = bool(self.api.repo_exists(item_id, repo_type=repo_type))
            except Exception as exc:  # noqa: BLE001
                exists = False
                result["resolution_error"] = f"{type(exc).__name__}: {exc}"[:300]
            result["resolution"] = "RESOLVED" if exists else "MISSING"
            if not exists:
                self.collection_resolution_errors.append(
                    f"{collection_slug}: missing {item_type} {item_id}"
                )
        return result

    def inventory_collections(self) -> None:
        summaries = [_mapping(item) for item in _invoke_supported(
            self.api,
            "list_collections",
            owner=ORG,
            namespace=ORG,
            limit=99,
        )]
        summaries = [item for item in summaries if _belongs_to_org(item)]
        output = []
        for summary in sorted(summaries, key=_identifier):
            slug = str(summary.get("slug") or summary.get("id") or "")
            if not slug:
                raise RuntimeError(f"collection summary lacks slug: {summary}")
            collection = self.api.get_collection(slug)
            raw_items: Iterable[Any] = getattr(collection, "items", None) or []
            items = [self._resolve_collection_item(slug, _mapping(item)) for item in raw_items]
            self.collection_reference_count += len(items)
            output.append(
                {
                    "slug": slug,
                    "title": getattr(collection, "title", None) or summary.get("title"),
                    "private": getattr(collection, "private", None),
                    "item_count": len(items),
                    "items": items,
                }
            )
        if self.clone_collection_references:
            raise RuntimeError(
                f"historical clone collection references remain: {self.clone_collection_references}"
            )
        if self.collection_resolution_errors:
            raise RuntimeError(
                "collection reference verification failed: "
                + "; ".join(self.collection_resolution_errors[:20])
            )
        self.inventory["collections"] = output
        self.record(
            ORG,
            "inventory:collections",
            "validated",
            f"count={len(output)}; references={self.collection_reference_count}; "
            "api=HfApi.list_collections+get_collection",
        )

    def _bucket_detail(self, summary: dict[str, Any]) -> dict[str, Any]:
        identity = _identifier(summary)
        if not identity:
            raise RuntimeError(f"bucket summary lacks identity: {summary}")
        method = getattr(self.api, "bucket_info", None)
        if not callable(method):
            raise RuntimeError("installed huggingface_hub lacks HfApi.bucket_info()")
        signature = inspect.signature(method)
        if "bucket_id" in signature.parameters:
            detail = method(bucket_id=identity)
        elif "bucket" in signature.parameters:
            detail = method(bucket=identity)
        else:
            detail = method(identity)
        merged = dict(summary)
        merged.update(_mapping(detail))
        merged["id"] = _identifier(merged) or identity
        return merged

    def inventory_buckets(self) -> None:
        summaries = [_mapping(item) for item in _invoke_supported(
            self.api,
            "list_buckets",
            owner=ORG,
            namespace=ORG,
            limit=1000,
        )]
        summaries = [item for item in summaries if _belongs_to_org(item)]
        details = [self._bucket_detail(item) for item in summaries]
        details.sort(key=_identifier)
        self.inventory["buckets"] = details
        self.record(
            ORG,
            "inventory:buckets",
            "validated",
            f"count={len(details)}; api=HfApi.list_buckets+bucket_info",
        )

    @staticmethod
    def _public_asset_view(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": _identifier(item),
            "sha": item.get("sha"),
            "private": item.get("private"),
            "sdk": item.get("sdk"),
            "downloads": item.get("downloads"),
            "likes": item.get("likes"),
            "last_modified": item.get("lastModified"),
        }

    def report(self) -> dict[str, Any]:
        statuses = [item.status for item in self.actions]
        repository_kinds = ("models", "datasets", "spaces", "kernels")
        assets = {
            kind: [self._public_asset_view(item) for item in self.inventory.get(kind, [])]
            for kind in repository_kinds
        }
        return {
            "schema": "szl.hf-official-estate-inventory/v1",
            "organization": ORG,
            "generation": self.generation,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "publish": self.publish,
            "inventory_api": {
                "models": "HfApi.list_models",
                "datasets": "HfApi.list_datasets",
                "spaces": "HfApi.list_spaces",
                "kernels": "HfApi.list_kernels",
                "collections": "HfApi.list_collections + HfApi.get_collection",
                "buckets": "HfApi.list_buckets + HfApi.bucket_info",
            },
            "counts": {
                "models": len(self.inventory.get("models", [])),
                "datasets": len(self.inventory.get("datasets", [])),
                "spaces": len(self.inventory.get("spaces", [])),
                "kernels": len(self.inventory.get("kernels", [])),
                "collections": len(self.inventory.get("collections", [])),
                "collection_references": self.collection_reference_count,
                "buckets": len(self.inventory.get("buckets", [])),
            },
            "canonical_a11oy": self.inventory.get("canonical_a11oy"),
            "clone_absence": self.inventory.get("clone_absence", {}),
            "assets": assets,
            "collections": self.inventory.get("collections", []),
            "buckets": self.inventory.get("buckets", []),
            "actions": [asdict(item) for item in self.actions],
            "summary": {
                "ok": sum(status in {"validated", "updated", "ok"} for status in statuses),
                "warning": sum(status == "warning" for status in statuses),
                "error": sum(status == "error" for status in statuses),
                "dry_run": sum(status == "dry-run" for status in statuses),
            },
            "boundaries": [
                "The verifier performs no model, dataset, Space, kernel, collection, bucket, visibility, or hardware mutation.",
                "Its only publish-mode write is an immutable JSON report in the private szl-evidence dataset.",
                "SZLHOLDINGS/a11oy remains the sole permanent A11oy Space and protected GitHub main remains source authority.",
                "Every supported collection repository reference must resolve and every historical clone reference must remain absent.",
                "Bucket discovery and readback use supported huggingface_hub APIs rather than raw private endpoints.",
            ],
        }

    def persist(self, report: dict[str, Any]) -> None:
        rendered = (json.dumps(report, indent=2, sort_keys=True, default=str) + "\n").encode()
        output = Path("reports/hf-official-estate-inventory-latest.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(rendered)
        self.record(str(output), "local-report", "updated")
        if not self.publish:
            return
        if not self.api.repo_exists(EVIDENCE_DATASET, repo_type="dataset"):
            raise RuntimeError(f"evidence dataset is missing: {EVIDENCE_DATASET}")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for destination in (
            "estate/official-inventory/latest.json",
            f"estate/official-inventory/history/{timestamp}.json",
        ):
            self.api.upload_file(
                repo_id=EVIDENCE_DATASET,
                repo_type="dataset",
                path_or_fileobj=io.BytesIO(rendered),
                path_in_repo=destination,
                commit_message=f"chore(estate): record official Hub inventory {timestamp}",
            )
        self.record(EVIDENCE_DATASET, "evidence-publish", "updated")

    def run(self) -> dict[str, Any]:
        self.authenticate()
        self.inventory_repositories()
        self.verify_canonical_and_clones()
        self.inventory_collections()
        self.inventory_buckets()
        report = self.report()
        self.persist(report)
        report = self.report()
        Path("reports/hf-official-estate-inventory-latest.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
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
        print("FATAL: no supported Hugging Face credential is configured", file=sys.stderr)
        return 2

    try:
        report = OfficialEstateInventory(
            token=token,
            generation=args.generation,
            publish=args.publish,
        ).run()
    except Exception as exc:  # noqa: BLE001
        Path("reports").mkdir(exist_ok=True)
        failure = {
            "schema": "szl.hf-official-estate-inventory/v1",
            "organization": ORG,
            "generation": args.generation,
            "publish": args.publish,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fatal": f"{type(exc).__name__}: {exc}",
            "summary": {"ok": 0, "warning": 0, "error": 1, "dry_run": 0},
        }
        Path("reports/hf-official-estate-inventory-latest.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 1 if report["summary"]["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
