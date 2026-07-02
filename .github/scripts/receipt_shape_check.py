#!/usr/bin/env python3
"""Org-wide receipt shape-conformance honesty guard.

The honesty doctrine forbids fabricating a pass. A receipt that *declares* itself
to be a well-known attestation format but is structurally broken is a quiet way
to fake one: a consumer (or a badge) sees the familiar `_type` / `payloadType`
and assumes a real, verifiable attestation, when a real verifier would reject it.
This guard is the net for that failure. The overclaim sweep reads governed
Markdown; the energy-provenance guard checks joules in receipt data; NEITHER
checks whether a declared-format receipt actually has that format's shape.

It is deliberately FORMAT-CONDITIONAL, never schema-imposing. The org carries
several honest receipt shapes on purpose (in-toto Statements, DSSE envelopes,
bespoke szl receipts, Khipu quorum verdicts, JSON-LD contexts, JSON Schemas).
Forcing one canonical shape was rejected once already — it invents a fake
contract and punishes honest-but-different producers. So this guard validates a
blob ONLY when the blob itself DECLARES a known format via that format's own
discriminator, and stays completely silent otherwise. Detection is conjunctive
and type-based (a discriminator that is the wrong TYPE does not trigger a rule),
which is what lets JSON-Schema files, JSON-LD contexts and Khipu vector fixtures
pass untouched even though they mention receipt-ish keys.

It shares the sibling energy guard's single lens: FABRICATION is the sin, honest
ABSENCE is not. A receipt that leaves a field absent / null / empty is in the
honest measured-or-UNAVAILABLE state and is NEVER flagged — the org ships such
honest stubs on PURPOSE (e.g. an in-toto Statement whose `subject.digest.sha256`
is intentionally "" with a "PENDING BUILD — nothing fabricated" note; leaving it
empty is the whole point, so a verifier isn't fooled). ONLY a field that is
PRESENT but the WRONG TYPE is flagged: a wrong-type value can never be an honest
absence, only structural corruption a real parser / verifier would choke on. So
these are TYPE-conformance rules, not completeness rules — a completeness guard
would do zero security work (a fabricated pass supplies a plausible *present*
value, never an empty one) while punishing the org's documented honest stubs.

Two format rules, applied only on a positive, typed match:

  S1  in-toto Statement — a dict whose `_type` is EXACTLY one of
        "https://in-toto.io/Statement/v1" or ".../Statement/v0.1"
      (the org uses both: v0.1 top-level in szl-lake/killinchu attestations, v1
      inside DSSE payloads). When PRESENT, each field must be the right TYPE:
        - `subject`, if present, is a list; each entry is a dict;
        - a subject's `digest`, if present, is a dict whose values are strings;
        - `predicateType`, if present, is a string.
      Absent / null / empty is honest UNAVAILABLE and is NEVER flagged — an empty
      `subject`, an empty-string digest, or a missing `predicateType` are all the
      honest "not measured yet" state (the string-slot analog of the energy
      guard's `joules: null`), not a violation. No digest hex-length / algorithm
      check either (honest org attestations carry 40-hex values under a `sha256`
      key; a length rule is a data-quality opinion, not a shape violation, and
      would punish honest producers).

  S2  DSSE envelope — a dict where `payloadType` (or `payload_type`) is a
      non-empty string AND `payload` is a string (the same trigger the energy
      guard uses to recurse). When PRESENT, each field must be the right TYPE:
        - a non-empty `payload` is base64-decodable;
        - `signatures`, if present, is a list; each entry is a dict; each entry's
          `sig`, if present, is a string.
      Absent / null / empty is honest UNAVAILABLE and is NEVER flagged — an
      UNSIGNED envelope, an empty payload, or a signature slot with no `sig` are
      all first-class honest states (a receipt is left unsigned so the cockpit
      shows an honest UNAVAILABLE badge rather than a fabricated pass); requiring
      a signature would punish that honesty. A bespoke envelope that signs via a
      different key (`signature` singular, `signed`, …) is likewise left alone —
      only a `signatures` LIST with a wrong-typed entry / sig is a violation.

  After a DSSE payload decodes it is parsed as JSON and recursed into, so an
  in-toto Statement wrapped in a DSSE envelope still gets its S1 shape checked.

What it deliberately does NOT do (honest limitations, not oversights):
  * It does not check completeness — an absent / null / empty field is honest
    UNAVAILABLE, never a violation; only present-but-wrong-type data is flagged.
  * It does not validate signatures cryptographically (no keys here) — only that
    a present signature entry is structurally a signature.
  * It does not parse or schema-check the DSSE payload's semantics (only that it
    base64-decodes); a payload that decodes to non-JSON is left alone.
  * It does not touch blobs that declare no known format (Khipu verdicts, plain
    ledgers, config) — no discriminator, no rule.

Two modes (mirrors energy_provenance_check.py / overclaim_sweep.py):

  * ORG mode (default): list every PUBLIC repo, walk its default-branch tree,
    fetch the receipt-ish `.json` / `.jsonl` blobs (paths matching
    receipt|attest|dsse|provenance|evidence|intoto|in-toto|statement|slsa|
    cosign|sbom, plus any `extra_data_surfaces` from the allowlist; use
    `--all-json` for a thorough catch-all over every committed .json/.jsonl),
    run the format rules, write a JSON report, exit non-zero on any violation.

  * LOCAL mode (`--local DIR`): recursively scan a checkout's .json/.jsonl.
    Used by the reusable per-repo guard (full-tree net) and by the self-test.
    No network or token required.

Auth (ORG mode only): $SZL_GITHUB_TOKEN / $GH_TOKEN / $GITHUB_TOKEN. Every repo
is public so the built-in Actions token is sufficient.

Exit code 0 = clean; 1 = at least one declared-format receipt is malformed.
"""
from __future__ import annotations

