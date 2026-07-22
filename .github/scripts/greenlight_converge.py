#!/usr/bin/env python3
"""Converge the installed protected lanes to a real final green report."""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

API = "https://api.github.com"
API_VERSION = "2022-11-28"
CONTROL_REPOSITORY = "szl-holdings/.github"
REPLIT_ISSUE_TITLE = "[replit-deployment-receipt] Unified Control Hub"
FINAL_ISSUE_TITLE = "[final-estate-reconciliation] SZL Holdings operational estate"
SOURCE_PRS = (
    ("szl-holdings/.github", 244),
    ("szl-holdings/.github", 246),
    ("szl-holdings/.github", 247),
    ("szl-holdings/.github", 248),
    ("szl-holdings/a11oy", 1035),
    ("szl-holdings/a11oy", 1036),
)
WORKFLOWS = {
    "hf": ("szl-holdings/.github", "hf-estate-official-api-v3.yml", {"publish": "true"}, 110 * 60),
    "brain": ("szl-holdings/.github", "merge-brain-pr-1003.yml", {"execute": "true"}, 150 * 60),
    "state_plane": ("szl-holdings/a11oy", "state-plane-continuity-v2.yml", {}, 35 * 60),
    "nemo": ("szl-holdings/a11oy", "nemo-v3-preregister.yml", {}, 35 * 60),
    "sweep": ("szl-holdings/.github", "org-pr-final-sweep.yml", {"execute": "true"}, 250 * 60),
    "final": ("szl-holdings/.github", "final-estate-reconciliation.yml", {}, 140 * 60),
}


