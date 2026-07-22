#!/usr/bin/env python3
"""Reconcile the SZLHOLDINGS Hub estate around one canonical A11oy Space.

This wrapper deliberately disables the legacy clone path in
``hf_estate_upgrade.py``. It preserves the estate-wide inventory, markers,
Space health checks, collection curation, kernel validation, and evidence
report while retiring only these exact historical private duplicates:

- SZLHOLDINGS/a11oy-clone-1
- SZLHOLDINGS/a11oy-clone-2
- SZLHOLDINGS/a11oy-clone-3
- SZLHOLDINGS/a11oy-clone-4

Deletion is fail-closed and only occurs after the canonical
``SZLHOLDINGS/a11oy`` Space is verified RUNNING at an immutable revision with
its Dockerfile present. Collection references are removed before repository
deletion, and repository absence is verified afterwards.
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

RETIRED_CLONE_IDS = (
    "SZLHOLDINGS/a11oy-clone-1",
    "SZLHOLDINGS/a11oy-clone-2",
    "SZLHOLDINGS/a11oy-clone-3",
    "SZLHOLDINGS/a11oy-clone-4",
)

# Fail closed if the historical implementation ever changes its clone set.
if tuple(legacy.CLONE_IDS) != RETIRED_CLONE_IDS:
    raise RuntimeError(
        "Legacy A11oy clone allowlist changed; review before estate reconciliation: "
        f"{legacy.CLONE_IDS!r}"
    )

# The inherited collection builder consults this module global. Emptying it
# prevents any future collection add for the retired repositories.
legacy.CLONE_IDS = []


def _runtime_stage(info: Any) -> str:
    runtime = getattr(info, "runtime", None)
    raw = getattr(runtime, "stage", None)
    raw = getattr(raw, "value", raw)
    return str(raw or "UNKNOWN").split(".")[-1].upper()


class CanonicalEstateUpgrade(legacy.EstateUpgrade):
    """Estate upgrade with exact, one-time A11oy clone retirement."""

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
                f"Canonical Space revision is not an immutable 40-character SHA: {sha!r}"
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

    def _clone_snapshots(self) -> dict[str, dict[str, Any]]:
        snapshots: dict[str, dict[str, Any]] = {}
        for clone_id in RETIRED_CLONE_IDS:
            exists = self.api.repo_exists(clone_id, repo_type="space")
            if not exists:
                snapshots[clone_id] = {"exists": False}
                self.record(clone_id, "clone-preflight", "ok", "already absent")
                continue
            info = self.api.space_info(clone_id)
            snapshot = {
                "exists": True,
                "sha": str(getattr(info, "sha", "") or ""),
                "private": getattr(info, "private", None),
                "stage": _runtime_stage(info),
            }
            snapshots[clone_id] = snapshot
            self.record(
                clone_id,
                "clone-preflight",
                "ok",
                "existing exact retired clone; "
                f"private={snapshot['private']}; stage={snapshot['stage']}; "
                f"sha={snapshot['sha']}",
            )
        return snapshots

    def _remove_clone_collection_references(self) -> None:
        summaries = list(self.api.list_collections(owner=legacy.ORG, limit=100))
        for summary in summaries:
            collection = self.api.get_collection(summary.slug)
            for item in collection.items:
                if item.item_type != "space" or item.item_id not in RETIRED_CLONE_IDS:
                    continue
                target = f"{collection.slug}:{item.item_id}"
                if not self.publish:
                    self.record(target, "collection-remove-clone", "dry-run")
                    continue
                self.api.delete_collection_item(
                    collection_slug=collection.slug,
                    item_object_id=item.item_object_id,
                    missing_ok=True,
                )
                self.record(target, "collection-remove-clone", "deleted")

    def create_or_refresh_clones(self) -> None:
        """Replace the legacy clone creator with exact clone retirement."""
        self.canonical_flagship = self._verify_canonical_flagship()
        self.retired_clone_snapshots = self._clone_snapshots()

        # Remove stale collection references before irreversible deletion.
        self._remove_clone_collection_references()

        for clone_id, snapshot in self.retired_clone_snapshots.items():
            if not snapshot["exists"]:
                continue
            if not self.publish:
                self.record(
                    clone_id,
                    "retire-flagship-clone",
                    "dry-run",
                    "would delete exact legacy private duplicate",
                )
                continue
            self.api.delete_repo(
                repo_id=clone_id,
                repo_type="space",
                missing_ok=True,
            )
            if self.api.repo_exists(clone_id, repo_type="space"):
                raise RuntimeError(f"Retired clone still exists after deletion: {clone_id}")
            self.record(
                clone_id,
                "retire-flagship-clone",
                "deleted",
                f"former_sha={snapshot.get('sha')}",
            )

        # The initial inventory was collected before retirement. Remove exact
        # retired IDs so collection curation and final counts cannot reintroduce
        # them or report them as live estate assets.
        self.inventory["spaces"] = [
            item
            for item in self.inventory.get("spaces", [])
            if self._asset_id(item) not in RETIRED_CLONE_IDS
        ]

    def report(self) -> dict[str, Any]:
        report = super().report()
        report.pop("clone_ids", None)
        report["canonical_flagship_space"] = getattr(
            self, "canonical_flagship", {"repo_id": legacy.FLAGSHIP_SPACE}
        )
        report["retired_clone_ids"] = list(RETIRED_CLONE_IDS)
        report["retired_clone_snapshots"] = getattr(
            self, "retired_clone_snapshots", {}
        )
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
            "SZLHOLDINGS/a11oy is the only canonical A11oy Space.",
            "Only the four exact allowlisted a11oy-clone-1..4 repositories may be deleted.",
            "Clone deletion requires a RUNNING public canonical Space at an immutable revision with Dockerfile present.",
            "No model weights or dataset payloads are changed.",
            "No paid hardware tier is changed.",
            "Healthy dynamic Spaces are not rewritten or restarted.",
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

    token = os.environ.get("HF_ORG_TOKEN") or os.environ.get("HF_TOKEN")
    if not token:
        print("FATAL: HF_ORG_TOKEN/HF_TOKEN is not set.", file=sys.stderr)
        return 2

    try:
        report = CanonicalEstateUpgrade(
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
