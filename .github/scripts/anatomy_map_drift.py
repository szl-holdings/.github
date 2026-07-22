#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - Doctrine v11
"""
SZL anatomy-map cross-surface drift guard (org-level).

The single honest "SZL Anatomy" map now lives on THREE independently-edited,
independently-deployed surfaces:

  * a11oy        szl-holdings/a11oy        pages/console.html
                 -> the `anatomy-map-tab-patch` JS block (marker-delimited),
                    rendered as the `V.anatomymap` console tab.
  * killinchu    szl-holdings/killinchu    killinchu_elite_console.py
                 -> the SAME marker block embedded in `_CONSOLE_HTML`
                    (NS-aware; the killinchu variant legitimately drops the
                    trailing `NS=` footer line).
  * HF Space     SZLHOLDINGS/anatomy       data.js + index.html
                 -> the standalone static deck (a-11-oy.com/anatomy-map mirror),
                    a DIFFERENT rendering of the same honest doctrine.

Because each is edited and shipped on its own pipeline, the honesty doctrine can
silently DRIFT between them: one surface could quietly change the locked-formula
ladder or relabel Λ while another stays honest. That is exactly the kind of
"looks fine on the surface you happened to open" regression a CI guard must fail
LOUD on.

What is asserted on EVERY surface (the non-negotiable honesty invariants):

  1. The locked-proven formula set is EXACTLY the canonical 8
     {F1, F4, F7, F11, F12, F18, F19, F22}. Not 7, not 9, not a swapped id.
  2. The Λ = Conjecture 1 honesty label is present (Λ uniqueness is a
     conjecture, never a theorem / never a pass-fail oracle).

Plus, for the two surfaces that embed the byte-shared marker block (a11oy +
killinchu), the capability ladder itself (each capability's key, status and
formula references) must MATCH between them -- so "one surface updates the
capability list" is caught even when both still satisfy (1) and (2). The
volatile per-surface prose (the Putnam DEMO/OPEN tally) and the documented
NS-footer variance are deliberately NOT part of the fingerprint, so the guard
fails on real honesty drift, not on expected chrome differences.

Exit status:
  0  every surface agrees and is honest.
  1  drift / a broken honesty invariant on at least one surface.
  2  a surface could not be fetched (network/auth). NEVER a silent green --
     coverage can't look clean when the check could not actually run.

stdlib only (no requests / huggingface_hub) so it runs on a bare runner.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GH_API = "https://api.github.com"
HF_HOST = "https://huggingface.co"
UA = {"User-Agent": "anatomy-map-drift/1.0"}

# The one canonical locked-proven set. Doctrine v11, kernel c7c0ba17.
CANONICAL_LOCKED = ("F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22")

# Marker delimiters of the shared anatomy block (a11oy + killinchu).
_BLOCK_START = "anatomy-map-tab-patch ::"
_BLOCK_END = "end anatomy-map-tab-patch"


# --------------------------------------------------------------------------- #
# HTTP (stdlib, retry + backoff)
# --------------------------------------------------------------------------- #
def _http(url, headers=None, accept=None, retries=6):
    last = None
    hdrs = dict(UA)
    if accept:
        hdrs["Accept"] = accept
    if headers:
        hdrs.update(headers)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                return e.code, b""
            last = e
            if e.code == 429 or 500 <= e.code < 600:
                ra = (e.headers or {}).get("Retry-After")
                try:
                    delay = float(ra) if ra else min(60.0, 2.0 * (2 ** attempt))
                except ValueError:
                    delay = min(60.0, 2.0 * (2 ** attempt))
                time.sleep(delay + random.uniform(0, 1.2))
                continue
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        time.sleep(1.4 * (attempt + 1) + random.uniform(0, 0.6))
    raise RuntimeError(f"GET failed after {retries} tries: {url}: {last}")


def _gh_headers():
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("SZL_GITHUB_TOKEN")
    h = {}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


def fetch_github_file(repo, path, ref="main"):
    """Raw file content via the contents API (works for PRIVATE repos w/ token)."""
    url = f"{GH_API}/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={ref}"
    status, body = _http(url, headers=_gh_headers(),
                         accept="application/vnd.github.raw")
    if status != 200:
        raise RuntimeError(f"GitHub {repo}:{path}@{ref}: HTTP {status}")
    return body.decode("utf-8", "replace")


def fetch_hf_file(repo, path, ref="main"):
    """Raw file content from a (public) Hugging Face Space."""
    url = f"{HF_HOST}/spaces/{repo}/raw/{ref}/{urllib.parse.quote(path)}"
    status, body = _http(url)
    if status != 200:
        raise RuntimeError(f"HF space {repo}:{path}@{ref}: HTTP {status}")
    return body.decode("utf-8", "replace")


def fetch_raw_url(url):
    """Raw content from an arbitrary public URL.

    Used for the live public-facing deployment (e.g. a-11-oy.com/anatomy-map),
    which serves its OWN built bundle -- distinct from the GitHub source and the
    HF Space raw files -- so it can silently drift (stale nginx/CDN build) even
    when both repos are in sync. A non-200 raises so the check fails loud rather
    than passing on an unreachable public site.
    """
    status, body = _http(url)
    if status != 200:
        raise RuntimeError(f"URL {url}: HTTP {status}")
    return body.decode("utf-8", "replace")


import urllib.parse  # noqa: E402  (kept next to its sole users above)


# --------------------------------------------------------------------------- #
# Pure extractors (network-free -> directly unit-testable)
# --------------------------------------------------------------------------- #
def extract_marker_block(text):
    """Return the substring between the anatomy-map markers, or None."""
    i = text.find(_BLOCK_START)
    if i < 0:
        return None
    j = text.find(_BLOCK_END, i)
    if j < 0:
        return None
    return text[i:j + len(_BLOCK_END)]


def _normalize_lambda(text):
    # The JS surfaces carry Λ as the literal escape "\u039b"; the doctrine prose
    # carries the glyph. Fold both so one regex covers every surface.
    return text.replace("\\u039b", "Λ").replace("\\u039B", "Λ")


# A run of >=5 comma-separated F-ids (the locked LADDER, never a 3-id subset
# like khipu's "F4, F7, F22"). Tolerant of whitespace AND the quoted JS-array
# form ('F1', 'F4', ...) used by the HF Space's data.js.
_FGROUP = re.compile(r"F\d+(?:['\"\s]*,['\"\s]*F\d+){4,}")
# Anchors that specifically denote the locked-EIGHT declaration (the "8" / "-8"
# / "_proven" / "proven" qualifier disambiguates it from a plain "(locked)"
# subset annotation).
_LOCKED_ANCHOR = re.compile(
    r"8\s*LOCKED|LOCKED[-\s]?8|locked[-\s]?8|locked_proven|locked[-\s]?proven|Locked\s+proven",
    re.IGNORECASE,
)


def parse_locked_groups(text):
    """Every locked-EIGHT formula group declared in ``text``.

    Returns a list of tuples (sorted F-id tuple). The honest invariant is that
    every such group equals the canonical 8; a returned group that differs (a
    swapped/dropped/added id) is drift. An empty list means the locked-8 ladder
    declaration VANISHED from this surface -> also drift.
    """
    anchors = [(m.start(), m.end()) for m in _LOCKED_ANCHOR.finditer(text)]
    groups = []
    # Match the F-id group against the FULL text (never a sliced window, which
    # would truncate a group straddling the boundary and read as a phantom
    # "dropped id"), then keep only groups that sit near a locked-8 anchor.
    for g in _FGROUP.finditer(text):
        gs = g.start()
        for (a_start, a_end) in anchors:
            if (a_start - 160) <= gs <= (a_end + 220):
                ids = tuple(re.findall(r"F\d+", g.group(0)))
                groups.append(_sorted_fids(ids))
                break
    return groups


def _sorted_fids(ids):
    return tuple(sorted(set(ids), key=lambda f: int(f[1:])))


def has_lambda_conjecture(text):
    """True iff the surface carries the Λ = Conjecture 1 honesty label."""
    t = _normalize_lambda(text)
    subj = r"(?:Λ|Lambda|lambda|uniqueness)"
    fwd = re.compile(subj + r"[^.\n]{0,48}Conjecture\s*1", re.IGNORECASE)
    rev = re.compile(r"Conjecture\s*1[^.\n]{0,48}" + subj, re.IGNORECASE)
    return bool(fwd.search(t) or rev.search(t))


def parse_capabilities(block_text):
    """Ordered capability ladder of the shared marker block.

    Returns a list of (key, status, formulas) triples taken from the CAPS array
    (`k:'..'`, `s:'..'`, `f:'..'`). Used to compare a11oy<->killinchu, which
    embed the byte-shared block, so a one-sided edit to the capability/formula
    list is caught even when the locked-8 + Λ invariants still hold.
    """
    keys = re.findall(r"\bk:\s*'((?:[^'\\]|\\.)*)'", block_text)
    stats = re.findall(r"\bs:\s*'((?:[^'\\]|\\.)*)'", block_text)
    forms = re.findall(r"\bf:\s*'((?:[^'\\]|\\.)*)'", block_text)
    n = min(len(keys), len(stats), len(forms))
    return [(keys[i], stats[i], forms[i]) for i in range(n)]


# --------------------------------------------------------------------------- #
# Per-surface fingerprint + evaluation (pure -> unit-testable)
# --------------------------------------------------------------------------- #
def fingerprint(surface):
    """Build a fingerprint dict for one surface from its already-fetched text.

    ``surface`` = {"id", "extract": "marker_block"|"invariant_scan", "text"}.
    For marker_block surfaces only the anatomy block is scanned (so unrelated
    page content can't satisfy/break the invariants); a missing block is itself
    a hard finding.
    """
    out = {"id": surface["id"], "errors": []}
    text = surface["text"]
    if surface["extract"] == "marker_block":
        block = extract_marker_block(text)
        if block is None:
            out["errors"].append("anatomy marker block not found "
                                 f"({_BLOCK_START} .. {_BLOCK_END})")
            out["locked_groups"] = []
            out["lambda_conjecture"] = False
            out["capabilities"] = None
            return out
        scan = block
        out["capabilities"] = parse_capabilities(block)
    else:
        scan = text
        out["capabilities"] = None
    out["locked_groups"] = parse_locked_groups(scan)
    out["lambda_conjecture"] = has_lambda_conjecture(scan)
    return out


def evaluate(surfaces):
    """Evaluate fetched surfaces. Returns (report, exit_code).

    ``surfaces`` is a list of {"id","extract","text"} dicts (text already
    fetched). Pure / network-free so the self-test can drive it with fixtures.
    """
    canon = _sorted_fids(CANONICAL_LOCKED)
    findings = []
    fps = [fingerprint(s) for s in surfaces]

    for fp in fps:
        for e in fp["errors"]:
            findings.append(f"[{fp['id']}] {e}")
        groups = fp["locked_groups"]
        if not groups:
            findings.append(f"[{fp['id']}] no locked-8 formula declaration "
                            "found (the honesty ladder vanished from this surface)")
        for g in groups:
            if g != canon:
                findings.append(
                    f"[{fp['id']}] locked-formula set drift: declares "
                    f"{{{', '.join(g)}}} but the canonical locked-8 is "
                    f"{{{', '.join(canon)}}}")
        if not fp["lambda_conjecture"]:
            findings.append(f"[{fp['id']}] Λ = Conjecture 1 honesty label is "
                            "missing (Λ uniqueness must never read as proven)")

    # Cross-surface agreement on the locked set (defensive: catches the case
    # where two surfaces drift to the SAME wrong-but-self-consistent set).
    declared = {}
    for fp in fps:
        uniq = {g for g in fp["locked_groups"]}
        if uniq:
            declared[fp["id"]] = uniq
    all_sets = set().union(*declared.values()) if declared else set()
    if len(all_sets) > 1:
        rendered = "; ".join(
            f"{sid}={{{', '.join(next(iter(s)))}}}" if len(s) == 1
            else f"{sid}=<multiple>"
            for sid, s in declared.items())
        findings.append("locked-formula set disagrees ACROSS surfaces: " + rendered)

    # Capability-ladder agreement between the marker-block surfaces.
    cap_surfaces = [fp for fp in fps if fp["capabilities"] is not None]
    if len(cap_surfaces) >= 2:
        ref = cap_surfaces[0]
        for other in cap_surfaces[1:]:
            if other["capabilities"] != ref["capabilities"]:
                diff = _cap_diff(ref, other)
                findings.append(
                    f"capability ladder drift between {ref['id']} and "
                    f"{other['id']}: {diff}")

    report = {
        "canonical_locked": list(canon),
        "surfaces": [
            {
                "id": fp["id"],
                "locked_groups": [list(g) for g in fp["locked_groups"]],
                "lambda_conjecture": fp["lambda_conjecture"],
                "capability_count": (len(fp["capabilities"])
                                     if fp["capabilities"] is not None else None),
            }
            for fp in fps
        ],
        "findings": findings,
        "ok": not findings,
    }
    return report, (0 if not findings else 1)


def _cap_diff(a, b):
    ca = {k: (s, f) for (k, s, f) in (a["capabilities"] or [])}
    cb = {k: (s, f) for (k, s, f) in (b["capabilities"] or [])}
    bits = []
    only_a = sorted(set(ca) - set(cb))
    only_b = sorted(set(cb) - set(ca))
    if only_a:
        bits.append(f"only in {a['id']}: {', '.join(only_a)}")
    if only_b:
        bits.append(f"only in {b['id']}: {', '.join(only_b)}")
    for k in sorted(set(ca) & set(cb)):
        if ca[k] != cb[k]:
            bits.append(f"'{k}' status/formulas differ "
                        f"({a['id']}={ca[k]} vs {b['id']}={cb[k]})")
    return "; ".join(bits) or "ordering differs"


# --------------------------------------------------------------------------- #
# Fetch + run
# --------------------------------------------------------------------------- #
def load_registry(path):
    with open(path) as fh:
        return json.load(fh)


def fetch_surface(spec, ref_overrides=None):
    ref_overrides = ref_overrides or {}
    repo = spec.get("repo")
    ref = ref_overrides.get(repo, spec.get("ref", "main")) if repo else spec.get("ref", "main")
    if spec["kind"] == "github":
        paths = spec.get("paths") or [spec["path"]]
        texts = [fetch_github_file(spec["repo"], p, ref) for p in paths]
    elif spec["kind"] == "hf_space":
        paths = spec.get("paths") or [spec["path"]]
        texts = [fetch_hf_file(spec["repo"], p, ref) for p in paths]
    elif spec["kind"] == "url":
        urls = spec.get("urls") or [spec["url"]]
        texts = [fetch_raw_url(u) for u in urls]
    else:
        raise RuntimeError(f"unknown surface kind: {spec['kind']}")
    return {"id": spec["id"], "extract": spec["extract"],
            "text": "\n\n".join(texts)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--registry",
                    default=os.path.join(os.path.dirname(__file__),
                                         "..", "data",
                                         "anatomy_map_registry.json"))
    ap.add_argument("--report", default=None,
                    help="path to write the JSON drift report")
    ap.add_argument("--only", action="append", default=None,
                    help="restrict the check to these surface id(s) "
                         "(repeatable, or comma-separated). Others in the "
                         "registry are skipped. Used by the tight HF-edit "
                         "watcher to validate just the SZLHOLDINGS/anatomy "
                         "Space soon after a direct HF-side edit.")
    ap.add_argument("--ref-override", action="append", default=None,
                    help="REPO=REF: read this surface repo at REF instead of "
                         "its registry ref (repeatable). The PR gate passes the "
                         "calling repo's PR-head SHA so the PROPOSED change is "
                         "validated while every other surface stays at main.")
    ap.add_argument("--skip-kind", action="append", default=None,
                    help="skip surfaces of this kind, e.g. url (repeatable). The "
                         "PR gate skips kind=url so a transient live-CDN/nginx "
                         "blip can't block a PR; the scheduled sweep + watcher "
                         "still cover the mirror.")
    args = ap.parse_args(argv)

    reg = load_registry(args.registry)
    global CANONICAL_LOCKED
    if reg.get("canonical_locked"):
        CANONICAL_LOCKED = tuple(reg["canonical_locked"])

    specs = reg["surfaces"]
    if args.only:
        wanted = set()
        for item in args.only:
            wanted.update(t.strip() for t in item.split(",") if t.strip())
        specs = [s for s in specs if s["id"] in wanted]
        missing = wanted - {s["id"] for s in specs}
        if missing:
            print("::error::--only names unknown surface id(s): "
                  + ", ".join(sorted(missing)))
            print("::error::Failing (exit 2) rather than silently checking "
                  "nothing -- coverage can never look clean on a typo.")
            return 2
        if not specs:
            print("::error::--only matched no surfaces; refusing to pass on "
                  "an empty check.")
            return 2

    if args.skip_kind:
        skip = {k.strip() for k in args.skip_kind if k.strip()}
        specs = [s for s in specs if s["kind"] not in skip]
        if not specs:
            print("::error::--skip-kind removed every surface; refusing to pass "
                  "on an empty check.")
            return 2

    ref_overrides = {}
    if args.ref_override:
        for item in args.ref_override:
            repo, sep, r = item.partition("=")
            repo, r = repo.strip(), r.strip()
            if not sep or not repo or not r:
                print("::error::--ref-override must be REPO=REF, got: " + item)
                return 2
            ref_overrides[repo] = r

    surfaces = []
    try:
        for spec in specs:
            surfaces.append(fetch_surface(spec, ref_overrides))
    except RuntimeError as e:
        print(f"::error::anatomy-map drift check could not fetch a surface: {e}")
        print("::error::Failing (exit 2) rather than passing -- coverage can "
              "never look clean when the check could not actually run.")
        return 2

    report, code = evaluate(surfaces)

    if args.report:
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
            fh.write("\n")

    if code == 0:
        print("✓ SZL anatomy map is consistent across all surfaces: "
              f"locked-8 = {{{', '.join(report['canonical_locked'])}}}, "
              "Λ = Conjecture 1 on every surface, capability ladder in sync.")
    else:
        print("::error::SZL anatomy-map DRIFT detected:")
        for f in report["findings"]:
            print(f"::error::  - {f}")
        print("::error::Re-sync the divergent surface(s) so the locked-8 ladder "
              "{F1,F4,F7,F11,F12,F18,F19,F22}, the Λ=Conjecture-1 label, and the "
              "capability ladder match on a11oy /console, killinchu /elite, and "
              "the SZLHOLDINGS/anatomy HF Space.")
    return code


if __name__ == "__main__":
    sys.exit(main())
