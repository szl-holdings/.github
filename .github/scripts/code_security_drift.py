#!/usr/bin/env python3
"""Managed-security-configuration drift checker for the szl-holdings org.

Task #307 created an org-level GitHub *code security configuration*
("SZL Holdings Managed Security", id 252588), attached it — enforced — to
every repo in the org, and set it as the default for new repos. Nothing
watched for drift afterwards: if someone detaches the config, swaps a repo
onto the old enterprise/global configuration, a new repo lands without it, or
the default-for-new-repos is changed, coverage could silently regress.

This script makes that drift catchable in CI / on a schedule. It:

  1. Confirms the canonical configuration still exists, is org-scoped, and is
     enforced.
  2. Confirms the org default-for-new-repos still points at it.
  3. Lists every repo in the org and cross-references it against the repos
     attached + enforced under the canonical configuration. Any NON-ARCHIVED
     repo that is not enforced under it — or that is attached to a different
     configuration (e.g. the legacy enterprise/global one) — is drift.

Archived repos are reported but never fail the check (Dependabot does not run
on archived repos; that difference is expected, not a regression). Intentional
exceptions can be allowlisted with a reason.

Auth: reads a token from $SZL_GITHUB_TOKEN / $GH_TOKEN / $GITHUB_TOKEN. The
code-security configuration endpoints require org-admin, so the built-in
GitHub Actions GITHUB_TOKEN is NOT sufficient — set the SZL_GITHUB_TOKEN PAT
secret. Two failure modes are kept DISTINCT so a missing secret never looks
like real drift and never looks like a pass:

  * NO token configured at all -> exit 3 (NEUTRAL "not configured, skipped").
    The check simply could not run; this is not a pass (coverage was NOT
    verified) and not drift. The CI workflow surfaces this as a neutral/skipped
    status, not a red failure.
  * A token IS present but the API call fails (401/403 insufficient scope,
    network, unexpected shape) -> exit 2 (ERROR). A configured-but-broken token
    is a real misconfiguration and fails loudly, never a silent pass.

Usage:
  python code_security_drift.py [--org szl-holdings] [--config-id 252588] \
      [--allowlist .github/data/code_security_allowlist.json] \
      [--report .github/data/code_security_report.json] \
      [--include-archived] [--json]

Exit code 0 = no drift (warnings allowed); 1 = drift detected; 2 = could not
complete the check (token present but auth/permission/API failure); 3 = no
token configured (neutral skip — check did not run, NOT a pass).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
CANONICAL_CONFIG_ID = 252588

# Exit-code contract (kept as named constants so the workflow and self-test
# stay in lockstep): 0 no drift, 1 drift, 2 token-present-but-check-failed,
# 3 no-token-configured (neutral skip — did not run, NOT a pass).
EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_ERROR = 2
EXIT_NO_TOKEN = 3
# Repo is genuinely covered when the enforced org config reports it "enforced".
OK_STATUSES = {"enforced"}
# Briefly-in-flight states: warn (re-check next run) rather than fail.
TRANSITIONAL_STATUSES = {"attached", "attaching", "updating", "enforcing"}


class CheckError(RuntimeError):
    """Raised when the check cannot be completed (auth/permission/API)."""


class MissingTokenError(CheckError):
    """Raised when NO token is configured at all.

    Distinct from a token that IS present but fails (401/403/network): a missing
    secret is an honest NEUTRAL skip (exit 3), never a red failure and never a
    pass. A present-but-broken token stays a loud error (exit 2).
    """


# --------------------------------------------------------------------------- #
# GitHub helpers

def _token() -> str:
    for name in ("SZL_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(name)
        if v:
            return v
    raise MissingTokenError(
        "No GitHub token configured. Set SZL_GITHUB_TOKEN (an org-admin PAT) — "
        "the built-in Actions GITHUB_TOKEN cannot read code-security "
        "configurations. Skipping (neutral): coverage was NOT verified."
    )


def _request(url: str, token: str):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-code-security-drift",
        },
    )
    return urllib.request.urlopen(req, timeout=60)


def gh_json(path: str, token: str):
    url = path if path.startswith("http") else f"{API}{path}"
    try:
        with _request(url, token) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        if e.code in (401, 403):
            raise CheckError(
                f"GitHub API {e.code} for {url}. The token likely lacks the "
                f"org-admin (admin:org) access required to read code-security "
                f"configurations. Set the SZL_GITHUB_TOKEN secret. "
                f"Detail: {body[:200]}"
            )
        raise CheckError(f"GitHub API {e.code} for {url}: {body[:300]}")
    except urllib.error.URLError as e:
        raise CheckError(f"Network error for {url}: {e}")


def gh_paginate(path: str, token: str):
    out = []
    page = 1
    sep = "&" if "?" in path else "?"
    while True:
        d = gh_json(f"{path}{sep}per_page=100&page={page}", token)
        if not isinstance(d, list) or not d:
            break
        out += d
        if len(d) < 100:
            break
        page += 1
    return out


# --------------------------------------------------------------------------- #
# Allowlist

def load_allowlist(path: str) -> dict:
    data: dict = {}
    if path and os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
    data.setdefault("repos", {})
    data.setdefault("default_for_new_repos_allowed", ["all"])
    return data


# --------------------------------------------------------------------------- #
# Core check

def run_check(args) -> dict:
    token = _token()
    org = args.org
    cfg_id = args.config_id
    allow = load_allowlist(args.allowlist)

    errors: list[str] = []
    warnings: list[str] = []

    # 1. Canonical configuration exists, org-scoped, enforced.
    configs = gh_json(f"/orgs/{org}/code-security/configurations", token)
    if not isinstance(configs, list):
        raise CheckError(f"Unexpected configurations response: {configs!r}")
    by_id = {c["id"]: c for c in configs}
    canonical = by_id.get(cfg_id)
    if canonical is None:
        errors.append(
            f"Canonical configuration id {cfg_id} not found in org {org} "
            f"(found ids: {sorted(by_id)}). It may have been deleted/renamed."
        )
    else:
        if canonical.get("target_type") != "organization":
            errors.append(
                f"Config {cfg_id} target_type is "
                f"{canonical.get('target_type')!r}, expected 'organization'."
            )
        if canonical.get("enforcement") != "enforced":
            errors.append(
                f"Config {cfg_id} enforcement is "
                f"{canonical.get('enforcement')!r}, expected 'enforced'."
            )

    # 2. Org default-for-new-repos still points at the canonical config.
    defaults = gh_json(f"/orgs/{org}/code-security/configurations/defaults", token)
    default_entry = None
    for d in defaults if isinstance(defaults, list) else []:
        if (d.get("configuration") or {}).get("id") == cfg_id:
            default_entry = d
            break
    default_scope = default_entry.get("default_for_new_repos") if default_entry else None
    allowed_scopes = set(allow["default_for_new_repos_allowed"])
    if default_entry is None:
        errors.append(
            f"Config {cfg_id} is no longer the default for new repos "
            f"(no defaults entry points at it). New repos may land uncovered."
        )
    elif default_scope not in allowed_scopes:
        errors.append(
            f"Default-for-new-repos scope for config {cfg_id} is "
            f"{default_scope!r}, expected one of {sorted(allowed_scopes)}."
        )

    # 3. Every org repo vs. repos enforced under the canonical config.
    repo_meta = {r["full_name"]: r for r in gh_paginate(f"/orgs/{org}/repos?type=all", token)}

    # Only query the canonical config's repositories if it still exists — a
    # deleted/renamed config already produced a headline error above; querying
    # its /repositories would 404 and mask drift behind an infra failure.
    attached: dict[str, str | None] = {}
    if canonical is not None:
        for x in gh_paginate(f"/orgs/{org}/code-security/configurations/{cfg_id}/repositories", token):
            attached[x["repository"]["full_name"]] = x.get("status")

    # Repos attached to a DIFFERENT configuration (legacy enterprise/global).
    elsewhere: dict[str, list] = {}
    for c in configs:
        if c["id"] == cfg_id:
            continue
        for x in gh_paginate(f"/orgs/{org}/code-security/configurations/{c['id']}/repositories", token):
            fn = x["repository"]["full_name"]
            if fn.startswith(org + "/"):
                elsewhere.setdefault(fn, []).append(
                    {"id": c["id"], "name": c.get("name"), "status": x.get("status")}
                )

    repo_report = []
    for fn in sorted(repo_meta):
        meta = repo_meta[fn]
        archived = bool(meta.get("archived"))
        status = attached.get(fn)
        other = elsewhere.get(fn)
        entry = {
            "repo": fn,
            "archived": archived,
            "private": bool(meta.get("private")),
            "status_under_canonical": status,
            "attached_elsewhere": other,
        }

        if fn in allow["repos"]:
            entry["result"] = "allowlisted"
            entry["reason"] = allow["repos"][fn]
            repo_report.append(entry)
            continue

        if archived and not args.include_archived:
            entry["result"] = "skipped_archived"
            repo_report.append(entry)
            continue

        problems = []
        if status in OK_STATUSES:
            pass
        elif status in TRANSITIONAL_STATUSES:
            warnings.append(
                f"{fn}: transitional status {status!r} under config {cfg_id} "
                f"(should settle to 'enforced'; re-check next run)."
            )
        else:
            problems.append(f"not enforced under config {cfg_id} (status={status!r})")

        if other:
            names = ", ".join(f"{o['id']} ({o['name']})" for o in other)
            problems.append(f"attached to other configuration(s): {names}")

        if problems:
            entry["result"] = "DRIFT"
            for p in problems:
                errors.append(f"{fn}: {p}")
        else:
            entry["result"] = "ok" if status in OK_STATUSES else "warn"
        repo_report.append(entry)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "org": org,
        "canonical_config": {
            "id": cfg_id,
            "name": canonical.get("name") if canonical else None,
            "target_type": canonical.get("target_type") if canonical else None,
            "enforcement": canonical.get("enforcement") if canonical else None,
        },
        "default_for_new_repos": default_scope,
        "totals": {
            "org_repos": len(repo_meta),
            "archived": sum(1 for r in repo_meta.values() if r.get("archived")),
            "enforced_under_canonical": sum(1 for s in attached.values() if s in OK_STATUSES),
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "errors": errors,
        "warnings": warnings,
        "repos": repo_report,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--org", default="szl-holdings")
    ap.add_argument("--config-id", type=int, default=CANONICAL_CONFIG_ID)
    ap.add_argument("--allowlist", default=".github/data/code_security_allowlist.json")
    ap.add_argument("--report", default=".github/data/code_security_report.json")
    ap.add_argument("--include-archived", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        report = run_check(args)
    except MissingTokenError as e:
        # No token configured: honest NEUTRAL skip. Not a pass (coverage was not
        # verified) and not drift. The workflow renders this as a skipped status.
        print(f"::notice::{e}", file=sys.stderr)
        return EXIT_NO_TOKEN
    except CheckError as e:
        # Token present but the check could not complete (auth/permission/API) —
        # fail loudly, never a silent pass.
        print(f"::error::{e}", file=sys.stderr)
        return EXIT_ERROR

    if args.report:
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w") as f:
            json.dump(report, f, indent=2)
            f.write("\n")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        cc = report["canonical_config"]
        t = report["totals"]
        print(f"Org: {report['org']}  Canonical config: {cc['id']} ({cc['name']})")
        print(
            f"  enforcement={cc['enforcement']} target={cc['target_type']} "
            f"default_for_new_repos={report['default_for_new_repos']}"
        )
        print(
            f"  org_repos={t['org_repos']} archived={t['archived']} "
            f"enforced_under_canonical={t['enforced_under_canonical']}"
        )
        for w in report["warnings"]:
            print(f"  ::warning:: {w}")
        for e in report["errors"]:
            print(f"  ::error:: {e}")
        print(f"  -> {len(report['errors'])} error(s), {len(report['warnings'])} warning(s)")

    return EXIT_DRIFT if report["errors"] else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
