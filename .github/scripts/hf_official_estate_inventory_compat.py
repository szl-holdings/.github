#!/usr/bin/env python3
"""Run the official estate inventory with current Kernel Hub compatibility.

`huggingface_hub` officially supports `kernel_info()` and repository readback for
kernel repositories, but it does not currently expose `HfApi.list_kernels()`.
Kernel discovery therefore uses the public authenticated Hub `/api/kernels`
endpoint and immediately reads every discovered repository back through the
supported `HfApi.kernel_info()` method. All other resource classes continue to
use the supported HfApi inventory methods in `hf_official_estate_inventory`.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import requests

import hf_official_estate_inventory as base
from hf_inventory_public_boundary import public_report

KERNEL_LIST_URL = f"https://huggingface.co/api/kernels?author={base.ORG}&limit=100"
MAX_KERNEL_PAGES = 10
MAX_KERNEL_ITEMS = 500
MAX_KERNEL_PAGE_BYTES = 2 * 1024 * 1024
MAX_KERNEL_FILES = 4096
KERNEL_ID = re.compile(r"SZLHOLDINGS/[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")


def _validate_kernel_url(url: str) -> None:
    if not isinstance(url, str) or len(url) > 8192 or any(ord(ch) <= 32 or ord(ch) == 127 for ch in url):
        raise ValueError("KERNEL_URL_REJECTED")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "huggingface.co"
            or parsed.path != "/api/kernels" or parsed.fragment):
        raise ValueError("KERNEL_URL_REJECTED")
    query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    names = [key for key, _ in query]
    if len(names) != len(set(names)) or set(names) - {"author", "limit", "cursor"}:
        raise ValueError("KERNEL_QUERY_REJECTED")
    for key, value in query:
        if key == "author" and value != base.ORG:
            raise ValueError("KERNEL_AUTHOR_REJECTED")
        if key == "limit" and (not value.isdigit() or not 1 <= int(value) <= 100):
            raise ValueError("KERNEL_LIMIT_REJECTED")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("KERNEL_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ValueError("KERNEL_NONFINITE_JSON")


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("KERNEL_NONFINITE_JSON")
    return result


def _next_link(header: str) -> str:
    if not isinstance(header, str) or len(header) > 8192:
        raise ValueError("KERNEL_LINK_BOUND_EXCEEDED")
    candidates: list[str] = []
    for part in str(header or "").split(","):
        if not part.strip() and not header:
            continue
        match = re.fullmatch(r'\s*<([^<>]+)>\s*;\s*rel\s*=\s*"([^"\r\n]+)"\s*', part)
        if match is None:
            raise ValueError("KERNEL_LINK_MALFORMED")
        if "next" not in match[2].lower().split():
            continue
        _validate_kernel_url(match[1])
        candidates.append(match[1])
    if len(candidates) > 1:
        raise ValueError("KERNEL_MULTIPLE_NEXT_LINKS")
    return candidates[0] if candidates else ""


class CurrentHubEstateInventory(base.OfficialEstateInventory):
    """Official inventory with REST discovery and HfApi kernel readback."""

    def record(self, target: str, action: str, status: str, detail: str = "") -> None:
        # Operator records stay in the private report, never public Actions logs.
        self.actions.append(base.Action(target, action, status, detail))

    def __init__(self, *, token: str, generation: str, publish: bool) -> None:
        super().__init__(token=token, generation=generation, publish=publish)
        self.http = requests.Session()
        self.http.trust_env = False
        self.http.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
                "User-Agent": "szl-hf-official-estate-inventory/2",
            }
        )

    def _list_kernel_summaries(self) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        url = KERNEL_LIST_URL
        pages = 0
        seen_urls: set[str] = set()
        seen_ids: set[str] = set()
        while url:
            _validate_kernel_url(url)  # Validate before sending the bearer token.
            if url in seen_urls:
                raise RuntimeError("KERNEL_PAGINATION_CYCLE")
            seen_urls.add(url)
            pages += 1
            if pages > MAX_KERNEL_PAGES:
                raise RuntimeError("KERNEL_PAGE_BOUND_EXCEEDED")
            try:
                response = self.http.get(url, timeout=(10, 15), allow_redirects=False, stream=True)
            except requests.RequestException:
                raise RuntimeError("KERNEL_HTTP_REQUEST_FAILED") from None
            try:
                if response.status_code != 200:
                    raise RuntimeError("KERNEL_HTTP_STATUS_REJECTED")
                chunks: list[bytes] = []
                size = 0
                started = time.monotonic()
                for chunk in response.iter_content(chunk_size=8192):
                    size += len(chunk)
                    if size > MAX_KERNEL_PAGE_BYTES:
                        raise RuntimeError("KERNEL_PAGE_BYTE_BOUND_EXCEEDED")
                    if time.monotonic() - started > 45:
                        raise RuntimeError("KERNEL_PAGE_TIME_BOUND_EXCEEDED")
                    chunks.append(chunk)
                payload = json.loads(b"".join(chunks), object_pairs_hook=_unique_object, parse_constant=_reject_constant, parse_float=_finite_float)
                next_url = _next_link(response.headers.get("Link") or response.headers.get("link") or "")
            finally:
                response.close()
            if isinstance(payload, dict) and isinstance(payload.get("items"), list):
                payload = payload["items"]
            if not isinstance(payload, list):
                raise TypeError("KERNEL_LIST_SHAPE_REJECTED")
            for item in payload:
                if not isinstance(item, dict):
                    raise TypeError("KERNEL_RECORD_SHAPE_REJECTED")
                repo_id = item.get("id")
                if not isinstance(repo_id, str) or not KERNEL_ID.fullmatch(repo_id):
                    raise ValueError("KERNEL_RECORD_ID_REJECTED")
                if repo_id in seen_ids:
                    raise ValueError("KERNEL_DUPLICATE_RECORD")
                seen_ids.add(repo_id)
                output.append(base._mapping(item))
                if len(output) > MAX_KERNEL_ITEMS:
                    raise RuntimeError("KERNEL_ITEM_BOUND_EXCEEDED")
            url = next_url
        return output

    def inventory_kernels(self) -> None:
        summaries = [
            item
            for item in self._list_kernel_summaries()
            if base._belongs_to_org(item)
        ]
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for summary in sorted(summaries, key=base._identifier):
            repo_id = base._identifier(summary)
            if not repo_id or repo_id in seen:
                continue
            seen.add(repo_id)
            info = self.api.kernel_info(repo_id, timeout=30)
            detail = base._mapping(info)
            if base._identifier(detail) != repo_id:
                raise RuntimeError("KERNEL_READBACK_ID_MISMATCH")
            merged = dict(summary)
            merged.update({key: value for key, value in detail.items() if value is not None})
            merged["id"] = repo_id
            revision = str(detail.get("sha") or "")
            if not base.SHA40.fullmatch(revision):
                raise RuntimeError("KERNEL_IMMUTABLE_REVISION_MISSING")
            files: set[str] = set()
            for path in self.api.list_repo_files(
                    repo_id,
                    repo_type="kernel",
                    revision=revision,
                ):
                if len(files) >= MAX_KERNEL_FILES:
                    raise RuntimeError("KERNEL_FILE_BOUND_EXCEEDED")
                if not isinstance(path, str) or path in files:
                    raise RuntimeError("KERNEL_FILE_RECORD_REJECTED")
                files.add(path)
            if "README.md" not in files:
                raise RuntimeError(f"kernel repository lacks README.md: {repo_id}")
            if not any(path.startswith("build/") for path in files):
                raise RuntimeError(f"kernel repository lacks build variants: {repo_id}")
            merged["file_count"] = len(files)
            merged["build_variants_present"] = True
            output.append(merged)
        self.inventory["kernels"] = output
        self.record(
            base.ORG,
            "inventory:kernels",
            "validated",
            (
                f"count={len(output)}; discovery=Hub REST /api/kernels; "
                "readback=HfApi.kernel_info+list_repo_files"
            ),
        )

    def inventory_repositories(self) -> None:
        self._inventory_kind("models", "list_models", author=base.ORG, full=True, limit=None)
        self._inventory_kind("datasets", "list_datasets", author=base.ORG, full=True, limit=None)
        self._inventory_kind("spaces", "list_spaces", author=base.ORG, full=True, limit=None)
        self.inventory_kernels()

    def report(self) -> dict[str, Any]:
        report = super().report()
        report["schema"] = "szl.hf-official-estate-inventory/v2"
        report["inventory_api"]["kernels"] = (
            "Official Hub REST /api/kernels discovery + "
            "HfApi.kernel_info + HfApi.list_repo_files readback"
        )
        report["boundaries"].append(
            "Kernel listing uses the official public Hub endpoint because the current "
            "huggingface_hub client supports kernel_info/readback but does not expose list_kernels."
        )
        for kind in ("models", "datasets", "spaces", "kernels", "collections", "buckets"):
            if kind not in self.inventory:
                report["counts"][kind] = None
        report["inventory_scope"] = "Authenticated visible namespace; not proof of ORG_COMPLETE or executable kernel compatibility."
        return report

    def persist(self, report: dict[str, Any]) -> None:
        if self.publish and self.api.dataset_info(base.EVIDENCE_DATASET).private is not True:
            raise RuntimeError("PRIVATE_EVIDENCE_DATASET_REQUIRED")
        super().persist(report)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--public-projection", type=Path, help="Project an existing operator report without network access.")
    parser.add_argument("--output", type=Path, default=Path("reports/hf-official-estate-inventory-public.json"))
    parser.add_argument(
        "--generation",
        default=os.environ.get("GITHUB_SHA") or "manual",
    )
    args = parser.parse_args()
    if args.public_projection:
        if args.public_projection.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("OPERATOR_REPORT_BOUND_EXCEEDED")
        raw = json.loads(args.public_projection.read_bytes(), object_pairs_hook=_unique_object, parse_constant=_reject_constant, parse_float=_finite_float)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(public_report(raw), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        return 0
    token = (
        os.environ.get("HF_ORG_TOKEN")
        or os.environ.get("HF_ORG_TOKEN1")
        or os.environ.get("HF_TOKEN")
    )
    if not token:
        print("FATAL: no supported Hugging Face credential is configured", file=sys.stderr)
        return 2

    try:
        report = CurrentHubEstateInventory(
            token=token,
            generation=args.generation,
            publish=args.publish,
        ).run()
    except Exception:  # noqa: BLE001
        Path("reports").mkdir(exist_ok=True)
        failure = {
            "schema": "szl.hf-official-estate-inventory/v2",
            "organization": base.ORG,
            "generation": args.generation,
            "publish": args.publish,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "error_class": "INVENTORY_FAILED",
            "fatal": "Authenticated inventory failed; private details withheld.",
            "summary": {"ok": 0, "warning": 0, "error": 1, "dry_run": 0},
        }
        Path("reports/hf-official-estate-inventory-latest.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print("FATAL: authenticated inventory failed; private details withheld", file=sys.stderr)
        return 2

    print(json.dumps({"state": "INVENTORY_COMPLETED", "scope": "OPERATOR_REPORT_WITHHELD"}))
    return 1 if report["summary"]["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
