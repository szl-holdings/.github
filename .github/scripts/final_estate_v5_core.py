#!/usr/bin/env python3
"""Shared contracts for the active SZL public-estate reconciler v5."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

import requests

from final_estate_v5_inventory import PublicPullRequestObserver

ORG = "szl-holdings"
A11OY_REPOSITORY = "szl-holdings/a11oy"
A11OY_BRANCH = "main"
REPORT_MARKER = "szl-final-estate-reconciliation-v5"
REPORT_SCHEMA = "szl.final-estate-reconciliation/v5"
REPLIT_DECOMMISSION_MARKER = "szl-replit-unified-control-hub-decommissioned"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
KERNEL_IDS = {
    "SZLHOLDINGS/governed-inference-meter",
    "SZLHOLDINGS/szl-governed-norm",
}
CLONE_IDS = {f"SZLHOLDINGS/a11oy-clone-{index}" for index in range(1, 5)}
INVENTORY_SCHEMAS = {
    "szl.hf-official-estate-inventory/v1",
    "szl.hf-official-estate-inventory/v2",
}
EVIDENCE_ISSUES = {
    "official_hf_inventory": ("szl-holdings/.github", 263),
    "hf_release_readiness": ("szl-holdings/.github", 257),
    "hf_release_publication": ("szl-holdings/.github", 301),
}
REPLIT_DECOMMISSION_ISSUE = ("szl-holdings/.github", 273)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_GITHUB_REQUESTS = 532  # Existing census plus fixed source/evidence/artifact reads.


def bounded_content(response: requests.Response, *, deadline: float) -> bytes:
    """Bound decoded body bytes; transport timeouts bound individual blocking reads."""
    chunks: list[bytes] = []
    size = 0
    try:
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES or time.monotonic() > deadline:
                raise RuntimeError("RESPONSE_BUDGET_EXCEEDED")
            chunks.append(chunk)
        if time.monotonic() > deadline:
            raise RuntimeError("RESPONSE_BUDGET_EXCEEDED")
        return b"".join(chunks)
    finally:
        response.close()


@dataclass(frozen=True)
class Gate:
    name: str
    ok: bool
    detail: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class ProbeSpec:
    url: str
    require_head: bool
    media_type: str
    expected_schema: str | None = None
    expected_statuses: tuple[str, ...] = ()
    required_keys: tuple[str, ...] = ()
    source_bound: bool = False


PROBES = {
    "a11oy_product": ProbeSpec("https://a-11-oy.com/", True, "html"),
    "a11oy_pages": ProbeSpec("https://a11oy.net/", True, "html"),
    "a11oy_space": ProbeSpec("https://szlholdings-a11oy.hf.space/", True, "html"),
    "a11oy_livez": ProbeSpec(
        "https://szlholdings-a11oy.hf.space/api/livez",
        False,
        "json",
        expected_statuses=("PROCESS_ALIVE",),
        required_keys=("process", "scope", "production_ready", "receipt_minted"),
    ),
    "a11oy_build_info": ProbeSpec(
        "https://szlholdings-a11oy.hf.space/api/build-info",
        False,
        "json",
        expected_statuses=("OBSERVED",),
        required_keys=("build", "runtime", "receipt_minted"),
        source_bound=True,
    ),
    "a11oy_brain_capabilities": ProbeSpec(
        "https://szlholdings-a11oy.hf.space/api/a11oy/v1/brain/capabilities",
        False,
        "json",
        expected_schema="szl.brain-capabilities.v1",
        required_keys=("capabilities", "claim_policy", "overall_status", "summary"),
    ),
    "a11oy_readiness": ProbeSpec(
        "https://szlholdings-a11oy.hf.space/api/a11oy/v1/readiness/tab-matrix?view=summary",
        False,
        "json",
        required_keys=("honest", "matrix_available", "probe_verdict_available", "view"),
    ),
    "a11oy_holographic": ProbeSpec(
        "https://szlholdings-a11oy.hf.space/holographic", True, "html"
    ),
}


class GitHubClient:
    def __init__(self, token: str | None) -> None:
        self.public_pr_observation: dict[str, Any] | None = None
        self.calls = 0
        self.base = "https://api.github.com"
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "szl-final-estate-reconciliation/5",
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
        allowed_path = (
            path in {"/search/issues", "/orgs/szl-holdings", "/orgs/szl-holdings/repos",
                     "/repos/szl-holdings/.github/branches/main",
                     "/repos/szl-holdings/a11oy/commits/main"}
            or re.fullmatch(r"/repos/szl-holdings/\.github/issues/(263|257|301|273)", path)
            or re.fullmatch(r"/repos/szl-holdings/(?!\.{1,2}/)[A-Za-z0-9_.-]+/pulls", path)
            or path == "/repos/szl-holdings/.github/actions/workflows/hf-release-finalization.yml/runs"
            or re.fullmatch(r"/repos/szl-holdings/\.github/actions/runs/[1-9][0-9]*(/artifacts)?", path)
            or re.fullmatch(r"/repos/szl-holdings/\.github/actions/artifacts/[1-9][0-9]*/zip", path)
        )
        if method != "GET" or payload is not None or not allowed_path:
            raise RuntimeError("GITHUB_READ_SCOPE_REJECTED")
        if self.calls >= MAX_GITHUB_REQUESTS:
            raise RuntimeError("GITHUB_READ_BUDGET_EXCEEDED")
        self.calls += 1
        deadline = time.monotonic() + 60
        response = self.session.request(
            method,
            f"{self.base}{path}",
            params=params,
            allow_redirects=False,
            stream=True,
            timeout=(10, 20),
        )
        if response.status_code not in set(expected):
            response.close()
            raise RuntimeError(
                f"GitHub GET returned HTTP {response.status_code}"
            )
        # Preserve Response.json() for the existing validators, after bounded read.
        response._content = bounded_content(response, deadline=deadline)
        response._content_consumed = True
        return response

    def controller_head(self) -> str:
        value = self.request("GET", "/repos/szl-holdings/.github/branches/main").json()
        commit = value.get("commit") if isinstance(value, dict) else None
        revision = commit.get("sha") if isinstance(commit, dict) else None
        if (not isinstance(value, dict) or value.get("name") != "main"
                or value.get("protected") is not True
                or not isinstance(revision, str) or SHA40.fullmatch(revision) is None
                or revision == "0" * 40):
            raise RuntimeError("CONTROLLER_PROTECTED_MAIN_UNAVAILABLE")
        return revision

    def publication_evidence(self):
        from final_estate_v5_artifacts import publication_evidence
        return publication_evidence(self)

    def issue(self, repo: str, number: int) -> dict[str, Any]:
        value = self.request("GET", f"/repos/{repo}/issues/{number}").json()
        if not isinstance(value, dict):
            raise RuntimeError(f"GitHub issue {repo}#{number} is not an object")
        return value

    def branch_head(self, repo: str, branch: str) -> str:
        value = self.request("GET", f"/repos/{repo}/commits/{branch}").json()
        if not isinstance(value, dict):
            raise RuntimeError(f"GitHub branch head {repo}@{branch} is not an object")
        revision = str(value.get("sha") or "").lower()
        if SHA40.fullmatch(revision) is None:
            raise RuntimeError(f"GitHub branch head lacks an immutable revision: {repo}@{branch}")
        return revision

    def open_public_pull_requests(self) -> list[dict[str, Any]]:
        # Clear any prior evidence before a new observation, including failure.
        self.public_pr_observation = None
        observation = PublicPullRequestObserver(self.request).observe()
        self.public_pr_observation = observation.evidence
        return observation.items

def json_fences(body: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for match in re.finditer(r"```json\s*(\{.*?\})\s*```", body or "", re.DOTALL):
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            output.append(value)
    return output


def latest_report(issue: Mapping[str, Any]) -> dict[str, Any]:
    reports = json_fences(str(issue.get("body") or ""))
    if not reports:
        raise RuntimeError("issue contains no valid fenced JSON evidence")
    return reports[-1]


def summary_clean(report: Mapping[str, Any]) -> bool:
    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        return False
    return all(
        type(summary.get(key)) is int and summary[key] == 0
        for key in ("error", "warning")
    )


def https_origin(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return None
    port = f":{parsed.port}" if parsed.port else ""
    return f"https://{parsed.hostname.lower()}{port}"


def selfcheck_passed(value: Any) -> bool:
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
