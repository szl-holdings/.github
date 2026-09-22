#!/usr/bin/env python3
"""Governed GitHub organization security scorecard.

Measures organization, repository, branch-protection and Actions supply-chain
controls for a public GitHub org and emits a fail-closed scorecard.

Doctrine labels are mandatory on every finding:
  MEASURED     - the control was read directly from the GitHub API this run.
  REPORTED     - the value came from policy/config in-repo, not from the API.
  UNKNOWN      - the control was not probed this run.
  UNAVAILABLE  - probe attempted but the credential/plan cannot see it.

Only MEASURED failures can turn the run red, so a missing admin:org scope
degrades to UNAVAILABLE instead of manufacturing a green board.

stdlib only. No third-party imports.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
UA = "szl-governance-scorecard/1.0"
SHA_PIN = re.compile(r"^[0-9a-f]{40}$")
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*['\"]?([^'\"\s#]+)", re.MULTILINE)
LOCAL_USE = re.compile(r"^\./|^docker://")

MEASURED, REPORTED, UNKNOWN, UNAVAILABLE = "MEASURED", "REPORTED", "UNKNOWN", "UNAVAILABLE"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Api:
    def __init__(self, token: str) -> None:
        self.token = token
        self.calls = 0

    def get(self, path: str, params: dict | None = None):
        url = path if path.startswith("http") else API + path
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": UA,
            "Authorization": f"Bearer {self.token}",
        })
        for attempt in range(3):
            try:
                self.calls += 1
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8") or "null"), resp.status
            except urllib.error.HTTPError as exc:
                if exc.code in (403, 429) and attempt < 2:
                    time.sleep(5 * (attempt + 1))
                    continue
                return None, exc.code
            except urllib.error.URLError:
                if attempt < 2:
                    time.sleep(3)
                    continue
                return None, 0
        return None, 0

    def paged(self, path: str, per_page: int = 100, cap: int = 500):
        out, page = [], 1
        while len(out) < cap:
            body, status = self.get(path, {"per_page": per_page, "page": page})
            if status != 200 or not body:
                break
            out.extend(body)
            if len(body) < per_page:
                break
            page += 1
        return out


class Board:
    def __init__(self) -> None:
        self.findings: list[dict] = []

    def add(self, check: str, area: str, ok, label: str, detail: str, weight: int = 1,
            remediation: str = "") -> None:
        if label in (UNKNOWN, UNAVAILABLE):
            state = label
        else:
            state = "PASS" if ok else "FAIL"
        self.findings.append({
            "check": check, "area": area, "state": state, "label": label,
            "detail": detail, "weight": weight, "remediation": remediation,
        })

    def drift(self) -> list[dict]:
        return [f for f in self.findings if f["state"] == "FAIL" and f["label"] == MEASURED]

    def unresolved(self) -> list[dict]:
        return [f for f in self.findings if f["label"] in (UNKNOWN, UNAVAILABLE)]

    def score(self) -> dict:
        scored = [f for f in self.findings if f["label"] in (MEASURED, REPORTED)]
        earned = sum(f["weight"] for f in scored if f["state"] == "PASS")
        total = sum(f["weight"] for f in scored)
        return {
            "earned": earned,
            "possible": total,
            "percent": round(100.0 * earned / total, 1) if total else 0.0,
            "measured_checks": len(scored),
            "unresolved_checks": len(self.unresolved()),
        }


def audit_org(api: Api, org: str, board: Board) -> None:
    body, status = api.get(f"/orgs/{org}")
    if status != 200 or not isinstance(body, dict):
        board.add("org.profile", "identity", None, UNAVAILABLE,
                  f"GET /orgs/{org} returned HTTP {status}", 3,
                  "Grant the workflow credential read:org / admin:org.")
        return

    def flag(key, check, weight, want=True, remediation=""):
        if key not in body or body.get(key) is None:
            board.add(check, "identity", None, UNAVAILABLE,
                      f"{key} absent from org payload (scope or plan)", weight, remediation)
        else:
            val = body[key]
            board.add(check, "identity", val is want, MEASURED, f"{key}={val}", weight, remediation)

    flag("two_factor_requirement_enabled", "org.2fa_required", 3, True,
         "Settings > Authentication security > Require two-factor authentication.")
    flag("members_can_create_public_repositories", "org.public_repo_creation_restricted", 2, False,
         "Restrict public repository creation to owners.")
    flag("web_commit_signoff_required", "org.web_commit_signoff", 1, True,
         "Enable web commit signoff org-wide.")
    flag("secret_scanning_push_protection_enabled_for_new_repositories",
         "org.push_protection_default", 3, True,
         "Enable secret scanning push protection for new repositories.")
    flag("advanced_security_enabled_for_new_repositories", "org.ghas_default", 1, True,
         "Enable GitHub Advanced Security defaults where licensed.")

    perm = body.get("default_repository_permission")
    if perm is None:
        board.add("org.base_permission_none", "identity", None, UNAVAILABLE,
                  "default_repository_permission not visible", 3,
                  "Requires admin:org to read; set base permission to 'none'.")
    else:
        board.add("org.base_permission_none", "identity", perm == "none", MEASURED,
                  f"default_repository_permission={perm}", 3,
                  "Set base permissions to 'No permission'; grant access via teams.")

    aperm, status = api.get(f"/orgs/{org}/actions/permissions")
    if status != 200 or not isinstance(aperm, dict):
        board.add("actions.allowed_actions_policy", "actions", None, UNAVAILABLE,
                  f"GET /orgs/{org}/actions/permissions returned HTTP {status}", 2,
                  "Needs admin:org; set allowed actions to selected/local+verified.")
    else:
        allowed = aperm.get("allowed_actions")
        board.add("actions.allowed_actions_policy", "actions", allowed in ("selected", "local_only"),
                  MEASURED, f"allowed_actions={allowed}", 2,
                  "Restrict to selected actions rather than 'all'.")

    wperm, status = api.get(f"/orgs/{org}/actions/permissions/workflow")
    if status != 200 or not isinstance(wperm, dict):
        board.add("actions.default_token_readonly", "actions", None, UNAVAILABLE,
                  f"GET workflow permissions returned HTTP {status}", 3,
                  "Needs admin:org; set default GITHUB_TOKEN to read-only.")
    else:
        default = wperm.get("default_workflow_permissions")
        approve = wperm.get("can_approve_pull_request_reviews")
        board.add("actions.default_token_readonly", "actions", default == "read", MEASURED,
                  f"default_workflow_permissions={default}", 3,
                  "Set default GITHUB_TOKEN permissions to read-only.")
        board.add("actions.token_cannot_approve_prs", "actions", approve is False, MEASURED,
                  f"can_approve_pull_request_reviews={approve}", 1,
                  "Disallow GITHUB_TOKEN approving pull requests.")


def audit_repos(api: Api, org: str, board: Board, repo_cap: int, pin_cap: int) -> dict:
    repos = api.paged(f"/orgs/{org}/repos", cap=repo_cap)
    if not repos:
        board.add("repo.inventory", "repos", None, UNAVAILABLE,
                  "repository listing returned no rows", 3, "Check credential repo scope.")
        return {"repos": 0}

    live = [r for r in repos if not r.get("archived")]
    public = [r for r in live if not r.get("private")]

    no_license = [r["name"] for r in public if not r.get("license")]
    board.add("repo.public_license_present", "repos", not no_license, MEASURED,
              f"{len(public) - len(no_license)}/{len(public)} public repos carry a license"
              + (f"; missing: {', '.join(sorted(no_license)[:12])}" if no_license else ""),
              2, "Add a LICENSE file to every public repository.")

    no_desc = [r["name"] for r in public if not (r.get("description") or "").strip()]
    board.add("repo.public_description_present", "repos", not no_desc, MEASURED,
              f"{len(no_desc)} public repos have no description"
              + (f": {', '.join(sorted(no_desc)[:12])}" if no_desc else ""),
              1, "Describe every public repo; empty repos read as abandoned.")

    forky = [r["name"] for r in live if r.get("allow_forking") is False]
    board.add("repo.forking_policy_recorded", "repos", True, REPORTED,
              f"{len(live)} active repos; {len(forky)} with forking disabled", 1,
              "Forking posture is a deliberate choice, recorded not enforced.")

    ordered = sorted(live, key=lambda r: r.get("pushed_at") or "", reverse=True)
    prot_sample = ordered[:min(len(ordered), pin_cap)]

    unsigned, weak_checks, forcepush, unreadable = [], [], [], []
    for r in prot_sample:
        branch = r.get("default_branch") or "main"
        prot, status = api.get(f"/repos/{org}/{r['name']}/branches/{branch}/protection")
        if status == 404:
            rules, rstatus = api.get(f"/repos/{org}/{r['name']}/rulesets")
            if rstatus == 200 and rules:
                continue
            weak_checks.append(f"{r['name']}#{branch}")
            continue
        if status != 200 or not isinstance(prot, dict):
            unreadable.append(f"{r['name']} (HTTP {status})")
            continue
        if not (prot.get("required_signatures") or {}).get("enabled"):
            unsigned.append(r["name"])
        rsc = prot.get("required_status_checks") or {}
        if not rsc.get("contexts") and not rsc.get("checks"):
            weak_checks.append(f"{r['name']}#{branch}")
        if (prot.get("allow_force_pushes") or {}).get("enabled"):
            forcepush.append(r["name"])

    board.add("branch.signed_commits_required", "branch", not unsigned, MEASURED,
              f"{len(unsigned)} sampled repos lack required signatures"
              + (f": {', '.join(unsigned[:12])}" if unsigned else ""),
              3, "Require signed commits on the default branch.")
    board.add("branch.required_checks_present", "branch", not weak_checks, MEASURED,
              f"{len(weak_checks)} sampled default branches have no required checks or ruleset"
              + (f": {', '.join(weak_checks[:12])}" if weak_checks else ""),
              3, "Require at least one green CI check before merge.")
    board.add("branch.force_push_blocked", "branch", not forcepush, MEASURED,
              f"{len(forcepush)} sampled repos allow force pushes to the default branch"
              + (f": {', '.join(forcepush[:12])}" if forcepush else ""),
              3, "Block force pushes and default-branch deletion.")
    if unreadable:
        board.add("branch.protection_readable", "branch", None, UNAVAILABLE,
                  f"protection unreadable on {len(unreadable)} repos: {', '.join(unreadable[:10])}",
                  1, "Credential needs repo admin to read protection.")

    unpinned, scanned_files, scanned_repos = [], 0, 0
    for r in prot_sample:
        listing, status = api.get(f"/repos/{org}/{r['name']}/contents/.github/workflows")
        if status != 200 or not isinstance(listing, list):
            continue
        scanned_repos += 1
        for entry in listing:
            if entry.get("type") != "file" or not entry["name"].endswith((".yml", ".yaml")):
                continue
            blob, bstatus = api.get(entry["url"])
            if bstatus != 200 or not isinstance(blob, dict):
                continue
            try:
                text = base64.b64decode(blob.get("content") or "").decode("utf-8", "replace")
            except Exception:
                continue
            scanned_files += 1
            for ref in USES.findall(text):
                if LOCAL_USE.match(ref):
                    continue
                pin = ref.rsplit("@", 1)[-1] if "@" in ref else ""
                if not SHA_PIN.match(pin):
                    unpinned.append(f"{r['name']}/{entry['name']}: {ref}")

    if scanned_repos == 0:
        board.add("actions.sha_pinned_uses", "actions", None, UNAVAILABLE,
                  "no workflow directories were readable", 4,
                  "Credential cannot read workflow files.")
    else:
        board.add("actions.sha_pinned_uses", "actions", not unpinned, MEASURED,
                  f"{len(unpinned)} unpinned uses: refs across {scanned_files} workflow files in "
                  f"{scanned_repos} repos"
                  + (f"; first: {'; '.join(unpinned[:15])}" if unpinned else ""),
                  4, "Pin every third-party action to a full 40-character commit SHA.")

    return {
        "repos_total": len(repos), "repos_active": len(live), "repos_public": len(public),
        "sampled": len(prot_sample), "workflow_files_scanned": scanned_files,
        "unpinned_refs": unpinned[:200],
    }


def render(board: Board, org: str, stats: dict, hf_report: dict | None) -> str:
    score = board.score()
    lines = [
        f"# SZL estate governance scorecard",
        "",
        f"- generated_at: `{utc_now()}`",
        f"- github_org: `{org}`",
        f"- score: **{score['earned']}/{score['possible']} ({score['percent']}%)** "
        f"across {score['measured_checks']} scored checks",
        f"- unresolved (UNKNOWN/UNAVAILABLE): **{score['unresolved_checks']}**",
        f"- measured drift: **{len(board.drift())}**",
        "",
        "## Findings",
        "",
        "| check | area | state | label | detail |",
        "| --- | --- | --- | --- | --- |",
    ]
    for f in board.findings:
        detail = f["detail"].replace("|", "\\|")[:300]
        lines.append(f"| `{f['check']}` | {f['area']} | {f['state']} | {f['label']} | {detail} |")

    lines += ["", "## Inventory", ""]
    for k, v in stats.items():
        if k == "unpinned_refs":
            continue
        lines.append(f"- {k}: {v}")

    if hf_report:
        s = hf_report.get("summary", {})
        lines += ["", "## Hugging Face estate", ""]
        for k in sorted(s):
            lines.append(f"- {k}: {s[k]}")

    drift = board.drift()
    if drift:
        lines += ["", "## Measured drift (fail-closed)", ""]
        for f in drift:
            lines.append(f"- `{f['check']}` \u2014 {f['detail']}")
            if f["remediation"]:
                lines.append(f"  remediation: {f['remediation']}")
    unresolved = board.unresolved()
    if unresolved:
        lines += ["", "## Unresolved controls (not scored, not green)", ""]
        for f in unresolved:
            lines.append(f"- `{f['check']}` [{f['label']}] \u2014 {f['detail']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", default=os.environ.get("GH_ORG", "szl-holdings"))
    ap.add_argument("--out-json", default="reports/governance/github-scorecard.json")
    ap.add_argument("--out-md", default="reports/governance/scorecard.md")
    ap.add_argument("--hf-report", default="reports/governance/hf-spaces.json")
    ap.add_argument("--repo-cap", type=int, default=300)
    ap.add_argument("--deep-sample", type=int, default=40)
    ap.add_argument("--strict-unknown", action="store_true",
                    help="treat UNKNOWN/UNAVAILABLE controls as drift")
    ap.add_argument("--dry-run", action="store_true", help="never exit non-zero")
    args = ap.parse_args()

    token = (os.environ.get("SCORECARD_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        print("FATAL: no token in SCORECARD_TOKEN or GITHUB_TOKEN", file=sys.stderr)
        return 2

    api = Api(token)
    board = Board()
    audit_org(api, args.org, board)
    stats = audit_repos(api, args.org, board, args.repo_cap, args.deep_sample)

    hf_report = None
    if os.path.exists(args.hf_report):
        try:
            with open(args.hf_report, encoding="utf-8") as fh:
                hf_report = json.load(fh)
        except Exception:
            hf_report = None
        if hf_report:
            s = hf_report.get("summary", {})
            board.add("hf.public_spaces_running", "huggingface",
                      s.get("public_not_running", 0) == 0, MEASURED,
                      f"{s.get('public_not_running', 0)} public Spaces not RUNNING", 3,
                      "Restart or repair non-running public Spaces.")
            board.add("hf.governance_stamp_present", "huggingface",
                      s.get("missing_stamp", 0) == 0, MEASURED,
                      f"{s.get('missing_stamp', 0)} assets missing a governance stamp backlink", 2,
                      "Stamp every asset with a literal model-ID backlink.")
            board.add("hf.license_declared", "huggingface",
                      s.get("missing_license", 0) == 0, MEASURED,
                      f"{s.get('missing_license', 0)} assets without a declared license", 2,
                      "Declare a license in card metadata.")
    else:
        board.add("hf.public_spaces_running", "huggingface", None, UNKNOWN,
                  "HF probe report absent this run", 3, "Run hf_space_prober.py first.")

    score = board.score()
    payload = {
        "schema": "szl.governance.scorecard/v1",
        "generated_at": utc_now(),
        "github_org": args.org,
        "api_calls": api.calls,
        "score": score,
        "inventory": stats,
        "findings": board.findings,
        "drift": board.drift(),
        "unresolved": board.unresolved(),
        "receipt_state": "UNSIGNED_HONEST",
    }
    for path, blob in ((args.out_json, json.dumps(payload, indent=2, sort_keys=True) + "\n"),
                       (args.out_md, render(board, args.org, stats, hf_report))):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(blob)

    print(f"score {score['earned']}/{score['possible']} ({score['percent']}%) "
          f"drift={len(board.drift())} unresolved={len(board.unresolved())}")
    if args.dry_run:
        return 0
    if board.drift():
        return 1
    if args.strict_unknown and board.unresolved():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
