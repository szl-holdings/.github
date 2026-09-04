#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Set the exact terminal status and merge the reconciler control PR.

The caller must already have validated the terminal estate/recovery ledgers and
committed the canonical workflow cleanup. GitHub branch protection, reviews,
and required checks remain authoritative: a rejected merge is recorded as a
blocker, never bypassed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping

OWNER = "szl-holdings"
REPO = ".github"
BRANCH = "ops/estate-reconciliation-2026-09-04-v1"


class ApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, body: Any) -> None:
        self.method = method
        self.path = path
        self.status = status
        self.body = body
        super().__init__(f"{method} {path}: HTTP {status}")


class GitHub:
    def __init__(self, token: str) -> None:
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        *,
        allow: Iterable[int] = (200, 201, 202, 204),
    ) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            "https://api.github.com" + path,
            method=method,
            data=data,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "szl-agent-estate-control-closeout/2",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
                if response.status not in set(allow):
                    raise ApiError(method, path, response.status, raw[:500])
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                body: Any = json.loads(raw)
            except json.JSONDecodeError:
                body = raw[:1000]
            raise ApiError(method, path, exc.code, body) from exc

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, payload: Any, *, allow: Iterable[int] = (200, 201, 202, 204)) -> Any:
        return self.request("POST", path, payload, allow=allow)

    def put(self, path: str, payload: Any, *, allow: Iterable[int] = (200, 201, 202, 204)) -> Any:
        return self.request("PUT", path, payload, allow=allow)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def safe_error(exc: Exception) -> dict[str, Any]:
    row: dict[str, Any] = {"type": type(exc).__name__, "message": str(exc)[:500]}
    if isinstance(exc, ApiError):
        row.update({"method": exc.method, "path": exc.path, "status": exc.status})
        if isinstance(exc.body, Mapping):
            row["provider_message"] = str(exc.body.get("message") or "")[:300]
    return row


