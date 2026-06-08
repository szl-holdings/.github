#!/usr/bin/env python3
"""Public→private/dead repo-link checker for the szl-holdings org.

Task #186 / #236 class of drift: a PUBLIC trust surface (a README or docs page)
links to `github.com/szl-holdings/<repo>` for a repo that is currently PRIVATE
or has been deleted — so the link 404s for an anonymous visitor. This happened
when `lutar-lean` was made private (it left dead click-throughs in the public
`docs-site` and `szl-cookbook` READMEs); it was only luck that a later
re-opening flipped `lutar-lean` back to public before anyone hit the dead link.
The org changes repo visibility fairly often, so this class recurs on every
visibility flip. For a company whose thesis is provable honesty, a public page
that links to a 404 must never ship silently.

For every PUBLIC repo in the org this script scans its README (and, with
--scan-docs, every tracked Markdown file) for hyperlinks whose target is
`github.com/szl-holdings/<repo>`, and flags any target that is currently
PRIVATE or MISSING (deleted / typo'd — i.e. would 404 for an anonymous
visitor). The org's own repo listing (read with a token that sees private repos)
is the source of truth for what is private vs. missing vs. publicly reachable.

Only CLICK-THROUGH link targets are checked. shields.io / image-badge URLs are
deliberately ignored: a badge IMAGE such as
`https://img.shields.io/github/license/szl-holdings/a11oy` or
`https://github.com/szl-holdings/a11oy/actions/.../badge.svg` is not a link a
visitor clicks, so it is never flagged (no false positives on badges).

Intentional cases (a public page that knowingly references a private repo) are
explicitly allowlisted in .github/data/public_repo_link_allowlist.json — nothing
is silently "passed"; un-listed drift fails the job.

Auth: reads a GitHub token from $GITHUB_TOKEN / $GH_TOKEN / $SZL_GITHUB_TOKEN.
The built-in $GITHUB_TOKEN is enough to read public repo contents; to know which
targets are PRIVATE (rather than merely missing) the listing must be read with a
token that can see the org's private repos (e.g. $SZL_GITHUB_TOKEN). When only a
public token is available, private targets are reported as MISSING instead —
still a flagged dead link, just labelled less precisely.

Usage:
  python public_repo_link_check.py [--org szl-holdings] \
      [--allowlist .github/data/public_repo_link_allowlist.json] \
      [--report .github/data/public_repo_link_report.json] \
      [--scan-docs] [--max-doc-files 200] [--include-archived] [--json]

Exit code 0 = no dead links (allowlisted ones excluded); 1 = at least one dead
public→private/missing link.
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
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
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


def _gh(path: str, token: str, retries: int = 4):
    """GET a GitHub API path as JSON, retrying transient failures.

    4xx other than rate-limit are raised immediately (the caller maps 404/409).
    Transient faults -- connection errors, timeouts, 5xx, and secondary
    rate-limit (403/429 with Retry-After) -- are retried with backoff so one
    flaky file fetch can't abort an otherwise-clean parallel scan.
    """
    req = urllib.request.Request(API + path)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            # 403/429 from GitHub here is almost always primary/secondary rate
            # limiting (the token is org-owner, so true permission denials are
            # not expected); honour Retry-After / x-ratelimit-reset, else back off.
            rate_limited = e.code in (403, 429)
            transient = rate_limited or e.code in (500, 502, 503, 504)
            if not transient or attempt == retries:
                raise
            wait = e.headers.get("Retry-After")
            reset = e.headers.get("X-RateLimit-Reset")
            remaining = e.headers.get("X-RateLimit-Remaining")
            if wait and wait.isdigit():
                delay = float(wait)
            elif rate_limited and remaining == "0" and reset and reset.isdigit():
                delay = max(1.0, float(reset) - time.time()) + 1
            else:
                delay = 2 ** attempt
            last = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == retries:
                raise
            delay = 2 ** attempt
            last = e
        time.sleep(min(delay, 20))
    raise last  # pragma: no cover


def _gh_text(full_name: str, path: str, token: str):
    """Return decoded file contents, or None if the file is absent (404)."""
    try:
        r = _gh(f"/repos/{full_name}/contents/{urllib.parse.quote(path)}", token)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if isinstance(r, dict) and r.get("content"):
        return base64.b64decode(r["content"]).decode("utf-8", "replace")
    return None


RAW = "https://raw.githubusercontent.com"


def _raw_text(full_name: str, branch: str, path: str, token: str,
              retries: int = 4):
    """Fetch a public repo file from raw.githubusercontent.com.

    We only ever scan PUBLIC repos' pages, so the raw host serves them without
    counting against the API's (low) secondary rate limit -- this is what keeps
    a multi-hundred-file doc scan from tripping 403s. Falls back to the contents
    API on a non-404 raw failure. Returns None when the file is absent.
    """
    url = f"{RAW}/{full_name}/{urllib.parse.quote(branch)}/" \
          f"{urllib.parse.quote(path)}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + token)  # raises raw limits
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (403, 429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(min(2 ** attempt, 20))
                continue
            return _gh_text(full_name, path, token)  # last-resort fallback
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == retries:
                return _gh_text(full_name, path, token)
            time.sleep(min(2 ** attempt, 20))
    return None


def list_all_repos(org: str, token: str):
    """Every repo in the org (public + private + archived), as full objects."""
    repos, page = [], 1
    while True:
        batch = _gh(f"/orgs/{org}/repos?per_page=100&page={page}&type=all", token)
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return repos


def _is_doc_page(path: str) -> bool:
    """A README (any dir) or a page under a docs/ directory -- the public
    trust surfaces a visitor actually reads. Excludes incidental Markdown such
    as ops payloads, recipes and audit dumps that aren't documentation."""
    low = path.lower()
    base = low.rsplit("/", 1)[-1]
    if base in ("readme.md", "readme.markdown", "readme.mdx"):
        return True
    segs = low.split("/")
    return any(s in ("docs", "doc") for s in segs[:-1])


