#!/usr/bin/env python3
"""Discover and verify the Unified Control Hub public deployment receipt."""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GITHUB_API = "https://api.github.com"
API_VERSION = "2022-11-28"
CONTROL_REPOSITORY = "szl-holdings/.github"
REPL_ID = "34870515-2d52-4ad8-9636-40cc3ced1771"
REPL_PAGE = "https://replit.com/@stephenlutar2/Unified-Control-Hub"
ISSUE_TITLE = "[replit-deployment-receipt] Unified Control Hub"
FINAL_WORKFLOW = "final-estate-reconciliation.yml"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
URL_RE = re.compile(r"https://[A-Za-z0-9][A-Za-z0-9.-]*\.(?:replit\.app|repl\.co)(?::\d+)?", re.I)
RECEIPT_RE = re.compile(r"https://[^\s`\"'<>]+/api/szl/deployment-receipt(?:\?[^\s`\"'<>]*)?", re.I)
USER_AGENT = "szl-replit-receipt-discovery/1.0"
MAX_BODY = 4 * 1024 * 1024


class DiscoveryError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def github_request(
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    allow_status: set[int] | None = None,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        GITHUB_API + path,
        data=body,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
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
        raise DiscoveryError(f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}") from exc
    return json.loads(raw.decode("utf-8")) if raw else None


def public_request(url: str, *, method: str = "GET", timeout: int = 45) -> dict[str, Any]:
    if method not in {"GET", "HEAD"}:
        raise DiscoveryError(f"unsupported public method {method}")
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "Accept": "application/json, text/plain;q=0.9, text/html;q=0.5",
            "Cache-Control": "no-cache",
            "User-Agent": USER_AGENT,
        },
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as response:
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
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": int(exc.code),
            "requested_url": url,
            "url": url,
            "method": method,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "content_type": str(exc.headers.get("Content-Type") or ""),
            "body": exc.read(4096).decode("utf-8", "replace"),
            "json": None,
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
            "error": f"{type(exc).__name__}: {exc}",
        }


