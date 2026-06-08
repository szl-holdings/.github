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

Beyond that org-repo-existence check, two OPTIONAL deeper modes catch link rot
that a repo-existence check can't see (both off by default so the fast scan is
unchanged):

  --check-deep-links
      HEAD-check DEEP links into LIVE (public, existing) org repos —
      `…/<repo>/blob/<ref>/<file>`, `…/tree/…`, `…/releases/tag/<tag>`,
      `…/issues/<n>`, `…/pull/<n>`, `…/commit/<sha>`, etc. The repo is public so
      the root link passes, but the deep path can still 404 (a renamed/deleted
      doc, a dead release tag, a deleted issue). A 404 here is surfaced as a WARN
      by default (pre-existing rot is a backlog, like missing-repo links), or an
      ERROR with --fail-on-deep. When a deep blob link to a Markdown file carries
      a `#fragment`, the target file's headings are read and the anchor is
      verified too (a renamed heading is a WARN, or ERROR with --fail-on-anchor).

  --check-external
      Liveness-check EXTERNAL click-through URLs (any http(s) link that is not a
      szl-holdings repo link — other GitHub orgs, gists, arXiv, vendor docs,
      etc.). Requests are HEAD-first (GET fallback), per-host rate-limited, and
      de-duplicated. A definitive 404/410 is surfaced as a WARN (external sites
      rot and flake, so it never fails the job unless --fail-on-external);
      timeouts / DNS failures / 5xx are reported as "unreachable" WARNINGS and
      never fail. Hosts/URLs/patterns can be allowlisted (see the allowlist).

Only CLICK-THROUGH link targets are checked. shields.io / image-badge URLs are
deliberately ignored: a badge IMAGE such as
`https://img.shields.io/github/license/szl-holdings/a11oy` or
`https://github.com/szl-holdings/a11oy/actions/.../badge.svg` is not a link a
visitor clicks, so it is never flagged (no false positives on badges).

Intentional cases (a public page that knowingly references a private repo, or a
known-flaky external host) are explicitly allowlisted in
.github/data/public_repo_link_allowlist.json — nothing is silently "passed";
un-listed drift fails the job (per the severity rules above).

Auth: reads a GitHub token from $GITHUB_TOKEN / $GH_TOKEN / $SZL_GITHUB_TOKEN.
The built-in $GITHUB_TOKEN is enough to read public repo contents; to know which
targets are PRIVATE (rather than merely missing) the listing must be read with a
token that can see the org's private repos (e.g. $SZL_GITHUB_TOKEN). When only a
public token is available, private targets are reported as MISSING instead —
still a flagged dead link, just labelled less precisely. Deep-link and external
liveness checks are made ANONYMOUSLY (faithful to what a visitor hits) and do
not consume the token.

Usage:
  python public_repo_link_check.py [--org szl-holdings] \
      [--allowlist .github/data/public_repo_link_allowlist.json] \
      [--report .github/data/public_repo_link_report.json] \
      [--scan-docs] [--max-doc-files 400] [--include-archived] \
      [--check-deep-links] [--check-external] \
      [--fail-on-anchor] [--fail-on-external] [--json]

Exit code 0 = no failing dead links (allowlisted/warning ones excluded); 1 = at
least one failing link (a public→PRIVATE org link, a broken deep org link, or a
warning-class link promoted to failing by the matching --fail-on-* flag).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

API = "https://api.github.com"

# Faithful to an anonymous visitor: deep-link + external liveness probes are
# made with this UA and NO auth, so we observe exactly what a click-through hits.
USER_AGENT = ("szl-holdings-link-check/1.0 "
              "(+https://github.com/szl-holdings/.github)")


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
# A general bare http(s) URL (used only for external liveness collection). Kept
# conservative: stops at whitespace and common closing punctuation; trailing
# sentence punctuation is trimmed by _strip_trailing_punct.
_BARE_URL_ANY_RE = re.compile(
    r"(?<![\(<\"'=\]])\bhttps?://[^\s)\]<>\"'`]+", re.IGNORECASE)


def _strip_trailing_punct(url: str) -> str:
    """Trim trailing sentence punctuation a Markdown author would not intend as
    part of the URL (e.g. a link at the end of a sentence)."""
    return url.rstrip(".,;:!?")


