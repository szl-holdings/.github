# Doctrine v7 Enforcement Guide

**Status:** Reference document — 2026-05-30  
**Scope:** All `szl-holdings` repositories.  
**Audience:** CI engineers and reviewers responsible for implementing and maintaining doctrine gates.

---

## Overview

Doctrine v7 adds 6 new grep CI gates, 8 new a11oy checker rules, 2 new receipt validators, 3 new human review requirements, 2 required manifest files, and 1 CODEOWNERS rule. This guide specifies the exact implementation for each.

---

## 1. grep CI Gates

All grep gates run as a single `doctrine-grep-check` CI job on every PR. The job exits non-zero if any gate fires.

### Gate G-1 — §1 Superlative Check

```bash
#!/usr/bin/env bash
# G-1: No superlatives without adjacent citation
set -euo pipefail
TERMS="revolutionary|unprecedented|world-class|seamless|industry-leading|cutting-edge|game-changing|breakthrough"
VIOLATIONS=0
while IFS= read -r -d '' file; do
  # Use Python for 5-line citation window logic
  python3 - "$file" <<'PYEOF'
import sys, re
path = sys.argv[1]
lines = open(path).readlines()
terms = ["revolutionary","unprecedented","world-class","seamless",
         "industry-leading","cutting-edge","game-changing","breakthrough"]
citation_re = re.compile(r'https?://|doi\.org|10\.\d{4,}')
for i, line in enumerate(lines):
  lower = line.lower()
  for t in terms:
    if t in lower:
      window = "".join(lines[i:min(i+5,len(lines))])
      if not citation_re.search(window):
        print(f"[G-1 FAIL] {path}:{i+1}: superlative '{t}' without adjacent citation")
        sys.exit(1)
PYEOF
done < <(git diff --name-only --diff-filter=ACM HEAD~1 HEAD | grep '\.md$' | tr '\n' '\0')
echo "[G-1 PASS] No unsupported superlatives found"
```

### Gate G-2 — §6 Emoji in Headers

Emoji check using Unicode ranges. Em-dash (U+2014), section sign (U+00A7), and mathematical
symbols (>=, <=) are permitted in headers. Only characters in emoji Unicode blocks are rejected.

```python
#!/usr/bin/env python3
# G-2: No emoji in ## or ### headers
import sys, re, subprocess
files = subprocess.check_output(
  ["git","diff","--name-only","--diff-filter=ACM","HEAD~1","HEAD"],text=True
).splitlines()
emoji_re = re.compile(
  u"[\U0001F000-\U0001FFFF"
  u"\U00002702-\U000027B0"
  u"\U0001F300-\U0001FAFF"
  u"\U00002600-\U000026FF"
  u"\U00002300-\U000023FF]"
)
header_re = re.compile(r"^#{2,3}\s+")
failed = False
for f in files:
  if not f.endswith(".md"): continue
  for i, line in enumerate(open(f).readlines(), 1):
    if header_re.match(line) and emoji_re.search(line):
      print(f"[G-2 FAIL] {f}:{i}: emoji in header: {line.rstrip()[:80]}")
      failed = True
if failed: sys.exit(1)
print("[G-2 PASS] No emoji in headers")
```

### Gate G-3 — §9 Concept-DOI Alias Labeling

```bash
# G-3: Known concept-DOI aliases must carry [concept-DOI-alias] label
KNOWN_ALIASES=("10.5281/zenodo.19944926")
for alias in "${KNOWN_ALIASES[@]}"; do
  git diff --name-only --diff-filter=ACM HEAD~1 HEAD | grep '\.md$' | while read -r file; do
    if grep -q "$alias" "$file"; then
      # Check for label within 2 lines of citation
      python3 - "$file" "$alias" <<'PYEOF'
import sys, re
path, alias = sys.argv[1], sys.argv[2]
lines = open(path).readlines()
label_re = re.compile(r'\[concept-DOI-alias\]')
for i, line in enumerate(lines):
  if alias in line:
    window = "".join(lines[max(0,i-1):min(i+3,len(lines))])
    if not label_re.search(window):
      print(f"[G-3 FAIL] {path}:{i+1}: concept-DOI alias {alias} without [concept-DOI-alias] label")
      sys.exit(1)
PYEOF
    fi
  done
done
echo "[G-3 PASS] All concept-DOI aliases labeled"
```

