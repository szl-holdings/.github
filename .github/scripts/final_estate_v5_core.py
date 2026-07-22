#!/usr/bin/env python3
"""Shared contracts for the active SZL public-estate reconciler v5."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

import requests

ORG = "szl-holdings"
A11OY_REPOSITORY = "szl-holdings/a11oy"
A11OY_BRANCH = "main"
REPORT_TITLE = "[final-estate-reconciliation] SZL Holdings operational estate"
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
        expected_statuses=("LIVE",),
        required_keys=("process", "scope", "receipt_minted"),
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
    "a11oy_3d_estate": ProbeSpec(
        "https://szlholdings-a11oy.hf.space/static/3d/estate.html", True, "html"
    ),
    "a11oy_3d_brain": ProbeSpec(
        "https://szlholdings-a11oy.hf.space/static/3d/brain.html", True, "html"
    ),
}


class GitHubClient:
    def __init__(self, token: str | None) -> None:
        self.base = "https://api.github.com"
        self.session = requests.Session()
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

    def branch_head(self, repo: str, branch: str) -> str:
        value = self.request("GET", f"/repos/{repo}/commits/{branch}").json()
        if not isinstance(value, dict):
            raise RuntimeError(f"GitHub branch head {repo}@{branch} is not an object")
        revision = str(value.get("sha") or "").lower()
        if SHA40.fullmatch(revision) is None:
            raise RuntimeError(f"GitHub branch head lacks an immutable revision: {repo}@{branch}")
        return revision

    def open_public_pull_requests(self) -> list[dict[str, Any]]:
        query = f"org:{ORG} is:pr is:open is:public"
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
        raise RuntimeError("public pull-request search exceeded 1,000 results")

    def upsert_report_issue(self, body: str, operational: bool) -> dict[str, Any]:
        query = f'repo:{ORG}/.github is:issue in:title "{REPORT_TITLE}"'
        payload = self.request(
            "GET", "/search/issues", params={"q": query, "per_page": 10}
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
            return self.request(
                "PATCH",
                f"/repos/{ORG}/.github/issues/{int(exact['number'])}",
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
            created = self.request(
                "PATCH",
                f"/repos/{ORG}/.github/issues/{int(created['number'])}",
                payload={"state": "closed"},
            ).json()
        return created


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
    summary = report.get("summary") or {}
    if not isinstance(summary, Mapping):
        return False
    try:
        return int(summary.get("error", 1)) == 0 and int(summary.get("warning", 0)) == 0
    except (TypeError, ValueError):
        return False


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
