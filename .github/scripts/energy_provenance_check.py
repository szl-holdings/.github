#!/usr/bin/env python3
"""Org-wide energy-provenance honesty guard for receipt / attestation DATA.

The honesty doctrine's load-bearing promise is **measured-or-UNAVAILABLE**: an
energy figure is either a real measurement or it is honestly absent — a joule is
NEVER fabricated. The overclaim sweep only reads governed *Markdown* prose;
energy fabrication lives in *data* (receipt JSON, JSONL ledgers, DSSE payloads),
which no existing guard inspects. This script is that data-scoped safety net.

It is deliberately KEY-BASED, not schema-based. Energy is represented several
honest ways across the org and forcing one shape would invent a fake contract
(explicitly rejected once already for DSSE producers). Instead it asserts two
narrow invariants wherever the relevant keys co-occur, and stays silent
otherwise:

  E1  A dict carrying BOTH `joules` and `measured`:
        - a numeric `joules` REQUIRES `measured == true`;
        - `measured != true` REQUIRES `joules` to be null / absent / the string
          "UNAVAILABLE" (a numeric joule — including 0 — is a fabrication).
      Shape seen in szl-receipt / anatomy: {"joules": 41.8, "measured": true}.

  E2  A dict carrying `measured_joules` (+ optional `label`):
        - a numeric `measured_joules` REQUIRES `label` NOT to start with
          "UNAVAILABLE";
        - a `label` starting with "UNAVAILABLE" REQUIRES `measured_joules` null.
      Shape seen in szl-energy-attest: {"measured_joules": null, "label":
      "UNAVAILABLE"}.

DSSE receipts store their body base64-encoded in `payload` (with a
`payloadType`). Such a dict is base64-decoded (standard then url-safe), parsed
as JSON, and recursed into; a decode/parse failure is skipped silently (a
non-JSON or non-base64 payload makes no energy claim we can read — a decode
failure is NOT evidence of fabrication).

What it deliberately does NOT do (honest limitations, not oversights):
  * It does not scan source code — a joule fabricated at runtime is statically
    undecidable. Out of scope; the reusable guard's full-tree data scan is the
    net for committed data.
  * It does not verify a measurement is *physically plausible* — it only checks
    the measured/unavailable flags are internally consistent with the figure.
  * It does not touch MODELED thermodynamic free energies (J/mol with error
    bars, e.g. szl-cookbook): those live in prose / use different keys and never
    co-occur as {joules, measured}, so the key-based rules cannot reach them.
  * A dict with `joules` but no `measured` is NOT flagged (ambiguous, and
    flagging it invites false positives) — E1 requires both keys.

Two modes (mirrors overclaim_sweep.py):

  * ORG mode (default): list every PUBLIC repo, walk its default-branch git
    tree, fetch the receipt-ish `.json` / `.jsonl` blobs (paths matching
    receipt|attest|dsse|provenance|evidence|energy|ledger|intoto|cosign, plus
    any `extra_data_surfaces` from the allowlist; use `--all-json` for a
    thorough catch-all over every committed .json/.jsonl), run the invariants,
    write a JSON report, and exit non-zero on any violation.

  * LOCAL mode (`--local DIR`): recursively scan a checkout's .json/.jsonl.
    Used by the reusable per-repo guard (full-tree net) and by the self-test.
    No network or token required.

Auth (ORG mode only): $SZL_GITHUB_TOKEN / $GH_TOKEN / $GITHUB_TOKEN. Every repo
is public so the built-in Actions token is sufficient.

Exit code 0 = clean; 1 = at least one energy-provenance violation.
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
# Basenames that are never energy data and are cheap to skip (lockfiles etc.).
NOISE_BASENAMES = {"package-lock.json", "composer.lock", "yarn.lock"}
# ORG-mode default path filter: only fetch receipt-ish data blobs (bounded).
RECEIPT_PATH_RE = re.compile(
    r"receipt|attest|dsse|provenance|evidence|energy|ledger|intoto|cosign|\.sig",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Invariant engine (key-based, recursive) — the single source of truth. The
# reusable per-repo guard runs THIS file (checks out szl-holdings/.github@main),
# so there is no inline duplication to keep in lockstep.
# --------------------------------------------------------------------------- #
def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _looks_unavailable(x) -> bool:
    return isinstance(x, str) and x.strip().upper().startswith("UNAVAILABLE")


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


def check_obj(obj, loc, out):
    """Recurse through a decoded JSON value, appending (locator, rule, detail)."""
    if isinstance(obj, dict):
        # E1 — {joules, measured}
        if "joules" in obj and "measured" in obj:
            j, m = obj["joules"], obj["measured"]
            if _is_num(j) and m is not True:
                out.append((f"{loc}", "E1",
                            f"numeric joules={j} with measured={m!r}: a joule "
                            f"requires measured:true, else null/absent/\"UNAVAILABLE\""))
        # E2 — {measured_joules, label?}
        if "measured_joules" in obj:
            mj, label = obj["measured_joules"], obj.get("label")
            if _is_num(mj) and _looks_unavailable(label):
                out.append((f"{loc}", "E2",
                            f"measured_joules={mj} but label={label!r} claims "
                            f"UNAVAILABLE (a figure and an UNAVAILABLE label conflict)"))
        # DSSE envelope: decode base64 payload and recurse into it
        ptype = obj.get("payloadType") or obj.get("payload_type")
        payload = obj.get("payload")
        if ptype and isinstance(payload, str):
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
# is to carry a dishonest receipt (so a downstream guard can prove it FAILS).
# Entries match by repo:path or by path suffix/substring.
# --------------------------------------------------------------------------- #
def _allowed(path: str, repo: str | None, ignore_paths) -> bool:
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
# GitHub helpers (ORG mode) — same auth/list infra as overclaim_sweep.py.
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
                      f"energy-provenance {v['rule']}: {v['detail']}. Doctrine: "
                      f"measured-or-UNAVAILABLE — never fabricate a joule.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Org-wide energy-provenance honesty guard for receipt data.")
    ap.add_argument("--org", default="szl-holdings")
    ap.add_argument("--local", metavar="DIR",
                    help="Recursively scan .json/.jsonl in a local checkout.")
    ap.add_argument("--all-json", action="store_true",
                    help="ORG mode: scan every .json/.jsonl, not just receipt-ish paths.")
    ap.add_argument("--allowlist", default=os.path.join(
        os.path.dirname(__file__), "..", "data", "energy_provenance_allowlist.json"))
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
            "schema": "szl.energy_provenance/v1",
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
            print(f"\n{n} energy-provenance violation(s) in {len(findings)} file(s).",
                  file=sys.stderr)
            return 1
        print("\u2713 No energy-provenance violation in scanned data.")
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
        "schema": "szl.energy_provenance/v1",
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
        print(f"Energy-provenance sweep for {args.org}: {payload['summary']['ok']} OK, "
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
        print(f"\n{len(errs)} repo(s) carry an energy-provenance violation: a joule "
              f"present while unmeasured, or a figure labelled UNAVAILABLE. Doctrine: "
              f"measured-or-UNAVAILABLE — never fabricate a joule. See annotations + "
              f"the report.", file=sys.stderr)

    return 1 if errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
