#!/usr/bin/env python3
"""Hugging Face license-claim consistency checker for the SZLHOLDINGS org.

The GitHub side is already guarded against issue #202-class drift (a repo's
public license claim disagreeing with its actual license) by
``license_consistency.py``. But the org also publishes Spaces, models and
datasets on Hugging Face (org ``SZLHOLDINGS``), where the license is declared in
each repo's README front-matter (the YAML block at the top of ``README.md``,
``license:``). Those HF declarations can drift from their GitHub counterpart
(e.g. the killinchu GitHub<->HF content fork) with no current guard. HF has no
PR CI like GitHub, so this runs on a schedule instead.

For every PUBLIC repo in the org (Spaces + models + datasets) it:
  1. Reads the README front-matter ``license:`` (and, for ``license: other``,
     the ``license_name`` / ``license_link`` pair) — the publicly-visible claim.
  2. Flags a missing front-matter ``license:`` as drift (HF requires/strongly
     expects it, and an unlicensed public artifact is exactly the silent-drift
     class we must catch) — unless the repo is allowlisted as license-optional.
  3. Cross-references the matching GitHub repo's *detected* SPDX id
     (``license.spdx_id`` — the truth from the actual LICENSE file) when a
     same-named ``szl-holdings`` GitHub repo exists and is readable, and flags a
     mismatch.

Intentional cases (org-card Spaces with no license, dual-licensed repos, name
mappings, deliberately HF-only repos) are explicitly allowlisted in
``hf_license_allowlist.json`` — nothing is silently "passed".

Auth:
  - HF token from $HF_ORG_TOKEN / $HF_TOKEN / $HF_WRITE_TOKEN (optional for
    public repos, but recommended to avoid rate limits and to list private).
  - GitHub token from $GITHUB_TOKEN / $GH_TOKEN / $SZL_GITHUB_TOKEN for the
    optional cross-reference (public repo metadata reads work with any token).

Usage:
  python hf_license_consistency.py [--org SZLHOLDINGS] \
      [--allowlist ../data/hf_license_allowlist.json] \
      [--report ../data/hf_license_consistency_report.json] \
      [--github-org szl-holdings] [--include-private] [--no-github] [--json]

Exit code 0 = all consistent (warnings allowed); 1 = at least one ERROR.
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

HF_API = "https://huggingface.co/api"
HF_HOST = "https://huggingface.co"
GH_API = "https://api.github.com"

# HF repo "kind" -> (api list path, raw-URL path prefix for README)
HF_KINDS = {
    "model": ("models", ""),
    "space": ("spaces", "spaces/"),
    "dataset": ("datasets", "datasets/"),
}


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #
def _hf_token() -> str | None:
    for var in ("HF_ORG_TOKEN", "HF_TOKEN", "HF_WRITE_TOKEN"):
        v = os.environ.get(var)
        if v:
            return v
    return None


def _gh_token() -> str | None:
    for var in ("GITHUB_TOKEN", "GH_TOKEN", "SZL_GITHUB_TOKEN"):
        v = os.environ.get(var)
        if v:
            return v
    return None


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _get_json(url: str, token: str | None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "szl-hf-license-consistency")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _get_text(url: str, token: str | None):
    """Return decoded text, or None on 404."""
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("User-Agent", "szl-hf-license-consistency")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def hf_whoami(token: str | None):
    """Return (ok, identity_dict, error_str).

    Used to PROVE an ``--include-private`` run actually holds a working token
    before we trust a "0 private drift" result. ``whoami-v2`` is the cheapest
    authenticated call HF offers; a 401/403 means the token is
    expired/revoked/rotated and cannot be trusted to unlock private listings.
    """
    if not token:
        return False, None, "no HF token present"
    url = f"{HF_API}/whoami-v2"
    try:
        return True, _get_json(url, token), None
    except urllib.error.HTTPError as e:
        return False, None, f"whoami-v2 returned HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 - any failure = untrustworthy token
        return False, None, f"whoami-v2 failed: {e}"


# --------------------------------------------------------------------------- #
# License-string normalization (shared canon with the GitHub checker)
# --------------------------------------------------------------------------- #
_CANON = [
    (re.compile(r"^apache(\s+license)?[\s_-]*2(\.0)?$"), "Apache-2.0"),
    (re.compile(r"^cc[\s_-]*by[\s_-]*sa[\s_-]*4(\.0)?$"), "CC-BY-SA-4.0"),
    (re.compile(r"^cc[\s_-]*by[\s_-]*nc[\s_-]*4(\.0)?$"), "CC-BY-NC-4.0"),
    (re.compile(r"^cc[\s_-]*by[\s_-]*4(\.0)?$"), "CC-BY-4.0"),
    (re.compile(r"^cc0[\s_-]*1?(\.0)?$"), "CC0-1.0"),
    (re.compile(r"^mit$"), "MIT"),
    (re.compile(r"^bsd[\s_-]*3([\s_-]*clause)?$"), "BSD-3-Clause"),
    (re.compile(r"^bsd[\s_-]*2([\s_-]*clause)?$"), "BSD-2-Clause"),
    (re.compile(r"^mpl[\s_-]*2(\.0)?$"), "MPL-2.0"),
    (re.compile(r"^gpl[\s_-]*v?3(\.0)?$"), "GPL-3.0"),
    (re.compile(r"^agpl[\s_-]*v?3(\.0)?$"), "AGPL-3.0"),
    (re.compile(r"^openrail([\s_-].*)?$"), "OpenRAIL"),
    (re.compile(r"^bigscience[\s_-]*openrail[\s_-]*m$"), "BigScience-OpenRAIL-M"),
    (re.compile(r"^llama2$"), "Llama-2"),
    (re.compile(r"^llama3(\.[0-9])?$"), "Llama-3"),
]


def normalize_license(raw: str | None) -> str:
    """Map any license string (HF tag, SPDX id, badge text, prose) to a canon."""
    if raw is None:
        return ""
    s = raw.strip()
    if not s:
        return ""
    low = s.lower()
    if "proprietary" in low or low.startswith("licenseref"):
        return "Proprietary"
    if low in ("other", "unknown"):
        return "OTHER"
    if low in ("noassertion",):
        return "NOASSERTION"
    if low in ("none", "no-license", "unlicensed"):
        return "NONE"
    cleaned = re.sub(r"[^a-z0-9.+\s_-]", "", low).strip()
    for rx, canon in _CANON:
        if rx.match(cleaned):
            return canon
    return s


# --------------------------------------------------------------------------- #
# Front-matter parsing
# --------------------------------------------------------------------------- #
_FRONTMATTER_RE = re.compile(r"^\ufeff?---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FM_LICENSE_RE = re.compile(r"^\s*license\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_FM_LICENSE_NAME_RE = re.compile(r"^\s*license_name\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_FM_LICENSE_LINK_RE = re.compile(r"^\s*license_link\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def _strip_quotes(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
        v = v[1:-1]
    return v.strip()


def parse_frontmatter_license(readme: str | None):
    """Return (license, license_name, license_link) from README front-matter.

    Each may be None if absent / no front-matter block at all.
    """
    if not readme:
        return None, None, None
    m = _FRONTMATTER_RE.match(readme)
    if not m:
        return None, None, None
    block = m.group(1)
    lic = _FM_LICENSE_RE.search(block)
    name = _FM_LICENSE_NAME_RE.search(block)
    link = _FM_LICENSE_LINK_RE.search(block)
    return (
        _strip_quotes(lic.group(1)) if lic else None,
        _strip_quotes(name.group(1)) if name else None,
        _strip_quotes(link.group(1)) if link else None,
    )


# --------------------------------------------------------------------------- #
# HF listing
# --------------------------------------------------------------------------- #
def list_hf_repos(org: str, token: str | None, include_private: bool):
    """Return ``(repos, list_errors)``.

    ``list_errors`` is non-empty if any HF "kind" listing call failed outright.
    A failed listing silently drops a whole class of repos from the sweep, so it
    must surface as loud drift — not a quietly smaller (still-green) result set.
    """
    repos = []
    list_errors = []
    for kind, (api_path, _) in HF_KINDS.items():
        url = f"{HF_API}/{api_path}?author={urllib.parse.quote(org)}&limit=1000"
        try:
            data = _get_json(url, token)
        except urllib.error.HTTPError as e:
            list_errors.append(f"failed to list HF {api_path}: HTTP {e.code}")
            continue
        except Exception as e:  # noqa: BLE001 - a dropped kind must be loud
            list_errors.append(f"failed to list HF {api_path}: {e}")
            continue
        for x in data:
            if x.get("private") and not include_private:
                continue
            repos.append({
                "id": x["id"],
                "name": x["id"].split("/", 1)[-1],
                "kind": kind,
                "private": bool(x.get("private")),
            })
    return sorted(repos, key=lambda r: (r["kind"], r["name"].lower())), list_errors


def hf_readme(repo, token: str | None):
    prefix = HF_KINDS[repo["kind"]][1]
    url = f"{HF_HOST}/{prefix}{repo['id']}/raw/main/README.md"
    return _get_text(url, token)


# --------------------------------------------------------------------------- #
# GitHub cross-reference
# --------------------------------------------------------------------------- #
_gh_cache: dict[str, object] = {}


def github_spdx(gh_org: str, repo_name: str, token: str | None):
    """Return (spdx_id_or_None, found_bool). found=False means no readable repo."""
    if not token:
        return None, False
    key = f"{gh_org}/{repo_name}"
    if key in _gh_cache:
        return _gh_cache[key]  # type: ignore[return-value]
    url = f"{GH_API}/repos/{gh_org}/{repo_name}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "szl-hf-license-consistency")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            d = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code in (404, 403):
            _gh_cache[key] = (None, False)
            return None, False
        raise
    spdx = (d.get("license") or {}).get("spdx_id")
    if spdx in (None, "NOASSERTION", "NONE"):
        # A NOASSERTION/none GitHub side is not a usable cross-reference truth.
        res = (spdx, True)
    else:
        res = (spdx, True)
    _gh_cache[key] = res
    return res


# --------------------------------------------------------------------------- #
# Per-repo check
# --------------------------------------------------------------------------- #
def check_repo(repo, allow_entry, gh_org, gh_token, use_github):
    readme = hf_readme(repo, _hf_token())
    fm_license, fm_name, fm_link = parse_frontmatter_license(readme)

    claimed_norm = normalize_license(fm_license)
    errors, warnings, notes = [], [], []

    license_optional = bool((allow_entry or {}).get("license_optional"))
    expected = (allow_entry or {}).get("expected_spdx")
    allowed = set()
    if expected:
        allowed.add(normalize_license(expected))
    for c in (allow_entry or {}).get("allowed_claims", []):
        allowed.add(normalize_license(c))
    allowed.discard("")

    # 1. Front-matter license present?
    if readme is None:
        if not license_optional:
            errors.append("README.md not found on main (cannot read license front-matter)")
        else:
            notes.append("no README (allowlisted as license-optional)")
    elif not fm_license:
        if not license_optional:
            errors.append("no 'license:' in README front-matter")
        else:
            notes.append("no license front-matter (allowlisted as license-optional)")
    else:
        # 1b. license: other must carry a name/link
        if claimed_norm == "OTHER" and not (fm_name or fm_link):
            errors.append("front-matter 'license: other' without license_name/license_link")

    # 2. Cross-reference the matching GitHub repo's detected SPDX.
    gh_spdx = None
    gh_found = False
    if use_github and gh_token:
        # Allowlist may pin the GitHub repo name, or disable cross-ref with false/null.
        gh_repo_name = (allow_entry or {}).get("github_repo", repo["name"]) \
            if allow_entry is not None else repo["name"]
        if gh_repo_name in (None, False, ""):
            notes.append("github cross-ref disabled by allowlist")
        else:
            gh_spdx, gh_found = github_spdx(gh_org, gh_repo_name, gh_token)
            if gh_found and gh_spdx and gh_spdx not in ("NOASSERTION", "NONE"):
                gh_norm = normalize_license(gh_spdx)
                # The HF claim must equal the GitHub SPDX, or be in allowed_claims,
                # or (if allowlisted) match the expected_spdx override.
                ok_set = set(allowed)
                ok_set.add(gh_norm)
                if fm_license and claimed_norm not in ok_set:
                    errors.append(
                        f"HF license '{fm_license}' (={claimed_norm}) != GitHub "
                        f"{gh_org}/{gh_repo_name} SPDX '{gh_spdx}' (={gh_norm}); "
                        f"allowed={sorted(ok_set)}")
            elif gh_found:
                notes.append(f"GitHub {gh_org}/{gh_repo_name} has no detectable SPDX "
                             f"(spdx={gh_spdx}); cross-ref skipped")
            else:
                notes.append("no matching GitHub repo (cross-ref skipped)")

    # 3. If allowlist pins expected_spdx and the HF claim disagrees with it.
    if expected and fm_license:
        if claimed_norm not in allowed:
            errors.append(f"HF license '{fm_license}' (={claimed_norm}) not in "
                          f"allowlisted expected/allowed {sorted(allowed)}")

    status = "ERROR" if errors else ("WARN" if warnings else "OK")
    return {
        "repo": repo["id"],
        "kind": repo["kind"],
        "private": repo["private"],
        "hf_license": fm_license,
        "hf_license_norm": claimed_norm or None,
        "hf_license_name": fm_name,
        "github_spdx": gh_spdx if gh_found else None,
        "allowlisted": bool(allow_entry),
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "notes": notes,
    }


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="SZLHOLDINGS HF license-claim consistency checker.")
    ap.add_argument("--org", default="SZLHOLDINGS")
    ap.add_argument("--github-org", default="szl-holdings")
    ap.add_argument("--allowlist", default=os.path.join(
        os.path.dirname(__file__), "..", "data", "hf_license_allowlist.json"))
    ap.add_argument("--report", help="Write the full JSON report to this path.")
    ap.add_argument("--include-private", action="store_true",
                    help="Also check private HF repos (needs a token with access).")
    ap.add_argument("--min-private", type=int, default=1,
                    help="With --include-private, require at least this many private "
                         "repos in the HF listing. This proves the token actually "
                         "unlocked private repos before a '0 drift' result is "
                         "trusted; set 0 to disable the empirical floor (default: 1).")
    ap.add_argument("--no-github", action="store_true",
                    help="Skip the GitHub SPDX cross-reference.")
    ap.add_argument("--json", action="store_true", help="Print the JSON report to stdout.")
    args = ap.parse_args()

    allow = {}
    if args.allowlist and os.path.exists(args.allowlist):
        with open(args.allowlist, "r", encoding="utf-8") as fh:
            allow = json.load(fh)
    allow_repos = allow.get("repos", {})
    ignore_repos = set(allow.get("ignore_repos", []))

    hf_token = _hf_token()
    gh_token = _gh_token()
    use_github = not args.no_github

    # --------------------------------------------------------------------- #
    # Preflight: when --include-private is requested, PROVE the token actually
    # unlocks private listings BEFORE trusting the result. Otherwise the HF API
    # silently returns only PUBLIC repos and the whole sweep reports a false
    # "0 drift" while private coverage has quietly vanished. Any failure here is
    # loud (the job goes red).
    # --------------------------------------------------------------------- #
    preflight_errors: list[str] = []
    if args.include_private:
        if not hf_token:
            preflight_errors.append(
                "--include-private was requested but no HF token "
                "(HF_ORG_TOKEN / HF_TOKEN / HF_WRITE_TOKEN) is set. The HF API "
                "would silently list only PUBLIC repos, dropping ALL private "
                "coverage while still reporting green.")
        else:
            ok, who, err = hf_whoami(hf_token)
            if not ok:
                preflight_errors.append(
                    f"--include-private was requested but the HF token failed "
                    f"validation ({err}); it cannot be trusted to unlock private "
                    f"listings (likely expired / revoked / rotated).")
            else:
                whoami_name = who.get("name")
                orgs = {(o.get("name") or "").lower()
                        for o in (who.get("orgs") or []) if isinstance(o, dict)}
                target = args.org.lower()
                # A user token must belong to the org; an org token's own name is
                # the org. If whoami exposes no orgs list at all, fall back to the
                # empirical min-private floor below rather than false-failing.
                if orgs and target not in orgs and (whoami_name or "").lower() != target:
                    # The persisted message stays PII-free (the report JSON is
                    # committed to a public repo); the token identity and the
                    # visible-org list go to stderr only, for live debugging.
                    preflight_errors.append(
                        f"HF token has no access to org '{args.org}'; its private "
                        f"repos cannot be listed (see job log for token identity).")
                    print(f"  [preflight] token identity '{whoami_name}' visible "
                          f"orgs={sorted(orgs)} (expected '{args.org}')",
                          file=sys.stderr)

    repos, list_errors = list_hf_repos(args.org, hf_token, args.include_private)
    preflight_errors.extend(list_errors)

    private_seen = sum(1 for r in repos if r.get("private"))
    if (args.include_private and args.min_private > 0
            and not preflight_errors and private_seen < args.min_private):
        preflight_errors.append(
            f"--include-private is on and the token validated, but the listing "
            f"returned only {private_seen} private repo(s) (expected at least "
            f"{args.min_private}). Private coverage appears to have silently "
            f"dropped to public-only — refusing to trust this result.")

    results = []
    for r in repos:
        if r["id"] in ignore_repos or r["name"] in ignore_repos:
            continue
        # allowlist key may be full id ("SZLHOLDINGS/foo") or bare name ("foo").
        entry = allow_repos.get(r["id"], allow_repos.get(r["name"]))
        results.append(check_repo(r, entry, args.github_org, gh_token, use_github))

    errs = [x for x in results if x["status"] == "ERROR"]
    warns = [x for x in results if x["status"] == "WARN"]
    payload = {
        "schema": "szl.hf_license_consistency/v1",
        "org": args.org,
        "github_org": args.github_org,
        "checked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "include_private": args.include_private,
        "private_repos_seen": private_seen,
        "min_private": args.min_private if args.include_private else None,
        "hf_token_present": bool(hf_token),
        "preflight_ok": not preflight_errors,
        "preflight_errors": preflight_errors,
        "github_crossref": use_github and bool(gh_token),
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
        xref = "on" if payload["github_crossref"] else "off"
        if args.include_private:
            print(f"private coverage: {private_seen} private repo(s) listed "
                  f"(HF token {'present' if hf_token else 'MISSING'}, "
                  f"floor={args.min_private})\n")
        print(f"HF license consistency for {args.org} (GitHub cross-ref: {xref}): "
              f"{payload['summary']['ok']} OK, {len(warns)} WARN, {len(errs)} ERROR "
              f"(of {len(results)} repos checked)\n")
        for x in results:
            mark = {"OK": "\u2713", "WARN": "\u26a0", "ERROR": "\u2717"}[x["status"]]
            note = " [allowlisted]" if x["allowlisted"] else ""
            priv = " [private]" if x["private"] else ""
            gh = f" gh={x['github_spdx']}" if x["github_spdx"] else ""
            print(f"  {mark} {x['kind']:7} {x['repo']:42} hf={x['hf_license']}{gh}{note}{priv}")
            for e in x["errors"]:
                print(f"        ERROR: {e}")
            for w in x["warnings"]:
                print(f"        warn:  {w}")

    if preflight_errors:
        print("\n\u2717 PREFLIGHT FAILURE — private HF coverage cannot be trusted:",
              file=sys.stderr)
        for e in preflight_errors:
            print(f"    \u2717 {e}", file=sys.stderr)
        print("  A '0 drift' result is meaningless without verified private "
              "coverage; failing loudly instead of reporting a false green.",
              file=sys.stderr)

    if errs:
        print(f"\n{len(errs)} HF repo(s) have license-claim drift. See above / report.",
              file=sys.stderr)

    if errs or preflight_errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
