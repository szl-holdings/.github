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
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

import hf_official_estate_inventory as base

KERNEL_LIST_URL = f"https://huggingface.co/api/kernels?author={base.ORG}&limit=1000"


def _next_link(header: str) -> str:
    for part in str(header or "").split(","):
        if 'rel="next"' not in part:
            continue
        if "<" not in part or ">" not in part:
            continue
        return part.split("<", 1)[1].split(">", 1)[0]
    return ""


class CurrentHubEstateInventory(base.OfficialEstateInventory):
    """Official inventory with REST discovery and HfApi kernel readback."""

    def __init__(self, *, token: str, generation: str, publish: bool) -> None:
        super().__init__(token=token, generation=generation, publish=publish)
        self.http = requests.Session()
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
        while url:
            pages += 1
            if pages > 100:
                raise RuntimeError("kernel inventory exceeded 100 pagination pages")
            response = self.http.get(url, timeout=45)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and isinstance(payload.get("items"), list):
                payload = payload["items"]
            if not isinstance(payload, list):
                raise TypeError(
                    f"official Kernel Hub endpoint returned {type(payload).__name__}, expected list"
                )
            output.extend(
                base._mapping(item)
                for item in payload
                if isinstance(item, dict)
            )
            url = _next_link(response.headers.get("Link") or response.headers.get("link") or "")
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
            info = self.api.kernel_info(repo_id)
            detail = base._mapping(info)
            merged = dict(summary)
            merged.update({key: value for key, value in detail.items() if value is not None})
            merged["id"] = repo_id
            revision = str(merged.get("sha") or "")
            if not base.SHA40.fullmatch(revision):
                raise RuntimeError(f"kernel lacks immutable revision: {repo_id}@{revision!r}")
            files = set(
                self.api.list_repo_files(
                    repo_id,
                    repo_type="kernel",
                    revision=revision,
                )
            )
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
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument(
        "--generation",
        default=os.environ.get("GITHUB_SHA") or "manual",
    )
    args = parser.parse_args()
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
    except Exception as exc:  # noqa: BLE001
        Path("reports").mkdir(exist_ok=True)
        failure = {
            "schema": "szl.hf-official-estate-inventory/v2",
            "organization": base.ORG,
            "generation": args.generation,
            "publish": args.publish,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fatal": f"{type(exc).__name__}: {exc}",
            "summary": {"ok": 0, "warning": 0, "error": 1, "dry_run": 0},
        }
        Path("reports/hf-official-estate-inventory-latest.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 1 if report["summary"]["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