### Gate G-4 — §10 Badge Version Anchoring

```bash
# G-4: Badges must have version anchor within 10 lines
python3 << 'PYEOF'
import sys, re, subprocess
files = subprocess.check_output(
  ["git","diff","--name-only","--diff-filter=ACM","HEAD~1","HEAD"],
  text=True
).splitlines()
badge_re = re.compile(r'!\[.*?\]\(https?://[^)]*(?:badge|shield|passing|green|status)[^)]*\)', re.I)
anchor_re = re.compile(r'as of [0-9a-f]{7,40}|as of v\d+\.\d+', re.I)
failed = False
for f in files:
  if not f.endswith('.md'): continue
  lines = open(f).readlines()
  for i, line in enumerate(lines):
    if badge_re.search(line):
      window = "".join(lines[i:min(i+10,len(lines))])
      if not anchor_re.search(window):
        print(f"[G-4 FAIL] {f}:{i+1}: badge without version anchor within 10 lines")
        failed = True
if failed: sys.exit(1)
print("[G-4 PASS] All badges version-scoped")
PYEOF
```

### Gate G-5 — §12 Outright-Claim Check

```bash
# G-5: Catalog-grade and related claims must carry staged-advisory prefix or artifact URL
TERMS="catalog-grade|SLSA.compliant|production-ready|air-gap-ready|catalog.ready"
python3 << 'PYEOF'
import sys, re, subprocess
files = subprocess.check_output(
  ["git","diff","--name-only","--diff-filter=ACM","HEAD~1","HEAD"],text=True
).splitlines()
claim_re = re.compile(r'catalog-grade|SLSA[- ]compliant|production-ready|air-gap-ready|catalog[- ]ready', re.I)
sa_re = re.compile(r'STAGED-ADVISORY:|claimed \(unverified\):|target \(not yet achieved\):', re.I)
url_re = re.compile(r'https?://(?:github\.com|ghcr\.io|huggingface\.co|zenodo\.org)')
failed = False
for f in files:
  if not f.endswith('.md'): continue
  lines = open(f).readlines()
  for i, line in enumerate(lines):
    if claim_re.search(line):
      window = "".join(lines[max(0,i-1):min(i+2,len(lines))])
      if not sa_re.search(window) and not url_re.search(window):
        print(f"[G-5 FAIL] {f}:{i+1}: outright claim without STAGED-ADVISORY or artifact URL")
        failed = True
if failed: sys.exit(1)
print("[G-5 PASS] All capability claims correctly qualified")
PYEOF
```

### Gate G-6 — §14 Orchestrator Tag in Bot Commits

```bash
# G-6: Bot-actor commits must carry [orchestrator: <name>] trailer
BOT_ACTORS=("github-actions[bot]" "perplexity-agent[bot]" "cursor[bot]" "dependabot[bot]")
git log --pretty=format:"%ae|%B" HEAD~1..HEAD | while IFS="|" read -r email body; do
  for bot in "${BOT_ACTORS[@]}"; do
    if [[ "$email" == *"$bot"* ]] || [[ "$email" == *"noreply"* ]]; then
      if ! echo "$body" | grep -q '\[orchestrator:'; then
        echo "[G-6 FAIL] Commit by $email lacks [orchestrator: <name>] trailer"
        exit 1
      fi
    fi
  done
done
echo "[G-6 PASS] All bot commits carry orchestrator tag"
```

---

## 2. a11oy Checker (doctrine_v7_checker.ts)

The a11oy checker runs as a separate CI step after the grep gates. It produces DSSE receipts per file and fails the CI job if any violation is found in a tracked file.

### CI job: `doctrine-v7-a11oy-check`

