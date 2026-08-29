#!/usr/bin/env python3
"""Bounded GitHub-native SZL estate convergence with public-safe evidence.

The executor authenticates to GitHub using a governed organization token,
scans every repository visible to that token, requests reruns only for recent
terminal failed latest default-branch workflows, waits for accepted reruns,
and records a public-safe report. Public repository names and workflow names
remain visible; private repositories use opaque ordinal aliases and private
workflow names never leave process memory.

The same pass inventories the public SZLHOLDINGS Hugging Face estate and probes
both A11oy public domains plus the canonical Hugging Face runtime. No Replit
service, dependency, API, or credential is used.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ORG = "szl-holdings"
HF_ORG = "SZLHOLDINGS"
GH_API = "https://api.github.com"
REPORT_JSON = Path("reports/native-org-convergence-20260829.json")
REPORT_MD = Path("reports/native-org-convergence-20260829.md")
MAX_BODY = 2_000_000
MAX_PAGES = 20
RECENT_DAYS = 30
STALL_HOURS = 6
POLL_SECONDS = 15
POLL_DEADLINE_SECONDS = 900
FAILURE_CONCLUSIONS = {"failure", "startup_failure", "timed_out"}
PENDING_STATUSES = {"queued", "in_progress", "pending", "waiting", "requested"}

ORG_TOKEN = str(os.environ.get("ORG_TOKEN") or "").strip()
HF_TOKEN = str(os.environ.get("HF_TOKEN") or "").strip()
EXECUTE_RERUNS = str(os.environ.get("EXECUTE_RERUNS") or "true").casefold() not in {
    "0",
    "false",
    "no",
}

_print_lock = threading.Lock()


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime | None = None) -> str:
    return (value or now()).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def headers(*, github: bool = False, hf: bool = False) -> dict[str, str]:
    result = {
        "Accept": "application/json",
        "User-Agent": "szl-native-org-convergence/2026-08-29",
    }
    if github:
        result.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Authorization": f"Bearer {ORG_TOKEN}",
            }
        )
    if hf and HF_TOKEN:
        result["Authorization"] = f"Bearer {HF_TOKEN}"
    return result


def request(
    url: str,
    *,
    method: str = "GET",
    request_headers: dict[str, str] | None = None,
    payload: bytes | None = None,
    timeout: float = 25.0,
    retries: int = 2,
) -> dict[str, Any]:
    last_error: str | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            url,
            data=payload,
            method=method,
            headers=request_headers or {},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read(MAX_BODY + 1)
                if len(body) > MAX_BODY:
                    raise RuntimeError(f"response exceeded {MAX_BODY} bytes")
                return {
                    "ok": 200 <= response.status < 300,
                    "status": response.status,
                    "body": body,
                    "headers": {key.casefold(): value for key, value in response.headers.items()},
                    "final_url": response.geturl(),
                    "error": None,
                }
        except urllib.error.HTTPError as exc:
            body = exc.read(MAX_BODY)
            last_error = f"HTTP {exc.code}"
            result = {
                "ok": False,
                "status": exc.code,
                "body": body,
                "headers": {key.casefold(): value for key, value in exc.headers.items()},
                "final_url": exc.geturl(),
                "error": last_error,
            }
            if exc.code not in {408, 429, 500, 502, 503, 504} or attempt >= retries:
                return result
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:240]}"
            if attempt >= retries:
                return {
                    "ok": False,
                    "status": None,
                    "body": b"",
                    "headers": {},
                    "final_url": url,
                    "error": last_error,
                }
        time.sleep(1.5 * (attempt + 1))
    return {
        "ok": False,
        "status": None,
        "body": b"",
        "headers": {},
        "final_url": url,
        "error": last_error or "request failed",
    }


def request_json(
    url: str,
    *,
    method: str = "GET",
    github: bool = False,
    hf: bool = False,
    payload: dict[str, Any] | None = None,
    timeout: float = 25.0,
    retries: int = 2,
) -> tuple[Any, dict[str, Any]]:
    body = None
    request_headers = headers(github=github, hf=hf)
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    meta = request(
        url,
        method=method,
        request_headers=request_headers,
        payload=body,
        timeout=timeout,
        retries=retries,
    )
    if not meta["body"]:
        return None, meta
    try:
        return json.loads(meta["body"].decode("utf-8")), meta
    except Exception as exc:
        meta["ok"] = False
        meta["error"] = f"JSONDecodeError: {type(exc).__name__}"
        return None, meta


def gh(path: str, **kwargs: Any) -> tuple[Any, dict[str, Any]]:
    return request_json(f"{GH_API}{path}", github=True, **kwargs)


def add_page(path: str, page: int) -> str:
    joiner = "&" if "?" in path else "?"
    return f"{path}{joiner}per_page=100&page={page}"


def gh_pages(
    path: str,
    *,
    item_key: str | None = None,
    max_pages: int = MAX_PAGES,
    timeout: float = 30.0,
) -> tuple[list[Any], list[dict[str, Any]]]:
    items: list[Any] = []
    errors: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        data, meta = gh(add_page(path, page), timeout=timeout)
        if not meta["ok"]:
            errors.append(
                {
                    "operation": "paginate",
                    "status": meta["status"],
                    "error_class": str(meta["error"] or "unknown").split(":", 1)[0],
                }
            )
            break
        page_items = data.get(item_key) if item_key and isinstance(data, dict) else data
        if not isinstance(page_items, list):
            errors.append(
                {
                    "operation": "paginate",
                    "status": meta["status"],
                    "error_class": "malformed_response",
                }
            )
            break
        items.extend(page_items)
        if len(page_items) < 100:
            break
    else:
        errors.append(
            {
                "operation": "paginate",
                "status": None,
                "error_class": "pagination_cap_reached",
            }
        )
    return items, errors


def repo_path(repo: str) -> str:
    return urllib.parse.quote(repo, safe="")


def branch_path(branch: str) -> str:
    return urllib.parse.quote(branch, safe="")


def latest_per_workflow(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for run in runs:
        workflow_id = run.get("workflow_id")
        if workflow_id is None:
            continue
        key = str(workflow_id)
        current = latest.get(key)
        stamp = str(run.get("created_at") or run.get("run_started_at") or "")
        current_stamp = str(
            (current or {}).get("created_at")
            or (current or {}).get("run_started_at")
            or ""
        )
        if current is None or stamp > current_stamp:
            latest[key] = run
    return latest


def sanitize_failure(run: dict[str, Any], *, public: bool) -> dict[str, Any]:
    result = {
        "workflow_id": run.get("workflow_id"),
        "run_id": run.get("id"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "event": run.get("event"),
        "head_sha": run.get("head_sha"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "run_attempt": run.get("run_attempt"),
    }
    if public:
        result["workflow"] = run.get("name")
        result["url"] = run.get("html_url")
    return result


def status_error(operation: str, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": operation,
        "status": meta.get("status"),
        "error_class": str(meta.get("error") or "unknown").split(":", 1)[0],
    }


def scan_repository(raw: dict[str, Any]) -> dict[str, Any]:
    name = str(raw.get("name") or "")
    default_branch = str(raw.get("default_branch") or "main")
    public = not bool(raw.get("private"))
    record: dict[str, Any] = {
        "_name": name,
        "visibility": raw.get("visibility") or ("private" if not public else "public"),
        "public": public,
        "archived": bool(raw.get("archived")),
        "disabled": bool(raw.get("disabled")),
        "fork": bool(raw.get("fork")),
        "default_branch": default_branch,
        "open_pull_requests": None,
        "workflow_count": None,
        "missing_recent_active_workflow_runs": 0,
        "latest_default_branch_workflows": [],
        "failing_workflows": [],
        "pending_workflows": [],
        "stalled_workflows": [],
        "protection": None,
        "rulesets": None,
        "errors": [],
    }
    encoded = repo_path(name)

    pulls, pull_errors = gh_pages(
        f"/repos/{ORG}/{encoded}/pulls?state=open",
        max_pages=10,
        timeout=25.0,
    )
    if pull_errors:
        record["errors"].extend(pull_errors)
    else:
        record["open_pull_requests"] = len(pulls)

    workflows_data, workflows_meta = gh(
        f"/repos/{ORG}/{encoded}/actions/workflows?per_page=100",
        timeout=25.0,
    )
    workflows = (
        workflows_data.get("workflows") if isinstance(workflows_data, dict) else None
    )
    if isinstance(workflows, list):
        active_workflows = [
            workflow
            for workflow in workflows
            if isinstance(workflow, dict) and workflow.get("state") == "active"
        ]
        record["workflow_count"] = len(active_workflows)
    else:
        active_workflows = []
        record["errors"].append(status_error("workflows", workflows_meta))

    runs_data, runs_meta = gh(
        f"/repos/{ORG}/{encoded}/actions/runs"
        f"?branch={branch_path(default_branch)}&per_page=100",
        timeout=30.0,
    )
    runs = runs_data.get("workflow_runs") if isinstance(runs_data, dict) else None
    if not isinstance(runs, list):
        record["errors"].append(status_error("workflow_runs", runs_meta))
        runs = []

    latest = latest_per_workflow([run for run in runs if isinstance(run, dict)])
    active_ids = {
        str(workflow.get("id"))
        for workflow in active_workflows
        if workflow.get("id") is not None
    }
    record["missing_recent_active_workflow_runs"] = max(0, len(active_ids - set(latest)))
    stale_cutoff = now() - dt.timedelta(hours=STALL_HOURS)
    for key in sorted(
        latest,
        key=lambda workflow_key: str(latest[workflow_key].get("name") or "").casefold(),
    ):
        if active_ids and key not in active_ids:
            continue
        run = latest[key]
        summary = sanitize_failure(run, public=public)
        record["latest_default_branch_workflows"].append(summary)
        status = str(run.get("status") or "")
        conclusion = str(run.get("conclusion") or "")
        created = parse_time(run.get("created_at") or run.get("run_started_at"))
        if conclusion in FAILURE_CONCLUSIONS:
            record["failing_workflows"].append(summary)
        elif status in PENDING_STATUSES or (status != "completed" and not conclusion):
            record["pending_workflows"].append(summary)
            if created is not None and created < stale_cutoff:
                record["stalled_workflows"].append(summary)

    protection_data, protection_meta = gh(
        f"/repos/{ORG}/{encoded}/branches/{branch_path(default_branch)}/protection",
        timeout=20.0,
        retries=1,
    )
    if protection_meta["status"] == 200 and isinstance(protection_data, dict):
        required = protection_data.get("required_status_checks")
        review = protection_data.get("required_pull_request_reviews")
        record["protection"] = {
            "state": "PROTECTED",
            "strict": required.get("strict") if isinstance(required, dict) else None,
            "required_check_count": len(required.get("checks") or required.get("contexts") or [])
            if isinstance(required, dict)
            else 0,
            "required_approvals": review.get("required_approving_review_count")
            if isinstance(review, dict)
            else 0,
            "enforce_admins": bool(
                isinstance(protection_data.get("enforce_admins"), dict)
                and protection_data["enforce_admins"].get("enabled")
            ),
            "required_signatures": bool(protection_data.get("required_signatures")),
        }
    elif protection_meta["status"] == 404:
        record["protection"] = {
            "state": "UNOBSERVED_OR_RULESET_ONLY",
            "status": 404,
        }
    else:
        record["protection"] = {
            "state": "UNKNOWN",
            "status": protection_meta["status"],
        }
        record["errors"].append(status_error("branch_protection", protection_meta))

    rulesets_data, rulesets_meta = gh(
        f"/repos/{ORG}/{encoded}/rulesets?includes_parents=true&per_page=100",
        timeout=20.0,
        retries=1,
    )
    if isinstance(rulesets_data, list):
        record["rulesets"] = {
            "observed": len(rulesets_data),
            "active": sum(
                isinstance(item, dict) and item.get("enforcement") == "active"
                for item in rulesets_data
            ),
            "evaluate": sum(
                isinstance(item, dict) and item.get("enforcement") == "evaluate"
                for item in rulesets_data
            ),
        }
    else:
        record["rulesets"] = {
            "observed": None,
            "active": None,
            "evaluate": None,
            "status": rulesets_meta["status"],
        }
        record["errors"].append(status_error("rulesets", rulesets_meta))

    return record


def public_repo_record(record: dict[str, Any], private_alias: str | None) -> dict[str, Any]:
    if record["public"]:
        return {
            "repository": record["_name"],
            "visibility": record["visibility"],
            "archived": record["archived"],
            "disabled": record["disabled"],
            "fork": record["fork"],
            "default_branch": record["default_branch"],
            "open_pull_requests": record["open_pull_requests"],
            "workflow_count": record["workflow_count"],
            "missing_recent_active_workflow_runs": record[
                "missing_recent_active_workflow_runs"
            ],
            "latest_default_branch_workflows": record[
                "latest_default_branch_workflows"
            ],
            "failing_workflows": record["failing_workflows"],
            "pending_workflows": record["pending_workflows"],
            "stalled_workflows": record["stalled_workflows"],
            "protection": record["protection"],
            "rulesets": record["rulesets"],
            "errors": record["errors"],
        }
    return {
        "repository": private_alias,
        "visibility": "private",
        "archived": record["archived"],
        "disabled": record["disabled"],
        "fork": record["fork"],
        "default_branch_observed": bool(record["default_branch"]),
        "open_pull_requests": record["open_pull_requests"],
        "workflow_count": record["workflow_count"],
        "missing_recent_active_workflow_runs": record[
            "missing_recent_active_workflow_runs"
        ],
        "latest_default_branch_workflow_count": len(
            record["latest_default_branch_workflows"]
        ),
        "failing_workflow_count": len(record["failing_workflows"]),
        "pending_workflow_count": len(record["pending_workflows"]),
        "stalled_workflow_count": len(record["stalled_workflows"]),
        "protection": record["protection"],
        "rulesets": record["rulesets"],
        "errors": record["errors"],
    }


def rerun_candidate(record: dict[str, Any], run: dict[str, Any]) -> bool:
    created = parse_time(run.get("created_at"))
    return bool(
        EXECUTE_RERUNS
        and not record["archived"]
        and not record["disabled"]
        and created is not None
        and created >= now() - dt.timedelta(days=RECENT_DAYS)
        and run.get("status") == "completed"
        and run.get("conclusion") in FAILURE_CONCLUSIONS
        and run.get("event") != "pull_request"
        and isinstance(run.get("run_id"), int)
    )


def request_rerun(record: dict[str, Any], run: dict[str, Any], alias: str) -> dict[str, Any]:
    run_id = int(run["run_id"])
    _, meta = gh(
        f"/repos/{ORG}/{repo_path(record['_name'])}/actions/runs/{run_id}/rerun-failed-jobs",
        method="POST",
        payload={},
        timeout=25.0,
        retries=1,
    )
    public = record["public"]
    result = {
        "_name": record["_name"],
        "repository": record["_name"] if public else alias,
        "visibility": "public" if public else "private",
        "workflow": run.get("workflow") if public else None,
        "run_id": run_id,
        "prior_attempt": run.get("run_attempt"),
        "prior_conclusion": run.get("conclusion"),
        "requested": meta["status"] in {201, 202},
        "request_status": meta["status"],
        "request_error_class": None
        if meta["status"] in {201, 202}
        else str(meta.get("error") or "unknown").split(":", 1)[0],
        "post_status": None,
        "post_conclusion": None,
        "post_attempt": None,
        "post_updated_at": None,
    }
    return result


def poll_reruns(requests: list[dict[str, Any]]) -> None:
    accepted = [item for item in requests if item["requested"]]
    if not accepted:
        return
    deadline = time.monotonic() + POLL_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        unsettled = 0
        for item in accepted:
            data, meta = gh(
                f"/repos/{ORG}/{repo_path(item['_name'])}/actions/runs/{item['run_id']}",
                timeout=20.0,
                retries=1,
            )
            if not meta["ok"] or not isinstance(data, dict):
                unsettled += 1
                continue
            attempt = data.get("run_attempt")
            status = data.get("status")
            conclusion = data.get("conclusion")
            item["post_status"] = status
            item["post_conclusion"] = conclusion
            item["post_attempt"] = attempt
            item["post_updated_at"] = data.get("updated_at")
            if not (
                status == "completed"
                and isinstance(attempt, int)
                and attempt > int(item.get("prior_attempt") or 0)
            ):
                unsettled += 1
        if unsettled == 0:
            break
        time.sleep(POLL_SECONDS)
    for item in requests:
        item.pop("_name", None)


def github_inventory() -> dict[str, Any]:
    repos, repo_errors = gh_pages(
        f"/orgs/{ORG}/repos?type=all&sort=full_name",
        max_pages=20,
        timeout=35.0,
    )
    raw_repos = [item for item in repos if isinstance(item, dict)]
    if not raw_repos:
        raise RuntimeError("authenticated repository census returned no repositories")
    private_names = sorted(
        str(item.get("name") or "")
        for item in raw_repos
        if bool(item.get("private"))
    )
    if not private_names:
        raise RuntimeError(
            "governed token did not expose any private repository"
        )
    private_aliases = {
        name: f"private_repository_{index:03d}"
        for index, name in enumerate(private_names, 1)
    }

    records: list[dict[str, Any]] = []
    worker_count = min(12, max(1, len(raw_repos)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as pool:
        future_map = {
            pool.submit(scan_repository, raw): str(raw.get("name") or "")
            for raw in raw_repos
        }
        by_name = {str(raw.get("name") or ""): raw for raw in raw_repos}
        for future in concurrent.futures.as_completed(future_map):
            name = future_map[future]
            try:
                records.append(future.result())
            except Exception as exc:
                raw = by_name[name]
                records.append(
                    {
                        "_name": name,
                        "visibility": raw.get("visibility")
                        or ("private" if raw.get("private") else "public"),
                        "public": not bool(raw.get("private")),
                        "archived": bool(raw.get("archived")),
                        "disabled": bool(raw.get("disabled")),
                        "fork": bool(raw.get("fork")),
                        "default_branch": str(raw.get("default_branch") or "main"),
                        "open_pull_requests": None,
                        "workflow_count": None,
                        "missing_recent_active_workflow_runs": 0,
                        "latest_default_branch_workflows": [],
                        "failing_workflows": [],
                        "pending_workflows": [],
                        "stalled_workflows": [],
                        "protection": {"state": "UNKNOWN"},
                        "rulesets": {
                            "observed": None,
                            "active": None,
                            "evaluate": None,
                        },
                        "errors": [
                            {
                                "operation": "repository_scan",
                                "status": None,
                                "error_class": type(exc).__name__,
                            }
                        ],
                    }
                )
    records.sort(key=lambda item: item["_name"].casefold())

    candidates: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for record in records:
        alias = private_aliases.get(record["_name"], record["_name"])
        for run in record["failing_workflows"]:
            if (
                run.get("head_sha")
                and rerun_candidate(record, run)
            ):
                candidates.append((record, run, alias))

    rerun_requests: list[dict[str, Any]] = []
    if candidates:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(candidates))) as pool:
            rerun_requests = list(
                pool.map(lambda args: request_rerun(*args), candidates)
            )
        poll_reruns(rerun_requests)

    public_records = [
        public_repo_record(
            record,
            private_aliases.get(record["_name"]),
        )
        for record in records
    ]
    return {
        "scope": "every repository visible to the governed organization token",
        "repository_count": len(records),
        "public_repository_count": sum(record["public"] for record in records),
        "private_repository_count": sum(not record["public"] for record in records),
        "active_repository_count": sum(
            not record["archived"] and not record["disabled"] for record in records
        ),
        "archived_repository_count": sum(record["archived"] for record in records),
        "open_pull_request_count": sum(
            int(record["open_pull_requests"] or 0)
            for record in records
            if record["open_pull_requests"] is not None
        ),
        "repositories_with_latest_failures_before": sum(
            bool(record["failing_workflows"]) for record in records
        ),
        "latest_failure_count_before": sum(
            len(record["failing_workflows"]) for record in records
        ),
        "repositories_with_pending_before": sum(
            bool(record["pending_workflows"]) for record in records
        ),
        "stalled_workflow_count": sum(
            len(record["stalled_workflows"]) for record in records
        ),
        "repository_scan_error_count": sum(
            len(record["errors"]) for record in records
        ) + len(repo_errors),
        "rerun_candidate_count": len(candidates),
        "rerun_requested_count": sum(item["requested"] for item in rerun_requests),
        "rerun_success_count": sum(
            item["requested"]
            and item["post_status"] == "completed"
            and item["post_conclusion"] == "success"
            for item in rerun_requests
        ),
        "rerun_failure_count": sum(
            item["requested"]
            and item["post_status"] == "completed"
            and item["post_conclusion"] not in {"success", "skipped", "neutral"}
            for item in rerun_requests
        ),
        "rerun_unsettled_count": sum(
            item["requested"] and item["post_status"] != "completed"
            for item in rerun_requests
        ),
        "rerun_requests": rerun_requests,
        "repositories": public_records,
        "organization_repo_enumeration_errors": repo_errors,
    }


def hf_list(kind: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = (
        f"https://huggingface.co/api/{kind}"
        f"?author={urllib.parse.quote(HF_ORG)}&limit=100&full=true"
    )
    data, meta = request_json(url, hf=True, timeout=30.0, retries=2)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)], meta
    return [], meta


def hugging_face_inventory(public_repo_names: set[str]) -> dict[str, Any]:
    inventory: dict[str, list[dict[str, Any]]] = {}
    errors: list[dict[str, Any]] = []
    lookup = {name.casefold(): name for name in public_repo_names}
    mappings: list[dict[str, Any]] = []
    for kind in ("models", "datasets", "spaces"):
        rows, meta = hf_list(kind)
        inventory[kind] = rows
        if not meta["ok"]:
            errors.append(status_error(kind, meta))
        for item in rows:
            identifier = str(item.get("id") or item.get("modelId") or "")
            leaf = identifier.rsplit("/", 1)[-1]
            exact = lookup.get(leaf.casefold())
            card_data = item.get("cardData") if isinstance(item.get("cardData"), dict) else {}
            runtime = item.get("runtime") if isinstance(item.get("runtime"), dict) else {}
            mappings.append(
                {
                    "kind": kind[:-1] if kind.endswith("s") else kind,
                    "id": identifier,
                    "sha": item.get("sha"),
                    "last_modified": item.get("lastModified") or item.get("last_modified"),
                    "private": item.get("private"),
                    "sdk": card_data.get("sdk"),
                    "app_file": card_data.get("app_file"),
                    "runtime_stage": runtime.get("stage"),
                    "hardware": runtime.get("hardware"),
                    "github_exact_public_name": exact,
                    "mapping": "EXACT_PUBLIC_NAME" if exact else "UNMAPPED_BY_PUBLIC_NAME",
                }
            )

    detail, detail_meta = request_json(
        "https://huggingface.co/api/spaces/SZLHOLDINGS/a11oy",
        hf=True,
        timeout=30.0,
        retries=2,
    )
    if not detail_meta["ok"]:
        errors.append(status_error("canonical_space_detail", detail_meta))
    card = detail.get("cardData") if isinstance(detail, dict) and isinstance(detail.get("cardData"), dict) else {}
    runtime = detail.get("runtime") if isinstance(detail, dict) and isinstance(detail.get("runtime"), dict) else {}
    return {
        "scope": "public author-filtered APIs; private Hub assets are not inferred",
        "counts": {kind: len(rows) for kind, rows in inventory.items()},
        "assets": sorted(mappings, key=lambda item: (item["kind"], item["id"].casefold())),
        "mapped_by_exact_public_name": sum(
            item["mapping"] == "EXACT_PUBLIC_NAME" for item in mappings
        ),
        "unmapped_by_exact_public_name": sum(
            item["mapping"] == "UNMAPPED_BY_PUBLIC_NAME" for item in mappings
        ),
        "canonical_space": {
            "id": detail.get("id") if isinstance(detail, dict) else None,
            "sha": detail.get("sha") if isinstance(detail, dict) else None,
            "last_modified": detail.get("lastModified") if isinstance(detail, dict) else None,
            "private": detail.get("private") if isinstance(detail, dict) else None,
            "sdk": card.get("sdk"),
            "app_file": card.get("app_file"),
            "runtime_stage": runtime.get("stage"),
            "hardware": runtime.get("hardware"),
            "http_status": detail_meta["status"],
        },
        "errors": errors,
    }


def extract_identity(value: Any, *, limit: int = 30) -> list[dict[str, str]]:
    accepted = {
        "source_sha",
        "github_sha",
        "commit_sha",
        "build_sha",
        "revision",
        "sha",
        "commit",
    }
    found: list[dict[str, str]] = []

    def walk(node: Any, path: str) -> None:
        if len(found) >= limit:
            return
        if isinstance(node, dict):
            for key, child in node.items():
                child_path = f"{path}.{key}" if path else str(key)
                if str(key).casefold() in accepted and isinstance(child, (str, int)):
                    text = str(child)
                    if len(text) <= 160:
                        found.append({"path": child_path, "value": text})
                walk(child, child_path)
        elif isinstance(node, list):
            for index, child in enumerate(node[:50]):
                walk(child, f"{path}[{index}]")

    walk(value, "")
    return found


def probe(url: str) -> dict[str, Any]:
    meta = request(
        url,
        request_headers={
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "User-Agent": "szl-native-org-convergence/2026-08-29",
        },
        timeout=30.0,
        retries=2,
    )
    body = meta["body"]
    content_type = str(meta["headers"].get("content-type") or "")
    parsed: Any = None
    if body and ("json" in content_type.casefold() or body[:1] in {b"{", b"["}):
        try:
            parsed = json.loads(body.decode("utf-8"))
        except Exception:
            parsed = None
    return {
        "url": url,
        "final_url": meta["final_url"],
        "ok": meta["ok"],
        "http_status": meta["status"],
        "content_type": content_type,
        "body_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest() if body else None,
        "identity": extract_identity(parsed) if parsed is not None else [],
        "error_class": None
        if meta["ok"]
        else str(meta.get("error") or "unknown").split(":", 1)[0],
    }


def public_surfaces() -> dict[str, Any]:
    urls = [
        "https://a-11-oy.com/",
        "https://a-11-oy.com/healthz",
        "https://a-11-oy.com/api/a11oy/v1/honest",
        "https://a-11-oy.com/api/a11oy/v1/readiness",
        "https://a-11-oy.com/api/a11oy/v1/models/series-a",
        "https://a11oy.net/",
        "https://a11oy.net/health.json",
        "https://a11oy.net/record.json",
        "https://szlholdings-a11oy.hf.space/",
        "https://szlholdings-a11oy.hf.space/healthz",
        "https://szlholdings-a11oy.hf.space/api/a11oy/v1/honest",
        "https://szlholdings-a11oy.hf.space/api/a11oy/v1/readiness",
        "https://szlholdings-a11oy.hf.space/api/a11oy/v1/models/series-a",
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        probes = list(pool.map(probe, urls))
    by_url = {item["url"]: item for item in probes}
    primary = by_url.get("https://a-11-oy.com/") or {}
    canonical = by_url.get("https://szlholdings-a11oy.hf.space/") or {}
    return {
        "probe_count": len(probes),
        "reachable_count": sum(item["ok"] for item in probes),
        "all_reachable": all(item["ok"] for item in probes),
        "primary_and_canonical_root_byte_equal": bool(
            primary.get("body_sha256")
            and primary.get("body_sha256") == canonical.get("body_sha256")
        ),
        "probes": probes,
    }


def write_reports(report: dict[str, Any]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    github = report["github"]
    hub = report["hugging_face"]
    surfaces = report["surfaces"]
    lines = [
        "# Native SZL organization convergence — no Replit",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        "## Executive readback",
        "",
        f"- Every repository visible to the governed organization token was scanned: **{github['repository_count']}** total, including **{github['private_repository_count']}** private repositories represented only by opaque ordinals.",
        f"- Open pull requests observed across the full visible estate: **{github['open_pull_request_count']}**.",
        f"- Latest active default-branch workflow failures before bounded recovery: **{github['latest_failure_count_before']}** across **{github['repositories_with_latest_failures_before']}** repositories.",
        f"- Bounded rerun requests accepted: **{github['rerun_requested_count']}** of **{github['rerun_candidate_count']}** candidates.",
        f"- Accepted reruns completed green: **{github['rerun_success_count']}**; completed non-green: **{github['rerun_failure_count']}**; unsettled at deadline: **{github['rerun_unsettled_count']}**.",
        f"- Stalled latest workflow runs older than {STALL_HOURS} hours: **{github['stalled_workflow_count']}**. They were recorded, not force-cancelled.",
        f"- Hugging Face public estate: **{hub['counts'].get('models', 0)} models**, **{hub['counts'].get('datasets', 0)} datasets**, **{hub['counts'].get('spaces', 0)} Spaces**.",
        f"- Exact public GitHub↔Hub name relationships: **{hub['mapped_by_exact_public_name']} mapped**, **{hub['unmapped_by_exact_public_name']} explicitly unmapped**.",
        f"- Public probes reachable: **{surfaces['reachable_count']} of {surfaces['probe_count']}**; all reachable: **{surfaces['all_reachable']}**; primary/HF root byte-equal: **{surfaces['primary_and_canonical_root_byte_equal']}**.",
        "",
        "## Bounded recovery requests",
        "",
    ]
    if github["rerun_requests"]:
        for item in github["rerun_requests"]:
            label = "ACCEPTED" if item["requested"] else "REJECTED"
            post = ""
            if item["requested"]:
                post = (
                    f" · attempt `{item.get('post_attempt')}` · "
                    f"`{item.get('post_status')}` / `{item.get('post_conclusion')}`"
                )
            workflow = f" · `{item['workflow']}`" if item.get("workflow") else ""
            lines.append(
                f"- `{item['repository']}`{workflow} · run `{item['run_id']}` · **{label}**{post}"
            )
    else:
        lines.append("- No recent terminal failed latest default-branch run met the bounded rerun policy.")

    lines.extend(
        [
            "",
            "## Repository estate",
            "",
            "| Repository | Visibility | Open PRs | Workflows | Latest failures | Pending | Stalled | Protection | Active rulesets | Scan errors |",
            "|---|---:|---:|---:|---:|---:|---:|---|---:|---:|",
        ]
    )
    for item in github["repositories"]:
        failures = (
            len(item.get("failing_workflows") or [])
            if item["visibility"] == "public"
            else int(item.get("failing_workflow_count") or 0)
        )
        pending = (
            len(item.get("pending_workflows") or [])
            if item["visibility"] == "public"
            else int(item.get("pending_workflow_count") or 0)
        )
        stalled = (
            len(item.get("stalled_workflows") or [])
            if item["visibility"] == "public"
            else int(item.get("stalled_workflow_count") or 0)
        )
        protection = (item.get("protection") or {}).get("state")
        active_rulesets = (item.get("rulesets") or {}).get("active")
        lines.append(
            "| `{repository}` | {visibility} | {open_prs} | {workflows} | {failures} | "
            "{pending} | {stalled} | {protection} | {rulesets} | {errors} |".format(
                repository=item["repository"],
                visibility=item["visibility"],
                open_prs=item.get("open_pull_requests"),
                workflows=item.get("workflow_count"),
                failures=failures,
                pending=pending,
                stalled=stalled,
                protection=protection,
                rulesets=active_rulesets,
                errors=len(item.get("errors") or []),
            )
        )

    lines.extend(["", "## Public surface probes", ""])
    for item in surfaces["probes"]:
        lines.append(
            f"- `{item['url']}` → HTTP `{item['http_status']}` · bytes `{item['body_bytes']}` · SHA-256 `{item['body_sha256'] or 'UNAVAILABLE'}`"
        )
    lines.extend(
        [
            "",
            "## Execution boundary",
            "",
            "This pass uses GitHub and Hugging Face directly. It has no Replit dependency. It retries only recent terminal failed latest runs on active default branches, never force-cancels current work, never weakens branch protection or rulesets, never exposes credentials, never publishes model weights, and never infers private Hugging Face assets or model quality.",
            "",
        ]
    )
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    if not ORG_TOKEN:
        raise SystemExit("ORG_TOKEN unavailable; refusing partial organization claims")
    generated_at = iso()
    github = github_inventory()
    public_names = {
        item["repository"]
        for item in github["repositories"]
        if item["visibility"] == "public"
    }
    report = {
        "schema": "szl.native-org-convergence.v1",
        "generated_at": generated_at,
        "organization": ORG,
        "replit_dependency": False,
        "mode": "SCAN_EVERY_VISIBLE_REPOSITORY_AND_RERUN_BOUNDED_FAILURES",
        "privacy": {
            "private_repository_names_in_public_evidence": False,
            "private_workflow_names_in_public_evidence": False,
            "private_repositories_use_opaque_ordinals": True,
        },
        "github": github,
        "hugging_face": hugging_face_inventory(public_names),
        "surfaces": public_surfaces(),
    }
    write_reports(report)
    with _print_lock:
        print(
            json.dumps(
                {
                    "generated_at": generated_at,
                    "repository_count": github["repository_count"],
                    "private_repository_count": github["private_repository_count"],
                    "open_pull_request_count": github["open_pull_request_count"],
                    "latest_failure_count_before": github[
                        "latest_failure_count_before"
                    ],
                    "rerun_requested_count": github["rerun_requested_count"],
                    "rerun_success_count": github["rerun_success_count"],
                    "rerun_failure_count": github["rerun_failure_count"],
                    "hf_counts": report["hugging_face"]["counts"],
                    "public_probes_reachable": report["surfaces"]["reachable_count"],
                    "public_probe_count": report["surfaces"]["probe_count"],
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
