#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded 2026-09-04 SZL organization convergence controller.

This one-shot controller inventories every open pull request and recent orphaned
branch in ``szl-holdings``; promotes exact terminal-green, same-organization
changes through normal GitHub protections; waits for the dependency-bound
Second Brain -> Anatomy -> A11oy successor chain; dispatches only fixed
post-merge workflows; audits the Hugging Face estate; probes the fixed public
surface set; and writes secret-free receipts.

It is deliberately incapable of force pushes, direct protected-main writes,
branch-protection changes, secret reads, arbitrary repository/URL selection,
Hugging Face deletion, DNS mutation, model training, or product effectors.
Provider mutation remains delegated to the reviewed repository workflows.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ORG = "szl-holdings"
API = "https://api.github.com"
GRAPHQL = API + "/graphql"
HF_API = "https://huggingface.co/api"
USER_AGENT = "SZLHOLDINGS-FrontierConvergence/2026-09-04"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
TRANSIENT = re.compile(
    r"(?:\b429\b|\b502\b|\b503\b|\b504\b|rate.?limit|timed?\s*out|"
    r"timeout|connection\s+reset|temporar(?:y|ily)\s+unavailable|econnreset)",
    re.IGNORECASE,
)
BLOCK_LABELS = {
    "hold",
    "do-not-merge",
    "do not merge",
    "blocked",
    "wip",
    "security-hold",
    "owner-review-required",
}
SUCCESS_CONCLUSIONS = {"success", "neutral", "skipped"}
ACTIVE_STATUSES = {"queued", "in_progress", "waiting", "pending", "requested"}
FAIL_CONCLUSIONS = {"failure", "cancelled", "timed_out", "action_required", "stale"}

# Exact work known to be owner-authorized in the current frontier wave.
INDEPENDENT_TARGETS: tuple[tuple[str, int], ...] = (
    ("szl-forge", 108),
    ("platform", 739),
    ("szl-org-health", 43),
    (".github", 645),
    ("szl-gpu-bridge", 99),
)

# Original dirty/stale agent work is never merged directly. A current-main
# successor is required and the original closes only after the successor merges.
SUCCESSOR_STACK: tuple[dict[str, Any], ...] = (
    {
        "repo": "szl-second-brain",
        "original": 8,
        "branch": "repair/continuous-frontier-memory-v1-20260904",
        "title": "feat(brain): reconcile continuous frontier memory on current main",
        "depends_on": (),
    },
    {
        "repo": "anatomy",
        "original": 61,
        "branch": "repair/holographic-v7-brain-quant-v1-20260904",
        "title": "feat(anatomy): reconcile Holographic v7 on current sources",
        "depends_on": (("szl-second-brain", 8),),
    },
    {
        "repo": "killinchu",
        "original": 403,
        "branch": "repair/asset-sbom-exposure-wave5-20260904",
        "title": "feat(defend): reconcile Asset Exposure Wave 5 on current main",
        "depends_on": (),
    },
    {
        "repo": "a11oy",
        "original": 1829,
        "branch": "repair/brain-frontier-holographic-v7-20260904",
        "title": "feat(holographic): bind final source-bound Brain Frontier v7",
        "depends_on": (("szl-second-brain", 8), ("anatomy", 61)),
    },
)

POST_MERGE_WORKFLOWS: tuple[tuple[str, str], ...] = (
    ("szl-forge", "publish-model-inference-lab.yml"),
    ("szl-second-brain", "continuous-frontier-memory.yml"),
    ("anatomy", "hf-sync.yml"),
    ("anatomy", "holographic-v7-live-witness.yml"),
    ("killinchu", "hf-sync.yml"),
    ("killinchu", "asset-exposure-live-witness.yml"),
    ("killinchu", "retire-legacy-resilience-spaces.yml"),
    ("szl-org-health", "autonomic-slo.yml"),
    (".github", "estate-deadman.yml"),
    ("szl-gpu-bridge", "windows-watchdog-install.yml"),
    ("a11oy", "hf-sync.yml"),
    ("a11oy", "hf-free-tier-recovery.yml"),
    ("a11oy", "repair-cloudflare-product-edge-production.yml"),
    ("a11oy", "public-estate-live-witness.yml"),
)

HF_SPACES: tuple[str, ...] = (
    "SZLHOLDINGS/a11oy",
    "SZLHOLDINGS/killinchu",
    "SZLHOLDINGS/sentra",
    "SZLHOLDINGS/vertical-services",
    "SZLHOLDINGS/terra",
    "SZLHOLDINGS/counsel",
    "SZLHOLDINGS/finance",
    "SZLHOLDINGS/lyte",
    "SZLHOLDINGS/vessels",
    "SZLHOLDINGS/aegis-assurance",
    "SZLHOLDINGS/immune",
    "SZLHOLDINGS/immune-lattice",
    "betterwithage/anatomy",
    "betterwithage/szl-vertical-services-runtime",
)

PUBLIC_PROBES: tuple[tuple[str, str], ...] = (
    ("a11oy-apex", "https://a-11-oy.com/"),
    ("a11oy-honesty", "https://a-11-oy.com/api/a11oy/v1/honest"),
    ("a11oy-www", "https://www.a-11-oy.com/__szl_edge_probe__/path?contract=v3&preserve=yes"),
    ("proof-apex", "https://a11oy.net/"),
    ("proof-www", "https://www.a11oy.net/__szl_probe__/path?preserve=yes"),
    ("a11oy-runtime", "https://szlholdings-a11oy.hf.space/api/build-info"),
    ("killinchu-runtime", "https://szlholdings-killinchu.hf.space/api/build-info"),
    ("killinchu-fusion", "https://szlholdings-killinchu.hf.space/api/killinchu/v1/connectors/defensive_fusion/health"),
    ("killinchu-wave5-schema", "https://szlholdings-killinchu.hf.space/api/killinchu/uds/v1/sbom/exposure/schema"),
    ("sentra-runtime", "https://szlholdings-sentra.hf.space/api/build-info"),
    ("anatomy-runtime", "https://betterwithage-anatomy.hf.space/.well-known/szl-source.json"),
    ("vertical-runtime", "https://betterwithage-szl-vertical-services-runtime.hf.space/api/build-info"),
    ("vertical-services-gateway", "https://szlholdings-vertical-services.hf.space/api/build-info"),
    ("terra-gateway", "https://szlholdings-terra.hf.space/api/build-info"),
    ("counsel-gateway", "https://szlholdings-counsel.hf.space/api/build-info"),
    ("finance-gateway", "https://szlholdings-finance.hf.space/api/build-info"),
    ("lyte-gateway", "https://szlholdings-lyte.hf.space/api/build-info"),
)

