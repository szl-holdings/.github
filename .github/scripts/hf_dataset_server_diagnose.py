#!/usr/bin/env python3
"""Collect read-only diagnostics for the published SZL Lake Dataset Viewer.

No Hub asset is mutated. The report binds the current immutable dataset revision,
required file set, remote Parquet readability, and the public Dataset Server
validity/splits/info/parquet/size/first-rows responses so a persistent Viewer
failure can be repaired at the correct layer.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pyarrow.parquet as pq
import requests
from huggingface_hub import HfApi, hf_hub_download

DATASET_ID = "SZLHOLDINGS/szl-lake"
CONFIG = "receipts"
SPLIT = "train"
BASE = "https://datasets-server.huggingface.co"
REQUIRED_FILES = (
    "README.md",
    "khipu/amaru_receipts.parquet",
    "khipu/sentra_receipts.parquet",
    "khipu/a11oy_receipts.parquet",
    "khipu/rosie_receipts.parquet",
    "khipu/killinchu_receipts.parquet",
    "khipu/EMPTY_CHAIN_MANIFEST.json",
)
PARQUET_FILES = tuple(path for path in REQUIRED_FILES if path.endswith(".parquet"))


def endpoint_urls() -> dict[str, str]:
    dataset = quote(DATASET_ID, safe="")
    config = quote(CONFIG, safe="")
    split = quote(SPLIT, safe="")
    return {
        "is_valid": f"{BASE}/is-valid?dataset={dataset}",
        "splits": f"{BASE}/splits?dataset={dataset}",
        "info": f"{BASE}/info?dataset={dataset}&config={config}",
        "parquet": f"{BASE}/parquet?dataset={dataset}",
        "size": f"{BASE}/size?dataset={dataset}&config={config}&split={split}",
        "first_rows": (
            f"{BASE}/first-rows?dataset={dataset}&config={config}&split={split}"
        ),
    }


def _bounded_payload(response: requests.Response) -> dict[str, Any]:
    text = response.text[:4000]
    try:
        payload = response.json()
    except ValueError:
        payload = None
    return {
        "http_status": response.status_code,
        "headers": {
            key: value
            for key, value in response.headers.items()
            if key.lower() in {
                "age",
                "cache-control",
                "cf-cache-status",
                "content-type",
                "date",
                "etag",
                "retry-after",
                "x-cache",
                "x-request-id",
            }
        },
        "json": payload if isinstance(payload, (dict, list)) else None,
        "text": text if payload is None else None,
    }


def query_dataset_server(session: requests.Session) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name, url in endpoint_urls().items():
        try:
            response = session.get(
                url,
                headers={
                    "Accept": "application/json",
                    "Cache-Control": "no-cache, no-store, max-age=0",
                    "Pragma": "no-cache",
                    "User-Agent": "szl-hf-dataset-server-diagnostic/1",
                },
                timeout=90,
            )
        except Exception as exc:  # noqa: BLE001
            output[name] = {
                "url": url,
                "transport_error": f"{type(exc).__name__}: {exc}",
            }
        else:
            output[name] = {"url": url, **_bounded_payload(response)}
    return output


def inspect_remote_parquets(api: HfApi, token: str, revision: str) -> dict[str, Any]:
    observations: dict[str, Any] = {}
    schemas: list[Any] = []
    for path in PARQUET_FILES:
        try:
            local = hf_hub_download(
                repo_id=DATASET_ID,
                repo_type="dataset",
                filename=path,
                revision=revision,
                token=token,
                force_download=True,
            )
            parquet = pq.ParquetFile(local)
            schema = parquet.schema_arrow
            schemas.append(schema)
            observations[path] = {
                "rows": parquet.metadata.num_rows,
                "row_groups": parquet.metadata.num_row_groups,
                "columns": schema.names,
                "schema": str(schema),
                "readable": True,
            }
        except Exception as exc:  # noqa: BLE001
            observations[path] = {
                "readable": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
    readable = [item for item in observations.values() if item.get("readable")]
    schema_equal = bool(schemas) and all(schema.equals(schemas[0]) for schema in schemas[1:])
    return {
        "files": observations,
        "all_readable": len(readable) == len(PARQUET_FILES),
        "schema_equal": schema_equal,
        "total_rows": sum(int(item.get("rows") or 0) for item in readable),
    }


def diagnose(*, token: str, generation: str) -> dict[str, Any]:
    api = HfApi(token=token)
    info = api.dataset_info(DATASET_ID)
    revision = str(getattr(info, "sha", "") or "")
    files = set(api.list_repo_files(DATASET_ID, repo_type="dataset", revision=revision))
    missing = sorted(set(REQUIRED_FILES) - files)
    parquets = inspect_remote_parquets(api, token, revision)
    endpoints = query_dataset_server(requests.Session())

    first_rows = endpoints.get("first_rows") or {}
    report = {
        "schema": "szl.hf-dataset-server-diagnostic/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation": generation,
        "dataset": DATASET_ID,
        "revision": revision,
        "private": getattr(info, "private", None),
        "downloads": getattr(info, "downloads", None),
        "likes": getattr(info, "likes", None),
        "remote_file_count": len(files),
        "required_files_missing": missing,
        "remote_parquets": parquets,
        "dataset_server": endpoints,
        "viewer_ready": (
            first_rows.get("http_status") == 200
            and isinstance(first_rows.get("json"), dict)
            and not first_rows["json"].get("error")
        ),
        "status": "PASS" if not missing and parquets["all_readable"] else "SOURCE_INVALID",
        "boundaries": [
            "This diagnostic performs no Hub mutation.",
            "Remote Parquet readability and schema equality do not substitute for Dataset Server materialization.",
            "The Viewer is PASS only when first-rows returns HTTP 200 with no error payload.",
        ],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation", required=True)
    parser.add_argument(
        "--output",
        default="reports/hf-dataset-server-diagnostic-latest.json",
    )
    args = parser.parse_args()
    token = (
        os.environ.get("HF_ORG_TOKEN")
        or os.environ.get("HF_ORG_TOKEN1")
        or os.environ.get("HF_TOKEN")
    )
    if not token:
        raise SystemExit("no supported Hugging Face credential is configured")
    report = diagnose(token=token, generation=args.generation)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
