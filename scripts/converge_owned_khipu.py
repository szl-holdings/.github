#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Finish the reviewed owned-Khipu A11oy branch through live HF proof.

Normal GitHub mergeability, checks, DCO, reviews, and deployment controls remain
binding. The controller never force-pushes, self-approves, or changes protection.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API = "https://api.github.com"
REPOSITORY = "szl-holdings/a11oy"
HEAD_BRANCH = "feat/hf-owned-khipu-cortex-v1"
HF_WORKFLOW = "hf-sync.yml"
HF_ORIGIN = "https://szlholdings-a11oy.hf.space"
PASSING = frozenset({"success", "neutral", "skipped"})
FAILED = frozenset({"failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"})
TOKEN_ALIASES = (
    "SZL_ORG_GITHUB_TOKEN",
    "SZL_GITHUB_TOKEN",
    "ORG_ADMIN_TOKEN",
    "GH_ADMIN_TOKEN",
    "GH_PAT",
    "GITHUB_PAT",
    "PAT_TOKEN",
    "FRONTIER_TOKEN",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def mask(value: str) -> None:
    if value:
        print(f"::add-mask::{value}")


def select_token() -> tuple[str, str]:
    attempts = []
    for alias in TOKEN_ALIASES:
        token = os.getenv(alias, "").strip()
        if not token:
            attempts.append({"alias": alias, "state": "ABSENT"})
            continue
        mask(token)
        request = urllib.request.Request(
            f"{API}/repos/{REPOSITORY}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "szl-owned-khipu-convergence/1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                repo = json.loads(response.read().decode())
            if (repo.get("permissions") or {}).get("push"):
                return alias, token
            attempts.append({"alias": alias, "state": "NO_PUSH_AUTHORITY"})
        except Exception as exc:
            attempts.append({"alias": alias, "state": "REJECTED", "error_type": type(exc).__name__})
    raise RuntimeError("no active token has push authority on szl-holdings/a11oy")


class GitHub:
    def __init__(self, token: str):
        self.token = token

    def request(self, method: str, path: str, payload: Any | None = None, expected=(200,)) -> Any:
        body = canonical(payload) if payload is not None else None
        request = urllib.request.Request(
            API + path,
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "szl-owned-khipu-convergence/1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
                if response.status not in expected:
                    raise RuntimeError(f"unexpected GitHub status {response.status}")
                return json.loads(raw.decode()) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1000]
            raise RuntimeError(f"GitHub {method} {path}: HTTP {exc.code}: {detail}") from exc

    def get(self, path: str) -> Any:
        return self.request("GET", path)


def checks(gh: GitHub, sha: str) -> dict[str, Any]:
    check_rows = list((gh.get(f"/repos/{REPOSITORY}/commits/{sha}/check-runs?per_page=100") or {}).get("check_runs") or [])
    status_rows = list((gh.get(f"/repos/{REPOSITORY}/commits/{sha}/status") or {}).get("statuses") or [])
    pending = [
        row.get("name")
        for row in check_rows
        if row.get("status") != "completed" or row.get("conclusion") is None
    ] + [row.get("context") for row in status_rows if row.get("state") == "pending"]
    failed = [
        row.get("name")
        for row in check_rows
        if row.get("status") == "completed" and str(row.get("conclusion")).lower() not in PASSING
    ] + [
        row.get("context")
        for row in status_rows
        if row.get("state") not in ("success", "pending")
    ]
    return {
        "total": len(check_rows) + len(status_rows),
        "pending": pending,
        "failed": failed,
        "green": bool(check_rows or status_rows) and not pending and not failed,
    }


def rerun_failed(gh: GitHub, sha: str) -> list[dict[str, Any]]:
    result = []
    rows = list(
        (
            gh.get(
                f"/repos/{REPOSITORY}/actions/runs?branch={urllib.parse.quote(HEAD_BRANCH, safe='')}&per_page=100"
            )
            or {}
        ).get("workflow_runs")
        or []
    )
    for run in rows:
        if run.get("head_sha") != sha or str(run.get("conclusion") or "").lower() not in FAILED:
            continue
        record = {"run_id": run.get("id"), "workflow": run.get("name"), "prior_conclusion": run.get("conclusion")}
        try:
            gh.request(
                "POST",
                f"/repos/{REPOSITORY}/actions/runs/{run['id']}/rerun-failed-jobs",
                expected=(201, 202),
            )
            record["state"] = "RERUN_ACCEPTED"
        except Exception as exc:
            record["state"] = "RERUN_REJECTED"
            record["error"] = str(exc)[:500].replace(gh.token, "[REDACTED]")
        result.append(record)
    return result


def open_pr(gh: GitHub) -> dict[str, Any] | None:
    owner = REPOSITORY.split("/", 1)[0]
    rows = gh.get(
        f"/repos/{REPOSITORY}/pulls?state=open&head={urllib.parse.quote(owner + ':' + HEAD_BRANCH, safe=':')}&per_page=10"
    )
    return rows[0] if rows else None


def main_file(gh: GitHub, path: str, sha: str) -> str:
    payload = gh.get(f"/repos/{REPOSITORY}/contents/{urllib.parse.quote(path, safe='/')}?ref={sha}")
    content = str((payload or {}).get("content") or "").replace("\n", "")
    return base64.b64decode(content).decode("utf-8")


def finish_pr(gh: GitHub, report: dict[str, Any]) -> str | None:
    pr = open_pr(gh)
    if pr is None:
        main = gh.get(f"/repos/{REPOSITORY}/git/ref/heads/main")
        sha = str((main.get("object") or {}).get("sha") or "")
        report["pull_request_state"] = "NO_OPEN_PR"
        return sha if len(sha) == 40 else None

    number = int(pr["number"])
    retried = False
    report["pull_number"] = number
    for _ in range(80):
        pr = gh.get(f"/repos/{REPOSITORY}/pulls/{number}")
        if pr.get("state") != "open":
            report["pull_request_state"] = "ALREADY_TERMINAL"
            report["pull_request_merged"] = pr.get("merged")
            main = gh.get(f"/repos/{REPOSITORY}/git/ref/heads/main")
            return str((main.get("object") or {}).get("sha") or "")
        sha = str((pr.get("head") or {}).get("sha") or "").lower()
        report["head_sha"] = sha
        snapshot = checks(gh, sha)
        report["checks"] = snapshot
        if snapshot["failed"] and not retried:
            report["reruns"] = rerun_failed(gh, sha)
            retried = True
            time.sleep(20)
            continue
        if snapshot["failed"]:
            report["pull_request_state"] = "DETERMINISTIC_CHECK_FAILURE"
            return None
        if snapshot["pending"] or snapshot["total"] == 0:
            time.sleep(15)
            continue
        if not snapshot["green"]:
            report["pull_request_state"] = "NO_GREEN_EVIDENCE"
            return None
        if pr.get("mergeable") is not True or str(pr.get("mergeable_state") or "").lower() not in {"clean", "unstable", "has_hooks"}:
            report["pull_request_state"] = "NORMAL_MERGE_BLOCKED"
            report["mergeable_state"] = pr.get("mergeable_state")
            return None
        merge = gh.request(
            "PUT",
            f"/repos/{REPOSITORY}/pulls/{number}/merge",
            {
                "sha": sha,
                "merge_method": "squash",
                "commit_title": f"feat(inference): serve the owned Khipu cortex through A11oy (#{number})",
                "commit_message": "Complete exact-model Khipu inference, Second Brain grounding, Nemo witnesses, deterministic receipts, and no-action-authority runtime wiring.\n\nSigned-off-by: Stephen Lutar <stephenlutar2@gmail.com>",
            },
        )
        report["pull_request_state"] = "MERGED" if merge.get("merged") else "MERGE_REJECTED"
        report["merge_sha"] = merge.get("sha")
        main = gh.get(f"/repos/{REPOSITORY}/git/ref/heads/main")
        return str((main.get("object") or {}).get("sha") or "")
    report["pull_request_state"] = "CHECKS_DID_NOT_CONVERGE"
    return None


def dispatch_hf(gh: GitHub, main_sha: str, report: dict[str, Any]) -> int | None:
    before = gh.get(f"/repos/{REPOSITORY}/actions/workflows/{HF_WORKFLOW}/runs?branch=main&per_page=30")
    before_ids = {int(row["id"]) for row in list((before or {}).get("workflow_runs") or [])}
    gh.request(
        "POST",
        f"/repos/{REPOSITORY}/actions/workflows/{HF_WORKFLOW}/dispatches",
        {"ref": "main"},
        expected=(204,),
    )
    report["hf_dispatch"] = "ACCEPTED"
    run = None
    for _ in range(30):
        rows = list(
            (
                gh.get(f"/repos/{REPOSITORY}/actions/workflows/{HF_WORKFLOW}/runs?branch=main&per_page=30")
                or {}
            ).get("workflow_runs")
            or []
        )
        candidates = [
            row
            for row in rows
            if int(row.get("id") or 0) not in before_ids and row.get("head_sha") == main_sha
        ]
        if candidates:
            candidates.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
            run = candidates[0]
            break
        time.sleep(5)
    if not run:
        report["hf_workflow_state"] = "DISPATCH_RUN_NOT_OBSERVED"
        return None
    run_id = int(run["id"])
    report["hf_workflow_run_id"] = run_id
    for _ in range(160):
        run = gh.get(f"/repos/{REPOSITORY}/actions/runs/{run_id}")
        report["hf_workflow_status"] = run.get("status")
        report["hf_workflow_conclusion"] = run.get("conclusion")
        if run.get("status") == "completed":
            report["hf_workflow_state"] = "TERMINAL"
            return run_id
        time.sleep(15)
    report["hf_workflow_state"] = "NONTERMINAL_TIMEOUT"
    return run_id


def run_live_proof(main_sha: str, output: Path) -> dict[str, Any]:
    url = f"https://raw.githubusercontent.com/{REPOSITORY}/{main_sha}/scripts/prove_hf_owned_cortex_live.py"
    request = urllib.request.Request(url, headers={"User-Agent": "szl-owned-khipu-convergence/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        script = response.read()
    script_path = Path("/tmp/prove_hf_owned_cortex_live.py")
    script_path.write_bytes(script)
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--base-url",
            HF_ORIGIN,
            "--expected-source-sha",
            main_sha,
            "--output",
            str(output),
        ],
        text=True,
        capture_output=True,
        timeout=1500,
        check=False,
    )
    proof = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    return {
        "exit_code": result.returncode,
        "proof": proof,
        "stderr_tail": result.stderr[-1000:],
        "stdout_tail": result.stdout[-1000:],
    }


def write(path: Path, report: dict[str, Any]) -> None:
    report["finished_at"] = now()
    report["report_sha256"] = hashlib.sha256(canonical(report)).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live-proof", type=Path, required=True)
    args = parser.parse_args(argv)
    report: dict[str, Any] = {
        "schema": "szl.owned-khipu-convergence/v1",
        "started_at": now(),
        "repository": REPOSITORY,
        "head_branch": HEAD_BRANCH,
        "hf_origin": HF_ORIGIN,
        "force_push": False,
        "admin_bypass": False,
        "self_approval": False,
        "secret_values_recorded": False,
    }
    try:
        alias, token = select_token()
        report["github_token_alias"] = alias
        gh = GitHub(token)
        main_sha = finish_pr(gh, report)
        if not main_sha or len(main_sha) != 40:
            report["state"] = "SOURCE_NOT_MERGED"
            write(args.output, report)
            return 2
        report["main_sha"] = main_sha
        cortex = main_file(gh, "a11oy_owned_cortex.py", main_sha)
        serve = main_file(gh, "serve.py", main_sha)
        docker = main_file(gh, "Dockerfile", main_sha)
        report["source_contract"] = {
            "cortex_present": "NO_ACTION_AUTHORITY" in cortex,
            "route_registered": "_a11oy_owned_cortex.register(app" in serve,
            "docker_cortex_copy": "COPY a11oy_owned_cortex.py ./" in docker,
            "docker_nemo_copy": "COPY szl_nemo/ ./szl_nemo/" in docker,
        }
        if not all(report["source_contract"].values()):
            report["state"] = "MERGED_SOURCE_CONTRACT_FAILED"
            write(args.output, report)
            return 2
        dispatch_hf(gh, main_sha, report)
        if report.get("hf_workflow_conclusion") != "success":
            report["state"] = "HF_DEPLOYMENT_FAILED"
            write(args.output, report)
            return 2
        report["live_verification"] = run_live_proof(main_sha, args.live_proof)
        live = report["live_verification"]
        proof_state = str((live.get("proof") or {}).get("state") or (live.get("proof") or {}).get("status") or "")
        report["state"] = "VERIFIED" if live.get("exit_code") == 0 and proof_state in {"VERIFIED", "PASS", "LIVE"} else "LIVE_PROOF_FAILED"
        write(args.output, report)
        return 0 if report["state"] == "VERIFIED" else 2
    except Exception as exc:
        report["state"] = "FAILED"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)[:1200]
        write(args.output, report)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
