#!/usr/bin/env python3
"""Required-status-check drift watcher for the lockfile-registry merge block.

Task #308 made the context

    lockfiles / No lockfile references a Replit-internal registry host

a REQUIRED status check on `main` for the six repos that actually commit
lockfiles, so a red lockfile run genuinely blocks merge. But that requirement
is just GitHub branch-protection config — anyone with admin can drop the
requirement, or a future ruleset rewrite can silently remove it, and nothing
would notice. The protection only matters if it stays in place.

This script makes that drift catchable on a schedule. For each wired repo it
gathers the EFFECTIVE set of required status-check contexts on the default
branch from BOTH mechanisms GitHub unions together:

  1. Branch RULESETS (the `series-a-default-branch` ruleset for a11oy +
     ouroboros): every ACTIVE branch ruleset whose conditions target the
     default branch and that carries a `required_status_checks` rule.
  2. CLASSIC branch protection (platform, vsp-otel, szl-uds-deployment,
     docs-site): `branches/<default>/protection/required_status_checks`.

If the required context is present via EITHER mechanism the repo is OK — that
keeps it robust to an intentional ruleset rename or a mechanism swap (moving
the requirement from classic to a ruleset still protects). If NO active
mechanism makes the context required on the default branch, that is drift and
the check fails. A `config["repos"][repo]["mechanism"]` hint is recorded in the
report for context but is NOT used to weaken the union check.

Auth: reads a token from $SZL_GITHUB_TOKEN / $GH_TOKEN / $GITHUB_TOKEN. The
rulesets and classic-protection endpoints require admin on each repo, so the
built-in Actions GITHUB_TOKEN is NOT sufficient — set the SZL_GITHUB_TOKEN PAT
secret. Any auth/permission/API failure is reported as an ERROR (exit 2) and
never as a silent pass, so a missing token can never produce a false green.

Usage:
  python required_check_drift.py \
      [--config   .github/data/required_check_config.json] \
      [--allowlist .github/data/required_check_allowlist.json] \
      [--report   .github/data/required_check_report.json] [--json]

Exit code 0 = every wired repo still requires the context (warnings allowed);
1 = drift (at least one repo no longer requires it); 2 = could not complete the
check (auth/permission/API failure).
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

# Rulesets that are not "active" do not actually enforce anything.
ACTIVE_ENFORCEMENT = "active"
# A ruleset condition targeting the default branch can be written either as the
# symbolic alias or the literal ref.
DEFAULT_BRANCH_TOKENS = {"~DEFAULT_BRANCH"}


class CheckError(RuntimeError):
    """Raised when the check cannot be completed (auth/permission/API)."""


# --------------------------------------------------------------------------- #
# GitHub helpers

def _token() -> str:
    for name in ("SZL_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(name)
        if v:
            return v
    raise CheckError(
        "No GitHub token found. Set SZL_GITHUB_TOKEN (an org-admin/repo-admin "
        "PAT) — the built-in Actions GITHUB_TOKEN cannot read rulesets or "
        "classic branch protection."
    )


def _request(url: str, token: str):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "szl-required-check-drift",
        },
    )
    return urllib.request.urlopen(req, timeout=60)


def gh_json(path: str, token: str, allow_404: bool = False):
    url = path if path.startswith("http") else f"{API}{path}"
    try:
        with _request(url, token) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        if e.code == 404 and allow_404:
            return None
        if e.code in (401, 403):
            raise CheckError(
                f"GitHub API {e.code} for {url}. The token likely lacks the "
                f"repo-admin access required to read rulesets / branch "
                f"protection. Set the SZL_GITHUB_TOKEN secret. "
                f"Detail: {body[:200]}"
            )
        raise CheckError(f"GitHub API {e.code} for {url}: {body[:300]}")
    except urllib.error.URLError as e:
        raise CheckError(f"Network error for {url}: {e}")


# --------------------------------------------------------------------------- #
# Config + allowlist

def load_json(path: str) -> dict:
    if path and os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def load_config(path: str) -> dict:
    cfg = load_json(path)
    if not cfg.get("required_context"):
        raise CheckError(
            f"Config {path!r} is missing 'required_context'. It must name the "
            f"exact status-check context string that has to stay required."
        )
    if not isinstance(cfg.get("repos"), dict) or not cfg["repos"]:
        raise CheckError(
            f"Config {path!r} is missing a non-empty 'repos' map of "
            f"repo-name -> {{mechanism: ruleset|classic}}."
        )
    cfg.setdefault("org", "szl-holdings")
    return cfg


def load_allowlist(path: str) -> dict:
    data = load_json(path)
    data.setdefault("ignore_repos", [])
    return data


# --------------------------------------------------------------------------- #
# Effective required contexts (per repo, both mechanisms)

def _condition_targets_default(conditions: dict) -> bool:
    include = ((conditions or {}).get("ref_name") or {}).get("include") or []
    return any(tok in DEFAULT_BRANCH_TOKENS for tok in include)


def ruleset_contexts(org: str, repo: str, token: str) -> tuple[set[str], list]:
    """Required-status-check contexts from ACTIVE default-branch rulesets."""
    contexts: set[str] = set()
    seen: list = []
    rulesets = gh_json(f"/repos/{org}/{repo}/rulesets", token, allow_404=True) or []
    for rs in rulesets:
        if rs.get("target") != "branch":
            continue
        full = gh_json(f"/repos/{org}/{repo}/rulesets/{rs['id']}", token)
        active = full.get("enforcement") == ACTIVE_ENFORCEMENT
        targets_default = _condition_targets_default(full.get("conditions"))
        rule_ctxs: set[str] = set()
        for rule in full.get("rules", []):
            if rule.get("type") != "required_status_checks":
                continue
            for c in (rule.get("parameters") or {}).get("required_status_checks", []):
                if c.get("context"):
                    rule_ctxs.add(c["context"])
        seen.append({
            "id": rs["id"],
            "name": rs.get("name"),
            "enforcement": full.get("enforcement"),
            "targets_default_branch": targets_default,
            "has_required_status_checks_rule": bool(rule_ctxs),
        })
        if active and targets_default:
            contexts |= rule_ctxs
    return contexts, seen


def classic_contexts(org: str, repo: str, default_branch: str, token: str) -> tuple[set[str], bool]:
    """Required-status-check contexts from classic branch protection."""
    rsc = gh_json(
        f"/repos/{org}/{repo}/branches/{default_branch}/protection/required_status_checks",
        token, allow_404=True,
    )
    if rsc is None:
        return set(), False
    ctxs = set(rsc.get("contexts") or [])
    for c in rsc.get("checks") or []:
        if c.get("context"):
            ctxs.add(c["context"])
    return ctxs, True


# --------------------------------------------------------------------------- #
# Core check

def run_check(args) -> dict:
    token = _token()
    cfg = load_config(args.config)
    allow = load_allowlist(args.allowlist)
    org = cfg["org"]
    required_context = cfg["required_context"]

    errors: list[str] = []
    warnings: list[str] = []
    repo_report = []

    for repo, spec in cfg["repos"].items():
        entry = {
            "repo": f"{org}/{repo}",
            "declared_mechanism": (spec or {}).get("mechanism"),
        }
        if repo in allow["ignore_repos"]:
            entry["result"] = "allowlisted"
            repo_report.append(entry)
            continue

        meta = gh_json(f"/repos/{org}/{repo}", token)
        default_branch = meta.get("default_branch", "main")
        entry["default_branch"] = default_branch

        rs_ctxs, rs_seen = ruleset_contexts(org, repo, token)
        cl_ctxs, classic_present = classic_contexts(org, repo, default_branch, token)

        entry["rulesets"] = rs_seen
        entry["classic_protection_present"] = classic_present
        entry["required_via_ruleset"] = required_context in rs_ctxs
        entry["required_via_classic"] = required_context in cl_ctxs

        if entry["required_via_ruleset"] or entry["required_via_classic"]:
            entry["result"] = "ok"
        else:
            entry["result"] = "DRIFT"
            errors.append(
                f"{org}/{repo}: the context {required_context!r} is NO LONGER a "
                f"required status check on '{default_branch}' via any active "
                f"ruleset or classic branch protection. A poisoned lockfile can "
                f"now be merged. Re-add it (see required_check_config.json hint: "
                f"mechanism={entry['declared_mechanism']!r})."
            )
        repo_report.append(entry)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "org": org,
        "required_context": required_context,
        "totals": {
            "wired_repos": len(cfg["repos"]),
            "ok": sum(1 for e in repo_report if e["result"] == "ok"),
            "drift": sum(1 for e in repo_report if e["result"] == "DRIFT"),
            "allowlisted": sum(1 for e in repo_report if e["result"] == "allowlisted"),
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "errors": errors,
        "warnings": warnings,
        "repos": repo_report,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=".github/data/required_check_config.json")
    ap.add_argument("--allowlist", default=".github/data/required_check_allowlist.json")
    ap.add_argument("--report", default=".github/data/required_check_report.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        report = run_check(args)
    except CheckError as e:
        print(f"::error::{e}", file=sys.stderr)
        return 2

    if args.report:
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w") as f:
            json.dump(report, f, indent=2)
            f.write("\n")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        t = report["totals"]
        print(f"Org: {report['org']}  Required context: {report['required_context']!r}")
        print(
            f"  wired_repos={t['wired_repos']} ok={t['ok']} drift={t['drift']} "
            f"allowlisted={t['allowlisted']}"
        )
        for e in report["repos"]:
            print(
                f"  - {e['repo']}: {e['result']} "
                f"(ruleset={e.get('required_via_ruleset')}, "
                f"classic={e.get('required_via_classic')})"
            )
        for w in report["warnings"]:
            print(f"  ::warning:: {w}")
        for e in report["errors"]:
            print(f"  ::error:: {e}")
        print(f"  -> {len(report['errors'])} error(s), {len(report['warnings'])} warning(s)")

    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
