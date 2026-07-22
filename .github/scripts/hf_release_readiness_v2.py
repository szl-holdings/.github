#!/usr/bin/env python3
"""Verify the current SZL Lake Viewer and first-class kernels without mutation.

This verifier is read-only for Hugging Face assets. It requires the current Lake
revision to expose the reviewed homogeneous receipts configuration, waits only
through bounded transient Dataset Server states, and runs ``selfcheck()`` on the
exact immutable revisions of both first-class kernels. The workflow that calls
this module supplies the CPU PyTorch 2.7.1 runtime required by the published
``torch27`` governed-norm build.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import requests

ORG = "SZLHOLDINGS"
DATASET_ID = f"{ORG}/szl-lake"
KERNEL_IDS = (
    f"{ORG}/governed-inference-meter",
    f"{ORG}/szl-governed-norm",
)
VIEWER_URL = (
    "https://datasets-server.huggingface.co/first-rows"
    "?dataset=SZLHOLDINGS%2Fszl-lake&config=receipts&split=train"
)
REQUIRED_DATASET_FILES = {
    "README.md",
    "khipu/amaru_receipts.parquet",
    "khipu/sentra_receipts.parquet",
    "khipu/a11oy_receipts.parquet",
    "khipu/rosie_receipts.parquet",
    "khipu/killinchu_receipts.parquet",
    "khipu/EMPTY_CHAIN_MANIFEST.json",
}
TRANSIENT_STATUSES = {408, 425, 429, 500, 502, 503, 504}
TRANSIENT_MARKERS = (
    "busy",
    "busier than usual",
    "not ready",
    "processing",
    "loading",
    "temporarily unavailable",
    "retry",
)


@dataclass(frozen=True)
class Action:
    target: str
    action: str
    status: str
    detail: str = ""


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if dataclasses.is_dataclass(value):
        return {key: json_safe(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def response_detail(response: Any) -> str:
    status = int(getattr(response, "status_code", 0) or 0)
    text = str(getattr(response, "text", "") or "")[:300]
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        payload = None
    if isinstance(payload, dict) and payload.get("error"):
        text = str(payload.get("error"))[:300]
    return f"HTTP {status}: {text}"


def is_transient_response(response: Any) -> bool:
    status = int(getattr(response, "status_code", 0) or 0)
    if status in TRANSIENT_STATUSES:
        return True
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        payload = None
    if status != 200 or not isinstance(payload, dict) or not payload.get("error"):
        return False
    lowered = str(payload.get("error") or "").lower()
    return any(marker in lowered for marker in TRANSIENT_MARKERS)


def wait_for_viewer(
    session: Any,
    *,
    attempts: int = 30,
    retry_seconds: float = 20.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Any, dict[str, Any], int]:
    """Return the first valid Viewer response or fail closed after a bound."""
    if attempts < 1:
        raise ValueError("attempts must be positive")
    if retry_seconds < 0:
        raise ValueError("retry_seconds must be non-negative")

    last_detail = "viewer was not queried"
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(
                VIEWER_URL,
                timeout=90,
                headers={
                    "Accept": "application/json",
                    "Cache-Control": "no-cache, no-store, max-age=0",
                    "Pragma": "no-cache",
                    "User-Agent": "szl-hf-release-readiness-v2/1",
                },
            )
        except requests.RequestException as exc:
            last_detail = f"{type(exc).__name__}: {exc}"
            transient = True
        else:
            status = int(getattr(response, "status_code", 0) or 0)
            if status == 200:
                try:
                    payload = response.json()
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        f"Dataset Viewer returned non-JSON HTTP 200: {exc}"
                    ) from exc
                if not isinstance(payload, dict):
                    raise RuntimeError("Dataset Viewer HTTP 200 payload is not an object")
                if not payload.get("error"):
                    return response, payload, attempt
            transient = is_transient_response(response)
            last_detail = response_detail(response)

        if not transient:
            raise RuntimeError(
                f"Dataset Viewer contract failed non-transiently: {last_detail}"
            )
        if attempt == attempts:
            break
        sleep(min(60.0, retry_seconds * attempt))

    raise RuntimeError(
        f"Dataset Viewer did not become ready after {attempts} attempts: {last_detail}"
    )


def default_kernel_loader(repo_id: str, revision: str) -> Any:
    from kernels import get_kernel

    return get_kernel(repo_id, revision=revision, trust_remote_code=True)


def verify_kernel(
    api: Any,
    repo_id: str,
    *,
    loader: Callable[[str, str], Any] = default_kernel_loader,
) -> dict[str, Any]:
    info = api.kernel_info(repo_id)
    revision = str(getattr(info, "sha", "") or "")
    if len(revision) != 40:
        raise RuntimeError(f"kernel lacks immutable revision: {repo_id}@{revision!r}")
    files = set(api.list_repo_files(repo_id, repo_type="kernel", revision=revision))
    missing = {"README.md", "contract.json"} - files
    if missing:
        raise RuntimeError(f"kernel contract is incomplete: {repo_id}: {sorted(missing)}")
    if not any(path.startswith("build/") for path in files):
        raise RuntimeError(f"kernel build variants are missing: {repo_id}")

    module = loader(repo_id, revision)
    check = getattr(module, "selfcheck", None)
    if not callable(check):
        raise RuntimeError(f"{repo_id}@{revision} does not expose selfcheck()")
    outcome = check()
    if outcome is False or (isinstance(outcome, dict) and outcome.get("ok") is False):
        raise RuntimeError(f"{repo_id}@{revision} selfcheck failed: {outcome}")
    return {
        "repo_id": repo_id,
        "revision": revision,
        "remote_file_count": len(files),
        "build_variants_present": True,
        "selfcheck": json_safe(outcome),
    }


class ReleaseReadinessVerifier:
    def __init__(
        self,
        *,
        token: str,
        generation: str,
        attempts: int,
        retry_seconds: float,
    ) -> None:
        from huggingface_hub import HfApi

        self.token = token
        self.generation = generation
        self.attempts = attempts
        self.retry_seconds = retry_seconds
        self.api = HfApi(token=token or None)
        self.actions: list[Action] = []
        self.results: dict[str, Any] = {}

    def record(self, target: str, action: str, status: str, detail: str = "") -> None:
        self.actions.append(Action(target, action, status, detail))
        print(f"[{status:>10}] {action}: {target}" + (f" — {detail}" if detail else ""))

    def authenticate(self) -> None:
        if not self.token:
            self.record(ORG, "authenticate", "warning", "public read-only mode")
            return
        who = self.api.whoami()
        match = next(
            (
                item
                for item in (who.get("orgs") or [])
                if str(item.get("name") or item.get("fullname") or "").upper() == ORG
            ),
            None,
        )
        if match is None:
            raise RuntimeError(f"authenticated identity is not a member of {ORG}")
        role = str(match.get("roleInOrg") or match.get("role") or "").lower()
        self.record(ORG, "authenticate", "validated", f"role={role or 'unknown'}")

    def verify_dataset(self) -> None:
        info = self.api.dataset_info(DATASET_ID)
        revision = str(getattr(info, "sha", "") or "")
        if len(revision) != 40:
            raise RuntimeError(f"dataset lacks immutable revision: {revision!r}")
        files = set(
            self.api.list_repo_files(DATASET_ID, repo_type="dataset", revision=revision)
        )
        missing = sorted(REQUIRED_DATASET_FILES - files)
        if missing:
            raise RuntimeError(f"published Lake revision is incomplete: {missing}")
        response, payload, attempts = wait_for_viewer(
            requests.Session(),
            attempts=self.attempts,
            retry_seconds=self.retry_seconds,
        )
        self.results["dataset"] = {
            "repo_id": DATASET_ID,
            "revision": revision,
            "viewer_http_status": int(response.status_code),
            "viewer_attempts": attempts,
            "remote_file_count": len(files),
            "viewer_payload_keys": sorted(payload.keys()),
        }
        self.record(
            DATASET_ID,
            "dataset-viewer-readiness",
            "validated",
            f"revision={revision}; HTTP=200; attempts={attempts}; files={len(files)}",
        )

    def verify_kernels(self) -> None:
        output: dict[str, Any] = {}
        for repo_id in KERNEL_IDS:
            result = verify_kernel(self.api, repo_id)
            output[repo_id] = result
            self.record(
                repo_id,
                "kernel-selfcheck",
                "validated",
                f"revision={result['revision']}; files={result['remote_file_count']}",
            )
        self.results["kernels"] = output

    def report(self) -> dict[str, Any]:
        statuses = [item.status for item in self.actions]
        return {
            "schema": "szl.hf-release-readiness/v2",
            "organization": ORG,
            "generation": self.generation,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "publish": False,
            "results": json_safe(self.results),
            "actions": [asdict(item) for item in self.actions],
            "summary": {
                "ok": sum(status == "validated" for status in statuses),
                "warning": sum(status == "warning" for status in statuses),
                "error": 0,
            },
            "boundaries": [
                "This verifier performs no Hugging Face asset mutation.",
                "Dataset success requires a final HTTP 200 JSON object without an error field.",
                "Kernel success requires exact immutable revisions, retained build variants, and selfcheck().",
                "PyTorch is supplied by the workflow runtime and is not published into a kernel repository.",
            ],
        }

    def run(self) -> dict[str, Any]:
        self.authenticate()
        self.verify_dataset()
        self.verify_kernels()
        return self.report()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        default="reports/hf-release-readiness-v2-latest.json",
    )
    parser.add_argument("--generation", default=os.environ.get("GITHUB_SHA") or "manual")
    parser.add_argument("--attempts", type=int, default=30)
    parser.add_argument("--retry-seconds", type=float, default=20.0)
    args = parser.parse_args()

    token = (
        os.environ.get("HF_ORG_TOKEN")
        or os.environ.get("HF_ORG_TOKEN1")
        or os.environ.get("HF_TOKEN")
        or ""
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = ReleaseReadinessVerifier(
            token=token,
            generation=args.generation,
            attempts=args.attempts,
            retry_seconds=args.retry_seconds,
        ).run()
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema": "szl.hf-release-readiness/v2",
            "organization": ORG,
            "generation": args.generation,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "publish": False,
            "fatal": f"{type(exc).__name__}: {exc}",
            "summary": {"ok": 0, "warning": 0, "error": 1},
        }
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 1

    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