import argparse
import base64
import binascii
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

MAX_BYTES = 2_000_000
SKIP_DIRS = {
    "node_modules", "dist", "build", ".git", "vendor", ".next",
    "coverage", "__pycache__", ".venv", "venv", ".turbo",
}
# Basenames that are never receipt data and are cheap to skip (lockfiles etc.).
NOISE_BASENAMES = {"package-lock.json", "composer.lock", "yarn.lock"}
# ORG-mode default path filter: only fetch receipt-ish data blobs (bounded).
RECEIPT_PATH_RE = re.compile(
    r"receipt|attest|dsse|provenance|evidence|intoto|in-toto|statement|slsa|"
    r"cosign|sbom|\.sig",
    re.IGNORECASE,
)

# in-toto Statement discriminators the org actually uses (both versions).
INTOTO_STATEMENT_TYPES = {
    "https://in-toto.io/Statement/v1",
    "https://in-toto.io/Statement/v0.1",
}


# --------------------------------------------------------------------------- #
# Invariant engine (format-conditional, recursive) — the single source of
# truth. The reusable per-repo guard runs THIS file (checks out
# szl-holdings/.github@main), so there is no inline duplication to keep in
# lockstep.
# --------------------------------------------------------------------------- #
def _nonempty_str(x) -> bool:
    return isinstance(x, str) and x.strip() != ""


def _b64decode_maybe(s: str):
    if not isinstance(s, str) or len(s) < 8:
        return None
    padded = s + "=" * (-len(s) % 4)
    for dec in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            return dec(padded)
        except (binascii.Error, ValueError):
            continue
    return None


def _typename(x) -> str:
    if x is None:
        return "null"
    return type(x).__name__


