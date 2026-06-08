#!/usr/bin/env python3
"""License-claim consistency checker for the szl-holdings org.

Issue #202 happened because a repo's public license badge / README claimed one
license while the actual LICENSE file said another (a11oy: README said
Apache-2.0, LICENSE was proprietary). For a company whose thesis is provable
honesty, that class of drift must never ship silently. This script makes it
catchable in CI / on a schedule.

For every PUBLIC repo in the org it compares GitHub's *detected* SPDX id
(`license.spdx_id`, the truth derived from the actual LICENSE file) against the
license *claimed* in three public surfaces:
  1. README front-matter `license:` (HuggingFace/Jekyll style)
  2. README shields.io License badge (the rendered, publicly-visible claim)
  3. CITATION.cff `license:`

Any mismatch — or a NOASSERTION (GitHub couldn't match the LICENSE to a known
SPDX id) — is flagged as an ERROR unless the repo is explicitly allowlisted as
an intentional case (e.g. a deliberately proprietary repo, or a dual-licensed
data/code repo). Allowlisting is explicit and reasoned — nothing is silently
"passed".

Auth: reads a GitHub token from $GITHUB_TOKEN / $GH_TOKEN / $SZL_GITHUB_TOKEN.
In GitHub Actions the built-in $GITHUB_TOKEN is enough — every repo checked is
public, and public repo listing + contents read work fine with it.

Usage:
  python license_consistency.py [--org szl-holdings] \
      [--allowlist .github/data/license_allowlist.json] \
      [--report .github/data/license_consistency_report.json] \
      [--include-archived] [--json]

Exit code 0 = all consistent (warnings allowed); 1 = at least one ERROR.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"


# --------------------------------------------------------------------------- #
# GitHub helpers
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


def _gh_text(repo: str, path: str, token: str):
    """Return decoded file contents, or None if the file is absent (404)."""
    import base64
    try:
        r = _gh(f"/repos/{repo}/contents/{urllib.parse.quote(path)}", token)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if isinstance(r, dict) and r.get("content"):
        return base64.b64decode(r["content"]).decode("utf-8", "replace")
    return None


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


# --------------------------------------------------------------------------- #
# License-string normalization
# --------------------------------------------------------------------------- #
_CANON = [
    (re.compile(r"^apache(\s+license)?[\s_-]*2(\.0)?$"), "Apache-2.0"),
    (re.compile(r"^cc[\s_-]*by[\s_-]*4(\.0)?$"), "CC-BY-4.0"),
    (re.compile(r"^cc[\s_-]*by[\s_-]*sa[\s_-]*4(\.0)?$"), "CC-BY-SA-4.0"),
    (re.compile(r"^cc0[\s_-]*1?(\.0)?$"), "CC0-1.0"),
    (re.compile(r"^mit$"), "MIT"),
    (re.compile(r"^bsd[\s_-]*3([\s_-]*clause)?$"), "BSD-3-Clause"),
    (re.compile(r"^bsd[\s_-]*2([\s_-]*clause)?$"), "BSD-2-Clause"),
    (re.compile(r"^mpl[\s_-]*2(\.0)?$"), "MPL-2.0"),
    (re.compile(r"^gpl[\s_-]*v?3(\.0)?$"), "GPL-3.0"),
    (re.compile(r"^agpl[\s_-]*v?3(\.0)?$"), "AGPL-3.0"),
]


def normalize_license(raw: str) -> str:
    """Map any license string (SPDX id, badge text, prose) to a canonical form."""
    if raw is None:
        return ""
    s = raw.strip()
    if not s:
        return ""
    low = s.lower()
    # Proprietary / custom LicenseRef -> single bucket
    if "proprietary" in low or low.startswith("licenseref"):
        return "Proprietary"
    if low in ("noassertion",):
        return "NOASSERTION"
    if low in ("none", "no-license", "unlicensed"):
        return "NONE"
    cleaned = re.sub(r"[^a-z0-9.+\s_-]", "", low).strip()
    for rx, canon in _CANON:
        if rx.match(cleaned):
            return canon
    # Fall back to the raw SPDX-style token (e.g. an SPDX id we don't special-case)
    return s


# --------------------------------------------------------------------------- #
# Claim extraction
# --------------------------------------------------------------------------- #
_FRONTMATTER_RE = re.compile(r"^\ufeff?---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FM_LICENSE_RE = re.compile(r"^\s*license\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_CFF_LICENSE_RE = re.compile(r"^\s*license\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_BADGE_RE = re.compile(r"https?://img\.shields\.io/badge/([^)\s\"']+)")


def _strip_quotes(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
        v = v[1:-1]
    return v.strip()


def _shields_decode(field: str) -> str:
    """Decode a single shields.io path field: %xx, '__'->'_', '_'->' ', '--'->'-'."""
    s = urllib.parse.unquote(field)
    s = s.replace("__", "\x01").replace("--", "\x02")
    s = s.replace("_", " ").replace("\x01", "_").replace("\x02", "-")
    return s.strip()


def _split_badge_fields(path: str):
    """Split 'Label-Message-Color' honoring shields '--' = literal hyphen."""
    path = path.split("?", 1)[0]
    for ext in (".svg", ".png", ".json"):
        if path.endswith(ext):
            path = path[: -len(ext)]
    tmp = path.replace("--", "\x00")
    parts = [p.replace("\x00", "--") for p in tmp.split("-")]
    return parts


def claims_from_readme(readme: str):
    """Return (frontmatter_claims, badge_claims) as lists of raw strings."""
    fm_claims, badge_claims = [], []
    if not readme:
        return fm_claims, badge_claims
    m = _FRONTMATTER_RE.match(readme)
    if m:
        for lm in _FM_LICENSE_RE.finditer(m.group(1)):
            fm_claims.append(_strip_quotes(lm.group(1)))
    for bm in _BADGE_RE.finditer(readme):
        fields = _split_badge_fields(bm.group(1))
        if len(fields) < 2:
            continue
        label = _shields_decode(fields[0])
        message = _shields_decode(fields[1])
        # Only treat as a license badge when the label mentions licen[sc]e.
        if not re.search(r"licen[sc]e", label, re.IGNORECASE):
            continue
        # A message may carry a dual claim, e.g. "Apache-2.0 | CC-BY-4.0".
        for piece in re.split(r"[|/]", message):
            piece = piece.strip()
            if piece:
                badge_claims.append(piece)
    return fm_claims, badge_claims


def claims_from_cff(cff: str):
    if not cff:
        return []
    return [_strip_quotes(m.group(1)) for m in _CFF_LICENSE_RE.finditer(cff)]


# --------------------------------------------------------------------------- #
# Per-repo check
# --------------------------------------------------------------------------- #
def check_repo(repo_obj, token, allow_entry):
    name = repo_obj["name"]
    spdx = (repo_obj.get("license") or {}).get("spdx_id")  # e.g. Apache-2.0 / NOASSERTION / NONE / None
    detected_norm = normalize_license(spdx) if spdx else "NONE"

    readme = _gh_text(f"{repo_obj['full_name']}", "README.md", token)
    cff = _gh_text(f"{repo_obj['full_name']}", "CITATION.cff", token)
    fm_claims, badge_claims = claims_from_readme(readme)
    cff_claims = claims_from_cff(cff)

    # Allowed set: canonical (expected override OR detected) + extra allowed claims.
    expected = (allow_entry or {}).get("expected_spdx")
    canonical = normalize_license(expected) if expected else detected_norm
    allowed = {canonical}
    for c in (allow_entry or {}).get("allowed_claims", []):
        allowed.add(normalize_license(c))
    allowed.discard("")

    errors, warnings = [], []

    # 1. LICENSE presence / detectability
    if detected_norm == "NONE":
        errors.append("no LICENSE file detected by GitHub")
    elif detected_norm == "NOASSERTION":
        if allow_entry and expected:
            pass  # intentional custom/proprietary license, allowlisted
        else:
            errors.append("GitHub reports NOASSERTION (LICENSE not a recognized SPDX id) "
                          "— allowlist it as intentional, or use a standard LICENSE")

    # 2. Claim-vs-detected comparison
    def _check(source, raws):
        for raw in raws:
            n = normalize_license(raw)
            if not n:
                continue
            if n not in allowed:
                errors.append(f"{source} claims '{raw}' (={n}) "
                              f"but allowed={sorted(allowed)}")

    _check("README front-matter", fm_claims)
    _check("README badge", badge_claims)
    _check("CITATION.cff", cff_claims)

    # 3. Soft warning: a public repo with no explicit, structured license claim.
    if not (fm_claims or badge_claims or cff_claims):
        warnings.append("no structured license claim (badge / front-matter / CITATION.cff)")

    status = "ERROR" if errors else ("WARN" if warnings else "OK")
    return {
        "repo": name,
        "archived": repo_obj.get("archived", False),
        "detected_spdx": spdx,
        "detected_norm": detected_norm,
        "allowlisted": bool(allow_entry),
        "claims": {
            "frontmatter": fm_claims,
            "badge": badge_claims,
            "citation_cff": cff_claims,
        },
        "status": status,
        "errors": errors,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="szl-holdings license-claim consistency checker.")
    ap.add_argument("--org", default="szl-holdings")
    ap.add_argument("--allowlist", default=os.path.join(
        os.path.dirname(__file__), "..", "data", "license_allowlist.json"))
    ap.add_argument("--report", help="Write the full JSON report to this path.")
    ap.add_argument("--include-archived", action="store_true",
                    help="Also check archived repos (they cannot be auto-fixed).")
    ap.add_argument("--json", action="store_true", help="Print the JSON report to stdout.")
    args = ap.parse_args()

    token = _token()

    allow = {}
    if args.allowlist and os.path.exists(args.allowlist):
        with open(args.allowlist, "r", encoding="utf-8") as fh:
            allow = json.load(fh)
    allow_repos = allow.get("repos", {})
    ignore_repos = set(allow.get("ignore_repos", []))

    repos = list_public_repos(args.org, token, args.include_archived)
    results = []
    for r in repos:
        if r["name"] in ignore_repos:
            continue
        results.append(check_repo(r, token, allow_repos.get(r["name"])))

    errs = [x for x in results if x["status"] == "ERROR"]
    warns = [x for x in results if x["status"] == "WARN"]
    payload = {
        "schema": "szl.license_consistency/v1",
        "org": args.org,
        "checked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "include_archived": args.include_archived,
        "summary": {
            "checked": len(results),
            "ok": sum(1 for x in results if x["status"] == "OK"),
            "warn": len(warns),
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
        print(f"License consistency for {args.org}: "
              f"{payload['summary']['ok']} OK, {len(warns)} WARN, {len(errs)} ERROR "
              f"(of {len(results)} public repos checked)\n")
        for x in results:
            mark = {"OK": "\u2713", "WARN": "\u26a0", "ERROR": "\u2717"}[x["status"]]
            note = " [allowlisted]" if x["allowlisted"] else ""
            arch = " [archived]" if x["archived"] else ""
            print(f"  {mark} {x['repo']:24} detected={x['detected_spdx']}{note}{arch}")
            for e in x["errors"]:
                print(f"        ERROR: {e}")
            for w in x["warnings"]:
                print(f"        warn:  {w}")

    if errs:
        print(f"\n{len(errs)} repo(s) have license-claim drift. See above / report.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
