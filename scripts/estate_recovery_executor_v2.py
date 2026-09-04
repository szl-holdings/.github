#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded recovery of stalled GitHub and Hugging Face estate work.

The executor uses normal provider APIs and never bypasses branch protection,
DCO, required reviews, environment approvals, or provider entitlements. It
merges only the exact observed pull-request head after all observed checks are
terminal green. Failed workflows are retried at most once per invocation.
Secret values, prompt text, output text, and private model state are never
written to the report.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN_ALIASES = (
    "SZL_ORG_GITHUB_TOKEN",
    "SZL_GITHUB_TOKEN",
    "ORG_ADMIN_TOKEN",
    "GH_ADMIN_TOKEN",
    "GH_PAT",
    "GITHUB_PAT",
    "PAT_TOKEN",
    "FRONTIER_TOKEN",
    "GITHUB_TOKEN",
)
HF_TOKEN_ALIASES = (
    "HF_ORG_TOKEN",
    "HF_ORG_TOKEN1",
    "HF_WRITE_TOKEN",
    "HF_TOKEN",
    "HUGGINGFACE_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
)
PASSING_CHECKS = frozenset({"success", "neutral", "skipped"})
FAILING_CHECKS = frozenset(
    {"failure", "cancelled", "timed_out", "action_required", "startup_failure", "stale"}
)
RETRYABLE_RUN_CONCLUSIONS = frozenset(
    {"failure", "cancelled", "timed_out", "action_required", "startup_failure"}
)
RECOVERABLE_SPACE_STAGES = frozenset(
    {
        "PAUSED",
        "SLEEPING",
        "STOPPED",
        "BUILD_ERROR",
        "RUNTIME_ERROR",
        "CONFIG_ERROR",
        "NO_APP_FILE",
    }
)
WORKFLOW_DISPATCH_TARGETS = (
    ("szl-holdings/a11oy", "hf-sync.yml", "main"),
    ("szl-holdings/a11oy", "deploy-cloudflare-governed-inference.yml", "main"),
    ("szl-holdings/a11oy", "repair-cloudflare-product-edge-production.yml", "main"),
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def first_secret(names: Iterable[str]) -> tuple[str | None, str | None]:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            print(f"::add-mask::{value}")
            return name, value
    return None, None


def safe_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    for name in (*GITHUB_TOKEN_ALIASES, *HF_TOKEN_ALIASES):
        value = os.getenv(name, "").strip()
        if value:
            text = text.replace(value, "[REDACTED]")
    return text[:1000]


class GitHubError(RuntimeError):
    def __init__(self, status: int | None, method: str, path: str, detail: str):
        super().__init__(f"GitHub {method} {path}: HTTP {status}: {detail[:500]}")
        self.status = status
        self.method = method
        self.path = path


class GitHub:
    def __init__(self, token: str):
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        *,
        accept: str = "application/vnd.github+json",
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        body = canonical(payload) if payload is not None else None
        request = urllib.request.Request(
            GITHUB_API + path,
            data=body,
            method=method,
            headers={
                "Accept": accept,
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "szl-estate-recovery/2",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
                if response.status not in expected:
                    raise GitHubError(response.status, method, path, raw.decode("utf-8", "replace"))
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise GitHubError(exc.code, method, path, detail) from exc
        except urllib.error.URLError as exc:
            raise GitHubError(None, method, path, str(exc.reason)) from exc

    def get(self, path: str, *, accept: str = "application/vnd.github+json") -> Any:
        return self.request("GET", path, accept=accept)

    def paginate(self, path: str) -> list[Any]:
        separator = "&" if "?" in path else "?"
        page = 1
        output: list[Any] = []
        while True:
            value = self.get(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(value, list):
                raise TypeError(f"paginated GitHub response is not a list: {path}")
            output.extend(value)
            if len(value) < 100:
                return output
            page += 1


def repo_parts(full_name: str) -> tuple[str, str]:
    owner, repo = full_name.split("/", 1)
    return owner, repo


def encoded(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def check_snapshot(gh: GitHub, repo: str, sha: str) -> dict[str, Any]:
    checks = gh.get(
        f"/repos/{repo}/commits/{sha}/check-runs?per_page=100",
        accept="application/vnd.github+json",
    )
    statuses = gh.get(f"/repos/{repo}/commits/{sha}/status")
    rows = list((checks or {}).get("check_runs") or [])
    status_rows = list((statuses or {}).get("statuses") or [])
    pending: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    passed: list[dict[str, Any]] = []
    for row in rows:
        record = {
            "name": row.get("name"),
            "status": row.get("status"),
            "conclusion": row.get("conclusion"),
            "details_url": row.get("details_url"),
        }
        if row.get("status") != "completed" or row.get("conclusion") is None:
            pending.append(record)
        elif str(row.get("conclusion")).lower() in PASSING_CHECKS:
            passed.append(record)
        else:
            failed.append(record)
    for row in status_rows:
        state = str(row.get("state") or "").lower()
        record = {
            "name": row.get("context"),
            "status": state,
            "conclusion": state,
            "details_url": row.get("target_url"),
        }
        if state == "pending":
            pending.append(record)
        elif state == "success":
            passed.append(record)
        else:
            failed.append(record)
    total = len(rows) + len(status_rows)
    return {
        "total": total,
        "passed_count": len(passed),
        "pending": pending,
        "failed": failed,
        "green": total > 0 and not pending and not failed,
    }


def rerun_failed_head_runs(
    gh: GitHub,
    repo: str,
    branch: str,
    sha: str,
    retried: set[int],
) -> list[dict[str, Any]]:
    runs = gh.get(
        f"/repos/{repo}/actions/runs?branch={encoded(branch)}&event=pull_request&per_page=100"
    )
    output: list[dict[str, Any]] = []
    for run in list((runs or {}).get("workflow_runs") or []):
        run_id = int(run.get("id") or 0)
        if not run_id or run_id in retried or run.get("head_sha") != sha:
            continue
        conclusion = str(run.get("conclusion") or "").lower()
        if conclusion not in RETRYABLE_RUN_CONCLUSIONS:
            continue
        try:
            gh.request(
                "POST",
                f"/repos/{repo}/actions/runs/{run_id}/rerun-failed-jobs",
                expected=(201, 202),
            )
            retried.add(run_id)
            output.append(
                {
                    "run_id": run_id,
                    "workflow": run.get("name"),
                    "prior_conclusion": conclusion,
                    "action": "RERUN_FAILED_JOBS_ACCEPTED",
                }
            )
        except Exception as exc:
            output.append(
                {
                    "run_id": run_id,
                    "workflow": run.get("name"),
                    "prior_conclusion": conclusion,
                    "action": "RERUN_FAILED_JOBS_REJECTED",
                    "error": safe_error(exc),
                }
            )
    return output


def recover_pull_requests(gh: GitHub, repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    retried: set[int] = set()
    for repository in repos:
        full_name = str(repository.get("full_name") or "")
        if not full_name or repository.get("archived") or repository.get("disabled"):
            continue
        try:
            pulls = gh.paginate(f"/repos/{full_name}/pulls?state=open&sort=updated&direction=desc")
        except Exception as exc:
            records.append({"repository": full_name, "state": "INVENTORY_FAILED", "error": safe_error(exc)})
            continue
        for initial in pulls:
            number = int(initial.get("number") or 0)
            record: dict[str, Any] = {
                "repository": full_name,
                "pull_number": number,
                "title": str(initial.get("title") or "")[:300],
                "observed_at": now(),
            }
            try:
                pr = gh.get(f"/repos/{full_name}/pulls/{number}")
                if pr.get("draft"):
                    record["state"] = "DRAFT_SKIPPED"
                    records.append(record)
                    continue
                head = pr.get("head") or {}
                head_repo = (head.get("repo") or {}).get("full_name")
                head_ref = str(head.get("ref") or "")
                head_sha = str(head.get("sha") or "").lower()
                record.update(
                    {
                        "head_ref": head_ref,
                        "head_sha": head_sha,
                        "mergeable": pr.get("mergeable"),
                        "mergeable_state": pr.get("mergeable_state"),
                    }
                )
                if head_repo != full_name:
                    record["state"] = "EXTERNAL_HEAD_REVIEW_REQUIRED"
                    records.append(record)
                    continue
                if len(head_sha) != 40:
                    record["state"] = "INVALID_HEAD_IDENTITY"
                    records.append(record)
                    continue
                mergeable_state = str(pr.get("mergeable_state") or "").lower()
                if mergeable_state == "behind":
                    try:
                        update = gh.request(
                            "PUT",
                            f"/repos/{full_name}/pulls/{number}/update-branch",
                            {"expected_head_sha": head_sha},
                            expected=(202,),
                        )
                        record["state"] = "UPDATE_BRANCH_ACCEPTED"
                        record["update_message"] = (update or {}).get("message")
                    except Exception as exc:
                        record["state"] = "UPDATE_BRANCH_REJECTED"
                        record["error"] = safe_error(exc)
                    records.append(record)
                    continue
                checks = check_snapshot(gh, full_name, head_sha)
                record["checks"] = checks
                if checks["failed"]:
                    record["workflow_retries"] = rerun_failed_head_runs(
                        gh, full_name, head_ref, head_sha, retried
                    )
                    record["state"] = (
                        "FAILED_RUNS_RETRIED"
                        if any(item.get("action") == "RERUN_FAILED_JOBS_ACCEPTED" for item in record["workflow_retries"])
                        else "DETERMINISTIC_FAILURE_REPAIR_REQUIRED"
                    )
                    records.append(record)
                    continue
                if checks["pending"]:
                    record["state"] = "CHECKS_NONTERMINAL"
                    records.append(record)
                    continue
                if not checks["green"]:
                    record["state"] = "NO_GREEN_CHECK_EVIDENCE"
                    records.append(record)
                    continue
                if pr.get("mergeable") is not True or mergeable_state not in {"clean", "unstable", "has_hooks"}:
                    record["state"] = "MERGEABILITY_BLOCKED"
                    records.append(record)
                    continue
                merge = gh.request(
                    "PUT",
                    f"/repos/{full_name}/pulls/{number}/merge",
                    {
                        "sha": head_sha,
                        "merge_method": "squash",
                        "commit_title": f"{record['title']} (#{number})",
                        "commit_message": "Merged by the bounded SZL estate recovery executor after exact-head terminal-green verification.\n\nSigned-off-by: Stephen Lutar <stephenlutar2@gmail.com>",
                    },
                    expected=(200,),
                )
                record["state"] = "MERGED" if (merge or {}).get("merged") else "MERGE_REJECTED"
                record["merge_sha"] = (merge or {}).get("sha")
                record["merge_message"] = (merge or {}).get("message")
            except Exception as exc:
                record["state"] = "PROCESSING_FAILED"
                record["error"] = safe_error(exc)
            records.append(record)
    return records


def recover_default_branch_runs(gh: GitHub, repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for repository in repos:
        full_name = str(repository.get("full_name") or "")
        branch = str(repository.get("default_branch") or "main")
        if not full_name or repository.get("archived") or repository.get("disabled"):
            continue
        try:
            runs = gh.get(
                f"/repos/{full_name}/actions/runs?branch={encoded(branch)}&per_page=100"
            )
            latest_by_workflow: dict[int, dict[str, Any]] = {}
            for run in list((runs or {}).get("workflow_runs") or []):
                workflow_id = int(run.get("workflow_id") or 0)
                if workflow_id and workflow_id not in latest_by_workflow:
                    latest_by_workflow[workflow_id] = run
            for run in latest_by_workflow.values():
                conclusion = str(run.get("conclusion") or "").lower()
                if conclusion not in RETRYABLE_RUN_CONCLUSIONS:
                    continue
                run_id = int(run.get("id") or 0)
                record = {
                    "repository": full_name,
                    "workflow": run.get("name"),
                    "run_id": run_id,
                    "head_sha": run.get("head_sha"),
                    "prior_conclusion": conclusion,
                }
                try:
                    gh.request(
                        "POST",
                        f"/repos/{full_name}/actions/runs/{run_id}/rerun-failed-jobs",
                        expected=(201, 202),
                    )
                    record["state"] = "RERUN_FAILED_JOBS_ACCEPTED"
                except Exception as exc:
                    record["state"] = "RERUN_REJECTED"
                    record["error"] = safe_error(exc)
                records.append(record)
        except Exception as exc:
            records.append({"repository": full_name, "state": "RUN_INVENTORY_FAILED", "error": safe_error(exc)})
    return records


def dispatch_release_workflows(gh: GitHub) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for repository, workflow, ref in WORKFLOW_DISPATCH_TARGETS:
        record = {"repository": repository, "workflow": workflow, "ref": ref}
        try:
            gh.request(
                "POST",
                f"/repos/{repository}/actions/workflows/{encoded(workflow)}/dispatches",
                {"ref": ref},
                expected=(204,),
            )
            record["state"] = "DISPATCH_ACCEPTED"
        except Exception as exc:
            record["state"] = "DISPATCH_REJECTED"
            record["error"] = safe_error(exc)
        records.append(record)
    return records


def stage_name(runtime: Any) -> str:
    stage = getattr(runtime, "stage", None)
    return str(getattr(stage, "value", stage) or "UNKNOWN").upper()


def recover_hugging_face(token: str | None, organization: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "organization": organization,
        "credential_present": bool(token),
        "credential_value_recorded": False,
        "spaces": [],
        "models": [],
        "datasets": [],
    }
    if not token:
        result["state"] = "BLOCKED_NO_WRITE_TOKEN"
        return result
    try:
        from huggingface_hub import HfApi

        api = HfApi(token=token)
        identity = api.whoami()
        result["identity_type"] = identity.get("type") if isinstance(identity, dict) else type(identity).__name__
        spaces = list(api.list_spaces(author=organization, limit=1000, full=True))
        models = list(api.list_models(author=organization, limit=1000, full=True))
        datasets = list(api.list_datasets(author=organization, limit=1000, full=True))
        result["models"] = [
            {
                "id": getattr(item, "id", None),
                "sha": getattr(item, "sha", None),
                "last_modified": str(getattr(item, "last_modified", None)),
            }
            for item in models
        ]
        result["datasets"] = [
            {
                "id": getattr(item, "id", None),
                "sha": getattr(item, "sha", None),
                "last_modified": str(getattr(item, "last_modified", None)),
            }
            for item in datasets
        ]
        restart_signature = inspect.signature(api.restart_space)
        supports_factory = "factory_reboot" in restart_signature.parameters
        for item in spaces:
            repo_id = str(getattr(item, "id", None) or "")
            record: dict[str, Any] = {
                "id": repo_id,
                "sha": getattr(item, "sha", None),
                "private": getattr(item, "private", None),
            }
            if not repo_id:
                record["state"] = "INVALID_IDENTITY"
                result["spaces"].append(record)
                continue
            try:
                before = api.space_info(repo_id, files_metadata=False)
                before_stage = stage_name(getattr(before, "runtime", None))
                record["before_stage"] = before_stage
                if before_stage in RECOVERABLE_SPACE_STAGES:
                    kwargs: dict[str, Any] = {}
                    if supports_factory and before_stage in {
                        "BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE"
                    }:
                        kwargs["factory_reboot"] = True
                    api.restart_space(repo_id, **kwargs)
                    record["action"] = "FACTORY_REBOOT_REQUESTED" if kwargs else "RESTART_REQUESTED"
                    time.sleep(1)
                    after = api.space_info(repo_id, files_metadata=False)
                    record["after_stage"] = stage_name(getattr(after, "runtime", None))
                else:
                    record["action"] = "NO_RESTART_REQUIRED"
                    record["after_stage"] = before_stage
                record["state"] = "OBSERVED"
            except Exception as exc:
                record["state"] = "RECOVERY_FAILED"
                record["error"] = safe_error(exc)
            result["spaces"].append(record)
        result["state"] = "EXECUTED"
    except Exception as exc:
        result["state"] = "FAILED"
        result["error"] = safe_error(exc)
    return result


def write_report(path: Path, report: dict[str, Any]) -> None:
    report["report_sha256"] = digest(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--github-org", default="szl-holdings")
    parser.add_argument("--hf-org", default="SZLHOLDINGS")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    github_alias, github_token = first_secret(GITHUB_TOKEN_ALIASES)
    hf_alias, hf_token = first_secret(HF_TOKEN_ALIASES)
    report: dict[str, Any] = {
        "schema": "szl.estate-recovery/v2",
        "started_at": now(),
        "github_organization": args.github_org,
        "hugging_face_organization": args.hf_org,
        "credentials": {
            "github_alias": github_alias,
            "github_present": bool(github_token),
            "hugging_face_alias": hf_alias,
            "hugging_face_present": bool(hf_token),
            "secret_values_recorded": False,
        },
        "policy": {
            "admin_bypass": False,
            "force_push": False,
            "dco_disabled": False,
            "branch_protection_bypassed": False,
            "merge_requires_exact_head": True,
            "merge_requires_terminal_green_evidence": True,
            "failed_run_retry_limit_per_invocation": 1,
        },
    }

    if not github_token:
        report["github"] = {"state": "BLOCKED_NO_ORG_TOKEN"}
        report["hugging_face"] = recover_hugging_face(hf_token, args.hf_org)
        report["finished_at"] = now()
        write_report(args.output, report)
        return 2

    try:
        gh = GitHub(github_token)
        actor = gh.get("/user")
        organization = gh.get(f"/orgs/{args.github_org}")
        repos = gh.paginate(f"/orgs/{args.github_org}/repos?type=all&sort=pushed&direction=desc")
        report["github"] = {
            "state": "EXECUTED",
            "actor": actor.get("login"),
            "organization": organization.get("login"),
            "repository_count": len(repos),
            "pull_requests": recover_pull_requests(gh, repos),
            "default_branch_workflow_retries": recover_default_branch_runs(gh, repos),
            "release_dispatches": dispatch_release_workflows(gh),
        }
    except Exception as exc:
        report["github"] = {"state": "FAILED", "error": safe_error(exc)}

    report["hugging_face"] = recover_hugging_face(hf_token, args.hf_org)
    report["finished_at"] = now()
    write_report(args.output, report)
    print(json.dumps({
        "schema": report["schema"],
        "github_state": report.get("github", {}).get("state"),
        "hugging_face_state": report.get("hugging_face", {}).get("state"),
        "report_sha256": report["report_sha256"],
    }, sort_keys=True))
    return 0 if report.get("github", {}).get("state") == "EXECUTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
