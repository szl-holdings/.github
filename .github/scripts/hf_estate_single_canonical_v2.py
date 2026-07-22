#!/usr/bin/env python3
"""Converge every A11oy Hugging Face candidate into one canonical Space.

The only surviving A11oy Space is ``SZLHOLDINGS/a11oy``. The reconciler:

1. inventories the canonical Space and the four historical clone IDs through
   immutable Hub revisions and byte-level tree identities;
2. ranks genuinely authored content commits rather than management-marker or
   clone-refresh commits;
3. adopts only the newest divergent source tree into the canonical repository;
4. proves the canonical repository and runtime revision, public visibility,
   Docker SDK, byte parity, and important read-only routes;
5. removes clone references from every collection, deletes every clone, and
   proves both repository and collection absence;
6. runs organization-wide model, dataset, Space, kernel, collection, and bucket
   inventory/readback through supported ``huggingface_hub`` APIs.

No code path in this module creates, duplicates, publishes, refreshes, or changes
visibility of a clone. Git feature branches, pull requests, Replit previews, and
explicitly temporary environments are the development lanes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from itertools import islice
from typing import Any, Iterable

import hf_estate_canonicalize as single

legacy = single.legacy

EXCLUDED_TREE_PATHS = frozenset({".gitattributes", legacy.MANAGED_PATH})
MANAGEMENT_COMMIT_PREFIXES = (
    "chore(estate): record managed generation",
    "chore(clone):",
    "feat(estate): publish hub upgrade report",
    "chore(hf): record",
)
PUBLIC_BASE = "https://szlholdings-a11oy.hf.space"
SAFE_ROUTE_CHECKS = (
    ("/healthz", ("status",)),
    ("/api/a11oy/v1/operator/ask", ("status", "citations", "fetchedAt", "doctrine")),
    ("/api/a11oy/v1/readiness", ("sections", "summary", "honest")),
    ("/api/a11oy/v1/evidence", ("claims", "total_assertions", "status_counts")),
    ("/api/a11oy/v1/mcp/tools", ("count", "tools", "flagship")),
    ("/api/a11oy/v1/verify/receipt", ("schema",)),
)
REPO_ITEM_TYPES = frozenset({"model", "dataset", "space"})
ITEM_TYPE_ALIASES = {
    "models": "model",
    "datasets": "dataset",
    "spaces": "space",
    "buckets": "bucket",
    "collections": "collection",
    "papers": "paper",
}

# Permanent runtime kill switch for the inherited clone creator and collection
# additions. The active workflow imports this module before running any estate
# mutation, so CLONE_IDS cannot be repopulated by the legacy publisher.
legacy.CLONE_IDS = []


def _json_scalar(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _record_from_object(value: Any) -> dict[str, Any]:
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
    return ITEM_TYPE_ALIASES.get(item_type, item_type)


def _commit_epoch(value: Any) -> float:
    created = (
        getattr(value, "created_at", None)
        or getattr(value, "createdAt", None)
        or getattr(value, "date", None)
    )
    if created is None:
        return 0.0
    if hasattr(created, "timestamp"):
        return float(created.timestamp())
    return single._parse_modified(created)


def _commit_identifier(value: Any) -> str:
    return str(
        getattr(value, "commit_id", None)
        or getattr(value, "oid", None)
        or getattr(value, "id", None)
        or ""
    )


def _commit_text(value: Any) -> str:
    return "\n".join(
        str(item or "")
        for item in (
            getattr(value, "title", None),
            getattr(value, "message", None),
        )
    ).strip()


def _is_management_commit(value: Any) -> bool:
    text = _commit_text(value).lower()
    return any(text.startswith(prefix) for prefix in MANAGEMENT_COMMIT_PREFIXES)


def choose_newest_candidate(snapshots: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Select the newest valid divergent content tree, failing on ambiguity."""
    valid = [item for item in snapshots.values() if item.get("valid")]
    if not valid:
        raise RuntimeError("No valid canonical-or-clone A11oy Docker Space exists")

    canonical = next(
        (item for item in valid if item["repo_id"] == legacy.FLAGSHIP_SPACE),
        None,
    )
    digests = {str(item.get("tree_digest") or "") for item in valid}
    if len(digests) == 1 and canonical is not None:
        return canonical

    ordered = sorted(
        valid,
        key=lambda item: (
            float(item.get("content_modified_epoch") or 0.0),
            float(item.get("last_modified_epoch") or 0.0),
            item["repo_id"] == legacy.FLAGSHIP_SPACE,
            str(item.get("content_commit_sha") or ""),
            str(item.get("sha") or ""),
        ),
        reverse=True,
    )
    if len(ordered) > 1:
        first, second = ordered[0], ordered[1]
        first_clock = (
            float(first.get("content_modified_epoch") or 0.0),
            float(first.get("last_modified_epoch") or 0.0),
        )
        second_clock = (
            float(second.get("content_modified_epoch") or 0.0),
            float(second.get("last_modified_epoch") or 0.0),
        )
        if first_clock == second_clock and first.get("tree_digest") != second.get("tree_digest"):
            raise RuntimeError(
                "Equally recent A11oy candidates have divergent file trees; "
                f"manual source adjudication required: {first['repo_id']} vs {second['repo_id']}"
            )
    return ordered[0]