class GateError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request(
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    allow_status: set[int] | None = None,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "szl-greenlight-convergence/1.0",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if allow_status and exc.code in allow_status:
            return None
        detail = exc.read().decode("utf-8", "replace")[:6000]
        raise GateError(f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise GateError(f"GitHub API {method} {path} failed: {type(exc).__name__}: {exc}") from exc
    return json.loads(raw.decode("utf-8")) if raw else None


def paginate(token: str, path: str, max_pages: int = 10) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    sep = "&" if "?" in path else "?"
    for page in range(1, max_pages + 1):
        payload = request(token, "GET", f"{path}{sep}per_page=100&page={page}")
        if not isinstance(payload, list):
            raise GateError(f"non-list pagination payload for {path}")
        output.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return output
    raise GateError(f"pagination exceeded {max_pages} pages for {path}")


def issue_by_title(token: str, title: str) -> dict[str, Any] | None:
    issues = paginate(token, f"/repos/{CONTROL_REPOSITORY}/issues?state=all&sort=updated&direction=desc")
    for issue in issues:
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


def receipt_url_from_body(body: str) -> str | None:
    report = parse_fenced_json(body)
    candidates: list[Any] = []
    if report:
        candidates.extend(
            [
                report.get("receipt_url"),
                report.get("deployment_receipt_url"),
                report.get("url") if "/api/szl/deployment-receipt" in str(report.get("url") or "") else None,
            ]
        )
    candidates.extend(
        re.findall(
            r"https://[^\s`\"<>]+/api/szl/deployment-receipt(?:\?[^\s`\"<>]*)?",
            body,
            flags=re.I,
        )
    )
    for candidate in candidates:
        text = str(candidate or "").strip().rstrip(".,;)")
        if text.startswith("https://"):
            return text
    return None


def set_receipt_variable(token: str, value: str) -> dict[str, Any]:
    encoded = urllib.parse.quote("REPLIT_DEPLOYMENT_RECEIPT_URL", safe="")
    current = request(
        token,
        "GET",
        f"/repos/{CONTROL_REPOSITORY}/actions/variables/{encoded}",
        allow_status={404},
    )
    payload = {"name": "REPLIT_DEPLOYMENT_RECEIPT_URL", "value": value}
    if current is None:
        request(token, "POST", f"/repos/{CONTROL_REPOSITORY}/actions/variables", payload)
        action = "created"
    elif str(current.get("value") or "") != value:
        request(token, "PATCH", f"/repos/{CONTROL_REPOSITORY}/actions/variables/{encoded}", payload)
        action = "updated"
    else:
        action = "unchanged"
    return {"action": action, "value": value}


def all_sources_merged(token: str) -> tuple[bool, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    for repository, number in SOURCE_PRS:
        pr = request(token, "GET", f"/repos/{repository}/pulls/{number}")
        row = {
            "repository": repository,
            "pull_request": number,
            "state": pr.get("state"),
            "merged": bool(pr.get("merged")),
            "merged_at": pr.get("merged_at"),
            "merge_sha": pr.get("merge_commit_sha"),
        }
        rows.append(row)
    return all(row["merged"] for row in rows), rows


def dispatch(token: str, key: str) -> dict[str, Any]:
    repository, workflow, inputs, timeout_seconds = WORKFLOWS[key]
    encoded = urllib.parse.quote(workflow, safe="")
    started = datetime.now(timezone.utc)
    payload: dict[str, Any] = {"ref": "main"}
    if inputs:
        payload["inputs"] = inputs
    request(token, "POST", f"/repos/{repository}/actions/workflows/{encoded}/dispatches", payload)
    return {
        "key": key,
        "repository": repository,
        "workflow": workflow,
        "started_at": started.isoformat(),
        "timeout_seconds": timeout_seconds,
    }


def parse_time(value: Any) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def wait_run(token: str, record: dict[str, Any], *, require_success: bool = True) -> dict[str, Any]:
    repository = record["repository"]
    workflow = record["workflow"]
    encoded = urllib.parse.quote(workflow, safe="")
    started = parse_time(record["started_at"]) - timedelta(seconds=10)
    deadline = time.monotonic() + int(record["timeout_seconds"])
    selected: dict[str, Any] | None = None
    while True:
        payload = request(
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


def run_once(token: str, keys: list[str], *, require_success: bool = True) -> list[dict[str, Any]]:
    records = [dispatch(token, key) for key in keys]
    return [wait_run(token, record, require_success=require_success) for record in records]


def final_report(token: str) -> dict[str, Any] | None:
    issue = issue_by_title(token, FINAL_ISSUE_TITLE)
    if not issue:
        return None
    return parse_fenced_json(str(issue.get("body") or ""))


def failed_gate_keys(report: dict[str, Any] | None) -> list[str]:
    if not isinstance(report, dict):
        return ["final-report-unavailable"]
    gates = report.get("required_gates") or {}
    return sorted(key for key, value in gates.items() if value is not True)


def remediation_keys(failed: list[str]) -> list[str]:
    mapping = {
        "control_workflows": ["hf", "brain", "state_plane", "nemo", "sweep"],
        "hf_publish_mode_report": ["hf"],
        "hf_asset_revisions": ["hf"],
        "hf_command_centers": ["hf"],
        "hf_collections": ["hf"],
        "hf_buckets": ["hf"],
        "live_surfaces": ["hf", "state_plane"],
        "state_plane_v2_packet": ["state_plane"],
        "brain_exact_merge_and_live_route": ["brain", "hf"],
        "organization_pr_sweep_coverage": ["sweep"],
        "nemo_v3_governed_preparation": ["nemo"],
    }
    output: list[str] = []
    for gate in failed:
        for key in mapping.get(gate, []):
            if key not in output:
                output.append(key)
    return output


def upsert_watchdog_issue(token: str, report: dict[str, Any]) -> dict[str, Any]:
    title = "[greenlight-convergence] operational estate"
    body = (
        "<!-- szl-greenlight-convergence -->\n"
        "# Operational estate convergence\n\n"
        f"Generated: `{report.get('generated_at')}`\n\n"
        "```json\n"
        + json.dumps(report, indent=2, sort_keys=True)
        + "\n```\n"
    )
    current = issue_by_title(token, title)
    if current:
        issue = request(
            token,
            "PATCH",
            f"/repos/{CONTROL_REPOSITORY}/issues/{current['number']}",
            {"body": body, "state": "closed" if report.get("ok") else "open"},
        )
    else:
        issue = request(token, "POST", f"/repos/{CONTROL_REPOSITORY}/issues", {"title": title, "body": body})
        if report.get("ok"):
            issue = request(
                token,
                "PATCH",
                f"/repos/{CONTROL_REPOSITORY}/issues/{issue['number']}",
                {"state": "closed"},
            )
    return {"number": issue.get("number"), "url": issue.get("html_url"), "state": issue.get("state")}


def converge(token: str, cycles: int, wait_seconds: int) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema": "szl.greenlight-convergence/v1",
        "generated_at": now(),
        "source_prs": [],
        "receipt_handoff": None,
        "cycles": [],
        "final_report": None,
        "failed_gates": [],
        "ok": False,
        "errors": [],
    }

    deadline = time.monotonic() + 5 * 60 * 60
    while True:
        merged, rows = all_sources_merged(token)
        report["source_prs"] = rows
        if merged:
            break
        if time.monotonic() >= deadline:
            raise GateError("not all six source PRs merged within convergence window")
        time.sleep(30)

    # Give the Replit agent a chance to publish its durable handoff while protected producers run.
    first_results = run_once(token, ["hf", "brain", "state_plane", "nemo"], require_success=False)
    report["cycles"].append({"cycle": 0, "producer_runs": first_results})

    for cycle in range(1, cycles + 1):
        receipt_issue = issue_by_title(token, REPLIT_ISSUE_TITLE)
        receipt_url = receipt_url_from_body(str((receipt_issue or {}).get("body") or ""))
        if receipt_url:
            report["receipt_handoff"] = {
                "issue_number": receipt_issue.get("number"),
                "issue_url": receipt_issue.get("html_url"),
                "receipt_url": receipt_url,
                "variable": set_receipt_variable(token, receipt_url),
            }

        sweep_result = run_once(token, ["sweep"], require_success=False)[0]
        final_result = run_once(token, ["final"], require_success=False)[0]
        current = final_report(token)
        failed = failed_gate_keys(current)
        entry: dict[str, Any] = {
            "cycle": cycle,
            "receipt_url": receipt_url,
            "sweep": sweep_result,
            "final_workflow": final_result,
            "failed_gates": failed,
        }
        report["cycles"].append(entry)
        report["final_report"] = current
        report["failed_gates"] = failed
        if final_result.get("ok") and isinstance(current, dict) and current.get("ok") is True:
            report["ok"] = True
            return report

        keys = remediation_keys(failed)
        if keys:
            entry["remediation_runs"] = run_once(token, keys, require_success=False)
        if cycle < cycles:
            time.sleep(wait_seconds)

    raise GateError(f"final estate remained open after {cycles} cycles: {report['failed_gates']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=4)
    parser.add_argument("--wait-seconds", type=int, default=300)
    args = parser.parse_args()
    token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    code = 0
    report: dict[str, Any]
    try:
        if not token:
            raise GateError("SZL_GITHUB_TOKEN is not configured")
        report = converge(token, args.cycles, args.wait_seconds)
    except Exception as exc:  # noqa: BLE001
        report = locals().get("report") if isinstance(locals().get("report"), dict) else {
            "schema": "szl.greenlight-convergence/v1",
            "generated_at": now(),
            "ok": False,
            "errors": [],
        }
        report["ok"] = False
        report.setdefault("errors", []).append(f"{type(exc).__name__}: {exc}")
        code = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if token:
        try:
            report["durable_issue"] = upsert_watchdog_issue(token, report)
            args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            report.setdefault("errors", []).append(f"issue persistence: {type(exc).__name__}: {exc}")
            report["ok"] = False
            args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            code = 1
    print(json.dumps({"ok": report.get("ok"), "failed_gates": report.get("failed_gates")}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
