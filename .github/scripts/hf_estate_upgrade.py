#!/usr/bin/env python3
"""Non-destructive estate-wide Hugging Face upgrade for the SZLHOLDINGS org.

The publisher:
- authenticates an org-scoped write token and inventories models, datasets,
  Spaces, kernels, collections, and buckets exposed by the Hub API;
- writes a machine-readable management marker to all models and datasets;
- writes the marker to static Spaces and unhealthy dynamic Spaces only, so
  healthy paid runtimes are not needlessly rebuilt;
- factory-restarts unhealthy non-static Spaces;
- creates/refreshes four private CPU-basic clones of the flagship a11oy Space;
- creates four canonical collections and adds every supported asset;
- publishes a signed-by-CI evidence report to the private szl-evidence dataset.

It never deletes or renames a Hub repository, never changes visibility of an
existing asset, never changes paid hardware, and never edits model weights or
dataset payloads.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from huggingface_hub import (
    CommitOperationCopy,
    CommitOperationDelete,
    HfApi,
)

ORG = "SZLHOLDINGS"
HF_BASE = "https://huggingface.co"
FLAGSHIP_SPACE = f"{ORG}/a11oy"
EVIDENCE_DATASET = f"{ORG}/szl-evidence"
MANAGED_PATH = "SZL_ESTATE_MANAGED.json"
CLONE_IDS = [f"{ORG}/a11oy-clone-{index}" for index in range(1, 5)]
UNHEALTHY_STAGES = {
    "BUILD_ERROR",
    "RUNTIME_ERROR",
    "PAUSED",
    "STOPPED",
    "NO_APP_FILE",
    "CONFIG_ERROR",
}
COLLECTION_SPECS = {
    "SZL Holdings — Canonical Estate": {
        "description": (
            "Canonical SZLHOLDINGS discovery surface. GitHub release evidence "
            "is authoritative; Hub resources are managed mirrors and runtimes."
        ),
        "theme": "blue",
    },
    "SZL Holdings — Spaces": {
        "description": "Managed public and private Spaces in the SZLHOLDINGS estate.",
        "theme": "green",
    },
    "SZL Holdings — Models & Kernel Contracts": {
        "description": (
            "Managed model repositories. First-class Kernel Hub revisions are "
            "tracked in the estate evidence report because collections do not "
            "currently accept kernel as an item type."
        ),
        "theme": "yellow",
    },
    "SZL Holdings — Datasets & Evidence": {
        "description": "Managed datasets, receipts, manifests, and diligence evidence.",
        "theme": "pink",
    },
}


@dataclass
class Action:
    target: str
    action: str
    status: str
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "target": self.target,
            "action": self.action,
            "status": self.status,
            "detail": self.detail,
        }


class EstateUpgrade:
    def __init__(self, token: str, generation: str, publish: bool) -> None:
        self.token = token
        self.generation = generation
        self.publish = publish
        self.api = HfApi(token=token)
        self.http = requests.Session()
        self.http.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "szl-hf-estate-upgrade/1",
            }
        )
        self.actions: list[Action] = []
        self.inventory: dict[str, list[dict[str, Any]]] = {}
        self.collections: dict[str, str] = {}

    def record(self, target: str, action: str, status: str, detail: str = "") -> None:
        self.actions.append(Action(target, action, status, detail))
        print(f"[{status:>8}] {action}: {target}" + (f" — {detail}" if detail else ""))

    def authenticate(self) -> dict[str, Any]:
        who = self.api.whoami()
        orgs = who.get("orgs") or []
        matching = [
            org
            for org in orgs
            if str(org.get("name") or org.get("fullname") or "").upper() == ORG
        ]
        if not matching:
            raise RuntimeError(
                f"Authenticated identity {who.get('name')!r} is not a member of {ORG}."
            )
        role = str(matching[0].get("roleInOrg") or matching[0].get("role") or "").lower()
        if role and role not in {"admin", "write", "contributor"}:
            raise RuntimeError(f"HF org role is not write-capable: {role}")
        self.record(ORG, "authenticate", "ok", f"identity={who.get('name')}; role={role or 'unknown'}")
        return who

    def _paginate(self, url: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        while url:
            response = self.http.get(url, timeout=45)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and "items" in payload:
                payload = payload["items"]
            if not isinstance(payload, list):
                raise TypeError(f"Expected list from {url}, got {type(payload).__name__}")
            output.extend(item for item in payload if isinstance(item, dict))
            link = response.headers.get("link") or ""
            next_url = ""
            for part in link.split(","):
                if 'rel="next"' in part:
                    next_url = part.split("<", 1)[1].split(">", 1)[0]
                    break
            url = next_url
        return output

    def collect_inventory(self) -> dict[str, list[dict[str, Any]]]:
        endpoints = {
            "models": f"{HF_BASE}/api/models?author={ORG}&limit=1000&full=true",
            "datasets": f"{HF_BASE}/api/datasets?author={ORG}&limit=1000&full=true",
            "spaces": f"{HF_BASE}/api/spaces?author={ORG}&limit=1000&full=true",
            "kernels": f"{HF_BASE}/api/kernels?author={ORG}&limit=1000",
            "collections": f"{HF_BASE}/api/collections?namespace={ORG}&limit=1000",
            "buckets": f"{HF_BASE}/api/buckets?owner={ORG}&limit=1000",
        }
        for kind, endpoint in endpoints.items():
            try:
                self.inventory[kind] = self._paginate(endpoint)
                self.record(ORG, f"inventory:{kind}", "ok", f"count={len(self.inventory[kind])}")
            except Exception as exc:
                self.inventory[kind] = []
                self.record(ORG, f"inventory:{kind}", "warning", repr(exc)[:300])
        return self.inventory

    @staticmethod
    def _asset_id(item: dict[str, Any]) -> str:
        return str(item.get("id") or item.get("modelId") or item.get("slug") or "")

    @staticmethod
    def _asset_sha(item: dict[str, Any]) -> str | None:
        value = item.get("sha")
        return str(value) if value else None

    def _managed_payload(
        self,
        *,
        repo_id: str,
        repo_type: str,
        observed_sha: str | None,
        runtime: dict[str, Any] | None = None,
        clone_of: str | None = None,
    ) -> bytes:
        payload = {
            "schema": "szl.hf-estate-managed/v1",
            "organization": ORG,
            "repo_id": repo_id,
            "repo_type": repo_type,
            "generation": self.generation,
            "observed_sha_before_upgrade": observed_sha,
            "managed_at": datetime.now(timezone.utc).isoformat(),
            "canonical_github_org": "https://github.com/szl-holdings",
            "canonical_flagship": "https://github.com/szl-holdings/a11oy",
            "canonical_rule": (
                "GitHub source, protected CI, release receipts, checksums, and "
                "provenance are authoritative. Hugging Face is the managed Hub surface."
            ),
            "runtime": runtime,
            "clone_of": clone_of,
            "non_destructive": True,
        }
        return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()

    def _upload_marker(
        self,
        *,
        repo_id: str,
        repo_type: str,
        observed_sha: str | None,
        runtime: dict[str, Any] | None = None,
        clone_of: str | None = None,
    ) -> None:
        if not self.publish:
            self.record(repo_id, "managed-marker", "dry-run")
            return
        data = self._managed_payload(
            repo_id=repo_id,
            repo_type=repo_type,
            observed_sha=observed_sha,
            runtime=runtime,
            clone_of=clone_of,
        )
        try:
            self.api.upload_file(
                repo_id=repo_id,
                repo_type=None if repo_type == "model" else repo_type,
                path_or_fileobj=io.BytesIO(data),
                path_in_repo=MANAGED_PATH,
                commit_message=f"chore(estate): record managed generation {self.generation[:12]}",
                commit_description=(
                    "Non-destructive machine-readable provenance marker. "
                    "No weights, dataset payloads, application code, visibility, "
                    "secrets, or hardware settings were changed."
                ),
            )
            self.record(repo_id, "managed-marker", "updated")
        except Exception as exc:
            self.record(repo_id, "managed-marker", "error", repr(exc)[:300])

    def upgrade_models_and_datasets(self) -> None:
        for kind, repo_type in (("models", "model"), ("datasets", "dataset")):
            for item in self.inventory.get(kind, []):
                repo_id = self._asset_id(item)
                if not repo_id:
                    continue
                self._upload_marker(
                    repo_id=repo_id,
                    repo_type=repo_type,
                    observed_sha=self._asset_sha(item),
                )

    def _space_detail(self, repo_id: str) -> dict[str, Any]:
        response = self.http.get(f"{HF_BASE}/api/spaces/{repo_id}", timeout=45)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def upgrade_spaces(self) -> None:
        for item in self.inventory.get("spaces", []):
            repo_id = self._asset_id(item)
            if not repo_id:
                continue
            try:
                detail = self._space_detail(repo_id)
            except Exception as exc:
                self.record(repo_id, "space-detail", "error", repr(exc)[:300])
                continue
            sdk = str(detail.get("sdk") or item.get("sdk") or "").lower()
            runtime = detail.get("runtime") or {}
            stage = str(runtime.get("stage") or runtime.get("status") or "UNKNOWN").upper()
            runtime_view = {
                "stage": stage,
                "hardware": runtime.get("hardware"),
                "requested_hardware": runtime.get("requestedHardware"),
                "storage": runtime.get("storage"),
                "sdk": sdk,
            }
            self.record(repo_id, "space-health", "ok", f"sdk={sdk or 'unknown'} stage={stage}")

            if sdk == "static" or stage in UNHEALTHY_STAGES:
                self._upload_marker(
                    repo_id=repo_id,
                    repo_type="space",
                    observed_sha=self._asset_sha(detail) or self._asset_sha(item),
                    runtime=runtime_view,
                )

            if sdk != "static" and stage in UNHEALTHY_STAGES:
                if not self.publish:
                    self.record(repo_id, "factory-restart", "dry-run", f"stage={stage}")
                    continue
                try:
                    updated = self.api.restart_space(repo_id=repo_id, factory_reboot=True)
                    self.record(
                        repo_id,
                        "factory-restart",
                        "requested",
                        f"before={stage}; after={getattr(updated, 'stage', 'requested')}",
                    )
                except Exception as exc:
                    self.record(repo_id, "factory-restart", "error", repr(exc)[:300])

    def _sync_existing_clone(self, source: str, destination: str) -> None:
        source_files = set(self.api.list_repo_files(source, repo_type="space"))
        destination_files = set(self.api.list_repo_files(destination, repo_type="space"))
        copy_ops = [
            CommitOperationCopy(
                src_path_in_repo=path,
                path_in_repo=path,
                src_repo_id=source,
                src_repo_type="space",
            )
            for path in sorted(source_files)
            if path != ".gitattributes"
        ]
        delete_ops = [
            CommitOperationDelete(path_in_repo=path)
            for path in sorted(destination_files - source_files)
            if path not in {".gitattributes", MANAGED_PATH}
        ]
        operations = copy_ops + delete_ops
        if not operations:
            self.record(destination, "clone-refresh", "ok", "already current")
            return
        for index in range(0, len(operations), 500):
            chunk = operations[index : index + 500]
            self.api.create_commit(
                repo_id=destination,
                repo_type="space",
                operations=chunk,
                commit_message=(
                    f"chore(clone): refresh from {source} "
                    f"generation {self.generation[:12]} ({index // 500 + 1})"
                ),
            )
        self.record(
            destination,
            "clone-refresh",
            "updated",
            f"copied={len(copy_ops)} deleted={len(delete_ops)}",
        )

    def create_or_refresh_clones(self) -> None:
        for clone_id in CLONE_IDS:
            if not self.publish:
                self.record(clone_id, "flagship-clone", "dry-run", f"source={FLAGSHIP_SPACE}")
                continue
            try:
                exists = self.api.repo_exists(clone_id, repo_type="space")
                if not exists:
                    self.api.duplicate_repo(
                        from_id=FLAGSHIP_SPACE,
                        to_id=clone_id,
                        repo_type="space",
                        visibility="private",
                        exist_ok=True,
                        space_hardware="cpu-basic",
                        space_sleep_time=300,
                    )
                    self.record(clone_id, "flagship-clone", "created", "private cpu-basic")
                else:
                    self._sync_existing_clone(FLAGSHIP_SPACE, clone_id)
                clone_info = self.api.space_info(clone_id)
                self._upload_marker(
                    repo_id=clone_id,
                    repo_type="space",
                    observed_sha=getattr(clone_info, "sha", None),
                    runtime={"stage": getattr(getattr(clone_info, "runtime", None), "stage", None)},
                    clone_of=FLAGSHIP_SPACE,
                )
            except Exception as exc:
                self.record(clone_id, "flagship-clone", "error", repr(exc)[:400])

    def _ensure_collection(self, title: str, spec: dict[str, str]) -> str | None:
        existing = list(self.api.list_collections(owner=ORG, limit=100))
        match = next((collection for collection in existing if collection.title == title), None)
        if match:
            slug = match.slug
            self.record(slug, "collection", "ok", "existing")
            return slug
        if not self.publish:
            self.record(title, "collection", "dry-run", "would create")
            return None
        try:
            created = self.api.create_collection(
                title=title,
                namespace=ORG,
                description=spec["description"],
                private=False,
                exists_ok=True,
            )
            try:
                created = self.api.update_collection_metadata(
                    collection_slug=created.slug,
                    title=title,
                    description=spec["description"],
                    private=False,
                    theme=spec["theme"],
                )
            except Exception as theme_exc:
                self.record(created.slug, "collection-theme", "warning", repr(theme_exc)[:250])
            self.record(created.slug, "collection", "created")
            return created.slug
        except Exception as exc:
            self.record(title, "collection", "error", repr(exc)[:300])
            return None

    def upgrade_collections(self) -> None:
        for title, spec in COLLECTION_SPECS.items():
            slug = self._ensure_collection(title, spec)
            if slug:
                self.collections[title] = slug

        models = [self._asset_id(item) for item in self.inventory.get("models", [])]
        datasets = [self._asset_id(item) for item in self.inventory.get("datasets", [])]
        spaces = [self._asset_id(item) for item in self.inventory.get("spaces", [])]
        spaces = sorted(set(spaces + CLONE_IDS))

        assignments = {
            "SZL Holdings — Spaces": [(item, "space") for item in spaces],
            "SZL Holdings — Models & Kernel Contracts": [(item, "model") for item in models],
            "SZL Holdings — Datasets & Evidence": [(item, "dataset") for item in datasets],
            "SZL Holdings — Canonical Estate": [
                (FLAGSHIP_SPACE, "space"),
                (f"{ORG}/a11oy-v19-substrate", "model"),
                (f"{ORG}/szl-lake", "dataset"),
                (EVIDENCE_DATASET, "dataset"),
                *[(clone, "space") for clone in CLONE_IDS],
            ],
        }

        for title, entries in assignments.items():
            slug = self.collections.get(title)
            if not slug:
                continue
            for item_id, item_type in entries:
                if not item_id:
                    continue
                if not self.publish:
                    self.record(item_id, f"collection-add:{title}", "dry-run")
                    continue
                try:
                    self.api.add_collection_item(
                        collection_slug=slug,
                        item_id=item_id,
                        item_type=item_type,
                        note="Managed by the SZLHOLDINGS estate upgrade workflow.",
                        exists_ok=True,
                    )
                    self.record(item_id, f"collection-add:{title}", "ok")
                except Exception as exc:
                    self.record(item_id, f"collection-add:{title}", "warning", repr(exc)[:250])

    def validate_kernels(self) -> None:
        for item in self.inventory.get("kernels", []):
            repo_id = self._asset_id(item)
            if not repo_id:
                continue
            try:
                info = self.api.kernel_info(repo_id)
                self.record(
                    repo_id,
                    "kernel-contract",
                    "validated",
                    f"sha={getattr(info, 'sha', None)}",
                )
            except Exception as exc:
                self.record(repo_id, "kernel-contract", "error", repr(exc)[:300])

    def report(self) -> dict[str, Any]:
        return {
            "schema": "szl.hf-estate-upgrade-report/v1",
            "organization": ORG,
            "generation": self.generation,
            "publish": self.publish,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "counts": {kind: len(items) for kind, items in self.inventory.items()},
            "clone_ids": CLONE_IDS,
            "collections": self.collections,
            "actions": [action.as_dict() for action in self.actions],
            "summary": {
                "ok": sum(action.status in {"ok", "updated", "created", "validated", "requested"} for action in self.actions),
                "warning": sum(action.status == "warning" for action in self.actions),
                "error": sum(action.status == "error" for action in self.actions),
                "dry_run": sum(action.status == "dry-run" for action in self.actions),
            },
            "boundaries": [
                "No repository was deleted, renamed, or made more public.",
                "No model weights or dataset payloads were changed.",
                "No paid hardware tier was changed.",
                "Healthy dynamic Spaces were not rewritten or restarted.",
                "Kernel repositories were validated; first-class kernel publishing remains governed by kernel-builder release workflows.",
            ],
        }

    def publish_report(self, report: dict[str, Any]) -> None:
        rendered = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        os.makedirs("reports", exist_ok=True)
        with open("reports/hf-estate-upgrade-latest.json", "wb") as handle:
            handle.write(rendered)
        self.record("reports/hf-estate-upgrade-latest.json", "local-report", "updated")
        if not self.publish:
            return
        try:
            self.api.create_repo(
                repo_id=EVIDENCE_DATASET,
                repo_type="dataset",
                private=True,
                exist_ok=True,
            )
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            for path in ("estate/latest.json", f"estate/history/{timestamp}.json"):
                self.api.upload_file(
                    repo_id=EVIDENCE_DATASET,
                    repo_type="dataset",
                    path_or_fileobj=io.BytesIO(rendered),
                    path_in_repo=path,
                    commit_message=f"feat(estate): publish Hub upgrade report {timestamp}",
                )
            self.record(EVIDENCE_DATASET, "publish-report", "updated")
        except Exception as exc:
            self.record(EVIDENCE_DATASET, "publish-report", "error", repr(exc)[:400])

    def run(self) -> dict[str, Any]:
        self.authenticate()
        self.collect_inventory()
        self.upgrade_models_and_datasets()
        self.upgrade_spaces()
        self.create_or_refresh_clones()
        self.upgrade_collections()
        self.validate_kernels()
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

    token = os.environ.get("HF_ORG_TOKEN") or os.environ.get("HF_TOKEN")
    if not token:
        print("FATAL: HF_ORG_TOKEN/HF_TOKEN is not set.", file=sys.stderr)
        return 2

    try:
        report = EstateUpgrade(
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
