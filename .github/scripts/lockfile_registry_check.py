#!/usr/bin/env python3
"""Replit-internal registry-host checker for committed lockfiles.

Task #308 class of drift: a lockfile (`package-lock.json`, `npm-shrinkwrap.json`,
`pnpm-lock.yaml`, or `yarn.lock`) generated *inside the Replit sandbox* records
`resolved` URLs that point at Replit's internal package mirror
(`http://package-firewall.replit.local/npm/...`, or any other `*.replit.local`
host). Those hosts do NOT resolve off-box, so `npm install` / `pnpm install`
fails with `EAI_AGAIN getaddrinfo package-firewall.replit.local` on GitHub
Actions runners (and any non-Replit machine). A workflow that depends on the
install step then goes permanently red at install — silently starving whatever
that workflow gates (e.g. the docs-site security-audit). The failure looks like
a flaky network error, not a committed-artifact bug, so it can hide for a long
time. For a company whose thesis is provable honesty, that must never ship
silently.

The fix is safe and mechanical: rewrite the host back to the public registry
(`https://registry.npmjs.org/`). The tarball content — and therefore the
`integrity` sha — is identical; only the mirror host differs.

This script has two modes:

  * ORG mode (default): scan every PUBLIC repo in the org over the GitHub API
    for committed lockfiles carrying a `*.replit.local` host, write a JSON
    report, and exit non-zero if any are found. Used on a schedule so a poisoned
    lockfile pushed anywhere in the org is caught fast.

  * LOCAL mode (`--local DIR`): scan lockfiles in a local checkout. Used by the
    reusable workflow (`reusable-lockfile-registry-check.yml`) so a repo can
    fail its OWN push / PR fast — before the poisoned lockfile ever lands on
    main. No network or token required.

Auth (ORG mode only): reads a token from $GITHUB_TOKEN / $GH_TOKEN /
$SZL_GITHUB_TOKEN. In GitHub Actions the built-in $GITHUB_TOKEN is enough — every
repo scanned is public, and public repo listing + git-tree + raw contents read
fine with it.

Usage:
  # org-wide scan + report (CI / schedule)
  python lockfile_registry_check.py [--org szl-holdings] \
      [--allowlist .github/data/lockfile_registry_allowlist.json] \
      [--report .github/data/lockfile_registry_report.json] [--json]

  # scan a local checkout (reusable workflow / pre-commit)
  python lockfile_registry_check.py --local .

Exit code 0 = clean; 1 = at least one lockfile carries a *.replit.local host.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

# Lockfiles worth scanning (text formats only; bun.lockb is binary -> skipped).
LOCKFILE_NAMES = (
    "package-lock.json",
    "npm-shrinkwrap.json",
    "pnpm-lock.yaml",
    "yarn.lock",
)

# Any host that ends in `.replit.local` is an internal Replit mirror that does
# not resolve off-box. `package-firewall.replit.local` is the one seen in the
# wild; the pattern generalizes so a different sandbox host is still caught.
_REPLIT_HOST_RE = re.compile(r"[A-Za-z0-9_.-]+\.replit\.local", re.IGNORECASE)

# The safe rewrite target (tarball + integrity sha are identical; only the
# mirror host differs). Used by --fix and reported as the suggested remedy.
PUBLIC_REGISTRY = "https://registry.npmjs.org/"
# What the poisoned prefix looks like, for the --fix rewrite (path is preserved
# after `/npm/`): http://package-firewall.replit.local/npm/<path> -> registry/<path>
_FIX_RE = re.compile(r"https?://[A-Za-z0-9_.-]+\.replit\.local/npm/", re.IGNORECASE)

# --------------------------------------------------------------------------- #
# Coverage gap detection (--check-coverage)
# --------------------------------------------------------------------------- #
# A repo that *commits* a lockfile must also be protected against the Replit-host
# drift on every future PR/push: it needs (1) the per-repo fail-fast caller
# workflow and (2) that check made REQUIRED on its default branch. The org sweep
# below only catches a lockfile that is *already* poisoned; without coverage
# detection a repo that adds its FIRST lockfile later would silently have neither
# guard, reopening the gap. Coverage detection flags exactly that situation so the
# repo can be wired + required like the existing ones.

# Path of the per-repo fail-fast caller workflow (uses the reusable workflow).
CALLER_WORKFLOW_PATH = ".github/workflows/lockfile-registry.yml"

# The status-check context emitted by the reusable workflow. A reusable workflow
# invoked via `uses:` reports its check as `<caller-job-id> / <reusable-job-name>`.
# The convention across the org is a job id of `lockfiles`, and the reusable job
# name is "No lockfile references a Replit-internal registry host", so the required
# context string is the two joined with " / ". (See lockfile-registry-guard.md.)
REQUIRED_CHECK_CONTEXT = (
    "lockfiles / No lockfile references a Replit-internal registry host"
)


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #
def scan_text(text: str):
    """Return a sorted list of unique `*.replit.local` hosts found in `text`."""
    if not text:
        return []
    return sorted({m.group(0).lower() for m in _REPLIT_HOST_RE.finditer(text)})


def is_lockfile(path: str) -> bool:
    base = path.rsplit("/", 1)[-1]
    return base in LOCKFILE_NAMES


# --------------------------------------------------------------------------- #
# GitHub helpers (ORG mode)
# --------------------------------------------------------------------------- #
def _token() -> str:
    for var in ("GITHUB_TOKEN", "GH_TOKEN", "SZL_GITHUB_TOKEN"):
        v = os.environ.get(var)
        if v:
            return v
    print("error: no GitHub token in $GITHUB_TOKEN / $GH_TOKEN / $SZL_GITHUB_TOKEN",
          file=sys.stderr)
    sys.exit(2)


def _gh(path: str, token: str):
    req = urllib.request.Request(API + path)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def _raw(repo_full: str, ref: str, path: str, token: str):
    """Fetch a file's raw bytes from raw.githubusercontent.com (public repos)."""
    url = f"{RAW}/{repo_full}/{ref}/{urllib.parse.quote(path)}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _gh_status(path: str, token: str):
    """Like _gh but returns (json_or_None, http_status) instead of raising.

    Used by the coverage check, which must distinguish "readable, nothing
    configured" (e.g. 404 = no classic branch protection) from "cannot read"
    (401/403 = the token lacks admin) so it never reports a false coverage gap.
    """
    req = urllib.request.Request(API + path)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp), resp.status
    except urllib.error.HTTPError as e:
        try:
            body = json.load(e)
        except Exception:
            body = None
        return body, e.code


