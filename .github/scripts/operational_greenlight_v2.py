#!/usr/bin/env python3
"""Drive the exact SZL public estate to an evidence-backed operational green state.

The controller is fail-closed and idempotent. It does not weaken reviews, checks,
branch protection, model promotion, or evidence semantics. It may dispatch already
installed protected workflows, publish bounded static deployment receipts to an
existing GitHub Pages source, set a public receipt URL repository variable, and
persist deterministic public issues.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

GITHUB_API = "https://api.github.com"
HF_BASE = "https://huggingface.co"
CONTROL_REPOSITORY = "szl-holdings/.github"
A11OY_REPOSITORY = "szl-holdings/a11oy"
GITHUB_ORG = "szl-holdings"
HF_ORG = "SZLHOLDINGS"
REPL_ID = "34870515-2d52-4ad8-9636-40cc3ced1771"
REPL_PAGE = "https://replit.com/@stephenlutar2/Unified-Control-Hub"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
URL_RE = re.compile(r"https://[A-Za-z0-9][A-Za-z0-9.-]*\.(?:replit\.app|repl\.co)(?::\d+)?", re.I)
RECEIPT_RE = re.compile(r"https://[^\s`\"'<>]+/api/szl/deployment-receipt(?:\?[^\s`\"'<>]*)?", re.I)
USER_AGENT = "szl-operational-greenlight-v2/1.0"
MAX_BODY = 4 * 1024 * 1024

SOURCE_PRS = (
    (CONTROL_REPOSITORY, 244),
    (CONTROL_REPOSITORY, 246),
    (CONTROL_REPOSITORY, 247),
    (CONTROL_REPOSITORY, 248),
    (A11OY_REPOSITORY, 1035),
    (A11OY_REPOSITORY, 1036),
)

WORKFLOWS = {
    "hf": (CONTROL_REPOSITORY, "hf-estate-official-api-v3.yml", {"publish": "true"}, 110 * 60),
    "state_plane": (A11OY_REPOSITORY, "state-plane-continuity-v2.yml", {}, 35 * 60),
    "nemo": (A11OY_REPOSITORY, "nemo-v3-preregister.yml", {}, 35 * 60),
    "sweep": (CONTROL_REPOSITORY, "org-pr-final-sweep.yml", {"execute": "true"}, 250 * 60),
}

ISSUE_TITLES = {
    "hf": "[hf-estate-report] official API publish and verification",
    "brain": "[brain-merge-report] A11oy PR 1003 exact scope",
    "replit": "[replit-deployment-receipt] Unified Control Hub",
    "sweep": "[org-pr-sweep] final reconciliation",
    "final": "[final-estate-reconciliation] SZL Holdings operational estate",
    "controller": "[operational-greenlight-v2] estate controller",
}

COMMAND_CENTERS = (
    "SZLHOLDINGS/a11oy",
    "SZLHOLDINGS/a11oy-clone-1",
    "SZLHOLDINGS/a11oy-clone-2",
    "SZLHOLDINGS/a11oy-clone-3",
    "SZLHOLDINGS/a11oy-clone-4",
)

BRAIN_EXPECTED_FILES = {
    "Dockerfile",
    "execution/brain/BRAIN_ARCHITECTURE.md",
    "execution/brain/CLAIM_EVIDENCE_LEDGER.csv",
    "execution/brain/CONNECTOR_REGISTRY.csv",
    "execution/brain/CONTINUOUS_LEARNING_PROTOCOL.md",
    "execution/brain/CONTRADICTION_ENGINE.md",
    "execution/brain/CURRENT_IMPLEMENTATION_AUDIT.md",
    "execution/brain/ECOSYSTEM_PROPAGATION.md",
    "execution/brain/FORGETTING_SPECIFICATION.md",
    "execution/brain/INDEPENDENT_VERIFICATION.md",
    "execution/brain/KNOWLEDGE_GRAPH_SCHEMA.md",
    "execution/brain/LEARNING_EXPERIMENTS.csv",
    "execution/brain/LIVE_DEPLOYMENT_EVIDENCE.md",
    "execution/brain/MEMORY_ADMISSION_POLICY.md",
    "execution/brain/MEMORY_BENCHMARK.md",
    "execution/brain/MEMORY_SCHEMA.json",
    "execution/brain/MEMORY_SCOPE_POLICY.md",
    "execution/brain/MEMORY_SECURITY_THREAT_MODEL.md",
    "execution/brain/OPERATIONAL_DEMONSTRATION.md",
    "execution/brain/QUANTUM_EVIDENCE_PLANE.md",
    "execution/brain/RESIDUAL_RISK.md",
    "execution/brain/RETRIEVAL_ARCHITECTURE.md",
    "execution/brain/RETRIEVAL_BENCHMARK.md",
    "execution/brain/SECURITY_RESULTS.md",
    "execution/brain/VERTICAL_SLICE_PLAN.md",
    "execution/brain/research/LEADER_MATRIX.csv",
    "execution/brain/research/LICENSE_LEDGER.csv",
    "execution/brain/research/ORIGINAL_DIFFERENTIATION.md",
    "execution/brain/research/PRINCIPLE_SYNTHESIS.md",
    "execution/brain/research/QUANTUM_FRONTIER_LEADERS.csv",
    "execution/brain/research/REJECTED_PATTERNS.md",
    "execution/brain/research/TRANSACTIONAL_ENERGY_PAPER_SYNTHESIS.md",
    "serve.py",
    "szl_brain_capabilities.py",
    "szl_brain_memory_schema.py",
    "szl_brain_quantum_evidence.py",
    "tests/test_brain_capabilities.py",
    "tests/test_brain_memory_schema.py",
    "tests/test_brain_quantum_evidence.py",
}
BRAIN_ORIGINAL_COMMIT = "12e48dfa683ee3ed279a90a2738c2519a0ce5df5"

DOMAIN_SPECS = {
    "a-11-oy.com": [
        "/api/a11oy/readyz?view=summary",
        "/api/a11oy/readyz",
        "/api/deployment-receipt.json",
        "/deployment-receipt.json",
        "/",
    ],
    "a11oy.net": [
        "/api/deployment-receipt.json",
        "/deployment-receipt.json",
        "/",
    ],
}


class GateError(RuntimeError):
    """Evidence or supported API contract failure."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def immutable_sha(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if SHA_RE.fullmatch(text) else None


