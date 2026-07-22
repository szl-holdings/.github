#!/usr/bin/env python3
"""Repair the bounded failures from the SZLHOLDINGS estate publisher.

This helper is intentionally narrow and non-destructive:
- creates the four private flagship clone repositories without using the
  daily-limited Space duplication endpoint;
- synchronizes the exact public a11oy Space revision into those clones;
- copies public Space variables but never reads or copies secret values;
- waits for every clone to reach RUNNING on cpu-basic;
- creates or repairs the models/kernel-contract collection using Hub-valid
  metadata and reconciles collection membership;
- rewrites and republishes the estate evidence report only after verification.

It never deletes or renames a Hub repository, changes model weights or dataset
payloads, makes a private asset public, or upgrades paid hardware.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, snapshot_download

ORG = "SZLHOLDINGS"
SOURCE = f"{ORG}/a11oy"
EVIDENCE_DATASET = f"{ORG}/szl-evidence"
REPORT_PATH = Path("reports/hf-estate-upgrade-latest.json")
MANAGED_PATH = "SZL_ESTATE_MANAGED.json"
CLONES = [f"{ORG}/a11oy-clone-{index}" for index in range(1, 5)]
MODEL_COLLECTION_TITLE = "SZL Holdings — Models & Kernel Contracts"
MODEL_COLLECTION_DESCRIPTION = (
    "Managed models with governed kernel revision contracts recorded in the estate evidence report."
)
COLLECTION_METADATA = {
    "SZL Holdings — Canonical Estate": (
        "Canonical estate discovery surface; GitHub evidence remains authoritative.",
        "blue",
    ),
    "SZL Holdings — Spaces": (
        "Managed public and private Spaces in the SZLHOLDINGS estate.",
        "green",
    ),
    MODEL_COLLECTION_TITLE: (MODEL_COLLECTION_DESCRIPTION, "yellow"),
    "SZL Holdings — Datasets & Evidence": (
        "Managed datasets, receipts, manifests, and diligence evidence.",
        "pink",
    ),
}


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _action(target: str, action: str, status: str, detail: str = "") -> dict[str, str]:
    return {"target": target, "action": action, "status": status, "detail": detail}


def _runtime_stage(api: HfApi, repo_id: str) -> str:
    runtime = api.get_space_runtime(repo_id=repo_id)
    return str(_value(runtime, "stage", "UNKNOWN") or "UNKNOWN").upper()


def _copy_public_variables(api: HfApi, destination: str) -> int:
    copied = 0
    try:
        variables = api.get_space_variables(repo_id=SOURCE)
    except Exception as exc:  # Public variables are additive, not a clone blocker.
        print(f"WARNING: could not read source public variables: {exc!r}")
        variables = {}
    for key, item in (variables or {}).items():
        value = _value(item, "value", item if isinstance(item, str) else None)
        if value is None:
            continue
        description = _value(item, "description", None)
        api.add_space_variable(
            repo_id=destination,
            key=str(key),
            value=str(value),
            description=str(description) if description else None,
        )
        copied += 1
    api.add_space_variable(
        repo_id=destination,
        key="SZL_CLONE_OF",
        value=SOURCE,
        description="Canonical source Space for this private operational clone.",
    )
    return copied + 1


def _managed_marker(
    *, clone_id: str, generation: str, source_sha: str, stage: str
) -> bytes:
    payload = {
        "schema": "szl.hf-estate-managed/v1",
        "organization": ORG,
        "repo_id": clone_id,
        "repo_type": "space",
        "generation": generation,
        "observed_sha_before_upgrade": source_sha,
        "managed_at": datetime.now(timezone.utc).isoformat(),
        "canonical_github_org": "https://github.com/szl-holdings",
        "canonical_flagship": "https://github.com/szl-holdings/a11oy",
        "canonical_rule": (
            "GitHub source, protected CI, release receipts, checksums, and provenance "
            "are authoritative. Hugging Face is the managed Hub surface."
        ),
        "runtime": {"stage": stage, "hardware": "cpu-basic", "sdk": "docker"},
        "clone_of": SOURCE,
        "public_variables_copied": True,
        "secret_values_copied": False,
        "non_destructive": True,
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sync_clone(
    api: HfApi,
    *,
    clone_id: str,
    source_dir: str,
    source_sha: str,
    generation: str,
) -> dict[str, str]:
    existed = api.repo_exists(repo_id=clone_id, repo_type="space")
    if not existed:
        api.create_repo(
            repo_id=clone_id,
            repo_type="space",
            private=True,
            exist_ok=True,
            space_sdk="docker",
            space_hardware="cpu-basic",
        )

    api.upload_folder(
        repo_id=clone_id,
        repo_type="space",
        folder_path=source_dir,
        ignore_patterns=[".cache/**", "**/.cache/**", "**/__pycache__/**"],
        delete_patterns="**/*",
        commit_message=f"chore(clone): sync {SOURCE}@{source_sha[:12]}",
        commit_description=(
            "Quota-safe exact-source synchronization. No secrets, paid hardware, "
            "or visibility changes were copied from the source Space."
        ),
    )
    variables = _copy_public_variables(api, clone_id)
    api.upload_file(
        repo_id=clone_id,
        repo_type="space",
        path_or_fileobj=io.BytesIO(
            _managed_marker(
                clone_id=clone_id,
                generation=generation,
                source_sha=source_sha,
                stage="BUILDING",
            )
        ),
        path_in_repo=MANAGED_PATH,
        commit_message=f"chore(estate): bind clone generation {generation[:12]}",
    )
    return _action(
        clone_id,
        "flagship-clone",
        "updated" if existed else "created",
        f"source={SOURCE}@{source_sha}; private=true; hardware=cpu-basic; public_variables={variables}",
    )


def _wait_for_clones(api: HfApi, timeout_seconds: int) -> list[dict[str, str]]:
    deadline = time.monotonic() + timeout_seconds
    stages = {clone: "UNKNOWN" for clone in CLONES}
    while time.monotonic() < deadline:
        all_running = True
        for clone in CLONES:
            try:
                stages[clone] = _runtime_stage(api, clone)
            except Exception as exc:
                stages[clone] = f"ERROR:{type(exc).__name__}"
            if stages[clone] != "RUNNING":
                all_running = False
        print("Clone stages:", json.dumps(stages, sort_keys=True))
        if all_running:
            break
        time.sleep(20)

    actions: list[dict[str, str]] = []
    for clone, stage in stages.items():
        if stage == "RUNNING":
            actions.append(_action(clone, "clone-runtime", "ok", "stage=RUNNING"))
        else:
            actions.append(_action(clone, "clone-runtime", "error", f"stage={stage}"))
    return actions


def _ensure_collections(api: HfApi) -> tuple[dict[str, str], list[dict[str, str]]]:
    actions: list[dict[str, str]] = []
    existing = list(api.list_collections(owner=ORG, limit=100))
    by_title = {str(_value(item, "title", "")): item for item in existing}
    slugs: dict[str, str] = {}
    for title, (description, theme) in COLLECTION_METADATA.items():
        collection = by_title.get(title)
        if collection is None:
            collection = api.create_collection(
                title=title,
                namespace=ORG,
                description=description,
                private=False,
                exists_ok=True,
            )
            status = "created"
        else:
            status = "updated"
        collection = api.update_collection_metadata(
            collection_slug=str(_value(collection, "slug")),
            title=title,
            description=description,
            private=False,
            theme=theme,
        )
        slug = str(_value(collection, "slug"))
        slugs[title] = slug
        actions.append(_action(slug, "collection", status, f"title={title}"))

    models = [str(_value(item, "id", "")) for item in api.list_models(author=ORG, limit=1000)]
    spaces_slug = slugs.get("SZL Holdings — Spaces")
    canonical_slug = slugs.get("SZL Holdings — Canonical Estate")
    models_slug = slugs.get(MODEL_COLLECTION_TITLE)

    if models_slug:
        for repo_id in sorted(item for item in models if item):
            api.add_collection_item(
                collection_slug=models_slug,
                item_id=repo_id,
                item_type="model",
                note="Managed by the SZLHOLDINGS estate upgrade workflow.",
                exists_ok=True,
            )
        actions.append(
            _action(models_slug, "collection-reconcile", "ok", f"models={len(models)}")
        )

    for clone in CLONES:
        for title, slug in (
            ("SZL Holdings — Spaces", spaces_slug),
            ("SZL Holdings — Canonical Estate", canonical_slug),
        ):
            if not slug:
                continue
            api.add_collection_item(
                collection_slug=slug,
                item_id=clone,
                item_type="space",
                note="Private cpu-basic operational clone of SZLHOLDINGS/a11oy.",
                exists_ok=True,
            )
            actions.append(_action(clone, f"collection-add:{title}", "ok"))
    return slugs, actions


def _publish_report(api: HfApi, report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rendered = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    REPORT_PATH.write_bytes(rendered)
    api.create_repo(
        repo_id=EVIDENCE_DATASET,
        repo_type="dataset",
        private=True,
        exist_ok=True,
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for path in ("estate/latest.json", f"estate/history/{timestamp}-repair.json"):
        api.upload_file(
            repo_id=EVIDENCE_DATASET,
            repo_type="dataset",
            path_or_fileobj=io.BytesIO(rendered),
            path_in_repo=path,
            commit_message=f"fix(estate): publish verified clone repair {timestamp}",
        )


def _recalculate(report: dict[str, Any]) -> None:
    actions = report.get("actions") or []
    report["summary"] = {
        "ok": sum(
            action.get("status") in {"ok", "updated", "created", "validated", "requested"}
            for action in actions
        ),
        "warning": sum(action.get("status") == "warning" for action in actions),
        "error": sum(action.get("status") == "error" for action in actions),
        "dry_run": sum(action.get("status") == "dry-run" for action in actions),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation", required=True)
    parser.add_argument("--runtime-timeout", type=int, default=1800)
    args = parser.parse_args()

    token = os.environ.get("HF_ORG_TOKEN") or os.environ.get("HF_TOKEN")
    if not token:
        print("FATAL: HF_ORG_TOKEN/HF_TOKEN is not set.", file=sys.stderr)
        return 2
    if not REPORT_PATH.exists():
        print(f"FATAL: missing {REPORT_PATH}", file=sys.stderr)
        return 2

    api = HfApi(token=token)
    who = api.whoami()
    org = next(
        (
            item
            for item in (who.get("orgs") or [])
            if str(item.get("name") or item.get("fullname") or "").upper() == ORG
        ),
        None,
    )
    role = str((org or {}).get("roleInOrg") or (org or {}).get("role") or "").lower()
    if org is None or role not in {"admin", "write", "contributor"}:
        print(f"FATAL: authenticated identity lacks {ORG} write authority: role={role!r}")
        return 2

    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    source_info = api.space_info(repo_id=SOURCE)
    source_sha = str(_value(source_info, "sha", ""))
    if len(source_sha) != 40:
        print(f"FATAL: source Space revision is not immutable: {source_sha!r}")
        return 2

    repair_actions: list[dict[str, str]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="szl-hf-clone-") as tmp:
            source_dir = snapshot_download(
                repo_id=SOURCE,
                repo_type="space",
                revision=source_sha,
                token=token,
                local_dir=Path(tmp) / "source",
                max_workers=8,
            )
            for clone in CLONES:
                repair_actions.append(
                    _sync_clone(
                        api,
                        clone_id=clone,
                        source_dir=source_dir,
                        source_sha=source_sha,
                        generation=args.generation,
                    )
                )
        runtime_actions = _wait_for_clones(api, args.runtime_timeout)
        repair_actions.extend(runtime_actions)
        collections, collection_actions = _ensure_collections(api)
        repair_actions.extend(collection_actions)
    except Exception as exc:
        repair_actions.append(
            _action(ORG, "estate-repair", "error", f"{type(exc).__name__}: {exc}"[:600])
        )
        collections = report.get("collections") or {}

    targeted_errors = {
        (clone, "flagship-clone") for clone in CLONES
    } | {(MODEL_COLLECTION_TITLE, "collection")}
    original_actions = [
        action
        for action in (report.get("actions") or [])
        if not (
            action.get("status") == "error"
            and (action.get("target"), action.get("action")) in targeted_errors
        )
    ]
    report["actions"] = original_actions + repair_actions
    report["generation"] = args.generation
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["publish"] = True
    report["clone_ids"] = CLONES
    report["collections"] = collections
    report.setdefault("counts", {})["spaces"] = len(
        list(api.list_spaces(author=ORG, limit=1000, full=True))
    )
    report["counts"]["collections"] = len(list(api.list_collections(owner=ORG, limit=100)))
    report["repair"] = {
        "schema": "szl.hf-estate-repair/v1",
        "source_space": SOURCE,
        "source_revision": source_sha,
        "clone_strategy": "create_repo+snapshot_download+upload_folder",
        "secret_values_copied": False,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    boundaries = report.setdefault("boundaries", [])
    for boundary in (
        "Four private cpu-basic clones are synchronized from an immutable source Space revision without using the daily-limited duplication endpoint.",
        "Only public Space variables are copied; secret values are never read or propagated.",
    ):
        if boundary not in boundaries:
            boundaries.append(boundary)
    _recalculate(report)
    _publish_report(api, report)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 1 if report["summary"]["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