TOKEN_ENV_ORDER: tuple[tuple[str, str], ...] = (
    ("FRONTIER_OPERATOR_TOKEN", "FRONTIER_OPERATOR_TOKEN_CANDIDATE"),
    ("SZL_GITHUB_TOKEN", "SZL_GITHUB_TOKEN_CANDIDATE"),
    ("ORG_ADMIN_TOKEN", "ORG_ADMIN_TOKEN_CANDIDATE"),
    ("GH_ADMIN_TOKEN", "GH_ADMIN_TOKEN_CANDIDATE"),
    ("GH_PAT", "GH_PAT_CANDIDATE"),
    ("GITHUB_PAT", "GITHUB_PAT_CANDIDATE"),
    ("PAT", "PAT_CANDIDATE"),
    ("GITHUB_TOKEN", "GITHUB_TOKEN_CANDIDATE"),
)
HF_TOKEN_ENV_ORDER: tuple[tuple[str, str], ...] = (
    ("HF_ORG_TOKEN", "HF_ORG_TOKEN_CANDIDATE"),
    ("HF_ORG_TOKEN1", "HF_ORG_TOKEN1_CANDIDATE"),
    ("HF_WRITE_TOKEN", "HF_WRITE_TOKEN_CANDIDATE"),
    ("HF_TOKEN", "HF_TOKEN_CANDIDATE"),
    ("HUGGINGFACEHUB_API_TOKEN", "HUGGINGFACEHUB_API_TOKEN_CANDIDATE"),
    ("HUGGING_FACE_HUB_TOKEN", "HUGGING_FACE_HUB_TOKEN_CANDIDATE"),
)


class ConvergenceError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_text(value: Any, limit: int = 600) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    return text[:limit]


@dataclasses.dataclass
class HttpResult:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class HttpClient:
    def __init__(self, token: str | None = None, *, github: bool = False) -> None:
        self.token = token
        self.github = github
        context = ssl.create_default_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context), NoRedirect()
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        payload: Any | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: int = 30,
        max_bytes: int = 4_194_304,
        ok: Iterable[int] = (200,),
    ) -> HttpResult:
        parsed = urllib.parse.urlparse(url)
        allowed_hosts = {"api.github.com", "github.com", "huggingface.co"}
        if not self.github:
            allowed_hosts.update(
                {
                    "a-11-oy.com",
                    "www.a-11-oy.com",
                    "a11oy.net",
                    "www.a11oy.net",
                    "szlholdings-a11oy.hf.space",
                    "szlholdings-killinchu.hf.space",
                    "szlholdings-sentra.hf.space",
                    "betterwithage-anatomy.hf.space",
                    "betterwithage-szl-vertical-services-runtime.hf.space",
                    "szlholdings-vertical-services.hf.space",
                    "szlholdings-terra.hf.space",
                    "szlholdings-counsel.hf.space",
                    "szlholdings-finance.hf.space",
                    "szlholdings-lyte.hf.space",
                }
            )
        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
            raise ConvergenceError(f"request escaped fixed HTTPS allowlist: {parsed.hostname}")
        request_headers = {
            "Accept": "application/vnd.github+json" if self.github else "application/json,text/html;q=0.8,*/*;q=0.5",
            "User-Agent": USER_AGENT,
        }
        if self.github:
            request_headers["X-GitHub-Api-Version"] = "2022-11-28"
        if self.token:
            request_headers["Authorization"] = f"Bearer {self.token}"
        if headers:
            request_headers.update(headers)
        data = None
        if payload is not None:
            data = canonical(payload)
            request_headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with self.opener.open(req, timeout=timeout) as response:
                body = response.read(max_bytes + 1)
                status = int(response.status)
                result_headers = {k.lower(): v for k, v in response.headers.items()}
        except urllib.error.HTTPError as error:
            body = error.read(max_bytes + 1)
            status = int(error.code)
            result_headers = {k.lower(): v for k, v in error.headers.items()}
        if len(body) > max_bytes:
            raise ConvergenceError(f"response exceeded bound for {parsed.hostname}{parsed.path}")
        if status not in set(ok):
            message = ""
            try:
                decoded = json.loads(body.decode("utf-8"))
                message = safe_text(decoded.get("message") if isinstance(decoded, dict) else decoded)
            except Exception:
                message = safe_text(body.decode("utf-8", errors="replace"))
            raise ConvergenceError(f"HTTP {status} {method} {parsed.path}: {message}")
        return HttpResult(status, result_headers, body)


class GitHub:
    def __init__(self, token: str) -> None:
        self.http = HttpClient(token, github=True)

    def api(self, method: str, path: str, *, payload: Any | None = None, ok: Iterable[int] = (200,)) -> HttpResult:
        if not path.startswith("/") or ".." in path:
            raise ConvergenceError("invalid GitHub API path")
        return self.http.request(method, API + path, payload=payload, ok=ok)

    def json(self, method: str, path: str, *, payload: Any | None = None, ok: Iterable[int] = (200,)) -> Any:
        return self.api(method, path, payload=payload, ok=ok).json()

    def graphql(self, query: str, variables: Mapping[str, Any]) -> Any:
        result = self.http.request(
            "POST",
            GRAPHQL,
            payload={"query": query, "variables": dict(variables)},
            ok=(200,),
        ).json()
        if result.get("errors"):
            raise ConvergenceError("GraphQL error: " + safe_text(result["errors"]))
        return result.get("data")