def evaluate_route_response(
    status_code: int,
    content_type: str,
    payload: Any,
    required: tuple[str, ...],
) -> tuple[bool, str]:
    if status_code != 200:
        return False, f"HTTP {status_code}, expected 200"
    if "application/json" not in str(content_type or "").lower():
        return False, f"non-JSON content type: {content_type!r}"
    if not isinstance(payload, dict):
        return False, "JSON payload is not an object"
    missing = [key for key in required if key not in payload]
    if missing:
        return False, f"missing keys: {', '.join(missing)}"
    return True, "ok"


class SingleCanonicalEstateUpgradeV2(single.SingleA11oyEstateUpgrade):
    """Single-A11oy consolidation with official API inventory and live proof."""

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
                self.inventory[kind] = _records(method(**kwargs))
                source = f"HfApi.{method_name}"
            elif fallback_url:
                self.inventory[kind] = self._paginate(fallback_url)
                source = "Hub REST compatibility fallback"
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
        self._inventory_call("models", "list_models", author=legacy.ORG, full=True, limit=None)
        self._inventory_call("datasets", "list_datasets", author=legacy.ORG, full=True, limit=None)
        self._inventory_call("spaces", "list_spaces", author=legacy.ORG, full=True, limit=None)
        self._inventory_call(
            "kernels",
            "list_kernels",
            fallback_url=f"{legacy.HF_BASE}/api/kernels?author={legacy.ORG}&limit=1000",
            author=legacy.ORG,
            limit=None,
        )
        self._inventory_call("collections", "list_collections", owner=legacy.ORG, limit=100)
        self._inventory_call("buckets", "list_buckets", namespace=legacy.ORG)
        return self.inventory

    def _tree_digest(self, repo_id: str) -> tuple[str, int]:
        mapping = {
            path: identity
            for path, identity in self._repo_file_map(repo_id).items()
            if path not in EXCLUDED_TREE_PATHS
        }
        digest = hashlib.sha256()
        for path, identity in sorted(mapping.items()):
            digest.update(path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(identity.encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest(), len(mapping)

    def _latest_content_commit(self, repo_id: str) -> dict[str, Any]:
        try:
            commits = self.api.list_repo_commits(
                repo_id=repo_id,
                repo_type="space",
                revision="main",
            )
            first_any: Any | None = None
            for commit in commits:
                if first_any is None:
                    first_any = commit
                if _is_management_commit(commit):
                    continue
                return {
                    "sha": _commit_identifier(commit),
                    "created_at": _json_scalar(
                        getattr(commit, "created_at", None)
                        or getattr(commit, "createdAt", None)
                    ),
                    "epoch": _commit_epoch(commit),
                    "title": str(getattr(commit, "title", None) or ""),
                    "management_only": False,
                }
            if first_any is not None:
                return {
                    "sha": _commit_identifier(first_any),
                    "created_at": _json_scalar(
                        getattr(first_any, "created_at", None)
                        or getattr(first_any, "createdAt", None)
                    ),
                    "epoch": _commit_epoch(first_any),
                    "title": str(getattr(first_any, "title", None) or ""),
                    "management_only": True,
                }
        except Exception as exc:  # noqa: BLE001
            self.record(repo_id, "content-commit-history", "warning", repr(exc)[:250])
        return {"sha": "", "created_at": None, "epoch": 0.0, "title": "", "management_only": False}

    def _candidate_snapshot(self, repo_id: str) -> dict[str, Any]:
        if not self.api.repo_exists(repo_id, repo_type="space"):
            snapshot = {"repo_id": repo_id, "exists": False, "valid": False}
            self.record(repo_id, "a11oy-candidate", "ok", "absent")
            return snapshot

        detail = self._space_detail(repo_id)
        sha = str(detail.get("sha") or "")
        modified = detail.get("lastModified") or detail.get("last_modified")
        runtime = detail.get("runtime") or {}
        sdk = str(detail.get("sdk") or "").lower()
        files = set(self.api.list_repo_files(repo_id, repo_type="space"))
        tree_digest, tree_files = self._tree_digest(repo_id)
        content_commit = self._latest_content_commit(repo_id)
        content_epoch = float(content_commit.get("epoch") or 0.0)
        last_modified_epoch = single._parse_modified(modified)
        if content_epoch <= 0:
            content_epoch = last_modified_epoch

        snapshot = {
            "repo_id": repo_id,
            "exists": True,
            "sha": sha,
            "runtime_sha": str(runtime.get("sha") or ""),
            "private": detail.get("private"),
            "sdk": sdk,
            "stage": single._detail_stage(detail),
            "last_modified": str(modified or ""),
            "last_modified_epoch": last_modified_epoch,
            "content_commit_sha": content_commit.get("sha"),
            "content_commit_created_at": content_commit.get("created_at"),
            "content_commit_title": content_commit.get("title"),
            "content_modified_epoch": content_epoch,
            "tree_digest": tree_digest,
            "tree_files": tree_files,
            "dockerfile_present": "Dockerfile" in files,
            "valid": bool(
                single.SHA_RE.fullmatch(sha)
                and "Dockerfile" in files
                and sdk == "docker"
            ),
        }
        self.record(
            repo_id,
            "a11oy-candidate",
            "validated" if snapshot["valid"] else "warning",
            (
                f"stage={snapshot['stage']}; sdk={sdk or 'UNKNOWN'}; "
                f"private={snapshot['private']}; sha={sha or 'UNKNOWN'}; "
                f"runtime_sha={snapshot['runtime_sha'] or 'UNKNOWN'}; "
                f"content_commit={snapshot['content_commit_sha'] or 'UNKNOWN'}; "
                f"tree={tree_digest[:16]}; files={tree_files}"
            ),
        )
        return snapshot

    def _select_newest_source(self) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        snapshots = {
            repo_id: self._candidate_snapshot(repo_id)
            for repo_id in single.CANDIDATE_IDS
        }
        selected = choose_newest_candidate(snapshots)
        self.record(
            selected["repo_id"],
            "select-newest-a11oy-source",
            "validated",
            (
                f"content_commit={selected.get('content_commit_sha') or 'UNKNOWN'}; "
                f"content_modified={selected.get('content_commit_created_at') or selected.get('last_modified') or 'UNKNOWN'}; "
                f"tree={str(selected.get('tree_digest') or '')[:16]}; "
                f"sha={selected.get('sha')}; stage={selected.get('stage')}"
            ),
        )
        return selected, snapshots

    @staticmethod
    def _runtime_sha(info: Any) -> str:
        runtime = getattr(info, "runtime", None)
        return str(getattr(runtime, "sha", None) or "")

    @staticmethod
    def _space_sdk(info: Any) -> str:
        value = getattr(info, "sdk", None)
        value = getattr(value, "value", value)
        return str(value or "").lower()

    def _wait_for_exact_canonical(
        self,
        *,
        expected_repo_sha: str,
        expected_runtime_sha: str,
        timeout_seconds: int = 1800,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last: dict[str, Any] = {}
        while True:
            info = self.api.space_info(legacy.FLAGSHIP_SPACE)
            repo_sha = str(getattr(info, "sha", None) or "")
            runtime_sha = self._runtime_sha(info)
            stage = single._runtime_stage(info)
            sdk = self._space_sdk(info)
            last = {
                "repo_id": legacy.FLAGSHIP_SPACE,
                "sha": repo_sha,
                "runtime_sha": runtime_sha,
                "stage": stage,
                "private": getattr(info, "private", None),
                "sdk": sdk,
            }
            if (
                repo_sha == expected_repo_sha
                and runtime_sha == expected_runtime_sha
                and stage == "RUNNING"
                and sdk == "docker"
                and last["private"] is False
            ):
                files = set(self.api.list_repo_files(legacy.FLAGSHIP_SPACE, repo_type="space"))
                if "Dockerfile" not in files:
                    raise RuntimeError("Canonical A11oy Space lost its Dockerfile")
                last["dockerfile_present"] = True
                self.record(
                    legacy.FLAGSHIP_SPACE,
                    "canonical-runtime",
                    "validated",
                    (
                        f"repo_sha={repo_sha}; runtime_sha={runtime_sha}; "
                        f"stage=RUNNING; sdk=docker; public=true"
                    ),
                )
                return last
            if stage in single.TERMINAL_FAILURE_STAGES:
                raise RuntimeError(f"Canonical A11oy entered terminal failure: {last}")
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Canonical A11oy did not converge to the exact repository/runtime "
                    f"revision within {timeout_seconds}s: expected_repo={expected_repo_sha}; "
                    f"expected_runtime={expected_runtime_sha}; last={last}"
                )
            time.sleep(15)

    def _verify_safe_routes(self, attempts: int = 5) -> dict[str, Any]:
        session = legacy.requests.Session()
        session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "szl-single-a11oy-post-deploy-proof/2.0",
            }
        )
        results: list[dict[str, Any]] = []
        for path, required in SAFE_ROUTE_CHECKS:
            last_reason = "not attempted"
            for attempt in range(1, attempts + 1):
                try:
                    response = session.get(
                        PUBLIC_BASE + path,
                        timeout=30,
                        headers={"Cache-Control": "no-cache"},
                    )
                    try:
                        payload = response.json()
                    except Exception:  # noqa: BLE001
                        payload = None
                    ok, reason = evaluate_route_response(
                        response.status_code,
                        response.headers.get("Content-Type", ""),
                        payload,
                        required,
                    )
                except Exception as exc:  # noqa: BLE001
                    ok, reason = False, f"{type(exc).__name__}: {exc}"
                if ok:
                    result = {
                        "method": "GET",
                        "path": path,
                        "status": "PASS",
                        "attempt": attempt,
                        "required_keys": list(required),
                    }
                    results.append(result)
                    self.record(
                        PUBLIC_BASE + path,
                        "canonical-route",
                        "validated",
                        f"attempt={attempt}; required={','.join(required)}",
                    )
                    break
                last_reason = reason
                if attempt < attempts:
                    time.sleep(10)
            else:
                results.append(
                    {
                        "method": "GET",
                        "path": path,
                        "status": "FAIL",
                        "reason": last_reason,
                        "required_keys": list(required),
                    }
                )
                self.record(
                    PUBLIC_BASE + path,
                    "canonical-route",
                    "error",
                    last_reason,
                )
        failures = [item for item in results if item["status"] != "PASS"]
        if failures:
            raise RuntimeError(f"Canonical A11oy route verification failed: {failures}")
        return {"base": PUBLIC_BASE, "checked": len(results), "results": results}

    def _verify_clone_absence_in_collections(self) -> None:
        clones = set(single.HISTORICAL_CLONE_IDS)
        remaining: list[str] = []
        for summary in self.api.list_collections(owner=legacy.ORG, limit=100):
            collection = self.api.get_collection(summary.slug)
            for item in collection.items:
                if _normalize_item_type(item.item_type) == "space" and str(item.item_id) in clones:
                    remaining.append(f"{collection.slug}:{item.item_id}")
        if remaining:
            raise RuntimeError(f"Clone collection references remain: {remaining}")
        self.record(
            legacy.ORG,
            "clone-collection-absence",
            "validated",
            "no collection references any historical A11oy clone",
        )

    def create_or_refresh_clones(self) -> None:
        """Adopt the newest verified content, prove canonical, then delete clones."""
        selected, snapshots = self._select_newest_source()
        self.candidate_snapshots = snapshots
        self.selected_newest_source = selected
        expected_sha, copied, deleted = self._sync_source_to_canonical(selected["repo_id"])
        expected_repo_sha = str(expected_sha or selected.get("sha") or "")
        expected_runtime_sha = (
            expected_repo_sha
            if copied or deleted
            else str(selected.get("runtime_sha") or expected_repo_sha)
        )
        if not single.SHA_RE.fullmatch(expected_repo_sha):
            raise RuntimeError(f"Expected canonical repository SHA is invalid: {expected_repo_sha!r}")
        if not single.SHA_RE.fullmatch(expected_runtime_sha):
            raise RuntimeError(f"Expected canonical runtime SHA is invalid: {expected_runtime_sha!r}")

        self.adoption_plan = {
            "source_repo_id": selected["repo_id"],
            "source_sha": selected.get("sha"),
            "source_content_commit_sha": selected.get("content_commit_sha"),
            "source_tree_digest": selected.get("tree_digest"),
            "copied_paths": copied,
            "deleted_paths": deleted,
            "expected_canonical_repo_sha": expected_repo_sha,
            "expected_canonical_runtime_sha": expected_runtime_sha,
        }

        if self.publish:
            self.canonical_flagship = self._wait_for_exact_canonical(
                expected_repo_sha=expected_repo_sha,
                expected_runtime_sha=expected_runtime_sha,
            )
            self._verify_adopted_file_set(selected["repo_id"])
            self.live_route_verification = self._verify_safe_routes()
        else:
            canonical = snapshots.get(legacy.FLAGSHIP_SPACE, {})
            self.canonical_flagship = {
                "repo_id": legacy.FLAGSHIP_SPACE,
                "sha": canonical.get("sha"),
                "runtime_sha": canonical.get("runtime_sha"),
                "stage": canonical.get("stage"),
                "private": canonical.get("private"),
                "sdk": canonical.get("sdk"),
                "dockerfile_present": canonical.get("dockerfile_present"),
                "planned_source_repo_id": selected["repo_id"],
                "planned_repo_sha": expected_repo_sha,
                "planned_runtime_sha": expected_runtime_sha,
            }
            self.live_route_verification = {
                "base": PUBLIC_BASE,
                "checked": 0,
                "status": "DRY_RUN_NOT_PROBED",
            }

        self._delete_historical_clones(snapshots)

        if self.publish:
            remaining = [
                clone_id
                for clone_id in single.HISTORICAL_CLONE_IDS
                if self.api.repo_exists(clone_id, repo_type="space")
            ]
            if remaining:
                raise RuntimeError(f"A11oy clone deletion verification failed: {remaining}")
            self._verify_clone_absence_in_collections()
            final = self._wait_for_exact_canonical(
                expected_repo_sha=expected_repo_sha,
                expected_runtime_sha=expected_runtime_sha,
            )
            if final != self.canonical_flagship:
                self.canonical_flagship = final

        try:
            self.inventory["spaces"] = _records(
                self.api.list_spaces(author=legacy.ORG, full=True, limit=None)
            )
        except Exception as exc:  # noqa: BLE001
            self.record(legacy.ORG, "inventory:spaces:refresh", "error", repr(exc)[:300])

    def _collection_item_resolves(self, item_type: str, item_id: str) -> None:
        if item_type in REPO_ITEM_TYPES:
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
        self.collection_validation: dict[str, dict[str, Any]] = {}
        for summary in self.inventory.get("collections", []):
            slug = str(summary.get("slug") or summary.get("id") or "")
            title = str(summary.get("title") or slug)
            if not slug:
                self.record(legacy.ORG, "collection-resolution", "error", "collection without slug")
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
                self.collection_validation[slug] = {
                    "title": title,
                    "total_items": len(items),
                    "resolved_items": resolved,
                    "unresolved_items": unresolved,
                    "private": getattr(collection, "private", None),
                    "theme": getattr(collection, "theme", None),
                }
                if unresolved:
                    self.record(
                        slug,
                        "collection-resolution",
                        "error",
                        f"unresolved={unresolved[:20]}",
                    )
                else:
                    self.record(
                        slug,
                        "collection-resolution",
                        "validated",
                        f"resolving_items={resolved}",
                    )
            except Exception as exc:  # noqa: BLE001
                self.collection_validation[slug] = {
                    "title": title,
                    "unresolved_items": [f"{type(exc).__name__}:{exc}"],
                }
                self.record(slug, "collection-resolution", "error", repr(exc)[:300])

    def validate_buckets(self) -> None:
        self.bucket_snapshots: dict[str, dict[str, Any]] = {}
        for item in self.inventory.get("buckets", []):
            bucket_id = str(item.get("id") or item.get("name") or "")
            if not bucket_id:
                self.record(legacy.ORG, "bucket-contract", "error", "bucket without id")
                continue
            try:
                info = self.api.bucket_info(bucket_id)
                private = getattr(info, "private", None)
                size = getattr(info, "size", None)
                total_files = getattr(info, "total_files", None)
                if not isinstance(private, bool):
                    raise RuntimeError(f"private flag is invalid: {private!r}")
                if not isinstance(size, int) or size < 0:
                    raise RuntimeError(f"size is invalid: {size!r}")
                if not isinstance(total_files, int) or total_files < 0:
                    raise RuntimeError(f"total_files is invalid: {total_files!r}")
                sample = list(islice(self.api.list_bucket_tree(bucket_id, recursive=True), 5))
                self.bucket_snapshots[bucket_id] = {
                    "private": private,
                    "size": size,
                    "total_files": total_files,
                    "sample_entries": len(sample),
                }
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
        report["schema"] = "szl.hf-single-canonical-estate-report/v2"
        report["inventory_contract"] = "huggingface_hub-supported-api/v2"
        report["clone_recreation"] = "PERMANENTLY_DISABLED"
        report["live_route_verification"] = getattr(
            self, "live_route_verification", {}
        )
        report["collection_validation"] = getattr(
            self, "collection_validation", {}
        )
        report["bucket_snapshots"] = getattr(self, "bucket_snapshots", {})
        report["boundaries"] = [
            "SZLHOLDINGS/a11oy is the sole governed A11oy Hugging Face Space.",
            "Only the newest genuinely authored divergent content tree may be adopted into the canonical Space.",
            "The four historical clone repositories and every collection reference are deleted after canonical proof.",
            "No active publisher path creates, duplicates, refreshes, publishes, or changes visibility of a clone.",
            "Canonical proof requires public visibility, Docker SDK, exact repository/runtime revisions, byte parity, and safe route contracts.",
            "No model weights or dataset payloads are changed by this estate lane.",
            "No paid hardware tier is changed.",
            "Collections and buckets are inventoried and read back through supported huggingface_hub APIs.",
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
        report = SingleCanonicalEstateUpgradeV2(
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
