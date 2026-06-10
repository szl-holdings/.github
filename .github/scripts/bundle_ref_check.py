#!/usr/bin/env python3
"""Unpublished container/package reference checker for szl-holdings UDS bundles.

Task #546 class of drift: a PUBLIC deploy walkthrough (a UDS bundle YAML wired
into a README's "build / deploy / verify" steps) points `packages[].repository`
+ `ref` at a GHCR package/tag that was never published — e.g.
`ghcr.io/szl-holdings/packages/szl-receipts:0.3.1` (wrong org path, 403/404). So
`uds create` / `uds deploy` fail on the first package pull for anyone who follows
the public docs. Nothing in CI caught this; it was only found by manual probing.

For every `kind: UDSBundle` file (basename uds-bundle.yaml / .yml) this script
parses each package's `repository` + `ref` and probes the reference against the
GHCR registry API (anonymous bearer-token + manifest HEAD, with a GET confirm and
an authenticated retry for private packages). A package declared with a local
`path:` (a directory checkout, or an `oci://...`/path-style local ref) is SKIPPED
— only remote `repository:` + `ref:` pairs hit a registry.

Severity split (mirrors the org's public-repo-link guard, so introducing this
guard does not retroactively red every repo on an upstream's retag):

  * An SZL-OWNED ref (`ghcr.io/szl-holdings/...`) that is unreachable (a clean
    403/404) is an ERROR and FAILS the run. This is exactly the recurring bug
    class: SZL referencing its own package/tag that it never published.
  * An EXTERNAL ref (any other GHCR host — defenseunicorns, zarf-dev, …) that is
    unreachable is a WARNING (reported, does not fail) unless --fail-on-external
    is passed: upstreams retag / move / re-flavor on their own schedule and use
    arch/flavor tag conventions we do not control.
  * A NETWORK fault (timeout / DNS / 5xx / rate-limit — not a definitive 403/404)
    is always a WARNING and never fails the run, faithful to registry flakiness.

GHCR tag resolution is flavor/arch aware: the plain `ref` is tried first, then —
if the bundle declares a concrete `metadata.architecture` (or as a fallback) —
arch-suffixed variants (`<ref>-amd64`, `<ref>-arm64`), since UDS/Zarf publish and
pull arch-suffixed package tags. A ref is "reachable" if ANY candidate resolves.

Intentional exceptions live in .github/data/bundle_ref_allowlist.json — nothing
is silently passed; an un-listed unreachable owned ref fails the run.

Modes:
  (default)        Org sweep: list every PUBLIC repo in --org, find its bundle
                   YAMLs via the git tree API, read them raw, and probe.
  --local DIR      Scan a local checkout (the per-repo fail-fast reusable guard).
  --selftest       Probe a known-good ref (must be reachable) and the exact
                   known-bad Task #546 ref (must be unreachable); exit non-zero if
                   the probing logic itself is broken.

Auth: a GitHub token ($GITHUB_TOKEN / $GH_TOKEN / $SZL_GITHUB_TOKEN) is used for
the org listing / git-tree reads and, when present, to mint an authenticated GHCR
pull token for PRIVATE szl-holdings packages. Public packages probe anonymously.

Exit code 0 = no failing refs (allowlisted / warning ones excluded); 1 = at least
one failing ref (an owned unreachable ref, or an external one promoted by
--fail-on-external); 2 = usage / auth error.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
GHCR = "ghcr.io"
USER_AGENT = "szl-holdings-bundle-ref-check/1.0 (+https://github.com/szl-holdings/.github)"

MANIFEST_ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])

OWNED_PREFIX = "szl-holdings/"

# The exact pair from the Task #546 incident — the canary for --selftest.
SELFTEST_GOOD = "ghcr.io/szl-holdings/szl-receipts:0.4.0-upstream"
SELFTEST_BAD = "ghcr.io/szl-holdings/packages/szl-receipts:0.3.1"

BUNDLE_BASENAMES = {"uds-bundle.yaml", "uds-bundle.yml"}


# --------------------------------------------------------------------------- #
# Token / GitHub helpers
# --------------------------------------------------------------------------- #
def _token() -> str | None:
    for var in ("SZL_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(var)
        if v:
            return v
    return None


def _gh_json(path: str, token: str | None, retries: int = 4):
    url = path if path.startswith("http") else f"{API}{path}"
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", USER_AGENT)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8")), resp.headers
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (403, 429) and attempt < retries - 1:
                ra = e.headers.get("Retry-After")
                time.sleep(int(ra) if (ra and ra.isdigit()) else (2 ** attempt))
                continue
            if e.code >= 500 and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    if last:
        raise last
    raise RuntimeError("unreachable")


def list_public_repos(org: str, token: str | None, include_archived: bool):
    repos = []
    page = 1
    while True:
        data, _ = _gh_json(
            f"/orgs/{org}/repos?per_page=100&type=public&page={page}", token)
        if not data:
            break
        for r in data:
            if r.get("private"):
                continue
            if r.get("archived") and not include_archived:
                continue
            repos.append(r["name"])
        if len(data) < 100:
            break
        page += 1
    return sorted(repos)


def find_bundle_files(org: str, repo: str, token: str | None):
    """Return [(path, default_branch)] for every bundle YAML in repo's tree."""
    try:
        info, _ = _gh_json(f"/repos/{org}/{repo}", token)
    except urllib.error.HTTPError:
        return []
    branch = info.get("default_branch") or "main"
    try:
        tree, _ = _gh_json(
            f"/repos/{org}/{repo}/git/trees/{branch}?recursive=1", token)
    except urllib.error.HTTPError:
        return []
    out = []
    for node in tree.get("tree", []):
        if node.get("type") != "blob":
            continue
        path = node.get("path", "")
        if path.rsplit("/", 1)[-1] in BUNDLE_BASENAMES:
            out.append((path, branch))
    return out


