#!/usr/bin/env python3
"""Reconcile two narrow, evidence-backed Hugging Face collection truths.

The reconciler intentionally owns only two facts:

* the public command-system domain is ``https://a-11-oy.com``; and
* ``SZLHOLDINGS/szl-nemo`` is a recipe/scorer repository, not a trained SZL
  weight artifact, so it must not be listed in ``Trained Models & Weights``.

Dry-run is the default.  Publication is allowed only when ``--publish`` is
supplied by the protected merged-main workflow.  The script does not create,
rename, or delete a collection or repository and does not touch model files.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ORG = "SZLHOLDINGS"
START_TITLE = "Start Here — Alloy Estate"
TRAINED_TITLE = "Trained Models & Weights"
NEMO_REPO = "SZLHOLDINGS/szl-nemo"
START_DESCRIPTION = (
    "Public navigation only; each artifact card and live status is authoritative. "
    "Λ remains Conjecture 1 (advisory). Canonical site: https://a-11-oy.com."
)
REQUIRED_TRAINED_WEIGHTS = frozenset(
    {
        "SZLHOLDINGS/SZL-Forge-1.5B-ReceiptAgent",
        "SZLHOLDINGS/SZL-Khipu-1.5B",
        "SZLHOLDINGS/SZL-Khipu-1.5B-GGUF",
    }
)


def _hub_token_from_environment(environ: Any) -> str | None:
    """Select the approved Hub credential without relying on implicit aliases."""

    return (
        environ.get("HF_ORG_TOKEN")
        or environ.get("HF_ORG_TOKEN1")
        or environ.get("HF_TOKEN")
    )


class ReconcileError(RuntimeError):
    """The live collection state is ambiguous or failed verification."""


@dataclass(frozen=True)
class Action:
    target: str
    operation: str
    status: str
    detail: str


def _item_id(item: Any) -> str:
    return str(getattr(item, "item_id", ""))


def _item_object_id(item: Any) -> str:
    value = getattr(item, "item_object_id", None)
    if not value:
        raise ReconcileError(f"collection item {_item_id(item)!r} has no object id")
    return str(value)


class CollectionTruthReconciler:
    def __init__(self, api: Any, *, publish: bool) -> None:
        self.api = api
        self.publish = publish
        self.actions: list[Action] = []

    def _collections_by_title(self) -> dict[str, Any]:
        wanted = {START_TITLE, TRAINED_TITLE}
        found: dict[str, Any] = {}
        for summary in self.api.list_collections(owner=ORG, limit=99):
            title = str(getattr(summary, "title", ""))
            if title not in wanted:
                continue
            if title in found:
                raise ReconcileError(f"duplicate collection title: {title}")
            found[title] = self.api.get_collection(summary.slug)
        missing = sorted(wanted - found.keys())
        if missing:
            raise ReconcileError(f"required collections missing: {missing}")
        return found

    def _reconcile_start(self, collection: Any) -> None:
        current = str(getattr(collection, "description", "") or "")
        if current == START_DESCRIPTION:
            self.actions.append(
                Action(collection.slug, "update-description", "unchanged", START_DESCRIPTION)
            )
            return
        status = "published" if self.publish else "dry-run"
        self.actions.append(
            Action(collection.slug, "update-description", status, START_DESCRIPTION)
        )
        if self.publish:
            self.api.update_collection_metadata(
                collection_slug=collection.slug,
                description=START_DESCRIPTION,
            )

    def _reconcile_trained(self, collection: Any) -> None:
        item_ids = {_item_id(item) for item in collection.items}
        missing = sorted(REQUIRED_TRAINED_WEIGHTS - item_ids)
        if missing:
            raise ReconcileError(
                "refusing removal because expected trained-weight anchors are missing: "
                f"{missing}"
            )
        nemo = [item for item in collection.items if _item_id(item) == NEMO_REPO]
        if len(nemo) > 1:
            raise ReconcileError(f"duplicate {NEMO_REPO} entries in {collection.slug}")
        if not nemo:
            self.actions.append(
                Action(collection.slug, "remove-recipe-from-trained", "unchanged", NEMO_REPO)
            )
            return
        status = "published" if self.publish else "dry-run"
        self.actions.append(
            Action(collection.slug, "remove-recipe-from-trained", status, NEMO_REPO)
        )
        if self.publish:
            self.api.delete_collection_item(
                collection_slug=collection.slug,
                item_object_id=_item_object_id(nemo[0]),
            )

    def _verify(self) -> dict[str, Any]:
        collections = self._collections_by_title()
        start = collections[START_TITLE]
        trained = collections[TRAINED_TITLE]
        errors: list[str] = []
        if str(getattr(start, "description", "") or "") != START_DESCRIPTION:
            errors.append("Start Here description does not match the canonical domain")
        trained_ids = {_item_id(item) for item in trained.items}
        if NEMO_REPO in trained_ids:
            errors.append("recipe-only szl-nemo remains in Trained Models & Weights")
        missing = sorted(REQUIRED_TRAINED_WEIGHTS - trained_ids)
        if missing:
            errors.append(f"trained-weight anchors missing after reconcile: {missing}")
        return {
            "start_collection": start.slug,
            "trained_collection": trained.slug,
            "start_description": str(getattr(start, "description", "") or ""),
            "trained_items": sorted(trained_ids),
            "errors": errors,
        }

    def run(self) -> dict[str, Any]:
        collections = self._collections_by_title()
        self._reconcile_start(collections[START_TITLE])
        self._reconcile_trained(collections[TRAINED_TITLE])

        verification: dict[str, Any]
        if self.publish:
            verification = self._verify()
            if verification["errors"]:
                raise ReconcileError("; ".join(verification["errors"]))
        else:
            verification = {
                "status": "NOT_EVALUATED",
                "reason": "dry-run performs no mutation; protected merged-main publishes and reads back",
            }
        return {
            "schema": "szl.hf.collection-truth-reconcile.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "organization": ORG,
            "mode": "publish" if self.publish else "dry-run",
            "actions": [asdict(action) for action in self.actions],
            "verification": verification,
            "boundaries": [
                "No collection or repository is created, renamed, or deleted.",
                "No model, dataset, Space, kernel, or weight file is modified.",
                "Collection membership is not training, quality, or operational proof.",
            ],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument(
        "--report", default="reports/hf-collection-truth-reconcile-latest.json"
    )
    args = parser.parse_args()

    from huggingface_hub import HfApi

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        token = _hub_token_from_environment(os.environ)
        if args.publish and not token:
            raise ReconcileError(
                "publish mode requires HF_ORG_TOKEN, HF_ORG_TOKEN1, or HF_TOKEN"
            )
        report = CollectionTruthReconciler(
            HfApi(token=token), publish=args.publish
        ).run()
        exit_code = 0
    except Exception as exc:
        report = {
            "schema": "szl.hf.collection-truth-reconcile.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "organization": ORG,
            "mode": "publish" if args.publish else "dry-run",
            "error": f"{type(exc).__name__}: {exc}",
        }
        exit_code = 2
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
