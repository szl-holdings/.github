#!/usr/bin/env python3
"""Verify the published Lake viewer and first-class kernels without rewriting them.

The release publisher has already written and read back the reviewed dataset and
kernel card bytes. Hugging Face's Dataset Viewer is asynchronous and can return a
bounded "busier than usual / not ready yet" response while it prepares a fresh
revision. This verifier retries only that transient readiness class. Unknown
viewer errors, malformed payloads, missing immutable revisions, and failed kernel
selfchecks remain terminal.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import requests
from huggingface_hub import HfApi

ORG = "SZLHOLDINGS"
DATASET_ID = f"{ORG}/szl-lake"
EVIDENCE_DATASET = f"{ORG}/szl-evidence"
KERNEL_IDS = (
    f"{ORG}/governed-inference-meter",
    f"{ORG}/szl-governed-norm",
)
VIEWER_URL = (
    "https://datasets-server.huggingface.co/first-rows"
    "?dataset=SZLHOLDINGS%2Fszl-lake&config=receipts&split=train"
)
VIEWER_ATTEMPTS = 30
VIEWER_RETRY_SECONDS = 20
TRANSIENT_STATUSES = {425, 429, 502, 503, 504}
TRANSIENT_MARKERS = (
    "busier than usual",
    "not ready yet",
    "still processing",
    "temporarily unavailable",
)


@dataclass(frozen=True)
class Action:
    target: str
    action: str
    status: str
    detail: str = ""


def _response_text(response: Any) -> str:
    return str(getattr(response, "text", "") or "")


def _transient_viewer_response(response: Any) -> bool:
    status = int(getattr(response, "status_code", 0) or 0)
    if status in TRANSIENT_STATUSES:
        return True
    if status != 500:
        return False
    body = _response_text(response).lower()
    return any(marker in body for marker in TRANSIENT_MARKERS)


def wait_for_viewer(
    session: Any,
    *,
    attempts: int = VIEWER_ATTEMPTS,
    retry_seconds: float = VIEWER_RETRY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Any, dict[str, Any], int]:
    """Return the first valid HTTP-200 viewer payload or fail closed."""
    if attempts < 1:
        raise ValueError("viewer attempts must be positive")

    last_error = "viewer was not queried"
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(
                VIEWER_URL,
                timeout=90,
                headers={
                    "Accept": "application/json",
                    "Cache-Control": "no-cache, no-store, max-age=0",
                    "Pragma": "no-cache",
                    "User-Agent": "szl-hf-release-readiness/1",
                },
            )
        except Exception as exc:  # noqa: BLE001
            last_error = f"transport {type(exc).__name__}: {exc}"
            if attempt == attempts:
                break
            sleep(retry_seconds)
            continue

        status = int(getattr(response, "status_code", 0) or 0)
        if status == 200:
            try:
                payload = response.json()
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Dataset Viewer returned non-JSON HTTP 200: {exc}") from exc
            if not isinstance(payload, dict):
                raise RuntimeError("Dataset Viewer HTTP 200 payload is not an object")
            error = payload.get("error")
            if not error:
                return response, payload, attempt
            text = str(error).lower()
            if any(marker in text for marker in TRANSIENT_MARKERS):
                last_error = f"HTTP 200 transient payload: {error}"
                if attempt < attempts:
                    sleep(retry_seconds)
                    continue
            raise RuntimeError(f"Dataset Viewer returned an error payload: {payload}")

        if _transient_viewer_response(response):
            last_error = f"HTTP {status}: {_response_text(response)[:300]}"
            if attempt < attempts:
                retry_after = str(getattr(response, "headers", {}).get("Retry-After", "") or "")
                try:
                    delay = min(60.0, max(retry_seconds, float(retry_after)))
                except ValueError:
                    delay = retry_seconds
                sleep(delay)
                continue
            break

        raise RuntimeError(
            f"Dataset Viewer contract returned terminal HTTP {status}: "
            f"{_response_text(response)[:300]}"
        )

    raise RuntimeError(
        f"Dataset Viewer did not become ready after {attempts} attempts: {last_error}"
    )


class ReadinessVerifier:
    def __init__(self, *, token: str, generation: str, publish: bool) -> None:
        self.token = token
        self.generation = generation
        self.publish = publish
        self.api = HfApi(token=token)
        self.actions: list[Action] = []
        self.results: dict[str, Any] = {}

    def record(self, target: str, action: str, status: str, detail: str = "") -> None:
        self.actions.append(Action(target, action, status, detail))
        print(f"[{status:>10}] {action}: {target}" + (f" — {detail}" if detail else ""))

    def authenticate(self) -> None:
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
        if role and role not in {"admin", "write", "contributor"}:
            raise RuntimeError(f"authenticated role is not write-capable: {role}")
        self.record(ORG, "authenticate", "validated", f"role={role or 'unknown'}")

    def verify_dataset(self) -> None:
        info = self.api.dataset_info(DATASET_ID)
        revision = str(getattr(info, "sha", "") or "")
        if len(revision) != 40:
            raise RuntimeError(f"dataset lacks an immutable revision: {revision!r}")
        files = set(self.api.list_repo_files(DATASET_ID, repo_type="dataset", revision=revision))
        required = {
            "README.md",
            "khipu/amaru_receipts.parquet",
            "khipu/sentra_receipts.parquet",
            "khipu/a11oy_receipts.parquet",
            "khipu/rosie_receipts.parquet",
            "khipu/killinchu_receipts.parquet",
            "khipu/EMPTY_CHAIN_MANIFEST.json",
        }
        missing = sorted(required - files)
        if missing:
            raise RuntimeError(f"published Lake revision is incomplete: {missing}")

        session = requests.Session()
        response, payload, attempts = wait_for_viewer(session)
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

    @staticmethod
    def _run_selfcheck(repo_id: str, revision: str) -> Any:
        from kernels import get_kernel

        module = get_kernel(repo_id, revision=revision, trust_remote_code=True)
        check = getattr(module, "selfcheck", None)
        if not callable(check):
            raise RuntimeError(f"{repo_id}@{revision} does not expose selfcheck()")
        result = check()
        if result is False:
            raise RuntimeError(f"{repo_id}@{revision} selfcheck returned false")
        if isinstance(result, dict) and result.get("ok") is False:
            raise RuntimeError(f"{repo_id}@{revision} selfcheck failed: {result}")
        return result

    def verify_kernels(self) -> None:
        output: dict[str, Any] = {}
        for repo_id in KERNEL_IDS:
            info = self.api.kernel_info(repo_id)
            revision = str(getattr(info, "sha", "") or "")
            if len(revision) != 40:
                raise RuntimeError(f"kernel lacks an immutable revision: {repo_id}")
            files = set(self.api.list_repo_files(repo_id, repo_type="kernel", revision=revision))
            if "README.md" not in files or "contract.json" not in files:
                raise RuntimeError(f"kernel card contract is incomplete: {repo_id}")
            if not any(path.startswith("build/") for path in files):
                raise RuntimeError(f"kernel build variants are missing: {repo_id}")
            result = self._run_selfcheck(repo_id, revision)
            output[repo_id] = {
                "revision": revision,
                "remote_file_count": len(files),
                "selfcheck": result,
            }
            self.record(
                repo_id,
                "kernel-selfcheck",
                "validated",
                f"revision={revision}; files={len(files)}",
            )
        self.results["kernels"] = output

    def report(self) -> dict[str, Any]:
        statuses = [item.status for item in self.actions]
        return {
            "schema": "szl.hf-release-readiness/v1",
            "organization": ORG,
            "generation": self.generation,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "publish": self.publish,
            "results": self.results,
            "actions": [asdict(item) for item in self.actions],
            "summary": {
                "ok": sum(status in {"validated", "updated", "ok"} for status in statuses),
                "warning": sum(status == "warning" for status in statuses),
                "error": sum(status == "error" for status in statuses),
                "dry_run": sum(status == "dry-run" for status in statuses),
            },
            "boundaries": [
                "This verifier performs no dataset, kernel, model, Space, visibility, or hardware mutation.",
                "Only the known asynchronous Dataset Viewer readiness response is retried.",
                "Unknown viewer responses and every kernel selfcheck failure remain terminal.",
                "Kernel selfchecks run at the exact immutable revisions recorded in this report.",
            ],
        }

    def persist(self, report: dict[str, Any]) -> None:
        rendered = (json.dumps(report, indent=2, sort_keys=True, default=str) + "\n").encode()
        os.makedirs("reports", exist_ok=True)
        with open("reports/hf-release-readiness-latest.json", "wb") as handle:
            handle.write(rendered)
        self.record("reports/hf-release-readiness-latest.json", "local-report", "updated")
        if not self.publish:
            return
        if not self.api.repo_exists(EVIDENCE_DATASET, repo_type="dataset"):
            raise RuntimeError(f"evidence dataset is missing: {EVIDENCE_DATASET}")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for destination in (
            "release-readiness/latest.json",
            f"release-readiness/history/{timestamp}.json",
        ):
            self.api.upload_file(
                repo_id=EVIDENCE_DATASET,
                repo_type="dataset",
                path_or_fileobj=io.BytesIO(rendered),
                path_in_repo=destination,
                commit_message=f"release(evidence): record viewer and kernel readiness {timestamp}",
            )
        self.record(EVIDENCE_DATASET, "evidence-publish", "updated")

    def run(self) -> dict[str, Any]:
        self.authenticate()
        self.verify_dataset()
        self.verify_kernels()
        report = self.report()
        self.persist(report)
        report = self.report()
        with open("reports/hf-release-readiness-latest.json", "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, default=str)
            handle.write("\n")
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--generation", required=True)
    args = parser.parse_args()

    token = (
        os.environ.get("HF_ORG_TOKEN")
        or os.environ.get("HF_ORG_TOKEN1")
        or os.environ.get("HF_TOKEN")
    )
    if not token:
        print("FATAL: no supported Hugging Face token is configured", file=sys.stderr)
        return 2

    try:
        report = ReadinessVerifier(
            token=token,
            generation=args.generation,
            publish=args.publish,
        ).run()
    except Exception as exc:  # noqa: BLE001
        os.makedirs("reports", exist_ok=True)
        failure = {
            "schema": "szl.hf-release-readiness/v1",
            "generation": args.generation,
            "publish": args.publish,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fatal": f"{type(exc).__name__}: {exc}",
            "summary": {"ok": 0, "warning": 0, "error": 1, "dry_run": 0},
        }
        with open("reports/hf-release-readiness-latest.json", "w", encoding="utf-8") as handle:
            json.dump(failure, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"FATAL: {exc!r}", file=sys.stderr)
        return 2

    print(json.dumps(report["summary"], indent=2))
    return 1 if report["summary"]["error"] else 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main())