def terminal_ledgers(estate_path: Path, recovery_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    estate = json.loads(estate_path.read_text(encoding="utf-8"))
    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
    terminal = estate.get("terminal") or {}
    counts = terminal.get("counts") or {}
    hf = estate.get("hugging_face_summary") or {}
    recovery_blocked = any(
        "BLOCKED" in str(row.get("action") or "")
        for group in ("reopened", "drafts", "dco_recoveries")
        for row in recovery.get(group, [])
    )
    conditions = {
        "estate_state": estate.get("state") == "VERIFIED_COMPLETE",
        "recovery_clear": not recovery_blocked,
        "product_prs": int(counts.get("open_pull_requests") or 0) == 0,
        "stale_runs": int(counts.get("stale_runs") or 0) == 0,
        "failed_default_workflows": int(counts.get("latest_failed_default_workflows") or 0) == 0,
        "hf_failures": int(hf.get("failed") or 0) == 0,
    }
    failed = [name for name, passed in conditions.items() if not passed]
    if failed:
        raise RuntimeError("terminal ledger conditions failed: " + ", ".join(failed))
    return estate, recovery


def write(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    report["report_sha256"] = digest({key: value for key, value in report.items() if key != "report_sha256"})
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--estate", required=True, type=Path)
    parser.add_argument("--recovery", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    report: dict[str, Any] = {
        "schema": "szl.agent-estate-control-plane-closeout/v2",
        "state": "BLOCKED",
        "repository": f"{OWNER}/{REPO}",
        "branch": BRANCH,
        "source_head_sha": args.head_sha,
        "branch_protection_bypass": False,
        "review_bypass": False,
        "dco_bypass": False,
        "secret_values_recorded": False,
    }
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", args.head_sha):
            raise RuntimeError("head SHA is not exact")
        estate, recovery = terminal_ledgers(args.estate, args.recovery)
        report["estate_report_sha256"] = estate.get("report_sha256")
        report["recovery_report_sha256"] = recovery.get("report_sha256")
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if not token:
            raise RuntimeError("repository token unavailable")
        print(f"::add-mask::{token}")
        api = GitHub(token)
        repository = api.get(f"/repos/{OWNER}/{REPO}")
        permissions = repository.get("permissions") or {}
        if not (permissions.get("push") or permissions.get("maintain") or permissions.get("admin")):
            raise RuntimeError("repository token has no write authority")

        branch = api.get(f"/repos/{OWNER}/{REPO}/git/ref/heads/{urllib.parse.quote(BRANCH, safe='')}")
        observed_head = str(((branch.get("object") or {}).get("sha") or ""))
        if observed_head != args.head_sha:
            raise RuntimeError(f"branch head moved: {observed_head} != {args.head_sha}")

        api.post(
            f"/repos/{OWNER}/{REPO}/statuses/{args.head_sha}",
            {
                "state": "success",
                "context": "agent-estate/terminal-ledger",
                "description": "Terminal GitHub and Hugging Face ledgers verified",
                "target_url": f"https://github.com/{OWNER}/{REPO}/tree/{args.head_sha}/reports/agent-estate",
            },
            allow=(201,),
        )
        head_query = urllib.parse.quote(f"{OWNER}:{BRANCH}", safe="")
        pulls = api.get(f"/repos/{OWNER}/{REPO}/pulls?state=open&head={head_query}&per_page=20")
        if not isinstance(pulls, list) or len(pulls) != 1:
            raise RuntimeError(f"expected one operator PR; observed {len(pulls or [])}")
        number = int(pulls[0]["number"])
        pull = None
        for _ in range(20):
            pull = api.get(f"/repos/{OWNER}/{REPO}/pulls/{number}")
            if str((pull.get("head") or {}).get("sha") or "") != args.head_sha:
                raise RuntimeError("operator PR head moved")
            if pull.get("mergeable") is not None:
                break
            time.sleep(3)
        if not pull or pull.get("draft"):
            raise RuntimeError("operator PR is absent or draft")
        if pull.get("mergeable") is not True:
            raise RuntimeError(f"operator PR is not mergeable: {pull.get('mergeable_state')}")
        report["premerge"] = {
            "pull_number": number,
            "mergeable": pull.get("mergeable"),
            "mergeable_state": pull.get("mergeable_state"),
            "draft": pull.get("draft"),
        }
        merged = api.put(
            f"/repos/{OWNER}/{REPO}/pulls/{number}/merge",
            {
                "sha": args.head_sha,
                "merge_method": "squash",
                "commit_title": f"{pull.get('title')} (#{number})",
                "commit_message": (
                    "Install the canonical exact-head agent-estate reconciler, retain terminal ledgers, "
                    "and remove every temporary recovery workflow.\n\n"
                    "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
                ),
            },
            allow=(200,),
        )
        if not isinstance(merged, Mapping) or merged.get("merged") is not True:
            raise RuntimeError(str((merged or {}).get("message") or "GitHub rejected the merge"))
        merge_sha = str(merged.get("sha") or "")
        if not re.fullmatch(r"[0-9a-f]{40}", merge_sha):
            raise RuntimeError("merge did not return an exact SHA")
        main_ref = api.get(f"/repos/{OWNER}/{REPO}/git/ref/heads/main")
        main_sha = str(((main_ref.get("object") or {}).get("sha") or ""))
        if main_sha != merge_sha:
            raise RuntimeError(f"main readback mismatch: {main_sha} != {merge_sha}")
        report.update(
            {
                "state": "VERIFIED_COMPLETE",
                "pull_number": number,
                "merge_sha": merge_sha,
                "main_readback_sha": main_sha,
                "canonical_workflow": ".github/workflows/agent-estate-reconciler.yml",
                "temporary_workflows_removed": True,
            }
        )
        write(args.report, report)
        print(json.dumps({"state": report["state"], "merge_sha": merge_sha}, sort_keys=True))
        return 0
    except Exception as exc:
        report["blocker"] = safe_error(exc)
        write(args.report, report)
        print(json.dumps({"state": report["state"], "blocker": report["blocker"]}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