```yaml
# .github/workflows/doctrine-v7-check.yml
name: Doctrine v7 Compliance Check

on:
  pull_request:
    branches: ["main", "release/**"]
  push:
    branches: ["main"]

jobs:
  grep-gates:
    name: Doctrine v7 grep gates
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2
      - name: Run grep gates G-1 through G-6
        run: bash .github/scripts/doctrine_v7_grep_gates.sh

  a11oy-check:
    name: Doctrine v7 a11oy checker
    runs-on: ubuntu-latest
    needs: grep-gates
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install ts-node
        run: npm install -g ts-node typescript
      - name: Run a11oy doctrine checker
        run: |
          npx ts-node tools/doctrine_v7_checker.ts \
            --dir . \
            --canonical .github/canonical_numbers.json \
            --output ./v7_receipts
      - name: Upload receipts as artifact
        uses: actions/upload-artifact@v4
        with:
          name: v7-dsse-receipts
          path: ./v7_receipts/
          if-no-files-found: error

  receipt-validator:
    name: Doctrine v7 receipt validation
    runs-on: ubuntu-latest
    needs: a11oy-check
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: v7-dsse-receipts
          path: ./v7_receipts/
      - name: Validate corpus convergence on invariant receipts
        run: |
          python3 .github/scripts/validate_invariant_receipts.py ./v7_receipts/
      - name: Check propagation deadline compliance
        run: |
          python3 .github/scripts/check_canonical_propagation.py \
            --canonical .github/canonical_numbers.json \
            --window-hours 48
```

---

## 3. Required Manifest Files

### 3-a. `.github/canonical_numbers.json` (§11)

Schema:
```json
{
  "putnam_coverage": {
    "value": "83.3% (10/12)",
    "propagation_targets": [
      "huggingface/SZLHOLDINGS/thesis-v18-formal-verification/README.md",
      "huggingface/SZLHOLDINGS/uds-spans-receipts/README.md"
    ],
    "updated_at": "2026-10-12T00:00:00Z"
  },
  "sorry_count": {
    "value": "5",
    "propagation_targets": [
      "lutar-lean/README.md",
      "lutar-lean/README.md:state-table"
    ],
    "updated_at": "2026-05-29T00:00:00Z"
  },
  "mcp_tool_count": {
    "value": "17",
    "propagation_targets": [
      "mcp-receipts-server/README.md"
    ],
    "updated_at": "2026-05-30T00:00:00Z"
  },
  "lean_declarations": {
    "value": "217",
    "propagation_targets": [],
    "updated_at": "2026-05-28T00:00:00Z"
  }
}
```

**NOTE:** This file must be populated by the Founder before §11 CI checks are active.

### 3-b. `.github/badges.json` (§10)

Schema:
```json
{
  "lutar-lean": [
    {
      "badge_url": "https://img.shields.io/badge/Lean_Kernel-Green-brightgreen",
      "anchor_commit": "7ef33a6",
      "anchor_date": "2026-05-29",
      "note": "main build is currently FAILING — badge is scoped to 7ef33a6 only"
    }
  ]
}
```

---

## 4. CODEOWNERS Rule (§16)

Add to `.github/CODEOWNERS`:

```
# Protected paths — require doctrine-authority team review per §16
.github/workflows/          @szl-holdings/doctrine-authority
.github/rulesets/           @szl-holdings/doctrine-authority
classifier/                 @szl-holdings/doctrine-authority
branch-protection.json      @szl-holdings/doctrine-authority
.github/canonical_numbers.json  @szl-holdings/doctrine-authority
```

The `doctrine-authority` team must be created in GitHub org settings with the Founder as a required member.

---

## 5. Receipt Validation Scripts

### `validate_invariant_receipts.py` (§15 enforcement)

```python
#!/usr/bin/env python3
"""
Validates that DSSE receipts asserting structural invariants carry
corpus_convergence with >=3 entries.
"""
import json, sys, pathlib, base64

receipts_dir = pathlib.Path(sys.argv[1])
failed = False

for receipt_file in receipts_dir.glob("*_v7_receipt.json"):
    envelope = json.loads(receipt_file.read_text())
    payload_raw = base64.urlsafe_b64decode(envelope["payload"] + "==")
    payload = json.loads(payload_raw)
    
    for v in payload.get("violations", []):
        if v["code"] == "INVARIANT_LOW_CORPORA":
            print(f"[FAIL] {receipt_file.name}: {v['text']}")
            failed = True

if failed:
    print("Receipt validation FAILED: invariant claims with <3 corpora found")
    sys.exit(1)

print(f"Receipt validation PASS: {len(list(receipts_dir.glob('*_v7_receipt.json')))} receipts checked")
```

