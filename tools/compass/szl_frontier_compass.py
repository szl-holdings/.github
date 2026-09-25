#!/usr/bin/env python3
"""
SZL FRONTIER COMPASS v2: company-level zoom-out across a-11-oy.com, a11oy.net, GitHub and Hugging Face.
Payload id: SZL-FRONTIER-COMPASS-2026-09-25 (hardened: .v2). Verbatim original: szl_frontier_compass.pasted.py

Checks what no single-repo audit can see:
  1. CLAIM CONSISTENCY  every numeric claim on every surface, classified against the canonical sources
                        (.github/.github/data/lean_numbers.json, measured public estate counts): CANONICAL,
                        CURRENT, SCOPED, HISTORICAL, or UNEXPLAINED / DISSENT / STALE (only these are findings).
  2. FRESHNESS          newest dated snapshot per page older than --stale-days (history pages exempt).
  3. LINK INTEGRITY     crawl both origins (+ sitemap); dead internal pages with referrers; GitHub links to
                        private/missing/archived repos; HF repo links probed individually; Space hosts probed.
  4. PROVENANCE         served landing vs canonical GitHub bytes, normalised, injected <script> deltas declared.
  5. WEB + DNS POSTURE  headers (HSTS strength, CSP scope), HTTP->HTTPS first hop, RFC 9116 security.txt
                        (Contact + unexpired Expires), SPF/DMARC/CAA/DNSSEC for web AND mail domains.
  6. NARRATIVE          no-JS placeholder text nodes, readability, whole-word jargon density, words before CTA.
  7. BOARD VIEW         pillar scores, coverage (no silent caps), BOARD_MEMO.md, WORK_ORDERS.md, baseline diff,
                        imports sibling payload reports (szl_frontier_audit report.json, agent ledger agent_report.json).
  8. LEAN REPRODUCTION  re-counts the LOCKED lutar-lean commit with the canonical method and reports whether the
                        published 749/14/163 reproduces, plus drift of main HEAD (doctrine: lock is a founder decision).

Read-only by default. --file-issues + SZL_COMPASS_CONFIRM=FILE_WORK_ORDERS files idempotent (fingerprinted),
capped issues in szl-holdings/.github and appends one receipt line per write. --fail-on turns it into a CI gate.
Stdlib only. ENV: GITHUB_TOKEN (recommended for rate limits; results are still computed from the PUBLIC view),
HF_TOKEN (optional; private HF items are filtered out).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import html as htmlmod
import io
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

VERSION = "SZL-FRONTIER-COMPASS-2026-09-25.v2"
UA = f"{VERSION} (+https://github.com/szl-holdings)"
NOW = dt.datetime.now(dt.timezone.utc)
GH = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
HFT = os.environ.get("HF_TOKEN")
CONFIRM_ENV, CONFIRM_VALUE = "SZL_COMPASS_CONFIRM", "FILE_WORK_ORDERS"
DEFAULT_RECEIPTS = Path.home() / "szl-work" / "receipts" / "szl_frontier.jsonl"
DOMAINS = ["a-11-oy.com", "a11oy.net"]
MACHINE = {
    "a11oy.net": ["/health.json", "/estate.json", "/record.json", "/atlas.json", "/evidence.json", "/decision.json",
                  "/public-inventory.json", "/models.json", "/llms.txt"],
    "a-11-oy.com": ["/api/a11oy/v1/honest", "/api/a11oy/healthz", "/api/a11oy/v1/frontier/surfaces",
                    "/api/a11oy/v1/attest/manifest", "/api/a11oy/v1/genome", "/llms.txt"],
}
COMMON = ["/.well-known/security.txt", "/robots.txt", "/sitemap.xml"]
LANDING_PAIR = ("https://a-11-oy.com/", "https://raw.githubusercontent.com/szl-holdings/a11oy/main/a11oy_landing.html")
LEAN_REPO = "szl-holdings/lutar-lean"
CANONICAL_LEAN = "https://raw.githubusercontent.com/szl-holdings/.github/main/.github/data/lean_numbers.json"
JARGON = ["khipu", "ayllu", "willay", "hatun", "puriq", "yarqa", "chaski", "huklla", "hukulla", "wiñay", "kay pacha", "yuyay",
          "allodial", "ouroboros", "organ", "organs", "hologram", "holographic", "genome", "lattice", "callsign", "bloodstream",
          "theorem u", "conjecture 1", "doctrine", "five-space", "n1–n25", "yawar", "nemo", "aegis", "lyte"]
PLACEHOLDER_WORDS = r"UNAVAILABLE|CHECKING|NOT PROBED|NOT OBSERVED|IDLE|reading…|reading\.\.\.|loading…|loading\.\.\.|—|–|-|…|n/a"
PLACEHOLDER_NODE = re.compile(r">\s*(" + PLACEHOLDER_WORDS + r")\s*<", re.I)
WORDNUM = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())}
COUNT_CTX = r"\b(?:SZL|SZLHOLDINGS|szl-holdings|org(?:anization)?|estate|Hub|Hugging\s*Face|HF|GitHub|public|inventory)\b"
N = r"(?<![\w,.\\])(\d{1,3}(?:,\d{3})+|\d{2,4})(?![\d,]\d)"  # whole number only: not u2014 (escaped em dash), not 1.44, not a fragment
CLAIMS = [
    ("locked_formulas", r"\b(\d+|eight|five|six|seven|nine|ten)\s+locked(?:[- ]proven)?(?:,)?\s*(?:axiom-free\s+)?(?:lean[- ]?4?\s+)?(?:theorems|formulas)"),
    ("locked_formulas", r"\blocked[- ](?:eight|8)\b"),
    ("lean_declarations", r"(?<![\d,.])(\d{1,2},\d{3}|\d{3,4})\s+(?:Lean\s+)?declarations\b"),
    ("lean_axioms", r"\b(\d{1,3})\s+(?:unique\s+|raw\s+|declared\s+|custom\s+|named\s+)?axioms\b"),
    ("lean_sorries", r"\b(\d{1,4})\s+(?:tracked\s+|open\s+|remaining\s+|raw\s+|live\s+)?sorr(?:y|ies)\b"),
    ("doctrine_triple", r"(?<![\d./-])(\d{3})\s*/\s*(\d{1,3})\s*/\s*(\d{1,4})(?![\d./-])"),
    ("flagships", r"(?-i:\b(\d+|one|two|three|four|five|six|One|Two|Three|Four|Five|Six)\s+(?:product\s+|public\s+)?"
                  r"[Ff]lagships?\b)(?!\s+(?:modules?|models?|kernels?|spaces?|repos?|packages?|features?|endpoints?|APIs?)\b)"),
    ("flagships", r"not a (fifth|fourth|third) flagship"),
    ("commercial_flagships", r"\b(\d+|one|two|three|four|five|six)\s+commercial\s+flagships?\b"),
    ("inference_flagships", r"\b(\d+|one|two|three)\s+inference\s+flagships?\b"),
    ("domain_bodies", r"\b(\d+|five|six|four)\s+public domain bodies\b"),
    ("internal_engines", r"\b(\d+|five|six|seven)\s+internal engines\b"),
    ("trust_ceiling", r"trust ceiling\W{0,6}(0\.\d+)"),
    ("slsa_claimed", r"SLSA\W{0,4}(?:level\s*|L)(\d)\b"),
    ("genome_entries", r"\b(\d{2,4})[- ]entry genome|of\s+(\d{2,4})\s+catalog entries"),
    ("catalog_locked", r"catalog LOCKED-PROVEN\W{0,6}(\d+)"),
    ("bom_models", r"all\s+(\d+)\s+public models"),
    ("estates", r"\b(\d{2,3})\s+estates\b"),
    ("count_repos", COUNT_CTX + r"[^.\n]{0,60}?" + N + r"\s+(?:public\s+)?(?:repos|repositories)\b"),
    ("count_models", COUNT_CTX + r"[^.\n]{0,60}?" + N + r"\s+(?:public\s+)?models\b"),
    ("count_spaces", COUNT_CTX + r"[^.\n]{0,60}?" + N + r"\s+(?:public\s+)?spaces\b"),
    ("count_datasets", COUNT_CTX + r"[^.\n]{0,60}?" + N + r"\s+(?:public\s+)?datasets\b"),
]
LEAN_KEYS = {"lean_declarations", "lean_axioms", "lean_sorries", "doctrine_triple"}
COUNT_KEYS = {"count_repos": "repos", "count_models": "models", "count_spaces": "spaces", "count_datasets": "datasets",
              "bom_models": "models"}
# flagships is deliberately NOT strict: "not a fourth flagship" (3 commercial) and "not a fifth flagship" (3 commercial + 1
# inference) are both consistent with the org taxonomy, so a flagship-count dissent is a messaging decision (P2), not a lie.
STRICT_KEYS = {"locked_formulas", "doctrine_triple", "slsa_claimed", "trust_ceiling", "lean_sorries",
               "lean_axioms", "lean_declarations", "domain_bodies", "internal_engines", "commercial_flagships"}
TRIPLE_CTX = re.compile(r"decl|axiom|sorr|lean|doctrine|locked|kernel", re.I)
STANDARD_BEFORE = re.compile(r"\b(FIPS|SP|RFC|ISO|NIST|IEC|IEEE|ECE|ASTM)\W{0,3}$", re.I)
NEGATED_AFTER = re.compile(r"^[^.]{0,100}?(\b(roadmap|not claimed|not yet|not earned|do(?:es)? not claim|is not claimed|"
                           r"remains on|stays on|planned|aspirational|was corrected|corrected to)\b|❌|🛣)", re.I)
NEGATED_BEFORE = re.compile(r"(\b(no|not|never|without|isn't)\W{0,14}$)|(\b(banned|overclaims?|forbidden|never (?:say|claim)|"
                            r"not claimed|don't say)\b[^.\n]{0,50}$)", re.I)
NEGATABLE_KEYS = {"slsa_claimed"}
SCOPED_BELOW = {"lean_sorries": 10, "lean_axioms": 10, "lean_declarations": 100}
SCOPED_AXIOM_CTX = re.compile(r"propext|Quot\.sound|Classical\.choice|standard axioms|kernel axioms", re.I)
HISTORICAL_CTX = re.compile(r"\b(?:HISTORICAL|historical|previously|prior|formerly|was|were|as of|snapshot|at SHA|"
                            r"MEASURED\s+20\d\d)\b|\b20\d\d-\d\d-\d\d\b|@\s?[0-9a-f]{7,40}\b")
FRESH_RX = re.compile(r"\b(snapshot|observed(?:_at(?:_utc)?|At(?:Iso)?)?|generated(?:_at|At)?|as of|updated(?:_at|At)?|"
                      r"measured(?:_at(?:_utc)?|At)?|last[ _-]?updated)\b[^0-9<>\n]{0,40}(20\d\d-\d\d-\d\d)", re.I)
HISTORY_PAGE = re.compile(r"CHANGELOG|/notes/|/archive|/history|INC\d|RECAPTURE|-20\d\d-\d\d-\d\d", re.I)
HF_NON_REPO = {"collections", "papers", "blog", "docs", "organizations", "settings", "join", "login", "pricing", "models",
               "datasets", "spaces", "tasks", "learn", "posts", "new", "chat", "enterprise", "api"}
BOT_BLOCK = {401, 403, 405, 406, 429, 999}
SEV_ORDER = ("P0", "P1", "P2", "P3")
PILLARS = {"truth": ("claims", "lean"), "freshness": ("freshness",), "integrity": ("links", "provenance", "contracts"),
           "security": ("web", "dns"), "narrative": ("narrative",), "estate": ("estate",), "imported": ("imported",)}
SECURITY_CATS = {"web", "dns"}
RECOMMENDATIONS = [
    ("F1", "Five-second story", "One sentence and one CTA on a-11-oy.com. Anatomy, organs, Quechua names and Λ tiers move one click deeper."),
    ("F2", "Server-rendered last-known-good", "Every runtime chip ships the last MEASURED value + timestamp in HTML; JS refreshes it. No-JS readers never see a wall of UNAVAILABLE."),
    ("F3", "One signed number source", "All public counts come from estate.json (signed); this compass runs in CI and fails on any cross-surface contradiction."),
    ("F4", "Freshness SLO", "Any snapshot older than 14 days is auto-labelled STALE and opens a work order."),
    ("F5", "Wedge + external proof", "One buyer, one job (e.g. AI-Act record-keeping evidence — confirm current applicability dates). One design partner and one third party reproducing a receipt, published."),
    ("F6", "Independent review", "External security review of szl-receipt + governed-receipt-spec verifier; verifier on PyPI/npm; publish findings."),
    ("F7", "Governance", "Second maintainer, agent attribution (szl_agent_ledger), estate consolidation to a few dozen canonical repos."),
    ("F8", "Brand + domains", "Resolve a-11-oy.com / a11oy.net / a11oy.com confusion; DMARC p=reject, CAA, HSTS, security.txt on every owned domain — including the mail domain."),
    ("F9", "Nightly compass", "audit -> agent ledger -> compass -> upgrade(plan) -> one BOARD_MEMO issue; humans approve write phases."),
]
TOKEN_RX = re.compile(r"(gh[opsu]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,}|xai-[A-Za-z0-9]{20,})")
STATS = Counter()
COVERAGE = {}
_LOCK = threading.Lock()


def redact(s):
    return TOKEN_RX.sub(lambda m: "***" + m.group(0)[-4:], str(s))


def log(msg):
    print(f"[compass] {msg}", file=sys.stderr, flush=True)


def cover(name, total, checked, note=""):
    COVERAGE[name] = {"total": total, "checked": checked, "truncated": total > checked, "note": note}


# ------------------------------------------------------------------------------------------------ http
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_NOREDIR = urllib.request.build_opener(_NoRedirect)


def _iri(url):
    """IRI -> URI: IDNA host, percent-encode non-ASCII path/query (urllib refuses raw non-ASCII)."""
    try:
        url.encode("ascii")
        return url
    except UnicodeEncodeError:
        p = urllib.parse.urlsplit(url)
        host = p.hostname.encode("idna").decode("ascii") if p.hostname else ""
        netloc = host + (f":{p.port}" if p.port else "")
        q = lambda s: urllib.parse.quote(s, safe="/:@!$&'()*+,;=%~-._?#[]")
        return urllib.parse.urlunsplit((p.scheme, netloc, q(p.path), q(p.query), q(p.fragment)))


def fetch(url, accept=None, timeout=25, method="GET", max_bytes=4_000_000, retries=2, follow=True, auth=True):
    """GET/HEAD; auth only for api.github.com (and HF API listings when auth=True). Never raises."""
    try:
        url = _iri(url)
    except Exception as e:
        return {"url": url, "final": url, "status": 0, "headers": {}, "body": "", "ms": None, "error": f"bad URL: {type(e).__name__}"}
    hdr = {"User-Agent": UA}
    if accept:
        hdr["Accept"] = accept
    host = urllib.parse.urlparse(url).netloc
    if host == "api.github.com":
        hdr.setdefault("Accept", "application/vnd.github+json")
        hdr["X-GitHub-Api-Version"] = "2022-11-28"
        if GH:
            hdr["Authorization"] = f"Bearer {GH}"
    elif host == "huggingface.co" and "/api/" in url and HFT and auth:
        hdr["Authorization"] = f"Bearer {HFT}"
    opener = urllib.request.build_opener() if follow else _NOREDIR
    for attempt in range(retries + 1):
        t0 = time.time()
        with _LOCK:
            STATS["http"] += 1
            if host == "api.github.com":
                STATS["github_rest"] += 1
        try:
            rq = urllib.request.Request(url, headers=hdr, method=method)
            with opener.open(rq, timeout=timeout) as r:
                body = r.read(max_bytes).decode("utf-8", "replace") if method != "HEAD" else ""
                return {"url": url, "final": r.geturl(), "status": r.status, "headers": {k.lower(): v for k, v in r.headers.items()},
                        "body": body, "ms": round((time.time() - t0) * 1000)}
        except urllib.error.HTTPError as e:
            headers = {k.lower(): v for k, v in (e.headers or {}).items()}
            body = ""
            try:
                body = e.read(200_000).decode("utf-8", "replace") if e.fp else ""
            except Exception:
                pass
            res = {"url": url, "final": headers.get("location", url) if 300 <= e.code < 400 else url, "status": e.code,
                   "headers": headers, "body": body, "ms": round((time.time() - t0) * 1000)}
            rest_exhausted = host == "api.github.com" and e.code in (403, 429) and headers.get("x-ratelimit-remaining") == "0"
            if rest_exhausted:
                with _LOCK:
                    STATS["github_rest_exhausted"] += 1
                return res  # doctrine: never retry-loop REST
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                ra = headers.get("retry-after", "")
                time.sleep(min(30.0, float(ra)) if ra.isdigit() else 1.5 * (2 ** attempt))
                continue
            return res
        except Exception as e:
            if attempt < retries:
                time.sleep(1.5 * (2 ** attempt))
                continue
            return {"url": url, "final": url, "status": 0, "headers": {}, "body": "", "ms": None,
                    "error": redact(f"{type(e).__name__}: {getattr(e, 'reason', '') or e}")[:200]}
    return {"url": url, "final": url, "status": 0, "headers": {}, "body": "", "ms": None, "error": "exhausted"}


def jget(url, **kw):
    r = fetch(url, **kw)
    try:
        return r["status"], (json.loads(r["body"]) if r["body"] else None)
    except Exception:
        return r["status"], None


def pmap(fn, items, workers=8):
    items = list(items)
    if not items:
        return []
    with cf.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        return list(ex.map(fn, items))


def gh_paged(path, cap=2000):
    out, url, ok = [], f"https://api.github.com{path}", True
    while url and len(out) < cap:
        r = fetch(url)
        try:
            js = json.loads(r["body"])
        except Exception:
            js = None
        if r["status"] != 200 or not isinstance(js, list):
            ok = False
            break
        out += js
        m = re.search(r'<([^>]+)>;\s*rel="next"', r["headers"].get("link", ""))
        url = m.group(1) if m else None
    return out, ok


def strip_code(html):
    return re.sub(r"(?is)<(script|style|template|noscript)\b[^>]*>.*?</\1\s*>", " ", html)


def text_of(html):
    """Visible text: drop script/style/svg/template, strip tags, unescape entities."""
    h = re.sub(r"(?is)<(script|style|svg|template)\b[^>]*>.*?</\1\s*>", " ", html)
    h = re.sub(r"(?s)<!--.*?-->", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", htmlmod.unescape(h)).strip()


class Findings:
    def __init__(self):
        self.items = []

    def add(self, cat, sev, target, title, evidence="", rec="", **extra):
        ev = redact(evidence).replace("\r\n", "\n").replace("\r", "\n")[:1200]
        f = {"cat": cat, "sev": sev, "target": redact(target), "title": redact(title), "evidence": ev, "rec": rec}
        f.update(extra)
        f["fp"] = hashlib.sha256(f"{cat}|{f['target']}|{re.sub(r'[0-9]+', '#', f['title'])}".encode()).hexdigest()[:16]
        self.items.append(f)
        return f


# ------------------------------------------------------------------------------------------------ crawl
SKIP_EXT = re.compile(r"\.(png|jpe?g|gif|svg|webp|avif|ico|pdf|zip|gz|css|js|mjs|map|woff2?|ttf|otf|mp4|webm|wasm)$", re.I)
TEMPLATE_HREF = re.compile(r"\$\{|\{\{|%7B%7B|%24%7B|\$%7B", re.I)


def crawl(domain, max_pages, referrers):
    start = f"https://{domain}/"
    queue, seen, pages, external = [start], set(), {}, set()
    sm = fetch(f"https://{domain}/sitemap.xml", accept="application/xml, text/xml, */*")
    if sm["status"] == 200:
        for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sm["body"]):
            p = urllib.parse.urlparse(htmlmod.unescape(loc))
            if p.netloc == domain:
                clean = p._replace(path=p.path or "/", query="", fragment="").geturl()
                referrers[clean].add(f"https://{domain}/sitemap.xml")
                queue.append(clean)
    pages[f"https://{domain}/sitemap.xml"] = sm
    while queue and len([u for u in pages if not u.endswith("/sitemap.xml")]) < max_pages:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        r = fetch(u)
        r["crawled"] = True
        pages[u] = r
        if r["status"] != 200:
            continue
        if urllib.parse.urlparse(r["final"]).netloc not in (domain, ""):
            continue
        if "html" not in r["headers"].get("content-type", ""):
            continue
        body = strip_code(r["body"])
        for href in re.findall(r'href\s*=\s*["\']([^"\'#\s]+)', body):
            href = htmlmod.unescape(href)
            if TEMPLATE_HREF.search(href):
                continue
            try:
                full = urllib.parse.urljoin(r["final"], href)
                p = urllib.parse.urlparse(full)
                p.port  # noqa: B018  (raises ValueError on malformed netloc such as https://[YOUR-DOMAIN]/)
            except ValueError:
                continue
            if p.scheme not in ("http", "https"):
                continue
            if p.netloc == domain:
                if SKIP_EXT.search(p.path):
                    continue
                clean = p._replace(path=p.path or "/", query="", fragment="").geturl()
                referrers[clean].add(u)
                if clean not in seen:
                    queue.append(clean)
            else:
                ext = p._replace(fragment="").geturl()
                external.add(ext)
                referrers[ext].add(u)
    left = len({q for q in queue if q not in seen})
    crawled = len([u for u in pages if pages[u].get("crawled")])
    cover(f"crawl:{domain}", crawled + left, crawled, "--max-pages")
    for path in MACHINE.get(domain, []) + COMMON:
        u = f"https://{domain}{path}"
        if u not in pages:
            pages[u] = fetch(u, accept="application/json, text/plain, */*")
        pages[u]["contract"] = path
    return pages, external


def internal_pages(pages, referrers, F):
    dead = defaultdict(list)
    for u, r in pages.items():
        if r.get("crawled") and r["status"] != 200 and not r.get("contract"):
            dead[(r["status"], urllib.parse.urlparse(u).netloc)].append(u)
    for (status, host), urls in dead.items():
        for u in urls:
            refs = sorted(referrers.get(u, []))
            is_root = urllib.parse.urlparse(u).path in ("", "/")
            F.add("links", "P1" if is_root else "P2", u, f"Internal page HTTP {status}",
                  f"linked from: {', '.join(refs[:6]) or 'sitemap/seed'}" + (f" (+{len(refs) - 6} more)" if len(refs) > 6 else ""),
                  "Restore the page, or remove/re-point every referrer listed.", referrers=refs[:25])


def machine_contracts(pages, F):
    """MACHINE endpoints are published machine contracts: they must exist and parse."""
    out = {}
    for u, r in pages.items():
        path = r.get("contract")
        if not path or path in COMMON:
            continue
        st = r["status"]
        state = "OK"
        if st != 200:
            state = f"HTTP {st}"
            F.add("contracts", "P2", u, f"Machine contract {path} returns HTTP {st}", r.get("error", ""),
                  "Publish the contract (or remove it from llms.txt / docs that advertise it).")
        elif path.endswith(".json") or "/api/" in path:
            try:
                json.loads(r["body"])
            except Exception:
                state = "INVALID_JSON"
                F.add("contracts", "P2", u, f"Machine contract {path} is not valid JSON",
                      r["body"][:160], "Serve application/json that parses; add a schema test in CI.")
        out[u] = {"status": st, "state": state, "bytes": len(r["body"]), "content_type": r["headers"].get("content-type", "")}
    return out


# ------------------------------------------------------------------------------------------------ estate truth
def estate_truth(gh_org, hf_org):
    repos, ok = gh_paged(f"/orgs/{gh_org}/repos?type=all&per_page=100")
    state = {"github": "MEASURED" if ok and repos else "UNAVAILABLE"}
    hf = {}
    for kind in ("models", "datasets", "spaces"):
        st, js = jget(f"https://huggingface.co/api/{kind}?author={hf_org}&limit=1000")
        items = js if isinstance(js, list) else []
        hf[kind] = [x for x in items if not x.get("private")]
        state[f"hf_{kind}"] = "MEASURED" if isinstance(js, list) else f"UNAVAILABLE (HTTP {st})"
        if len(items) >= 1000:
            cover(f"hf-list:{kind}", 1001, len(items), "HF list API limit=1000; more may exist")
    return repos, hf, state


# ------------------------------------------------------------------------------------------------ lean (canonical method)
DECL_RE = re.compile(r"^(?:private\s+)?(?:noncomputable\s+)?(?:private\s+)?"
                     r"(theorem|lemma|def|abbrev|instance|structure|inductive|class)\b")
AXIOM_RE = re.compile(r"^(?:private\s+)?axiom\s+([A-Za-z_][A-Za-z0-9_']*)")
SORRY_RE = re.compile(r"\bsorry\b")
COMMENT_LINE_RE = re.compile(r"^\s*--")
LEAN_FIELDS = ("declarations", "axioms_raw", "axioms_unique", "sorries_raw", "sorries_noncomment", "sorries_putnam",
               "sorries_baseline")
HEADLINE_FIELDS = ("declarations", "axioms_unique", "sorries_raw")


def lean_count(files):
    """files: iterable of (path, text). Mirrors .github/.github/scripts/lean_numbers.py count() line for line."""
    n = dict.fromkeys(LEAN_FIELDS, 0)
    names = set()
    for path, text in files:
        is_putnam = "/Putnam/" in "/" + path.replace("\\", "/")
        for line in io.StringIO(text, newline=None):  # same line splitting as iterating a text-mode file
            if DECL_RE.match(line):
                n["declarations"] += 1
            m = AXIOM_RE.match(line)
            if m:
                n["axioms_raw"] += 1
                names.add(m.group(1))
            hits = len(SORRY_RE.findall(line))
            if hits:
                n["sorries_raw"] += hits
                if not COMMENT_LINE_RE.match(line):
                    n["sorries_noncomment"] += hits
                n["sorries_putnam" if is_putnam else "sorries_baseline"] += hits
    n["axioms_unique"] = len(names)
    n["axiom_names"] = sorted(names)
    return n


def measure_lean_ref(ref, workers, cap):
    st, c = jget(f"https://api.github.com/repos/{LEAN_REPO}/commits/{urllib.parse.quote(ref)}")
    if st != 200 or not isinstance(c, dict):
        return {"state": f"UNAVAILABLE (commit {ref}: HTTP {st})", "ref": ref}
    sha, tree_sha = c["sha"], c["commit"]["tree"]["sha"]
    st, tree = jget(f"https://api.github.com/repos/{LEAN_REPO}/git/trees/{tree_sha}?recursive=1")
    if st != 200 or not isinstance(tree, dict):
        return {"state": f"UNAVAILABLE (tree: HTTP {st})", "ref": ref, "sha": sha}
    paths = sorted(x["path"] for x in tree.get("tree", []) if x.get("type") == "blob" and x["path"].endswith(".lean")
                   and (x["path"].startswith("Lutar/") or x["path"] == "Main.lean"))
    todo = paths[:cap]
    got = pmap(lambda p: (p, fetch(f"https://raw.githubusercontent.com/{LEAN_REPO}/{sha}/{urllib.parse.quote(p)}",
                                   max_bytes=20_000_000)), todo, workers)
    failed = [p for p, r in got if r["status"] != 200]
    n = lean_count((p, r["body"]) for p, r in got if r["status"] == 200)
    cover(f"lean:{ref}", len(paths), len(todo) - len(failed), "--lean-cap / fetch failures")
    complete = not failed and not tree.get("truncated") and len(todo) == len(paths)
    return {"state": "MEASURED" if complete else "PARTIAL", "ref": ref, "sha": sha,
            "committed_at": c["commit"]["committer"]["date"], "files": len(paths), "fetched": len(todo) - len(failed),
            "failed": failed[:20], "tree_truncated": bool(tree.get("truncated")),
            "method": "canonical .github/scripts/lean_numbers.py (Lutar/ + Main.lean, line regexes)", **n}


def lean_truth(workers, cap, F, enabled=True):
    st, canon = jget(CANONICAL_LEAN)
    out = {"canonical_url": CANONICAL_LEAN, "canonical": canon if isinstance(canon, dict) else None}
    if not isinstance(canon, dict) or not isinstance(canon.get("numbers"), dict):
        F.add("lean", "P1", CANONICAL_LEAN, "Canonical lean_numbers.json unreadable", f"HTTP {st}",
              "Restore .github/.github/data/lean_numbers.json; every surface cites it.")
        out["state"] = "UNAVAILABLE"
        return out
    if not enabled:
        out["state"] = "CANONICAL_ONLY"
        return out
    num = canon["numbers"]
    locked = measure_lean_ref(canon.get("sha", "main"), workers, cap)
    head = measure_lean_ref("main", workers, cap)
    out.update({"locked": locked, "head": head})
    if locked.get("state") == "MEASURED":
        diffs = {k: (num.get(k), locked[k]) for k in LEAN_FIELDS if k in num and num.get(k) != locked[k]}
        headline = {k: v for k, v in diffs.items() if k in HEADLINE_FIELDS}
        out["locked_reproduces"] = not headline
        out["locked_secondary_mismatch"] = {k: {"canonical": a, "recount": b} for k, (a, b) in diffs.items() if k not in HEADLINE_FIELDS}
        if headline:
            F.add("lean", "P1", f"{LEAN_REPO}@{canon.get('sha')}", "Locked Lean HEADLINE figures do NOT reproduce with the canonical method",
                  "; ".join(f"{k}: canonical {a} vs recount {b}" for k, (a, b) in headline.items()),
                  "Re-run .github/scripts/lean_numbers.py at the locked SHA; fix the JSON or the doctrine text, never both silently.")
        for k, (a, b) in diffs.items():
            if k not in HEADLINE_FIELDS:
                F.add("lean", "P2", f"{LEAN_REPO}@{canon.get('sha')}#{k}",
                      f"lean_numbers.json {k} = {a} but the canonical method yields {b} at the locked SHA",
                      f"headline {num.get('declarations')}/{num.get('axioms_unique')}/{num.get('sorries_raw')} reproduces; "
                      f"secondary field {k} does not (recount of {locked['files']} files at {locked['sha'][:12]})",
                      f"Correct {k} to {b} in .github/.github/data/lean_numbers.json (same SHA; a transcription fix, not a lock advance).")
    else:
        out["locked_reproduces"] = None
    if head.get("state") == "MEASURED" and locked.get("state") == "MEASURED":
        delta = {k: head[k] - locked[k] for k in ("declarations", "axioms_unique", "sorries_raw")}
        if any(delta.values()):
            age = (NOW - dt.datetime.fromisoformat(locked["committed_at"].replace("Z", "+00:00"))).days
            F.add("lean", "P3", f"{LEAN_REPO}@main", "Public Lean figures are pinned to the locked commit; main HEAD has moved",
                  f"locked {canon.get('sha')} ({age} d old) = {locked['declarations']}/{locked['axioms_unique']}/{locked['sorries_raw']}; "
                  f"main {head['sha'][:8]} = {head['declarations']}/{head['axioms_unique']}/{head['sorries_raw']} (decl/axioms/sorries)",
                  "Doctrine: advancing the lock is a founder decision. Publish both lines (LOCKED + CURRENT, each with SHA and date).")
    out["state"] = "MEASURED"
    return out


# ------------------------------------------------------------------------------------------------ claims
def _num(g):
    g = g.lower().replace(",", "")
    return str(WORDNUM.get(g, g))


def extract_claims(surfaces):
    """surfaces: {name: text}. Returns list of {key, value, surface, snippet}."""
    out = []
    for name, txt in surfaces.items():
        for key, pat in CLAIMS:
            for m in re.finditer(pat, txt, re.I):
                snippet = txt[max(0, m.start() - 80): m.end() + 80]
                groups = [g for g in m.groups() if g] if m.groups() else []
                if key == "doctrine_triple" and (not TRIPLE_CTX.search(snippet) or STANDARD_BEFORE.search(txt[max(0, m.start() - 16): m.start()])):
                    continue
                negated = key in NEGATABLE_KEYS and bool(NEGATED_AFTER.search(txt[m.end(): m.end() + 110]) or
                                                         NEGATED_BEFORE.search(txt[max(0, m.start() - 70): m.start()]))
                if key == "flagships" and "not a" in m.group(0).lower():
                    vals = [{"fifth": "4", "fourth": "3", "third": "2"}[m.group(1).lower()]]
                elif key == "locked_formulas" and not groups:
                    vals = ["8"]
                else:
                    vals = [_num(g) for g in groups] or [m.group(0).lower()]
                c = {"key": key, "value": "/".join(vals), "surface": name, "snippet": snippet.replace("\n", " ")}
                if negated:
                    c["cls"] = "NEGATED"
                out.append(c)
    return out


def lean_allowed(lean):
    """Canonical-locked values (every published variant) plus CURRENT measured main HEAD values."""
    canon = ((lean or {}).get("canonical") or {}).get("numbers") or {}
    head = (lean or {}).get("head") or {}
    allowed = {"lean_declarations": set(), "lean_axioms": set(), "lean_sorries": set(), "doctrine_triple": set(),
               "locked_formulas": set()}
    cur = {k: set() for k in allowed}
    if canon:
        allowed["lean_declarations"] |= {canon.get("declarations")}
        allowed["lean_axioms"] |= {canon.get("axioms_unique"), canon.get("axioms_raw")}
        allowed["lean_sorries"] |= {canon.get(k) for k in ("sorries_raw", "sorries_noncomment", "sorries_baseline", "sorries_putnam")}
        allowed["doctrine_triple"] |= {(canon.get("declarations"), a, s) for a in (canon.get("axioms_unique"), canon.get("axioms_raw"))
                                       for s in (canon.get("sorries_raw"), canon.get("sorries_noncomment"))}
        if canon.get("locked_formula_count") is not None:
            allowed["locked_formulas"] |= {canon.get("locked_formula_count")}
    if head.get("state") == "MEASURED":
        cur["lean_declarations"] |= {head["declarations"]}
        cur["lean_axioms"] |= {head["axioms_unique"], head["axioms_raw"]}
        cur["lean_sorries"] |= {head[k] for k in ("sorries_raw", "sorries_noncomment", "sorries_baseline", "sorries_putnam")}
        cur["doctrine_triple"] |= {(head["declarations"], a, s) for a in (head["axioms_unique"], head["axioms_raw"])
                                   for s in (head["sorries_raw"], head["sorries_noncomment"])}
    return allowed, cur


def classify_claims(claims, truth):
    """Adds c['cls'] to every claim. Only UNEXPLAINED / DISSENT / STALE become findings."""
    allowed, cur = lean_allowed(truth.get("lean"))
    counts = truth.get("counts", {})
    by = defaultdict(list)
    for c in claims:
        by[c["key"]].append(c)
    consensus = {}
    for key, cs in by.items():
        for c in cs:
            if c.get("cls") == "NEGATED":
                continue
            snip, val = c["snippet"], c["value"]
            try:
                parts = tuple(int(x) for x in val.split("/"))
            except ValueError:
                parts = ()
            v = parts[0] if len(parts) == 1 else parts
            if key in LEAN_KEYS or key == "locked_formulas":
                if key == "doctrine_triple":
                    c["cls"] = "CANONICAL" if v in allowed[key] else "CURRENT" if v in cur[key] else \
                        "HISTORICAL" if HISTORICAL_CTX.search(snip) else "UNEXPLAINED"
                elif v == 0 or (key == "lean_axioms" and SCOPED_AXIOM_CTX.search(snip)) or \
                        (isinstance(v, int) and v < SCOPED_BELOW.get(key, 0)):
                    c["cls"] = "SCOPED"
                elif key == "locked_formulas" and not allowed[key]:
                    c["cls"] = "UNCHECKED"
                else:
                    c["cls"] = "CANONICAL" if v in allowed[key] else "CURRENT" if v in cur.get(key, ()) else \
                        "HISTORICAL" if HISTORICAL_CTX.search(snip) else "UNEXPLAINED"
            elif key in COUNT_KEYS:
                noun = COUNT_KEYS[key]
                truths = [t for t in (counts.get(noun), counts.get(noun + "_total")) if t]
                if not truths or not isinstance(v, int):
                    c["cls"] = "UNCHECKED"
                elif any(abs(v - t) / t <= 0.1 for t in truths):
                    c["cls"] = "CURRENT"
                elif HISTORICAL_CTX.search(snip):
                    c["cls"] = "HISTORICAL"
                else:
                    c["cls"] = "STALE"
            else:
                c["cls"] = "PENDING"
        pend = [c for c in cs if c.get("cls") == "PENDING"]
        if pend:
            weight = Counter()
            for val, srcs in _group(pend).items():
                weight[val] = len(srcs)
            top = weight.most_common(2)
            if len(top) == 1 or top[0][1] > top[1][1]:
                consensus[key] = top[0][0]
                for c in pend:
                    c["cls"] = "CONSENSUS" if c["value"] == top[0][0] else \
                        "HISTORICAL" if HISTORICAL_CTX.search(c["snippet"]) else "DISSENT"
            else:
                consensus[key] = None
                for c in pend:
                    c["cls"] = "HISTORICAL" if HISTORICAL_CTX.search(c["snippet"]) else "DISSENT"
    return consensus


def _group(cs):
    g = defaultdict(set)
    for c in cs:
        g[c["value"]].add(c["surface"])
    return g


def surface_url(name):
    if name == "github:org-profile":
        return "https://github.com/szl-holdings"
    if name.startswith("github:"):
        full, _, part = name[len("github:"):].partition("#")
        return f"https://github.com/{full}" + ("#readme" if part == "README" else "")
    if name.startswith("hf:"):
        return f"https://huggingface.co/{name[3:]}"
    return name


def check_claims(claims, truth, consensus, F):
    bad = defaultdict(list)
    for c in claims:
        if c["cls"] in ("UNEXPLAINED", "DISSENT", "STALE"):
            bad[(c["key"], c["value"], c["cls"])].append(c)
    lean = truth.get("lean") or {}
    canon = (lean.get("canonical") or {}).get("numbers") or {}
    head = lean.get("head") or {}
    for (key, val, cls), cs in sorted(bad.items()):
        surfaces = sorted({c["surface"] for c in cs})
        urls = [surface_url(s) for s in surfaces]
        ev = f"{len(surfaces)} surface(s): " + ", ".join(urls[:8]) + (f" (+{len(urls) - 8} more)" if len(urls) > 8 else "") + \
             f' | e.g. "…{cs[0]["snippet"].strip()[:220]}…"'
        if cls == "UNEXPLAINED":
            ref = f"canonical-locked {sorted(x for x in lean_allowed(lean)[0].get(key, set()) if x is not None)}"
            if head.get("state") == "MEASURED":
                ref += f"; main HEAD {head['sha'][:8]}: decl {head['declarations']}, axioms {head['axioms_unique']}/{head['axioms_raw']}, sorries {head['sorries_raw']}"
            F.add("claims", "P1", f"{key}={val}", f"'{key}' = {val} matches neither the locked canonical figures nor main HEAD",
                  ev + " | reference: " + ref,
                  "Replace with the canonical LOCKED figure (cite lean_numbers.json + SHA) or the CURRENT measured figure with date + SHA.",
                  surfaces=surfaces, cls=cls, claim_key=key, claim_value=val)
        elif cls == "DISSENT":
            cons = consensus.get(key)
            sev = "P1" if key in STRICT_KEYS else "P2"
            what = f"majority value is {cons}" if cons else "no majority value — surfaces disagree"
            F.add("claims", sev, f"{key}={val}", f"'{key}' = {val} contradicts the public consensus ({what})", ev,
                  "Pick one canonical value, publish it in estate.json, render every surface from it.",
                  surfaces=surfaces, cls=cls, claim_key=key, claim_value=val)
        else:
            noun = COUNT_KEYS[key]
            t = truth["counts"].get(noun)
            tt = truth["counts"].get(noun + "_total")
            F.add("claims", "P2", f"{key}={val}", f"Claims {val} {noun}; measured public {t}" + (f" (incl. archived {tt})" if tt else ""),
                  ev, "Render counts from the manifest with an observation date, or label as HISTORICAL.",
                  surfaces=surfaces, cls=cls, claim_key=key, claim_value=val)


# ------------------------------------------------------------------------------------------------ checks
def freshness(pages, stale_days, F):
    for u, r in pages.items():
        if r["status"] != 200 or HISTORY_PAGE.search(u):
            continue
        best = None
        for m in FRESH_RX.finditer(r["body"]):
            try:
                d = dt.datetime.fromisoformat(m.group(2)).replace(tzinfo=dt.timezone.utc)
            except ValueError:
                continue
            if d > NOW + dt.timedelta(days=2):
                continue
            if best is None or d > best[0]:
                best = (d, m)
        if not best:
            continue
        d, m = best
        age = (NOW - d).days
        if age > stale_days:
            F.add("freshness", "P2" if age < 45 else "P1", u, f"Newest dated snapshot on page is {m.group(2)} ({age} days old)",
                  r["body"][max(0, m.start() - 60): m.end() + 60].replace("\n", " "),
                  "Regenerate on a schedule, or label the block STALE with its date (F4 freshness SLO).")


def parse_hf(u):
    p = urllib.parse.urlparse(u)
    parts = [x for x in p.path.split("/") if x]
    if not parts:
        return None
    if parts[0] in ("spaces", "datasets"):
        if len(parts) < 3:
            return None
        return ({"spaces": "space", "datasets": "dataset"}[parts[0]], f"{parts[1]}/{parts[2]}")
    if parts[0] in HF_NON_REPO or len(parts) < 2:
        return None
    return ("model", f"{parts[0]}/{parts[1]}")


def link_integrity(external, referrers, repos, hf, est_state, hf_org, gh_org, cap, workers, F):
    pub = {r["name"].lower(): r for r in repos if not r.get("private")}
    priv = {r["name"].lower(): r for r in repos if r.get("private")}
    hf_ids = {("model", x["id"].lower()) for x in hf["models"]} | {("dataset", x["id"].lower()) for x in hf["datasets"]} | \
             {("space", x["id"].lower()) for x in hf["spaces"]}
    gh_dead, hf_probe, hosts, other = defaultdict(set), defaultdict(set), defaultdict(set), []
    for u in sorted(external):
        p = urllib.parse.urlparse(u)
        parts = [x for x in p.path.split("/") if x]
        refs = referrers.get(u, set())
        if p.netloc in ("github.com", "www.github.com") and len(parts) >= 2 and parts[0].lower() == gh_org.lower():
            if est_state.get("github") != "MEASURED":
                continue
            name = parts[1].lower().removesuffix(".git")
            if name in pub:
                if pub[name].get("archived"):
                    gh_dead[(f"https://github.com/{gh_org}/{parts[1]}", "archived")].update(refs)
            elif name in priv:
                gh_dead[(f"https://github.com/{gh_org}/{parts[1]}", "private")].update(refs)
            else:
                gh_dead[(f"https://github.com/{gh_org}/{parts[1]}", "missing")].update(refs)
        elif p.netloc == "huggingface.co":
            k = parse_hf(u)
            if k and k[1].split("/")[0].lower() == hf_org.lower() and (k[0], k[1].lower()) not in hf_ids:
                hf_probe[(k[0], k[1].lower())].update(refs)
        elif p.netloc.endswith(".hf.space") and p.netloc.startswith(hf_org.lower() + "-"):
            hosts[p.netloc].update(refs)
        else:
            other.append(u)
    for (url, why), refs in gh_dead.items():
        sev = "P2" if why == "archived" else "P1"
        desc = (pub.get(url.rsplit("/", 1)[1].lower()) or {}).get("description") or ""
        title = {"archived": "Links to an ARCHIVED repo as if current", "private": "Links to a PRIVATE repo (404 for the public)",
                 "missing": "Links to a GitHub repo that does not exist"}[why]
        F.add("links", sev, url, title, f"linked from: {', '.join(sorted(refs)[:6])}" + (f" | {desc[:160]}" if desc else ""),
              "Point to the canonical successor." if why == "archived" else "Fix the link, or publish the repo.",
              referrers=sorted(refs)[:25])

    def probe_hf(key):
        kind, rid = key
        st, _ = jget(f"https://huggingface.co/api/{kind}s/{rid}", auth=False)
        return key, st

    dead_by_page = defaultdict(list)
    for (kind, rid), st in pmap(probe_hf, list(hf_probe), workers):
        if st in (401, 404):
            url = f"https://huggingface.co/{'' if kind == 'model' else kind + 's/'}{rid}"
            for ref in sorted(hf_probe[(kind, rid)]) or ["(unknown referrer)"]:
                dead_by_page[ref].append(url)
    for page, urls in sorted(dead_by_page.items()):
        F.add("links", "P1", page, f"Page links to {len(urls)} Hugging Face repo(s) that are missing or private for the public (HTTP 401/404)",
              ", ".join(u.rsplit("/", 1)[1] for u in sorted(urls)[:40]) + (f" (+{len(urls) - 40} more)" if len(urls) > 40 else ""),
              "Remove or re-point each link (the Space/model was consolidated, renamed or made private).", dead_targets=sorted(urls))
    cover("hf-link-probes", len(hf_probe), len(hf_probe), f"{sum(len(v) for v in dead_by_page.values())} dead link instances")

    def probe_host(h):
        return h, fetch(f"https://{h}/", timeout=20, max_bytes=20_000)

    for h, r in pmap(probe_host, list(hosts), workers):
        if r["status"] in (0, 404, 410):
            F.add("links", "P1", f"https://{h}", "Links to a Space host that does not answer for the public",
                  f"HTTP {r['status']} {r.get('error', '')} | linked from: {', '.join(sorted(hosts[h])[:6])}",
                  "Remove or re-point.", referrers=sorted(hosts[h])[:25])

    def probe(u):
        r = fetch(u, timeout=15, max_bytes=100_000, retries=1)
        return u, r

    checked = other[:cap]
    unverifiable = []
    for u, r in pmap(probe, checked, workers):
        st = r["status"]
        if st in BOT_BLOCK:
            unverifiable.append(u)
        elif st >= 400 or st == 0:
            refs = sorted(referrers.get(u, []))
            F.add("links", "P2", u, f"External link HTTP {st}" + (f" ({r.get('error')})" if r.get("error") else ""),
                  f"linked from: {', '.join(refs[:6])}", "Fix or remove.", referrers=refs[:25])
    cover("external-links", len(other), len(checked), f"--ext-cap; {len(unverifiable)} answered 401/403/429 (bot protection): UNVERIFIED")
    return {"unverifiable": unverifiable}


def _norm_lines(body):
    body = re.sub(r"(?is)<script\b[^>]*>.*?</script\s*>", "", body)
    return [ln.rstrip() for ln in body.replace("\r\n", "\n").split("\n")]


def provenance(F):
    served, canon = fetch(LANDING_PAIR[0]), fetch(LANDING_PAIR[1])
    if served["status"] != 200 or canon["status"] != 200:
        F.add("provenance", "P1", LANDING_PAIR[0], "Could not fetch served and canonical landing for comparison",
              f"served={served['status']} canonical={canon['status']}", "Keep the canonical path in the site's '4th wall' footer valid.")
        return {"state": "UNAVAILABLE"}
    a, b = _norm_lines(served["body"]), _norm_lines(canon["body"])
    sa, sb = set(a), set(b)
    extra = [ln for ln in a if ln not in sb]
    missing = [ln for ln in b if ln not in sa]
    # Declared deltas are edge injections only (Cloudflare beacons/email-decode, cache-buster query strings).
    # A changed line that merely *contains* href=/src= is still a content change and must stay visible.
    declared = re.compile(r"cdn-cgi|cloudflareinsights|__cf|data-cf-|cf-beacon|email-protection", re.I)
    buster = re.compile(r"([?&](?:v|ver|h|hash|t)=[\w.-]+)|(\.[0-9a-f]{8,}(?=\.(?:m?js|css)\b))", re.I)
    sb_norm = {buster.sub("", ln) for ln in b}
    sa_norm = {buster.sub("", ln) for ln in a}
    undeclared = [ln for ln in extra if ln.strip() and not declared.search(ln) and buster.sub("", ln) not in sb_norm] + \
                 [ln for ln in missing if ln.strip() and not declared.search(ln) and buster.sub("", ln) not in sa_norm]
    res = {"served_sha256": hashlib.sha256(served["body"].encode()).hexdigest(),
           "canonical_sha256": hashlib.sha256(canon["body"].encode()).hexdigest(),
           "byte_identical": served["body"] == canon["body"],
           "extra_lines": len(extra), "missing_lines": len(missing), "undeclared_delta_lines": len(undeclared),
           "method": "line-set diff after stripping <script> blocks, CRLF and trailing whitespace"}
    if undeclared:
        F.add("provenance", "P1" if len(undeclared) > 3 else "P2", LANDING_PAIR[0],
              f"Served landing differs from canonical beyond declared deltas ({len(undeclared)} lines)",
              " | ".join(("+ " if ln in extra else "- ") + ln.strip()[:100] for ln in undeclared[:5]),
              "Deploy from canonical bytes; declare every server-side rewrite (the page promises 'hash this page').")
    return res


def web_posture(pages, F):
    out = {}
    for d in DOMAINS:
        r = pages.get(f"https://{d}/")
        if not r or r["status"] != 200:
            continue
        h = r["headers"]
        gh_pages = "x-github-request-id" in h
        where = ("GitHub Pages cannot set response headers and ignores _headers: set them with a Cloudflare Transform Rule "
                 "(zone settings work order).") if gh_pages else "Set at the edge (Cloudflare Transform Rules / Worker response headers)."
        out[d] = {"github_pages": gh_pages, "headers": {k: h.get(k) for k in ("strict-transport-security", "content-security-policy",
                  "x-content-type-options", "referrer-policy", "permissions-policy", "x-frame-options")}}
        for hdr, sev in (("strict-transport-security", "P2"), ("content-security-policy", "P2"), ("x-content-type-options", "P3"),
                         ("referrer-policy", "P3"), ("permissions-policy", "P3")):
            if hdr not in h:
                F.add("web", sev, d, f"Missing {hdr}", "", where)
        hsts = h.get("strict-transport-security", "")
        m = re.search(r"max-age=(\d+)", hsts)
        if hsts and (not m or int(m.group(1)) < 31536000):
            F.add("web", "P3", d, "HSTS max-age below one year", hsts, "max-age=63072000; includeSubDomains")
        csp = h.get("content-security-policy", "")
        if csp and not re.search(r"(default|script)-src", csp):
            F.add("web", "P3", d, "CSP only restricts framing (no default-src/script-src)", csp[:200],
                  "Add a report-only script-src policy first, then enforce.")
        if "x-frame-options" not in h and "frame-ancestors" not in csp:
            F.add("web", "P3", d, "No clickjacking protection (X-Frame-Options / frame-ancestors)", "", "Add frame-ancestors 'self'. " + where)
        sec = pages.get(f"https://{d}/.well-known/security.txt")
        body = (sec or {}).get("body", "") if sec and sec["status"] == 200 else ""
        if not body or "contact:" not in body.lower():
            F.add("web", "P2", d, "No valid /.well-known/security.txt (Contact missing)", "", "Publish Contact + Expires (RFC 9116).")
        else:
            em = re.search(r"(?im)^expires:\s*(\S+)", body)
            if not em:
                F.add("web", "P2", d, "security.txt has no Expires field (required by RFC 9116)", body[:200], "Add Expires: <ISO date < 1 year ahead>.")
            else:
                try:
                    exp = dt.datetime.fromisoformat(em.group(1).replace("Z", "+00:00"))
                    exp = exp if exp.tzinfo else exp.replace(tzinfo=dt.timezone.utc)
                    if exp < NOW:
                        F.add("web", "P1", d, f"security.txt EXPIRED on {em.group(1)}", body[:200], "Renew Expires (< 1 year ahead).")
                    elif exp > NOW + dt.timedelta(days=366):
                        F.add("web", "P3", d, "security.txt Expires more than a year ahead", em.group(1), "RFC 9116 recommends < 1 year.")
                except ValueError:
                    F.add("web", "P2", d, "security.txt Expires is not an ISO 8601 date", em.group(1), "Use RFC 3339 format.")
        plain = fetch(f"http://{d}/", timeout=15, max_bytes=10_000, follow=False, retries=1)
        loc = plain["headers"].get("location", "")
        if plain["status"] == 200 or (300 <= plain["status"] < 400 and not loc.startswith("https://")):
            F.add("web", "P2", d, "HTTP does not redirect to HTTPS on the first hop", f"HTTP {plain['status']} location={loc}",
                  "Always Use HTTPS + HSTS preload.")
    return out


class DnsUnavailable(Exception):
    pass


def doh(name, rtype):
    """DNS-over-HTTPS (Cloudflare, fallback Google). Raises DnsUnavailable rather than pretending a record is absent."""
    for base in ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve"):
        st, js = jget(f"{base}?name={urllib.parse.quote(name)}&type={rtype}", accept="application/dns-json")
        if isinstance(js, dict) and js.get("Status") in (0, 3):  # NOERROR / NXDOMAIN are real answers
            return js
    raise DnsUnavailable(f"{name} {rtype}")


def dmarc_policy(records):
    """Return the p= tag of the first DMARC record (not sp=)."""
    for rec in records:
        tags = dict(t.strip().split("=", 1) for t in rec.strip('"').split(";") if "=" in t)
        if tags.get("v", "").upper() == "DMARC1":
            return tags.get("p", "").lower()
    return ""


def dns_posture(F, extra_domains, mail_domains):
    out = {}
    for d in list(dict.fromkeys(DOMAINS + mail_domains + extra_domains)):
        try:
            txt = [a.get("data", "") for a in doh(d, "TXT").get("Answer", []) if a.get("type") == 16]
            dmarc = [a.get("data", "") for a in doh(f"_dmarc.{d}", "TXT").get("Answer", []) if a.get("type") == 16
                     and "dmarc1" in a.get("data", "").lower()]
            caa = [a for a in doh(d, "CAA").get("Answer", []) if a.get("type") == 257]
            a_rec = doh(d, "A")
            mx = [a.get("data", "") for a in doh(d, "MX").get("Answer", []) if a.get("type") == 15]
        except DnsUnavailable as e:
            out[d] = {"role": "unknown", "state": "UNAVAILABLE", "resolves": None, "dnssec_ad": None, "mx": [], "spf": [], "dmarc": [], "caa": 0}
            F.add("dns", "P3", d, "DNS posture UNAVAILABLE (DoH lookups failed); no record findings emitted", str(e), "Re-run.")
            continue
        spf = [t for t in txt if "v=spf1" in t]
        role = "lookalike" if d in extra_domains and d not in DOMAINS + mail_domains else "mail" if mx else "web"
        out[d] = {"role": role, "resolves": bool(a_rec.get("Answer")), "dnssec_ad": a_rec.get("AD"), "mx": mx[:4], "spf": spf,
                  "dmarc": dmarc, "caa": len(caa)}
        if role == "lookalike":
            if out[d]["resolves"]:
                F.add("dns", "P2", d, "Look-alike domain resolves (not owned per site footer): brand confusion risk", out[d],
                      "Decide brand/domain strategy (acquire, or state 'never a11oy.com' on every surface).")
            continue
        if not spf:
            F.add("dns", "P2", d, "No SPF record", "", "Publish v=spf1 ... -all (or v=spf1 -all if the domain sends no mail).")
        elif mx and re.search(r"[~?]all", " ".join(spf)):
            F.add("dns", "P3", d, "SPF ends in soft-fail (~all) on a mail-sending domain", spf,
                  "Move to -all once DMARC reports show only legitimate senders.")
        if not dmarc:
            F.add("dns", "P1", d, "No DMARC record: domain spoofable in phishing" + (" (this is the MAIL domain)" if mx else ""), "",
                  "Publish v=DMARC1; p=none; rua=mailto:dmarc@<domain> now, then quarantine, then reject.")
        elif dmarc_policy(dmarc) not in ("reject", "quarantine"):
            F.add("dns", "P2", d, f"DMARC policy is not enforcing (p={dmarc_policy(dmarc) or 'missing'})", dmarc,
                  "Move to p=quarantine then p=reject.")
        if not caa:
            F.add("dns", "P3", d, "No CAA record", "", "Restrict issuing CAs (e.g. letsencrypt.org, pki.goog, digicert.com).")
        if not a_rec.get("AD"):
            F.add("dns", "P3", d, "DNSSEC not validated (AD flag false)", "", "Enable DNSSEC at the DNS host + registrar DS.")
    return out


def narrative(pages, F):
    stats = {}
    for d in DOMAINS:
        r = pages.get(f"https://{d}/")
        if not r or r["status"] != 200:
            continue
        txt = text_of(r["body"])
        words = re.findall(r"[A-Za-zÀ-ÿ']+", txt)
        n = max(len(words), 1)
        sentences = max(len(re.findall(r"[.!?](\s|$)", txt)), 1)
        syll = sum(max(1, len(re.findall(r"[aeiouy]+", w.lower()))) for w in words)
        flesch = round(206.835 - 1.015 * (n / sentences) - 84.6 * (syll / n), 1)
        low = txt.lower()
        jargon = {}
        for j in JARGON:
            k = len(re.findall(r"(?<![\w-])" + re.escape(j) + r"(?![\w-])", low))
            if k:
                jargon[j] = k
        placeholders = len(PLACEHOLDER_NODE.findall(re.sub(r"(?is)<(script|style|template)\b[^>]*>.*?</\1\s*>", " ", r["body"])))
        caps_labels = len(re.findall(r"\b[A-Z]{4,}(?:[- ][A-Z]{3,})*\b", txt))
        cta = re.search(r"\b(book|request|contact|verify a receipt|get started|pilot|talk to)\b", low)
        stats[d] = {"words": n, "flesch": flesch, "jargon_hits": sum(jargon.values()), "jargon": jargon,
                    "placeholders_no_js": placeholders, "all_caps_labels": caps_labels,
                    "words_before_first_cta": len(re.findall(r"\w+", low[: cta.start()])) if cta else None}
        if placeholders > 15:
            F.add("narrative", "P1", d, f"{placeholders} placeholder text nodes (UNAVAILABLE/CHECKING/—) in no-JS HTML",
                  "", "Server-render last-known-good MEASURED values with timestamps (F2).")
        if n > 2500:
            F.add("narrative", "P2", d, f"Landing page is {n} words", "", "Cut the first screen to <150 words; move depth to /diligence.")
        if flesch < 30:
            F.add("narrative", "P2", d, f"Readability Flesch {flesch} (very difficult)", "", "Shorter sentences, fewer coined terms above the fold.")
        if sum(jargon.values()) / n * 1000 > 15:
            F.add("narrative", "P2", d, f"Jargon density {round(sum(jargon.values()) / n * 1000, 1)} per 1,000 words", jargon,
                  "Glossary page; plain-language hero.")
        if caps_labels / n * 1000 > 40:
            F.add("narrative", "P3", d, f"{caps_labels} ALL-CAPS labels", "", "Keep honesty labels, but cap them to one per card above the fold.")
        if stats[d]["words_before_first_cta"] is None:
            F.add("narrative", "P2", d, "No call to action found on the landing page", "", "One CTA in the first screen (F1).")
        elif stats[d]["words_before_first_cta"] > 150:
            F.add("narrative", "P3", d, f"{stats[d]['words_before_first_cta']} words before the first call to action", "", "Move the CTA into the hero.")
    return stats


def estate_checks(repos, hf, F):
    live = [r for r in repos if not r.get("archived") and not r.get("private")]
    if len(live) > 60:
        F.add("estate", "P2", "szl-holdings", f"{len(live)} active public repos", "", "Consolidate to a few dozen canonical repos (manifest-driven).")
    stubs = [m["id"] for m in hf["models"] if set(m.get("tags", [])) & {"roadmap", "alias", "org-stub", "not-a-model", "no-weights"}]
    if stubs:
        F.add("estate", "P2", "SZLHOLDINGS", f"{len(stubs)} roadmap/stub cards in Models", ", ".join(stubs[:10]), "Move to the ROADMAP collection only.")


def import_reports(paths, F):
    got = {}
    for p in paths or []:
        try:
            js = json.loads(Path(p).read_text(encoding="utf-8-sig"))
        except Exception as e:
            F.add("imported", "P3", p, "Could not read imported report", f"{type(e).__name__}: {e}", "")
            continue
        if "severity_counts" in js:
            got["audit"] = {"file": str(p), "generated_at": js.get("generated_at"), "severity_counts": js["severity_counts"],
                            "top": [f"{f.get('severity') or f.get('sev')} {f.get('title', '')[:100]}" for f in (js.get("findings") or [])
                                    if (f.get("severity") or f.get("sev")) in ("P0", "P1")][:8]}
            if js["severity_counts"].get("P0"):
                F.add("imported", "P0", p, f"Estate audit reports {js['severity_counts']['P0']} P0 findings", "", "Resolve before any investor share.")
        if "scorecards" in js:
            got["agents"] = {"file": str(p), "generated_at": js.get("generated_at"), "scorecards": js["scorecards"]}
    return got


# ------------------------------------------------------------------------------------------------ report
INCOMPLETE = set()


def guarded(F, name, cat, fn, *args, default=None):
    """Run one check; a crash becomes a P1 finding and marks the pillar incomplete instead of killing the report."""
    try:
        return fn(*args)
    except Exception as e:
        F.add(cat, "P1", f"compass:{name}", f"Compass check '{name}' crashed: {type(e).__name__}", redact(str(e))[:300],
              "Fix the compass; this pillar's findings are incomplete for this run.")
        INCOMPLETE.add(cat)
        return default


def score(F):
    sev_w = {"P0": 25, "P1": 10, "P2": 4, "P3": 1}
    return {pillar: max(0, 100 - sum(sev_w[f["sev"]] for f in F.items if f["cat"] in cats)) for pillar, cats in PILLARS.items()}


def diff_baseline(F, path):
    if not path:
        return None
    try:
        old = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    old_fp = {f.get("fp"): f for f in old.get("findings", []) if f.get("fp")}
    new_fp = {f["fp"]: f for f in F.items}
    return {"baseline": str(path), "baseline_generated_at": old.get("generated_at"),
            "new": [f"{f['sev']} {f['title']}" for fp, f in new_fp.items() if fp not in old_fp][:40],
            "resolved": [f"{f['sev']} {f['title']}" for fp, f in old_fp.items() if fp not in new_fp][:40],
            "new_count": sum(1 for fp in new_fp if fp not in old_fp), "resolved_count": sum(1 for fp in old_fp if fp not in new_fp)}


def _w(path, text):
    path.write_text(text, encoding="utf-8", newline="\n")


def write(out, F, data):
    out.mkdir(parents=True, exist_ok=True)
    F.items.sort(key=lambda f: (SEV_ORDER.index(f["sev"]), f["cat"], f["target"]))
    chain = "0" * 64
    for f in F.items:
        chain = hashlib.sha256((chain + json.dumps(f, sort_keys=True)).encode()).hexdigest()
    data.update({"findings": F.items, "receipt_root": chain, "signature": "UNSIGNED_HONEST", "recommendations": RECOMMENDATIONS})
    _w(out / "compass_report.json", json.dumps(data, indent=2, default=str, ensure_ascii=False) + "\n")
    sev = data["severity"]
    sc = {k: (f"{v} (incomplete)" if any(c in INCOMPLETE for c in PILLARS[k]) else v) for k, v in data["pillars"].items()}
    L = data.get("lean") or {}
    canon = (L.get("canonical") or {})
    M = [f"# SZL Board Memo — Frontier Compass · {NOW:%Y-%m-%d %H:%M UTC}", "",
         f"`{VERSION}` · receipt root `{chain[:16]}…` (UNSIGNED_HONEST) · {sev['P0']} P0 · {sev['P1']} P1 · {sev['P2']} P2 · {sev['P3']} P3", "",
         "## Pillar scores (100 = no findings)", "",
         "| " + " | ".join(sc) + " |", "|" + "---|" * len(sc), "| " + " | ".join(str(v) for v in sc.values()) + " |", ""]
    cm = data["counts_measured"]
    M += ["## Measured estate (public view)", "",
          f"- GitHub `{data['gh_org']}`: **{cm.get('repos')}** active public repos ({cm.get('repos_total')} incl. archived; state {data['estate_state'].get('github')}).",
          f"- Hugging Face `{data['hf_org']}`: **{cm.get('models')}** models · **{cm.get('datasets')}** datasets · **{cm.get('spaces')}** Spaces (public)."]
    if canon.get("numbers"):
        n = canon["numbers"]
        lk, hd = L.get("locked") or {}, L.get("head") or {}
        rep = {True: "**REPRODUCES**", False: "**DOES NOT REPRODUCE**", None: "UNAVAILABLE"}[L.get("locked_reproduces")]
        M += [f"- Lean (canonical LOCKED `{canon.get('sha')}`, measured {canon.get('measured_at_utc', '')[:10]}): {n.get('declarations')} declarations · "
              f"{n.get('axioms_unique')} axioms · {n.get('sorries_raw')} sorries — recount with the canonical method {rep}."]
        if hd.get("state") == "MEASURED":
            M += [f"- Lean main HEAD `{hd['sha'][:8]}` ({hd['committed_at'][:10]}): {hd['declarations']} declarations · {hd['axioms_unique']} axioms · "
                  f"{hd['sorries_raw']} sorries ({hd['sorries_noncomment']} non-comment). Λ uniqueness stays Conjecture 1."]
    M += ["", "## Truth ledger (every numeric claim found, by class)", "", "| Key | " + " | ".join(data["claim_classes"]) + " |",
          "|---|" + "---|" * len(data["claim_classes"])]
    for key, row in sorted(data["claims_summary"].items()):
        M.append(f"| `{key}` | " + " | ".join(str(row.get(c, 0)) for c in data["claim_classes"]) + " |")
    M += ["", "Only UNEXPLAINED, DISSENT and STALE become findings. CANONICAL = matches lean_numbers.json; CURRENT = matches today's "
          "measurement; CONSENSUS = the majority value across surfaces; SCOPED = a sub-scope figure (e.g. 0 sorries in the locked formulas); "
          "NEGATED = 'roadmap / not claimed' context; HISTORICAL = dated/labelled in context.", ""]
    M += ["## Top findings", "", "| Sev | Pillar | Target | Finding |", "|---|---|---|---|"]
    M += [f"| {f['sev']} | {f['cat']} | `{f['target'][:70]}` | {f['title']} |" for f in F.items[:20]]
    if data.get("diff"):
        dd = data["diff"]
        M += ["", f"## Since last run ({dd.get('baseline_generated_at', '?')})", "",
              f"- New: {dd.get('new_count', 0)} · Resolved: {dd.get('resolved_count', 0)}"]
        M += [f"  - NEW {x}" for x in dd.get("new", [])[:10]] + [f"  - RESOLVED {x}" for x in dd.get("resolved", [])[:10]]
    M += ["", "## Narrative", ""] + [f"- **{d}**: {s['words']} words · Flesch {s['flesch']} · {s['placeholders_no_js']} no-JS placeholder nodes · "
                                      f"jargon {s['jargon_hits']} · words before first CTA {s['words_before_first_cta']}" for d, s in data["narrative"].items()]
    M += ["", "## Domains", "", "| Domain | Role | SPF | DMARC | CAA | DNSSEC |", "|---|---|---|---|---|---|"]
    for d, v in data["dns"].items():
        M.append(f"| {d} | {v['role']} | {'; '.join(x.strip(chr(34))[:40] for x in v['spf']) or '—'} | "
                 f"{'; '.join(x.strip(chr(34))[:48] for x in v['dmarc']) or '**none**'} | {v['caa'] or '—'} | {'yes' if v['dnssec_ad'] else 'no'} |")
    M += ["", "## Coverage (nothing silently capped)", ""]
    M += [f"- `{k}`: checked {v['checked']}/{v['total']}" + (" **TRUNCATED**" if v["truncated"] else "") + (f" — {v['note']}" if v.get("note") else "")
          for k, v in sorted(COVERAGE.items())]
    M += [f"- HTTP calls {data['http'].get('http', 0)} · GitHub REST {data['http'].get('github_rest', 0)}"
          + (" · **REST QUOTA EXHAUSTED mid-run: GitHub-derived checks are partial**" if data["http"].get("github_rest_exhausted") else "")]
    if data.get("imported"):
        M += ["", "## Imported payload results", "", "```", json.dumps(data["imported"], indent=2, ensure_ascii=False)[:1800], "```"]
    M += ["", "## Recommendations", ""] + [f"- **{i} {t}.** {d}" for i, t, d in RECOMMENDATIONS]
    M += ["", "## 30 / 60 / 90", "",
          "- **30 days:** fix every P0/P1 above; server-render last-known-good; one number source; DMARC on the mail domain; kill dead links.",
          "- **60 days:** five-second hero; estate consolidation; attribution kit live; external security review booked; verifier on PyPI/npm.",
          "- **90 days:** one design partner with an externally reproduced receipt; nightly compass green; board memo auto-posted weekly."]
    _w(out / "BOARD_MEMO.md", "\n".join(M) + "\n")
    W = ["# Work orders", "", f"Generated by `{VERSION}` at {NOW:%Y-%m-%d %H:%M UTC}. Fingerprint `fp` is stable across runs.", ""]
    for cat in sorted({f["cat"] for f in F.items}):
        fs = [f for f in F.items if f["cat"] == cat and f["sev"] in ("P0", "P1", "P2")]
        if not fs:
            continue
        W += [f"## {cat}", ""]
        W += [f"### [{f['sev']}] {f['title']}\n- Target: `{f['target']}`\n- Evidence: {f['evidence']}\n- Fix: {f['rec']}\n- fp: `{f['fp']}`\n"
              for f in fs]
    _w(out / "WORK_ORDERS.md", "\n".join(W) + "\n")


def receipt(path, action, result, evidence):
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "lane": "szl_frontier_compass",
            "action": action, "result": redact(result), "evidence": redact(evidence)}
    with open(p, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")


def file_issues(F, repo, cap, receipts, include_security=False, cats=None):
    if os.environ.get(CONFIRM_ENV) != CONFIRM_VALUE:
        print(f"REFUSED: set {CONFIRM_ENV}={CONFIRM_VALUE} to file issues.", file=sys.stderr)
        return []
    if not GH:
        print("REFUSED: GITHUB_TOKEN required to file issues.", file=sys.stderr)
        return []
    cap = max(0, min(int(cap), 50))
    groups = defaultdict(list)
    for f in F.items:
        if f["sev"] in ("P0", "P1") and (include_security or f["cat"] not in SECURITY_CATS) and (not cats or f["cat"] in cats):
            groups[(f["cat"], re.sub(r"[0-9]+", "#", f["title"])[:90])].append(f)
    done = []
    items = list(groups.items())
    for (cat, title), _fs in items[cap:]:
        done.append(f"DEFERRED (issue cap {cap}): [{cat}] {title}")
    for (cat, title), fs in items[:cap]:
        fp = hashlib.sha256(f"{cat}|{title}".encode()).hexdigest()[:16]
        q = urllib.parse.quote(f'repo:{repo} is:issue is:open in:body "compass-fp:{fp}"')
        st, js = jget(f"https://api.github.com/search/issues?q={q}")
        if st != 200 or not isinstance(js, dict):
            done.append(f"SKIPPED {cat}: idempotency search HTTP {st}")
            continue
        if js.get("total_count"):
            done.append(f"EXISTS {js['items'][0].get('html_url')}")
            continue
        t = f"[compass:{cat}] {fs[0]['title']}" + (f" (+{len(fs) - 1} similar)" if len(fs) > 1 else "")
        body = f"<!-- szl-frontier-compass -->\nGenerated by `{VERSION}` at {NOW:%Y-%m-%d %H:%M UTC}. " \
               f"Evidence or UNREVIEWED; heuristics are labelled.\n\n" + "\n".join(
                   f"- **{f['sev']}** `{f['target']}` — {f['evidence'][:400]}\n  - Fix: {f['rec']}" for f in fs[:40])
        body = re.sub(r"@(?=[A-Za-z0-9])", "@​", redact(body))[:59000] + f"\n\n---\ncompass-fp:{fp}\n"  # no @-mention pings
        rq = urllib.request.Request(f"https://api.github.com/repos/{repo}/issues", method="POST",
                                    data=json.dumps({"title": t[:250], "body": body}).encode(),
                                    headers={"Authorization": f"Bearer {GH}", "Accept": "application/vnd.github+json",
                                             "Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(rq, timeout=30) as r:
                url = json.loads(r.read()).get("html_url")
                done.append(url)
                receipt(receipts, f"file work-order issue [{cat}] {title[:80]}", url, f"compass-fp:{fp}")
        except Exception as e:
            done.append(f"FAILED {t[:80]}: {type(e).__name__}")
            receipt(receipts, f"file work-order issue [{cat}] {title[:80]}", f"FAILED {type(e).__name__}", f"compass-fp:{fp}")
        time.sleep(2.5)
    return done


def main(argv=None):
    ap = argparse.ArgumentParser(description=VERSION)
    ap.add_argument("--gh-org", default="szl-holdings")
    ap.add_argument("--hf-org", default="SZLHOLDINGS")
    ap.add_argument("--out", default="szl-compass-out")
    ap.add_argument("--max-pages", type=int, default=60)
    ap.add_argument("--ext-cap", type=int, default=150)
    ap.add_argument("--stale-days", type=int, default=14)
    ap.add_argument("--lean-cap", type=int, default=2000)
    ap.add_argument("--no-lean", action="store_true", help="skip the Lean recount (canonical JSON still read)")
    ap.add_argument("--readme-cap", type=int, default=40)
    ap.add_argument("--card-cap", type=int, default=40, help="HF README cards fetched per kind")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--lookalikes", default="a11oy.com", help="comma list of look-alike domains to check")
    ap.add_argument("--mail-domains", default="szlholdings.com", help="comma list of owned mail domains (DMARC matters most here)")
    ap.add_argument("--import", dest="imports", nargs="*", help="report.json / agent_report.json from sibling payloads")
    ap.add_argument("--baseline", help="previous compass_report.json for a new/resolved diff")
    ap.add_argument("--fail-on", default="P0", choices=["P0", "P1", "P2", "P3", "none"],
                    help="exit non-zero if any finding at or above this severity (CI gate)")
    ap.add_argument("--file-issues", action="store_true")
    ap.add_argument("--issue-repo", default=None, help="default <gh-org>/.github")
    ap.add_argument("--issue-cap", type=int, default=25)
    ap.add_argument("--issues-include-security", action="store_true", help="also file web/dns posture findings publicly")
    ap.add_argument("--issue-cats", default="", help="comma list: only file these categories (e.g. freshness,narrative)")
    ap.add_argument("--receipts", default=str(DEFAULT_RECEIPTS) if DEFAULT_RECEIPTS.parent.exists() else "")
    a = ap.parse_args(argv)
    F = Findings()
    t0 = time.time()
    log("crawling origins…")
    pages, external, referrers = {}, set(), defaultdict(set)
    for d in DOMAINS:
        p, e = crawl(d, a.max_pages, referrers)
        pages.update(p)
        external |= e
    guarded(F, "internal_pages", "links", internal_pages, pages, referrers, F)
    contracts = guarded(F, "machine_contracts", "contracts", machine_contracts, pages, F, default={})
    log("estate truth…")
    repos, hf, est_state = estate_truth(a.gh_org, a.hf_org)
    for src, st in est_state.items():
        if st != "MEASURED":
            F.add("estate", "P1", f"{a.gh_org if src == 'github' else a.hf_org}:{src}", f"Inventory source {src} UNAVAILABLE: dependent checks skipped",
                  st, "Re-run with a valid token; the board view is incomplete until this source is MEASURED.")
            INCOMPLETE.update({"claims", "links", "estate"})
    pub = [r for r in repos if not r.get("private")]
    ok = lambda s: est_state.get(s) == "MEASURED"  # noqa: E731
    counts = {"repos": sum(1 for r in pub if not r.get("archived")) if ok("github") else None,
              "repos_total": len(pub) if ok("github") else None,
              "models": len(hf["models"]) if ok("hf_models") else None, "spaces": len(hf["spaces"]) if ok("hf_spaces") else None,
              "datasets": len(hf["datasets"]) if ok("hf_datasets") else None}
    log("lean truth (canonical method, locked + main)…")
    lean = guarded(F, "lean_truth", "lean", lean_truth, a.workers, a.lean_cap, F, not a.no_lean, default={"state": "UNAVAILABLE"})
    log("claims across surfaces…")
    surfaces = {u: (text_of(r["body"]) if "html" in r["headers"].get("content-type", "") else r["body"])
                for u, r in pages.items() if r["status"] == 200}
    for r in pub:
        if r.get("description"):
            surfaces[f"github:{r['full_name']}#description"] = r["description"]
    ranked = sorted((r for r in pub if not r.get("archived")), key=lambda r: -(r.get("stargazers_count") or 0) - (100 if r["name"] in
                    ("a11oy", "killinchu", "szl-router", "immune", "lutar-lean", ".github", "a11oy-net", "szl-doctrine") else 0))
    readme_targets = ranked[: a.readme_cap]
    cover("github-readmes", len(ranked), len(readme_targets), "--readme-cap (ranked by stars + flagships)")
    for r, rr in pmap(lambda r: (r, fetch(f"https://api.github.com/repos/{r['full_name']}/readme", accept="application/vnd.github.raw")),
                      readme_targets, a.workers):
        if rr["status"] == 200:
            surfaces[f"github:{r['full_name']}#README"] = rr["body"]
    prof = fetch(f"https://raw.githubusercontent.com/{a.gh_org}/.github/main/profile/README.md")
    if prof["status"] == 200:
        surfaces["github:org-profile"] = prof["body"]
    card_jobs = []
    for kind in ("models", "spaces", "datasets"):
        pre = {"models": "", "spaces": "spaces/", "datasets": "datasets/"}[kind]
        card_jobs += [f"{pre}{x['id']}" for x in hf[kind][: a.card_cap]]
        cover(f"hf-cards:{kind}", len(hf[kind]), min(len(hf[kind]), a.card_cap), "--card-cap")
    for rid, rr in pmap(lambda rid: (rid, fetch(f"https://huggingface.co/{rid}/raw/main/README.md", max_bytes=300_000)), card_jobs, a.workers):
        if rr["status"] == 200:
            surfaces[f"hf:{rid}"] = rr["body"]
    claims = guarded(F, "extract_claims", "claims", extract_claims, surfaces, default=[])
    truth = {"lean": lean, "counts": counts}
    consensus = guarded(F, "classify_claims", "claims", classify_claims, claims, truth, default={})
    for c in claims:
        c.setdefault("cls", "UNCHECKED")
    guarded(F, "check_claims", "claims", check_claims, claims, truth, consensus, F)
    classes = ["CANONICAL", "CURRENT", "CONSENSUS", "SCOPED", "NEGATED", "HISTORICAL", "UNCHECKED", "UNEXPLAINED", "DISSENT", "STALE"]
    summary = defaultdict(Counter)
    for c in claims:
        summary[c["key"]][c["cls"]] += 1
    guarded(F, "freshness", "freshness", freshness, pages, a.stale_days, F)
    log("links, provenance, posture…")
    links = guarded(F, "link_integrity", "links", link_integrity, external, referrers, repos, hf, est_state, a.hf_org, a.gh_org,
                    a.ext_cap, a.workers, F, default={"unverifiable": []})
    prov = guarded(F, "provenance", "provenance", provenance, F, default={"state": "UNAVAILABLE"})
    web = guarded(F, "web_posture", "web", web_posture, pages, F, default={})
    mail = [x.strip() for x in a.mail_domains.split(",") if x.strip()]
    dns = guarded(F, "dns_posture", "dns", dns_posture, F, [x.strip() for x in a.lookalikes.split(",") if x.strip()], mail, default={})
    narr = guarded(F, "narrative", "narrative", narrative, pages, F, default={})
    guarded(F, "estate_checks", "estate", estate_checks, repos, hf, F)
    imported = guarded(F, "import_reports", "imported", import_reports, a.imports, F, default={})
    sev = {s: sum(1 for f in F.items if f["sev"] == s) for s in SEV_ORDER}
    data = {"payload": VERSION, "generated_at": NOW.isoformat(), "runtime_s": round(time.time() - t0, 1), "gh_org": a.gh_org,
            "hf_org": a.hf_org, "view": "public (private repos/HF items filtered out)", "counts_measured": counts,
            "estate_state": est_state, "lean": lean, "consensus": consensus, "claim_classes": classes,
            "claims_summary": {k: dict(v) for k, v in summary.items()}, "provenance": prov, "web": web, "dns": dns,
            "narrative": narr, "contracts": contracts, "imported": imported, "claims": claims,
            "unverifiable_links": links["unverifiable"], "coverage": COVERAGE, "http": dict(STATS),
            "pages": {u: {"status": r["status"], "ms": r["ms"], "bytes": len(r["body"])} for u, r in pages.items()},
            "external_links": len(external), "severity": sev, "pillars": score(F), "pillars_incomplete": sorted(INCOMPLETE),
            "diff": diff_baseline(F, a.baseline)}
    out = Path(a.out)
    write(out, F, data)
    if a.file_issues:
        data["issues_filed"] = file_issues(F, a.issue_repo or f"{a.gh_org}/.github", a.issue_cap, a.receipts, a.issues_include_security,
                                           {x.strip() for x in a.issue_cats.split(",") if x.strip()})
        _w(out / "compass_report.json", json.dumps(data, indent=2, default=str, ensure_ascii=False) + "\n")
    print(json.dumps({"out": str(out.resolve()), "pillars": data["pillars"], "severity": sev, "claims": len(claims),
                      "lean_locked_reproduces": lean.get("locked_reproduces"), "runtime_s": data["runtime_s"],
                      "issues_filed": data.get("issues_filed")}, indent=2, ensure_ascii=False))
    if sev["P0"]:
        return 2
    if a.fail_on != "none" and any(sev[s] for s in SEV_ORDER[: SEV_ORDER.index(a.fail_on) + 1]):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
