#!/usr/bin/env python3
"""Publish and verify the exact Hugging Face estate green-light gates.

Uses supported huggingface_hub client methods for collections, buckets, repository
settings, Space hardware, repository synchronization, and runtime state. The
workflow is idempotent and preserves model weights and dataset payloads.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from huggingface_hub import HfApi, snapshot_download

HF_BASE = "https://huggingface.co"
HF_ORG = "SZLHOLDINGS"
GITHUB_API = "https://api.github.com"
CONTROL_REPOSITORY = "szl-holdings/.github"
ISSUE_TITLE = "[hf-estate-report] official API publish and verification"
USER_AGENT = "szl-hf-estate-greenlight-final/1.0"
COMMAND_CENTERS = (
    "SZLHOLDINGS/a11oy",
    "SZLHOLDINGS/a11oy-clone-1",
    "SZLHOLDINGS/a11oy-clone-2",
    "SZLHOLDINGS/a11oy-clone-3",
    "SZLHOLDINGS/a11oy-clone-4",
)
SHA_CHARS = set("0123456789abcdef")
TERMINAL_STAGES = {"RUNTIME_ERROR", "BUILD_ERROR", "CONFIG_ERROR", "DELETED", "PAUSED"}


class EstateError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def immutable_sha(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if len(text) == 40 and set(text) <= SHA_CHARS else None


def object_value(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, dict) and value.get(name) is not None:
            return value[name]
        candidate = getattr(value, name, None)
        if candidate is not None:
            return candidate
    return default


def supported_kwargs(callable_obj: Callable[..., Any], values: dict[str, Any]) -> dict[str, Any]:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return values
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return values
    return {key: value for key, value in values.items() if key in signature.parameters}


def call_first(callable_obj: Callable[..., Any], attempts: list[dict[str, Any]]) -> Any:
    failures: list[str] = []
    for attempt in attempts:
        kwargs = supported_kwargs(callable_obj, attempt)
        try:
            return callable_obj(**kwargs)
        except TypeError as exc:
            failures.append(f"{kwargs!r}: {exc}")
    raise EstateError(
        f"No supported invocation for {getattr(callable_obj, '__name__', callable_obj)!r}: "
        + " | ".join(failures)
    )


def call_iterable(callable_obj: Callable[..., Iterable[Any]], attempts: list[dict[str, Any]]) -> list[Any]:
    return list(call_first(callable_obj, attempts))


def hf_request(token: str, url: str) -> tuple[Any, dict[str, str]]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:5000]
        raise EstateError(f"Hugging Face API GET {url} failed HTTP {exc.code}: {detail}") from exc


def hf_paginate(token: str, url: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    while url:
        payload, headers = hf_request(token, url)
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            payload = payload["items"]
        if not isinstance(payload, list):
            raise EstateError(f"Hugging Face inventory returned non-list for {url}")
        output.extend(item for item in payload if isinstance(item, dict))
        link = str(headers.get("Link") or headers.get("link") or "")
        next_url = ""
        for part in link.split(","):
            if 'rel="next"' in part and "<" in part and ">" in part:
                next_url = part.split("<", 1)[1].split(">", 1)[0]
                break
        url = next_url
    return output


def inventory_id(item: Any) -> str:
    return str(
        object_value(
            item,
            "id",
            "repo_id",
            "modelId",
            "datasetId",
            "spaceId",
            "slug",
            "name",
            default="",
        )
        or ""
    )


def collection_slug(item: Any) -> str:
    return str(object_value(item, "slug", "id", default="") or "")


def bucket_identifier(item: Any) -> str:
    return str(object_value(item, "bucket_id", "id", "repo_id", "name", default="") or "")


def repo_file_map(api: HfApi, repo_id: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entry in api.list_repo_tree(repo_id, repo_type="space", recursive=True, expand=False):
        path = str(object_value(entry, "path", default="") or "")
        if not path:
            continue
        entry_type = str(object_value(entry, "type", default="file") or "file").lower()
        if entry_type in {"directory", "dir", "folder"}:
            continue
        lfs = object_value(entry, "lfs", default=None)
        identity = object_value(lfs, "sha256", default=None) or object_value(entry, "blob_id", "oid", default=None)
        if identity and path not in {".gitattributes", "SZL_ESTATE_MANAGED.json"}:
            mapping[path] = str(identity)
    return mapping


def stage(info: Any) -> str:
    runtime = object_value(info, "runtime", default=None)
    value = object_value(runtime, "stage", "status", default="UNKNOWN")
    value = getattr(value, "value", value)
    return str(value or "UNKNOWN").split(".")[-1].upper()


def hardware(info: Any) -> tuple[str, str]:
    runtime = object_value(info, "runtime", default=None)
    current = object_value(runtime, "hardware", "currentHardware", "current_hardware", default="")
    requested = object_value(runtime, "requestedHardware", "requested_hardware", default="")
    current = getattr(current, "value", current)
    requested = getattr(requested, "value", requested)
    return str(current or "").lower(), str(requested or "").lower()


def wait_space(api: HfApi, repo_id: str, timeout_seconds: int = 45 * 60) -> Any:
    deadline = time.monotonic() + timeout_seconds
    latest: Any = None
    while time.monotonic() < deadline:
        latest = api.space_info(repo_id)
        value = stage(latest)
        if value == "RUNNING":
            return latest
        if value in TERMINAL_STAGES:
            raise EstateError(f"{repo_id} entered terminal runtime stage {value}")
        time.sleep(20)
    raise EstateError(f"{repo_id} did not reach RUNNING; latest={stage(latest)}")


def set_public(api: HfApi, repo_id: str) -> None:
    method = getattr(api, "update_repo_settings", None)
    if not callable(method):
        raise EstateError("HfApi.update_repo_settings is unavailable")
    call_first(
        method,
        [
            {"repo_id": repo_id, "repo_type": "space", "private": False},
            {"repo_id": repo_id, "private": False, "repo_type": "space"},
        ],
    )


def request_cpu_basic(api: HfApi, repo_id: str) -> None:
    method = getattr(api, "request_space_hardware", None)
    if not callable(method):
        raise EstateError("HfApi.request_space_hardware is unavailable")
    call_first(
        method,
        [
            {"repo_id": repo_id, "hardware": "cpu-basic"},
            {"repo_id": repo_id, "hardware": "cpu-basic", "sleep_time": 0},
        ],
    )


def restart(api: HfApi, repo_id: str) -> None:
    method = getattr(api, "restart_space", None)
    if not callable(method):
        raise EstateError("HfApi.restart_space is unavailable")
    call_first(method, [{"repo_id": repo_id}, {"repo_id": repo_id, "factory_reboot": False}])


def sync_clone(api: HfApi, canonical_dir: str, repo_id: str) -> Any:
    set_public(api, repo_id)
    upload = getattr(api, "upload_folder", None)
    if not callable(upload):
        raise EstateError("HfApi.upload_folder is unavailable")
    call_first(
        upload,
        [
            {
                "repo_id": repo_id,
                "repo_type": "space",
                "folder_path": canonical_dir,
                "delete_patterns": ["*"],
                "commit_message": "Sync canonical A11oy command center for operational green-light",
            },
            {
                "repo_id": repo_id,
                "repo_type": "space",
                "folder_path": canonical_dir,
                "delete_patterns": "*",
                "commit_message": "Sync canonical A11oy command center for operational green-light",
            },
        ],
    )
    request_cpu_basic(api, repo_id)
    restart(api, repo_id)
    return wait_space(api, repo_id)


def command_centers(api: HfApi, publish: bool) -> dict[str, Any]:
    errors: list[str] = []
    actions: list[dict[str, Any]] = []
    canonical_id = COMMAND_CENTERS[0]
    canonical_info = api.space_info(canonical_id)
    canonical_files = repo_file_map(api, canonical_id)
    if not canonical_files:
        raise EstateError("canonical A11oy Space exposes no managed files")
    canonical_dir: str | None = None
    temp: tempfile.TemporaryDirectory[str] | None = None
    try:
        for repo_id in COMMAND_CENTERS[1:]:
            info = api.space_info(repo_id)
            files = repo_file_map(api, repo_id)
            current_hw, requested_hw = hardware(info)
            needs_sync = files != canonical_files
            needs_public = object_value(info, "private", default=None) is not False
            needs_cpu = "cpu-basic" not in {current_hw, requested_hw}
            needs_runtime = stage(info) != "RUNNING"
            if publish and (needs_sync or needs_public or needs_cpu or needs_runtime):
                if canonical_dir is None:
                    temp = tempfile.TemporaryDirectory(prefix="szl-hf-command-center-")
                    canonical_dir = snapshot_download(
                        repo_id=canonical_id,
                        repo_type="space",
                        local_dir=str(Path(temp.name) / "canonical"),
                    )
                    for cache in Path(canonical_dir).rglob(".cache"):
                        if cache.is_dir():
                            shutil.rmtree(cache, ignore_errors=True)
                before_sha = immutable_sha(object_value(info, "sha", default=None))
                info = sync_clone(api, canonical_dir, repo_id)
                files = repo_file_map(api, repo_id)
                actions.append(
                    {
                        "repo_id": repo_id,
                        "status": "updated",
                        "before_sha": before_sha,
                        "after_sha": immutable_sha(object_value(info, "sha", default=None)),
                        "reasons": {
                            "file_parity": needs_sync,
                            "visibility": needs_public,
                            "cpu_basic": needs_cpu,
                            "runtime": needs_runtime,
                        },
                    }
                )
            else:
                actions.append(
                    {
                        "repo_id": repo_id,
                        "status": "verified" if not (needs_sync or needs_public or needs_cpu or needs_runtime) else "open",
                        "reasons": {
                            "file_parity": needs_sync,
                            "visibility": needs_public,
                            "cpu_basic": needs_cpu,
                            "runtime": needs_runtime,
                        },
                    }
                )
        snapshots: dict[str, Any] = {}
        canonical_files = repo_file_map(api, canonical_id)
        for repo_id in COMMAND_CENTERS:
            info = wait_space(api, repo_id) if publish else api.space_info(repo_id)
            files = repo_file_map(api, repo_id)
            current_hw, requested_hw = hardware(info)
            snapshot = {
                "sha": immutable_sha(object_value(info, "sha", default=None)),
                "stage": stage(info),
                "private": object_value(info, "private", default=None),
                "hardware": current_hw,
                "requested_hardware": requested_hw,
                "managed_file_count": len(files),
                "file_parity": files == canonical_files,
            }
            snapshots[repo_id] = snapshot
            if not snapshot["sha"]:
                errors.append(f"{repo_id} lacks immutable revision")
            if snapshot["stage"] != "RUNNING":
                errors.append(f"{repo_id} stage={snapshot['stage']}")
            if snapshot["private"] is not False:
                errors.append(f"{repo_id} is not public")
            if not snapshot["file_parity"]:
                errors.append(f"{repo_id} differs from canonical managed files")
            if repo_id != canonical_id and "cpu-basic" not in {current_hw, requested_hw}:
                errors.append(f"{repo_id} is not confirmed CPU basic")
        return {"ok": not errors, "snapshots": snapshots, "actions": actions, "errors": errors}
    finally:
        if temp is not None:
            temp.cleanup()


def repo_exists(api: HfApi, item_type: str, item_id: str) -> bool:
    if item_type == "model":
        return bool(api.repo_exists(item_id, repo_type=None))
    if item_type in {"dataset", "space"}:
        return bool(api.repo_exists(item_id, repo_type=item_type))
    if item_type in {"paper", "papers"}:
        url = f"{HF_BASE}/papers/{urllib.parse.quote(item_id, safe='') }"
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return 200 <= int(response.status) < 400
        except Exception:  # noqa: BLE001
            return False
    return False


def collections(api: HfApi) -> dict[str, Any]:
    method = getattr(api, "list_collections", None)
    if not callable(method):
        return {"ok": False, "count": 0, "references": {"total": 0, "resolving": 0}, "collections": {}, "errors": ["HfApi.list_collections unavailable"]}
    summaries = call_iterable(
        method,
        [
            {"owner": HF_ORG, "limit": 1000},
            {"owner": HF_ORG, "limit": 100},
            {"owner": HF_ORG},
        ],
    )
    output: dict[str, Any] = {}
    errors: list[str] = []
    total = 0
    resolving = 0
    for summary in summaries:
        slug = collection_slug(summary)
        if not slug:
            errors.append("collection summary lacks slug")
            continue
        try:
            collection = api.get_collection(slug)
            refs: list[dict[str, Any]] = []
            for item in list(object_value(collection, "items", default=[]) or []):
                item_type = str(object_value(item, "item_type", "type", default="") or "").lower()
                item_id = str(object_value(item, "item_id", "repo_id", "id", default="") or "")
                if not item_type or not item_id:
                    raise EstateError(f"malformed collection item {item!r}")
                total += 1
                exists = repo_exists(api, item_type, item_id)
                if exists:
                    resolving += 1
                else:
                    errors.append(f"{slug} references missing {item_type} {item_id}")
                refs.append({"item_type": item_type, "item_id": item_id, "resolves": exists})
            output[slug] = {
                "title": object_value(collection, "title", default=None),
                "private": object_value(collection, "private", default=None),
                "items": refs,
            }
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{slug}: {type(exc).__name__}: {exc}")
    return {
        "ok": not errors and total == resolving,
        "count": len(output),
        "references": {"total": total, "resolving": resolving},
        "collections": output,
        "errors": errors,
    }


def bucket_tree(api: HfApi, bucket_id: str) -> list[Any]:
    for name in ("list_bucket_tree", "list_bucket_files"):
        method = getattr(api, name, None)
        if not callable(method):
            continue
        return call_iterable(
            method,
            [
                {"bucket_id": bucket_id, "recursive": True, "expand": True},
                {"bucket_id": bucket_id, "recursive": True},
                {"bucket_id": bucket_id},
                {"repo_id": bucket_id, "recursive": True, "expand": True},
                {"repo_id": bucket_id, "recursive": True},
                {"repo_id": bucket_id},
            ],
        )
    raise EstateError("HfApi exposes no supported bucket tree method")


def buckets(api: HfApi) -> dict[str, Any]:
    list_method = getattr(api, "list_buckets", None)
    info_method = getattr(api, "bucket_info", None)
    if not callable(list_method) or not callable(info_method):
        return {"ok": False, "count": 0, "buckets": {}, "errors": ["Supported bucket client methods are unavailable"]}
    values = call_iterable(
        list_method,
        [{"owner": HF_ORG}, {"namespace": HF_ORG}, {}],
    )
    summaries = []
    for item in values:
        owner = str(object_value(item, "owner", "namespace", default="") or "")
        bucket_id = bucket_identifier(item)
        if owner and owner.upper() != HF_ORG:
            continue
        if not owner and "/" in bucket_id and bucket_id.split("/", 1)[0].upper() != HF_ORG:
            continue
        summaries.append(item)
    output: dict[str, Any] = {}
    errors: list[str] = []
    for summary in summaries:
        bucket_id = bucket_identifier(summary)
        if not bucket_id:
            errors.append("bucket summary lacks identifier")
            continue
        try:
            info = call_first(
                info_method,
                [{"bucket_id": bucket_id}, {"repo_id": bucket_id}, {"name": bucket_id}],
            )
            files = 0
            size = 0
            for entry in bucket_tree(api, bucket_id):
                entry_type = str(object_value(entry, "type", "kind", default="file") or "file").lower()
                if entry_type in {"directory", "dir", "folder"}:
                    continue
                files += 1
                try:
                    size += int(object_value(entry, "size", default=0) or 0)
                except (TypeError, ValueError):
                    pass
            output[bucket_id] = {
                "private": object_value(info, "private", default=object_value(summary, "private", default=None)),
                "files": files,
                "bytes": size,
                "created_at": str(object_value(info, "created_at", "createdAt", default="") or ""),
                "updated_at": str(object_value(info, "updated_at", "updatedAt", default="") or ""),
            }
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{bucket_id}: {type(exc).__name__}: {exc}")
    return {"ok": not errors, "count": len(output), "buckets": output, "errors": errors}


def github_request(token: str, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        GITHUB_API + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:5000]
        raise EstateError(f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}") from exc
    return json.loads(raw.decode("utf-8")) if raw else None


def issues(token: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for page in range(1, 11):
        payload = github_request(
            token,
            "GET",
            f"/repos/{CONTROL_REPOSITORY}/issues?state=all&sort=updated&direction=desc&per_page=100&page={page}",
        )
        if not isinstance(payload, list):
            raise EstateError("GitHub issues payload is not a list")
        output.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return output
    raise EstateError("GitHub issue pagination exceeded ten pages")


def upsert_issue(token: str, report: dict[str, Any]) -> dict[str, Any]:
    body = (
        "<!-- szl-hf-estate-greenlight-final -->\n"
        "# Hugging Face estate — official API publish and verification\n\n"
        "```json\n"
        + json.dumps(report, indent=2, sort_keys=True)
        + "\n```\n"
    )
    current = next(
        (
            issue
            for issue in issues(token)
            if not issue.get("pull_request") and str(issue.get("title") or "") == ISSUE_TITLE
        ),
        None,
    )
    if current:
        issue = github_request(
            token,
            "PATCH",
            f"/repos/{CONTROL_REPOSITORY}/issues/{current['number']}",
            {"body": body, "state": "closed" if report.get("ok") else "open"},
        )
    else:
        issue = github_request(
            token,
            "POST",
            f"/repos/{CONTROL_REPOSITORY}/issues",
            {"title": ISSUE_TITLE, "body": body},
        )
        if report.get("ok"):
            issue = github_request(
                token,
                "PATCH",
                f"/repos/{CONTROL_REPOSITORY}/issues/{issue['number']}",
                {"state": "closed"},
            )
    return {"number": issue.get("number"), "url": issue.get("html_url"), "state": issue.get("state")}


def run(hf_token: str, github_token: str, publish: bool) -> dict[str, Any]:
    api = HfApi(token=hf_token)
    identity = api.whoami()
    inventory = {
        "models": hf_paginate(hf_token, f"{HF_BASE}/api/models?author={HF_ORG}&limit=1000&full=true"),
        "datasets": hf_paginate(hf_token, f"{HF_BASE}/api/datasets?author={HF_ORG}&limit=1000&full=true"),
        "spaces": hf_paginate(hf_token, f"{HF_BASE}/api/spaces?author={HF_ORG}&limit=1000&full=true"),
        "kernels": hf_paginate(hf_token, f"{HF_BASE}/api/kernels?author={HF_ORG}&limit=1000"),
    }
    command_center_report = command_centers(api, publish)
    collection_report = collections(api)
    bucket_report = buckets(api)
    errors = [
        *command_center_report.get("errors", []),
        *collection_report.get("errors", []),
        *bucket_report.get("errors", []),
    ]
    report = {
        "schema": "szl.hf-estate-official-api-greenlight/v1",
        "generated_at": now(),
        "organization": HF_ORG,
        "identity": identity.get("name") if isinstance(identity, dict) else str(identity),
        "publish": publish,
        "counts": {key: len(value) for key, value in inventory.items()},
        "command_centers": command_center_report,
        "collections": collection_report,
        "buckets": bucket_report,
        "summary": {
            "error": len(errors),
            "errors": errors,
            "models": len(inventory["models"]),
            "datasets": len(inventory["datasets"]),
            "spaces": len(inventory["spaces"]),
            "kernels": len(inventory["kernels"]),
            "collections": collection_report.get("count", 0),
            "buckets": bucket_report.get("count", 0),
            "command_centers_verified": sum(
                1
                for item in (command_center_report.get("snapshots") or {}).values()
                if item.get("stage") == "RUNNING" and item.get("private") is False and item.get("file_parity")
            ),
        },
        "ok": publish and not errors and command_center_report.get("ok") and collection_report.get("ok") and bucket_report.get("ok"),
        "boundaries": [
            "No model weights or dataset payloads are modified.",
            "Only the four managed command-center clones may be synchronized to the canonical A11oy Space.",
            "CPU-basic is requested for clones; no paid hardware tier is requested.",
            "Every collection reference and bucket tree is verified through supported client methods.",
        ],
    }
    report["durable_issue"] = upsert_issue(github_token, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    hf_token = (
        os.environ.get("HF_ORG_TOKEN", "").strip()
        or os.environ.get("HF_ORG_TOKEN1", "").strip()
        or os.environ.get("HF_TOKEN", "").strip()
    )
    github_token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    code = 0
    try:
        if not hf_token:
            raise EstateError("HF_ORG_TOKEN/HF_ORG_TOKEN1/HF_TOKEN is not configured")
        if not github_token:
            raise EstateError("SZL_GITHUB_TOKEN is not configured")
        report = run(hf_token, github_token, args.publish)
        if not report.get("ok"):
            code = 1
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema": "szl.hf-estate-official-api-greenlight/v1",
            "generated_at": now(),
            "organization": HF_ORG,
            "publish": bool(args.publish),
            "ok": False,
            "summary": {"error": 1, "errors": [f"{type(exc).__name__}: {exc}"]},
        }
        if github_token:
            try:
                report["durable_issue"] = upsert_issue(github_token, report)
            except Exception as issue_exc:  # noqa: BLE001
                report["summary"]["errors"].append(f"issue persistence: {type(issue_exc).__name__}: {issue_exc}")
        code = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report.get("ok"), "summary": report.get("summary")}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
