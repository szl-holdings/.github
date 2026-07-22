#!/usr/bin/env python3
"""Keep exactly one governed A11oy Hugging Face Space.

The sole survivor is ``SZLHOLDINGS/a11oy``. The reconciler inventories that
Space plus the four historical ``a11oy-clone-*`` repositories, adopts the most
recently modified valid Docker Space into the canonical repository, verifies the
canonical runtime, removes all clone collection references, deletes only the
four exact clone IDs, and proves they are absent.

No code path creates, duplicates, restores, refreshes, or changes visibility of
an A11oy clone. The inherited estate publisher's clone list is disabled before
its normal estate-maintenance sequence runs.
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

CLONES = tuple(f"{legacy.ORG}/a11oy-clone-{i}" for i in range(1, 5))
CANDIDATES = (legacy.FLAGSHIP_SPACE, *CLONES)
HISTORICAL_CLONE_IDS = CLONES
CANDIDATE_IDS = CANDIDATES
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
FAILURE_STAGES = {"BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE"}
EXCLUDED_PATHS = {".gitattributes", legacy.MANAGED_PATH}

# Kill the inherited creation and collection-add paths before base execution.
legacy.CLONE_IDS = []


def _epoch(value: Any) -> float:
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


def _stage(detail: dict[str, Any]) -> str:
    runtime = detail.get("runtime") or {}
    value = runtime.get("stage") or runtime.get("status") or "UNKNOWN"
    return str(value).split(".")[-1].upper()


class SingleA11oyUpgrade(legacy.EstateUpgrade):
    """Run normal estate maintenance while converging A11oy to one Space."""

    def _snapshot(self, repo_id: str) -> dict[str, Any]:
        if not self.api.repo_exists(repo_id, repo_type="space"):
            result = {"repo_id": repo_id, "exists": False, "valid": False}
            self.record(repo_id, "a11oy-candidate", "ok", "absent")
            return result

        detail = self._space_detail(repo_id)
        files = set(self.api.list_repo_files(repo_id, repo_type="space"))
        modified = detail.get("lastModified") or detail.get("last_modified")
        sha = str(detail.get("sha") or "")
        result = {
            "repo_id": repo_id,
            "exists": True,
            "sha": sha,
            "private": detail.get("private"),
            "stage": _stage(detail),
            "last_modified": str(modified or ""),
            "modified_epoch": _epoch(modified),
            "dockerfile_present": "Dockerfile" in files,
            "valid": bool(SHA_RE.fullmatch(sha) and "Dockerfile" in files),
        }
        self.record(
            repo_id,
            "a11oy-candidate",
            "validated" if result["valid"] else "warning",
            (
                f"stage={result['stage']}; private={result['private']}; "
                f"sha={sha or 'UNKNOWN'}; modified={result['last_modified'] or 'UNKNOWN'}; "
                f"dockerfile={result['dockerfile_present']}"
            ),
        )
        return result

    def _select_source(
        self,
    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        snapshots = {repo_id: self._snapshot(repo_id) for repo_id in CANDIDATES}
        eligible = [
            item
            for item in snapshots.values()
            if item.get("valid") and item.get("stage") == "RUNNING"
        ]
        if not eligible:
            raise RuntimeError(
                "No RUNNING valid canonical-or-clone A11oy Docker Space exists"
            )
        selected = max(
            eligible,
            key=lambda item: (
                float(item.get("modified_epoch") or 0.0),
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

    def _adopt_source(self, source_id: str) -> str | None:
        if source_id == legacy.FLAGSHIP_SPACE:
            info = self.api.space_info(legacy.FLAGSHIP_SPACE)
            self.record(
                legacy.FLAGSHIP_SPACE,
                "canonical-content-adoption",
                "ok",
                "canonical repository is already the newest valid source",
            )
            return str(getattr(info, "sha", "") or "")

        source_files = set(self.api.list_repo_files(source_id, repo_type="space"))
        canonical_files = set(
            self.api.list_repo_files(legacy.FLAGSHIP_SPACE, repo_type="space")
        )
        copy_paths = sorted(source_files - EXCLUDED_PATHS)
        delete_paths = sorted(canonical_files - source_files - EXCLUDED_PATHS)
        if not self.publish:
            self.record(
                legacy.FLAGSHIP_SPACE,
                "canonical-content-adoption",
                "dry-run",
                (
                    f"would adopt {source_id}; copy={len(copy_paths)}; "
                    f"delete={len(delete_paths)}"
                ),
            )
            return None

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
        expected: str | None = None
        for offset in range(0, len(operations), 500):
            result = self.api.create_commit(
                repo_id=legacy.FLAGSHIP_SPACE,
                repo_type="space",
                operations=operations[offset : offset + 500],
                commit_message=(
                    f"fix(estate): adopt newest A11oy source {source_id} "
                    f"({offset // 500 + 1})"
                ),
                commit_description=(
                    "Consolidate the newest valid A11oy source into the sole "
                    "governed Space before retiring historical clones."
                ),
            )
            expected = str(
                getattr(result, "oid", None)
                or getattr(result, "commit_id", None)
                or ""
            ) or expected
        self.record(
            legacy.FLAGSHIP_SPACE,
            "canonical-content-adoption",
            "updated",
            (
                f"source={source_id}; copied={len(copy_paths)}; "
                f"deleted={len(delete_paths)}; expected_sha={expected or 'UNKNOWN'}"
            ),
        )
        return expected

    def _wait_for_canonical(
        self,
        expected_sha: str | None,
        timeout_seconds: int = 1800,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        restart_requested = False
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            detail = self._space_detail(legacy.FLAGSHIP_SPACE)
            sha = str(detail.get("sha") or "")
            stage = _stage(detail)
            last = {
                "repo_id": legacy.FLAGSHIP_SPACE,
                "sha": sha,
                "stage": stage,
                "private": detail.get("private"),
                "dockerfile_present": (
                    "Dockerfile"
                    in set(
                        self.api.list_repo_files(
                            legacy.FLAGSHIP_SPACE,
                            repo_type="space",
                        )
                    )
                ),
            }
            if (
                (not expected_sha or sha == expected_sha)
                and stage == "RUNNING"
                and SHA_RE.fullmatch(sha)
                and last["private"] is not True
                and last["dockerfile_present"]
            ):
                self.record(
                    legacy.FLAGSHIP_SPACE,
                    "canonical-runtime",
                    "validated",
                    f"stage=RUNNING; sha={sha}; private={last['private']}",
                )
                return last
            if stage in FAILURE_STAGES:
                raise RuntimeError(f"Canonical A11oy entered terminal failure: {last}")
            if (
                self.publish
                and not restart_requested
                and stage in {"PAUSED", "STOPPED", "SLEEPING"}
            ):
                self.api.restart_space(
                    repo_id=legacy.FLAGSHIP_SPACE,
                    factory_reboot=False,
                )
                restart_requested = True
                self.record(
                    legacy.FLAGSHIP_SPACE,
                    "canonical-restart",
                    "requested",
                    f"stage={stage}",
                )
            time.sleep(15)
        raise RuntimeError(
            f"Canonical A11oy did not converge: expected={expected_sha}; last={last}"
        )

    def _remove_collection_refs(self) -> None:
        clone_ids = set(CLONES)
        for summary in self.api.list_collections(owner=legacy.ORG, limit=100):
            collection = self.api.get_collection(summary.slug)
            for item in collection.items:
                if item.item_type != "space" or item.item_id not in clone_ids:
                    continue
                target = f"{collection.slug}:{item.item_id}"
                if not self.publish:
                    self.record(target, "collection-remove-a11oy-clone", "dry-run")
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

    def _delete_clones(self, snapshots: dict[str, dict[str, Any]]) -> None:
        self._remove_collection_refs()
        for clone_id in CLONES:
            snapshot = snapshots[clone_id]
            if not snapshot.get("exists"):
                self.record(clone_id, "retire-a11oy-clone", "ok", "already absent")
                continue
            if not self.publish:
                self.record(
                    clone_id,
                    "retire-a11oy-clone",
                    "dry-run",
                    f"would delete former_sha={snapshot.get('sha')}",
                )
                continue
            self.api.delete_repo(
                repo_id=clone_id,
                repo_type="space",
                missing_ok=True,
            )
            if self.api.repo_exists(clone_id, repo_type="space"):
                raise RuntimeError(f"Clone remains after deletion: {clone_id}")
            self.record(
                clone_id,
                "retire-a11oy-clone",
                "deleted",
                f"former_sha={snapshot.get('sha')}",
            )

    def upgrade_spaces(self) -> None:
        original = self.inventory.get("spaces", [])
        self.inventory["spaces"] = [
            item for item in original if self._asset_id(item) not in CLONES
        ]
        try:
            super().upgrade_spaces()
        finally:
            self.inventory["spaces"] = original

    def create_or_refresh_clones(self) -> None:
        """Adopt newest A11oy content and retire every historical clone."""
        selected, snapshots = self._select_source()
        expected_sha = self._adopt_source(selected["repo_id"])
        self.selected_source = selected
        self.candidate_snapshots = snapshots

        canonical_snapshot = snapshots.get(legacy.FLAGSHIP_SPACE, {})
        self.canonical_flagship = (
            self._wait_for_canonical(expected_sha)
            if self.publish
            else {
                "repo_id": legacy.FLAGSHIP_SPACE,
                "sha": canonical_snapshot.get("sha"),
                "stage": canonical_snapshot.get("stage"),
                "private": canonical_snapshot.get("private"),
                "dockerfile_present": canonical_snapshot.get(
                    "dockerfile_present"
                ),
            }
        )
        self._delete_clones(snapshots)

        if self.publish:
            for clone_id in CLONES:
                if self.api.repo_exists(clone_id, repo_type="space"):
                    raise RuntimeError(f"Clone still exists: {clone_id}")
            self.inventory["spaces"] = self._paginate(
                f"{legacy.HF_BASE}/api/spaces?"
                f"author={legacy.ORG}&limit=1000&full=true"
            )
        else:
            self.inventory["spaces"] = [
                item
                for item in self.inventory.get("spaces", [])
                if self._asset_id(item) not in CLONES
            ]

    def report(self) -> dict[str, Any]:
        report = super().report()
        report["canonical_flagship_space"] = getattr(
            self,
            "canonical_flagship",
            {"repo_id": legacy.FLAGSHIP_SPACE},
        )
        report["selected_newest_source"] = getattr(self, "selected_source", None)
        report["candidate_snapshots"] = getattr(
            self,
            "candidate_snapshots",
            {},
        )
        report["clone_ids"] = []
        report["retired_clone_ids"] = list(CLONES)
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
            "The newest valid A11oy content is adopted before clone deletion.",
            "Only the four exact a11oy-clone-1..4 repositories may be deleted.",
            "No active path creates, restores, refreshes, or publicizes an A11oy clone.",
            "No model weights or dataset payloads are changed.",
            "No paid hardware tier is changed.",
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
        report = SingleA11oyUpgrade(
            token=token,
            generation=args.generation,
            publish=args.publish,
        ).run()
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 1 if report["summary"]["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
