#!/usr/bin/env python3
"""Publish a bounded immutable deployment receipt to all A11oy command centers."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi

HF_ORG = "SZLHOLDINGS"
COMMAND_CENTERS = (
    "SZLHOLDINGS/a11oy",
    "SZLHOLDINGS/a11oy-clone-1",
    "SZLHOLDINGS/a11oy-clone-2",
    "SZLHOLDINGS/a11oy-clone-3",
    "SZLHOLDINGS/a11oy-clone-4",
)
RECEIPT_PATHS = (
    "deployment-receipt.json",
    "api/deployment-receipt.json",
    "static/deployment-receipt.json",
)
PROBE_ORIGINS = (
    "https://szlholdings-a11oy.hf.space",
    "https://a-11-oy.com",
)
USER_AGENT = "szl-hf-domain-receipt-publisher/1.0"
MAX_BODY = 1024 * 1024
SHA_CHARS = set("0123456789abcdef")


class ReceiptError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def immutable_sha(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if len(text) == 40 and set(text) <= SHA_CHARS else None


def public_get(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/plain;q=0.9, text/html;q=0.5",
            "Cache-Control": "no-cache",
            "User-Agent": USER_AGENT,
        },
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=60, context=ssl.create_default_context()) as response:
            body = response.read(MAX_BODY)
            content_type = str(response.headers.get("Content-Type") or "")
            payload: Any = None
            if body and ("json" in content_type.lower() or body.lstrip()[:1] in {b"{", b"["}):
                try:
                    payload = json.loads(body.decode("utf-8", "replace"))
                except json.JSONDecodeError:
                    payload = None
            return {
                "ok": 200 <= int(response.status) < 400,
                "status": int(response.status),
                "url": response.geturl(),
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "content_type": content_type,
                "json": payload,
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": int(exc.code),
            "url": url,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "content_type": str(exc.headers.get("Content-Type") or ""),
            "json": None,
            "error": f"HTTPError: {exc.code}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": 0,
            "url": url,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "content_type": "",
            "json": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def revision_from_payload(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(marker in normalized for marker in ("revision", "sha", "commit")):
                sha = immutable_sha(child)
                if sha:
                    return sha
            nested = revision_from_payload(child)
            if nested:
                return nested
    elif isinstance(value, list):
        for child in value:
            nested = revision_from_payload(child)
            if nested:
                return nested
    return None


def wait_running(api: HfApi, repo_id: str, timeout_seconds: int = 45 * 60) -> Any:
    deadline = time.monotonic() + timeout_seconds
    latest: Any = None
    while time.monotonic() < deadline:
        latest = api.space_info(repo_id)
        runtime = getattr(latest, "runtime", None)
        raw = getattr(runtime, "stage", None) or getattr(runtime, "status", None) or "UNKNOWN"
        raw = getattr(raw, "value", raw)
        stage = str(raw).split(".")[-1].upper()
        if stage == "RUNNING":
            return latest
        if stage in {"RUNTIME_ERROR", "BUILD_ERROR", "CONFIG_ERROR", "DELETED"}:
            raise ReceiptError(f"{repo_id} entered terminal stage {stage}")
        time.sleep(20)
    raise ReceiptError(f"{repo_id} did not reach RUNNING")


def upload(api: HfApi, repo_id: str, local_path: str, path_in_repo: str) -> Any:
    return api.upload_file(
        repo_id=repo_id,
        repo_type="space",
        path_or_fileobj=local_path,
        path_in_repo=path_in_repo,
        commit_message="Publish immutable public deployment receipt",
    )


def run(api: HfApi) -> dict[str, Any]:
    before: dict[str, str] = {}
    for repo_id in COMMAND_CENTERS:
        info = api.space_info(repo_id)
        sha = immutable_sha(getattr(info, "sha", None))
        if not sha:
            raise ReceiptError(f"{repo_id} lacks immutable source revision")
        before[repo_id] = sha
    canonical_revision = before[COMMAND_CENTERS[0]]
    receipt = {
        "schema": "szl.a11oy-public-deployment-receipt/v1",
        "generated_at": now(),
        "source_authority": COMMAND_CENTERS[0],
        "source_revision": canonical_revision,
        "command_centers": [
            {"repo_id": repo_id, "observed_pre_publish_revision": before[repo_id]}
            for repo_id in COMMAND_CENTERS
        ],
        "public_origins": list(PROBE_ORIGINS),
        "verification_boundary": "The source_revision is the immutable canonical Space revision observed immediately before this bounded receipt-only publication.",
    }
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    receipt["content_sha256"] = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    actions: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="szl-domain-receipt-") as temporary:
        path = Path(temporary) / "deployment-receipt.json"
        path.write_text(rendered, encoding="utf-8")
        for repo_id in COMMAND_CENTERS:
            for path_in_repo in RECEIPT_PATHS:
                result = upload(api, repo_id, str(path), path_in_repo)
                actions.append(
                    {
                        "repo_id": repo_id,
                        "path": path_in_repo,
                        "commit": str(result),
                    }
                )
            api.restart_space(repo_id)
        post: dict[str, Any] = {}
        for repo_id in COMMAND_CENTERS:
            info = wait_running(api, repo_id)
            post[repo_id] = {
                "revision": immutable_sha(getattr(info, "sha", None)),
                "stage": "RUNNING",
                "private": getattr(info, "private", None),
            }

    deadline = time.monotonic() + 45 * 60
    probes: dict[str, Any] = {}
    while time.monotonic() < deadline:
        probes = {}
        all_origins = True
        for origin in PROBE_ORIGINS:
            attempts: list[dict[str, Any]] = []
            verified = False
            for path in ("/deployment-receipt.json", "/api/deployment-receipt.json", "/static/deployment-receipt.json"):
                probe = public_get(origin + path)
                revision = revision_from_payload(probe.get("json"))
                attempts.append({"path": path, "probe": probe, "revision": revision})
                if probe.get("ok") and revision == canonical_revision:
                    verified = True
                    break
            probes[origin] = {"ok": verified, "attempts": attempts}
            all_origins = all_origins and verified
        if all_origins:
            break
        time.sleep(30)
    errors = [origin for origin, value in probes.items() if not value.get("ok")]
    return {
        "schema": "szl.a11oy-public-deployment-receipt-publication/v1",
        "generated_at": now(),
        "publish": True,
        "receipt": receipt,
        "actions": actions,
        "post_publish_spaces": post,
        "public_probes": probes,
        "ok": not errors,
        "errors": [f"receipt not served by {origin}" for origin in errors],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    token = (
        os.environ.get("HF_ORG_TOKEN", "").strip()
        or os.environ.get("HF_ORG_TOKEN1", "").strip()
        or os.environ.get("HF_TOKEN", "").strip()
    )
    code = 0
    try:
        if not token:
            raise ReceiptError("HF_ORG_TOKEN/HF_ORG_TOKEN1/HF_TOKEN is not configured")
        report = run(HfApi(token=token))
        if not report.get("ok"):
            code = 1
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema": "szl.a11oy-public-deployment-receipt-publication/v1",
            "generated_at": now(),
            "publish": True,
            "ok": False,
            "errors": [f"{type(exc).__name__}: {exc}"],
        }
        code = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report.get("ok"), "errors": report.get("errors")}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