def list_public_repos(org: str, token: str, include_archived: bool):
    repos, page = [], 1
    while True:
        batch = _gh(f"/orgs/{org}/repos?per_page=100&page={page}&type=all", token)
        if not batch:
            break
        repos.extend(batch)
        page += 1
    out = []
    for r in repos:
        if r.get("private"):
            continue
        if r.get("archived") and not include_archived:
            continue
        out.append(r)
    return sorted(out, key=lambda r: r["name"])


def repo_lockfiles(repo_full: str, ref: str, token: str):
    """List committed lockfile paths in a repo via the recursive git tree."""
    try:
        tree = _gh(f"/repos/{repo_full}/git/trees/{urllib.parse.quote(ref, safe='')}?recursive=1",
                   token)
    except urllib.error.HTTPError as e:
        if e.code in (404, 409):  # empty repo / missing ref
            return []
        raise
    paths = []
    for node in tree.get("tree", []):
        if node.get("type") != "blob":
            continue
        p = node.get("path", "")
        if "node_modules/" in p:
            continue
        if is_lockfile(p):
            paths.append(p)
    return sorted(paths)


def repo_tree_blobs(repo_full: str, ref: str, token: str):
    """Return every (non-node_modules) blob path in a repo's default-branch tree."""
    try:
        tree = _gh(f"/repos/{repo_full}/git/trees/{urllib.parse.quote(ref, safe='')}?recursive=1",
                   token)
    except urllib.error.HTTPError as e:
        if e.code in (404, 409):  # empty repo / missing ref
            return []
        raise
    out = []
    for node in tree.get("tree", []):
        if node.get("type") != "blob":
            continue
        p = node.get("path", "")
        if "node_modules/" in p:
            continue
        out.append(p)
    return out