### `check_canonical_propagation.py` (§11 enforcement)

```python
#!/usr/bin/env python3
"""
Checks that all propagation_targets for recently updated canonical numbers
have been updated within the specified window.
"""
import json, sys, argparse, pathlib
from datetime import datetime, timedelta, timezone

parser = argparse.ArgumentParser()
parser.add_argument("--canonical", required=True)
parser.add_argument("--window-hours", type=int, default=48)
args = parser.parse_args()

canonicals = json.loads(pathlib.Path(args.canonical).read_text())
cutoff = datetime.now(timezone.utc) - timedelta(hours=args.window_hours)
failed = False

for key, entry in canonicals.items():
    updated_at = datetime.fromisoformat(entry["updated_at"].replace("Z", "+00:00"))
    if updated_at > cutoff:
        # This canonical was updated recently — check propagation targets
        for target in entry.get("propagation_targets", []):
            target_path = pathlib.Path(target)
            if target_path.exists():
                content = target_path.read_text()
                if entry["value"] not in content:
                    print(f"[FAIL] Canonical '{key}' value '{entry['value']}' not in {target}")
                    failed = True
            else:
                print(f"[WARN] Propagation target not found locally: {target} (may be remote)")

if failed:
    print(f"Canonical propagation FAILED: stale values found within {args.window_hours}h window")
    sys.exit(1)

print("Canonical propagation PASS")
```

---

## 6. Human Review Protocol

### §3 — Axiom Review

When a PR adds or modifies a Lean axiom:
1. Reviewer must check the axiom allowlist in `lutar-lean/axiom_allowlist.json`.
2. If the axiom is not in the allowlist, the PR is blocked pending Founder approval.
3. Founder approval must be recorded as a GitHub PR review approval (not a comment).

### §4 — Sorry Discharge Route Review

When a PR introduces a `sorry` in a `.lean` file:
1. Reviewer locates the `-- discharge: <route>` comment.
2. Reviewer confirms the route is specific and actionable (not "TBD" or "future work").
3. Reviewer confirms `canonical_numbers.json` sorry count is updated.

### §15 — Invariant Founder Sign-off Review

When a PR promotes a result to validated-invariant status:
1. Reviewer checks the DSSE receipt `corpus_convergence` array (≥3 entries).
2. Reviewer checks that the Founder has left a PR review approval (not a comment).
3. The promotion is blocked until both checks pass.

---

## 7. Violation Severity Table

| Violation Code | Clause | Severity | CI Action |
|---------------|--------|----------|-----------|
| SUPERLATIVE | §1 | CRITICAL | Fail PR |
| BADGE_UNSCOPED | §10/§2 | CRITICAL | Fail PR |
| STALE_CANONICAL | §11 | CRITICAL | Fail PR (after 48h window) |
| OUTRIGHT_CLAIM | §12 | CRITICAL | Fail PR |
| ARTIFACT_NO_URL | §13 | CRITICAL | Fail PR |
| DOI_UNRESOLVED | §9 | MAJOR | Fail PR |
| EMOJI_IN_HEADER | §6 | MAJOR | Fail PR |
| UNCITED_CLAIM | §7 | MAJOR | Fail PR |
| NO_LINEAGE_TAG | §8 | MINOR | Warn + require human sign-off |
| MISSING_ORCHESTRATOR_TAG | §14 | MAJOR | Fail PR |
| INVARIANT_LOW_CORPORA | §15 | CRITICAL | Fail PR |
| PROTECTION_TOGGLE_NO_HUMAN | §16 | CRITICAL | Fail PR |

---

## 8. Audit Trail

Every CI run of `doctrine-v7-check` must produce:
1. DSSE receipts per file, uploaded as GitHub Actions artifacts (retained 90 days).
2. A `SUMMARY.json` archived to `SZLHOLDINGS/uds-governance-receipts` HuggingFace dataset on merge to `main`.
3. A GitHub commit status of `doctrine-v7` on the PR head SHA, with state `success` or `failure`.

---

*Enforcement Guide v7 | SZL | 2026-05-30 | No superlatives. No fake green. No doctrine that bends.*
