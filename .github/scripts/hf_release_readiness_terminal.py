#!/usr/bin/env python3
"""Verify the released Hugging Face Lake and first-class Kernels read-only.

The release publisher owns all Hugging Face mutation. This terminal verifier
runs only after that publisher completes, binds every observation to immutable
revisions, verifies the Dataset Viewer while the dataset revision is stable,
reads Kernel trees through the first-class Kernel REST endpoint, executes each
Kernel selfcheck at the exact observed revision, and updates one deterministic
GitHub evidence issue.

No generic ``huggingface_hub`` repository helper is called with the unsupported
Kernel repository type and no Hugging Face asset is mutated here.
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

REPORT_SCHEMA = "szl.hf-release-readiness/v1"
PRERELEASE_SCHEMA = "szl.hf-release-readiness/v1-prerelease"
ORG = "SZLHOLDINGS"
DATASET_ID = f"{ORG}/szl-lake"
ISSUE_REPO = "szl-holdings/.github"
ISSUE_NUMBER = 257
ISSUE_MARKER = "szl-hf-release-readiness-report"
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
    return (
        os.environ.get("HF_ORG_TOKEN")
        or os.environ.get("HF_ORG_TOKEN1")
        or os.environ.get("HF_TOKEN")
    )


def _headers(token: str | None, *, user_agent: str) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": user_agent}
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
    return (
        isinstance(checks, Mapping)
        and bool(checks)
        and all(item is True for item in checks.values())
    )


def _immutable_revision(value: object, *, label: str) -> str:
    revision = str(value or "").strip().lower()
    if not SHA40.fullmatch(revision):
        raise RuntimeError(f"{label} lacks an immutable revision: {revision!r}")
    return revision


def _require_successful_upstream() -> None:
    workflow = str(os.environ.get("UPSTREAM_WORKFLOW") or "").strip()
    conclusion = str(os.environ.get("UPSTREAM_CONCLUSION") or "").strip().lower()
    if workflow and conclusion != "success":
        run_url = str(os.environ.get("UPSTREAM_RUN_URL") or "").strip()
        suffix = f"; run={run_url}" if run_url else ""
        raise RuntimeError(
            "upstream release finalization did not succeed: "
            f"workflow={workflow}; conclusion={conclusion or 'missing'}{suffix}"
        )


def _workflow_context() -> dict[str, str]:
    fields = {
        "event": os.environ.get("GITHUB_EVENT_NAME", ""),
        "upstream_workflow": os.environ.get("UPSTREAM_WORKFLOW", ""),
        "upstream_run_id": os.environ.get("UPSTREAM_RUN_ID", ""),
        "upstream_run_url": os.environ.get("UPSTREAM_RUN_URL", ""),
        "upstream_conclusion": os.environ.get("UPSTREAM_CONCLUSION", ""),
        "upstream_head_sha": os.environ.get("UPSTREAM_HEAD_SHA", ""),
    }
    return {key: value for key, value in fields.items() if value}


class TerminalReadiness:
    def __init__(self, *, token: str, generation: str) -> None:
        if not token:
            raise ValueError("a non-empty Hugging Face token is required")
        self.generation = _immutable_revision(
            generation,
            label="readiness generation",
        )
        self.token = token
        self.api = HfApi(token=token)
        self.actions: list[Action] = []
        self.results: dict[str, Any] = {}

    def record(self, target: str, action: str, status: str, detail: str = "") -> None:
        self.actions.append(Action(target, action, status, detail))
        print(
            f"[{status:>10}] {action}: {target}"
            + (f" — {detail}" if detail else "")
        )

    def verify_dataset(self) -> None:
        revision = _immutable_revision(
            getattr(self.api.dataset_info(DATASET_ID), "sha", ""),
            label=DATASET_ID,
        )
        files = set(
            self.api.list_repo_files(
                DATASET_ID,
                repo_type="dataset",
                revision=revision,
            )
        )
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

        response = requests.get(
            VIEWER_URL,
            headers=_headers(
                self.token,
                user_agent="szl-hf-release-readiness-terminal/2",
            ),
            timeout=90,
        )
        if response.status_code != 200:
            raise RuntimeError(
                "Dataset Viewer did not return HTTP 200: "
                f"{response.status_code} {response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("Dataset Viewer did not return JSON") from exc
        if not isinstance(payload, dict) or payload.get("error"):
            raise RuntimeError(f"Dataset Viewer returned an error payload: {payload}")
        expected_identity = {
            "dataset": DATASET_ID,
            "config": "receipts",
            "split": "train",
        }
        mismatched = {
            key: payload.get(key)
            for key, expected in expected_identity.items()
            if payload.get(key) != expected
        }
        if mismatched:
            raise RuntimeError(
                "Dataset Viewer identity mismatch: "
                f"expected={expected_identity}; observed={mismatched}"
            )

        revision_after = _immutable_revision(
            getattr(self.api.dataset_info(DATASET_ID), "sha", ""),
            label=DATASET_ID,
        )
        if revision_after != revision:
            raise RuntimeError(
                "dataset revision moved during Viewer verification: "
                f"before={revision}; after={revision_after}"
            )

        rows = payload.get("rows")
        self.results["dataset"] = {
            "repo_id": DATASET_ID,
            "revision": revision,
            "remote_file_count": len(files),
            "viewer_http_status": response.status_code,
            "viewer_json_keys": sorted(payload)[:50],
            "viewer_row_count": len(rows) if isinstance(rows, list) else None,
            "metadata_stable": True,
        }
        self.record(
            DATASET_ID,
            "dataset-viewer-readback",
            "validated",
            f"revision={revision}; files={len(files)}; metadata_stable=true",
        )

    def _kernel_tree_paths(self, repo_id: str, revision: str) -> tuple[str, ...]:
        owner, name = repo_id.split("/", 1)
        url = (
            f"https://huggingface.co/api/kernels/{owner}/{name}/tree/"
            f"{revision}?recursive=true"
        )
        response = requests.get(
            url,
            headers=_headers(
                self.token,
                user_agent="szl-hf-release-readiness-terminal/2",
            ),
            timeout=90,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"kernel tree readback failed for {repo_id}@{revision}: "
                f"HTTP {response.status_code} {response.text[:300]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"kernel tree did not return JSON for {repo_id}") from exc
        if not isinstance(payload, list):
            raise RuntimeError(f"kernel tree payload is not a list for {repo_id}")
        paths = tuple(
            sorted(
                {
                    str(item.get("path") or "")
                    for item in payload
                    if isinstance(item, dict)
                    and item.get("type") in {"file", "blob"}
                    and str(item.get("path") or "")
                }
            )
        )
        if not paths:
            raise RuntimeError(f"kernel tree contains no files for {repo_id}@{revision}")
        missing = {"README.md", "contract.json"} - set(paths)
        if missing:
            raise RuntimeError(
                f"kernel card contract is incomplete for {repo_id}: {sorted(missing)}"
            )
        if not any(path.startswith("build/") for path in paths):
            raise RuntimeError(
                f"kernel build variants are missing for {repo_id}@{revision}"
            )
        return paths

    def verify_kernel(self, repo_id: str) -> None:
        revision = _immutable_revision(
            getattr(self.api.kernel_info(repo_id), "sha", ""),
            label=repo_id,
        )
        paths = self._kernel_tree_paths(repo_id, revision)

        from kernels import get_kernel

        module = get_kernel(repo_id, revision=revision, trust_remote_code=True)
        check = getattr(module, "selfcheck", None)
        if not callable(check):
            raise RuntimeError(f"{repo_id}@{revision} does not expose selfcheck()")
        result = check()
        if not _selfcheck_passed(result):
            raise RuntimeError(f"{repo_id}@{revision} selfcheck did not pass: {result}")

        revision_after = _immutable_revision(
            getattr(self.api.kernel_info(repo_id), "sha", ""),
            label=repo_id,
        )
        if revision_after != revision:
            raise RuntimeError(
                f"kernel revision moved during selfcheck: {repo_id}; "
                f"before={revision}; after={revision_after}"
            )

        self.results.setdefault("kernels", {})[repo_id] = {
            "revision": revision,
            "remote_file_count": len(paths),
            "build_variants_present": True,
            "metadata_stable": True,
            "selfcheck": result,
        }
        self.record(
            repo_id,
            "kernel-tree-and-selfcheck",
            "validated",
            f"revision={revision}; files={len(paths)}; metadata_stable=true",
        )

    def report(self) -> dict[str, Any]:
        statuses = [action.status for action in self.actions]
        report: dict[str, Any] = {
            "schema": REPORT_SCHEMA,
            "organization": ORG,
            "generation": self.generation,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "publish": True,
            "results": self.results,
            "actions": [asdict(action) for action in self.actions],
            "summary": {
                "ok": sum(
                    status in {"validated", "updated", "ok"}
                    for status in statuses
                ),
                "warning": sum(status == "warning" for status in statuses),
                "error": sum(status == "error" for status in statuses),
                "dry_run": 0,
            },
            "boundaries": [
                "This terminal verifier performs no Hugging Face mutation.",
                "The Lake file inventory is bound to one immutable dataset revision and the Viewer is checked while that revision remains stable.",
                "First-class Kernel trees are read through the exact-revision Kernel REST endpoint; generic repository helpers never receive repo_type=kernel.",
                "Kernel selfcheck is executed at the exact immutable revision and metadata must remain stable through verification.",
                "No model weights are trained, merged, relabeled, uploaded, deployed, or promoted.",
            ],
        }
        workflow = _workflow_context()
        if workflow:
            report["workflow"] = workflow
        return report

    def run(self) -> dict[str, Any]:
        self.verify_dataset()
        for repo_id in KERNEL_IDS:
            self.verify_kernel(repo_id)
        return self.report()


def issue_body(report: Mapping[str, Any], run_url: str | None) -> str:
    lines = [
        f"<!-- {ISSUE_MARKER} -->",
        "# Hugging Face release readiness",
        "",
    ]
    if run_url:
        lines.append(f"- Run: {run_url}")
    lines.extend(
        [
            f"- Source revision: `{report.get('generation')}`",
            "",
            "```json",
            json.dumps(report, indent=2, sort_keys=True, default=str),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def publish_issue(report: Mapping[str, Any]) -> None:
    token = (
        os.environ.get("SZL_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
    )
    if not token:
        raise RuntimeError("no GitHub token is configured for issue publication")
    run_url = None
    if (
        os.environ.get("GITHUB_SERVER_URL")
        and os.environ.get("GITHUB_REPOSITORY")
        and os.environ.get("GITHUB_RUN_ID")
    ):
        run_url = (
            f"{os.environ['GITHUB_SERVER_URL']}/"
            f"{os.environ['GITHUB_REPOSITORY']}/actions/runs/"
            f"{os.environ['GITHUB_RUN_ID']}"
        )
    body = issue_body(report, run_url)
    summary = report.get("summary") or {}
    valid = (
        report.get("schema") == REPORT_SCHEMA
        and report.get("publish") is True
        and int(summary.get("error", 1)) == 0
        and int(summary.get("warning", 1)) == 0
    )
    response = requests.patch(
        f"https://api.github.com/repos/{ISSUE_REPO}/issues/{ISSUE_NUMBER}",
        headers={
            **_headers(token, user_agent="szl-hf-release-readiness-terminal/2"),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"body": body, "state": "closed" if valid else "open"},
        timeout=60,
    )
    if response.status_code not in {200, 201}:
        raise RuntimeError(
            f"issue update failed: HTTP {response.status_code} {response.text[:500]}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        default="reports/hf-release-readiness-latest.json",
    )
    parser.add_argument(
        "--generation",
        default=os.environ.get("GITHUB_SHA") or "",
    )
    parser.add_argument("--publish-issue", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    token = _token()
    try:
        if not token:
            raise RuntimeError("no supported Hugging Face token is configured")
        _require_successful_upstream()
        report = TerminalReadiness(
            token=token,
            generation=args.generation,
        ).run()
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema": REPORT_SCHEMA,
            "organization": ORG,
            "generation": args.generation,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "publish": True,
            "fatal": f"{type(exc).__name__}: {exc}",
            "summary": {"ok": 0, "warning": 0, "error": 1, "dry_run": 0},
            "workflow": _workflow_context(),
        }
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        if args.publish_issue:
            publish_issue(report)
        print(f"FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1 if args.enforce else 0

    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    if args.publish_issue:
        publish_issue(report)
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
