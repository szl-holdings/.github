#!/usr/bin/env python3
"""Read protected-main workflow and artifact evidence without mutating GitHub."""
from __future__ import annotations

import io
import json
import os
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "szl.post-merge-evidence-diagnostics/v1"
WORKFLOW_NAMES = (
    "Code Security Config Drift",
    "HF Release Finalization — Supported Kernel Git",
    "HF Release Readiness Terminal",
    "Final Estate Reconciliation v5",
)
ISSUES = (176, 257, 298, 301, 321)


def invoke(arguments: list[str], *, binary: bool = False) -> dict[str, Any]:
    process = subprocess.run(
        ["gh", "api", *arguments],
        check=False,
        capture_output=True,
        env=os.environ,
    )
    if binary:
        payload: Any = process.stdout
    else:
        stdout = process.stdout.decode("utf-8", errors="replace").strip()
        try:
            payload = json.loads(stdout) if stdout else None
        except json.JSONDecodeError:
            payload = stdout[:4000]
    return {
        "ok": process.returncode == 0,
        "returncode": process.returncode,
        "payload": payload,
        "stderr": process.stderr.decode("utf-8", errors="replace").strip()[:3000],
    }


def rest(path: str) -> dict[str, Any]:
    return invoke(["--method", "GET", path])