def github_request(
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    allow_status: set[int] | None = None,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        GITHUB_API + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": USER_AGENT,
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if allow_status and exc.code in allow_status:
            return None
        detail = exc.read().decode("utf-8", "replace")[:8000]
        raise GateError(f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise GateError(f"GitHub API {method} {path} failed: {type(exc).__name__}: {exc}") from exc
    return json.loads(raw.decode("utf-8")) if raw else None


def github_paginate(token: str, path: str, max_pages: int = 100) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    separator = "&" if "?" in path else "?"
    for page in range(1, max_pages + 1):
        payload = github_request(token, "GET", f"{path}{separator}per_page=100&page={page}")
        if not isinstance(payload, list):
            raise GateError(f"GitHub pagination returned non-list for {path}")
        output.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return output
    raise GateError(f"GitHub pagination exceeded {max_pages} pages for {path}")


def public_request(
    url: str,
    *,
    token: str | None = None,
    method: str = "GET",
    timeout: float = 45.0,
) -> dict[str, Any]:
    if method not in {"GET", "HEAD"}:
        raise GateError(f"public verifier forbids method {method!r}")
    headers = {
        "Accept": "application/json, text/plain;q=0.9, text/html;q=0.5",
        "Cache-Control": "no-cache",
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, method=method, headers=headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
            context=ssl.create_default_context(),
        ) as response:
            body = b"" if method == "HEAD" else response.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                body = body[:MAX_BODY]
            content_type = str(response.headers.get("Content-Type") or "")
            payload: Any = None
            if body and ("json" in content_type.lower() or body.lstrip()[:1] in {b"{", b"["}):
                try:
                    payload = json.loads(body.decode("utf-8", "replace"))
                except json.JSONDecodeError:
                    payload = None
            return {
                "ok": 200 <= int(response.status) < 400,
                "status": int(response.status),
                "requested_url": url,
                "url": response.geturl(),
                "method": method,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "content_type": content_type,
                "body": body.decode("utf-8", "replace") if body else "",
                "json": payload,
                "headers": {
                    key.lower(): value
                    for key, value in response.headers.items()
                    if key.lower() in {"etag", "last-modified", "cache-control", "content-type", "server"}
                },
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read(8192)
        return {
            "ok": False,
            "status": int(exc.code),
            "requested_url": url,
            "url": url,
            "method": method,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "content_type": str(exc.headers.get("Content-Type") or ""),
            "body": body.decode("utf-8", "replace"),
            "json": None,
            "headers": {},
            "error": f"HTTPError: {exc.code}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "status": 0,
            "requested_url": url,
            "url": url,
            "method": method,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "content_type": "",
            "body": "",
            "json": None,
            "headers": {},
            "error": f"{type(exc).__name__}: {exc}",
        }


def clean_probe(probe: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in probe.items() if key not in {"body", "json"}}


def walk_values(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk_values(child, (*path, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_values(child, (*path, str(index)))
    else:
        yield path, value


def revisions_from_payload(payload: Any) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    if not isinstance(payload, (dict, list)):
        return output
    for path, value in walk_values(payload):
        if not path:
            continue
        key = path[-1].lower().replace("-", "_")
        sha = immutable_sha(value)
        if sha and ("sha" in key or "revision" in key or "commit" in key):
            rendered = ".".join(path)
            marker = (rendered, sha)
            if marker not in seen:
                seen.add(marker)
                output.append({"path": rendered, "sha": sha})
    return output


def issue_inventory(token: str) -> list[dict[str, Any]]:
    return github_paginate(
        token,
        f"/repos/{CONTROL_REPOSITORY}/issues?state=all&sort=updated&direction=desc",
        max_pages=15,
    )


def issue_by_title(token: str, title: str) -> dict[str, Any] | None:
    for issue in issue_inventory(token):
        if issue.get("pull_request"):
            continue
        if str(issue.get("title") or "") == title:
            return issue
    return None


def parse_fenced_json(body: str) -> dict[str, Any] | None:
    fences = re.findall(r"```json\s*(.*?)\s*```", body, flags=re.I | re.S)
    for candidate in reversed(fences):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def durable_report(token: str, title: str) -> dict[str, Any] | None:
    issue = issue_by_title(token, title)
    if not issue:
        return None
    report = parse_fenced_json(str(issue.get("body") or ""))
    if isinstance(report, dict):
        report = dict(report)
        report["_issue"] = {
            "number": issue.get("number"),
            "url": issue.get("html_url"),
            "state": issue.get("state"),
            "updated_at": issue.get("updated_at"),
        }
    return report


def upsert_issue(
    token: str,
    title: str,
    report: dict[str, Any],
    *,
    heading: str,
    close: bool = False,
    showcase: str | None = None,
) -> dict[str, Any]:
    body_parts = [f"<!-- {hashlib.sha256(title.encode()).hexdigest()[:16]} -->", f"# {heading}", ""]
    if showcase:
        body_parts.extend([showcase.rstrip(), ""])
    body_parts.extend(["```json", json.dumps(report, indent=2, sort_keys=True), "```", ""])
    body = "\n".join(body_parts)
    current = issue_by_title(token, title)
    if current:
        issue = github_request(
            token,
            "PATCH",
            f"/repos/{CONTROL_REPOSITORY}/issues/{current['number']}",
            {"body": body, "state": "closed" if close else "open"},
        )
    else:
        issue = github_request(
            token,
            "POST",
            f"/repos/{CONTROL_REPOSITORY}/issues",
            {"title": title, "body": body},
        )
        if close:
            issue = github_request(
                token,
                "PATCH",
                f"/repos/{CONTROL_REPOSITORY}/issues/{issue['number']}",
                {"state": "closed"},
            )
    return {
        "number": issue.get("number"),
        "url": issue.get("html_url"),
        "state": issue.get("state"),
    }


def set_repository_variable(token: str, repository: str, name: str, value: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(name, safe="")
    current = github_request(
        token,
        "GET",
        f"/repos/{repository}/actions/variables/{encoded}",
        allow_status={404},
    )
    payload = {"name": name, "value": value}
    if current is None:
        github_request(token, "POST", f"/repos/{repository}/actions/variables", payload)
        action = "created"
    elif str(current.get("value") or "") != value:
        github_request(token, "PATCH", f"/repos/{repository}/actions/variables/{encoded}", payload)
        action = "updated"
    else:
        action = "unchanged"
    return {"repository": repository, "name": name, "action": action, "value": value}


def source_pr_state(token: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for repository, number in SOURCE_PRS:
        pr = github_request(token, "GET", f"/repos/{repository}/pulls/{number}")
        rows.append(
            {
                "repository": repository,
                "pull_request": number,
                "url": pr.get("html_url"),
                "title": pr.get("title"),
                "state": pr.get("state"),
                "merged": bool(pr.get("merged")),
                "merged_at": pr.get("merged_at"),
                "head_sha": ((pr.get("head") or {}).get("sha")),
                "merge_sha": pr.get("merge_commit_sha"),
            }
        )
    return {"ok": all(row["merged"] for row in rows), "pull_requests": rows}


def dispatch_workflow(token: str, key: str) -> dict[str, Any]:
    repository, workflow, inputs, timeout_seconds = WORKFLOWS[key]
    encoded = urllib.parse.quote(workflow, safe="")
    started = datetime.now(timezone.utc)
    payload: dict[str, Any] = {"ref": "main"}
    if inputs:
        payload["inputs"] = inputs
    github_request(
        token,
        "POST",
        f"/repos/{repository}/actions/workflows/{encoded}/dispatches",
        payload,
    )
    return {
        "key": key,
        "repository": repository,
        "workflow": workflow,
        "started_at": started.isoformat(),
        "timeout_seconds": timeout_seconds,
    }


def parse_time(value: Any) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def wait_workflow(token: str, record: dict[str, Any], *, require_success: bool = False) -> dict[str, Any]:
    repository = record["repository"]
    workflow = record["workflow"]
    encoded = urllib.parse.quote(workflow, safe="")
    started = parse_time(record["started_at"]) - timedelta(seconds=10)
    deadline = time.monotonic() + int(record["timeout_seconds"])
    selected: dict[str, Any] | None = None
    while True:
        payload = github_request(
            token,
            "GET",
            f"/repos/{repository}/actions/workflows/{encoded}/runs?branch=main&event=workflow_dispatch&per_page=30",
            allow_status={404},
        )
        runs = payload.get("workflow_runs") if isinstance(payload, dict) else []
        candidates = [run for run in runs or [] if parse_time(run.get("created_at")) >= started]
        if candidates:
            candidates.sort(key=lambda run: parse_time(run.get("created_at")), reverse=True)
            selected = candidates[0]
            if selected.get("status") == "completed":
                result = {
                    "key": record["key"],
                    "repository": repository,
                    "workflow": workflow,
                    "run_id": selected.get("id"),
                    "url": selected.get("html_url"),
                    "head_sha": selected.get("head_sha"),
                    "event": selected.get("event"),
                    "status": selected.get("status"),
                    "conclusion": selected.get("conclusion"),
                    "created_at": selected.get("created_at"),
                    "updated_at": selected.get("updated_at"),
                    "ok": selected.get("conclusion") == "success",
                }
                if require_success and not result["ok"]:
                    raise GateError(f"{repository}/{workflow} concluded {result['conclusion']}; {result['url']}")
                return result
        if time.monotonic() >= deadline:
            raise GateError(f"timeout waiting for {repository}/{workflow}; latest={selected}")
        time.sleep(20)


def execute_workflow(token: str, key: str, *, require_success: bool = False) -> dict[str, Any]:
    return wait_workflow(token, dispatch_workflow(token, key), require_success=require_success)


def hf_get(token: str, path: str) -> dict[str, Any]:
    probe = public_request(HF_BASE + path, token=token, timeout=60)
    if not probe.get("ok") or not isinstance(probe.get("json"), (dict, list)):
        raise GateError(f"Hugging Face API failed for {path}: {probe.get('status')} {probe.get('error')}")
    return probe


def hf_tree(token: str, repo_id: str) -> dict[str, str]:
    encoded = "/".join(urllib.parse.quote(part, safe="") for part in repo_id.split("/"))
    probe = hf_get(token, f"/api/spaces/{encoded}/tree/main?recursive=true&expand=false")
    payload = probe["json"]
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        payload = payload["items"]
    if not isinstance(payload, list):
        raise GateError(f"Space tree is not a list for {repo_id}")
    mapping: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict) or str(item.get("type") or "file").lower() in {"directory", "dir", "folder"}:
            continue
        path = str(item.get("path") or "")
        lfs = item.get("lfs") or {}
        identity = str(lfs.get("sha256") or item.get("oid") or item.get("blob_id") or "")
        if path and identity and path not in {".gitattributes", "SZL_ESTATE_MANAGED.json"}:
            mapping[path] = identity
    return mapping


def verify_command_centers(hf_token: str) -> dict[str, Any]:
    snapshots: dict[str, Any] = {}
    errors: list[str] = []
    canonical: dict[str, str] | None = None
    for repo_id in COMMAND_CENTERS:
        encoded = "/".join(urllib.parse.quote(part, safe="") for part in repo_id.split("/"))
        try:
            metadata = hf_get(hf_token, f"/api/spaces/{encoded}")["json"]
            if not isinstance(metadata, dict):
                raise GateError("metadata is not an object")
            runtime = metadata.get("runtime") or {}
            stage = str(runtime.get("stage") or runtime.get("status") or "UNKNOWN").split(".")[-1].upper()
            sha = immutable_sha(metadata.get("sha"))
            private = metadata.get("private")
            hardware = str(runtime.get("hardware") or runtime.get("currentHardware") or "")
            requested = str(runtime.get("requestedHardware") or runtime.get("requested_hardware") or "")
            files = hf_tree(hf_token, repo_id)
            snapshots[repo_id] = {
                "sha": sha,
                "stage": stage,
                "private": private,
                "hardware": hardware,
                "requested_hardware": requested,
                "managed_file_count": len(files),
            }
            if not sha:
                errors.append(f"{repo_id} lacks immutable revision")
            if stage != "RUNNING":
                errors.append(f"{repo_id} stage={stage}, not RUNNING")
            if private is not False:
                errors.append(f"{repo_id} is not confirmed public")
            if canonical is None:
                canonical = files
            elif files != canonical:
                missing = sorted(set(canonical) - set(files))[:20]
                extra = sorted(set(files) - set(canonical))[:20]
                differing = sorted(path for path in set(files) & set(canonical) if files[path] != canonical[path])[:20]
                errors.append(
                    f"{repo_id} differs from canonical: missing={missing}; extra={extra}; differing={differing}"
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{repo_id}: {type(exc).__name__}: {exc}")
    return {"ok": not errors, "snapshots": snapshots, "errors": errors}


def nested_values(value: Any, keys: set[str]) -> list[Any]:
    output: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in keys:
                output.append(child)
            output.extend(nested_values(child, keys))
    elif isinstance(value, list):
        for child in value:
            output.extend(nested_values(child, keys))
    return output


def hf_report_state(token: str) -> dict[str, Any]:
    report = durable_report(token, ISSUE_TITLES["hf"])
    command_centers = verify_command_centers(os.environ.get("HF_ORG_TOKEN", "").strip() or os.environ.get("HF_ORG_TOKEN1", "").strip() or os.environ.get("HF_TOKEN", "").strip())
    if not isinstance(report, dict):
        return {
            "ok": False,
            "publish": False,
            "zero_errors": False,
            "collections_resolve": False,
            "buckets_readable": False,
            "command_centers": command_centers,
            "report": None,
            "errors": ["durable Hugging Face report is unavailable"],
        }
    publish = report.get("publish") is True
    error_values = nested_values(report, {"error", "errors", "error_count"})
    numeric_errors = []
    textual_errors = []
    for item in error_values:
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            numeric_errors.append(int(item))
        elif isinstance(item, list):
            textual_errors.extend(str(value) for value in item if str(value).strip())
        elif isinstance(item, str) and item.strip() and item.strip().lower() not in {"0", "none", "null", "[]"}:
            textual_errors.append(item.strip())
    zero_errors = not any(value > 0 for value in numeric_errors) and not textual_errors

    reference_totals = nested_values(report, {"references", "collection_references"})
    collections_resolve = False
    for value in reference_totals:
        if isinstance(value, dict):
            total = value.get("total")
            resolving = value.get("resolving") or value.get("resolved")
            if isinstance(total, int) and isinstance(resolving, int) and total == resolving:
                collections_resolve = True
    if not reference_totals:
        collections_resolve = bool(report.get("collections_verified"))

    bucket_values = nested_values(report, {"buckets", "bucket_verification"})
    buckets_readable = False
    for value in bucket_values:
        if isinstance(value, dict):
            if value.get("ok") is True:
                buckets_readable = True
            errors = value.get("errors")
            if isinstance(errors, list) and not errors and (value.get("count", 0) > 0 or value.get("buckets")):
                buckets_readable = True
    if not bucket_values:
        buckets_readable = bool(report.get("buckets_verified"))

    errors: list[str] = []
    if not publish:
        errors.append("publish mode is not true")
    if not zero_errors:
        errors.append(f"report exposes errors: numeric={numeric_errors}; text={textual_errors[:10]}")
    if not collections_resolve:
        errors.append("collection references are not proven fully resolving")
    if not buckets_readable:
        errors.append("buckets are not proven readable")
    if not command_centers.get("ok"):
        errors.extend(command_centers.get("errors") or [])
    return {
        "ok": not errors,
        "publish": publish,
        "zero_errors": zero_errors,
        "collections_resolve": collections_resolve,
        "buckets_readable": buckets_readable,
        "command_centers": command_centers,
        "report": report,
        "errors": errors,
    }


def exact_brain_files(token: str) -> list[str]:
    files = github_paginate(token, f"/repos/{A11OY_REPOSITORY}/pulls/1003/files", max_pages=2)
    observed = {str(item.get("filename") or "") for item in files}
    if observed != BRAIN_EXPECTED_FILES:
        raise GateError(
            f"Brain scope differs: missing={sorted(BRAIN_EXPECTED_FILES - observed)}; extra={sorted(observed - BRAIN_EXPECTED_FILES)}"
        )
    return sorted(observed)


def brain_state(token: str) -> dict[str, Any]:
    errors: list[str] = []
    pr = github_request(token, "GET", f"/repos/{A11OY_REPOSITORY}/pulls/1003")
    head_sha = immutable_sha(((pr.get("head") or {}).get("sha")))
    merged = bool(pr.get("merged"))
    merged_at = pr.get("merged_at")
    merge_sha = immutable_sha(pr.get("merge_commit_sha"))
    files: list[str] = []
    ancestry: dict[str, Any] | None = None
    try:
        files = exact_brain_files(token)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{type(exc).__name__}: {exc}")
    if head_sha:
        comparison = github_request(
            token,
            "GET",
            f"/repos/{A11OY_REPOSITORY}/compare/{BRAIN_ORIGINAL_COMMIT}...{head_sha}",
        )
        ancestry = {
            "status": comparison.get("status"),
            "ahead_by": comparison.get("ahead_by"),
            "behind_by": comparison.get("behind_by"),
        }
        if comparison.get("status") not in {"ahead", "identical"}:
            errors.append(f"original evidence commit is not in head ancestry: {ancestry}")
    else:
        errors.append("Brain PR head is not an immutable SHA")
    if not merged or not merged_at or not merge_sha:
        errors.append("Brain PR #1003 is not proven merged with immutable merge metadata")

    routes: dict[str, Any] = {}
    for path in ("/api/a11oy/v1/brain/capabilities", "/api/a11oy/v1/brain/info"):
        probe = public_request("https://szlholdings-a11oy.hf.space" + path, timeout=60)
        routes[path] = clean_probe(probe)
        if not probe.get("ok"):
            errors.append(f"Brain route {path} is not live: {probe.get('status')} {probe.get('error')}")
    report = {
        "schema": "szl.brain-pr-1003-final-proof/v2",
        "generated_at": now(),
        "repository": A11OY_REPOSITORY,
        "pull_request": 1003,
        "head_sha": head_sha,
        "merge_sha": merge_sha,
        "merged_at": merged_at,
        "files": files,
        "ancestry": ancestry,
        "live_routes": routes,
        "ok": not errors,
        "errors": errors,
        "boundary": "Operational Brain routes and evidence-backed capability files do not establish a fully trained neural Brain model.",
    }
    report["durable_issue"] = upsert_issue(
        token,
        ISSUE_TITLES["brain"],
        report,
        heading="A11oy Brain PR #1003 — exact merged scope and live routes",
        close=report["ok"],
    )
    return report


def replit_candidate_origins(token: str) -> list[str]:
    candidates = {
        "https://unified-control-hub-stephenlutar2.replit.app",
        "https://unified-control-hub--stephenlutar2.repl.co",
        "https://unified-control-hub-stephenlutar2.repl.co",
        "https://unified-control-hub.stephenlutar2.repl.co",
    }
    issue = issue_by_title(token, ISSUE_TITLES["replit"])
    texts = [str((issue or {}).get("body") or "")]
    for url in (REPL_PAGE, f"https://replit.com/data/repls/{REPL_ID}", f"https://replit.com/api/v1/repls/{REPL_ID}"):
        probe = public_request(url, timeout=60)
        texts.append(str(probe.get("body") or ""))
        if isinstance(probe.get("json"), (dict, list)):
            texts.append(json.dumps(probe["json"]))
    for text in texts:
        for match in URL_RE.findall(text):
            candidates.add(match.rstrip("/"))
        for match in RECEIPT_RE.findall(text):
            parsed = urllib.parse.urlsplit(match)
            candidates.add(f"{parsed.scheme}://{parsed.netloc}")
    return sorted(candidates)


def verify_replit_receipt(url: str) -> dict[str, Any]:
    get_probe = public_request(url, method="GET", timeout=60)
    head_probe = public_request(url, method="HEAD", timeout=60)
    payload = get_probe.get("json") if isinstance(get_probe.get("json"), dict) else {}
    source_sha = immutable_sha(payload.get("source_revision") or payload.get("source_sha") or payload.get("commit_sha"))
    deployment_sha = immutable_sha(
        payload.get("deployment_revision") or payload.get("deployment_sha") or payload.get("deployed_revision")
    )
    production_url = str(payload.get("production_url") or payload.get("url") or "").strip() or None
    tests = payload.get("tests") or payload.get("test_results")
    mobile = payload.get("mobile") or payload.get("mobile_probes")
    readiness = payload.get("readiness") or payload.get("readiness_probes")
    production_get = public_request(production_url, method="GET", timeout=60) if production_url else None
    production_head = public_request(production_url, method="HEAD", timeout=60) if production_url else None
    missing: list[str] = []
    if not get_probe.get("ok"):
        missing.append("receipt GET")
    if not head_probe.get("ok"):
        missing.append("receipt HEAD")
    if not source_sha:
        missing.append("immutable source revision")
    if not deployment_sha:
        missing.append("immutable deployment revision")
    if not production_url or not production_url.startswith("https://"):
        missing.append("production URL")
    if not tests:
        missing.append("test receipt")
    if not mobile:
        missing.append("mobile/keyboard receipt")
    if not readiness:
        missing.append("readiness GET/HEAD receipt")
    if production_get and not production_get.get("ok"):
        missing.append("production GET")
    if production_head and not production_head.get("ok"):
        missing.append("production HEAD")
    return {
        "ok": not missing,
        "receipt_url": url,
        "source_revision": source_sha,
        "deployment_revision": deployment_sha,
        "production_url": production_url,
        "deployed_at": payload.get("deployed_at"),
        "tests": tests,
        "mobile": mobile,
        "readiness": readiness,
        "receipt_get": clean_probe(get_probe),
        "receipt_head": clean_probe(head_probe),
        "production_get": None if production_get is None else clean_probe(production_get),
        "production_head": None if production_head is None else clean_probe(production_head),
        "public_receipt": payload,
        "missing": missing,
    }


def discover_replit(token: str) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    issue = issue_by_title(token, ISSUE_TITLES["replit"])
    direct_urls: list[str] = []
    if issue:
        direct_urls.extend(RECEIPT_RE.findall(str(issue.get("body") or "")))
        report = parse_fenced_json(str(issue.get("body") or ""))
        if isinstance(report, dict):
            direct_urls.extend(
                str(value)
                for value in (report.get("receipt_url"), report.get("deployment_receipt_url"))
                if value
            )
    for origin in replit_candidate_origins(token):
        handoff = public_request(origin.rstrip("/") + "/REPLIT_DEPLOYMENT_RECEIPT_URL.txt", timeout=60)
        if handoff.get("ok"):
            for line in str(handoff.get("body") or "").splitlines():
                if line.strip().startswith("https://") and "/api/szl/deployment-receipt" in line:
                    direct_urls.insert(0, line.strip())
                    break
        direct_urls.append(origin.rstrip("/") + "/api/szl/deployment-receipt")
    for url in dict.fromkeys(text.strip().rstrip(".,;)") for text in direct_urls if str(text).startswith("https://")):
        result = verify_replit_receipt(url)
        attempts.append({"receipt_url": url, "ok": result["ok"], "missing": result["missing"]})
        if result["ok"]:
            result["repository_variables"] = [
                set_repository_variable(token, CONTROL_REPOSITORY, "REPLIT_DEPLOYMENT_RECEIPT_URL", url),
                set_repository_variable(token, A11OY_REPOSITORY, "REPLIT_DEPLOYMENT_RECEIPT_URL", url),
            ]
            result["durable_issue"] = upsert_issue(
                token,
                ISSUE_TITLES["replit"],
                result["public_receipt"],
                heading="Unified Control Hub deployment receipt",
                close=True,
                showcase=f"Receipt URL: {url}\n\nProduction URL: {result['production_url']}",
            )
            result["attempts"] = attempts
            return result
    pending = {
        "schema": "szl.replit-deployment-receipt/v2",
        "generated_at": now(),
        "repl_id": REPL_ID,
        "ok": False,
        "state": "OPEN_UNVERIFIED",
        "attempts": attempts,
        "missing": ["complete public deployment receipt"],
    }
    pending["durable_issue"] = upsert_issue(
        token,
        ISSUE_TITLES["replit"],
        pending,
        heading="Unified Control Hub deployment receipt",
        close=False,
    )
    return pending


def current_open_prs(token: str) -> list[dict[str, Any]]:
    repos = github_paginate(token, f"/orgs/{GITHUB_ORG}/repos?type=all&sort=full_name&direction=asc")
    output: list[dict[str, Any]] = []
    for repo in repos:
        if repo.get("archived") or repo.get("disabled"):
            continue
        name = str(repo.get("full_name") or "")
        if not name:
            continue
        for pr in github_paginate(token, f"/repos/{name}/pulls?state=open&sort=updated&direction=desc"):
            output.append(
                {
                    "repository": name,
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "url": pr.get("html_url"),
                    "draft": pr.get("draft"),
                    "head_sha": ((pr.get("head") or {}).get("sha")),
                    "base": ((pr.get("base") or {}).get("ref")),
                    "updated_at": pr.get("updated_at"),
                }
            )
    return output


def sweep_coverage(token: str) -> dict[str, Any]:
    current = current_open_prs(token)
    report = durable_report(token, ISSUE_TITLES["sweep"])
    if not isinstance(report, dict):
        return {"ok": False, "current_open_prs": current, "report": None, "missing": current, "unhandled": []}
    records = report.get("pull_requests") or []
    indexed = {
        (str(item.get("repository") or ""), int(item.get("pull_request") or 0)): item
        for item in records
        if isinstance(item, dict)
    }
    accepted = {
        "left-open",
        "updated-branch-waiting-checks",
        "merged",
        "closed",
        "no-longer-open",
        "would-update-branch",
        "would-merge",
        "would-close",
    }
    missing = [
        item for item in current
        if (item["repository"], int(item["number"] or 0)) not in indexed
    ]
    handled = [
        indexed[(item["repository"], int(item["number"] or 0))]
        for item in current
        if (item["repository"], int(item["number"] or 0)) in indexed
    ]
    unhandled = [item for item in handled if item.get("action") not in accepted]
    summary = report.get("summary") or {}
    return {
        "ok": not missing and not unhandled and summary.get("pull_request_errors", 0) == 0 and summary.get("repository_errors", 0) == 0,
        "current_open_prs": current,
        "covered": len(handled),
        "missing": missing,
        "unhandled": unhandled,
        "report": report,
    }


def github_branch_head(token: str, repository: str, branch: str) -> str:
    encoded = urllib.parse.quote(branch, safe="")
    ref = github_request(token, "GET", f"/repos/{repository}/git/ref/heads/{encoded}")
    sha = immutable_sha(((ref.get("object") or {}).get("sha")))
    if not sha:
        raise GateError(f"cannot resolve {repository}:{branch}")
    return sha


def pages_sites(token: str) -> list[dict[str, Any]]:
    repos = github_paginate(token, f"/orgs/{GITHUB_ORG}/repos?type=all&sort=full_name&direction=asc")
    output: list[dict[str, Any]] = []
    for repo in repos:
        if repo.get("archived") or repo.get("disabled"):
            continue
        name = str(repo.get("full_name") or "")
        if not name:
            continue
        pages = github_request(token, "GET", f"/repos/{name}/pages", allow_status={404})
        if isinstance(pages, dict):
            output.append(
                {
                    "repository": name,
                    "html_url": pages.get("html_url"),
                    "cname": pages.get("cname"),
                    "build_type": pages.get("build_type"),
                    "source": pages.get("source"),
                    "status": pages.get("status"),
                }
            )
    return output


def contents_file(token: str, repository: str, path: str, ref: str) -> dict[str, Any] | None:
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
    payload = github_request(
        token,
        "GET",
        f"/repos/{repository}/contents/{encoded_path}?ref={urllib.parse.quote(ref, safe='')}",
        allow_status={404},
    )
    return payload if isinstance(payload, dict) else None


def put_contents(
    token: str,
    repository: str,
    branch: str,
    path: str,
    content: str,
    message: str,
) -> dict[str, Any]:
    current = contents_file(token, repository, path, branch)
    payload: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    if current and current.get("sha"):
        payload["sha"] = current["sha"]
    result = github_request(
        token,
        "PUT",
        f"/repos/{repository}/contents/{'/'.join(urllib.parse.quote(part, safe='') for part in path.split('/'))}",
        payload,
    )
    return {
        "repository": repository,
        "branch": branch,
        "path": path,
        "commit_sha": ((result.get("commit") or {}).get("sha")),
        "content_sha": ((result.get("content") or {}).get("sha")),
    }


def domain_probe(domain: str) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for path in DOMAIN_SPECS[domain]:
        probe = public_request("https://" + domain + path, timeout=60)
        revisions = revisions_from_payload(probe.get("json"))
        attempts.append(
            {
                "path": path,
                "probe": clean_probe(probe),
                "revisions": revisions,
            }
        )
        if probe.get("ok") and revisions:
            return {
                "ok": True,
                "domain": domain,
                "selected_path": path,
                "selected_url": probe.get("url"),
                "revisions": revisions,
                "attempts": attempts,
            }
    return {"ok": False, "domain": domain, "selected_path": None, "revisions": [], "attempts": attempts}


def ensure_pages_receipt(token: str, domain: str, site: dict[str, Any]) -> dict[str, Any]:
    current = domain_probe(domain)
    if current.get("ok"):
        return {"action": "already-attested", "site": site, "probe": current, "ok": True}
    source = site.get("source") or {}
    branch = str(source.get("branch") or "")
    folder = str(source.get("path") or "/")
    if not branch:
        return {
            "action": "unsupported-pages-build-type",
            "site": site,
            "probe": current,
            "ok": False,
            "error": "Pages source branch is unavailable; receipt publication requires the existing Actions deployment lane",
        }
    source_revision = github_branch_head(token, site["repository"], branch)
    prefix = "" if folder in {"", "/"} else folder.strip("/") + "/"
    receipt_path = prefix + "deployment-receipt.json"
    api_path = prefix + "api/deployment-receipt.json"
    receipt = {
        "schema": "szl.public-domain-deployment-receipt/v1",
        "generated_at": now(),
        "domain": domain,
        "repository": site["repository"],
        "source_branch": branch,
        "source_revision": source_revision,
        "pages_source_path": folder,
        "verification_boundary": "The immutable source revision is the Pages source head observed immediately before this bounded receipt-only commit.",
    }
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    writes = [
        put_contents(
            token,
            site["repository"],
            branch,
            receipt_path,
            rendered,
            f"docs(receipt): bind {domain} to immutable source\n\nSigned-off-by: Stephen Lutar <stephenlutar2@gmail.com>",
        ),
        put_contents(
            token,
            site["repository"],
            branch,
            api_path,
            rendered,
            f"docs(receipt): expose {domain} API receipt\n\nSigned-off-by: Stephen Lutar <stephenlutar2@gmail.com>",
        ),
    ]
    deadline = time.monotonic() + 25 * 60
    latest = current
    while time.monotonic() < deadline:
        time.sleep(30)
        latest = domain_probe(domain)
        if latest.get("ok"):
            return {"action": "published", "site": site, "writes": writes, "probe": latest, "ok": True}
    return {
        "action": "published-not-yet-attested",
        "site": site,
        "writes": writes,
        "probe": latest,
        "ok": False,
    }


def domain_states(token: str) -> dict[str, Any]:
    sites = pages_sites(token)
    by_domain: dict[str, dict[str, Any]] = {}
    for site in sites:
        for value in (site.get("cname"), site.get("html_url")):
            text = str(value or "").lower()
            for domain in DOMAIN_SPECS:
                if domain in text:
                    by_domain[domain] = site
    results: dict[str, Any] = {}
    for domain in DOMAIN_SPECS:
        current = domain_probe(domain)
        if current.get("ok"):
            results[domain] = {"ok": True, "action": "already-attested", "probe": current}
        elif domain in by_domain:
            results[domain] = ensure_pages_receipt(token, domain, by_domain[domain])
        else:
            results[domain] = {
                "ok": False,
                "action": "non-pages-plane-unattested",
                "probe": current,
                "pages_sites_considered": sites,
                "error": "The domain did not expose a revision and is not an existing GitHub Pages custom domain discoverable through the supported API.",
            }
    return {"ok": all(item.get("ok") for item in results.values()), "domains": results, "pages_sites": sites}


def github_json_file(token: str, repository: str, path: str, ref: str = "main") -> dict[str, Any] | None:
    current = contents_file(token, repository, path, ref)
    if not current or current.get("encoding") != "base64":
        return None
    raw = base64.b64decode(str(current.get("content") or ""))
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"json": None, "error": f"{type(exc).__name__}: {exc}", "sha": current.get("sha")}
    return {"json": value, "error": None, "sha": current.get("sha")}


def nemo_state(token: str) -> dict[str, Any]:
    policy = github_json_file(token, A11OY_REPOSITORY, "execution/models/szl-nemo-v3/candidate_policy.json")
    binding = github_json_file(token, A11OY_REPOSITORY, "execution/models/szl-nemo-v3/v2_holdout_binding.json")
    errors: list[str] = []
    policy_json = (policy or {}).get("json") if isinstance(policy, dict) else None
    binding_json = (binding or {}).get("json") if isinstance(binding, dict) else None
    if not isinstance(policy_json, dict):
        errors.append("candidate policy is absent from protected main")
    else:
        if policy_json.get("state") != "PRETRAINING_PREREGISTERED_NOT_TRAINED":
            errors.append(f"candidate state is {policy_json.get('state')!r}")
        promotion = policy_json.get("promotion") or {}
        for key in (
            "signing_before_promotion_review",
            "upload_before_promotion_review",
            "publication_before_promotion_review",
            "deployment_before_promotion_review",
        ):
            if promotion.get(key) is not False:
                errors.append(f"promotion boundary {key} is not false")
    if not isinstance(binding_json, dict):
        errors.append("exact v2 holdout binding is absent from protected main")
    else:
        v2 = binding_json.get("v2") or {}
        if (v2.get("original_holdout") or {}).get("records") != 8:
            errors.append("original v2 holdout is not exactly 8 records")
        if (v2.get("shadow_holdout") or {}).get("records") != 10:
            errors.append("shadow v2 holdout is not exactly 10 records")
        if v2.get("contents_copied_into_v3") is not False:
            errors.append("holdout payload isolation is not preserved")
    return {
        "ok": not errors,
        "state": "PRETRAINING_PREREGISTERED_NOT_TRAINED" if not errors else "UNVERIFIED",
        "trained": False,
        "promoted": False,
        "policy": policy,
        "binding": binding,
        "errors": errors,
    }


def render_showcase(report: dict[str, Any]) -> str:
    lines = [
        "# SZL Holdings operational estate — evidence-backed green-light",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        f"Overall state: **{report['overall_state']}**",
        "",
        "## Required gates",
        "",
        "| Gate | State |",
        "|---|---|",
    ]
    for gate, state in report.get("required_gates", {}).items():
        lines.append(f"| `{gate}` | {'PASS' if state else 'OPEN'} |")
    lines.extend(["", "## Command centers", "", "| Space | Runtime | Visibility | Revision |", "|---|---|---|---|"])
    snapshots = (((report.get("hugging_face") or {}).get("command_centers") or {}).get("snapshots") or {})
    for repo_id, item in snapshots.items():
        visibility = "public" if item.get("private") is False else "unverified"
        lines.append(f"| `{repo_id}` | {item.get('stage')} | {visibility} | `{item.get('sha') or 'UNVERIFIED'}` |")
    lines.extend(["", "## Public planes", "", "| Plane | State | Revision evidence |", "|---|---|---|"])
    for domain, item in ((report.get("domains") or {}).get("domains") or {}).items():
        revisions = (((item.get("probe") or {}).get("revisions")) or [])
        rendered = ", ".join(value.get("sha", "") for value in revisions) or "none"
        lines.append(f"| `{domain}` | {'VERIFIED' if item.get('ok') else 'OPEN'} | `{rendered}` |")
    replit = report.get("replit") or {}
    lines.append(
        f"| `replit_unified_control_hub` | {'VERIFIED' if replit.get('ok') else 'OPEN'} | `{replit.get('deployment_revision') or 'none'}` |"
    )
    lines.extend(
        [
            "",
            "## Model boundary",
            "",
            "- The Brain is reported as an operational, evidence-backed capability and retrieval plane; this is not a fully trained neural-model claim.",
            "- SZL-Nemo v3 remains `PRETRAINING_PREREGISTERED_NOT_TRAINED`; no signing, upload, publication, deployment, or production promotion is claimed.",
            "",
            "## Verification boundary",
            "",
            "Every green gate above is derived from current protected GitHub state, publish-mode Hub evidence, supported API metadata, immutable revisions, and live GET/HEAD probes. Missing evidence remains OPEN.",
            "",
        ]
    )
    return "\n".join(lines)


def evaluate(
    token: str,
    hf: dict[str, Any],
    brain: dict[str, Any],
    replit: dict[str, Any],
    sweep: dict[str, Any],
    domains: dict[str, Any],
    nemo: dict[str, Any],
) -> dict[str, Any]:
    source = source_pr_state(token)
    gates = {
        "protected_source_lanes": bool(source.get("ok")),
        "hf_publish_mode_report": bool(hf.get("publish") and hf.get("zero_errors")),
        "hf_collection_references": bool(hf.get("collections_resolve")),
        "hf_readable_buckets": bool(hf.get("buckets_readable")),
        "five_verified_command_centers": bool((hf.get("command_centers") or {}).get("ok")),
        "brain_exact_merge_and_live_routes": bool(brain.get("ok")),
        "replit_deployment_receipt": bool(replit.get("ok")),
        "organization_pr_sweep_coverage": bool(sweep.get("ok")),
        "public_domain_revision_receipts": bool(domains.get("ok")),
        "nemo_v3_governed_no_training_state": bool(nemo.get("ok")),
    }
    ok = all(gates.values())
    report = {
        "schema": "szl.final-estate-reconciliation/v2",
        "generated_at": now(),
        "overall_state": "OPERATIONAL_VERIFIED" if ok else "PARTIAL_EVIDENCE_OPEN",
        "ok": ok,
        "required_gates": gates,
        "source_lanes": source,
        "hugging_face": hf,
        "brain": brain,
        "replit": replit,
        "organization_pr_sweep": sweep,
        "domains": domains,
        "nemo_v3": nemo,
        "boundaries": [
            "A successful transport response without an immutable revision is not source equivalence.",
            "The Brain operational state does not establish a fully trained neural Brain model.",
            "Nemo v3 is governed preparation only and remains untrained and unpromoted.",
            "No branch-protection, review, secret, paid-hardware, model-weight, or dataset-payload gate is weakened by this controller.",
        ],
    }
    showcase = render_showcase(report)
    report["durable_issue"] = upsert_issue(
        token,
        ISSUE_TITLES["final"],
        report,
        heading="SZL Holdings operational estate — final reconciliation",
        close=ok,
        showcase=showcase,
    )
    return report


def controller_issue(token: str, report: dict[str, Any]) -> dict[str, Any]:
    return upsert_issue(
        token,
        ISSUE_TITLES["controller"],
        report,
        heading="Operational green-light v2 controller",
        close=report.get("ok") is True,
    )


def run_cycle(token: str, *, execute_producers: bool) -> dict[str, Any]:
    workflow_results: dict[str, Any] = {}
    if execute_producers:
        for key in ("hf", "nemo"):
            try:
                workflow_results[key] = execute_workflow(token, key, require_success=False)
            except Exception as exc:  # noqa: BLE001
                workflow_results[key] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    hf = hf_report_state(token)
    brain = brain_state(token)
    replit = discover_replit(token)
    domains = domain_states(token)

    if execute_producers:
        try:
            workflow_results["state_plane"] = execute_workflow(token, "state_plane", require_success=False)
        except Exception as exc:  # noqa: BLE001
            workflow_results["state_plane"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        try:
            workflow_results["sweep"] = execute_workflow(token, "sweep", require_success=False)
        except Exception as exc:  # noqa: BLE001
            workflow_results["sweep"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    sweep = sweep_coverage(token)
    nemo = nemo_state(token)
    final = evaluate(token, hf, brain, replit, sweep, domains, nemo)
    return {"workflow_results": workflow_results, "final": final}


def converge(token: str, cycles: int, wait_seconds: int) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema": "szl.operational-greenlight-controller/v2",
        "generated_at": now(),
        "cycles": [],
        "ok": False,
        "errors": [],
    }
    source_deadline = time.monotonic() + 2 * 60 * 60
    while True:
        source = source_pr_state(token)
        if source.get("ok"):
            break
        report["source_lanes"] = source
        if time.monotonic() >= source_deadline:
            raise GateError("protected source lanes did not all merge within two hours")
        time.sleep(30)

    for cycle in range(1, cycles + 1):
        current = run_cycle(token, execute_producers=True)
        final = current["final"]
        report["cycles"].append(
            {
                "cycle": cycle,
                "generated_at": final.get("generated_at"),
                "workflow_results": current.get("workflow_results"),
                "overall_state": final.get("overall_state"),
                "required_gates": final.get("required_gates"),
                "durable_issue": final.get("durable_issue"),
            }
        )
        report["final"] = final
        if final.get("ok"):
            report["ok"] = True
            report["completed_at"] = now()
            return report
        if cycle < cycles:
            time.sleep(wait_seconds)
    failed = [key for key, value in (report.get("final", {}).get("required_gates") or {}).items() if not value]
    raise GateError(f"estate remained partially open after {cycles} cycles: {failed}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=5)
    parser.add_argument("--wait-seconds", type=int, default=300)
    args = parser.parse_args()
    token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    hf_token = (
        os.environ.get("HF_ORG_TOKEN", "").strip()
        or os.environ.get("HF_ORG_TOKEN1", "").strip()
        or os.environ.get("HF_TOKEN", "").strip()
    )
    report: dict[str, Any]
    code = 0
    try:
        if not token:
            raise GateError("SZL_GITHUB_TOKEN is not configured")
        if not hf_token:
            raise GateError("HF_ORG_TOKEN/HF_ORG_TOKEN1/HF_TOKEN is not configured")
        report = converge(token, args.cycles, args.wait_seconds)
    except Exception as exc:  # noqa: BLE001
        report = locals().get("report") if isinstance(locals().get("report"), dict) else {
            "schema": "szl.operational-greenlight-controller/v2",
            "generated_at": now(),
            "cycles": [],
            "ok": False,
            "errors": [],
        }
        report["ok"] = False
        report.setdefault("errors", []).append(f"{type(exc).__name__}: {exc}")
        code = 1
    if token:
        try:
            report["durable_issue"] = controller_issue(token, report)
        except Exception as exc:  # noqa: BLE001
            report.setdefault("errors", []).append(f"controller issue: {type(exc).__name__}: {exc}")
            report["ok"] = False
            code = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report.get("ok"), "errors": report.get("errors")}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