def list_markdown_paths(full_name: str, default_branch: str, token: str,
                        cap: int, doc_only: bool):
    """Return tracked Markdown file paths via the recursive git tree (capped).

    When doc_only is True (the default scan), only README files and docs/ pages
    are returned -- faithful to the task's "README/docs" scope. With doc_only
    False every tracked Markdown file is scanned.
    """
    try:
        tree = _gh(
            f"/repos/{full_name}/git/trees/"
            f"{urllib.parse.quote(default_branch)}?recursive=1", token)
    except urllib.error.HTTPError as e:
        if e.code in (404, 409):  # empty repo / missing branch
            return []
        raise
    out = []
    for node in tree.get("tree", []):
        if node.get("type") != "blob":
            continue
        p = node.get("path", "")
        low = p.lower()
        if not low.endswith((".md", ".markdown", ".mdx")):
            continue
        if doc_only and not _is_doc_page(p):
            continue
        out.append(p)
    out.sort()
    return out[:cap]


# --------------------------------------------------------------------------- #
# Link extraction
# --------------------------------------------------------------------------- #
_ORG_LINK_RE = re.compile(
    r"github\.com/szl-holdings/([A-Za-z0-9._-]+)", re.IGNORECASE)

# Image references whose URL must be IGNORED (badges, screenshots, etc.).
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\s*<?([^)>\s]+)", re.DOTALL)
_HTML_IMG_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']?([^\"'\s>]+)", re.IGNORECASE)

# Click-through link targets we DO check.
# Nested badge form `[![alt](image)](click-target)`: capture the OUTER click
# target (the image src is handled by _MD_IMAGE_RE and excluded). This is the
# single most common way a README links a repo behind a shields/CI badge.
_MD_IMG_LINK_RE = re.compile(
    r"\[!\[[^\]]*\]\([^)\s]*\)\]\(\s*<?([^)>\s]+)", re.DOTALL)
_MD_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(\s*<?([^)>\s]+)>?", re.DOTALL)
_HTML_A_RE = re.compile(r"<a\b[^>]*?\bhref\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>", re.IGNORECASE)
_BARE_URL_RE = re.compile(
    r"(?<![\(<\"'=])\bhttps?://github\.com/szl-holdings/[^\s)\]<>\"'`]+",
    re.IGNORECASE)


def _repo_from_url(url: str):
    """Extract the szl-holdings repo name a URL points at, or None."""
    m = _ORG_LINK_RE.search(url)
    if not m:
        return None
    repo = m.group(1)
    if repo.lower().endswith(".git"):
        repo = repo[:-4]
    repo = repo.rstrip(".")
    return repo or None