def fetch_raw(org: str, repo: str, branch: str, path: str, token: str | None) -> str | None:
    url = f"https://raw.githubusercontent.com/{org}/{repo}/{branch}/{urllib.parse.quote(path)}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError:
        return None
    except (urllib.error.URLError, TimeoutError):
        return None


# --------------------------------------------------------------------------- #
# Bundle parsing
# --------------------------------------------------------------------------- #
def parse_bundle(text: str):
    """Return (architecture, [package dict]) for a UDSBundle, or (None, [])."""
    try:
        import yaml  # type: ignore
        doc = yaml.safe_load(text)
        if not isinstance(doc, dict) or doc.get("kind") != "UDSBundle":
            return None, []
        arch = ((doc.get("metadata") or {}).get("architecture")) or None
        pkgs = []
        for p in (doc.get("packages") or []):
            if not isinstance(p, dict):
                continue
            pkgs.append({
                "name": p.get("name"),
                "repository": p.get("repository"),
                "ref": p.get("ref"),
                "path": p.get("path"),
            })
        return arch, pkgs
    except ImportError:
        return _parse_bundle_fallback(text)


def _parse_bundle_fallback(text: str):
    """Stdlib-only parser for the regular UDSBundle layout (no PyYAML).

    Reads metadata.architecture and the top-level packages: list, capturing each
    item's name / repository / ref / path. Deeper-indented keys (overrides,
    variables, values) are ignored because they live below the package-key indent.
    """
    lines = text.splitlines()
    if not any(l.strip() == "kind: UDSBundle" or l.strip().startswith("kind: UDSBundle")
               for l in lines):
        return None, []

    def _val(s: str) -> str:
        s = s.strip()
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1]
        return s

    arch = None
    in_meta = False
    for l in lines:
        st = l.strip()
        if l.startswith("metadata:"):
            in_meta = True
            continue
        if in_meta:
            if l and not l[0].isspace():
                in_meta = False
            elif st.startswith("architecture:"):
                arch = _val(st.split(":", 1)[1]) or None
    pkgs = []
    in_pkgs = False
    pkgs_indent = None
    cur = None
    item_indent = None
    for raw in lines:
        if raw.strip() == "packages:" or raw.rstrip() == "packages:":
            in_pkgs = True
            pkgs_indent = len(raw) - len(raw.lstrip())
            continue
        if not in_pkgs:
            continue
        if raw.strip() == "" or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        # A new top-level key at/under packages indent ends the block.
        if indent <= pkgs_indent and not raw.lstrip().startswith("-"):
            break
        stripped = raw.strip()
        if stripped.startswith("- "):
            # new package item
            if cur is not None:
                pkgs.append(cur)
            cur = {"name": None, "repository": None, "ref": None, "path": None}
            item_indent = indent
            rest = stripped[2:].strip()
            if ":" in rest:
                k, _, v = rest.partition(":")
                if k.strip() in cur:
                    cur[k.strip()] = _val(v)
            continue
        if cur is not None and item_indent is not None and indent > item_indent:
            if ":" in stripped:
                k, _, v = stripped.partition(":")
                k = k.strip()
                if k in cur and cur[k] is None:
                    cur[k] = _val(v)
    if cur is not None:
        pkgs.append(cur)
    return arch, pkgs


