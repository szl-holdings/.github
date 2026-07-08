#!/usr/bin/env python3
"""SZL Doctrine Invariants — line-wrap-tolerant, testable port of doctrine-check.yml.

WHY THIS FILE EXISTS
--------------------
The org-wide honesty gate (`.github/workflows/doctrine-check.yml`) was, for its
whole history, ~200 lines of inline bash `grep` pipelines. Two structural
problems made it the single most fragile load-bearing check in the org:

  1. LINE-BASED. `grep` matches one physical line at a time. Every honesty
     invariant is really "TRIGGER token X is present AND no governance-safe
     qualifier Y is nearby". Bash implements that as
     `grep TRIGGER | grep -v QUALIFIER`, so the qualifier MUST live on the SAME
     physical line as the trigger. A cosmetic text reflow that splits one honest
     sentence across two lines (so the trigger lands on a line without its
     qualifier) turns an honest doc into a FALSE-POSITIVE doctrine failure.
     This actually happened: a 2-line wrap in `szl_kc_atlas.py` broke
     `check / doctrine` on `main` AND every open PR org-wide (a11oy PR #768 was
     needed just to re-flow the sentence back onto one line — a bandaid that
     leaves the NEXT reflow free to break the org again).

  2. UNTESTED. Every OTHER org guard (overclaim-sweep, energy-provenance,
     receipt-shape, codename, anatomy-map, ...) ships a network-free self-test
     wired into tests.yml so a refactor can't weaken it into a false-green
     no-op. The most important gate — doctrine — had NONE, because its logic
     was un-importable inline bash. So a weakening (or a false positive) could
     land with no signal.

THE FIX (no bandaid)
--------------------
Port the invariant logic to Python and make the honesty qualifiers WINDOW-scoped
instead of single-line-scoped: when a TRIGGER matches, we test the governance
qualifier against a whitespace-normalized window (the trigger line joined with a
few neighbouring lines). A soft-wrap can no longer hide the qualifier from the
check, so a cosmetic reflow can never again break the org. A genuine unqualified
overclaim (no qualifier anywhere in the window) still FAILS.

This is kept behaviour-compatible with the bash gate's INTENT (same triggers,
same exemptions, same repo-scoping for the a11oy/killinchu verified-L2 banner),
and is pinned by test_doctrine_check.py.

Modes:
  --local DIR   scan a local checkout (network-free; used by CI + the self-test)
Exit code 0 = all invariants satisfied; 1 = at least one violation.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# File selection (mirrors the bash gate's --include / --exclude-dir set).
# ---------------------------------------------------------------------------
SCAN_EXT = {".md", ".json", ".yaml", ".yml", ".py", ".ts", ".go", ".lean"}
EXCLUDE_DIRS = {
    ".git", ".lake", "node_modules", "dist", "build", "coordination",
    "cursor-directives", "replit-sync", "corpus", "resilience_observability",
    "__tests__",
}
# Files the bash gate excluded by name (generated snapshots / self-referential
# guard sources that quote banned strings on purpose).
EXCLUDE_BASENAMES = {
    "governed_loop.json", "wayra_snapshot.json", "all_open_prs.json",
    "cto_prs_opened_recent.json", "szl_math_corpus.py", "szl_chaski.py",
    "szl_hub.py", "run_all_json.py", "OUROBOROS_RUN_ALL.py", "szlBreaker.ts",
    "szl_breaker.py", "serve.py", "szl_wire.py", "_live_serve.py",
    "YACHAY_SYSTEM_PROMPT.md", "doctrine_check.py", "test_doctrine_check.py",
}
EXCLUDE_GLOBS = ("governed_loop", "wayra_snapshot")


def _excluded_basename(name: str) -> bool:
    if name in EXCLUDE_BASENAMES:
        return True
    return any(name.startswith(g) for g in EXCLUDE_GLOBS)


def iter_files(root: str, exts=None):
    exts = exts or SCAN_EXT
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            ext = os.path.splitext(fn)[1]
            if ext not in exts:
                continue
            if _excluded_basename(fn):
                continue
            yield os.path.join(dirpath, fn)


def _iter_dockerfiles(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn.startswith("Dockerfile"):
                yield os.path.join(dirpath, fn)


def read_lines(path: str):
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return fh.read().splitlines()
    except Exception:
        return []


# ---------------------------------------------------------------------------
# The window primitive — the heart of the line-wrap fix.
# ---------------------------------------------------------------------------
def window_text(lines, idx: int, radius: int = 2, rel: str = "") -> str:
    """Whitespace-normalized join of line[idx] with `radius` neighbours each side.

    This is what defeats the reflow-breaks-the-org failure: an honesty qualifier
    that a soft-wrap pushed onto an adjacent physical line is still visible to
    the exemption test, because we test the exemption against this joined window
    rather than against the single physical trigger line.
    """
    lo = max(0, idx - radius)
    hi = min(len(lines), idx + radius + 1)
    # Prefix the relative path so PATH-based exemptions work in byte-parity with
    # the bash gate, whose `grep` output lines are `path:content` and whose
    # `grep -v knowledge\.json` etc. therefore match on the path segment too.
    joined = (rel + ": " if rel else "") + " ".join(lines[lo:hi])
    return re.sub(r"\s+", " ", joined).strip()


def _search(patterns, text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


# ---------------------------------------------------------------------------
# Invariant definitions. Each honesty invariant = (trigger, exemptions).
# A line FAILS iff the trigger matches AND NO exemption matches the WINDOW.
# ---------------------------------------------------------------------------

INV1_TRIGGER = r"doctrine.*v(9|10|12|13)"
INV1_EXEMPT = [
    r"additive", r"proposed", r"planned.*release", r"roadmap",
    r"not yet promoted", r"future", r"historical", r"deprecated",
    r"archived", r"out of scope", r"not pursuing", r"rejected",
    r"v10.*v11|v11.*v10|v10-v11|additive over|edge organ|4th organ",
    r"v12.*v11|v11.*v12|puriq|chaski|organ.*v1[23]|v1[23].*organ",
    r"§[0-9]|doctrine_state|doctrine-v|doctrine v[0-9].*locked|v1[12].*locked",
]
INV1_EXT = {".md", ".json", ".yaml", ".yml", ".py", ".ts", ".go"}

INV2_TRIGGER = r"Λ.*theorem|Lambda.*theorem|lambda.*Theorem|lambdaUniqueness[^C]"
INV2_EXEMPT = [
    r"conjecture", r"not a proven theorem|not a theorem|never a theorem",
    r"never claim|do ?n['o]t claim", r"do ?n['o]t call|never call",
    r"gate.*theorem|theorem.*enforced|readme.*theorem|gates/readme",
    r"lambdacategory|lambdamonotonicity|composability|minmaxbounds",
    r"theoremu_lambdaunique|theoremu_|lutar/uniqueness/theoremu",
    r"knowledge\.json|lean.*theorem|lean 4.*theorem",
    r"does ?n['o]t assert|do not assert|not assert.*theorem",
    r"[0-9]+ theorems|all [0-9]+ theorem|theorems '|every theorem|theorem carries",
    r"ks_theorem|_theorem_[0-9]|theorem_ref|theorem [0-9]",
    r"→ ?theorem|theorem ?→|receipt.*theorem|provenance.*theorem|theorem.*doi",
    r"uniqueness theorem is conditional|theorem is conditional-only|conditional.*not claimed",
    r"dress .*up as a theorem|conditional Λ theorem|conditional lambda theorem",
]
INV2_EXT = {".md", ".json", ".py", ".ts", ".lean"}
# --- INV2 training-data exemption (NARROW, path-scoped — NOT a global disable) ---
# a11oy's ORPO / preference-training corpus GENERATORS intentionally embed the
# disallowed "Λ ... proven theorem" strings as the REJECTED half of contrastive
# preference pairs: the model is trained to PREFER the honest "Λ = Conjecture 1,
# never a theorem" completion and to REJECT the overclaim. These rejected strings
# are negative-training FIXTURES, not product/serve/README claims, so they are
# not real overclaims and must not trip the honesty gate.
#
# Scope is a tight relative-path allowlist under training/ (the ORPO generator
# and the box run-doc that quotes the refusal smoke-test prompt). This exempts
# ONLY those files, ONLY from INV2 — every other invariant still scans them, and
# INV2 still fires on every non-training file. A planted real overclaim outside
# training/ (or a non-INV2 overclaim inside it) still FAILS; see the negative
# control in test_doctrine_check.py.
INV2_TRAINING_EXEMPT_PREFIXES = (
    "training/build_orpo",      # ORPO rejected/accepted preference-pair generator
    "training/box/RUN_ON_BOX",  # box run-doc quoting the "Is Λ a theorem?" refusal test
)


def _inv2_training_exempt(rel: str) -> bool:
    r = rel.replace(os.sep, "/")
    return any(r.startswith(p) for p in INV2_TRAINING_EXEMPT_PREFIXES)

INV3_L3_TRIGGER = r"SLSA.*L3|SLSA Level 3"
INV3_L3_EXEMPT = [
    r"not l3|no.*l3|l3.*not|banned|prohibited|forbidden|out of scope",
    r"roadmap|future|planned|historical|archived|rejected|path to",
    r"staged|awaiting|mis-?claimed|corrected|previously",
    r"flags bare|appears only inside|quoted prohibition|overclaim grep",
]
INV3_L2_TRIGGER = r"SLSA.*L2|SLSA Level 2"
INV3_L2_EXEMPT_BASE = [
    r"ghcr-build-push\.yml|ghcr\.io/szl-holdings/(a11oy|killinchu)",
    r"verified|attested|attestation.*(exists|created|uploaded)",
    r"(a11oy|killinchu)\.slsa-provenance|szl-(a11oy|killinchu)|l2 on organ images",
    r"bundle-level.*not.*earned|no bundle-level",
    r"roadmap|future|planned|historical|archived|rejected|path to|not yet",
    r"not l2|no.*l2|l2.*not|banned|prohibited",
]
INV3_L2_BANNER_EXEMPT = [
    r"SLSA L1 ?\+ ?L2|SLSA L1\+L2|L1 ?\+ ?L2|SLSA Build L2 provenance attestation",
]
INV3_EXT = {".md", ".json", ".yaml"}

INV5_TRIGGER = r"Iron Bank|FedRAMP (High|Moderate)|CMMC L[2-5]|SWFT certified|Mission Owner"
INV5_EXEMPT = [
    r"out of scope|not pursuing|historical|archived|rejected|deprecated|proposed|roadmap",
    r"no iron bank|not.*iron bank|no fedramp|not.*fedramp|no cmmc|not.*cmmc|gap|vanilla|approved base|citation|nist",
    r"not claimed|❌|not pursued|not held|no.*authorization",
    r"customer.*requirement|policy.*map|compliance.*map|does not|cannot|without",
    r"upstream|ecosystem|respective.*polic|their.*polic|contribute to",
]
INV5_EXT = {".md", ".json", ".yaml"}
INV5_EXCLUDE_BASENAMES = {"OPS_NOTES.md"}
INV5_EXCLUDE_GLOBS = ("defense",)
INV5_EXCLUDE_DIRS = {"vertical"}


def _verified_l2_repo(repo: str) -> bool:
    return (repo or "").split("/")[-1] in {"a11oy", "killinchu"}


def scan_local(root: str, repo: str = ""):
    """Return list of (invariant, path, lineno, line) violations."""
    violations = []
    is_verified_l2 = _verified_l2_repo(repo)

    for path in iter_files(root):
        ext = os.path.splitext(path)[1]
        base = os.path.basename(path)
        rel = os.path.relpath(path, root)
        # skip anything under a .git/.lake path that os.walk pruning missed
        if re.search(r"(^|/)(\.git|\.lake|node_modules|dist|build)/", rel):
            continue
        lines = read_lines(path)

        for i, line in enumerate(lines):
            win = None  # computed lazily

            # --- Invariant 1: doctrine version drift ---
            # TRIGGER is case-SENSITIVE (byte-parity with the bash gate's
            # `grep -rE`, which has no -i on the trigger — only the exclusions
            # are -i). Capitalised prose like "Doctrine v10" is intentionally
            # NOT a trigger; only lower-case `doctrine v1x` fires.
            if ext in INV1_EXT and re.search(INV1_TRIGGER, line):
                win = win or window_text(lines, i, rel=rel)
                if not _search(INV1_EXEMPT, win):
                    violations.append(("Inv1", rel, i + 1, line.strip()))

            # --- Invariant 2: Λ must be Conjecture 1, never a theorem ---
            # Path-scoped skip for intentional ORPO negative-training data (the
            # rejected half of preference pairs deliberately contains the banned
            # overclaim). Only these training-data files, and only INV2, are
            # exempt; see INV2_TRAINING_EXEMPT_PREFIXES.
            if (ext in INV2_EXT and re.search(INV2_TRIGGER, line)
                    and not _inv2_training_exempt(rel)):
                win = window_text(lines, i, rel=rel)
                if not _search(INV2_EXEMPT, win):
                    violations.append(("Inv2", rel, i + 1, line.strip()))

            # --- Invariant 3: SLSA honesty ---
            if ext in INV3_EXT:
                # base64 blobs stripped like the bash `sed`
                clean = re.sub(r";base64,[A-Za-z0-9+/=]+", "", line)
                if re.search(INV3_L3_TRIGGER, clean):
                    w = window_text(lines, i, rel=rel)
                    if not _search(INV3_L3_EXEMPT, w):
                        violations.append(("Inv3-L3", rel, i + 1, line.strip()))
                if re.search(INV3_L2_TRIGGER, clean):
                    w = window_text(lines, i, rel=rel)
                    exempts = list(INV3_L2_EXEMPT_BASE)
                    if is_verified_l2:
                        exempts += INV3_L2_BANNER_EXEMPT
                    if not _search(exempts, w):
                        violations.append(("Inv3-L2", rel, i + 1, line.strip()))

            # --- Invariant 5: banned compliance positive claims ---
            if ext in INV5_EXT:
                if base in INV5_EXCLUDE_BASENAMES:
                    pass
                elif any(base.startswith(g) for g in INV5_EXCLUDE_GLOBS):
                    pass
                elif any(("/%s/" % d) in ("/" + rel) for d in INV5_EXCLUDE_DIRS):
                    pass
                elif re.search(INV5_TRIGGER, line):
                    w = window_text(lines, i, rel=rel)
                    if not _search(INV5_EXEMPT, w):
                        violations.append(("Inv5", rel, i + 1, line.strip()))

    # --- Invariant 6: no `COPY . .` in Dockerfiles (extension-less, scanned separately) ---
    for path in _iter_dockerfiles(root):
        rel = os.path.relpath(path, root)
        for i, line in enumerate(read_lines(path)):
            if re.match(r"^COPY \. \.", line):
                violations.append(("Inv6", rel, i + 1, line.strip()))

    return violations


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SZL Doctrine invariant check (line-wrap tolerant).")
    ap.add_argument("--local", default=".", help="root dir of a local checkout to scan")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""),
                    help="owner/name — enables the verified-L2 (a11oy/killinchu) banner exemption")
    ap.add_argument("--json", action="store_true", help="emit JSON report")
    args = ap.parse_args(argv)

    repo = args.repo
    print(f"repo={repo.split('/')[-1] or '?'} verified_L2={int(_verified_l2_repo(repo))}")
    violations = scan_local(args.local, repo=repo)

    if args.json:
        print(json.dumps([
            {"invariant": inv, "path": p, "line": ln, "text": t}
            for inv, p, ln, t in violations
        ], indent=2))
    else:
        for inv, p, ln, t in violations:
            print(f"::error file={p},line={ln}::[{inv}] {t}")

    if violations:
        by_inv = {}
        for inv, *_ in violations:
            by_inv[inv] = by_inv.get(inv, 0) + 1
        summary = ", ".join(f"{k}={v}" for k, v in sorted(by_inv.items()))
        print(f"::error::Doctrine check FAILED ({len(violations)} violation(s): {summary}).")
        return 1
    print("All doctrine invariants satisfied (line-wrap tolerant).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