def extract_link_targets(text: str):
    """Return [(repo_name, raw_url)] for click-through org links in `text`.

    Image / badge URLs are excluded so shields.io badges and github actions
    badge SVGs never count as click-throughs.
    """
    if not text:
        return []

    image_urls = set()
    for m in _MD_IMAGE_RE.finditer(text):
        image_urls.add(m.group(1).strip())
    for m in _HTML_IMG_RE.finditer(text):
        image_urls.add(m.group(1).strip())

    candidates = []
    for rx in (_MD_IMG_LINK_RE, _MD_LINK_RE, _HTML_A_RE, _AUTOLINK_RE):
        for m in rx.finditer(text):
            candidates.append(m.group(1).strip())
    for m in _BARE_URL_RE.finditer(text):
        candidates.append(m.group(0).strip())

    seen = set()
    out = []
    for url in candidates:
        if url in image_urls:
            continue  # it's an image src, not a click-through
        repo = _repo_from_url(url)
        if not repo:
            continue
        key = (repo, url)
        if key in seen:
            continue
        seen.add(key)
        out.append((repo, url))
    return out


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(
        description="szl-holdings public→private/dead repo-link checker.")
    ap.add_argument("--org", default="szl-holdings")
    ap.add_argument("--allowlist", default=os.path.join(
        os.path.dirname(__file__), "..", "data", "public_repo_link_allowlist.json"))
    ap.add_argument("--report", help="Write the full JSON report to this path.")
    ap.add_argument("--scan-docs", action="store_true",
                    help="Also scan docs pages (README files in any dir + docs/ "
                         "pages), not just the root README.")
    ap.add_argument("--all-markdown", action="store_true",
                    help="With --scan-docs, scan EVERY tracked Markdown file "
                         "(not just README/docs trust surfaces).")
    ap.add_argument("--max-doc-files", type=int, default=400,
                    help="Cap on Markdown files scanned per repo (with --scan-docs).")
    ap.add_argument("--include-archived", action="store_true",
                    help="Also scan archived public repos' pages.")
    ap.add_argument("--fail-on-missing", action="store_true",
                    help="Also fail the job on links to deleted/missing repos "
                         "(default: only links to PRIVATE repos fail; missing "
                         "ones are surfaced as warnings).")
    ap.add_argument("--json", action="store_true", help="Print the JSON report to stdout.")
    args = ap.parse_args()

    token = _token()

    allow = {}
    if args.allowlist and os.path.exists(args.allowlist):
        with open(args.allowlist, "r", encoding="utf-8") as fh:
            allow = json.load(fh)
    allow_pairs = {(p.get("source_repo"), p.get("target"))
                   for p in allow.get("allow", [])}
    ignore_targets = set(allow.get("ignore_targets", []))
    ignore_source_repos = set(allow.get("ignore_source_repos", []))

    all_repos = list_all_repos(args.org, token)
    existing_names = {r["name"] for r in all_repos}
    private_names = {r["name"] for r in all_repos if r.get("private")}
    # Repos to scan: public ones (optionally including archived).
    scan_repos = sorted(
        (r for r in all_repos
         if not r.get("private")
         and (args.include_archived or not r.get("archived"))
         and r["name"] not in ignore_source_repos),
        key=lambda r: r["name"])

    # Resolve the Markdown pages to scan per repo (parallel tree reads).
    def _paths_for(repo):
        if args.scan_docs:
            paths = list_markdown_paths(
                repo["full_name"], repo.get("default_branch") or "main",
                token, args.max_doc_files, doc_only=not args.all_markdown)
            if "README.md" not in paths:
                paths = ["README.md"] + paths
            return paths
        return ["README.md"]

    with ThreadPoolExecutor(max_workers=8) as ex:
        repo_paths = dict(zip(
            (r["name"] for r in scan_repos),
            ex.map(_paths_for, scan_repos)))

    # Fetch every (repo, page) body in parallel.
    fetch_jobs = [(r, p) for r in scan_repos for p in repo_paths[r["name"]]]

    def _fetch(job):
        repo, path = job
        branch = repo.get("default_branch") or "main"
        return repo["name"], path, _raw_text(
            repo["full_name"], branch, path, token)

    with ThreadPoolExecutor(max_workers=8) as ex:
        fetched = list(ex.map(_fetch, fetch_jobs))

    pages_by_repo = {}
    for rname, path, text in fetched:
        if text is not None:
            pages_by_repo.setdefault(rname, []).append((path, text))

    results = []
    for repo in scan_repos:
        name = repo["name"]

        findings = []
        pages = sorted(pages_by_repo.get(name, []))
        pages_scanned = len(pages)
        for path, text in pages:
            for target, url in extract_link_targets(text):
                if target == name:
                    continue  # self-link is always reachable (this repo is public)
                if target in private_names:
                    kind = "private"
                elif target not in existing_names:
                    kind = "missing"
                else:
                    continue  # target is a reachable public repo
                allowlisted = (
                    target in ignore_targets
                    or (name, target) in allow_pairs)
                findings.append({
                    "page": path,
                    "target_repo": target,
                    "kind": kind,
                    "url": url,
                    "allowlisted": allowlisted,
                })

        # A finding "fails the job" when it's a non-allowlisted link to a PRIVATE
        # repo (the exact visibility-flip incident this guard exists for), or any
        # non-allowlisted dead link when --fail-on-missing is set. Links to
        # deleted/missing repos are otherwise surfaced as warnings (still a 404,
        # but a pre-existing backlog rather than the recurring flip trigger).
        for f in findings:
            f["fails"] = (not f["allowlisted"]) and (
                f["kind"] == "private" or args.fail_on_missing)
        failing = [f for f in findings if f["fails"]]
        warned = [f for f in findings
                  if not f["allowlisted"] and not f["fails"]]
        status = "ERROR" if failing else ("WARN" if warned else "OK")
        results.append({
            "repo": name,
            "archived": repo.get("archived", False),
            "pages_scanned": pages_scanned,
            "findings": findings,
            "status": status,
        })

    errs = [x for x in results if x["status"] == "ERROR"]
    warns = [x for x in results if x["status"] == "WARN"]
    all_findings = [f for x in results for f in x["findings"]]
    total_failing = sum(1 for f in all_findings if f["fails"])
    total_private = sum(1 for f in all_findings
                        if f["kind"] == "private" and not f["allowlisted"])
    total_missing = sum(1 for f in all_findings
                        if f["kind"] == "missing" and not f["allowlisted"])
    total_allowlisted = sum(1 for f in all_findings if f["allowlisted"])
    payload = {
        "schema": "szl.public_repo_link_check/v1",
        "org": args.org,
        "checked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scan_docs": args.scan_docs,
        "scan_scope": ("all-markdown" if (args.scan_docs and args.all_markdown)
                       else "readme+docs" if args.scan_docs else "readme-only"),
        "include_archived": args.include_archived,
        "fail_on_missing": args.fail_on_missing,
        "private_repos": sorted(private_names),
        "summary": {
            "repos_scanned": len(results),
            "ok": sum(1 for x in results if x["status"] == "OK"),
            "warn": len(warns),
            "error": len(errs),
            "links_to_private": total_private,
            "links_to_missing": total_missing,
            "failing_links": total_failing,
            "allowlisted_links": total_allowlisted,
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
        s = payload["summary"]
        print(f"Public repo-link check for {args.org}: "
              f"{s['ok']} OK, {s['warn']} WARN, {s['error']} ERROR across "
              f"{s['repos_scanned']} public repos "
              f"({s['links_to_private']} link(s) to PRIVATE, "
              f"{s['links_to_missing']} to MISSING, "
              f"{s['allowlisted_links']} allowlisted)\n")
        for x in results:
            if not x["findings"]:
                continue
            mark = {"ERROR": "\u2717", "WARN": "\u26a0", "OK": "\u2713"}[x["status"]]
            arch = " [archived]" if x["archived"] else ""
            print(f"  {mark} {x['repo']}{arch}")
            for f in x["findings"]:
                tag = " [allowlisted]" if f["allowlisted"] else ""
                # GitHub Actions annotation: error for failing, warning for the rest.
                if f["fails"]:
                    level = "error"
                elif not f["allowlisted"]:
                    level = "warning"
                else:
                    level = None
                if level:
                    print(f"::{level} file={x['repo']}/{f['page']}::"
                          f"{x['repo']}/{f['page']} links to "
                          f"{args.org}/{f['target_repo']} which is {f['kind']} "
                          f"(404 for anonymous visitors): {f['url']}")
                print(f"        {f['kind'].upper()}{tag}: {f['page']} -> "
                      f"{args.org}/{f['target_repo']}  ({f['url']})")

    if errs:
        print(f"\n{total_failing} public page link(s) point at a "
              f"{'private/deleted' if args.fail_on_missing else 'PRIVATE'} repo "
              f"(404 for anonymous visitors) across {len(errs)} repo(s). "
              f"See above / report.", file=sys.stderr)
        return 1
    if warns:
        print(f"\n\u2713 No public page links to a PRIVATE repo. "
              f"({total_missing} link(s) to deleted/missing repos surfaced as "
              f"warnings -- see the report.)")
        return 0
    print("\n\u2713 No public page links to a private or deleted szl-holdings repo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