def check_repo(repo_obj, token, ignore_paths, blobs=None):
    full = repo_obj["full_name"]
    ref = repo_obj.get("default_branch") or "main"
    if blobs is None:
        lockfiles = repo_lockfiles(full, ref, token)
    else:
        lockfiles = sorted(p for p in blobs if is_lockfile(p))
    findings = []
    for path in lockfiles:
        if path in ignore_paths:
            continue
        text = _raw(full, ref, path, token)
        if text is None:
            continue
        hosts = scan_text(text)
        if hosts:
            findings.append({"path": path, "hosts": hosts})
    status = "ERROR" if findings else "OK"
    return {
        "repo": repo_obj["name"],
        "archived": repo_obj.get("archived", False),
        "default_branch": ref,
        "status": status,
        "findings": findings,
    }


# --------------------------------------------------------------------------- #
# Coverage gap detection
# --------------------------------------------------------------------------- #
def _ruleset_targets_branch(detail: dict, branch: str) -> bool:
    """True if a ruleset's ref-name condition applies to `branch`."""
    cond = (detail.get("conditions") or {}).get("ref_name") or {}
    include = cond.get("include") or []
    exclude = cond.get("exclude") or []
    ref = f"refs/heads/{branch}"
    applies = ("~ALL" in include or "~DEFAULT_BRANCH" in include or ref in include)
    blocked = ref in exclude
    return applies and not blocked


def required_check_present(repo_full: str, branch: str, token: str):
    """Determine whether REQUIRED_CHECK_CONTEXT is a required check on `branch`.

    Returns one of "present" / "absent" / "unverifiable". The required check can
    be enforced two ways across the org — classic branch protection or a repo
    ruleset — so both are consulted. "unverifiable" is returned only when neither
    source can be read (token without admin), so a coverage gap is never reported
    on a false read.
    """
    verifiable = False

    # 1) Classic branch protection.
    data, code = _gh_status(
        f"/repos/{repo_full}/branches/{urllib.parse.quote(branch, safe='')}"
        "/protection/required_status_checks", token)
    if code == 200:
        verifiable = True
        contexts = [c.get("context") for c in (data or {}).get("checks", [])]
        if REQUIRED_CHECK_CONTEXT in contexts:
            return "present"
    elif code == 404:
        # Readable, but no classic required-status-checks configured.
        verifiable = True

    # 2) Repo rulesets (e.g. series-a-default-branch).
    rulesets, code = _gh_status(f"/repos/{repo_full}/rulesets?includes_parents=true", token)
    if code == 200:
        verifiable = True
        for rs in rulesets or []:
            if rs.get("enforcement") != "active":
                continue
            detail, dcode = _gh_status(f"/repos/{repo_full}/rulesets/{rs['id']}", token)
            if dcode != 200 or not detail:
                continue
            if not _ruleset_targets_branch(detail, branch):
                continue
            for rule in detail.get("rules", []):
                if rule.get("type") != "required_status_checks":
                    continue
                params = rule.get("parameters") or {}
                contexts = [c.get("context")
                            for c in params.get("required_status_checks", [])]
                if REQUIRED_CHECK_CONTEXT in contexts:
                    return "present"

    return "absent" if verifiable else "unverifiable"


def check_repo_coverage(repo_obj, token, blobs):
    """For a repo that COMMITS a lockfile, verify it is wired + required.

    `blobs` is the repo's default-branch blob list (already fetched). Only repos
    that actually commit a lockfile need the guard, so repos with none are not
    flagged. Returns a coverage record, or None if the repo has no lockfile.
    """
    lockfiles = sorted(p for p in blobs if is_lockfile(p))
    if not lockfiles:
        return None
    full = repo_obj["full_name"]
    branch = repo_obj.get("default_branch") or "main"

    caller_present = CALLER_WORKFLOW_PATH in blobs
    required = required_check_present(full, branch, token)

    gaps = []
    if not caller_present:
        gaps.append("missing caller workflow " + CALLER_WORKFLOW_PATH)
    if required == "absent":
        gaps.append(
            f"required status check '{REQUIRED_CHECK_CONTEXT}' not enforced on "
            f"{branch}")

    if gaps:
        status = "GAP"
    elif required == "unverifiable":
        status = "UNVERIFIABLE"
    else:
        status = "OK"

    return {
        "repo": repo_obj["name"],
        "default_branch": branch,
        "lockfiles": lockfiles,
        "caller_workflow_present": caller_present,
        "required_check": required,
        "status": status,
        "gaps": gaps,
    }