def immutable_sha(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if SHA_RE.fullmatch(text) else None


def candidate_origins() -> tuple[list[str], list[dict[str, Any]]]:
    candidates = {
        "https://unified-control-hub-stephenlutar2.replit.app",
        "https://unified-control-hub--stephenlutar2.repl.co",
        "https://unified-control-hub-stephenlutar2.repl.co",
        "https://unified-control-hub.stephenlutar2.repl.co",
    }
    probes: list[dict[str, Any]] = []
    discovery_urls = [
        REPL_PAGE,
        f"https://replit.com/data/repls/{REPL_ID}",
        f"https://replit.com/api/v1/repls/{REPL_ID}",
    ]
    for url in discovery_urls:
        probe = public_request(url, timeout=60)
        probes.append({key: value for key, value in probe.items() if key != "body"})
        text = probe.get("body") or ""
        for match in URL_RE.findall(text):
            candidates.add(match.rstrip("/"))
        for match in RECEIPT_RE.findall(text):
            parsed = urllib.parse.urlsplit(match)
            candidates.add(f"{parsed.scheme}://{parsed.netloc}")
        payload = probe.get("json")
        if isinstance(payload, dict):
            flattened = json.dumps(payload)
            for match in URL_RE.findall(flattened):
                candidates.add(match.rstrip("/"))
    return sorted(candidates), probes


def receipt_candidates(origin: str) -> tuple[list[str], list[dict[str, Any]]]:
    candidates = [origin.rstrip("/") + "/api/szl/deployment-receipt"]
    probes: list[dict[str, Any]] = []
    handoff = public_request(origin.rstrip("/") + "/REPLIT_DEPLOYMENT_RECEIPT_URL.txt")
    probes.append({key: value for key, value in handoff.items() if key != "body"})
    if handoff.get("ok"):
        for line in str(handoff.get("body") or "").splitlines():
            text = line.strip()
            if text.startswith("https://") and "/api/szl/deployment-receipt" in text:
                candidates.insert(0, text)
                break
    return list(dict.fromkeys(candidates)), probes


def validate_receipt(url: str) -> dict[str, Any]:
    get_probe = public_request(url, method="GET", timeout=60)
    head_probe = public_request(url, method="HEAD", timeout=60)
    payload = get_probe.get("json") if isinstance(get_probe.get("json"), dict) else {}
    source = immutable_sha(
        payload.get("source_revision") or payload.get("source_sha") or payload.get("commit_sha")
    )
    deployment = immutable_sha(
        payload.get("deployment_revision")
        or payload.get("deployment_sha")
        or payload.get("deployed_revision")
    )
    production_url = str(payload.get("production_url") or payload.get("url") or "").strip() or None
    tests = payload.get("tests") or payload.get("test_results")
    mobile = payload.get("mobile") or payload.get("mobile_probes")
    readiness = payload.get("readiness") or payload.get("readiness_probes")
    missing: list[str] = []
    if not get_probe.get("ok"):
        missing.append("receipt GET")
    if not head_probe.get("ok"):
        missing.append("receipt HEAD")
    if not source:
        missing.append("immutable source revision")
    if not deployment:
        missing.append("immutable deployment revision")
    if not production_url or not production_url.startswith("https://"):
        missing.append("production URL")
    if not tests:
        missing.append("test receipt")
    if not mobile:
        missing.append("mobile/keyboard receipt")
    if not readiness:
        missing.append("readiness GET/HEAD receipt")
    production_get = public_request(production_url, method="GET", timeout=60) if production_url else None
    production_head = public_request(production_url, method="HEAD", timeout=60) if production_url else None
    if production_get and not production_get.get("ok"):
        missing.append("production GET")
    if production_head and not production_head.get("ok"):
        missing.append("production HEAD")
    return {
        "ok": not missing,
        "receipt_url": url,
        "source_revision": source,
        "deployment_revision": deployment,
        "production_url": production_url,
        "deployed_at": payload.get("deployed_at"),
        "tests": tests,
        "mobile": mobile,
        "readiness": readiness,
        "receipt_get": {key: value for key, value in get_probe.items() if key not in {"body", "json"}},
        "receipt_head": {key: value for key, value in head_probe.items() if key not in {"body", "json"}},
        "production_get": None if production_get is None else {key: value for key, value in production_get.items() if key not in {"body", "json"}},
        "production_head": None if production_head is None else {key: value for key, value in production_head.items() if key not in {"body", "json"}},
        "public_receipt": payload,
        "missing": missing,
    }


def discover_once() -> dict[str, Any]:
    origins, discovery_probes = candidate_origins()
    attempts: list[dict[str, Any]] = []
    for origin in origins:
        urls, handoff_probes = receipt_candidates(origin)
        for url in urls:
            result = validate_receipt(url)
            attempts.append(
                {
                    "origin": origin,
                    "receipt_url": url,
                    "ok": result.get("ok"),
                    "missing": result.get("missing"),
                    "handoff_probes": handoff_probes,
                }
            )
            if result.get("ok"):
                return {
                    "schema": "szl.replit-deployment-receipt-discovery/v1",
                    "generated_at": now(),
                    "repl_id": REPL_ID,
                    "ok": True,
                    "receipt": result,
                    "origins_considered": origins,
                    "discovery_probes": discovery_probes,
                    "attempts": attempts,
                }
    return {
        "schema": "szl.replit-deployment-receipt-discovery/v1",
        "generated_at": now(),
        "repl_id": REPL_ID,
        "ok": False,
        "receipt": None,
        "origins_considered": origins,
        "discovery_probes": discovery_probes,
        "attempts": attempts,
    }


def paginate_issues(token: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for page in range(1, 11):
        payload = github_request(
            token,
            "GET",
            f"/repos/{CONTROL_REPOSITORY}/issues?state=all&sort=updated&direction=desc&per_page=100&page={page}",
        )
        if not isinstance(payload, list):
            raise DiscoveryError("issues payload is not a list")
        output.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return output
    raise DiscoveryError("issue pagination exceeded ten pages")


def upsert_issue(token: str, report: dict[str, Any]) -> dict[str, Any]:
    receipt = report.get("receipt") or {}
    body = (
        "<!-- szl-replit-deployment-receipt -->\n"
        "# Unified Control Hub deployment receipt\n\n"
        f"Receipt URL: {receipt.get('receipt_url') or 'not yet verified'}\n\n"
        "```json\n"
        + json.dumps(receipt.get("public_receipt") or report, indent=2, sort_keys=True)
        + "\n```\n"
    )
    current = next(
        (
            issue
            for issue in paginate_issues(token)
            if not issue.get("pull_request") and str(issue.get("title") or "") == ISSUE_TITLE
        ),
        None,
    )
    payload = {"body": body, "state": "closed" if report.get("ok") else "open"}
    if current:
        issue = github_request(
            token,
            "PATCH",
            f"/repos/{CONTROL_REPOSITORY}/issues/{current['number']}",
            payload,
        )
    else:
        issue = github_request(
            token,
            "POST",
            f"/repos/{CONTROL_REPOSITORY}/issues",
            {"title": ISSUE_TITLE, "body": body},
        )
        if report.get("ok"):
            issue = github_request(
                token,
                "PATCH",
                f"/repos/{CONTROL_REPOSITORY}/issues/{issue['number']}",
                {"state": "closed"},
            )
    return {"number": issue.get("number"), "url": issue.get("html_url"), "state": issue.get("state")}


def set_variable(token: str, value: str) -> dict[str, Any]:
    name = "REPLIT_DEPLOYMENT_RECEIPT_URL"
    encoded = urllib.parse.quote(name, safe="")
    current = github_request(
        token,
        "GET",
        f"/repos/{CONTROL_REPOSITORY}/actions/variables/{encoded}",
        allow_status={404},
    )
    payload = {"name": name, "value": value}
    if current is None:
        github_request(token, "POST", f"/repos/{CONTROL_REPOSITORY}/actions/variables", payload)
        action = "created"
    elif str(current.get("value") or "") != value:
        github_request(token, "PATCH", f"/repos/{CONTROL_REPOSITORY}/actions/variables/{encoded}", payload)
        action = "updated"
    else:
        action = "unchanged"
    return {"name": name, "action": action, "value": value}


def dispatch_final(token: str) -> None:
    encoded = urllib.parse.quote(FINAL_WORKFLOW, safe="")
    github_request(
        token,
        "POST",
        f"/repos/{CONTROL_REPOSITORY}/actions/workflows/{encoded}/dispatches",
        {"ref": "main"},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=60)
    parser.add_argument("--interval-seconds", type=int, default=300)
    args = parser.parse_args()
    token = os.environ.get("SZL_GITHUB_TOKEN", "").strip()
    report: dict[str, Any] = {
        "schema": "szl.replit-deployment-receipt-discovery/v1",
        "generated_at": now(),
        "repl_id": REPL_ID,
        "ok": False,
        "receipt": None,
        "attempt_history": [],
        "errors": [],
    }
    code = 1
    try:
        if not token:
            raise DiscoveryError("SZL_GITHUB_TOKEN is not configured")
        for attempt in range(1, args.attempts + 1):
            current = discover_once()
            report["attempt_history"].append(
                {
                    "attempt": attempt,
                    "generated_at": current.get("generated_at"),
                    "ok": current.get("ok"),
                    "origins_considered": current.get("origins_considered"),
                    "attempts": current.get("attempts"),
                }
            )
            if current.get("ok"):
                report.update(current)
                receipt = current["receipt"]
                report["repository_variable"] = set_variable(token, receipt["receipt_url"])
                report["durable_issue"] = upsert_issue(token, report)
                dispatch_final(token)
                report["final_reconciliation_dispatched"] = True
                code = 0
                break
            if attempt < args.attempts:
                time.sleep(args.interval_seconds)
        if not report.get("ok"):
            report["errors"].append("No complete public Replit deployment receipt was discovered in the allotted window")
            report["durable_issue"] = upsert_issue(token, report)
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"{type(exc).__name__}: {exc}")
        if token:
            try:
                report["durable_issue"] = upsert_issue(token, report)
            except Exception as issue_exc:  # noqa: BLE001
                report["errors"].append(f"issue persistence: {type(issue_exc).__name__}: {issue_exc}")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report.get("ok"), "receipt_url": (report.get("receipt") or {}).get("receipt_url")}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