def _check_intoto_statement(obj, loc, out):
    """S1 — TYPE-conformance for a dict that DECLARES an in-toto Statement.

    Absent / null / empty is honest UNAVAILABLE and is NEVER flagged
    (measured-or-UNAVAILABLE). Only a field that is PRESENT but the WRONG TYPE —
    which can never be an honest absence, only corruption — is a violation.
    """
    itype = obj.get("_type")
    subject = obj.get("subject")
    if subject is not None and not isinstance(subject, list):
        out.append((loc, "S1",
                    f"in-toto Statement (_type={itype}) 'subject' must be a list "
                    f"when present; got {_typename(subject)}"))
    elif isinstance(subject, list):
        for i, s in enumerate(subject):
            if not isinstance(s, dict):
                out.append((f"{loc}.subject[{i}]", "S1",
                            "in-toto subject entry must be an object when present; "
                            f"got {_typename(s)}"))
                continue
            digest = s.get("digest")
            if digest is not None and not isinstance(digest, dict):
                out.append((f"{loc}.subject[{i}].digest", "S1",
                            "in-toto subject 'digest' must be an object when "
                            f"present; got {_typename(digest)}"))
            elif isinstance(digest, dict):
                for algo, val in digest.items():
                    if val is not None and not isinstance(val, str):
                        out.append((f"{loc}.subject[{i}].digest.{algo}", "S1",
                                    f"in-toto subject digest '{algo}' must be a "
                                    f"string when present; got {_typename(val)}"))
    ptype = obj.get("predicateType")
    if ptype is not None and not isinstance(ptype, str):
        out.append((loc, "S1",
                    "in-toto Statement 'predicateType' must be a string when "
                    f"present; got {_typename(ptype)}"))


def _check_dsse_envelope(obj, loc, out):
    """S2 — TYPE-conformance for a dict that DECLARES a DSSE envelope.

    Called only when payloadType is a non-empty string and payload is a string.
    Absent / null / empty is honest UNAVAILABLE and is NEVER flagged — an unsigned
    envelope, an empty payload, and a signature slot with no `sig` are first-class
    honest states; only PRESENT-but-wrong-type structure is a violation.
    """
    payload = obj.get("payload")
    if isinstance(payload, str) and payload != "" and _b64decode_maybe(payload) is None:
        out.append((loc, "S2",
                    "DSSE envelope 'payload' is non-empty but not base64-decodable "
                    "(a DSSE payload MUST be base64-encoded)"))
    sigs = obj.get("signatures")
    if sigs is not None and not isinstance(sigs, list):
        out.append((loc, "S2",
                    f"DSSE 'signatures' must be a list when present; "
                    f"got {_typename(sigs)}"))
    elif isinstance(sigs, list):
        for i, sg in enumerate(sigs):
            if not isinstance(sg, dict):
                out.append((f"{loc}.signatures[{i}]", "S2",
                            "DSSE signature entry must be an object when present; "
                            f"got {_typename(sg)}"))
                continue
            sig = sg.get("sig")
            if sig is not None and not isinstance(sig, str):
                out.append((f"{loc}.signatures[{i}].sig", "S2",
                            "DSSE signature 'sig' must be a string when present; "
                            f"got {_typename(sig)}"))


