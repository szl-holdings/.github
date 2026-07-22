#!/usr/bin/env python3
"""Reconcile the public SZL estate from immutable evidence and safe probes.

The controller is deliberately read-only for runtime assets. It reads deterministic
GitHub evidence issues, performs public GET/HEAD probes, records the organization
pull-request census, writes one JSON report, and may update one deterministic issue.
It never mutates Hugging Face assets, deployments, visibility, hardware, branches,
training, weights, qualification, or promotion state.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlsplit

import requests

ORG = "szl-holdings"
REPL_ID = "34870515-2d52-4ad8-9636-40cc3ced1771"
REPORT_TITLE = "[final-estate-reconciliation] SZL Holdings operational estate"
REPORT_MARKER = "szl-final-estate-reconciliation-v4"
REPORT_SCHEMA = "szl.final-estate-reconciliation/v4"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SOURCE_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
DEPLOYMENT_REVISION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{6,127}$")
KERNEL_IDS = {
    "SZLHOLDINGS/governed-inference-meter",
    "SZLHOLDINGS/szl-governed-norm",
}
CLONE_IDS = {
    f"SZLHOLDINGS/a11oy-clone-{index}" for index in range(1, 5)
}

EVIDENCE_ISSUES = {
    "official_hf_inventory": ("szl-holdings/.github", 263),
    "hf_release_readiness": ("szl-holdings/.github", 257),
    "kernel_publication": ("szl-holdings/.github", 275),
    "canonical_a11oy_relock": ("szl-holdings/a11oy", 1043),
    "unified_control_hub": ("szl-holdings/.github", 273),
}

SAFE_PROBES = {
    "a11oy_product": "https://a-11-oy.com/",
    "a11oy_pages": "https://a11oy.net/",
    "a11oy_space": "https://szlholdings-a11oy.hf.space/",
    "a11oy_livez": "https://szlholdings-a11oy.hf.space/api/livez",
    "a11oy_build_info": "https://szlholdings-a11oy.hf.space/api/build-info",
    "a11oy_brain_capabilities": (
        "https://szlholdings-a11oy.hf.space/api/a11oy/v1/brain/capabilities"
    ),
    "a11oy_readiness": (
        "https://szlholdings-a11oy.hf.space/"
        "api/a11oy/v1/readiness/tab-matrix?view=summary"
    ),
    "a11oy_holographic": (
        "https://szlholdings-a11oy.hf.space/static/3d/holographic.html"
    ),
}


@dataclass(frozen=True)
class Gate:
    name: str
    ok: bool
    detail: str
    evidence: dict[str, Any]


class GitHubClient:
    def __init__(self, token: str | None) -> None:
        self.base = "https://api.github.com"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "szl-final-estate-reconciliation/4",
            }
        )
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
        expected: Iterable[int] = (200,),
    ) -> requests.Response:
        response = self.session.request(
            method,
            f"{self.base}{path}",
            params=params,
            json=payload,
            timeout=60,
        )
        if response.status_code not in set(expected):
            raise RuntimeError(
                f"GitHub {method} {path} returned HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )
        return response

    def issue(self, repo: str, number: int) -> dict[str, Any]:
        value = self.request("GET", f"/repos/{repo}/issues/{number}").json()
        if not isinstance(value, dict):
            raise RuntimeError(f"GitHub issue {repo}#{number} is not an object")
        return value

    def open_pull_requests(self) -> list[dict[str, Any]]:
        query = f"org:{ORG} is:pr is:open"
        output: list[dict[str, Any]] = []
        for page in range(1, 11):
            payload = self.request(
                "GET",
                "/search/issues",
                params={"q": query, "per_page": 100, "page": page},
            ).json()
            if not isinstance(payload, dict):
                raise RuntimeError("GitHub pull-request search is not an object")
            values = payload.get("items") or []
            if not isinstance(values, list):
                raise RuntimeError("GitHub pull-request search items are not a list")
            output.extend(item for item in values if isinstance(item, dict))
            if len(values) < 100:
                return output
        raise RuntimeError("open pull-request search exceeded 1,000 results")

    def upsert_report_issue(self, body: str, operational: bool) -> dict[str, Any]:
        query = f'repo:{ORG}/.github is:issue in:title "{REPORT_TITLE}"'
        payload = self.request(
            "GET",
            "/search/issues",
            params={"q": query, "per_page": 10},
        ).json()
        values = payload.get("items", []) if isinstance(payload, dict) else []
        exact = next(
            (
                item
                for item in values
                if isinstance(item, dict) and item.get("title") == REPORT_TITLE
            ),
            None,
        )
        desired_state = "closed" if operational else "open"
        if exact:
            number = int(exact["number"])
            return self.request(
                "PATCH",
                f"/repos/{ORG}/.github/issues/{number}",
                payload={"body": body, "state": desired_state},
            ).json()

        created = self.request(
            "POST",
            f"/repos/{ORG}/.github/issues",
            payload={"title": REPORT_TITLE, "body": body},
            expected=(201,),
        ).json()
        if not isinstance(created, dict):
            raise RuntimeError("created reconciliation issue is not an object")
        if operational:
            number = int(created["number"])
            created = self.request(
                "PATCH",
                f"/repos/{ORG}/.github/issues/{number}",
                payload={"state": "closed"},
            ).json()
        return created


def _json_fences(body: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for match in re.finditer(r"```json\s*(\{.*?\})\s*```", body or "", re.DOTALL):
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            output.append(value)
    return output


def _latest_report(issue: Mapping[str, Any]) -> dict[str, Any]:
    reports = _json_fences(str(issue.get("body") or ""))
    if not reports:
        raise RuntimeError("issue contains no valid fenced JSON evidence")
    return reports[-1]


def _summary_clean(report: Mapping[str, Any]) -> bool:
    summary = report.get("summary") or {}
    if not isinstance(summary, Mapping):
        return False
    try:
        return int(summary.get("error", 1)) == 0
    except (TypeError, ValueError):
        return False


def _https_origin(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return None
    port = f":{parsed.port}" if parsed.port else ""
    return f"https://{parsed.hostname.lower()}{port}"


def _status_passed(value: Any) -> bool:
    return str(value or "").strip().lower() in {
        "pass",
        "passed",
        "green",
        "ready",
        "operational",
    }


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
    return isinstance(checks, Mapping) and bool(checks) and all(
        item is True for item in checks.values()
    )


def validate_official_inventory(report: Mapping[str, Any]) -> tuple[bool, str]:
    counts = report.get("counts") or {}
    canonical = report.get("canonical_a11oy") or {}
    clones = report.get("clone_absence") or {}
    required_counts = (
        "models",
        "datasets",
        "spaces",
        "kernels",
        "collections",
        "collection_references",
        "buckets",
    )
    counts_ok = isinstance(counts, Mapping) and all(
        isinstance(counts.get(key), int) and counts[key] >= 0 for key in required_counts
    )
    clones_ok = (
        isinstance(clones, Mapping)
        and set(clones) == CLONE_IDS
        and all(value is True for value in clones.values())
    )
    canonical_ok = (
        isinstance(canonical, Mapping)
        and canonical.get("private") is False
        and str(canonical.get("sdk") or "").lower() == "docker"
        and str(canonical.get("stage") or "").upper() == "RUNNING"
        and SHA40.fullmatch(str(canonical.get("sha") or "")) is not None
    )
    ok = (
        report.get("publish") is True
        and _summary_clean(report)
        and counts_ok
        and canonical_ok
        and clones_ok
    )
    return ok, (
        f"publish={report.get('publish')}; errors={(report.get('summary') or {}).get('error')}; "
        f"counts_ok={counts_ok}; canonical_ok={canonical_ok}; clones_ok={clones_ok}"
    )


def validate_release_readiness(report: Mapping[str, Any]) -> tuple[bool, str]:
    results = report.get("results") or {}
    dataset = results.get("dataset") if isinstance(results, Mapping) else None
    kernels = results.get("kernels") if isinstance(results, Mapping) else None
    dataset_ok = (
        isinstance(dataset, Mapping)
        and dataset.get("viewer_http_status") == 200
        and SHA40.fullmatch(str(dataset.get("revision") or "")) is not None
        and isinstance(dataset.get("remote_file_count"), int)
        and dataset["remote_file_count"] > 0
    )
    kernel_ids = set(kernels) if isinstance(kernels, Mapping) else set()
    kernels_ok = kernel_ids == KERNEL_IDS and all(
        isinstance(kernels[repo_id], Mapping)
        and SHA40.fullmatch(str(kernels[repo_id].get("revision") or "")) is not None
        and isinstance(kernels[repo_id].get("remote_file_count"), int)
        and kernels[repo_id]["remote_file_count"] > 0
        and _selfcheck_passed(kernels[repo_id].get("selfcheck"))
        for repo_id in KERNEL_IDS
    )
    ok = (
        report.get("publish") is True
        and _summary_clean(report)
        and dataset_ok
        and kernels_ok
    )
    return ok, (
        f"publish={report.get('publish')}; errors={(report.get('summary') or {}).get('error')}; "
        f"dataset_ok={dataset_ok}; kernels_ok={kernels_ok}; kernels={sorted(kernel_ids)}"
    )


def validate_kernel_publication(report: Mapping[str, Any]) -> tuple[bool, str]:
    runtime = report.get("runtime") or {}
    results = report.get("results") or {}
    kernel_ids = set(results) if isinstance(results, Mapping) else set()
    runtime_ok = (
        isinstance(runtime, Mapping)
        and runtime.get("numpy") == "2.2.6"
        and str(runtime.get("torch") or "").startswith("2.7.1")
    )
    kernels_ok = kernel_ids == KERNEL_IDS and all(
        isinstance(results[repo_id], Mapping)
        and SHA40.fullmatch(str(results[repo_id].get("revision") or "")) is not None
        and results[repo_id].get("build_variants_preserved") is True
        and results[repo_id].get("card_contract_byte_parity") is True
        and isinstance(results[repo_id].get("remote_file_count"), int)
        and results[repo_id]["remote_file_count"] > 0
        and _selfcheck_passed(results[repo_id].get("selfcheck"))
        for repo_id in KERNEL_IDS
    )
    ok = (
        report.get("schema") == "szl.hf-kernel-card-publish/v2"
        and report.get("publish") is True
        and _summary_clean(report)
        and runtime_ok
        and kernels_ok
    )
    return ok, (
        f"schema={report.get('schema')}; publish={report.get('publish')}; "
        f"errors={(report.get('summary') or {}).get('error')}; "
        f"runtime_ok={runtime_ok}; kernels_ok={kernels_ok}"
    )


def validate_a11oy_relock(report: Mapping[str, Any]) -> tuple[bool, str]:
    clones = report.get("clone_presence") or {}
    clones_ok = (
        isinstance(clones, Mapping)
        and set(clones) == CLONE_IDS
        and all(value is False for value in clones.values())
    )
    ok = (
        report.get("schema") == "szl.a11oy-deployment-relock/v2"
        and str(report.get("status") or "").upper() == "PASS"
        and report.get("public") is True
        and str(report.get("sdk") or "").lower() == "docker"
        and str(report.get("runtime_stage") or "").upper() == "RUNNING"
        and report.get("dockerfile_present") is True
        and report.get("build_identity_contains_source") is True
        and isinstance(report.get("managed_file_count"), int)
        and report["managed_file_count"] > 0
        and SHA40.fullmatch(str(report.get("github_source_sha") or "")) is not None
        and SHA40.fullmatch(str(report.get("hf_repository_sha") or "")) is not None
        and report.get("hf_repository_sha") == report.get("hf_runtime_sha")
        and clones_ok
    )
    return ok, (
        f"status={report.get('status')}; public={report.get('public')}; "
        f"runtime={report.get('runtime_stage')}; source_bound={report.get('build_identity_contains_source')}; "
        f"clones_ok={clones_ok}"
    )


def validate_replit(report: Mapping[str, Any]) -> tuple[bool, str]:
    receipt = report.get("receipt") or {}
    attempts = report.get("attempts") or []
    top_origin = _https_origin(report.get("production_url"))
    receipt_origin = _https_origin(receipt.get("production_url")) if isinstance(receipt, Mapping) else None

    tests = receipt.get("tests") if isinstance(receipt, Mapping) else None
    mobile = receipt.get("mobile") if isinstance(receipt, Mapping) else None
    readiness = receipt.get("readiness") if isinstance(receipt, Mapping) else None
    accessibility = receipt.get("accessibility") if isinstance(receipt, Mapping) else None

    tests_ok = (
        isinstance(tests, Mapping)
        and _status_passed(tests.get("status"))
        and isinstance(tests.get("commands"), list)
        and bool(tests["commands"])
        and all(isinstance(item, str) and item.strip() for item in tests["commands"])
    )
    mobile_ok = (
        isinstance(mobile, Mapping)
        and _status_passed(mobile.get("status"))
        and isinstance(mobile.get("viewport_widths"), list)
        and any(isinstance(item, int) and 280 <= item <= 480 for item in mobile["viewport_widths"])
    )
    readiness_checks = readiness.get("checks") if isinstance(readiness, Mapping) else None
    readiness_ok = (
        isinstance(readiness, Mapping)
        and readiness.get("ok") is True
        and _status_passed(readiness.get("status"))
        and isinstance(readiness_checks, Mapping)
        and bool(readiness_checks)
        and all(value is True for value in readiness_checks.values())
    )
    accessibility_ok = (
        isinstance(accessibility, Mapping)
        and _status_passed(accessibility.get("status"))
        and accessibility.get("keyboard") is True
        and accessibility.get("focus_visible") is True
        and accessibility.get("semantic_landmarks") is True
        and accessibility.get("contrast") is True
    )
    attempt_ok = isinstance(attempts, list) and any(
        isinstance(item, Mapping)
        and item.get("ok") is True
        and item.get("get_status") == 200
        and item.get("head_status") in {200, 204}
        and _https_origin(item.get("final_origin")) == top_origin
        for item in attempts
    )
    source_revision = receipt.get("source_revision") if isinstance(receipt, Mapping) else None
    deployment_revision = receipt.get("deployment_revision") if isinstance(receipt, Mapping) else None
    receipt_ok = (
        isinstance(receipt, Mapping)
        and receipt.get("schema") == "szl.unified-control-hub.deployment-receipt/v1"
        and receipt.get("repl_id") == REPL_ID
        and SOURCE_REVISION.fullmatch(str(source_revision or "")) is not None
        and DEPLOYMENT_REVISION.fullmatch(str(deployment_revision or "")) is not None
        and top_origin is not None
        and receipt_origin == top_origin
        and tests_ok
        and mobile_ok
        and readiness_ok
        and accessibility_ok
    )
    ok = (
        report.get("schema") == "szl.replit-public-status/v1"
        and report.get("repl_id") == REPL_ID
        and report.get("ok") is True
        and str(report.get("status") or "").upper() == "OPERATIONAL"
        and receipt_ok
        and attempt_ok
    )
    return ok, (
        f"status={report.get('status')}; receipt_ok={receipt_ok}; tests_ok={tests_ok}; "
        f"mobile_ok={mobile_ok}; readiness_ok={readiness_ok}; "
        f"accessibility_ok={accessibility_ok}; get_head_ok={attempt_ok}"
    )


VALIDATORS: dict[str, Callable[[Mapping[str, Any]], tuple[bool, str]]] = {
    "official_hf_inventory": validate_official_inventory,
    "hf_release_readiness": validate_release_readiness,
    "kernel_publication": validate_kernel_publication,
    "canonical_a11oy_relock": validate_a11oy_relock,
    "unified_control_hub": validate_replit,
}


def evaluate_issue_gate(
    client: GitHubClient,
    name: str,
    repo: str,
    number: int,
) -> Gate:
    try:
        issue = client.issue(repo, number)
        report = _latest_report(issue)
        valid, detail = VALIDATORS[name](report)
        closed = issue.get("state") == "closed"
        return Gate(
            name=name,
            ok=closed and valid,
            detail=f"issue_state={issue.get('state')}; {detail}",
            evidence={
                "issue_url": issue.get("html_url") or issue.get("url"),
                "issue_state": issue.get("state"),
                "issue_updated_at": issue.get("updated_at"),
                "report_schema": report.get("schema"),
                "report_generated_at": report.get("generated_at"),
                "report_generation": report.get("generation"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return Gate(name, False, f"{type(exc).__name__}: {exc}", {})


def safe_probe(
    name: str,
    url: str,
    source_sha: str | None,
    *,
    session: requests.Session | None = None,
) -> Gate:
    session = session or requests.Session()
    session.headers.update(
        {
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "User-Agent": "szl-final-estate-reconciliation/4",
        }
    )
    try:
        head = session.head(url, allow_redirects=True, timeout=45)
        response = session.get(url, allow_redirects=True, timeout=60)
        final_origin = _https_origin(response.url)
        ok = (
            200 <= head.status_code < 400
            and 200 <= response.status_code < 400
            and final_origin is not None
            and len(response.content) > 0
        )
        evidence: dict[str, Any] = {
            "url": url,
            "head_http_status": head.status_code,
            "get_http_status": response.status_code,
            "final_url": response.url,
            "content_type": response.headers.get("content-type"),
            "bytes": len(response.content),
        }
        content_type = str(response.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            try:
                payload = response.json()
            except ValueError as exc:
                payload = None
                evidence["json_error"] = str(exc)
                ok = False
            if isinstance(payload, Mapping):
                evidence["json_keys"] = sorted(str(key) for key in payload)[:100]
                evidence["schema"] = payload.get("schema")
                evidence["status"] = payload.get("status") or payload.get("overall_status")
                if name == "a11oy_build_info":
                    source_bound = bool(source_sha) and source_sha in json.dumps(
                        payload, sort_keys=True, default=str
                    )
                    evidence["source_bound"] = source_bound
                    ok = ok and source_bound
            elif name == "a11oy_build_info":
                ok = False
        elif name == "a11oy_build_info":
            ok = False
        return Gate(
            name=f"probe:{name}",
            ok=ok,
            detail=(
                f"HEAD={head.status_code}; GET={response.status_code}; "
                f"final={response.url}; bytes={len(response.content)}"
            ),
            evidence=evidence,
        )
    except Exception as exc:  # noqa: BLE001
        return Gate(
            f"probe:{name}",
            False,
            f"{type(exc).__name__}: {exc}",
            {"url": url},
        )


def evaluate_open_prs(client: GitHubClient) -> Gate:
    try:
        values = client.open_pull_requests()
        evidence = [
            {
                "repository_url": item.get("repository_url"),
                "number": item.get("number"),
                "title": item.get("title"),
                "url": item.get("html_url"),
                "draft": item.get("draft"),
                "updated_at": item.get("updated_at"),
            }
            for item in values
        ]
        return Gate(
            "organization_open_prs",
            len(values) == 0,
            f"open_pull_requests={len(values)}",
            {"open_pull_requests": evidence},
        )
    except Exception as exc:  # noqa: BLE001
        return Gate("organization_open_prs", False, f"{type(exc).__name__}: {exc}", {})


def evaluate(client: GitHubClient) -> dict[str, Any]:
    gates = [
        evaluate_issue_gate(client, name, repo, number)
        for name, (repo, number) in EVIDENCE_ISSUES.items()
    ]
    source_sha: str | None = None
    try:
        relock_issue = client.issue(*EVIDENCE_ISSUES["canonical_a11oy_relock"])
        candidate = str(_latest_report(relock_issue).get("github_source_sha") or "")
        if SHA40.fullmatch(candidate):
            source_sha = candidate
    except Exception:  # noqa: BLE001
        source_sha = None
    gates.extend(safe_probe(name, url, source_sha) for name, url in SAFE_PROBES.items())
    gates.append(evaluate_open_prs(client))
    operational = all(gate.ok for gate in gates)
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "organization": ORG,
        "status": "OPERATIONAL_VERIFIED" if operational else "NOT_VERIFIED",
        "operational_verified": operational,
        "gates": [asdict(gate) for gate in gates],
        "summary": {
            "ok": sum(gate.ok for gate in gates),
            "error": sum(not gate.ok for gate in gates),
            "total": len(gates),
        },
        "boundaries": [
            "This controller performs only GitHub evidence reads, safe public GET/HEAD probes, and one deterministic issue update.",
            "It does not mutate any Hugging Face asset, deployment, visibility, hardware, model, dataset, kernel, collection, bucket, branch rule, training state, weight, qualification, or promotion state.",
            "OPERATIONAL_VERIFIED requires every recorded gate to pass in the same run, including zero organization pull requests.",
            "This status does not claim SZL-Nemo v3 is trained or that the Brain is a fully trained neural model.",
        ],
    }


def issue_body(report: Mapping[str, Any], run_url: str | None) -> str:
    lines = [
        f"<!-- {REPORT_MARKER} -->",
        "# SZL Holdings operational estate reconciliation",
        "",
        f"- Status: **{report['status']}**",
        f"- Generated: `{report['generated_at']}`",
    ]
    if run_url:
        lines.append(f"- Run: {run_url}")
    lines.extend(["", "| Gate | Result | Detail |", "|---|---|---|"])
    for gate in report["gates"]:
        detail = str(gate["detail"]).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{gate['name']}` | `{'PASS' if gate['ok'] else 'FAIL'}` | {detail} |"
        )
    lines.extend(["", "```json", json.dumps(report, indent=2, sort_keys=True), "```", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reports/final-estate-reconciliation-v4.json")
    parser.add_argument("--publish-issue", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    token = (
        os.environ.get("SZL_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
    )
    client = GitHubClient(token)
    report = evaluate(client)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))

    if args.publish_issue:
        run_url = None
        if all(
            os.environ.get(key)
            for key in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")
        ):
            run_url = (
                f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
                f"/actions/runs/{os.environ['GITHUB_RUN_ID']}"
            )
        client.upsert_report_issue(
            issue_body(report, run_url),
            bool(report["operational_verified"]),
        )

    if args.enforce and not report["operational_verified"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
