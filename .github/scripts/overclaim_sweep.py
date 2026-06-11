#!/usr/bin/env python3
"""Org-wide honesty-overclaim sweep for governed Markdown docs.

The reusable doctrine-overclaim guard
(`.github/workflows/reusable-overclaim-guard.yml`) only runs in a repo that opts
in by wiring a thin caller workflow. A repo that never wires the caller — or that
publishes an overclaim in a doc outside the caller's narrow governed-surface list
— is completely uncovered. The license-consistency and lockfile-registry guards
each ALSO ship a scheduled org-wide sweep in `szl-holdings/.github` that walks
every public repo as a catch-all; this script is the equivalent safety net for
the honesty-overclaim rule.

What it catches (the SAME grep as the reusable guard, ported to Python so the two
stay in lockstep):

  A) An unqualified "Λ (the aggregator) is unique / uniqueness of Λ is proven"
     claim with NO governance-safe qualifier (Theorem U / U₁ / U₂; uniqueness
     modulo ≈Λ under the Identifiability Assumptions; strict equality only under
     Anchored/Normalized). Unconditional uniqueness is Conjecture 1 and stays
     OPEN (machine-checked false as stated).

  B) Conjecture 1 described as proven / closed / resolved, with the verb bound
     tightly to "Conjecture 1" so honest meta-prose ("...what was proven and what
     was not") is not a false positive.

Two modes (mirrors lockfile_registry_check.py):

  * ORG mode (default): list every PUBLIC repo in the org, walk each repo's
    default-branch git tree, raw-fetch every committed Markdown doc, run the grep,
    write a JSON report, and exit non-zero if any governed doc overclaims. Used on
    a weekly schedule so an overclaim pushed to an UNWIRED repo is still caught.

  * LOCAL mode (`--local DIR`): scan Markdown under a local checkout. Used for
    testing the grep against a synthetic fixture; no network or token required.

Auth (ORG mode only): a token from $SZL_GITHUB_TOKEN / $GH_TOKEN / $GITHUB_TOKEN.
Every repo scanned is public, so the built-in Actions $GITHUB_TOKEN is sufficient
(public repo listing + git-tree + raw contents all read fine with it).

Usage:
  # org-wide sweep + report (CI / schedule)
  python overclaim_sweep.py [--org szl-holdings] \
      [--allowlist .github/data/overclaim_sweep_allowlist.json] \
      [--report .github/data/overclaim_sweep_report.json] [--json]

  # scan a local checkout (testing / pre-commit)
  python overclaim_sweep.py --local .

Exit code 0 = clean; 1 = at least one governed doc carries an overclaim.
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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"

# The governed-surface set — kept byte-identical to the CANDIDATES default in
# .github/workflows/reusable-overclaim-guard.yml. These are the honest-taxonomy
# docs the per-repo caller checks; this sweep fans the SAME grep over the SAME
# surfaces across EVERY public repo, so a repo that never wired the caller still
# has its governed surfaces enforced.
#
# Scope is deliberately this fixed list, NOT every committed Markdown doc: the
# grep is tuned for the curated governed surfaces, and the org's own canonical
# doctrine prose elsewhere (e.g. docs that explain "Λ-uniqueness is Conjecture 1,
# *not* a theorem") legitimately discusses uniqueness/Conjecture-1 in ways that a
# whole-tree scan would mis-flag. Mirroring the reusable guard's surfaces keeps
# the two in lockstep — green here iff green in the per-repo caller. A repo with
# an extra governed surface can add it via the allowlist's "extra_surfaces".
GOVERNED_SURFACES = (
    "README.md",
    "PROVEN_FORMULAS.md",
    "STATUS.md",
    "DEPENDENCY_MAP.md",
    "PAPERS_INDEX.md",
    "preprints/puriq/README.md",
)

# --------------------------------------------------------------------------- #
# Grep logic — kept byte-for-byte equivalent to the regexes in
# .github/workflows/reusable-overclaim-guard.yml so a repo that is green in the
# per-repo caller is green here, and vice versa. grep -i => re.IGNORECASE; grep is
# per-line, so we evaluate line by line. Edit BOTH places together.
# --------------------------------------------------------------------------- #
# Qualifiers that make a Λ-uniqueness sentence governance-safe (A-pattern exempt).
_SAFE_RE = re.compile(
    r"[Cc]onjecture|[Cc]onditional|modulo|≈Λ|≉Λ|Theorem U|TheoremU|U₁|U₂|"
    r"under IA|Identifiab|Anchored|Normalized|statement-only|machine-checked|"
    r"FALSE|false|not a theorem|NOT a theorem|never|stays|OPEN|open|bounty|"
    r"lambda_unique_|unique aggregator|min-gate|impostor",
    re.IGNORECASE,
)

# A) Unconditional "Λ is unique" / "uniqueness of Λ is proven" with NO safe qualifier.
_A_RE = re.compile(
    r"(Λ|lambda)[^.|]{0,80}(is|are|was)[^.|]{0,40}uniqu"
    r"|uniqu[a-z]*[^.|]{0,40}(of|for)[^.|]{0,20}(Λ|lambda)[^.|]{0,40}"
    r"(is |are )?(proven|proved|established|a theorem)",
    re.IGNORECASE,
)

# B) Conjecture 1 declared proven / closed / resolved (verb tightly bound).
_B_RE = re.compile(
    r"conjecture[ _-]?1\b[^.|]{0,25}(is |was |now |been |=|: )?"
    r"(proven|proved|closed|resolved|solved|a theorem|holds unconditionally)",
    re.IGNORECASE,
)
# B-specific exclusion list (narrower than _SAFE_RE, matching the reusable guard).
_B_EXCLUDE_RE = re.compile(
    r"statement-only|machine-checked|FALSE|false|OPEN|open|not |never|stays|"
    r"bounty|non-claim|unqualified|overclaim",
    re.IGNORECASE,
)


def grep_overclaims(text: str):
    """Return a list of {line, type, text} overclaim hits in `text`.

    `type` is "lambda_uniqueness" (A) or "conjecture1_proven" (B), mirroring the
    two annotations the reusable guard emits.
    """
    hits = []
    if not text:
        return hits
    for i, line in enumerate(text.splitlines(), start=1):
        if _A_RE.search(line) and not _SAFE_RE.search(line):
            hits.append({"line": i, "type": "lambda_uniqueness", "text": line.strip()[:300]})
        if _B_RE.search(line) and not _B_EXCLUDE_RE.search(line):
            hits.append({"line": i, "type": "conjecture1_proven", "text": line.strip()[:300]})
    return hits


# --------------------------------------------------------------------------- #
# GitHub helpers (ORG mode)
# --------------------------------------------------------------------------- #
def _token() -> str:
    for var in ("SZL_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(var)
        if v:
            return v
    print("error: no GitHub token in $SZL_GITHUB_TOKEN / $GH_TOKEN / $GITHUB_TOKEN",
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


def check_repo(repo_obj, token, ignore_paths, extra_surfaces):
    full = repo_obj["full_name"]
    ref = repo_obj.get("default_branch") or "main"
    candidates = list(GOVERNED_SURFACES) + list(extra_surfaces)
    paths = [
        p for p in candidates
        if p not in ignore_paths and f"{repo_obj['name']}:{p}" not in ignore_paths
    ]

    # Probe the governed surfaces concurrently — most repos hold only a few of
    # these and a missing file is a cheap 404. The grep + per-repo result are
    # independent of fetch order; findings are re-sorted by path below so the
    # report stays deterministic.
    def _scan(path):
        text = _raw(full, ref, path, token)
        if text is None:
            return None
        hits = grep_overclaims(text)
        return {"path": path, "hits": hits} if hits else None

    findings = []
    if paths:
        with ThreadPoolExecutor(max_workers=6) as pool:
            for res in pool.map(_scan, paths):
                if res is not None:
                    findings.append(res)
        findings.sort(key=lambda f: f["path"])
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
def scan_local(root: str, extra_surfaces=()):
    """Scan the governed-surface set inside a local checkout (mirrors ORG mode)."""
    findings = []
    for rel in list(GOVERNED_SURFACES) + list(extra_surfaces):
        full = os.path.join(root, rel)
        if not os.path.isfile(full):
            continue
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        hits = grep_overclaims(text)
        if hits:
            findings.append({"path": rel, "hits": hits})
    findings.sort(key=lambda f: f["path"])
    return findings


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def _emit_annotations(findings_by_repo):
    for r in findings_by_repo:
        for f in r["findings"]:
            for h in f["hits"]:
                where = f"{r['repo']}/{f['path']}:{h['line']}"
                if h["type"] == "lambda_uniqueness":
                    print(f"::error::{where} — unqualified Λ-uniqueness overclaim. "
                          f"Cite Theorem U / U₁ / U₂ (uniqueness modulo ≈Λ under the "
                          f"Identifiability Assumptions; strict = only under "
                          f"Anchored/Normalized). Unconditional uniqueness is "
                          f"Conjecture 1 (OPEN). Line: {h['text']}")
                else:
                    print(f"::error::{where} — Conjecture 1 described as proven/closed; "
                          f"it is OPEN (statement-only, machine-checked false as "
                          f"stated). Line: {h['text']}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Org-wide sweep for honesty overclaims in governed Markdown docs.")
    ap.add_argument("--org", default="szl-holdings")
    ap.add_argument("--local", metavar="DIR",
                    help="Scan Markdown in a local checkout instead of the org API.")
    ap.add_argument("--allowlist", default=os.path.join(
        os.path.dirname(__file__), "..", "data", "overclaim_sweep_allowlist.json"))
    ap.add_argument("--report", help="Write the full JSON report to this path.")
    ap.add_argument("--include-archived", action="store_true",
                    help="Also scan archived repos (ORG mode).")
    ap.add_argument("--json", action="store_true", help="Print the JSON report to stdout.")
    args = ap.parse_args()

    allow = {}
    if args.allowlist and os.path.exists(args.allowlist):
        with open(args.allowlist, "r", encoding="utf-8") as fh:
            allow = json.load(fh)
    ignore_repos = set(allow.get("ignore_repos", []))
    ignore_paths = set(allow.get("ignore_paths", []))
    extra_surfaces = list(allow.get("extra_surfaces", []))

    # ---------------- LOCAL mode ---------------- #
    if args.local:
        findings = scan_local(args.local, extra_surfaces)
        payload = {
            "schema": "szl.overclaim_sweep/v1",
            "mode": "local",
            "root": os.path.abspath(args.local),
            "checked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "findings": findings,
        }
        if args.report:
            os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
            with open(args.report, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, indent=2) + "\n")
        if args.json:
            print(json.dumps(payload, indent=2))
        for f in findings:
            for h in f["hits"]:
                print(f"  [FOUND] {f['path']}:{h['line']} ({h['type']}): {h['text']}")
        if findings:
            print(f"\n{sum(len(f['hits']) for f in findings)} overclaim(s) in "
                  f"{len(findings)} doc(s). See above.", file=sys.stderr)
            return 1
        print("✓ No governed Markdown doc carries an honesty overclaim.")
        return 0

    # ---------------- ORG mode ---------------- #
    token = _token()
    repos = list_public_repos(args.org, token, args.include_archived)
    results = []
    for r in repos:
        if r["name"] in ignore_repos:
            continue
        results.append(check_repo(r, token, ignore_paths, extra_surfaces))

    errs = [x for x in results if x["status"] == "ERROR"]
    payload = {
        "schema": "szl.overclaim_sweep/v1",
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
        print(f"Overclaim sweep for {args.org}: {payload['summary']['ok']} OK, "
              f"{len(errs)} ERROR (of {len(results)} public repos checked)\n")
        for x in results:
            mark = {"OK": "\u2713", "ERROR": "\u2717"}[x["status"]]
            arch = " [archived]" if x["archived"] else ""
            print(f"  {mark} {x['repo']}{arch}")
            for f in x["findings"]:
                for h in f["hits"]:
                    print(f"        {f['path']}:{h['line']} ({h['type']}): {h['text']}")

    if errs:
        _emit_annotations(errs)
        print(f"\n{len(errs)} repo(s) have a governed Markdown doc that overclaims "
              f"Λ-uniqueness or declares Conjecture 1 proven. Cite Theorem U / U₁ / "
              f"U₂ (uniqueness modulo ≈Λ under IA; strict = only under "
              f"Anchored/Normalized); Conjecture 1 stays OPEN. See annotations + the "
              f"report.", file=sys.stderr)

    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
