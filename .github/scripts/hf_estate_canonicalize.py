#!/usr/bin/env python3
"""Consolidate A11oy to one governed Hugging Face Space.

The only surviving repository is ``SZLHOLDINGS/a11oy``. Before deleting the
historical ``a11oy-clone-1`` through ``a11oy-clone-4`` repositories, the
reconciler inventories the canonical Space and every existing clone, selects
the most recently modified valid Docker Space, and copies any newer byte-level
content into the canonical repository. It then verifies the canonical Space is
RUNNING at an immutable revision, removes clone references from collections,
deletes the four exact clone repositories, and proves they are absent.

No code path creates, duplicates, publishes, refreshes, or changes visibility
of an A11oy clone. The inherited estate publisher's clone list is emptied at
import time so collection maintenance and direct wrapper execution cannot
reintroduce clones.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any

import hf_estate_upgrade as legacy

HISTORICAL_CLONE_IDS = tuple(
    f"{legacy.ORG}/a11oy-clone-{index}" for index in range(1, 5)
)
CANDIDATE_IDS = (legacy.FLAGSHIP_SPACE, *HISTORICAL_CLONE_IDS)
TERMINAL_FAILURE_STAGES = {
    "BUILD_ERROR",
    "RUNTIME_ERROR",
    "CONFIG_ERROR",
    "NO_APP_FILE",
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# Permanent kill switch for the inherited clone creator and collection additions.
legacy.CLONE_IDS = []


def _runtime_stage(value: Any) -> str:
    runtime = getattr(value, "runtime", None)
    raw = getattr(runtime, "stage", None)
    raw = getattr(raw, "value", raw)
    return str(raw or "UNKNOWN").split(".")[-1].upper()


def _detail_stage(detail: dict[str, Any]) -> str:
    runtime = detail.get("runtime") or {}
    raw = runtime.get("stage") or runtime.get("status") or "UNKNOWN"
    return str(raw).split(".")[-1].upper()


def _parse_modified(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


class SingleA11oyEstateUpgrade(legacy.EstateUpgrade):
    """Estate upgrade that converges all A11oy content into one Space."""

    @staticmethod
    def _tree_identity(entry: Any) -> str | None:
        lfs = getattr(entry, "lfs", None)
        lfs_sha = getattr(lfs, "sha256", None)
        if lfs_sha:
            return f"lfs:{lfs_sha}"
        blob_id = getattr(entry, "blob_id", None)
        return f"git:{blob_id}" if blob_id else None

    def _repo_file_map(self, repo_id: str) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for entry in self.api.list_repo_tree(
            repo_id,
            repo_type="space",
            recursive=True,
            expand=False,
        ):
            path = str(getattr(entry, "path", "") or "")
            identity = self._tree_identity(entry)
            if path and identity:
                mapping[path] = identity
        return mapping

    def _candidate_snapshot(self, repo_id: str) -> dict[str, Any]:
        if not self.api.repo_exists(repo_id, repo_type="space"):
            snapshot = {"repo_id": repo_id, "exists": False, "valid": False}
            self.record(repo_id, "a11oy-candidate", "ok", "absent")
            return snapshot

        detail = self._space_detail(repo_id)
        sha = str(detail.get("sha") or "")
        modified = detail.get("lastModified") or detail.get("last_modified")
        files = set(self.api.list_repo_files(repo_id, repo_type="space"))
        snapshot = {
            "repo_id": repo_id,
            "exists": True,
            "sha": sha,
            "private": detail.get("private"),
            "stage": _detail_stage(detail),
            "last_modified": str(modified or ""),
            "last_modified_epoch": _parse_modified(modified),
            "dockerfile_present": "Dockerfile" in files,
            "valid": bool(SHA_RE.fullmatch(sha) and "Dockerfile" in files),
        }
        self.record(
            repo_id,
            "a11oy-candidate",
            "validated" if snapshot["valid"] else "warning",
            (
                f"stage={snapshot['stage']}; private={snapshot['private']}; "
                f"sha={sha or 'UNKNOWN'}; modified={snapshot['last_modified'] or 'UNKNOWN'}; "
                f"dockerfile={snapshot['dockerfile_present']}"
            ),
        )
        return snapshot

    def _select_newest_source(
        self,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        snapshots = {
            repo_id: self._candidate_snapshot(repo_id) for repo_id in CANDIDATE_IDS
        }
        valid = [item for item in snapshots.values() if item.get("valid")]
        if not valid:
            raise RuntimeError("No valid canonical-or-clone A11oy Docker Space exists")
        selected = max(
            valid,
            key=lambda item: (
                float(item.get("last_modified_epoch") or 0.0),
                item["repo_id"] == legacy.FLAGSHIP_SPACE,
                str(item.get("sha") or ""),
            ),
        )
        self.record(
            selected["repo_id"],
            "select-newest-a11oy-source",
            "validated",
            (
                f"modified={selected.get('last_modified') or 'UNKNOWN'}; "
                f"sha={selected.get('sha')}; stage={selected.get('stage')}"
            ),
        )
        return selected, snapshots

    def _sync_source_to_canonical(
        self,
        source_id: str,
    ) -> tuple[str | None, int, int]:
        if source_id == legacy.FLAGSHIP_SPACE:
            current = self.api.space_info(legacy.FLAGSHIP_SPACE)
            self.record(
                legacy.FLAGSHIP_SPACE,
                "canonical-content-adoption",
                "ok",
                "canonical repository is already the newest valid source",
            )
            return str(getattr(current, "sha", "") or ""), 0, 0

        source = self._repo_file_map(source_id)
        destination = self._repo_file_map(legacy.FLAGSHIP_SPACE)
        excluded = {".gitattributes", legacy.MANAGED_PATH}
        copy_paths = sorted(
            path
            for path, identity in source.items()
            if path not in excluded and destination.get(path) != identity
        )
        delete_paths = sorted(
            path
            for path in destination
            if path not in excluded and path not in source
        )

        if not copy_paths and not delete_paths:
            current = self.api.space_info(legacy.FLAGSHIP_SPACE)
            self.record(
                legacy.FLAGSHIP_SPACE,
                "canonical-content-adoption",
                "ok",
                f"already byte-equivalent to newest source {source_id}",
            )
            return str(getattr(current, "sha", "") or ""), 0, 0

        if not self.publish:
            self.record(
                legacy.FLAGSHIP_SPACE,
                "canonical-content-adoption",
                "dry-run",
                (
                    f"would adopt newest source {source_id}; "
                    f"copy={len(copy_paths)} delete={len(delete_paths)}"
                ),
            )
            return None, len(copy_paths), len(delete_paths)

        operations = [
            legacy.CommitOperationCopy(
                src_path_in_repo=path,
                path_in_repo=path,
                src_repo_id=source_id,
                src_repo_type="space",
            )
            for path in copy_paths
        ] + [
            legacy.CommitOperationDelete(path_in_repo=path)
            for path in delete_paths
        ]
        expected_sha: str | None = None
        for index in range(0, len(operations), 500):
            result = self.api.create_commit(
                repo_id=legacy.FLAGSHIP_SPACE,
                repo_type="space",
                operations=operations[index : index + 500],
                commit_message=(
                    f"fix(estate): adopt newest A11oy source {source_id} "
                    f"({index // 500 + 1})"
                ),
                commit_description=(
                    "Consolidate the newest verified A11oy content into the sole "
                    "governed Space before retiring historical clone repositories."
                ),
            )
            expected_sha = str(
                getattr(result, "oid", None)
                or getattr(result, "commit_id", None)
                or ""
            ) or expected_sha

        self.record(
            legacy.FLAGSHIP_SPACE,
            "canonical-content-adoption",
            "updated",
            (
                f"source={source_id}; copied={len(copy_paths)}; "
                f"deleted={len(delete_paths)}; expected_sha={expected_sha or 'UNKNOWN'}"
            ),
        )
        return expected_sha, len(copy_paths), len(delete_paths)

    def _wait_for_canonical(
        self,
        expected_sha: str | None,
        timeout_seconds: int = 1800,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last: dict[str, Any] = {}
        while True:
            info = self.api.space_info(legacy.FLAGSHIP_SPACE)
            sha = str(getattr(info, "sha", "") or "")
            stage = _runtime_stage(info)
            last = {
                "repo_id": legacy.FLAGSHIP_SPACE,
                "sha": sha,
                "stage": stage,
                "private": getattr(info, "private", None),
            }
            revision_ready = not expected_sha or sha == expected_sha
            if (
                revision_ready
                and stage == "RUNNING"
                and SHA_RE.fullmatch(sha)
                and last["private"] is not True
            ):
                files = set(
                    self.api.list_repo_files(
                        legacy.FLAGSHIP_SPACE,
                        repo_type="space",
                    )
                )
                if "Dockerfile" not in files:
                    raise RuntimeError("Canonical A11oy Space lost its Dockerfile")
                last["dockerfile_present"] = True
                self.record(
                    legacy.FLAGSHIP_SPACE,
                    "canonical-runtime",
                    "validated",
                    f"stage=RUNNING; sha={sha}; private={last['private']}",
                )
                return last
            if stage in TERMINAL_FAILURE_STAGES:
                raise RuntimeError(
                    f"Canonical A11oy entered terminal failure: {last}"
                )
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Canonical A11oy did not converge within "
                    f"{timeout_seconds}s: expected={expected_sha}; last={last}"
                )
            time.sleep(15)

    def _verify_adopted_file_set(self, source_id: str) -> None:
        excluded = {".gitattributes", legacy.MANAGED_PATH}
        source = {
            path: identity
            for path, identity in self._repo_file_map(source_id).items()
            if path not in excluded
        }
        canonical = {
            path: identity
            for path, identity in self._repo_file_map(legacy.FLAGSHIP_SPACE).items()
            if path not in excluded
        }
        if source != canonical:
            missing = sorted(source.keys() - canonical.keys())[:20]
            extra = sorted(canonical.keys() - source.keys())[:20]
            changed = sorted(
                path
                for path in source.keys() & canonical.keys()
                if source[path] != canonical[path]
            )[:20]
            raise RuntimeError(
                "Canonical file-set does not match selected newest source: "
                f"missing={missing}; extra={extra}; changed={changed}"
            )
        self.record(
            legacy.FLAGSHIP_SPACE,
            "canonical-file-set",
            "validated",
            f"source={source_id}; files={len(source)}",
        )

    def _remove_collection_references(self) -> None:
        clone_ids = set(HISTORICAL_CLONE_IDS)
        for summary in self.api.list_collections(owner=legacy.ORG, limit=100):
            collection = self.api.get_collection(summary.slug)
            for item in collection.items:
                if item.item_type != "space" or item.item_id not in clone_ids:
                    continue
                target = f"{collection.slug}:{item.item_id}"
                if not self.publish:
                    self.record(
                        target,
                        "collection-remove-a11oy-clone",
                        "dry-run",
                    )
                    continue
                self.api.delete_collection_item(
                    collection_slug=collection.slug,
                    item_object_id=item.item_object_id,
                    missing_ok=True,
                )
                self.record(
                    target,
                    "collection-remove-a11oy-clone",
                    "deleted",
                )

    def _delete_historical_clones(
        self,
        snapshots: dict[str, dict[str, Any]],
    ) -> None:
        self._remove_collection_references()
        for clone_id in HISTORICAL_CLONE_IDS:
            snapshot = snapshots[clone_id]
            if not snapshot.get("exists"):
                self.record(
                    clone_id,
                    "retire-a11oy-clone",
                    "ok",
                    "already absent",
                )
                continue
            if not self.publish:
                self.record(
                    clone_id,
                    "retire-a11oy-clone",
                    "dry-run",
                    (
                        f"would delete former_sha={snapshot.get('sha')}; "
                        f"modified={snapshot.get('last_modified')}"
                    ),
                )
                continue
            self.api.delete_repo(
                repo_id=clone_id,
                repo_type="space",
                missing_ok=True,
            )
            if self.api.repo_exists(clone_id, repo_type="space"):
                raise RuntimeError(
                    f"Historical A11oy clone still exists after deletion: {clone_id}"
                )
            self.record(
                clone_id,
                "retire-a11oy-clone",
                "deleted",
                f"former_sha={snapshot.get('sha')}",
            )

    def upgrade_spaces(self) -> None:
        original = self.inventory.get("spaces", [])
        self.inventory["spaces"] = [
            item
            for item in original
            if self._asset_id(item) not in HISTORICAL_CLONE_IDS
        ]
        try:
            super().upgrade_spaces()
        finally:
            self.inventory["spaces"] = original

    def create_or_refresh_clones(self) -> None:
        """Adopt the newest A11oy content, then delete every clone."""
        selected, snapshots = self._select_newest_source()
        self.candidate_snapshots = snapshots
        self.selected_newest_source = selected
        expected_sha, copied, deleted = self._sync_source_to_canonical(
            selected["repo_id"]
        )
        self.adoption_plan = {
            "source_repo_id": selected["repo_id"],
            "source_sha": selected.get("sha"),
            "copied_paths": copied,
            "deleted_paths": deleted,
            "expected_canonical_sha": expected_sha,
        }

        if self.publish:
            self.canonical_flagship = self._wait_for_canonical(expected_sha)
            self._verify_adopted_file_set(selected["repo_id"])
        else:
            canonical = snapshots.get(legacy.FLAGSHIP_SPACE, {})
            self.canonical_flagship = {
                "repo_id": legacy.FLAGSHIP_SPACE,
                "sha": canonical.get("sha"),
                "stage": canonical.get("stage"),
                "private": canonical.get("private"),
                "dockerfile_present": canonical.get("dockerfile_present"),
                "planned_source_repo_id": selected["repo_id"],
            }

        self._delete_historical_clones(snapshots)

        if self.publish:
            remaining = [
                clone_id
                for clone_id in HISTORICAL_CLONE_IDS
                if self.api.repo_exists(clone_id, repo_type="space")
            ]
            if remaining:
                raise RuntimeError(
                    f"A11oy clone deletion verification failed: {remaining}"
                )

        try:
            refreshed = self._paginate(
                f"{legacy.HF_BASE}/api/spaces?"
                f"author={legacy.ORG}&limit=1000&full=true"
            )
            self.inventory["spaces"] = [
                item
                for item in refreshed
                if self._asset_id(item) not in HISTORICAL_CLONE_IDS
            ]
        except Exception as exc:
            self.record(
                legacy.ORG,
                "inventory:spaces:refresh",
                "error",
                repr(exc)[:300],
            )

    def report(self) -> dict[str, Any]:
        report = super().report()
        report.pop("clone_ids", None)
        report["canonical_flagship_space"] = getattr(
            self,
            "canonical_flagship",
            {"repo_id": legacy.FLAGSHIP_SPACE},
        )
        report["selected_newest_source"] = getattr(
            self,
            "selected_newest_source",
            None,
        )
        report["a11oy_candidates_before_consolidation"] = getattr(
            self,
            "candidate_snapshots",
            {},
        )
        report["adoption_plan"] = getattr(self, "adoption_plan", {})
        report["retired_clone_ids"] = list(HISTORICAL_CLONE_IDS)
        report["summary"]["ok"] = sum(
            action.status
            in {
                "ok",
                "updated",
                "created",
                "validated",
                "requested",
                "deleted",
            }
            for action in self.actions
        )
        report["boundaries"] = [
            "SZLHOLDINGS/a11oy is the sole governed A11oy Space.",
            "The newest valid content among the canonical Space and four historical clones is adopted before deletion.",
            "The exact a11oy-clone-1..4 repositories are deleted and cannot be recreated by this publisher.",
            "No model weights or dataset payloads are changed.",
            "No paid hardware tier is changed.",
            "Healthy non-A11oy dynamic Spaces are not rewritten or restarted.",
            "Kernel repositories are validated; first-class kernel publishing remains governed by kernel-builder release workflows.",
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
        print(
            "FATAL: HF_ORG_TOKEN/HF_ORG_TOKEN1/HF_TOKEN is not set.",
            file=sys.stderr,
        )
        return 2

    try:
        report = SingleA11oyEstateUpgrade(
            token=token,
            generation=args.generation,
            publish=args.publish,
        ).run()
    except Exception as exc:
        print(f"FATAL: {exc!r}", file=sys.stderr)
        return 2

    summary = report["summary"]
    print(json.dumps(summary, indent=2))
    return 1 if summary["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
