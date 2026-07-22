#!/usr/bin/env python3
"""Reconcile the SZLHOLDINGS Hub around one canonical A11oy and four public clones.

The canonical production Space remains ``SZLHOLDINGS/a11oy``. The four exact
managed clones ``a11oy-clone-1`` through ``a11oy-clone-4`` are retained as
public CPU-basic recovery/showcase runtimes and refreshed from the canonical
Space without using Hugging Face's daily-limited duplication endpoint.

Only surplus repositories that are positively identified as A11oy duplicates
are eligible for deletion. A repository is a surplus duplicate only when it is
outside the five-Space keep set and either:

* its name matches the narrow ``a11oy-(clone|copy|duplicate)-<number>`` form; or
* its managed marker explicitly declares ``clone_of=SZLHOLDINGS/a11oy``.

The wrapper preserves the estate-wide model/dataset markers, Space health
checks, collections, kernel validation, and evidence report from
``hf_estate_upgrade.py``.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any

import hf_estate_upgrade as legacy

MANAGED_CLONE_IDS = tuple(
    f"{legacy.ORG}/a11oy-clone-{index}" for index in range(1, 5)
)
KEEP_SPACE_IDS = frozenset((legacy.FLAGSHIP_SPACE, *MANAGED_CLONE_IDS))
DUPLICATE_NAME = re.compile(
    rf"^{re.escape(legacy.ORG)}/a11oy-(?:clone|copy|duplicate)-\d+$",
    re.IGNORECASE,
)
MARKER_URL = (
    "https://huggingface.co/spaces/{repo_id}/resolve/main/"
    + legacy.MANAGED_PATH
)
TERMINAL_FAILURE_STAGES = {
    "BUILD_ERROR",
    "RUNTIME_ERROR",
    "CONFIG_ERROR",
    "NO_APP_FILE",
}


# The inherited collection builder consults this module global. Keep the exact
# managed clone set enabled so the Spaces and Canonical Estate collections
# include the four public recovery/showcase runtimes.
legacy.CLONE_IDS = list(MANAGED_CLONE_IDS)


def _runtime_stage(info: Any) -> str:
    runtime = getattr(info, "runtime", None)
    raw = getattr(runtime, "stage", None)
    raw = getattr(raw, "value", raw)
    return str(raw or "UNKNOWN").split(".")[-1].upper()


def _snapshot(info: Any) -> dict[str, Any]:
    return {
        "sha": str(getattr(info, "sha", "") or ""),
        "private": getattr(info, "private", None),
        "stage": _runtime_stage(info),
    }


class CommandCenterEstateUpgrade(legacy.EstateUpgrade):
    """Estate upgrade with four retained public A11oy command-center clones."""

    def _verify_canonical_flagship(self) -> dict[str, Any]:
        if not self.api.repo_exists(legacy.FLAGSHIP_SPACE, repo_type="space"):
            raise RuntimeError(f"Canonical Space is missing: {legacy.FLAGSHIP_SPACE}")

        info = self.api.space_info(legacy.FLAGSHIP_SPACE)
        stage = _runtime_stage(info)
        sha = str(getattr(info, "sha", "") or "")
        private = getattr(info, "private", None)
        files = set(self.api.list_repo_files(legacy.FLAGSHIP_SPACE, repo_type="space"))

        if stage != "RUNNING":
            raise RuntimeError(
                f"Canonical Space is not RUNNING: {legacy.FLAGSHIP_SPACE} stage={stage}"
            )
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise RuntimeError(
                "Canonical Space revision is not an immutable 40-character SHA: "
                f"{sha!r}"
            )
        if private is True:
            raise RuntimeError(
                f"Canonical Space unexpectedly became private: {legacy.FLAGSHIP_SPACE}"
            )
        if "Dockerfile" not in files:
            raise RuntimeError(
                f"Canonical Docker Space is missing Dockerfile: {legacy.FLAGSHIP_SPACE}"
            )

        snapshot = {
            "repo_id": legacy.FLAGSHIP_SPACE,
            "stage": stage,
            "sha": sha,
            "private": private,
            "dockerfile_present": True,
        }
        self.record(
            legacy.FLAGSHIP_SPACE,
            "canonical-space-preflight",
            "validated",
            f"stage={stage}; sha={sha}; private={private}",
        )
        return snapshot

    def _read_marker(self, repo_id: str) -> dict[str, Any] | None:
        response = self.http.get(
            MARKER_URL.format(repo_id=repo_id),
            headers={"Cache-Control": "no-cache"},
            timeout=45,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None

    def _is_surplus_duplicate(self, repo_id: str) -> tuple[bool, str]:
        if repo_id in KEEP_SPACE_IDS:
            return False, "keep-set"
        if DUPLICATE_NAME.fullmatch(repo_id):
            return True, "narrow-name-match"
        try:
            marker = self._read_marker(repo_id)
        except Exception as exc:
            self.record(
                repo_id,
                "duplicate-marker-read",
                "warning",
                repr(exc)[:250],
            )
            return False, "marker-unavailable"
        if marker and marker.get("clone_of") == legacy.FLAGSHIP_SPACE:
            return True, "managed-marker-clone-of-canonical"
        return False, "not-proven-duplicate"

    def _set_public(self, repo_id: str) -> None:
        info = self.api.space_info(repo_id)
        if getattr(info, "private", None) is False:
            self.record(repo_id, "clone-visibility", "ok", "already public")
            return
        if not self.publish:
            self.record(repo_id, "clone-visibility", "dry-run", "would make public")
            return

        update = getattr(self.api, "update_repo_settings", None)
        if not callable(update):
            raise RuntimeError(
                "Installed huggingface_hub lacks HfApi.update_repo_settings; "
                f"cannot safely make {repo_id} public"
            )
        try:
            update(repo_id=repo_id, repo_type="space", private=False)
        except TypeError:
            # Compatibility with clients whose signature infers repo_type.
            update(repo_id=repo_id, private=False)

        after = self.api.space_info(repo_id)
        if getattr(after, "private", None) is not False:
            raise RuntimeError(f"Visibility update did not make {repo_id} public")
        self.record(repo_id, "clone-visibility", "updated", "public")

    def _create_missing_clone(self, clone_id: str) -> None:
        if not self.publish:
            self.record(
                clone_id,
                "flagship-clone",
                "dry-run",
                "would create public cpu-basic Space without duplication API",
            )
            return
        self.api.create_repo(
            repo_id=clone_id,
            repo_type="space",
            private=False,
            exist_ok=True,
            space_sdk="docker",
            space_hardware="cpu-basic",
            space_sleep_time=300,
        )
        if not self.api.repo_exists(clone_id, repo_type="space"):
            raise RuntimeError(f"Clone creation did not produce repository: {clone_id}")
        self.record(
            clone_id,
            "flagship-clone",
            "created",
            "public cpu-basic; quota-safe create_repo path",
        )

    def _wait_for_running(self, repo_id: str, timeout_seconds: int = 1800) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last: dict[str, Any] = {}
        while True:
            info = self.api.space_info(repo_id)
            last = _snapshot(info)
            stage = last["stage"]
            if stage == "RUNNING":
                self.record(
                    repo_id,
                    "clone-runtime",
                    "validated",
                    f"stage=RUNNING; sha={last['sha']}; private={last['private']}",
                )
                return last
            if stage in TERMINAL_FAILURE_STAGES:
                raise RuntimeError(
                    f"Clone runtime entered terminal failure: {repo_id} stage={stage}"
                )
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Clone runtime did not reach RUNNING within {timeout_seconds}s: "
                    f"{repo_id} last={last}"
                )
            time.sleep(15)

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
            identity = self._tree_identity(entry)
            path = str(getattr(entry, "path", "") or "")
            if path and identity:
                mapping[path] = identity
        return mapping

    def _sync_clone_from_canonical(self, clone_id: str) -> tuple[int, int]:
        source = self._repo_file_map(legacy.FLAGSHIP_SPACE)
        destination = self._repo_file_map(clone_id)

        copy_paths = sorted(
            path
            for path, identity in source.items()
            if path != ".gitattributes" and destination.get(path) != identity
        )
        delete_paths = sorted(
            path
            for path in destination
            if path not in source and path not in {".gitattributes", legacy.MANAGED_PATH}
        )
        operations = [
            legacy.CommitOperationCopy(
                src_path_in_repo=path,
                path_in_repo=path,
                src_repo_id=legacy.FLAGSHIP_SPACE,
                src_repo_type="space",
            )
            for path in copy_paths
        ] + [
            legacy.CommitOperationDelete(path_in_repo=path)
            for path in delete_paths
        ]

        if not operations:
            self.record(clone_id, "clone-refresh", "ok", "already byte-current")
            return 0, 0

        for index in range(0, len(operations), 500):
            chunk = operations[index : index + 500]
            self.api.create_commit(
                repo_id=clone_id,
                repo_type="space",
                operations=chunk,
                commit_message=(
                    f"chore(clone): sync canonical A11oy generation "
                    f"{self.generation[:12]} ({index // 500 + 1})"
                ),
                commit_description=(
                    f"Quota-safe server-side copy from "
                    f"{legacy.FLAGSHIP_SPACE}; canonical revision is recorded "
                    "in the managed marker."
                ),
            )

        self.record(
            clone_id,
            "clone-refresh",
            "updated",
            f"copied={len(copy_paths)} deleted={len(delete_paths)}",
        )
        return len(copy_paths), len(delete_paths)

    def _verify_clone_file_set(self, clone_id: str) -> None:
        source_files = set(
            self.api.list_repo_files(legacy.FLAGSHIP_SPACE, repo_type="space")
        )
        clone_files = set(self.api.list_repo_files(clone_id, repo_type="space"))
        source_files.discard(".gitattributes")
        clone_files.discard(".gitattributes")
        clone_files.discard(legacy.MANAGED_PATH)
        if clone_files != source_files:
            missing = sorted(source_files - clone_files)[:20]
            extra = sorted(clone_files - source_files)[:20]
            raise RuntimeError(
                f"Clone file-set mismatch for {clone_id}: missing={missing}; extra={extra}"
            )
        self.record(
            clone_id,
            "clone-file-set",
            "validated",
            f"files={len(source_files)}",
        )

    def _reconcile_clone(
        self,
        clone_id: str,
        canonical_sha: str,
    ) -> dict[str, Any]:
        exists = self.api.repo_exists(clone_id, repo_type="space")
        if not exists:
            self._create_missing_clone(clone_id)
            if not self.publish:
                return {"exists": False, "planned": True}

        before = _snapshot(self.api.space_info(clone_id))
        self.record(
            clone_id,
            "clone-preflight",
            "ok",
            f"private={before['private']}; stage={before['stage']}; sha={before['sha']}",
        )
        self._set_public(clone_id)

        if not self.publish:
            self.record(
                clone_id,
                "clone-refresh",
                "dry-run",
                f"would sync from {legacy.FLAGSHIP_SPACE}@{canonical_sha}",
            )
            return before

        # Copy only byte-different files in bounded server-side commits, avoiding
        # local downloads and the daily-limited duplicate endpoint.
        self._sync_clone_from_canonical(clone_id)
        self._upload_marker(
            repo_id=clone_id,
            repo_type="space",
            observed_sha=before.get("sha"),
            runtime={"stage_before": before.get("stage")},
            clone_of=legacy.FLAGSHIP_SPACE,
        )
        self._verify_clone_file_set(clone_id)

        # A content commit normally triggers a rebuild. If the clone was already
        # current, restart only when it is not running.
        current = self.api.space_info(clone_id)
        if _runtime_stage(current) != "RUNNING":
            self.api.restart_space(repo_id=clone_id, factory_reboot=False)
            self.record(clone_id, "clone-restart", "requested")

        after = self._wait_for_running(clone_id)
        if after["private"] is not False:
            raise RuntimeError(f"Clone became non-public after reconciliation: {clone_id}")
        return after

    def _remove_collection_references(self, repo_ids: set[str]) -> None:
        if not repo_ids:
            return
        summaries = list(self.api.list_collections(owner=legacy.ORG, limit=100))
        for summary in summaries:
            collection = self.api.get_collection(summary.slug)
            for item in collection.items:
                if item.item_type != "space" or item.item_id not in repo_ids:
                    continue
                target = f"{collection.slug}:{item.item_id}"
                if not self.publish:
                    self.record(target, "collection-remove-surplus", "dry-run")
                    continue
                self.api.delete_collection_item(
                    collection_slug=collection.slug,
                    item_object_id=item.item_object_id,
                    missing_ok=True,
                )
                self.record(target, "collection-remove-surplus", "deleted")

    def _delete_surplus_duplicates(self) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for item in self.inventory.get("spaces", []):
            repo_id = self._asset_id(item)
            if not repo_id:
                continue
            eligible, reason = self._is_surplus_duplicate(repo_id)
            if not eligible:
                continue
            info = self.api.space_info(repo_id)
            candidates.append(
                {
                    "repo_id": repo_id,
                    "reason": reason,
                    **_snapshot(info),
                }
            )

        candidate_ids = {item["repo_id"] for item in candidates}
        self._remove_collection_references(candidate_ids)
        for candidate in candidates:
            repo_id = candidate["repo_id"]
            if not self.publish:
                self.record(
                    repo_id,
                    "delete-surplus-duplicate",
                    "dry-run",
                    f"reason={candidate['reason']}; sha={candidate['sha']}",
                )
                continue
            self.api.delete_repo(repo_id=repo_id, repo_type="space", missing_ok=True)
            if self.api.repo_exists(repo_id, repo_type="space"):
                raise RuntimeError(f"Surplus duplicate still exists after deletion: {repo_id}")
            self.record(
                repo_id,
                "delete-surplus-duplicate",
                "deleted",
                f"reason={candidate['reason']}; former_sha={candidate['sha']}",
            )
        return candidates

    def create_or_refresh_clones(self) -> None:
        """Retain, publish, synchronize, and verify four exact managed clones."""
        self.canonical_flagship = self._verify_canonical_flagship()
        canonical_sha = self.canonical_flagship["sha"]
        self.managed_clone_snapshots: dict[str, dict[str, Any]] = {}

        for clone_id in MANAGED_CLONE_IDS:
            self.managed_clone_snapshots[clone_id] = self._reconcile_clone(
                clone_id, canonical_sha
            )

        self.surplus_duplicate_snapshots = self._delete_surplus_duplicates()

        # Refresh Space inventory after clone creation/visibility changes/deletions
        # so collection curation and report counts describe the final estate.
        try:
            self.inventory["spaces"] = self._paginate(
                f"{legacy.HF_BASE}/api/spaces?author={legacy.ORG}&limit=1000&full=true"
            )
        except Exception as exc:
            self.record(
                legacy.ORG,
                "inventory:spaces:refresh",
                "error",
                repr(exc)[:300],
            )

    def report(self) -> dict[str, Any]:
        report = super().report()
        report["canonical_flagship_space"] = getattr(
            self, "canonical_flagship", {"repo_id": legacy.FLAGSHIP_SPACE}
        )
        report["managed_clone_ids"] = list(MANAGED_CLONE_IDS)
        report["managed_clone_snapshots"] = getattr(
            self, "managed_clone_snapshots", {}
        )
        report["surplus_duplicate_snapshots"] = getattr(
            self, "surplus_duplicate_snapshots", []
        )
        report["command_center_keep_set"] = sorted(KEEP_SPACE_IDS)
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
            "SZLHOLDINGS/a11oy remains the canonical production A11oy Space.",
            "The four exact a11oy-clone-1..4 Spaces are retained, public, and synchronized from the canonical Space.",
            "The daily-limited Hugging Face duplication endpoint is never used.",
            "Only positively identified surplus A11oy duplicates outside the five-Space keep set may be deleted.",
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
        report = CommandCenterEstateUpgrade(
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
