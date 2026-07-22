#!/usr/bin/env python3
"""Merge the clean green-light v2 PR using the repository's real required-check policy."""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API = "https://api.github.com"
REPOSITORY = "szl-holdings/.github"
HEAD_BRANCH = "ops/operational-greenlight-v2-main"
TITLE = "ops(greenlight): install scheduled evidence-driven estate control plane"
EXPECTED_PATHS = {
    ".github/scripts/operational_greenlight_v2.py",
    ".github/scripts/hf_estate_greenlight_final.py",
    ".github/scripts/discover_replit_receipt.py",
    ".github/scripts/hf_domain_receipt_publish.py",
    ".github/workflows/operational-greenlight-v2-main.yml",
    ".github/workflows/hf-estate-greenlight-final-main.yml",
    ".github/workflows/discover-replit-receipt-main.yml",
    ".github/workflows/hf-domain-receipt-publish-main.yml",
}
ALLOWED = {"success", "neutral", "skipped"}


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
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-merge-operational-greenlight-v2-policy/1.0",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        if allow_status and exc.code in allow_status:
            return None
        detail = exc.read().decode("utf-8", "replace")[:7000]
        raise GateError(f"GitHub API {method} {path} failed HTTP {exc.code}: {detail}") from exc
    return json.loads(raw.decode("utf-8")) if raw else None


def find_pr(token: str) -> dict[str, Any]:
    for page in range(1, 6):
        pulls = request(token, "GET", f"/repos/{REPOSITORY}/pulls?state=all&sort=updated&direction=desc&per_page=100&page={page}")
        if not isinstance(pulls, list):
            raise GateError("pull request list is malformed")
        exact = [
            pr for pr in pulls
            if str(pr.get("title") or "") == TITLE
            and str((pr.get("head") or {}).get("ref") or "") == HEAD_BRANCH
        ]
        if exact:
            exact.sort(key=lambda pr: str(pr.get("updated_at") or ""), reverse=True)
            return exact[0]
        if len(pulls) < 100:
            break
    raise GateError("clean operational-greenlight v2 pull request not found")


def get_pr(token: str, number: int) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for attempt in range(6):
        value = request(token, "GET", f"/repos/{REPOSITORY}/pulls/{number}")
        if value.get("mergeable") is not None or value.get("merged"):
            return value
        if attempt < 5:
            time.sleep(2)
    return value


def exact_files(token: str, number: int, changed: int) -> list[str]:
    rows = request(token, "GET", f"/repos/{REPOSITORY}/pulls/{number}/files?per_page=100")
    if not isinstance(rows, list) or len(rows) != changed:
        raise GateError(f"file audit incomplete: expected {changed}, got {len(rows) if isinstance(rows, list) else 'non-list'}")
    observed = {str(row.get("filename") or "") for row in rows}
    if observed != EXPECTED_PATHS:
        raise GateError(f"scope drift: missing={sorted(EXPECTED_PATHS-observed)}; extra={sorted(observed-EXPECTED_PATHS)}")
    return sorted(observed)


def review_state(token: str, number: int) -> dict[str, Any]:
    query = """
    query ExactReview($owner:String!,$name:String!,$number:Int!){
      repository(owner:$owner,name:$name){pullRequest(number:$number){
        headRefOid mergeable mergeStateStatus reviewDecision
        reviewThreads(first:100){nodes{isResolved} pageInfo{hasNextPage}}
        latestReviews(first:100){nodes{state author{login}} pageInfo{hasNextPage}}
      }}
    }
    """
    payload = request(token, "POST", "/graphql", {"query": query, "variables": {"owner": "szl-holdings", "name": ".github", "number": number}})
    if payload.get("errors"):
        raise GateError(f"GraphQL errors: {payload['errors']}")
    value = (((payload.get("data") or {}).get("repository") or {}).get("pullRequest"))
    if not value:
        raise GateError("GraphQL PR state missing")
    for key in ("reviewThreads", "latestReviews"):
        if ((value.get(key) or {}).get("pageInfo") or {}).get("hasNextPage"):
            raise GateError(f"more than 100 {key}")
    unresolved = sum(not bool(node.get("isResolved")) for node in ((value.get("reviewThreads") or {}).get("nodes") or []))
    requested = [
        (node.get("author") or {}).get("login") or "<unknown>"
        for node in ((value.get("latestReviews") or {}).get("nodes") or [])
        if node.get("state") == "CHANGES_REQUESTED"
    ]
    blockers=[]
    if unresolved: blockers.append(f"{unresolved} unresolved review thread(s)")
    if requested: blockers.append("active change requests from "+", ".join(requested))
    if value.get("reviewDecision")=="REVIEW_REQUIRED": blockers.append("independent approving review is required")
    return {**value,"blockers":blockers}