# --------------------------------------------------------------------------- #
# GHCR probing
# --------------------------------------------------------------------------- #
def _ghcr_bearer(name: str, pat: str | None, timeout: int):
    url = (f"https://{GHCR}/token?service={GHCR}"
           f"&scope=repository:{urllib.parse.quote(name)}:pull")
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    if pat:
        basic = base64.b64encode(f"x:{pat}".encode()).decode()
        req.add_header("Authorization", f"Basic {basic}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8")).get("token", "")


def _manifest_status(name: str, tag: str, bearer: str, method: str, timeout: int) -> int:
    url = f"https://{GHCR}/v2/{name}/manifests/{urllib.parse.quote(tag)}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Accept", MANIFEST_ACCEPT)
    req.add_header("User-Agent", USER_AGENT)
    if bearer:
        req.add_header("Authorization", f"Bearer {bearer}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode()
    except urllib.error.HTTPError as e:
        return e.code


def probe_tag(name: str, tag: str, pat: str | None, timeout: int) -> tuple[str, int]:
    """Probe one repo:tag. Returns (state, http) where state is
    reachable / unreachable / network. Anonymous first; authenticated retry on
    401/403 when a PAT is available; HEAD then GET confirm before declaring 404.
    """
    try:
        bearer = _ghcr_bearer(name, None, timeout)
    except (urllib.error.URLError, TimeoutError, urllib.error.HTTPError):
        bearer = ""
    try:
        code = _manifest_status(name, tag, bearer, "HEAD", timeout)
        if code in (401, 403) and pat:
            try:
                bearer = _ghcr_bearer(name, pat, timeout)
                code = _manifest_status(name, tag, bearer, "HEAD", timeout)
            except (urllib.error.URLError, TimeoutError, urllib.error.HTTPError):
                pass
        # HEAD can be quirky on some registries — confirm a non-200 with GET.
        if code != 200:
            gcode = _manifest_status(name, tag, bearer, "GET", timeout)
            code = gcode
        if code == 200:
            return "reachable", 200
        if code in (401, 403, 404):
            return "unreachable", code
        return "network", code
    except (urllib.error.URLError, TimeoutError):
        return "network", 0


def probe_ref(repository: str, ref: str, arch: str | None, pat: str | None,
              timeout: int) -> dict:
    """Probe a repository+ref, flavor/arch aware. Only ghcr.io is probed."""
    repo = repository.strip()
    if repo.startswith("oci://"):
        repo = repo[len("oci://"):]
    host, _, name = repo.partition("/")
    if host != GHCR or not name:
        return {"state": "skipped-nonghcr", "http": None,
                "resolved_tag": None, "owned": False}
    owned = name.startswith(OWNED_PREFIX)
    candidates = [ref]
    if arch and arch not in ("multi", ""):
        candidates.append(f"{ref}-{arch}")
    else:
        candidates += [f"{ref}-amd64", f"{ref}-arm64"]
    last_state, last_http = "unreachable", 404
    for tag in candidates:
        state, http = probe_tag(name, tag, pat, timeout)
        if state == "reachable":
            return {"state": "reachable", "http": 200, "resolved_tag": tag,
                    "owned": owned}
        if state == "network":
            last_state, last_http = "network", http
        else:
            last_state, last_http = state, http
    return {"state": last_state, "http": last_http,
            "resolved_tag": None, "owned": owned}


# --------------------------------------------------------------------------- #
# Allowlist
# --------------------------------------------------------------------------- #
def load_allowlist(path: str | None):
    if not path or not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as fh:
        raw = fh.read().strip()
    if not raw:
        return set()
    data = json.loads(raw)
    out = set()
    for e in data.get("allow", []):
        if isinstance(e, str):
            out.add(e.strip())
        elif isinstance(e, dict):
            repo = (e.get("repository") or "").strip()
            ref = (e.get("ref") or "").strip()
            if e.get("match"):
                out.add(e["match"].strip())
            elif repo and ref:
                out.add(f"{repo}:{ref}")
    return out


# --------------------------------------------------------------------------- #
# Scan
# --------------------------------------------------------------------------- #
def scan_text(repo_label: str, bundle_path: str, text: str, pat: str | None,
              allow: set, timeout: int, results: list):
    arch, pkgs = parse_bundle(text)
    if not pkgs:
        return
    for p in pkgs:
        repository = p.get("repository")
        ref = p.get("ref")
        path = p.get("path")
        name = p.get("name")
        if not repository:
            # local checkout / path-style ref — skipped
            results.append({
                "repo": repo_label, "bundle": bundle_path, "package": name,
                "repository": None, "ref": ref, "path": path,
                "state": "skipped-local", "http": None, "resolved_tag": None,
                "owned": False, "severity": "ok",
            })
            continue
        if not ref:
            results.append({
                "repo": repo_label, "bundle": bundle_path, "package": name,
                "repository": repository, "ref": None, "path": path,
                "state": "skipped-no-ref", "http": None, "resolved_tag": None,
                "owned": False, "severity": "ok",
            })
            continue
        match = f"{repository}:{ref}"
        if match in allow:
            results.append({
                "repo": repo_label, "bundle": bundle_path, "package": name,
                "repository": repository, "ref": ref, "path": path,
                "state": "allowlisted", "http": None, "resolved_tag": None,
                "owned": repository.replace("oci://", "").startswith(f"{GHCR}/{OWNED_PREFIX}"),
                "severity": "ok",
            })
            continue
        pr = probe_ref(repository, ref, arch, pat, timeout)
        results.append({
            "repo": repo_label, "bundle": bundle_path, "package": name,
            "repository": repository, "ref": ref, "path": path,
            "state": pr["state"], "http": pr["http"],
            "resolved_tag": pr["resolved_tag"], "owned": pr["owned"],
            "severity": None,  # assigned later
        })


def assign_severity(results: list, fail_on_external: bool):
    for r in results:
        if r["severity"] == "ok":
            continue
        st = r["state"]
        if st == "reachable":
            r["severity"] = "ok"
        elif st in ("skipped-local", "skipped-no-ref", "skipped-nonghcr",
                    "allowlisted"):
            r["severity"] = "ok"
        elif st == "network":
            r["severity"] = "warn"
        elif st == "unreachable":
            if r["owned"]:
                r["severity"] = "error"
            else:
                r["severity"] = "error" if fail_on_external else "warn"
        else:
            r["severity"] = "warn"


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def annotate(results: list):
    for r in results:
        sev = r["severity"]
        if sev == "ok":
            continue
        loc = f"{r['repo']}:{r['bundle']}"
        msg = (f"{loc} package '{r.get('package')}' references "
               f"{r['repository']}:{r['ref']} which is unreachable on GHCR "
               f"(HTTP {r['http']}, state {r['state']}).")
        if sev == "error":
            if r["owned"]:
                msg += (" This is an SZL-owned package/tag that is not published "
                        "— publish it, fix the repository/ref, or (if intentional) "
                        "allowlist it in .github/data/bundle_ref_allowlist.json.")
            print(f"::error::{msg}")
        else:
            print(f"::warning::{msg}")


def write_report(path: str | None, org: str, results: list, mode: str):
    summary = {
        "bundles": len({(r["repo"], r["bundle"]) for r in results}),
        "refs_probed": sum(1 for r in results if r["state"] in (
            "reachable", "unreachable", "network")),
        "reachable": sum(1 for r in results if r["state"] == "reachable"),
        "unreachable_owned": sum(1 for r in results
                                 if r["state"] == "unreachable" and r["owned"]),
        "unreachable_external": sum(1 for r in results
                                    if r["state"] == "unreachable" and not r["owned"]),
        "network": sum(1 for r in results if r["state"] == "network"),
        "allowlisted": sum(1 for r in results if r["state"] == "allowlisted"),
        "skipped_local": sum(1 for r in results if r["state"] in (
            "skipped-local", "skipped-no-ref", "skipped-nonghcr")),
        "errors": sum(1 for r in results if r["severity"] == "error"),
        "warnings": sum(1 for r in results if r["severity"] == "warn"),
    }
    report = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "org": org,
        "mode": mode,
        "summary": summary,
        "results": sorted(results, key=lambda r: (r["repo"], r["bundle"],
                                                  str(r.get("package")))),
    }
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")
    return report


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #
def run_selftest(pat: str | None, timeout: int) -> int:
    print("Self-test: probing a known-good and the known-bad Task #546 ref.")
    good_repo, _, good_ref = SELFTEST_GOOD.rpartition(":")
    bad_repo, _, bad_ref = SELFTEST_BAD.rpartition(":")
    good = probe_ref(good_repo, good_ref, None, pat, timeout)
    bad = probe_ref(bad_repo, bad_ref, None, pat, timeout)
    ok_good = good["state"] == "reachable"
    ok_bad = bad["state"] == "unreachable"
    print(f"  known-good {SELFTEST_GOOD} -> state={good['state']} "
          f"http={good['http']} (expect reachable) "
          f"{'PASS' if ok_good else 'FAIL'}")
    print(f"  known-bad  {SELFTEST_BAD} -> state={bad['state']} "
          f"http={bad['http']} (expect unreachable) "
          f"{'PASS' if ok_bad else 'FAIL'}")
    if good["state"] == "network" or bad["state"] == "network":
        print("::warning::Self-test hit a network fault talking to GHCR; "
              "treating as inconclusive (not a probing-logic failure).")
        return 0
    if ok_good and ok_bad:
        print("✓ Self-test passed: the guard reaches a published ref and "
              "correctly flags the unpublished one.")
        return 0
    print("::error::Self-test FAILED: the GHCR probing logic is not "
          "distinguishing published from unpublished refs.")
    return 1


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--org", default="szl-holdings")
    ap.add_argument("--local", metavar="DIR",
                    help="Scan a local checkout instead of sweeping the org.")
    ap.add_argument("--allowlist",
                    default=".github/data/bundle_ref_allowlist.json")
    ap.add_argument("--report",
                    default=None,
                    help="Write the JSON report to this path.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--fail-on-external", action="store_true",
                    help="Promote unreachable EXTERNAL refs from warning to error.")
    ap.add_argument("--include-archived", action="store_true")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--json", action="store_true",
                    help="Print the JSON report to stdout.")
    args = ap.parse_args()

    pat = _token()

    if args.selftest:
        return run_selftest(pat, args.timeout)

    allow = load_allowlist(args.allowlist)
    results: list = []

    if args.local:
        root = os.path.abspath(args.local)
        found = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if d not in (".git", "node_modules")]
            for fn in filenames:
                if fn in BUNDLE_BASENAMES:
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, root)
                    with open(full, "r", encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                    found += 1
                    scan_text("(local)", rel, text, pat, allow, args.timeout,
                              results)
        print(f"Scanned {found} bundle file(s) under {root}.")
        mode = "local"
    else:
        if not pat:
            print("error: org sweep needs a GitHub token in "
                  "$SZL_GITHUB_TOKEN / $GH_TOKEN / $GITHUB_TOKEN.",
                  file=sys.stderr)
            return 2
        repos = list_public_repos(args.org, pat, args.include_archived)
        print(f"Sweeping {len(repos)} public repo(s) in {args.org}.")
        for repo in repos:
            for path, branch in find_bundle_files(args.org, repo, pat):
                text = fetch_raw(args.org, repo, branch, path, pat)
                if text is None:
                    continue
                scan_text(repo, path, text, pat, allow, args.timeout, results)
        mode = "org-sweep"

    assign_severity(results, args.fail_on_external)
    annotate(results)
    report = write_report(args.report, args.org, results, mode)

    s = report["summary"]
    print(
        f"\nBundles: {s['bundles']}  refs probed: {s['refs_probed']}  "
        f"reachable: {s['reachable']}  "
        f"unreachable(owned): {s['unreachable_owned']}  "
        f"unreachable(external): {s['unreachable_external']}  "
        f"network: {s['network']}  allowlisted: {s['allowlisted']}  "
        f"skipped(local): {s['skipped_local']}")
    print(f"Errors: {s['errors']}  Warnings: {s['warnings']}")

    if args.json:
        print(json.dumps(report, indent=2))

    if s["errors"] > 0:
        print("\n::error::One or more bundle package references are unreachable "
              "(see annotations above and the report).")
        return 1
    print("\n✓ No failing bundle package references "
          "(every owned repository/ref resolves on GHCR).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
