#!/usr/bin/env python3
"""Required-status-check drift watcher for security-load-bearing merge blocks.

Some status-check contexts are made REQUIRED on `main` so that a red run
genuinely BLOCKS merge. Two such merge blocks are watched here:

  1. lockfile-registry (Task #308): the context
        lockfiles / No lockfile references a Replit-internal registry host
     on the six repos that actually commit lockfiles, so a poisoned
     (`*.replit.local`) lockfile cannot be merged.
  2. overclaim-honesty (Task #393): the context
        overclaim / Governed surfaces are honest (Theorem U citation rule)
     on lutar-lean + szl-papers, so a doc that overclaims Λ-uniqueness or
     "Conjecture 1 proven" cannot be merged past the honesty guard.

But "required" is just GitHub branch-protection config — anyone with admin can
drop the requirement, or a ruleset/classic-protection rewrite can silently
remove it, and nothing would notice. The protection only matters if it stays in
place. This script makes that drift catchable on a schedule.

For each wired repo it gathers the EFFECTIVE set of required status-check
contexts on the default branch from BOTH mechanisms GitHub unions together:

  1. Branch RULESETS: every ACTIVE branch ruleset whose conditions target the
     default branch and that carries a `required_status_checks` rule.
  2. CLASSIC branch protection:
     `branches/<default>/protection/required_status_checks`.

If the required context is present via EITHER mechanism the repo is OK for that
check — that keeps it robust to an intentional ruleset rename or a mechanism
swap (moving the requirement from classic to a ruleset still protects). If NO
active mechanism makes the context required on the default branch, that is drift
and the check fails. A per-repo `mechanism` hint is recorded in the report for
context but is NOT used to weaken the union check.

Config supports two shapes:
  * MULTI (current): a top-level `checks` array, each entry
    `{id, required_context, repos: {repo: {mechanism, ...}}}`.
  * LEGACY (single check): top-level `required_context` + `repos`.
Both normalize to the same internal list of check groups.

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

Exit code 0 = every wired repo still requires its context (warnings allowed);
1 = drift (at least one repo no longer requires its context); 2 = could not
complete the check (auth/permission/API failure).
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
    has_legacy = bool(cfg.get("required_context")) and isinstance(
        cfg.get("repos"), dict) and bool(cfg.get("repos"))
    has_multi = isinstance(cfg.get("checks"), list) and bool(cfg.get("checks"))
    if not (has_legacy or has_multi):
        raise CheckError(
            f"Config {path!r} must either be a single check (top-level "
            f"'required_context' + non-empty 'repos' map) or a multi-check "
            f"config (non-empty 'checks' array of "
            f"{{id, required_context, repos}})."
        )
    cfg.setdefault("org", "szl-holdings")
    return cfg


def load_allowlist(path: str) -> dict:
    data = load_json(path)
    data.setdefault("ignore_repos", [])
    return data


def check_groups(cfg: dict) -> list[dict]:
    """Normalize the legacy single-check and the multi-check config shapes into
    a list of `{id, required_context, repos}` groups."""
    if isinstance(cfg.get("checks"), list) and cfg.get("checks"):
        groups = []
        for i, c in enumerate(cfg["checks"]):
            ctx = (c or {}).get("required_context")
            repos = (c or {}).get("repos")
            if not ctx:
                raise CheckError(
                    f"checks[{i}] is missing 'required_context'. Each entry "
                    f"must name the exact status-check context that has to "
                    f"stay required."
                )
            if not isinstance(repos, dict) or not repos:
                raise CheckError(
                    f"checks[{i}] ({ctx!r}) is missing a non-empty 'repos' map "
                    f"of repo-name -> {{mechanism: ruleset|classic}}."
                )
            groups.append({
                "id": c.get("id") or ctx,
                "required_context": ctx,
                "repos": repos,
            })
        return groups
    # Legacy single-check shape.
    return [{
        "id": cfg.get("id") or cfg["required_context"],
        "required_context": cfg["required_context"],
        "repos": cfg["repos"],
    }]


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
    groups = check_groups(cfg)

    errors: list[str] = []
    warnings: list[str] = []
    check_reports: list[dict] = []

    # A repo can be wired for more than one check; read its rulesets / classic
    # protection once and reuse across check groups.
    repo_cache: dict[str, dict] = {}

    def repo_state(repo: str) -> dict:
        if repo not in repo_cache:
            meta = gh_json(f"/repos/{org}/{repo}", token)
            default_branch = meta.get("default_branch", "main")
            rs_ctxs, rs_seen = ruleset_contexts(org, repo, token)
            cl_ctxs, classic_present = classic_contexts(
                org, repo, default_branch, token)
            repo_cache[repo] = {
                "default_branch": default_branch,
                "rs_ctxs": rs_ctxs,
                "rs_seen": rs_seen,
                "cl_ctxs": cl_ctxs,
                "classic_present": classic_present,
            }
        return repo_cache[repo]

    for group in groups:
        required_context = group["required_context"]
        group_id = group["id"]
        repo_report = []

        for repo, spec in group["repos"].items():
            entry = {
                "repo": f"{org}/{repo}",
                "declared_mechanism": (spec or {}).get("mechanism"),
            }
            if repo in allow["ignore_repos"]:
                entry["result"] = "allowlisted"
                repo_report.append(entry)
                continue

            st = repo_state(repo)
            entry["default_branch"] = st["default_branch"]
            entry["rulesets"] = st["rs_seen"]
            entry["classic_protection_present"] = st["classic_present"]
            entry["required_via_ruleset"] = required_context in st["rs_ctxs"]
            entry["required_via_classic"] = required_context in st["cl_ctxs"]

            if entry["required_via_ruleset"] or entry["required_via_classic"]:
                entry["result"] = "ok"
            else:
                entry["result"] = "DRIFT"
                errors.append(
                    f"{org}/{repo}: the context {required_context!r} (check "
                    f"{group_id!r}) is NO LONGER a required status check on "
                    f"'{st['default_branch']}' via any active ruleset or "
                    f"classic branch protection. The merge block is gone — a "
                    f"bad change can now be merged past it. Re-add it (hint: "
                    f"mechanism={entry['declared_mechanism']!r})."
                )
            repo_report.append(entry)

        check_reports.append({
            "id": group_id,
            "required_context": required_context,
            "totals": {
                "wired_repos": len(group["repos"]),
                "ok": sum(1 for e in repo_report if e["result"] == "ok"),
                "drift": sum(1 for e in repo_report if e["result"] == "DRIFT"),
                "allowlisted": sum(
                    1 for e in repo_report if e["result"] == "allowlisted"),
            },
            "repos": repo_report,
        })

    all_repos = [e for c in check_reports for e in c["repos"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "org": org,
        "checks": check_reports,
        "totals": {
            "checks": len(check_reports),
            "wired_repos": sum(len(g["repos"]) for g in groups),
            "ok": sum(1 for e in all_repos if e["result"] == "ok"),
            "drift": sum(1 for e in all_repos if e["result"] == "DRIFT"),
            "allowlisted": sum(
                1 for e in all_repos if e["result"] == "allowlisted"),
            "errors": len(errors),
            "warnings": len(warnings),
        },
        "errors": errors,
        "warnings": warnings,
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
        print(f"Org: {report['org']}  checks={t['checks']}")
        print(
            f"  wired_repos={t['wired_repos']} ok={t['ok']} drift={t['drift']} "
            f"allowlisted={t['allowlisted']}"
        )
        for c in report["checks"]:
            print(f"  [{c['id']}] {c['required_context']!r}")
            for e in c["repos"]:
                print(
                    f"    - {e['repo']}: {e['result']} "
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