def required_contexts(token: str) -> dict[str, Any]:
    protection = request(token, "GET", f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks", allow_status={404})
    contexts: set[str] = set()
    strict = False
    if isinstance(protection, dict):
        strict = bool(protection.get("strict"))
        contexts.update(str(value) for value in protection.get("contexts") or [] if str(value))
        for check in protection.get("checks") or []:
            if isinstance(check, dict) and check.get("context"):
                contexts.add(str(check["context"]))
    # Rulesets may impose additional status checks. Only active branch-targeting rules are considered.
    rulesets = request(token, "GET", f"/repos/{REPOSITORY}/rulesets?includes_parents=true", allow_status={404})
    inspected_rulesets=[]
    if isinstance(rulesets, list):
        for summary in rulesets:
            if not isinstance(summary, dict) or summary.get("enforcement") != "active":
                continue
            ruleset_id=summary.get("id")
            if not ruleset_id:
                continue
            detail=request(token,"GET",f"/repos/{REPOSITORY}/rulesets/{ruleset_id}")
            inspected_rulesets.append({"id":ruleset_id,"name":detail.get("name"),"target":detail.get("target")})
            if detail.get("target") != "branch":
                continue
            for rule in detail.get("rules") or []:
                if not isinstance(rule,dict) or rule.get("type")!="required_status_checks":
                    continue
                parameters=rule.get("parameters") or {}
                strict = strict or bool(parameters.get("strict_required_status_checks_policy"))
                for check in parameters.get("required_status_checks") or []:
                    if isinstance(check,dict) and check.get("context"):
                        contexts.add(str(check["context"]))
    return {"contexts":sorted(contexts),"strict":strict,"rulesets":inspected_rulesets}


def observed_checks(token: str, sha: str) -> dict[str, Any]:
    payload=request(token,"GET",f"/repos/{REPOSITORY}/commits/{sha}/check-runs?filter=latest&per_page=100")
    if not isinstance(payload,dict) or not isinstance(payload.get("check_runs"),list):
        raise GateError("check-run payload malformed")
    observations:dict[str,dict[str,Any]]={}
    failures=[]; pending=[]
    for run in payload["check_runs"]:
        name=str(run.get("name") or "")
        if not name: continue
        status=str(run.get("status") or "").lower(); conclusion=str(run.get("conclusion") or "").lower()
        observations[name]={"type":"check_run","status":status,"conclusion":conclusion,"url":run.get("html_url") or run.get("details_url")}
        if status!="completed": pending.append(name)
        elif conclusion not in ALLOWED: failures.append(f"{name}: {conclusion or 'NONE'}")
    combined=request(token,"GET",f"/repos/{REPOSITORY}/commits/{sha}/status")
    latest={}
    for item in combined.get("statuses") or []:
        name=str(item.get("context") or "")
        if name and name not in latest: latest[name]=item
    for name,item in latest.items():
        state=str(item.get("state") or "").lower()
        observations[name]={"type":"status_context","state":state,"url":item.get("target_url")}
        if state=="pending": pending.append(name)
        elif state!="success": failures.append(f"{name}: {state or 'NONE'}")
    return {"observations":observations,"failures":sorted(set(failures)),"pending":sorted(set(pending))}


def checks_satisfy_policy(policy:dict[str,Any],observed:dict[str,Any])->dict[str,Any]:
    required=set(policy.get("contexts") or [])
    observations=observed.get("observations") or {}
    missing=sorted(required-set(observations))
    unsuccessful=[]
    for name in sorted(required & set(observations)):
        item=observations[name]
        if item.get("type")=="check_run":
            if item.get("status")!="completed" or item.get("conclusion") not in ALLOWED:
                unsuccessful.append(name)
        elif item.get("state")!="success":
            unsuccessful.append(name)
    # Any observed failure is a blocker, even when not formally required. Pending non-required checks
    # are recorded but do not override a policy that requires none.
    failures=list(observed.get("failures") or [])
    ok=not missing and not unsuccessful and not failures
    return {"ok":ok,"required":sorted(required),"missing":missing,"unsuccessful":unsuccessful,"observed_failures":failures,"observed_pending":observed.get("pending") or [],"observations":observations}


def run(token:str,timeout:int)->dict[str,Any]:
    seed=find_pr(token); number=int(seed["number"]); deadline=time.monotonic()+timeout; updated=None
    while True:
        pr=get_pr(token,number)
        if pr.get("merged"):
            return {"ok":True,"status":"already-merged","pull_request":number,"merge_sha":pr.get("merge_commit_sha")}
        if pr.get("state")!="open" or pr.get("draft"):
            raise GateError("PR is not an open non-draft")
        if str((pr.get("head") or {}).get("ref") or "")!=HEAD_BRANCH or str((((pr.get("head") or {}).get("repo") or {}).get("full_name")) or "")!=REPOSITORY:
            raise GateError("head identity changed")
        if str((pr.get("base") or {}).get("ref") or "")!="main": raise GateError("base changed")
        paths=exact_files(token,number,int(pr.get("changed_files") or 0)); sha=str((pr.get("head") or {}).get("sha") or "")
        reviews=review_state(token,number)
        if reviews.get("headRefOid")!=sha: raise GateError("REST/GraphQL head mismatch")
        if reviews["blockers"]: raise GateError("; ".join(reviews["blockers"]))
        policy=required_contexts(token); observed=observed_checks(token,sha); check_state=checks_satisfy_policy(policy,observed)
        if not check_state["ok"]:
            if check_state["observed_failures"] or check_state["unsuccessful"]:
                raise GateError(f"check policy failed: {check_state}")
        merge_state=str(pr.get("mergeable_state") or "").lower()
        if merge_state=="behind" and check_state["ok"]:
            if updated==sha: raise GateError("update-branch did not advance head")
            request(token,"PUT",f"/repos/{REPOSITORY}/pulls/{number}/update-branch",{"expected_head_sha":sha}); updated=sha; time.sleep(15); continue
        if check_state["ok"] and pr.get("mergeable") is True and reviews.get("mergeable")=="MERGEABLE" and merge_state in {"clean","has_hooks","unstable"} and reviews.get("mergeStateStatus") in {"CLEAN","HAS_HOOKS","UNSTABLE"}:
            final=get_pr(token,number)
            if str((final.get("head") or {}).get("sha") or "")!=sha: raise GateError("head moved during final preflight")
            result=request(token,"PUT",f"/repos/{REPOSITORY}/pulls/{number}/merge",{"sha":sha,"merge_method":"squash","commit_title":f"{TITLE} (#{number})","commit_message":"Install the clean scheduled evidence-driven estate control plane.\n\nSigned-off-by: Stephen Lutar <stephenlutar2@gmail.com>"})
            if not result.get("merged"): raise GateError(f"merge returned {result!r}")
            return {"ok":True,"status":"merged","pull_request":number,"head_sha":sha,"merge_sha":result.get("sha"),"files":paths,"required_check_policy":policy,"check_state":check_state}
        if pr.get("mergeable") is False or reviews.get("mergeable")=="CONFLICTING": raise GateError("merge conflict")
        if time.monotonic()>=deadline: raise GateError(f"timeout: mergeable_state={merge_state}; policy={policy}; checks={check_state}")
        time.sleep(20)


def main()->int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--report",type=Path,required=True); parser.add_argument("--timeout",type=int,default=10800); args=parser.parse_args(); token=os.environ.get("SZL_GITHUB_TOKEN","").strip(); code=0
    try:
        if not token: raise GateError("SZL_GITHUB_TOKEN is not configured")
        report={"schema":"szl.merge-operational-greenlight-v2-policy/v1","generated_at":now(),**run(token,args.timeout)}
    except Exception as exc:  # noqa: BLE001
        report={"schema":"szl.merge-operational-greenlight-v2-policy/v1","generated_at":now(),"ok":False,"errors":[f"{type(exc).__name__}: {exc}"]}; code=1
    args.report.parent.mkdir(parents=True,exist_ok=True); args.report.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps(report,indent=2,sort_keys=True)); return code


if __name__=="__main__": raise SystemExit(main())