def _clickthrough_urls(text: str, include_bare_external: bool = False):
    """Return de-duplicated click-through hyperlink URLs from `text`.

    Image / badge URLs (Markdown `![..](..)` and `<img src=..>`) are excluded so
    shields.io badges and github actions badge SVGs never count as click-throughs
    -- this is the same exclusion the org-repo check has always relied on.
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
    if include_bare_external:
        for m in _BARE_URL_ANY_RE.finditer(text):
            candidates.append(_strip_trailing_punct(m.group(0).strip()))

    seen = set()
    out = []
    for url in candidates:
        if url in image_urls:
            continue  # it's an image src, not a click-through
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


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
    badge SVGs never count as click-throughs. (Unchanged behaviour: this is the
    default org-repo-existence check.)
    """
    seen = set()
    out = []
    for url in _clickthrough_urls(text):
        repo = _repo_from_url(url)
        if not repo:
            continue
        key = (repo, url)
        if key in seen:
            continue
        seen.add(key)
        out.append((repo, url))
    return out


def _split_fragment(url: str):
    """Split a URL into (base_without_fragment, fragment_without_hash)."""
    base, _, frag = url.partition("#")
    return base, frag


# The DEEP path kinds we HEAD-check: content references that a doc legitimately
# links to and that 404 for everyone when the content rots (a renamed/deleted
# file, a dead tag, a removed issue). We deliberately do NOT probe app-surface
# tabs (security/settings/actions/pulse/graphs/network/projects/packages/...) —
# those are often auth-gated and 404 anonymously even on a perfectly healthy
# repo, so probing them would be noise, not honesty drift.
_DEEP_KINDS = frozenset({
    "blob", "tree", "raw", "blame", "releases", "release",
    "issues", "pull", "pulls", "commit", "commits", "wiki",
    "discussions", "tags",
})


def classify_extended_url(org: str, url: str):
    """Classify a click-through URL for the extended (deep / external) checks.

    Returns (category, repo, base_url, fragment) or None:
      * ("deep", repo, base, frag)     -> a DEEP path into an org repo
                                          (…/<org>/<repo>/<something>).
      * ("external", None, base, frag) -> any other absolute http(s) URL.
      * None                           -> not checkable here (relative link,
                                          mailto:, an org-repo ROOT link which the
                                          existence check already handles, etc.).
    """
    base, frag = _split_fragment(url)
    try:
        parts = urllib.parse.urlsplit(base)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https"):
        return None
    host = (parts.hostname or "").lower()
    if host in ("github.com", "www.github.com"):
        segs = [s for s in parts.path.split("/") if s]
        if len(segs) >= 2 and segs[0].lower() == org.lower():
            repo = segs[1]
            if repo.lower().endswith(".git"):
                repo = repo[:-4]
            repo = repo.rstrip(".")
            if not repo:
                return None
            if len(segs) > 2:
                if segs[2].lower() in _DEEP_KINDS:
                    return ("deep", repo, base, frag)
                return None  # app-surface tab (security/settings/...) -> skip
            return None  # root org link -> handled by the existence check
        # github.com link to some other org/user/gist -> external liveness
        return ("external", None, base, frag)
    return ("external", None, base, frag)


def extract_extended(org: str, text: str, include_bare_external: bool):
    """[(category, repo, base_url, fragment, raw_url)] for one page, de-duped."""
    out = []
    seen = set()
    for url in _clickthrough_urls(text, include_bare_external):
        c = classify_extended_url(org, url)
        if not c:
            continue
        cat, repo, base, frag = c
        key = (cat, base, frag)
        if key in seen:
            continue
        seen.add(key)
        out.append((cat, repo, base, frag, url))
    return out


# --------------------------------------------------------------------------- #
# Liveness probing (anonymous, polite, de-duplicated)
# --------------------------------------------------------------------------- #
class _HostThrottle:
    """Per-host minimum interval between requests, so a liveness sweep stays a
    polite citizen of github.com and any external host."""

    def __init__(self, min_interval: float):
        self._min = max(0.0, min_interval)
        self._last = {}
        self._lock = threading.Lock()

    def wait(self, host: str):
        if self._min <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                last = self._last.get(host, 0.0)
                if now - last >= self._min:
                    self._last[host] = now
                    return
                remaining = self._min - (now - last)
            time.sleep(min(remaining, 5))