def compact_run(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "event": item.get("event"),
        "status": item.get("status"),
        "conclusion": item.get("conclusion"),
        "head_branch": item.get("head_branch"),
        "head_sha": item.get("head_sha"),
        "run_number": item.get("run_number"),
        "run_attempt": item.get("run_attempt"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "html_url": item.get("html_url"),
    }


def artifact_payload(repository: str, artifact: dict[str, Any]) -> dict[str, Any]:
    artifact_id = artifact.get("id")
    if not isinstance(artifact_id, int):
        return {"ok": False, "error": "artifact id missing"}
    result = invoke(
        [f"repos/{repository}/actions/artifacts/{artifact_id}/zip"],
        binary=True,
    )
    if not result["ok"]:
        return {"ok": False, "error": result["stderr"]}
    try:
        with zipfile.ZipFile(io.BytesIO(result["payload"])) as archive:
            names = sorted(archive.namelist())
            json_names = [name for name in names if name.lower().endswith(".json")]
            documents: dict[str, Any] = {}
            for name in json_names:
                try:
                    documents[name] = json.loads(
                        archive.read(name).decode("utf-8")
                    )
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    documents[name] = {"decode_error": str(exc)}
            return {"ok": True, "files": names, "documents": documents}
    except zipfile.BadZipFile as exc:
        return {"ok": False, "error": f"bad zip: {exc}"}


def find_security_report(decoded: dict[str, Any]) -> dict[str, Any] | None:
    if not decoded.get("ok"):
        return None
    for document in (decoded.get("documents") or {}).values():
        if isinstance(document, dict) and document.get("schema") == (
            "szl.code-security-drift/v2"
        ):
            return document
    return None


def main() -> int:
    repository = os.environ["GITHUB_REPOSITORY"]
    ref_result = rest(f"repos/{repository}/git/ref/heads/main")
    ref_payload = ref_result.get("payload")
    main_sha = None
    if ref_result["ok"] and isinstance(ref_payload, dict):
        main_sha = (ref_payload.get("object") or {}).get("sha")

    runs_result = rest(f"repos/{repository}/actions/runs?branch=main&per_page=100")
    runs_payload = runs_result.get("payload")
    raw_runs = (
        runs_payload.get("workflow_runs", [])
        if runs_result["ok"] and isinstance(runs_payload, dict)
        else []
    )
    selected_runs: dict[str, dict[str, Any]] = {}
    for name in WORKFLOW_NAMES:
        candidates = [
            item
            for item in raw_runs
            if isinstance(item, dict) and item.get("name") == name
        ]
        if candidates:
            selected_runs[name] = compact_run(candidates[0])

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "diagnostic_generation": os.environ.get("GITHUB_SHA"),
        "repository": repository,
        "main_sha": main_sha,
        "workflows": {},
        "issues": {},
    }

    security_report: dict[str, Any] | None = None
    for name, run in selected_runs.items():
        run_id = run.get("id")
        entry: dict[str, Any] = {"run": run, "artifacts": []}
        if isinstance(run_id, int):
            artifacts_result = rest(
                f"repos/{repository}/actions/runs/{run_id}/artifacts?per_page=100"
            )
            artifacts_payload = artifacts_result.get("payload")
            artifacts = (
                artifacts_payload.get("artifacts", [])
                if artifacts_result["ok"] and isinstance(artifacts_payload, dict)
                else []
            )
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue
                compact = {
                    "id": artifact.get("id"),
                    "name": artifact.get("name"),
                    "size_in_bytes": artifact.get("size_in_bytes"),
                    "expired": artifact.get("expired"),
                    "created_at": artifact.get("created_at"),
                    "expires_at": artifact.get("expires_at"),
                    "digest": artifact.get("digest"),
                }
                decoded = artifact_payload(repository, artifact)
                compact["decoded"] = decoded
                entry["artifacts"].append(compact)
                if name == "Code Security Config Drift" and security_report is None:
                    security_report = find_security_report(decoded)
        report["workflows"][name] = entry

    for issue_number in ISSUES:
        issue_result = rest(f"repos/{repository}/issues/{issue_number}")
        issue = issue_result.get("payload")
        report["issues"][str(issue_number)] = (
            {
                "ok": True,
                "number": issue.get("number"),
                "title": issue.get("title"),
                "state": issue.get("state"),
                "state_reason": issue.get("state_reason"),
                "updated_at": issue.get("updated_at"),
                "html_url": issue.get("html_url"),
            }
            if issue_result["ok"] and isinstance(issue, dict)
            else {
                "ok": False,
                "error": issue_result.get("stderr"),
            }
        )

    report["security_report"] = security_report
    path = Path(
        os.environ.get(
            "POST_MERGE_REPORT_PATH",
            "reports/post-merge-evidence.json",
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    security = security_report or {}
    authentication = security.get("authentication") or {}
    totals = security.get("totals") or {}
    errors = security.get("errors") or []
    warnings = security.get("warnings") or []
    summary = {
        "schema": SCHEMA,
        "main_sha": main_sha,
        "workflow_runs": {
            name: {
                "id": entry["run"].get("id"),
                "head_sha": entry["run"].get("head_sha"),
                "status": entry["run"].get("status"),
                "conclusion": entry["run"].get("conclusion"),
                "artifact_count": len(entry.get("artifacts") or []),
            }
            for name, entry in report["workflows"].items()
        },
        "security": {
            "present": bool(security_report),
            "schema": security.get("schema"),
            "status": security.get("status"),
            "generation": security.get("generation"),
            "authentication_mode": authentication.get("mode"),
            "credential_name": authentication.get("credential_name"),
            "authorized_endpoint_completed": authentication.get(
                "authorized_endpoint_completed"
            ),
            "value_recorded": authentication.get("value_recorded"),
            "canonical_config": security.get("canonical_config"),
            "default_for_new_repos": security.get("default_for_new_repos"),
            "org_repos": totals.get("org_repos"),
            "archived": totals.get("archived"),
            "enforced_under_canonical": totals.get(
                "enforced_under_canonical"
            ),
            "error_count": len(errors),
            "warning_count": len(warnings),
        },
        "issues": report["issues"],
    }
    summary_path = Path(
        os.environ.get(
            "POST_MERGE_SUMMARY_PATH",
            "reports/post-merge-summary.json",
        )
    )
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("POST_MERGE_EVIDENCE_SUMMARY")
    print(json.dumps(summary, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