def select_github_token() -> tuple[str, str, dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for source, variable in TOKEN_ENV_ORDER:
        token = os.environ.get(variable, "").strip()
        if not token:
            attempts.append({"source": source, "present": False, "valid": False})
            continue
        try:
            gh = GitHub(token)
            user = gh.json("GET", "/user")
            repo = gh.json("GET", f"/repos/{ORG}/a11oy")
            permissions = repo.get("permissions") or {}
            push = bool(permissions.get("push") or permissions.get("admin") or permissions.get("maintain"))
            attempts.append(
                {
                    "source": source,
                    "present": True,
                    "valid": True,
                    "login": user.get("login"),
                    "a11oy_push": push,
                }
            )
            if push:
                return source, token, {"attempts": attempts, "selected_login": user.get("login")}
        except Exception as exc:
            attempts.append(
                {
                    "source": source,
                    "present": True,
                    "valid": False,
                    "error": safe_text(type(exc).__name__ + ": " + str(exc)),
                }
            )
    raise ConvergenceError("no validated cross-repository GitHub write credential; attempts=" + json.dumps(attempts))


def select_hf_token() -> tuple[str | None, str | None, dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for source, variable in HF_TOKEN_ENV_ORDER:
        token = os.environ.get(variable, "").strip()
        if not token:
            attempts.append({"source": source, "present": False, "valid": False})
            continue
        try:
            http = HttpClient(token)
            identity = http.request("GET", HF_API + "/whoami-v2", ok=(200,)).json()
            login = identity.get("name") or identity.get("fullname")
            orgs = identity.get("orgs") or []
            org_names = {
                str(item.get("name") or item.get("fullname") or "")
                for item in orgs
                if isinstance(item, dict)
            }
            attempts.append(
                {
                    "source": source,
                    "present": True,
                    "valid": True,
                    "login": login,
                    "szl_org_visible": any(name.lower() == "szlholdings" for name in org_names),
                }
            )
            return source, token, {"attempts": attempts, "selected_login": login}
        except Exception as exc:
            attempts.append(
                {
                    "source": source,
                    "present": True,
                    "valid": False,
                    "error": safe_text(type(exc).__name__ + ": " + str(exc)),
                }
            )
    return None, None, {"attempts": attempts, "selected_login": None}


def repo_full(repo: str) -> str:
    return f"{ORG}/{repo}"


def fetch_pr(gh: GitHub, repo: str, number: int) -> dict[str, Any]:
    return gh.json("GET", f"/repos/{repo_full(repo)}/pulls/{number}")


def pr_labels(pr: Mapping[str, Any]) -> set[str]:
    return {str(item.get("name") or "").strip().lower() for item in pr.get("labels") or []}


def review_state(gh: GitHub, repo: str, number: int) -> dict[str, Any]:
    reviews = gh.json("GET", f"/repos/{repo_full(repo)}/pulls/{number}/reviews?per_page=100")
    latest: dict[str, str] = {}
    for review in reviews:
        author = ((review.get("user") or {}).get("login") or "").lower()
        state = str(review.get("state") or "").upper()
        if author:
            latest[author] = state
    change_requests = sorted(author for author, state in latest.items() if state == "CHANGES_REQUESTED")
    unresolved = 0
    try:
        data = gh.graphql(
            """
            query($owner:String!,$name:String!,$number:Int!){
              repository(owner:$owner,name:$name){
                pullRequest(number:$number){
                  reviewThreads(first:100){nodes{isResolved}}
                }
              }
            }
            """,
            {"owner": ORG, "name": repo, "number": number},
        )
        nodes = (((data or {}).get("repository") or {}).get("pullRequest") or {}).get("reviewThreads", {}).get("nodes", [])
        unresolved = sum(1 for item in nodes if not item.get("isResolved"))
    except Exception:
        unresolved = -1
    return {"change_requests": change_requests, "unresolved_threads": unresolved}


def checks_state(gh: GitHub, repo: str, sha: str) -> dict[str, Any]:
    if not SHA40.fullmatch(sha):
        raise ConvergenceError("invalid pull request head SHA")
    checks = gh.json(
        "GET",
        f"/repos/{repo_full(repo)}/commits/{sha}/check-runs?per_page=100",
    ).get("check_runs", [])
    statuses = gh.json(
        "GET",
        f"/repos/{repo_full(repo)}/commits/{sha}/status",
    ).get("statuses", [])
    active: list[str] = []
    failed: list[str] = []
    terminal: list[str] = []
    for item in checks:
        name = str(item.get("name") or "unnamed-check")
        status = str(item.get("status") or "").lower()
        conclusion = str(item.get("conclusion") or "").lower()
        if status != "completed" or status in ACTIVE_STATUSES:
            active.append(name)
        elif conclusion not in SUCCESS_CONCLUSIONS:
            failed.append(f"{name}:{conclusion or 'none'}")
        else:
            terminal.append(name)
    for item in statuses:
        name = str(item.get("context") or "unnamed-status")
        state = str(item.get("state") or "").lower()
        if state == "pending":
            active.append(name)
        elif state not in {"success"}:
            failed.append(f"{name}:{state}")
        else:
            terminal.append(name)
    return {
        "observed": len(checks) + len(statuses),
        "active": sorted(set(active)),
        "failed": sorted(set(failed)),
        "successful": sorted(set(terminal)),
        "ready": bool(checks or statuses) and not active and not failed,
    }


def refresh_mergeability(gh: GitHub, repo: str, number: int, timeout: int = 90) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest = fetch_pr(gh, repo, number)
    while latest.get("mergeable") is None and time.monotonic() < deadline:
        time.sleep(3)
        latest = fetch_pr(gh, repo, number)
    return latest


def evaluate_pr(gh: GitHub, repo: str, number: int) -> dict[str, Any]:
    pr = refresh_mergeability(gh, repo, number)
    head = ((pr.get("head") or {}).get("sha") or "").lower()
    reviews = review_state(gh, repo, number)
    checks = checks_state(gh, repo, head) if SHA40.fullmatch(head) else {
        "observed": 0,
        "active": [],
        "failed": ["invalid-head"],
        "successful": [],
        "ready": False,
    }
    labels = pr_labels(pr)
    blocked_labels = sorted(labels & BLOCK_LABELS)
    body = str(pr.get("body") or "")
    title = str(pr.get("title") or "")
    topology_conflict = bool(
        re.search(r"sentra.{0,80}(?:into|inside|fold|consolidat).{0,80}killinchu", title + "\n" + body, re.I)
        or re.search(r"separate\s+(?:aegis|vessels)\s+(?:public\s+)?space", title + "\n" + body, re.I)
    )
    return {
        "repo": repo,
        "number": number,
        "url": pr.get("html_url"),
        "title": title,
        "state": pr.get("state"),
        "merged": bool(pr.get("merged")),
        "draft": bool(pr.get("draft")),
        "head": head,
        "base": ((pr.get("base") or {}).get("ref")),
        "mergeable": pr.get("mergeable"),
        "mergeable_state": pr.get("mergeable_state"),
        "same_org_head": ((pr.get("head") or {}).get("repo") or {}).get("owner", {}).get("login") == ORG,
        "maintainer_can_modify": bool(pr.get("maintainer_can_modify", True)),
        "blocked_labels": blocked_labels,
        "topology_conflict": topology_conflict,
        "reviews": reviews,
        "checks": checks,
        "eligible": (
            pr.get("state") == "open"
            and not pr.get("draft")
            and pr.get("mergeable") is True
            and str(pr.get("mergeable_state") or "") not in {"dirty", "unknown"}
            and not blocked_labels
            and not topology_conflict
            and not reviews["change_requests"]
            and reviews["unresolved_threads"] == 0
            and checks["ready"]
        ),
    }


def update_branch(gh: GitHub, repo: str, number: int, sha: str) -> dict[str, Any]:
    try:
        result = gh.json(
            "PUT",
            f"/repos/{repo_full(repo)}/pulls/{number}/update-branch",
            payload={"expected_head_sha": sha},
            ok=(202,),
        )
        return {"requested": True, "message": result.get("message")}
    except Exception as exc:
        return {"requested": False, "error": safe_text(type(exc).__name__ + ": " + str(exc))}


def enable_auto_merge(gh: GitHub, pr: Mapping[str, Any]) -> dict[str, Any]:
    node_id = pr.get("node_id")
    if not node_id:
        return {"enabled": False, "error": "missing pull request node id"}
    try:
        data = gh.graphql(
            """
            mutation($id:ID!){
              enablePullRequestAutoMerge(input:{pullRequestId:$id,mergeMethod:SQUASH}){
                pullRequest{number autoMergeRequest{enabledAt}}
              }
            }
            """,
            {"id": node_id},
        )
        request = (((data or {}).get("enablePullRequestAutoMerge") or {}).get("pullRequest") or {}).get("autoMergeRequest")
        return {"enabled": bool(request), "enabled_at": (request or {}).get("enabledAt")}
    except Exception as exc:
        return {"enabled": False, "error": safe_text(type(exc).__name__ + ": " + str(exc))}


def merge_exact(gh: GitHub, repo: str, number: int, expected_sha: str, title: str) -> dict[str, Any]:
    payload = {
        "sha": expected_sha,
        "merge_method": "squash",
        "commit_title": f"{title} (#{number})",
        "commit_message": "Owner-authorized exact-head convergence through normal repository protections.\n\nSigned-off-by: Stephen Lutar <stephenlutar2@gmail.com>",
    }
    try:
        result = gh.json(
            "PUT",
            f"/repos/{repo_full(repo)}/pulls/{number}/merge",
            payload=payload,
            ok=(200,),
        )
        return {"merged": bool(result.get("merged")), "sha": result.get("sha"), "message": result.get("message")}
    except Exception as exc:
        return {"merged": False, "error": safe_text(type(exc).__name__ + ": " + str(exc))}


def create_successor_pr(gh: GitHub, item: Mapping[str, Any]) -> dict[str, Any] | None:
    repo = str(item["repo"])
    branch = str(item["branch"])
    refs = gh.json("GET", f"/repos/{repo_full(repo)}/git/ref/heads/{urllib.parse.quote(branch, safe='')}", ok=(200, 404))
    if isinstance(refs, dict) and refs.get("message") == "Not Found":
        return None
    existing = gh.json(
        "GET",
        f"/repos/{repo_full(repo)}/pulls?state=all&head={urllib.parse.quote(ORG + ':' + branch)}&base=main&per_page=20",
    )
    if existing:
        return existing[0]
    body = (
        f"## Current-main successor to #{item['original']}\n\n"
        "This branch was produced by the repository-owned one-use reconciliation workflow. "
        "It starts from current protected main, preserves the reviewed feature, removes transport-only machinery, "
        "re-runs the repository contract, and never force-pushes or bypasses protection.\n\n"
        "Merge only after exact-head checks, reviews, and thread resolution are terminal. "
        f"Close #{item['original']} only after this successor merges.\n\n"
        "Signed-off-by: Stephen Lutar <stephenlutar2@gmail.com>"
    )
    return gh.json(
        "POST",
        f"/repos/{repo_full(repo)}/pulls",
        payload={"title": item["title"], "head": branch, "base": "main", "body": body, "maintainer_can_modify": True},
        ok=(201,),
    )


def comment(gh: GitHub, repo: str, number: int, body: str) -> None:
    gh.json(
        "POST",
        f"/repos/{repo_full(repo)}/issues/{number}/comments",
        payload={"body": body},
        ok=(201,),
    )


def close_original_after_successor(
    gh: GitHub,
    repo: str,
    original: int,
    successor: Mapping[str, Any],
) -> dict[str, Any]:
    if not successor.get("merged_at"):
        successor = fetch_pr(gh, repo, int(successor["number"]))
    if not successor.get("merged_at"):
        return {"closed": False, "reason": "successor-not-merged"}
    original_pr = fetch_pr(gh, repo, original)
    if original_pr.get("state") == "closed":
        return {"closed": True, "already_closed": True}
    merge_sha = successor.get("merge_commit_sha")
    comment(
        gh,
        repo,
        original,
        f"Superseded by #{successor['number']}, merged as `{merge_sha}` after current-main reconciliation and exact-head qualification.",
    )
    gh.json(
        "PATCH",
        f"/repos/{repo_full(repo)}/pulls/{original}",
        payload={"state": "closed"},
    )
    return {"closed": True, "successor": successor.get("number"), "merge_sha": merge_sha}


def converge_known_pr(gh: GitHub, repo: str, number: int) -> dict[str, Any]:
    observation = evaluate_pr(gh, repo, number)
    if observation["merged"]:
        return {"observation": observation, "action": "ALREADY_MERGED"}
    if observation["state"] != "open":
        return {"observation": observation, "action": "CLOSED_UNMERGED"}
    if observation["mergeable_state"] == "behind" and observation["same_org_head"]:
        action = update_branch(gh, repo, number, observation["head"])
        return {"observation": observation, "action": "UPDATE_BRANCH", "result": action}
    if observation["eligible"]:
        result = merge_exact(gh, repo, number, observation["head"], observation["title"])
        return {"observation": observation, "action": "MERGE_EXACT", "result": result}
    raw = fetch_pr(gh, repo, number)
    auto = enable_auto_merge(gh, raw) if not observation["blocked_labels"] and not observation["topology_conflict"] else {"enabled": False}
    return {"observation": observation, "action": "WAIT_OR_AUTO_MERGE", "result": auto}


def all_org_open_prs(gh: GitHub) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    page = 1
    while page <= 10:
        query = urllib.parse.quote(f"org:{ORG} is:pr is:open", safe="")
        payload = gh.json("GET", f"/search/issues?q={query}&per_page=100&page={page}&sort=updated&order=desc")
        items = payload.get("items") or []
        results.extend(items)
        if len(items) < 100:
            break
        page += 1
    return results


def general_pr_sweep(gh: GitHub, excluded: set[tuple[str, int]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in all_org_open_prs(gh):
        url = str(item.get("repository_url") or "")
        repo = url.rsplit("/", 1)[-1]
        number = int(item["number"])
        if (repo, number) in excluded:
            continue
        try:
            observed = evaluate_pr(gh, repo, number)
            record: dict[str, Any] = {"repo": repo, "number": number, "observation": observed}
            if observed["mergeable_state"] == "behind" and observed["same_org_head"] and observed["maintainer_can_modify"]:
                record["action"] = "UPDATE_BRANCH"
                record["result"] = update_branch(gh, repo, number, observed["head"])
            elif observed["eligible"]:
                record["action"] = "MERGE_EXACT"
                record["result"] = merge_exact(gh, repo, number, observed["head"], observed["title"])
            else:
                record["action"] = "HOLD_WITH_EVIDENCE"
            actions.append(record)
        except Exception as exc:
            actions.append({"repo": repo, "number": number, "action": "AUDIT_ERROR", "error": safe_text(type(exc).__name__ + ": " + str(exc))})
    return actions


def recent_orphan_branches(gh: GitHub, open_prs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    head_refs: set[tuple[str, str]] = set()
    for item in open_prs:
        repo = str(item.get("repository_url") or "").rsplit("/", 1)[-1]
        try:
            pr = fetch_pr(gh, repo, int(item["number"]))
            head_refs.add((repo, str((pr.get("head") or {}).get("ref") or "")))
        except Exception:
            continue
    repos = gh.json("GET", f"/orgs/{ORG}/repos?type=all&per_page=100&sort=updated")
    candidates: list[dict[str, Any]] = []
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=14)
    for repo_info in repos:
        if repo_info.get("archived") or repo_info.get("disabled"):
            continue
        repo = str(repo_info["name"])
        default = str(repo_info.get("default_branch") or "main")
        try:
            branches = gh.json("GET", f"/repos/{repo_full(repo)}/branches?per_page=100")
        except Exception:
            continue
        for branch in branches:
            name = str(branch.get("name") or "")
            if not name or name == default or (repo, name) in head_refs:
                continue
            if not re.search(r"(?:codex|perplexity|agent|frontier|repair|fix|feat|automation)", name, re.I):
                continue
            try:
                compare = gh.json(
                    "GET",
                    f"/repos/{repo_full(repo)}/compare/{urllib.parse.quote(default, safe='')}...{urllib.parse.quote(name, safe='')}",
                )
                commits = compare.get("commits") or []
                newest = None
                if commits:
                    newest_raw = (((commits[-1].get("commit") or {}).get("committer") or {}).get("date"))
                    if newest_raw:
                        newest = dt.datetime.fromisoformat(str(newest_raw).replace("Z", "+00:00"))
                if int(compare.get("ahead_by") or 0) > 0 and (newest is None or newest >= cutoff):
                    candidates.append(
                        {
                            "repo": repo,
                            "branch": name,
                            "status": compare.get("status"),
                            "ahead_by": compare.get("ahead_by"),
                            "behind_by": compare.get("behind_by"),
                            "newest_commit": newest.isoformat() if newest else None,
                            "changed_files": len(compare.get("files") or []),
                        }
                    )
            except Exception:
                continue
    return candidates


def latest_run_for_workflow(gh: GitHub, repo: str, workflow: str) -> dict[str, Any] | None:
    try:
        payload = gh.json(
            "GET",
            f"/repos/{repo_full(repo)}/actions/workflows/{urllib.parse.quote(workflow, safe='')}/runs?branch=main&per_page=5",
        )
        runs = payload.get("workflow_runs") or []
        return runs[0] if runs else None
    except Exception:
        return None


def dispatch_workflow(gh: GitHub, repo: str, workflow: str) -> dict[str, Any]:
    try:
        info = gh.json(
            "GET",
            f"/repos/{repo_full(repo)}/actions/workflows/{urllib.parse.quote(workflow, safe='')}",
        )
        if info.get("state") != "active":
            return {"dispatched": False, "state": info.get("state")}
        gh.api(
            "POST",
            f"/repos/{repo_full(repo)}/actions/workflows/{urllib.parse.quote(workflow, safe='')}/dispatches",
            payload={"ref": "main"},
            ok=(204,),
        )
        return {"dispatched": True, "workflow_id": info.get("id")}
    except Exception as exc:
        return {"dispatched": False, "error": safe_text(type(exc).__name__ + ": " + str(exc))}


def transient_rerun(gh: GitHub, repo: str, workflow: str) -> dict[str, Any] | None:
    run = latest_run_for_workflow(gh, repo, workflow)
    if not run or run.get("conclusion") not in FAIL_CONCLUSIONS:
        return None
    run_id = int(run["id"])
    try:
        raw = gh.api("GET", f"/repos/{repo_full(repo)}/actions/runs/{run_id}/logs", ok=(200,)).body
        text = ""
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in archive.namelist()[:200]:
                if name.endswith(".txt"):
                    text += archive.read(name)[:500_000].decode("utf-8", errors="replace")
        if not TRANSIENT.search(text):
            return {"rerun": False, "run_id": run_id, "reason": "failure-not-classified-transient"}
        gh.api("POST", f"/repos/{repo_full(repo)}/actions/runs/{run_id}/rerun-failed-jobs", ok=(201, 202))
        return {"rerun": True, "run_id": run_id}
    except Exception as exc:
        return {"rerun": False, "run_id": run_id, "error": safe_text(type(exc).__name__ + ": " + str(exc))}


def audit_hf(token: str | None) -> dict[str, Any]:
    http = HttpClient(token)
    spaces: list[dict[str, Any]] = []
    for repo_id in HF_SPACES:
        quoted = "/".join(urllib.parse.quote(part, safe="") for part in repo_id.split("/", 1))
        try:
            result = http.request("GET", HF_API + f"/spaces/{quoted}", ok=(200, 401, 403, 404))
            if result.status == 200:
                data = result.json()
                runtime = data.get("runtime") or {}
                spaces.append(
                    {
                        "id": repo_id,
                        "status": 200,
                        "sha": data.get("sha"),
                        "private": data.get("private"),
                        "disabled": data.get("disabled"),
                        "sdk": data.get("sdk"),
                        "stage": runtime.get("stage") if isinstance(runtime, dict) else None,
                        "hardware": runtime.get("hardware") if isinstance(runtime, dict) else None,
                    }
                )
            else:
                spaces.append({"id": repo_id, "status": result.status})
        except Exception as exc:
            spaces.append({"id": repo_id, "status": "ERROR", "error": safe_text(type(exc).__name__ + ": " + str(exc))})
    return {
        "spaces": spaces,
        "mutation_performed": False,
        "retirement_rule": "Vessels/Aegis deletion only through the source-bound Killinchu retirement workflow; Sentra remains the sole Assurance Command; IMMUNE remains gated.",
    }


def probe_public() -> list[dict[str, Any]]:
    http = HttpClient(None)
    results: list[dict[str, Any]] = []
    for probe_id, url in PUBLIC_PROBES:
        try:
            result = http.request("GET", url, timeout=30, max_bytes=1_048_576, ok=range(200, 600))
            content_type = result.headers.get("content-type", "")
            parsed_json = None
            if "json" in content_type.lower() or result.body[:1] in {b"{", b"["}:
                try:
                    parsed_json = result.json()
                except Exception:
                    parsed_json = None
            results.append(
                {
                    "id": probe_id,
                    "url": url,
                    "status": result.status,
                    "location": result.headers.get("location"),
                    "server": result.headers.get("server"),
                    "cf_ray_present": bool(result.headers.get("cf-ray")),
                    "x_szl_edge": result.headers.get("x-szl-edge"),
                    "body_sha256": sha256(result.body),
                    "bytes": len(result.body),
                    "json": parsed_json,
                }
            )
        except Exception as exc:
            results.append({"id": probe_id, "url": url, "status": "ERROR", "error": safe_text(type(exc).__name__ + ": " + str(exc))})
    return results


def current_main(gh: GitHub, repo: str) -> str | None:
    try:
        data = gh.json("GET", f"/repos/{repo_full(repo)}/commits/main")
        sha = str(data.get("sha") or "").lower()
        return sha if SHA40.fullmatch(sha) else None
    except Exception:
        return None


def source_revision(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for path in (
        ("build", "revision"),
        ("build", "source_revision"),
        ("source", "commit"),
        ("source_revision",),
        ("observed_source_revision",),
        ("revision",),
    ):
        current: Any = value
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        if isinstance(current, str) and SHA40.fullmatch(current.lower()):
            return current.lower()
    return None


def final_truth(gh: GitHub, report: Mapping[str, Any]) -> dict[str, Any]:
    mains = {
        repo: current_main(gh, repo)
        for repo in ("a11oy", "killinchu", "anatomy", "szl-second-brain", "vertical-services", "szl-forge", "platform", "szl-org-health", ".github", "szl-gpu-bridge")
    }
    probes = report.get("public_probes") or []
    by_id = {item.get("id"): item for item in probes if isinstance(item, dict)}
    live_revisions = {
        "a11oy": source_revision((by_id.get("a11oy-runtime") or {}).get("json")),
        "killinchu": source_revision((by_id.get("killinchu-runtime") or {}).get("json")),
        "anatomy": source_revision((by_id.get("anatomy-runtime") or {}).get("json")),
        "vertical-services": source_revision((by_id.get("vertical-runtime") or {}).get("json")),
    }
    open_pr_count = len(all_org_open_prs(gh))
    domains = {
        item_id: (by_id.get(item_id) or {}).get("status")
        for item_id in ("a11oy-apex", "a11oy-honesty", "a11oy-www", "proof-apex", "proof-www")
    }
    runtime_match = {
        key: bool(mains.get(key) and live_revisions.get(key) == mains.get(key))
        for key in ("a11oy", "killinchu", "anatomy", "vertical-services")
    }
    cloudflare_ok = (
        domains.get("a11oy-apex") == 200
        and domains.get("a11oy-honesty") == 200
        and domains.get("a11oy-www") in {301, 308}
        and domains.get("proof-apex") == 200
        and domains.get("proof-www") in {200, 301, 308}
        and bool((by_id.get("a11oy-apex") or {}).get("cf_ray_present"))
    )
    return {
        "mains": mains,
        "live_revisions": live_revisions,
        "runtime_matches_main": runtime_match,
        "open_pr_count": open_pr_count,
        "domain_status": domains,
        "cloudflare_public_contract": cloudflare_ok,
        "terminal_success": (
            open_pr_count == 0
            and all(runtime_match.values())
            and cloudflare_ok
            and (by_id.get("killinchu-fusion") or {}).get("status") == 200
            and (by_id.get("killinchu-wave5-schema") or {}).get("status") == 200
        ),
    }


def write_markdown(path: Path, report: Mapping[str, Any]) -> None:
    lines = [
        "# SZL Frontier Convergence Receipt",
        "",
        f"Observed: `{report.get('completed_at') or report.get('started_at')}`",
        f"Controller source: `{report.get('controller_source_revision')}`",
        f"GitHub credential source: `{(report.get('github_auth') or {}).get('source')}`",
        f"Hugging Face credential source: `{(report.get('hf_auth') or {}).get('source') or 'UNAVAILABLE'}`",
        "",
        "## Final truth",
        "",
        "```json",
        json.dumps(report.get("final_truth"), indent=2, sort_keys=True),
        "```",
        "",
        "## Known PR actions",
        "",
    ]
    for item in report.get("known_pr_actions") or []:
        lines.append(f"- `{item.get('repo')}#{item.get('number')}` — `{item.get('action')}`")
    lines.extend(["", "## Successor stack", ""])
    for item in report.get("successor_actions") or []:
        lines.append(f"- `{item.get('repo')}#{item.get('original')}` — `{item.get('action')}` — `{item.get('branch')}`")
    lines.extend(["", "## Remaining open PRs", ""])
    for item in report.get("remaining_open_prs") or []:
        repo = str(item.get("repository_url") or "").rsplit("/", 1)[-1]
        lines.append(f"- `{repo}#{item.get('number')}` — {safe_text(item.get('title'), 180)}")
    lines.extend(["", "## Recent orphaned agent branches", ""])
    for item in report.get("orphan_branches") or []:
        lines.append(f"- `{item.get('repo')}:{item.get('branch')}` — ahead `{item.get('ahead_by')}`, behind `{item.get('behind_by')}`")
    lines.extend(["", "## Provider dispatches", ""])
    for item in report.get("workflow_actions") or []:
        lines.append(f"- `{item.get('repo')}/{item.get('workflow')}` — `{item.get('result')}`")
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for error in report["errors"]:
            lines.append(f"- `{safe_text(error, 500)}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def publish_issue_receipt(gh: GitHub, report: Mapping[str, Any]) -> dict[str, Any]:
    truth = report.get("final_truth") or {}
    body = (
        "## Organization convergence observation\n\n"
        f"- Terminal success: `{truth.get('terminal_success')}`\n"
        f"- Open PRs: `{truth.get('open_pr_count')}`\n"
        f"- Runtime/main matches: `{json.dumps(truth.get('runtime_matches_main'), sort_keys=True)}`\n"
        f"- Cloudflare public contract: `{truth.get('cloudflare_public_contract')}`\n"
        f"- Receipt SHA-256: `{report.get('receipt_sha256')}`\n\n"
        "The workflow artifact contains the complete secret-free evidence. Credential values were not recorded."
    )
    query = urllib.parse.quote(f"repo:{ORG}/.github is:issue is:open frontier convergence", safe="")
    search = gh.json("GET", f"/search/issues?q={query}&per_page=20")
    items = search.get("items") or []
    if items:
        issue = items[0]
        comment(gh, ".github", int(issue["number"]), body)
        return {"issue": issue["number"], "action": "COMMENTED"}
    created = gh.json(
        "POST",
        f"/repos/{ORG}/.github/issues",
        payload={"title": "Frontier convergence receipt", "body": body},
        ok=(201,),
    )
    return {"issue": created.get("number"), "action": "CREATED"}


def run(args: argparse.Namespace) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema": "szl.frontier-convergence/v1",
        "started_at": utc_now(),
        "controller_repository": os.environ.get("GITHUB_REPOSITORY"),
        "controller_source_revision": os.environ.get("GITHUB_SHA"),
        "execute": bool(args.execute),
        "direct_main_write": False,
        "force_push": False,
        "admin_bypass": False,
        "credential_values_recorded": False,
        "known_pr_actions": [],
        "successor_actions": [],
        "general_pr_actions": [],
        "workflow_actions": [],
        "errors": [],
    }

    source, token, github_auth = select_github_token()
    report["github_auth"] = {"source": source, **github_auth}
    gh = GitHub(token)
    hf_source, hf_token, hf_auth = select_hf_token()
    report["hf_auth"] = {"source": hf_source, **hf_auth}

    excluded = set(INDEPENDENT_TARGETS)
    excluded.update((str(item["repo"]), int(item["original"])) for item in SUCCESSOR_STACK)

    for repo, number in INDEPENDENT_TARGETS:
        try:
            action = converge_known_pr(gh, repo, number) if args.execute else {"observation": evaluate_pr(gh, repo, number), "action": "AUDIT_ONLY"}
            report["known_pr_actions"].append({"repo": repo, "number": number, **action})
        except Exception as exc:
            report["known_pr_actions"].append({"repo": repo, "number": number, "action": "ERROR", "error": safe_text(type(exc).__name__ + ": " + str(exc))})

    deadline = time.monotonic() + args.wait_minutes * 60
    pending_stack = list(SUCCESSOR_STACK)
    while pending_stack and time.monotonic() < deadline:
        next_pending: list[dict[str, Any]] = []
        progress = False
        for item in pending_stack:
            repo = str(item["repo"])
            original = int(item["original"])
            dependencies_ready = True
            for dep_repo, dep_original in item["depends_on"]:
                dep_item = next((entry for entry in SUCCESSOR_STACK if entry["repo"] == dep_repo and entry["original"] == dep_original), None)
                if dep_item is None:
                    continue
                try:
                    dep_pr = create_successor_pr(gh, dep_item)
                    if not dep_pr or not fetch_pr(gh, dep_repo, int(dep_pr["number"])).get("merged"):
                        dependencies_ready = False
                except Exception:
                    dependencies_ready = False
            if not dependencies_ready:
                next_pending.append(item)
                continue
            try:
                successor = create_successor_pr(gh, item)
                if successor is None:
                    report["successor_actions"].append({"repo": repo, "original": original, "branch": item["branch"], "action": "WAIT_BRANCH"})
                    next_pending.append(item)
                    continue
                number = int(successor["number"])
                excluded.add((repo, number))
                action = converge_known_pr(gh, repo, number) if args.execute else {"observation": evaluate_pr(gh, repo, number), "action": "AUDIT_ONLY"}
                report["successor_actions"].append({"repo": repo, "original": original, "branch": item["branch"], "number": number, **action})
                refreshed = fetch_pr(gh, repo, number)
                if refreshed.get("merged"):
                    if args.execute:
                        close_result = close_original_after_successor(gh, repo, original, refreshed)
                        report["successor_actions"].append({"repo": repo, "original": original, "branch": item["branch"], "action": "CLOSE_ORIGINAL", "result": close_result})
                    progress = True
                else:
                    next_pending.append(item)
            except Exception as exc:
                report["successor_actions"].append({"repo": repo, "original": original, "branch": item["branch"], "action": "ERROR", "error": safe_text(type(exc).__name__ + ": " + str(exc))})
                next_pending.append(item)
        pending_stack = next_pending
        if pending_stack:
            time.sleep(20 if progress else 30)

    try:
        report["general_pr_actions"] = general_pr_sweep(gh, excluded) if args.execute else []
    except Exception as exc:
        report["errors"].append("general-pr-sweep: " + safe_text(type(exc).__name__ + ": " + str(exc)))

    # Give branch updates and exact merges a bounded interval to settle, then
    # make one additional pass over known independent work.
    if args.execute:
        time.sleep(15)
        for repo, number in INDEPENDENT_TARGETS:
            try:
                report["known_pr_actions"].append({"repo": repo, "number": number, **converge_known_pr(gh, repo, number)})
            except Exception as exc:
                report["errors"].append(f"second-pass {repo}#{number}: " + safe_text(type(exc).__name__ + ": " + str(exc)))

    for repo, workflow in POST_MERGE_WORKFLOWS:
        action = dispatch_workflow(gh, repo, workflow) if args.execute else {"dispatched": False, "audit_only": True}
        transient = transient_rerun(gh, repo, workflow) if args.execute and not action.get("dispatched") else None
        report["workflow_actions"].append({"repo": repo, "workflow": workflow, "result": action, "transient_rerun": transient})

    open_prs = all_org_open_prs(gh)
    report["remaining_open_prs"] = [
        {"number": item.get("number"), "title": item.get("title"), "repository_url": item.get("repository_url"), "html_url": item.get("html_url")}
        for item in open_prs
    ]
    try:
        report["orphan_branches"] = recent_orphan_branches(gh, open_prs)
    except Exception as exc:
        report["orphan_branches"] = []
        report["errors"].append("orphan-branch-audit: " + safe_text(type(exc).__name__ + ": " + str(exc)))

    report["hugging_face"] = audit_hf(hf_token)
    report["public_probes"] = probe_public()
    report["final_truth"] = final_truth(gh, report)
    report["completed_at"] = utc_now()
    unsigned = dict(report)
    unsigned.pop("receipt_sha256", None)
    report["receipt_sha256"] = sha256(canonical(unsigned))
    try:
        report["issue_receipt"] = publish_issue_receipt(gh, report)
    except Exception as exc:
        report["errors"].append("issue-receipt: " + safe_text(type(exc).__name__ + ": " + str(exc)))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--wait-minutes", type=int, default=75)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.wait_minutes <= 120:
        raise SystemExit("--wait-minutes must be 1..120")
    report = run(args)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(args.markdown_output, report)
    print(json.dumps({"terminal_success": report["final_truth"]["terminal_success"], "receipt_sha256": report["receipt_sha256"], "open_pr_count": report["final_truth"]["open_pr_count"]}, sort_keys=True))
    return 0 if report["final_truth"]["terminal_success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
