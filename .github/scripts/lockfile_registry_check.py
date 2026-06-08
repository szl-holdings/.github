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
        tree = _gh(f"/repos/{repo_full}/git/trees/{urllib.parse.quote(ref)}?recursive=1",
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


def check_repo(repo_obj, token, ignore_paths):
    full = repo_obj["full_name"]
    ref = repo_obj.get("default_branch") or "main"
    findings = []
    for path in repo_lockfiles(full, ref, token):
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
    for r in repos:
        if r["name"] in ignore_repos:
            continue
        results.append(check_repo(r, token, ignore_paths))

    errs = [x for x in results if x["status"] == "ERROR"]
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

    if errs:
        _emit_annotations(errs)
        print(f"\n{len(errs)} repo(s) have a lockfile referencing a Replit-internal "
              f"(*.replit.local) registry host. These break npm/pnpm install on "
              f"GitHub runners. Rewrite the host to {PUBLIC_REGISTRY} (integrity "
              f"unchanged).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
