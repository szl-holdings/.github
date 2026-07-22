#!/usr/bin/env python3
"""Probe the public Unified Control Hub status and persist the exact blocker or receipt."""
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
CONTROL_REPOSITORY = "szl-holdings/.github"
A11OY_REPOSITORY = "szl-holdings/a11oy"
ISSUE_TITLE = "[replit-deployment-receipt] Unified Control Hub"
REPL_ID = "34870515-2d52-4ad8-9636-40cc3ced1771"
REPL_PAGE = "https://replit.com/@stephenlutar2/Unified-Control-Hub"
URL_RE = re.compile(r"https://[A-Za-z0-9][A-Za-z0-9.-]*\.(?:replit\.app|repl\.co)(?::\d+)?", re.I)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
USER_AGENT = "szl-replit-status-probe/1.0"
MAX_BODY = 2 * 1024 * 1024


class ProbeError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def immutable_sha(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if SHA_RE.fullmatch(text) else None


def public_get(url: str, method: str = "GET") -> dict[str, Any]:
    request = urllib.request.Request(
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
        with urllib.request.urlopen(request, timeout=60, context=ssl.create_default_context()) as response:
            body = b"" if method == "HEAD" else response.read(MAX_BODY)
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
                "url": response.geturl(),
                "method": method,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "content_type": content_type,
                "body": body.decode("utf-8", "replace") if body else "",
                "json": payload,
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": int(exc.code), "url": url, "method": method, "elapsed_ms": round((time.monotonic()-started)*1000,3), "content_type": str(exc.headers.get("Content-Type") or ""), "body": exc.read(8192).decode("utf-8", "replace"), "json": None, "error": f"HTTPError: {exc.code}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": 0, "url": url, "method": method, "elapsed_ms": round((time.monotonic()-started)*1000,3), "content_type": "", "body": "", "json": None, "error": f"{type(exc).__name__}: {exc}"}


def clean(probe: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in probe.items() if key not in {"body", "json"}}


def candidates() -> list[str]:
    values = {
        "https://unified-control-hub-stephenlutar2.replit.app",
        "https://unified-control-hub--stephenlutar2.repl.co",
        "https://unified-control-hub-stephenlutar2.repl.co",
        "https://unified-control-hub.stephenlutar2.repl.co",
    }
    for url in (REPL_PAGE, f"https://replit.com/data/repls/{REPL_ID}", f"https://replit.com/api/v1/repls/{REPL_ID}"):
        probe = public_get(url)
        texts = [str(probe.get("body") or "")]
        if isinstance(probe.get("json"), (dict, list)):
            texts.append(json.dumps(probe["json"]))
        for text in texts:
            values.update(match.rstrip("/") for match in URL_RE.findall(text))
    return sorted(values)


def validate_receipt(url: str) -> dict[str, Any]:
    get_probe = public_get(url, "GET")
    head_probe = public_get(url, "HEAD")
    payload = get_probe.get("json") if isinstance(get_probe.get("json"), dict) else {}
    source = immutable_sha(payload.get("source_revision") or payload.get("source_sha") or payload.get("commit_sha"))
    deployment = immutable_sha(payload.get("deployment_revision") or payload.get("deployment_sha") or payload.get("deployed_revision"))
    production_url = str(payload.get("production_url") or payload.get("url") or "").strip() or None
    tests = payload.get("tests") or payload.get("test_results")
    mobile = payload.get("mobile") or payload.get("mobile_probes")
    readiness = payload.get("readiness") or payload.get("readiness_probes")
    production_get = public_get(production_url, "GET") if production_url else None
    production_head = public_get(production_url, "HEAD") if production_url else None
    missing = []
    if not get_probe.get("ok"): missing.append("receipt GET")
    if not head_probe.get("ok"): missing.append("receipt HEAD")
    if not source: missing.append("source_revision")
    if not deployment: missing.append("deployment_revision")
    if not production_url: missing.append("production_url")
    if not tests: missing.append("tests")
    if not mobile: missing.append("mobile")
    if not readiness: missing.append("readiness")
    if production_get and not production_get.get("ok"): missing.append("production GET")
    if production_head and not production_head.get("ok"): missing.append("production HEAD")
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
        "receipt_get": clean(get_probe),
        "receipt_head": clean(head_probe),
        "production_get": None if production_get is None else clean(production_get),
        "production_head": None if production_head is None else clean(production_head),
        "public_receipt": payload,
        "missing": missing,
    }


def probe() -> dict[str, Any]:
    attempts = []
    best_status: dict[str, Any] | None = None
    for origin in candidates():
        status_probe = public_get(origin + "/CURRENT_DEPLOYMENT_STATUS.json")
        status = status_probe.get("json") if isinstance(status_probe.get("json"), dict) else None
        if status:
            best_status = {
                "origin": origin,
                "status_url": origin + "/CURRENT_DEPLOYMENT_STATUS.json",
                "probe": clean(status_probe),
                "public_status": status,
            }
            receipt_url = str(status.get("receipt_url") or "").strip()
            if receipt_url.startswith("https://"):
                receipt = validate_receipt(receipt_url)
                attempts.append({"origin": origin, "receipt_url": receipt_url, "ok": receipt["ok"], "missing": receipt["missing"]})
                if receipt["ok"]:
                    return {"schema": "szl.replit-public-status/v1", "generated_at": now(), "repl_id": REPL_ID, "ok": True, "status": best_status, "receipt": receipt, "attempts": attempts}
        handoff = public_get(origin + "/REPLIT_DEPLOYMENT_RECEIPT_URL.txt")
        urls = []
        if handoff.get("ok"):
            urls.extend(line.strip() for line in str(handoff.get("body") or "").splitlines() if line.strip().startswith("https://"))
        urls.append(origin + "/api/szl/deployment-receipt")
        for receipt_url in dict.fromkeys(urls):
            receipt = validate_receipt(receipt_url)
            attempts.append({"origin": origin, "receipt_url": receipt_url, "ok": receipt["ok"], "missing": receipt["missing"]})
            if receipt["ok"]:
                return {"schema": "szl.replit-public-status/v1", "generated_at": now(), "repl_id": REPL_ID, "ok": True, "status": best_status, "receipt": receipt, "attempts": attempts}
    return {"schema": "szl.replit-public-status/v1", "generated_at": now(), "repl_id": REPL_ID, "ok": False, "status": best_status, "receipt": None, "attempts": attempts, "current_blocker": ((best_status or {}).get("public_status") or {}).get("current_blocker") or "No complete public status or deployment receipt was discovered"}


def github_request(token: str, method: str, path: str, payload: dict[str, Any] | None = None, allow_404: bool = False) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(GITHUB_API + path, data=body, method=method, headers={"Accept":"application/vnd.github+json","Authorization":f"Bearer {token}","X-GitHub-Api-Version":"2022-11-28","User-Agent":USER_AGENT, **({"Content-Type":"application/json"} if body is not None else {})})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if allow_404 and exc.code == 404: return None
        raise
    return json.loads(raw.decode("utf-8")) if raw else None


def issues(token: str) -> list[dict[str, Any]]:
    output=[]
    for page in range(1,11):
        rows=github_request(token,"GET",f"/repos/{CONTROL_REPOSITORY}/issues?state=all&sort=updated&direction=desc&per_page=100&page={page}")
        output.extend(row for row in rows if isinstance(row,dict))
        if len(rows)<100: return output
    return output


def set_variable(token: str, repository: str, value: str) -> dict[str, Any]:
    name="REPLIT_DEPLOYMENT_RECEIPT_URL"; encoded=urllib.parse.quote(name,safe="")
    current=github_request(token,"GET",f"/repos/{repository}/actions/variables/{encoded}",allow_404=True)
    payload={"name":name,"value":value}
    if current is None:
        github_request(token,"POST",f"/repos/{repository}/actions/variables",payload); action="created"
    elif str(current.get("value") or "")!=value:
        github_request(token,"PATCH",f"/repos/{repository}/actions/variables/{encoded}",payload); action="updated"
    else: action="unchanged"
    return {"repository":repository,"action":action,"value":value}


def persist(token: str, report: dict[str, Any]) -> dict[str, Any]:
    showcase=""
    if report.get("ok"):
        receipt=report["receipt"]
        showcase=f"Receipt URL: {receipt['receipt_url']}\n\nProduction URL: {receipt['production_url']}\n\n"
        report["repository_variables"]=[set_variable(token,CONTROL_REPOSITORY,receipt["receipt_url"]),set_variable(token,A11OY_REPOSITORY,receipt["receipt_url"])]
    elif report.get("status"):
        status=report["status"]["public_status"]
        showcase=f"State: `{status.get('state')}`\n\nCurrent blocker: {status.get('current_blocker')}\n\nStatus URL: {report['status']['status_url']}\n\n"
    else:
        showcase=f"Current blocker: {report.get('current_blocker')}\n\n"
    body="<!-- szl-replit-public-status -->\n# Unified Control Hub deployment receipt\n\n"+showcase+"```json\n"+json.dumps(report.get("receipt",{}).get("public_receipt") if report.get("ok") else report,indent=2,sort_keys=True)+"\n```\n"
    current=next((issue for issue in issues(token) if not issue.get("pull_request") and str(issue.get("title") or "")==ISSUE_TITLE),None)
    if current:
        issue=github_request(token,"PATCH",f"/repos/{CONTROL_REPOSITORY}/issues/{current['number']}",{"body":body,"state":"closed" if report.get("ok") else "open"})
    else:
        issue=github_request(token,"POST",f"/repos/{CONTROL_REPOSITORY}/issues",{"title":ISSUE_TITLE,"body":body})
        if report.get("ok"): issue=github_request(token,"PATCH",f"/repos/{CONTROL_REPOSITORY}/issues/{issue['number']}",{"state":"closed"})
    return {"number":issue.get("number"),"url":issue.get("html_url"),"state":issue.get("state")}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--report",type=Path,required=True); args=parser.parse_args()
    token=os.environ.get("SZL_GITHUB_TOKEN","").strip(); code=0
    try:
        if not token: raise ProbeError("SZL_GITHUB_TOKEN is not configured")
        report=probe(); report["durable_issue"]=persist(token,report)
        if not report.get("ok"): code=1
    except Exception as exc:  # noqa: BLE001
        report={"schema":"szl.replit-public-status/v1","generated_at":now(),"repl_id":REPL_ID,"ok":False,"errors":[f"{type(exc).__name__}: {exc}"]}; code=1
    args.report.parent.mkdir(parents=True,exist_ok=True); args.report.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps({"ok":report.get("ok"),"blocker":report.get("current_blocker")},indent=2)); return code


if __name__=="__main__": raise SystemExit(main())
