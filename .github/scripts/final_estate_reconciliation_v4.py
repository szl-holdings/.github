#!/usr/bin/env python3
"""Fail-closed reconciliation of the SZL Holdings operational estate.

This controller reads durable GitHub evidence, performs safe public GET/HEAD
probes, writes one JSON report, and may update one deterministic GitHub issue.
It does not mutate models, datasets, Spaces, kernels, collections, buckets,
deployments, visibility, hardware, branch protection, training, or promotion.
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
from typing import Any, Callable, Iterable

import requests

ORG = "szl-holdings"
REPORT_TITLE = "[final-estate-reconciliation] SZL Holdings operational estate"
REPORT_MARKER = "szl-final-estate-reconciliation-v4"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
KERNEL_IDS = {
    "SZLHOLDINGS/governed-inference-meter",
    "SZLHOLDINGS/szl-governed-norm",
}
EVIDENCE_ISSUES = {
    "official_hf_inventory": ("szl-holdings/.github", 263),
    "hf_release_readiness": ("szl-holdings/.github", 257),
    "kernel_readiness": ("szl-holdings/.github", 275),
    "canonical_a11oy_relock": ("szl-holdings/a11oy", 1043),
    "unified_control_hub": ("szl-holdings/.github", 273),
}
CREDENTIAL_HEALTH_ISSUE = ("szl-holdings/.github", 176)
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
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
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
        return self.request("GET", f"/repos/{repo}/issues/{number}").json()

    def code_security_configurations(self) -> list[dict[str, Any]]:
        payload = self.request(
            "GET",
            f"/orgs/{ORG}/code-security/configurations",
            params={"per_page": 1},
        ).json()
        if not isinstance(payload, list):
            raise RuntimeError("organization code-security response is not a list")
        return [item for item in payload if isinstance(item, dict)]

    def open_pull_requests(self) -> list[dict[str, Any]]:
        query = f"org:{ORG} is:pr is:open"
        output: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self.request(
                "GET",
                "/search/issues",
                params={"q": query, "per_page": 100, "page": page},
            ).json()
            values = payload.get("items") or []
            output.extend(item for item in values if isinstance(item, dict))
            if len(values) < 100:
                return output
            page += 1
            if page > 10:
                raise RuntimeError("open pull-request search exceeded 1,000 results")

    def upsert_report_issue(self, body: str, operational: bool) -> dict[str, Any]:
        query = f'repo:{ORG}/.github is:issue in:title "{REPORT_TITLE}"'
        values = self.request(
            "GET",
            "/search/issues",
            params={"q": query, "per_page": 10},
        ).json().get("items", [])
        exact = next((item for item in values if item.get("title") == REPORT_TITLE), None)
        if exact:
            number = int(exact["number"])
            return self.request(
                "PATCH",
                f"/repos/{ORG}/.github/issues/{number}",
                payload={"body": body, "state": "closed" if operational else "open"},
            ).json()
        return self.request(
            "POST",
            f"/repos/{ORG}/.github/issues",
            payload={"title": REPORT_TITLE, "body": body},
            expected=(201,),
        ).json()


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


def _latest_report(issue: dict[str, Any]) -> dict[str, Any]:
    reports = _json_fences(str(issue.get("body") or ""))
    if not reports:
        raise RuntimeError("issue contains no valid fenced JSON evidence")
    return reports[-1]


def _summary_clean(report: dict[str, Any]) -> bool:
    summary = report.get("summary") or {}
    try:
        return int(summary.get("error", 1)) == 0 and int(summary.get("warning", 0)) == 0
    except (TypeError, ValueError):
        return False


def _field_values(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for name, item in value.items():
            if name == key:
                found.append(item)
            found.extend(_field_values(item, key))
    elif isinstance(value, list):
        for item in value:
            found.extend(_field_values(item, key))
    return found


def _has_true(value: Any, *keys: str) -> bool:
    return any(any(item is True for item in _field_values(value, key)) for key in keys)


def _has_sha(value: Any, *keys: str) -> bool:
    return any(
        any(SHA40.fullmatch(str(item or "")) for item in _field_values(value, key))
        for key in keys
    )


def _selfcheck_passed(value: Any) -> bool:
    if value is True:
        return True
    if not isinstance(value, dict):
        return False
    if value.get("passed") is True or value.get("ok") is True:
        return True
    checks = value.get("checks")
    return bool(checks) and isinstance(checks, dict) and all(
        item is True for item in checks.values()
    )


def validate_official_inventory(report: dict[str, Any]) -> tuple[bool, str]:
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
    counts_ok = all(
        isinstance(counts.get(key), int) and counts[key] > 0 for key in required_counts
    )
    ok = (
        report.get("publish") is True
        and _summary_clean(report)
        and counts_ok
        and canonical.get("private") is False
        and str(canonical.get("sdk") or "").lower() == "docker"
        and str(canonical.get("stage") or "").upper() == "RUNNING"
        and SHA40.fullmatch(str(canonical.get("sha") or "")) is not None
        and len(clones) == 4
        and all(value is True for value in clones.values())
    )
    return ok, (
        f"publish={report.get('publish')}; errors={(report.get('summary') or {}).get('error')}; "
        f"warnings={(report.get('summary') or {}).get('warning')}; "
        f"counts={{{', '.join(f'{key}={counts.get(key)}' for key in required_counts)}}}; "
        f"canonical={canonical.get('stage')}; "
        f"clones_absent={sum(value is True for value in clones.values())}/4"
    )


def validate_release_readiness(report: dict[str, Any]) -> tuple[bool, str]:
    results = report.get("results") or {}
    dataset = results.get("dataset") or {}
    kernels = results.get("kernels") or {}
    dataset_revision = dataset.get("after_sha") or dataset.get("revision")
    kernel_ids = set(kernels)
    kernel_ok = kernel_ids == KERNEL_IDS and all(
        SHA40.fullmatch(
            str(
                (kernels.get(repo_id) or {}).get("after_sha")
                or (kernels.get(repo_id) or {}).get("revision")
                or ""
            )
        )
        and _selfcheck_passed((kernels.get(repo_id) or {}).get("selfcheck"))
        for repo_id in KERNEL_IDS
    )
    ok = (
        report.get("publish") is True
        and _summary_clean(report)
        and dataset.get("viewer_http_status") == 200
        and SHA40.fullmatch(str(dataset_revision or "")) is not None
        and kernel_ok
    )
    return ok, (
        f"publish={report.get('publish')}; errors={(report.get('summary') or {}).get('error')}; "
        f"viewer_http={dataset.get('viewer_http_status')}; "
        f"dataset_revision={dataset_revision}; kernels={sorted(kernel_ids)}"
    )


def validate_kernel_readiness(report: dict[str, Any]) -> tuple[bool, str]:
    results = report.get("results") or {}
    kernel_ids = set(results)
    failures = report.get("failures")
    kernel_ok = kernel_ids == KERNEL_IDS and all(
        SHA40.fullmatch(str((results.get(repo_id) or {}).get("revision") or ""))
        and (results.get(repo_id) or {}).get("build_variants_preserved") is True
        and (results.get(repo_id) or {}).get("card_contract_byte_parity") is True
        and _selfcheck_passed((results.get(repo_id) or {}).get("selfcheck"))
        for repo_id in KERNEL_IDS
    )
    ok = (
        report.get("publish") is True
        and _summary_clean(report)
        and failures in (None, [])
        and kernel_ok
    )
    return ok, (
        f"publish={report.get('publish')}; errors={(report.get('summary') or {}).get('error')}; "
        f"failures={len(failures or [])}; kernels={sorted(kernel_ids)}"
    )


def validate_a11oy_relock(report: dict[str, Any]) -> tuple[bool, str]:
    ok = (
        str(report.get("status") or "").upper() == "PASS"
        and report.get("public") is True
        and str(report.get("sdk") or "").lower() == "docker"
        and str(report.get("runtime_stage") or "").upper() == "RUNNING"
        and SHA40.fullmatch(str(report.get("github_source_sha") or "")) is not None
        and SHA40.fullmatch(str(report.get("hf_repository_sha") or "")) is not None
        and report.get("hf_repository_sha") == report.get("hf_runtime_sha")
        and all(value is False for value in (report.get("clone_presence") or {}).values())
    )
    return ok, (
        f"status={report.get('status')}; public={report.get('public')}; "
        f"sdk={report.get('sdk')}; runtime={report.get('runtime_stage')}; "
        f"source={report.get('github_source_sha')}; hf={report.get('hf_runtime_sha')}"
    )


def validate_replit(report: dict[str, Any]) -> tuple[bool, str]:
    receipt = report.get("receipt")
    serialized = json.dumps(report, sort_keys=True, default=str)
    urls = [
        str(item)
        for key in ("production_url", "url", "origin", "receipt_url")
        for item in _field_values(report, key)
        if isinstance(item, str) and item.startswith("https://")
    ]
    ok = (
        report.get("ok") is True
        and isinstance(receipt, dict)
        and _has_sha(receipt, "source_revision", "source_sha", "github_source_sha")
        and bool(
            _field_values(receipt, "deployment_revision")
            or _field_values(receipt, "deployment_id")
        )
        and bool(urls)
        and _has_true(receipt, "tests_passed", "tests_ok")
        and _has_true(receipt, "mobile_passed", "mobile_ok")
        and _has_true(receipt, "keyboard_passed", "keyboard_ok")
        and "GET" in serialized
        and "HEAD" in serialized
    )
    return ok, (
        f"ok={report.get('ok')}; receipt={isinstance(receipt, dict)}; "
        f"source_revision={_has_sha(receipt or {}, 'source_revision', 'source_sha', 'github_source_sha')}; "
        f"deployment_revision={bool(_field_values(receipt or {}, 'deployment_revision') or _field_values(receipt or {}, 'deployment_id'))}; "
        f"https_urls={len(urls)}"
    )


VALIDATORS: dict[str, Callable[[dict[str, Any]], tuple[bool, str]]] = {
    "official_hf_inventory": validate_official_inventory,
    "hf_release_readiness": validate_release_readiness,
    "kernel_readiness": validate_kernel_readiness,
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
            name,
            closed and valid,
            f"issue_state={issue.get('state')}; {detail}",
            {
                "issue_url": issue.get("html_url"),
                "issue_state": issue.get("state"),
                "issue_updated_at": issue.get("updated_at"),
                "report_schema": report.get("schema"),
                "report_generated_at": report.get("generated_at"),
                "report_generation": report.get("generation"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return Gate(name, False, f"{type(exc).__name__}: {exc}", {})


def evaluate_credential_gate(
    evidence_client: GitHubClient,
    org_client: GitHubClient,
    token_configured: bool,
) -> Gate:
    repo, number = CREDENTIAL_HEALTH_ISSUE
    try:
        issue = evidence_client.issue(repo, number)
    except Exception as exc:  # noqa: BLE001
        return Gate(
            "organization_credential_health",
            False,
            f"evidence read failed: {type(exc).__name__}: {exc}",
            {},
        )
    evidence = {
        "issue_url": issue.get("html_url"),
        "issue_state": issue.get("state"),
    }
    if not token_configured:
        return Gate(
            "organization_credential_health",
            False,
            f"issue_state={issue.get('state')}; SZL_GITHUB_TOKEN is not configured",
            evidence,
        )
    try:
        configurations = org_client.code_security_configurations()
    except Exception as exc:  # noqa: BLE001
        return Gate(
            "organization_credential_health",
            False,
            f"issue_state={issue.get('state')}; live organization credential check failed: "
            f"{type(exc).__name__}: {exc}",
            evidence,
        )
    issue_closed = issue.get("state") == "closed"
    evidence.update(
        {
            "code_security_configurations_readable": True,
            "sample_count": len(configurations),
        }
    )
    return Gate(
        "organization_credential_health",
        issue_closed and bool(configurations),
        f"issue_state={issue.get('state')}; code_security_configurations_readable=true; "
        f"sample_count={len(configurations)}",
        evidence,
    )


def safe_probe(name: str, url: str, source_sha: str | None) -> Gate:
    session = requests.Session()
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
        ok = (
            200 <= head.status_code < 400
            and 200 <= response.status_code < 400
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
        if "application/json" in str(response.headers.get("content-type") or ""):
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                evidence["json_keys"] = sorted(payload)[:100]
                evidence["schema"] = payload.get("schema")
                evidence["status"] = payload.get("status") or payload.get("overall_status")
                if name == "a11oy_build_info" and source_sha:
                    source_bound = source_sha in json.dumps(
                        payload, sort_keys=True, default=str
                    )
                    evidence["source_bound"] = source_bound
                    ok = ok and source_bound
        return Gate(
            f"probe:{name}",
            ok,
            f"HEAD={head.status_code}; GET={response.status_code}; "
            f"final={response.url}; bytes={len(response.content)}",
            evidence,
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
        return Gate(
            "organization_open_prs",
            False,
            f"{type(exc).__name__}: {exc}",
            {},
        )


def evaluate(
    client: GitHubClient,
    org_client: GitHubClient,
    org_token_configured: bool,
) -> dict[str, Any]:
    gates = [
        evaluate_issue_gate(client, name, repo, number)
        for name, (repo, number) in EVIDENCE_ISSUES.items()
    ]
    gates.append(evaluate_credential_gate(client, org_client, org_token_configured))

    source_sha = None
    try:
        relock_issue = client.issue(*EVIDENCE_ISSUES["canonical_a11oy_relock"])
        source_sha = str(_latest_report(relock_issue).get("github_source_sha") or "")
    except Exception:  # noqa: BLE001
        source_sha = None

    gates.extend(safe_probe(name, url, source_sha) for name, url in SAFE_PROBES.items())
    gates.append(evaluate_open_prs(org_client))
    operational = all(gate.ok for gate in gates)
    return {
        "schema": "szl.final-estate-reconciliation/v4",
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
        "model_boundaries": {
            "szl_nemo_v3": "CURRICULUM_MATERIALIZED_NOT_TRAINED",
            "brain": "OPERATIONAL_CAPABILITIES_NOT_A_FULLY_TRAINED_NEURAL_MODEL",
        },
        "boundaries": [
            "The controller performs only GitHub evidence reads, safe public GET/HEAD probes, and one deterministic issue update.",
            "It does not mutate any Hugging Face asset, deployment, visibility, hardware, model, dataset, kernel, collection, or bucket.",
            "OPERATIONAL_VERIFIED requires every gate to pass in the same run.",
            "Organization-wide pull-request completeness requires a live SZL_GITHUB_TOKEN and a closed credential-health issue.",
            "Operational verification does not claim SZL-Nemo v3 is trained or the Brain is a fully trained neural model.",
        ],
    }


def issue_body(report: dict[str, Any], run_url: str | None) -> str:
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
    parser.add_argument(
        "--output", default="reports/final-estate-reconciliation-v4.json"
    )
    parser.add_argument("--publish-issue", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    repository_token = (
        os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("SZL_GITHUB_TOKEN")
    )
    organization_token = os.environ.get("SZL_GITHUB_TOKEN")
    client = GitHubClient(repository_token)
    org_client = GitHubClient(organization_token)
    report = evaluate(client, org_client, bool(organization_token))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))

    if args.publish_issue:
        run_url = None
        if (
            os.environ.get("GITHUB_SERVER_URL")
            and os.environ.get("GITHUB_REPOSITORY")
            and os.environ.get("GITHUB_RUN_ID")
        ):
            run_url = (
                f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
                f"/actions/runs/{os.environ['GITHUB_RUN_ID']}"
            )
        try:
            client.upsert_report_issue(
                issue_body(report, run_url), bool(report["operational_verified"])
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"FATAL: deterministic report issue publication failed: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 2

    if args.enforce and not report["operational_verified"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