def _request_status(url: str, timeout: float, method: str):
    """One HTTP request; returns (status_code | None, error_name | None)."""
    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Accept", "*/*")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return getattr(resp, "status", None) or resp.getcode(), None
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError, ConnectionError,
            OSError, ValueError) as e:
        return None, e.__class__.__name__


def check_url(url: str, throttle: _HostThrottle, timeout: float = 12.0,
              retries: int = 2):
    """Probe a URL's liveness. Returns {"state": ..., "code": int|None}.

    state is one of:
      ok          -> 2xx/3xx
      broken      -> a definitive 404/410 (the link is dead)
      blocked     -> 401/403/405/451 (bot-blocked; NOT evidence of a dead link)
      error       -> some other 4xx
      unreachable -> timeout / DNS / connection error / persistent 5xx / 429
    """
    host = urllib.parse.urlsplit(url).hostname or ""
    last = {"state": "unreachable", "code": None}
    for attempt in range(retries + 1):
        throttle.wait(host)
        code, err = _request_status(url, timeout, "HEAD")
        # Some hosts reject or mishandle HEAD; fall back to GET.
        if code in (400, 403, 405, 501, 999) or code is None:
            gcode, _ = _request_status(url, timeout, "GET")
            if gcode is not None:
                code = gcode
        if code is not None:
            if 200 <= code < 400:
                return {"state": "ok", "code": code}
            if code in (404, 410):
                return {"state": "broken", "code": code}
            if code in (401, 403, 405, 451):
                return {"state": "blocked", "code": code}
            if code == 429 or 500 <= code < 600:
                last = {"state": "unreachable", "code": code}
            else:
                return {"state": "error", "code": code}
        else:
            last = {"state": "unreachable", "code": None, "error": err}
        if attempt < retries:
            time.sleep(min(2 ** attempt, 8))
    return last


# --------------------------------------------------------------------------- #
# Heading-anchor resolution (for deep blob links with a #fragment)
# --------------------------------------------------------------------------- #
_ATX_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_HTML_ANCHOR_RE = re.compile(
    r"""<(?:a|h[1-6]|div|span|section)\b[^>]*?\b(?:id|name)\s*=\s*"""
    r"""["']([^"']+)["']""", re.IGNORECASE)
_MD_ATTR_ID_RE = re.compile(r"\{:?#([A-Za-z0-9_\-:.]+)[^}]*\}")
_LINE_ANCHOR_RE = re.compile(r"^l\d+(?:c\d+)?(?:-l?\d+(?:c\d+)?)?$", re.IGNORECASE)


def _slugify_heading(text: str) -> str:
    """Approximate GitHub's heading->anchor slugger."""
    text = re.sub(r"`+", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)          # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)      # links -> label
    text = re.sub(r"<[^>]+>", "", text)                       # html tags
    text = re.sub(r"[*_~]+", "", text)                        # emphasis
    s = text.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s, flags=re.UNICODE)
    s = s.replace(" ", "-")
    return s


def heading_anchors(md: str):
    """Set of anchor slugs GitHub would generate for this Markdown document."""
    if not md:
        return set()
    out = set()
    counts = {}
    in_fence = False
    fence = None
    for line in md.splitlines():
        st = line.strip()
        if not in_fence and (st.startswith("```") or st.startswith("~~~")):
            in_fence, fence = True, st[:3]
            continue
        if in_fence:
            if st.startswith(fence):
                in_fence, fence = False, None
            continue
        m = _ATX_RE.match(line)
        if m:
            head = m.group(2)
            cid = _MD_ATTR_ID_RE.search(head)
            if cid:
                out.add(cid.group(1).lower())
                head = _MD_ATTR_ID_RE.sub("", head)
            base = _slugify_heading(head)
            if base:
                n = counts.get(base, 0)
                out.add(base if n == 0 else f"{base}-{n}")
                counts[base] = n + 1
    for m in _HTML_ANCHOR_RE.finditer(md):
        anc = m.group(1).lower()
        if anc.startswith("user-content-"):
            anc = anc[len("user-content-"):]
        out.add(anc)
    return out


def _normalize_fragment(frag: str) -> str:
    frag = urllib.parse.unquote(frag).strip().lower()
    if frag.startswith("user-content-"):
        frag = frag[len("user-content-"):]
    return frag


def _is_line_anchor(frag: str) -> bool:
    return bool(_LINE_ANCHOR_RE.match(frag))


def _parse_blob_target(org: str, repo: str, base_url: str):
    """For a …/<org>/<repo>/blob|raw|blame/<ref>/<path> URL, return
    (full_name, ref, path) for a Markdown file, else None."""
    parts = urllib.parse.urlsplit(base_url)
    segs = [s for s in parts.path.split("/") if s]
    # segs = [org, repo, kind, ref, *path]
    if len(segs) < 5:
        return None
    if segs[2].lower() not in ("blob", "raw", "blame"):
        return None
    ref = urllib.parse.unquote(segs[3])
    path = urllib.parse.unquote("/".join(segs[4:]))
    if not path.lower().endswith((".md", ".markdown", ".mdx")):
        return None
    return (f"{org}/{repo}", ref, path)


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
    ap.add_argument("--only", action="append", default=[],
                    help="Restrict the scan to this repo name (repeatable). "
                         "Handy for debugging a single repo's links.")
    ap.add_argument("--fail-on-missing", action="store_true",
                    help="Also fail the job on links to deleted/missing repos "
                         "(default: only links to PRIVATE repos fail; missing "
                         "ones are surfaced as warnings).")
    # Extended (optional, off by default) checks.
    ap.add_argument("--check-deep-links", action="store_true",
                    help="HEAD-check DEEP links into live org repos "
                         "(blob/tree/releases/issues/...) and flag 404s; verify "
                         "#anchors on deep Markdown blob links too.")
    ap.add_argument("--check-external", action="store_true",
                    help="Liveness-check EXTERNAL click-through URLs (non-org "
                         "http(s) links), rate-limited and allowlistable.")
    ap.add_argument("--fail-on-deep", action="store_true",
                    help="Promote a broken (404) DEEP org link from WARN to "
                         "ERROR (fails the job). Off by default so enabling the "
                         "deep check on a schedule surfaces a pre-existing rot "
                         "backlog as warnings rather than breaking CI at once.")
    ap.add_argument("--fail-on-anchor", action="store_true",
                    help="Promote a missing #anchor on a deep Markdown link from "
                         "WARN to ERROR (fails the job).")
    ap.add_argument("--fail-on-external", action="store_true",
                    help="Promote a definitively dead (404/410) EXTERNAL link "
                         "from WARN to ERROR (timeouts/5xx still only warn).")
    ap.add_argument("--external-workers", type=int, default=6,
                    help="Concurrency for deep/external liveness probes.")
    ap.add_argument("--external-timeout", type=float, default=12.0,
                    help="Per-request timeout (seconds) for liveness probes.")
    ap.add_argument("--request-interval", type=float, default=0.25,
                    help="Minimum seconds between requests to the SAME host "
                         "(politeness throttle for liveness probes).")
    ap.add_argument("--max-external", type=int, default=3000,
                    help="Cap on unique external URLs probed (others are "
                         "reported as skipped, never flagged).")
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
    ignore_external_hosts = {h.lower() for h in allow.get("ignore_external_hosts", [])}
    ignore_external_urls = set(allow.get("ignore_external_urls", []))
    ignore_deep_urls = set(allow.get("ignore_deep_urls", []))
    ignore_link_patterns = []
    for p in allow.get("ignore_link_patterns", []):
        try:
            ignore_link_patterns.append(re.compile(p))
        except re.error as e:
            print(f"warning: bad ignore_link_patterns regex {p!r}: {e}",
                  file=sys.stderr)

    def _pattern_match(url: str) -> bool:
        return any(rx.search(url) for rx in ignore_link_patterns)

    def _deep_allowlisted(base: str) -> bool:
        return base in ignore_deep_urls or _pattern_match(base)

    def _external_allowlisted(base: str) -> bool:
        host = (urllib.parse.urlsplit(base).hostname or "").lower()
        return (host in ignore_external_hosts
                or base in ignore_external_urls
                or _pattern_match(base))

    all_repos = list_all_repos(args.org, token)
    existing_names = {r["name"] for r in all_repos}
    private_names = {r["name"] for r in all_repos if r.get("private")}
    public_existing = {r["name"] for r in all_repos if not r.get("private")}
    # Repos to scan: public ones (optionally including archived).
    scan_repos = sorted(
        (r for r in all_repos
         if not r.get("private")
         and (args.include_archived or not r.get("archived"))
         and r["name"] not in ignore_source_repos),
        key=lambda r: r["name"])
    if args.only:
        only = set(args.only)
        scan_repos = [r for r in scan_repos if r["name"] in only]

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

    extended_on = args.check_deep_links or args.check_external

    # --------------------------------------------------------------------- #
    # Pass 1: org-repo existence findings (unchanged) + collect extended
    # candidates (deep org links & external links) for the optional probes.
    # --------------------------------------------------------------------- #
    org_findings_by_repo = {}
    deep_occ = []   # {repo, page, target_repo, base, frag, url}
    ext_occ = []    # {repo, page, base, frag, url}
    branch_by_repo = {r["name"]: (r.get("default_branch") or "main")
                      for r in scan_repos}

    for repo in scan_repos:
        name = repo["name"]
        findings = []
        pages = sorted(pages_by_repo.get(name, []))
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
                    "category": "org-repo",
                    "page": path,
                    "target_repo": target,
                    "kind": kind,
                    "url": url,
                    "fragment": "",
                    "detail": "",
                    "allowlisted": allowlisted,
                })
            if extended_on:
                for cat, trepo, base, frag, url in extract_extended(
                        args.org, text, include_bare_external=args.check_external):
                    if cat == "deep" and args.check_deep_links:
                        # Skip deep links into private/missing repos: the org-repo
                        # existence check already flags those root links, and an
                        # anonymous probe of a private repo would 404 misleadingly.
                        if trepo not in public_existing:
                            continue
                        deep_occ.append({"repo": name, "page": path,
                                         "target_repo": trepo, "base": base,
                                         "frag": frag, "url": url})
                    elif cat == "external" and args.check_external:
                        ext_occ.append({"repo": name, "page": path,
                                        "base": base, "frag": frag, "url": url})
        org_findings_by_repo[name] = findings

    # --------------------------------------------------------------------- #
    # Pass 2: liveness probes (de-duplicated by base URL, parallel, polite).
    # --------------------------------------------------------------------- #
    throttle = _HostThrottle(args.request_interval)
    live_cache = {}
    anchors_cache = {}
    deep_checked = ext_checked = 0
    skipped_external = 0

    def _probe(base):
        return check_url(base, throttle, args.external_timeout)

    if args.check_deep_links and deep_occ:
        deep_bases = sorted({o["base"] for o in deep_occ
                             if not _deep_allowlisted(o["base"])})
        deep_checked = len(deep_bases)
        with ThreadPoolExecutor(max_workers=args.external_workers) as ex:
            for base, res in zip(deep_bases, ex.map(_probe, deep_bases)):
                live_cache[base] = res

    if args.check_external and ext_occ:
        ext_bases = sorted({o["base"] for o in ext_occ
                            if not _external_allowlisted(o["base"])})
        if len(ext_bases) > args.max_external:
            skipped_external = len(ext_bases) - args.max_external
            ext_bases = ext_bases[:args.max_external]
        ext_checked = len(ext_bases)
        with ThreadPoolExecutor(max_workers=args.external_workers) as ex:
            for base, res in zip(ext_bases, ex.map(_probe, ext_bases)):
                live_cache[base] = res

    # Anchor resolution for deep Markdown blob links that are reachable.
    def _anchors_for(full_name, ref, path):
        key = (full_name, ref, path)
        if key in anchors_cache:
            return anchors_cache[key]
        md = _raw_text(full_name, ref, path, token)
        anchors = heading_anchors(md) if md is not None else None
        anchors_cache[key] = anchors
        return anchors

    # --------------------------------------------------------------------- #
    # Pass 3: turn probe results into extended findings (only problematic ones).
    # --------------------------------------------------------------------- #
    ext_findings_by_repo = {}

    def _add(repo, finding):
        ext_findings_by_repo.setdefault(repo, []).append(finding)

    for o in deep_occ:
        base = o["base"]
        if _deep_allowlisted(base):
            continue
        res = live_cache.get(base)
        if not res:
            continue
        state = res["state"]
        code = res.get("code")
        if state == "broken":
            _add(o["repo"], {
                "category": "deep", "page": o["page"],
                "target_repo": o["target_repo"], "kind": "deep-broken",
                "url": o["url"], "fragment": o["frag"],
                "detail": f"HTTP {code}", "allowlisted": False,
                "fails": args.fail_on_deep})
            continue
        if state != "ok":
            # blocked / unreachable / error: can't confirm a dead link -> warn.
            _add(o["repo"], {
                "category": "deep", "page": o["page"],
                "target_repo": o["target_repo"], "kind": "deep-unreachable",
                "url": o["url"], "fragment": o["frag"],
                "detail": f"{state} ({code})" if code else state,
                "allowlisted": False, "fails": False})
            continue
        # Reachable: verify the #anchor on Markdown blob links.
        frag = o["frag"]
        if not frag:
            continue
        nf = _normalize_fragment(frag)
        if not nf or _is_line_anchor(nf):
            continue
        blob = _parse_blob_target(args.org, o["target_repo"], base)
        if not blob:
            continue  # not a Markdown blob link; nothing to verify
        anchors = _anchors_for(*blob)
        if anchors is None:
            continue  # couldn't read the file (ambiguous ref) -> skip, no FP
        if nf not in anchors:
            _add(o["repo"], {
                "category": "deep", "page": o["page"],
                "target_repo": o["target_repo"], "kind": "deep-anchor",
                "url": o["url"], "fragment": frag,
                "detail": f"#{frag} not a heading in {blob[2]}",
                "allowlisted": False, "fails": args.fail_on_anchor})

    for o in ext_occ:
        base = o["base"]
        if _external_allowlisted(base):
            continue
        res = live_cache.get(base)
        if not res:
            continue  # not probed (over the cap) -> skipped, never flagged
        state = res["state"]
        code = res.get("code")
        if state == "broken":
            _add(o["repo"], {
                "category": "external", "page": o["page"], "target_repo": None,
                "kind": "external-broken", "url": o["url"], "fragment": o["frag"],
                "detail": f"HTTP {code}", "allowlisted": False,
                "fails": args.fail_on_external})
        elif state in ("unreachable", "error"):
            _add(o["repo"], {
                "category": "external", "page": o["page"], "target_repo": None,
                "kind": "external-unreachable", "url": o["url"],
                "fragment": o["frag"],
                "detail": f"{state} ({code})" if code
                          else f"{state} ({res.get('error', '?')})",
                "allowlisted": False, "fails": False})
        # 'blocked' (bot protection) and 'ok' are not flagged.

    # --------------------------------------------------------------------- #
    # Assemble per-repo results.
    # --------------------------------------------------------------------- #
    results = []
    for repo in scan_repos:
        name = repo["name"]
        org_findings = org_findings_by_repo.get(name, [])
        # Fill in the org-repo `fails` field (same rule as before).
        for f in org_findings:
            f["fails"] = (not f["allowlisted"]) and (
                f["kind"] == "private" or args.fail_on_missing)
        findings = org_findings + ext_findings_by_repo.get(name, [])
        failing = [f for f in findings if f["fails"]]
        warned = [f for f in findings
                  if not f["allowlisted"] and not f["fails"]]
        status = "ERROR" if failing else ("WARN" if warned else "OK")
        results.append({
            "repo": name,
            "archived": repo.get("archived", False),
            "pages_scanned": len(pages_by_repo.get(name, [])),
            "findings": findings,
            "status": status,
        })

    errs = [x for x in results if x["status"] == "ERROR"]
    warns = [x for x in results if x["status"] == "WARN"]
    all_findings = [f for x in results for f in x["findings"]]

    def _count(pred):
        return sum(1 for f in all_findings if pred(f))

    total_failing = _count(lambda f: f["fails"])
    total_private = _count(lambda f: f["kind"] == "private" and not f["allowlisted"])
    total_missing = _count(lambda f: f["kind"] == "missing" and not f["allowlisted"])
    total_allowlisted = _count(lambda f: f["allowlisted"])
    deep_broken = _count(lambda f: f["kind"] == "deep-broken")
    deep_anchor = _count(lambda f: f["kind"] == "deep-anchor")
    deep_unreachable = _count(lambda f: f["kind"] == "deep-unreachable")
    ext_broken = _count(lambda f: f["kind"] == "external-broken")
    ext_unreachable = _count(lambda f: f["kind"] == "external-unreachable")

    payload = {
        "schema": "szl.public_repo_link_check/v1",
        "org": args.org,
        "checked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scan_docs": args.scan_docs,
        "scan_scope": ("all-markdown" if (args.scan_docs and args.all_markdown)
                       else "readme+docs" if args.scan_docs else "readme-only"),
        "include_archived": args.include_archived,
        "fail_on_missing": args.fail_on_missing,
        "checks": {
            "deep_links": args.check_deep_links,
            "external": args.check_external,
            "fail_on_anchor": args.fail_on_anchor,
            "fail_on_external": args.fail_on_external,
        },
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
            "deep_links_checked": deep_checked,
            "deep_broken": deep_broken,
            "deep_anchor_missing": deep_anchor,
            "deep_unreachable": deep_unreachable,
            "external_links_checked": ext_checked,
            "external_broken": ext_broken,
            "external_unreachable": ext_unreachable,
            "external_skipped_over_cap": skipped_external,
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
        line = (f"Public repo-link check for {args.org}: "
                f"{s['ok']} OK, {s['warn']} WARN, {s['error']} ERROR across "
                f"{s['repos_scanned']} public repos "
                f"({s['links_to_private']} link(s) to PRIVATE, "
                f"{s['links_to_missing']} to MISSING")
        if extended_on:
            line += (f"; deep: {deep_broken} broken/{deep_anchor} anchor/"
                     f"{deep_unreachable} unreachable of {deep_checked} checked"
                     f"; external: {ext_broken} broken/{ext_unreachable} "
                     f"unreachable of {ext_checked} checked")
        line += f"; {s['allowlisted_links']} allowlisted)\n"
        print(line)
        for x in results:
            if not x["findings"]:
                continue
            mark = {"ERROR": "\u2717", "WARN": "\u26a0", "OK": "\u2713"}[x["status"]]
            arch = " [archived]" if x["archived"] else ""
            print(f"  {mark} {x['repo']}{arch}")
            for f in x["findings"]:
                tag = " [allowlisted]" if f["allowlisted"] else ""
                if f["fails"]:
                    level = "error"
                elif not f["allowlisted"]:
                    level = "warning"
                else:
                    level = None
                if f["category"] == "org-repo":
                    human = (f"{x['repo']}/{f['page']} links to "
                             f"{args.org}/{f['target_repo']} which is {f['kind']} "
                             f"(404 for anonymous visitors): {f['url']}")
                    short = (f"{f['kind'].upper()}{tag}: {f['page']} -> "
                             f"{args.org}/{f['target_repo']}  ({f['url']})")
                else:
                    human = (f"{x['repo']}/{f['page']} -> {f['url']} "
                             f"[{f['kind']}: {f['detail']}]")
                    short = (f"{f['kind'].upper()}{tag}: {f['page']} -> "
                             f"{f['url']}  ({f['detail']})")
                if level:
                    print(f"::{level} file={x['repo']}/{f['page']}::{human}")
                print(f"        {short}")

    if errs:
        bits = []
        if total_private:
            bits.append(f"{total_private} to a PRIVATE repo")
        if args.fail_on_missing and total_missing:
            bits.append(f"{total_missing} to a deleted/missing repo")
        if args.fail_on_deep and deep_broken:
            bits.append(f"{deep_broken} broken deep link(s)")
        if args.fail_on_anchor and deep_anchor:
            bits.append(f"{deep_anchor} missing anchor(s)")
        if args.fail_on_external and ext_broken:
            bits.append(f"{ext_broken} dead external link(s)")
        print(f"\n{total_failing} failing public page link(s) "
              f"({'; '.join(bits) if bits else 'see report'}) across "
              f"{len(errs)} repo(s). See above / report.", file=sys.stderr)
        return 1
    if warns:
        print(f"\n\u2713 No failing public page links. "
              f"({total_missing} to deleted/missing repos, "
              f"{deep_unreachable} unreachable deep, "
              f"{ext_broken + ext_unreachable} external issue(s) surfaced as "
              f"warnings -- see the report.)")
        return 0
    print("\n\u2713 No dead public page links found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