def check_obj(obj, loc, out):
    """Recurse through a decoded JSON value, appending (locator, rule, detail)."""
    if isinstance(obj, dict):
        # S1 — in-toto Statement (typed discriminator: _type is a known string)
        itype = obj.get("_type")
        if isinstance(itype, str) and itype in INTOTO_STATEMENT_TYPES:
            _check_intoto_statement(obj, loc, out)
        # S2 — DSSE envelope (typed discriminator: string payloadType + string payload)
        ptype = obj.get("payloadType") or obj.get("payload_type")
        payload = obj.get("payload")
        if _nonempty_str(ptype) and isinstance(payload, str):
            _check_dsse_envelope(obj, loc, out)
            raw = _b64decode_maybe(payload)
            if raw is not None:
                try:
                    inner = json.loads(raw.decode("utf-8", "replace"))
                except (ValueError, UnicodeDecodeError):
                    inner = None
                if inner is not None:
                    check_obj(inner, f"{loc}.payload~b64", out)
        for k, v in obj.items():
            check_obj(v, f"{loc}.{k}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            check_obj(v, f"{loc}[{i}]", out)


def scan_text(text: str, is_jsonl: bool):
    """Parse `text` (json or jsonl) and return a list of (locator, rule, detail)."""
    out = []
    if not text:
        return out
    if is_jsonl:
        for i, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except ValueError:
                continue
            check_obj(obj, f"L{i}$", out)
    else:
        try:
            obj = json.loads(text)
        except ValueError:
            return out
        check_obj(obj, "$", out)
    return out


# --------------------------------------------------------------------------- #
# Allowlist — for DELIBERATE negative / tamper-demo fixtures whose whole purpose
# is to carry a malformed declared-format receipt (so a downstream guard can
# prove it FAILS). Entries match by repo:path or by path suffix/substring.
# --------------------------------------------------------------------------- #
def _allowed(path: str, repo, ignore_paths) -> bool:
    for entry in ignore_paths:
        e = entry
        if ":" in entry and not entry.startswith("http"):
            er, ep = entry.split(":", 1)
            if repo is not None and er != repo:
                continue
            e = ep
        if path == e or path.endswith(e) or e in path:
            return True
    return False


# --------------------------------------------------------------------------- #
# GitHub helpers (ORG mode) — same auth/list infra as energy_provenance_check.py.
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


def _tree(full: str, ref: str, token: str):
    try:
        data = _gh(f"/repos/{full}/git/trees/{urllib.parse.quote(ref)}?recursive=1", token)
    except urllib.error.HTTPError as e:
        if e.code in (404, 409):  # empty repo / no such ref
            return [], False
        raise
    return data.get("tree", []), data.get("truncated", False)


def _is_candidate(path: str, size: int, all_json: bool, extra: list) -> bool:
    low = path.lower()
    if not (low.endswith(".json") or low.endswith(".jsonl")):
        return False
    parts = set(path.split("/"))
    if parts & SKIP_DIRS:
        return False
    if os.path.basename(path) in NOISE_BASENAMES:
        return False
    if size and size > MAX_BYTES:
        return False
    if all_json:
        return True
    if RECEIPT_PATH_RE.search(path):
        return True
    return any(x and x in path for x in extra)


def check_repo(repo_obj, token, ignore_paths, extra_surfaces, all_json):
    full = repo_obj["full_name"]
    name = repo_obj["name"]
    ref = repo_obj.get("default_branch") or "main"
    tree, truncated = _tree(full, ref, token)
    cands = [
        t["path"] for t in tree
        if t.get("type") == "blob"
        and _is_candidate(t["path"], t.get("size", 0), all_json, extra_surfaces)
    ]
    cands = [p for p in cands if not _allowed(p, name, ignore_paths)]

    def _scan(path):
        text = _raw(full, ref, path, token)
        if text is None:
            return None
        viols = scan_text(text, path.lower().endswith(".jsonl"))
        if not viols:
            return None
        return {"path": path,
                "violations": [{"locator": l, "rule": r, "detail": d} for (l, r, d) in viols]}

    findings = []
    if cands:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for res in pool.map(_scan, cands):
                if res is not None:
                    findings.append(res)
        findings.sort(key=lambda f: f["path"])
    return {
        "repo": name,
        "archived": repo_obj.get("archived", False),
        "default_branch": ref,
        "scanned_blobs": len(cands),
        "tree_truncated": truncated,
        "status": "ERROR" if findings else "OK",
        "findings": findings,
    }


# --------------------------------------------------------------------------- #
# LOCAL mode
# --------------------------------------------------------------------------- #
def scan_local(root: str, ignore_paths):
    findings = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            low = fn.lower()
            if not (low.endswith(".json") or low.endswith(".jsonl")):
                continue
            if fn in NOISE_BASENAMES:
                continue
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, root)
            if _allowed(rel, None, ignore_paths):
                continue
            try:
                if os.path.getsize(fp) > MAX_BYTES:
                    continue
                with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            viols = scan_text(text, low.endswith(".jsonl"))
            if viols:
                findings.append({"path": rel,
                                 "violations": [{"locator": l, "rule": r, "detail": d}
                                                for (l, r, d) in viols]})
    findings.sort(key=lambda f: f["path"])
    return findings


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _emit_annotations(results):
    for r in results:
        for f in r["findings"]:
            for v in f["violations"]:
                print(f"::error::{r['repo']}/{f['path']} [{v['locator']}] "
                      f"receipt-shape {v['rule']}: {v['detail']}. A receipt that "
                      f"declares a format must actually have that format's shape "
                      f"— never fabricate a pass.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Org-wide receipt shape-conformance honesty guard.")
    ap.add_argument("--org", default="szl-holdings")
    ap.add_argument("--local", metavar="DIR",
                    help="Recursively scan .json/.jsonl in a local checkout.")
    ap.add_argument("--all-json", action="store_true",
                    help="ORG mode: scan every .json/.jsonl, not just receipt-ish paths.")
    ap.add_argument("--allowlist", default=os.path.join(
        os.path.dirname(__file__), "..", "data", "receipt_shape_allowlist.json"))
    ap.add_argument("--report", help="Write the full JSON report to this path.")
    ap.add_argument("--include-archived", action="store_true")
    ap.add_argument("--json", action="store_true", help="Print JSON report to stdout.")
    args = ap.parse_args()

    allow = {}
    if args.allowlist and os.path.exists(args.allowlist):
        with open(args.allowlist, "r", encoding="utf-8") as fh:
            allow = json.load(fh)
    ignore_repos = set(allow.get("ignore_repos", []))
    ignore_paths = list(allow.get("ignore_paths", []))
    extra_surfaces = list(allow.get("extra_data_surfaces", []))

    # ---------------- LOCAL mode ---------------- #
    if args.local:
        findings = scan_local(args.local, ignore_paths)
        payload = {
            "schema": "szl.receipt_shape/v1",
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
            for v in f["violations"]:
                print(f"  [FOUND] {f['path']} [{v['locator']}] {v['rule']}: {v['detail']}")
        if findings:
            n = sum(len(f["violations"]) for f in findings)
            print(f"\n{n} receipt-shape violation(s) in {len(findings)} file(s).",
                  file=sys.stderr)
            return 1
        print("\u2713 No receipt-shape violation in scanned data.")
        return 0

    # ---------------- ORG mode ---------------- #
    token = _token()
    repos = list_public_repos(args.org, token, args.include_archived)
    results = []
    for r in repos:
        if r["name"] in ignore_repos:
            continue
        results.append(check_repo(r, token, ignore_paths, extra_surfaces, args.all_json))

    errs = [x for x in results if x["status"] == "ERROR"]
    payload = {
        "schema": "szl.receipt_shape/v1",
        "mode": "org",
        "org": args.org,
        "all_json": args.all_json,
        "checked_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "include_archived": args.include_archived,
        "summary": {
            "checked": len(results),
            "ok": sum(1 for x in results if x["status"] == "OK"),
            "error": len(errs),
            "blobs_scanned": sum(x["scanned_blobs"] for x in results),
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
        print(f"Receipt-shape sweep for {args.org}: {payload['summary']['ok']} OK, "
              f"{len(errs)} ERROR (of {len(results)} public repos; "
              f"{payload['summary']['blobs_scanned']} data blobs scanned)\n")
        for x in results:
            mark = {"OK": "\u2713", "ERROR": "\u2717"}[x["status"]]
            arch = " [archived]" if x["archived"] else ""
            trunc = " [tree-truncated]" if x.get("tree_truncated") else ""
            print(f"  {mark} {x['repo']}{arch}{trunc} ({x['scanned_blobs']} blob(s))")
            for f in x["findings"]:
                for v in f["violations"]:
                    print(f"        {f['path']} [{v['locator']}] {v['rule']}: {v['detail']}")

    if errs:
        _emit_annotations(errs)
        print(f"\n{len(errs)} repo(s) carry a receipt-shape violation: a blob that "
              f"declares an in-toto Statement or DSSE envelope but is missing that "
              f"format's required structure. A declared-format receipt must have "
              f"that format's shape — never fabricate a pass. See annotations + the "
              f"report.", file=sys.stderr)

    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