# --------------------------------------------------------------------------- #
# LOCAL mode
# --------------------------------------------------------------------------- #
def scan_local(root: str, fix: bool):
    """Walk `root`, scan (optionally fix) every lockfile. Returns findings list."""
    findings = []
    for dirpath, dirnames, filenames in os.walk(root):
        if "node_modules" in dirnames:
            dirnames.remove("node_modules")
        if ".git" in dirnames:
            dirnames.remove(".git")
        for fn in filenames:
            if fn not in LOCKFILE_NAMES:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            hosts = scan_text(text)
            if not hosts:
                continue
            entry = {"path": rel, "hosts": hosts}
            if fix:
                fixed = _FIX_RE.sub(PUBLIC_REGISTRY, text)
                # also catch a bare host with no /npm/ path, conservatively.
                if fixed != text:
                    with open(full, "w", encoding="utf-8") as fh:
                        fh.write(fixed)
                    entry["fixed"] = True
                    entry["remaining"] = scan_text(fixed)
            findings.append(entry)
    return findings


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def _emit_annotations(findings_by_repo):
    for r in findings_by_repo:
        for f in r["findings"]:
            hosts = ", ".join(f["hosts"])
            print(f"::error::{r['repo']}/{f['path']} references Replit-internal "
                  f"registry host(s): {hosts}. Rewrite to {PUBLIC_REGISTRY} "
                  f"(integrity unchanged).")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Catch Replit-internal (*.replit.local) registry hosts in lockfiles.")
    ap.add_argument("--org", default="szl-holdings")
    ap.add_argument("--local", metavar="DIR",
                    help="Scan lockfiles in a local checkout instead of the org API.")
    ap.add_argument("--fix", action="store_true",
                    help="(LOCAL mode) rewrite *.replit.local hosts to the public "
                         "registry in place.")
    ap.add_argument("--allowlist", default=os.path.join(
        os.path.dirname(__file__), "..", "data", "lockfile_registry_allowlist.json"))
    ap.add_argument("--report", help="Write the full JSON report to this path.")
    ap.add_argument("--include-archived", action="store_true",
                    help="Also scan archived repos (ORG mode).")
    ap.add_argument("--check-coverage", action="store_true",
                    help="(ORG mode) also flag any repo that COMMITS a lockfile but "
                         "is missing the per-repo caller workflow or the required "
                         "status check on its default branch. Needs an org-admin "
                         "token to read branch protection/rulesets; repos it cannot "
                         "read are reported 'unverifiable' (never a false gap).")
    ap.add_argument("--json", action="store_true", help="Print the JSON report to stdout.")
    args = ap.parse_args()

    # ---------------- LOCAL mode ---------------- #
    if args.local:
        findings = scan_local(args.local, args.fix)
        payload = {
            "schema": "szl.lockfile_registry/v1",
            "mode": "local",
            "root": os.path.abspath(args.local),
            "checked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fix": args.fix,
            "findings": findings,
        }
        if args.report:
            os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
            with open(args.report, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, indent=2) + "\n")
        if args.json:
            print(json.dumps(payload, indent=2))
        unresolved = [f for f in findings if f.get("remaining") or not f.get("fixed")]
        for f in findings:
            tag = "fixed" if f.get("fixed") else "FOUND"
            print(f"  [{tag}] {f['path']}: {', '.join(f['hosts'])}")
            if f.get("fixed"):
                print(f"          -> rewritten to {PUBLIC_REGISTRY}")
                _emit = f.get("remaining")
                if _emit:
                    print(f"          !! still references: {', '.join(_emit)}")
        if args.fix:
            # In fix mode, success means nothing remains after the rewrite.
            if unresolved:
                print(f"\n{len(unresolved)} lockfile(s) still reference a "
                      f"*.replit.local host after --fix. See above.", file=sys.stderr)
                return 1
            if findings:
                print(f"\n✓ Rewrote {len(findings)} lockfile(s) to {PUBLIC_REGISTRY}.")
            else:
                print("✓ No lockfile references a Replit-internal registry host.")
            return 0
        if findings:
            for f in findings:
                print(f"::error::{f['path']} references Replit-internal registry "
                      f"host(s): {', '.join(f['hosts'])}. Rewrite to {PUBLIC_REGISTRY} "
                      f"(integrity unchanged) — e.g. run this script with --fix.")
            print(f"\n{len(findings)} lockfile(s) reference a Replit-internal "
                  f"(*.replit.local) registry host. These break npm/pnpm install on "
                  f"GitHub runners. Rewrite the host to {PUBLIC_REGISTRY}.",
                  file=sys.stderr)
            return 1
        print("✓ No lockfile references a Replit-internal registry host.")
        return 0

    # ---------------- ORG mode ---------------- #
    token = _token()
    allow = {}
    if args.allowlist and os.path.exists(args.allowlist):
        with open(args.allowlist, "r", encoding="utf-8") as fh:
            allow = json.load(fh)
    ignore_repos = set(allow.get("ignore_repos", []))
    ignore_paths = set(allow.get("ignore_paths", []))

    repos = list_public_repos(args.org, token, args.include_archived)
    results = []
    coverage = []
    for r in repos:
        if r["name"] in ignore_repos:
            continue
        # Fetch the default-branch tree once and reuse it for the poisoned-host
        # scan and (when enabled) the coverage check.
        blobs = repo_tree_blobs(r["full_name"], r.get("default_branch") or "main", token)
        results.append(check_repo(r, token, ignore_paths, blobs=blobs))
        if args.check_coverage and not r.get("archived"):
            cov = check_repo_coverage(r, token, blobs)
            if cov is not None:
                coverage.append(cov)

    errs = [x for x in results if x["status"] == "ERROR"]
    cov_gaps = [c for c in coverage if c["status"] == "GAP"]
    payload = {
        "schema": "szl.lockfile_registry/v1",
        "mode": "org",
        "org": args.org,
        "checked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "include_archived": args.include_archived,
        "summary": {
            "checked": len(results),
            "ok": sum(1 for x in results if x["status"] == "OK"),
            "error": len(errs),
        },
        "results": results,
    }
    if args.check_coverage:
        payload["coverage_summary"] = {
            "lockfile_repos": len(coverage),
            "ok": sum(1 for c in coverage if c["status"] == "OK"),
            "gap": len(cov_gaps),
            "unverifiable": sum(1 for c in coverage if c["status"] == "UNVERIFIABLE"),
        }
        payload["coverage"] = coverage

    if args.report:
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {args.report}")

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Lockfile registry-host check for {args.org}: "
              f"{payload['summary']['ok']} OK, {len(errs)} ERROR "
              f"(of {len(results)} public repos checked)\n")
        for x in results:
            mark = {"OK": "\u2713", "ERROR": "\u2717"}[x["status"]]
            arch = " [archived]" if x["archived"] else ""
            print(f"  {mark} {x['repo']}{arch}")
            for f in x["findings"]:
                print(f"        {f['path']}: {', '.join(f['hosts'])}")
        if args.check_coverage:
            cs = payload["coverage_summary"]
            print(f"\nLockfile-guard coverage: {cs['ok']} OK, {cs['gap']} GAP, "
                  f"{cs['unverifiable']} unverifiable "
                  f"(of {cs['lockfile_repos']} repos that commit a lockfile)")
            cmark = {"OK": "\u2713", "GAP": "\u2717", "UNVERIFIABLE": "?"}
            for c in coverage:
                print(f"  {cmark[c['status']]} {c['repo']}")
                for g in c["gaps"]:
                    print(f"        {g}")

    if cov_gaps:
        for c in cov_gaps:
            for g in c["gaps"]:
                print(f"::error::{c['repo']} commits a lockfile but {g}. Wire the "
                      f"per-repo caller workflow ({CALLER_WORKFLOW_PATH}) and make "
                      f"the '{REQUIRED_CHECK_CONTEXT}' check required on "
                      f"{c['default_branch']}, like the already-protected repos.")

    if errs:
        _emit_annotations(errs)
        print(f"\n{len(errs)} repo(s) have a lockfile referencing a Replit-internal "
              f"(*.replit.local) registry host. These break npm/pnpm install on "
              f"GitHub runners. Rewrite the host to {PUBLIC_REGISTRY} (integrity "
              f"unchanged).", file=sys.stderr)
    if cov_gaps:
        print(f"\n{len(cov_gaps)} repo(s) commit a lockfile but are missing the "
              f"per-repo caller workflow and/or the required status check on their "
              f"default branch, reopening the *.replit.local gap for any future "
              f"lockfile change. See the annotations above and the 'coverage' "
              f"section of the report.", file=sys.stderr)

    return 1 if (errs or cov_gaps) else 0


if __name__ == "__main__":
    raise SystemExit(main())
