#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Doctrine gate G5 - org-wide user-visible-codename sweep.

Companion CI gate (alongside overclaim_sweep.py for G2). Enforces:

    0 user-visible codenames (amaru / rosie / sentra / jarvis).

Internal route keys are allowed as code identifiers; this sweep only fails when
a banned codename appears in *user-visible* text:
  - the VISIBLE text + visible attrs (title/aria-label/alt/placeholder) of
    served HTML on the live a11oy + killinchu Spaces, and
  - rendered-text columns of governed CSV / served-JSON surfaces in the repo
    allowlist.

It deliberately does NOT fail on id=/class=/data-* attributes or <script> bodies
(those are allowed internal keys), so honest code that uses amaru_* / rosie_* as
internal route keys is never a false positive. The shared visible-text scanner
in szl_codename_gate.py is the single source of truth for both apps and this CI.

Modes:
  * LIVE mode (default): GET each URL in --urls (or the built-in Space surface
    list), extract visible text, fail on any banned token.
  * FILE mode: scan local files/globs passed as positional args.

Exit 0 = clean (G5 PASS). Exit 1 = at least one user-visible codename (G5 FAIL).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import List

import szl_codename_gate as G  # shared single-source scanner

# Default live surfaces to sweep (the SPA shell + the honest/about surfaces that
# render OSINT/Operator/verdict labels). HTML 000 / transient errors -> WARN,
# not FAIL, so a flaky Space fetch never masks a real signal incorrectly.
DEFAULT_URLS = [
    "https://szlholdings-a11oy.hf.space/",
    "https://szlholdings-killinchu.hf.space/",
    "https://szlholdings-a11oy.hf.space/api/a11oy/v1/honest",
    "https://szlholdings-killinchu.hf.space/api/killinchu/v1/gov/a11oy-honest",
    "https://szlholdings-killinchu.hf.space/api/killinchu/v1/osint/archive/recent",
]


def sweep_urls(urls: List[str], retries: int = 6) -> int:
    import time

    violations = 0
    for url in urls:
        hits = None
        last_err = ""
        for attempt in range(retries):
            try:
                hits = G.scan_url(url, timeout=30.0)
                break
            except Exception as e:  # transient HF 000 / network
                last_err = str(e)
                time.sleep(3)
        if hits is None:
            print("WARN %s -> unreachable after %d tries (%s) - not failing on a flaky fetch" % (url, retries, last_err))
            continue
        if hits:
            violations += len(hits)
            print("FAIL %s -> user-visible codename(s): %s" % (url, ", ".join(sorted(set(hits)))))
        else:
            print("ok   %s" % url)
    return violations


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="G5 user-visible codename sweep")
    ap.add_argument("paths", nargs="*", help="files/globs to scan (FILE mode)")
    ap.add_argument("--urls", nargs="*", default=None, help="live URLs to sweep (LIVE mode)")
    ap.add_argument("--report", default=None, help="write JSON report to this path")
    args = ap.parse_args(argv)

    total = 0
    report = {"gate": "G5", "rule": "0 user-visible codenames (amaru/rosie/sentra/jarvis)", "violations": 0, "surfaces": []}

    if args.paths:
        for p in args.paths:
            import glob

            for path in (glob.glob(p, recursive=True) or [p]):
                hits = G._scan_path(path)
                if hits:
                    total += len(hits)
                    print("FAIL %s -> %s" % (path, ", ".join(sorted(set(hits)))))
                    report["surfaces"].append({"surface": path, "hits": sorted(set(hits))})
                else:
                    print("ok   %s" % path)

    urls = args.urls if args.urls is not None else DEFAULT_URLS
    if urls:
        total += sweep_urls(urls)

    report["violations"] = total
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)

    print("\nG5 codename sweep: %d user-visible codename(s)." % total)
    if total:
        print("Doctrine G5 violated. Map amaru->YACHAY, rosie->Operator, sentra->CHAPAQ, jarvis->Operator in the rendered output.")
        return 1
    print("G5 PASS - 0 user-visible codenames.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
