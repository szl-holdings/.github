#!/usr/bin/env python3
"""Reconcile SZLHOLDINGS around one canonical governed A11oy Space.

``SZLHOLDINGS/a11oy`` is the sole retained A11oy runtime. Publish mode
removes collection entries for, deletes, and verifies absence of the four
exact historical automation-created repositories ``a11oy-clone-1`` through
``a11oy-clone-4``. No replacement clone is created.
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

RETIRED_CLONE_IDS = tuple(
    f"{legacy.ORG}/a11oy-clone-{index}" for index in range(1, 5)
)
KEEP_SPACE_IDS = frozenset({legacy.FLAGSHIP_SPACE})
legacy.CLONE_IDS = []


def _runtime_stage(info: Any) -> str:
    runtime = getattr(info, "runtime", None)
    raw = getattr(runtime, "stage", None)
    raw = getattr(raw, "value", raw)
    return str(raw or "UNKNOWN").split(".")[-1].upper()


def _snapshot(info: Any) -> dict[str, Any]:
    modified = getattr(info, "last_modified", None)
    if modified is None:
        modified = getattr(info, "lastModified", None)
    return {
        "sha": str(getattr(info, "sha", "") or ""),
        "private": getattr(info, "private", None),
        "stage": _runtime_stage(info),
        "last_modified": str(modified or ""),
    }


class SingleA11oyEstateUpgrade(legacy.EstateUpgrade):
    """Estate upgrade that retains only the canonical A11oy Space."""

    def _verify_canonical_flagship(self) -> dict[str, Any]:
        if not self.api.repo_exists(legacy.FLAGSHIP_SPACE, repo_type="space"):
            raise RuntimeError(f"Canonical Space is missing: {legacy.FLAGSHIP_SPACE}")
        info = self.api.space_info(legacy.FLAGSHIP_SPACE)
        snapshot = _snapshot(info)
        files = set(self.api.list_repo_files(legacy.FLAGSHIP_SPACE, repo_type="space"))
        if snapshot["stage"] != "RUNNING":
            raise RuntimeError(
                f"Canonical Space is not RUNNING: {legacy.FLAGSHIP_SPACE} "
                f"stage={snapshot['stage']}"
            )
        if not re.fullmatch(r"[0-9a-f]{40}", snapshot["sha"]):
            raise RuntimeError(
                f"Canonical revision is not an immutable SHA: {snapshot['sha']!r}"
            )
        if snapshot["private"] is True:
            raise RuntimeError(
                f"Canonical Space unexpectedly became private: {legacy.FLAGSHIP_SPACE}"
            )
        if "Dockerfile" not in files:
            raise RuntimeError(
                f"Canonical Docker Space lacks Dockerfile: {legacy.FLAGSHIP_SPACE}"
            )
        result = {
            "repo_id": legacy.FLAGSHIP_SPACE,
            **snapshot,
            "dockerfile_present": True,
        }
        self.record(
            legacy.FLAGSHIP_SPACE,
            "canonical-space-preflight",
            "validated",
            f"stage={snapshot['stage']}; sha={snapshot['sha']}; "
            f"private={snapshot['private']}",
        )
        return result

    def _remove_collection_references(self, repo_ids: set[str]) -> None:
        if not repo_ids:
            return
        for summary in self.api.list_collections(owner=legacy.ORG, limit=100):
            collection = self.api.get_collection(summary.slug)
            for item in collection.items:
                if item.item_type != "space" or item.item_id not in repo_ids:
                    continue
                target = f"{collection.slug}:{item.item_id}"
                if not self.publish:
                    self.record(
                        target,
                        "collection-remove-retired-clone",
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
                    "collection-remove-retired-clone",
                    "deleted",
                )

    def create_or_refresh_clones(self) -> None:
        """Delete only the four exact retired clone IDs; create nothing."""
        self.canonical_flagship = self._verify_canonical_flagship()
        existing: dict[str, dict[str, Any]] = {}
        for repo_id in RETIRED_CLONE_IDS:
            if self.api.repo_exists(repo_id, repo_type="space"):
                existing[repo_id] = _snapshot(self.api.space_info(repo_id))
                self.record(
                    repo_id,
                    "retired-clone-preflight",
                    "ok",
                    json.dumps(existing[repo_id], sort_keys=True),
                )
            else:
                self.record(
                    repo_id,
                    "retired-clone-preflight",
                    "ok",
                    "already absent",
                )

        self._remove_collection_references(set(existing))
        self.deleted_clone_snapshots: list[dict[str, Any]] = []
        for repo_id, before in existing.items():
            snapshot = {"repo_id": repo_id, **before}
            if not self.publish:
                snapshot["planned"] = True
                self.deleted_clone_snapshots.append(snapshot)
                self.record(
                    repo_id,
                    "delete-retired-clone",
                    "dry-run",
                    f"former_sha={before['sha']}",
                )
                continue
            self.api.delete_repo(
                repo_id=repo_id,
                repo_type="space",
                missing_ok=True,
            )
            if self.api.repo_exists(repo_id, repo_type="space"):
                raise RuntimeError(
                    f"Retired clone still exists after deletion: {repo_id}"
                )
            self.deleted_clone_snapshots.append(snapshot)
            self.record(
                repo_id,
                "delete-retired-clone",
                "deleted",
                f"former_sha={before['sha']}",
            )

        remaining = [
            repo_id
            for repo_id in RETIRED_CLONE_IDS
            if self.api.repo_exists(repo_id, repo_type="space")
        ]
        if self.publish and remaining:
            raise RuntimeError(f"Retired A11oy clones remain: {remaining}")

        self.inventory["spaces"] = self._paginate(
            f"{legacy.HF_BASE}/api/spaces?author={legacy.ORG}&limit=1000&full=true"
        )
        self.record(
            legacy.FLAGSHIP_SPACE,
            "canonical-only-policy",
            "validated",
            f"retired_clones_remaining={len(remaining)}",
        )

    def report(self) -> dict[str, Any]:
        report = super().report()
        report["canonical_flagship_space"] = getattr(
            self,
            "canonical_flagship",
            {"repo_id": legacy.FLAGSHIP_SPACE},
        )
        report["managed_clone_ids"] = []
        report["retired_clone_ids"] = list(RETIRED_CLONE_IDS)
        report["deleted_clone_snapshots"] = getattr(
            self,
            "deleted_clone_snapshots",
            [],
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
            "SZLHOLDINGS/a11oy is the sole retained governed A11oy Space.",
            "The exact historical a11oy-clone-1..4 repositories are deleted in publish mode and never recreated.",
            "No unrelated Hugging Face repository is deleted or renamed.",
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
