#!/usr/bin/env python3
"""Close the HF release-readiness gate without unsupported kernel repo_type calls.

This verifier is intentionally read-only for Hugging Face assets. It validates the
published Lake Dataset Viewer and exact first-class kernel selfchecks, writes one
local JSON report, and may update the deterministic GitHub evidence issue.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests
from huggingface_hub import HfApi

ORG = "SZLHOLDINGS"
DATASET_ID = f"{ORG}/szl-lake"
ISSUE_REPO = "szl-holdings/.github"
ISSUE_NUMBER = 257
ISSUE_MARKER = "szl-hf-release-finalization-report"
KERNEL_IDS = (
    f"{ORG}/governed-inference-meter",
    f"{ORG}/szl-governed-norm",
)
VIEWER_URL = (
    "https://datasets-server.huggingface.co/first-rows"
    "?dataset=SZLHOLDINGS%2Fszl-lake&config=receipts&split=train"
)
SHA40 = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Action:
    target: str
    action: str
    status: str
    detail: str = ""


def _token() -> str | None:
    return os.environ.get("HF_ORG_TOKEN") or os.environ.get("HF_ORG_TOKEN1") or os.environ.get("HF_TOKEN")


def _headers(token: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "szl-hf-release-readiness-terminal/1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _selfcheck_passed(value: Any) -> bool:
    if value is True:
        return True
    if not isinstance(value, Mapping):
        return False
    if value.get("ok") is False or value.get("passed") is False:
        return False
    if value.get("ok") is True or value.get("passed") is True:
        return True
    checks = value.get("checks")
    return isinstance(checks, Mapping) and bool(checks) and all(item is True for item in checks.values())


class TerminalReadiness:
    def __init__(self, *, token: str, generation: str) -> None:
        self.token = token
        self.generation = generation
        self.api = HfApi(token=token)
        self.actions: list[Action] = []
        self.results: dict[str, Any] = {}

    def record(self, target: str, action: str, status: str, detail: str = "") -> None:
        self.actions.append(Action(target, action, status, detail))
        print(f"[{status:>10}] {action}: {target}" + (f" — {detail}" if detail else ""))

    def verify_dataset(self) -> None:
        info = self.api.dataset_info(DATASET_ID)
        revision = str(getattr(info, "sha", "") or "")
        if not SHA40.fullmatch(revision):
            raise RuntimeError(f"dataset lacks immutable revision: {revision!r}")
        files = set(self.api.list_repo_files(DATASET_ID, repo_type="dataset"))
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
            raise RuntimeError(f"dataset is missing viewer files: {missing}")
        response = requests.get(VIEWER_URL, headers=_headers(self.token), timeout=90)
        if response.status_code != 200:
            raise RuntimeError(f"Dataset Viewer did not return HTTP 200: {response.status_code} {response.text[:300]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Dataset Viewer did not return JSON") from exc
        if not isinstance(payload, dict) or payload.get("error"):
            raise RuntimeError(f"Dataset Viewer returned an error payload: {payload}")
        self.results["dataset"] = {
            "repo_id": DATASET_ID,
            "revision": revision,
            "remote_file_count": len(files),
            "viewer_http_status": response.status_code,
            "viewer_json_keys": sorted(payload)[:50],
        }
        self.record(DATASET_ID, "dataset-viewer-readback", "validated", f"revision={revision}; files={len(files)}")

    def _kernel_tree_count(self, repo_id: str, revision: str) -> int:
        owner, name = repo_id.split("/", 1)
        url = f"https://huggingface.co/api/kernels/{owner}/{name}/tree/{revision}?recursive=true"
        response = requests.get(url, headers=_headers(self.token), timeout=90)
        if response.status_code != 200:
            raise RuntimeError(f"kernel tree readback failed for {repo_id}@{revision}: HTTP {response.status_code} {response.text[:300]}")
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError(f"kernel tree payload is not a list for {repo_id}")
        file_count = sum(1 for item in payload if isinstance(item, dict) and item.get("type") in {"file", "blob"})
        if file_count <= 0:
            raise RuntimeError(f"kernel tree contains no files for {repo_id}@{revision}")
        return file_count

    def verify_kernel(self, repo_id: str) -> None:
        info = self.api.kernel_info(repo_id)
        revision = str(getattr(info, "sha", "") or "")
        if not SHA40.fullmatch(revision):
            raise RuntimeError(f"kernel lacks immutable revision: {repo_id} {revision!r}")
        file_count = self._kernel_tree_count(repo_id, revision)
        from kernels import get_kernel

        module = get_kernel(repo_id, revision=revision, trust_remote_code=True)
        check = getattr(module, "selfcheck", None)
        if not callable(check):
            raise RuntimeError(f"{repo_id}@{revision} does not expose selfcheck()")
        result = check()
        if not _selfcheck_passed(result):
            raise RuntimeError(f"{repo_id}@{revision} selfcheck did not pass: {result}")
        self.results.setdefault("kernels", {})[repo_id] = {
            "revision": revision,
            "remote_file_count": file_count,
            "selfcheck": result,
        }
        self.record(repo_id, "kernel-tree-and-selfcheck", "validated", f"revision={revision}; files={file_count}")

    def report(self) -> dict[str, Any]:
        statuses = [action.status for action in self.actions]
        return {
            "schema": "szl.hf-release-finalization/v1",
            "organization": ORG,
            "generation": self.generation,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "publish": True,
            "results": self.results,
            "actions": [asdict(action) for action in self.actions],
            "summary": {
                "ok": sum(status in {"validated", "updated", "ok"} for status in statuses),
                "warning": sum(status == "warning" for status in statuses),
                "error": sum(status == "error" for status in statuses),
                "dry_run": 0,
            },
            "boundaries": [
                "This terminal verifier performs no Hugging Face mutation.",
                "It uses dataset repo_type only for the Lake dataset and Kernel Hub REST tree readback for first-class kernels.",
                "Kernel selfcheck is executed at the exact immutable revision observed by HfApi.kernel_info().",
                "No model weights are trained, merged, relabeled, uploaded, deployed, or promoted.",
            ],
        }

    def run(self) -> dict[str, Any]:
        self.verify_dataset()
        for repo_id in KERNEL_IDS:
            self.verify_kernel(repo_id)
        return self.report()


def issue_body(report: Mapping[str, Any], run_url: str | None) -> str:
    lines = [
        f"<!-- {ISSUE_MARKER} -->",
        "# Hugging Face release finalization",
        "",
    ]
    if run_url:
        lines.append(f"- Run: {run_url}")
    lines.extend([
        f"- Source revision: `{report.get('generation')}`",
        "",
        "```json",
        json.dumps(report, indent=2, sort_keys=True, default=str),
        "```",
        "",
    ])
    return "\n".join(lines)


def publish_issue(report: Mapping[str, Any]) -> None:
    token = os.environ.get("SZL_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("no GitHub token is configured for issue publication")
    run_url = None
    if os.environ.get("GITHUB_SERVER_URL") and os.environ.get("GITHUB_REPOSITORY") and os.environ.get("GITHUB_RUN_ID"):
        run_url = f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    body = issue_body(report, run_url)
    state = "closed" if int((report.get("summary") or {}).get("error", 1)) == 0 else "open"
    response = requests.patch(
        f"https://api.github.com/repos/{ISSUE_REPO}/issues/{ISSUE_NUMBER}",
        headers={**_headers(token), "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
        json={"body": body, "state": state},
        timeout=60,
    )
    if response.status_code not in {200, 201}:
        raise RuntimeError(f"issue update failed: HTTP {response.status_code} {response.text[:500]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="reports/hf-release-finalization-latest.json")
    parser.add_argument("--generation", default=os.environ.get("GITHUB_SHA") or "manual")
    parser.add_argument("--publish-issue", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    token = _token()
    try:
        if not token:
            raise RuntimeError("no supported Hugging Face token is configured")
        report = TerminalReadiness(token=token, generation=args.generation).run()
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema": "szl.hf-release-finalization/v1",
            "organization": ORG,
            "generation": args.generation,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "publish": True,
            "fatal": f"{type(exc).__name__}: {exc}",
            "summary": {"ok": 0, "warning": 0, "error": 1, "dry_run": 0},
        }
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        if args.publish_issue:
            publish_issue(report)
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1 if args.enforce else 0

    report_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    if args.publish_issue:
        publish_issue(report)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
