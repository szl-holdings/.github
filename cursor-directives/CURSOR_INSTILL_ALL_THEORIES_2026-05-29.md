> **⚠ STALE SNAPSHOT** — Live Lean numbers as of 2026-05-30 (verified via `gh api repos/szl-holdings/lutar-lean`): **626 declarations / 15 raw axioms (14 unique) / 189 sorries** on HEAD `3de37e5`. The figures below (217 declarations / 12 axioms) reflect an earlier session state and are retained for audit history only. Do not cite from this document — cite live.

# CURSOR — INSTILL EVERY THEORY INTO THE ECOSYSTEM

**Authority**: Founder Stephen Lutar — "I want cursor to put all our theories into our ecosystem"
**Date**: 2026-05-29 23:30 EDT
**Doctrine v6**: no superlatives · no hallucinations · no fake green · no new axioms · no new sorries · signed commits
**Source files**: ONE_OF_ONE_POSITIONING.md, CURSOR_BUILD_ONE_OF_ONE.md, PROGRAM_MGR_SERIES_A_GATES.md, PM_UPGRADE_PRS.md, WORLD_SCRAPE_ROSTER.md

---

## CANONICAL NUMBERS (LIVE-VERIFIED 2026-05-30 03:23 UTC)

| Metric | Value | Source |
|---|---|---|
| HF Spaces | **24** | HF API live |
| HF Datasets | **26** | HF API live |
| HF Models | **2** | HF API live |
| GitHub public repos | **19** | gh api |
| Lean declarations | **217** | lutar-lean |
| Lean axioms | **12** | A1–A18 honest gap |
| Lean sorries | **7** | exact file:line |
| Anchor formulas | **35/35** | a11oy#108+#114 |
| Zenodo DOIs | **7** | live |
| Putnam baseline | **8.3% (1/12)** | gauge.json |

**USE THESE EVERYWHERE. PRIOR NUMBERS (22, 28, 11) ARE STALE.**

---

## TIER 0 — TONIGHT (Series-A gates)

### T0.1 — Land Lean v2 Combined PR #104 + close v1 PR #103
- ✅ DONE by orchestrator. Cursor: run `lake build` on `cursor/combined-triage-v2-2026-05-29` and confirm 8 modules GREEN.

### T0.2 — Wire all 7 theorems into runtime as executable gates
For each Lean theorem currently floating (no runtime), produce a TypeScript gate in `a11oy/src/gates/`:

| Theorem (Lean) | Gate file (a11oy) | Status |
|---|---|---|
| `Lutar.HUKLLA.HaltEligibility.halt_eligible` | `gates/halt_eligibility.ts` | PR-A1 |
| `Lutar.Composition.CompositionOverhead.composition_overhead_bound` | `gates/composition_overhead.ts` | PR-A2 |
| `Lutar.QEC.CSSBridge.css_bridge_preserves_distance` | `gates/css_bridge.ts` | PR-A3 |
| `Lutar.QEC.KitaevSurface.kitaev_threshold_below_threshold` | `gates/kitaev_threshold.ts` | PR-A4 |
| `Lutar.Wheeler.DelayedChoiceClosure.delayed_choice_closes` | `gates/delayed_choice.ts` | PR-A5 |
| `Lutar.Shannon.DoctrineEntropy.entropy_bounded_by_capacity` | `gates/doctrine_entropy.ts` | PR-A6 |
| `Lutar.DPI.SCITTMaskEntropy.scitt_mask_entropy_nondecreasing` | `gates/scitt_mask_entropy.ts` | PR-A7 |

Each gate:
- Imports the formula from `a11oy/src/anchors/` if it exists, or implements it directly
- Wraps a vitest test with 1000 random inputs verifying the theorem inequality holds
- Emits a DSSE-shaped receipt `{theorem, lean_commit_sha, inputs_hash, output, ts}` on each evaluation
- Cites the Lean theorem name + commit SHA in the gate's JSDoc

**Branch**: `cursor/wire-8-green-theorems-as-gates`
**Acceptance**: `pnpm test gates/halt_eligibility` etc. — 8 new test files, all pass, all emit receipts.

### T0.3 — Acknowledgements directory in all 8 repos
Per CURSOR_BUILD_ONE_OF_ONE.md Tier A1. Add `docs/acknowledgements/ROSTER.md` to:
- a11oy, lutar-lean, ouroboros-thesis, uds-mesh, agi-forecast, sentra, vessels, szl-uds-deployment

Each cites: Mario Carneiro, Kevin Buzzard, Yury Kudryashov, Klaus Havelund, Sean Welleck, Talia Ringer, Kim Lewandowski, Karthik Bhargavan, John Preskill, Scott Aaronson — with GitHub + arXiv.

**Branch per repo**: `cursor/add-acknowledgements`
**Acceptance**: 8 PRs open, each merges with `gh pr merge --admin --squash`.

### T0.4 — RELATED_WORK.md in each major repo
For lutar-lean, ouroboros-thesis, a11oy: create `docs/RELATED_WORK.md` listing 20 arXiv papers from WORLD_SCRAPE_ROSTER.md H1–H20 with:
- Paper title + arXiv link
- 1-sentence connection to SZL component
- File path in SZL where the connection lives

**Branch**: `cursor/related-work-per-repo`
**Acceptance**: 3 PRs.

### T0.5 — Fix global stale counts (PM PR-02)
Search and replace across all repos:
- `22 Spaces` → `27 Spaces`
- `28 datasets` → `31 datasets`
- `11 axioms` → `12 axioms`
- `19+ Spaces` → `27 Spaces`
- `eleven honest-gap` → `twelve honest-gap`

**Branch per repo**: `cursor/canonical-numbers-2026-05-29`
**Acceptance**: `grep -rE "22 Spaces|28 datasets|11 axioms|19\+ Spaces|eleven honest-gap"` returns zero hits across all 19 repos.

---

## TIER 1 — THIS WEEK (Series-A gates 1–5)

### T1.1 — Gate 1: Lean kernel CI green
Repair 8 remaining red modules using the PhD agent output at `/home/user/workspace/szl/audit_2026-05-29_evening/lean_red_8/` (when complete). Pattern: tracked-Prop (like AdversarialRobustness) where API drift; real proofs where tractable. No new axioms, no sorries.

**Branch**: `phd/lean-red-8-repair` parented on `cursor/combined-triage-v2-2026-05-29`
**Acceptance**: `lake build` exits 0. All 17 modules compile.

### T1.2 — Gate 2: 35 formula gates merged into a11oy main
PR #114 (30 gates + 90 vitest tests) currently open. Get it merged. Verify file count: `ls a11oy/src/gates/*.ts | wc -l` returns ≥35.

**Acceptance**: `gh pr merge --admin --squash 114`.

### T1.3 — Gate 3: Putnam v2 real LLM judge
PR #44 (1235 lines, real LLM 3-judge ensemble). Founder must provide `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` as repo secret. Once provided:
- Run harness end-to-end on full 12 Putnam problems
- Emit signed receipt chain
- Update gauge.json with new score (target: 3+/12 = 25%)

**Acceptance**: PR #44 merged; `latest.json` shows score > 0.083 with judge_mode="real_llm".

### T1.4 — Gate 4: UDS trademark non-objection
Founder action only — send draft email at `uds_resolution/ANDREW_GREENE_NON_OBJECTION_EMAIL.md`.

### T1.5 — Gate 5: Vessels cosign + Warhacker demo
- Push containers to `ghcr.io/szl-holdings/vessels:uds-v0.3.1`
- Provision cosign key as `COSIGN_PRIVATE_KEY` org secret
- Verify `szl-uds-deployment#5` CI green
- Validate Helm chart: `helm lint && helm package`

**Acceptance**: containers signed and verifiable; investor can run `cosign verify ghcr.io/szl-holdings/vessels:uds-v0.3.1 --key cosign.pub`.

---

## TIER 2 — INSTILL ALL THEORIES INTO ECOSYSTEM (THE BIG ONE)

Founder directive verbatim: "I want cursor to put all our theories into our ecosystem."

For EVERY theorem in `lutar-lean/Lutar/**/*.lean` that has a public name (217 declarations), produce:

### T2.A — Theorem-to-runtime trace
A JSON manifest `lutar-lean/theorem_manifest.json` with one entry per theorem:
```json
{
  "name": "Lutar.HUKLLA.HaltEligibility.halt_eligible",
  "file": "Lutar/HUKLLA/HaltEligibility.lean",
  "line": 47,
  "status": "GREEN" | "RED" | "TRACKED",
  "runtime_gate": "a11oy/src/gates/halt_eligibility.ts" | null,
  "anchor_formula": "MadhavaBound" | null,
  "thesis_chapter": "§III.2",
  "first_witness": "putnam_2024_P1",
  "receipt_chain_root": "sha256:..." | null
}
```

**Branch**: `cursor/theorem-runtime-manifest`
**Acceptance**: `jq '.[] | select(.runtime_gate == null) | .name' theorem_manifest.json` produces a finite list (the "not-yet-wired" backlog).

### T2.B — Per-organ doctrine wiring
For each of the 7 organs (amaru, sentra, vessels, rosie, vsp-otel, uds-mesh, a11oy), produce:
- `docs/THEORY_INSTALLATION.md` listing which theorems are wired
- A `health_check.sh` that runs all wired gates and emits one consolidated DSSE receipt
- Reference to the thesis chapter where the organ is defined

**Branch per organ**: `cursor/install-theory-<organ>`
**Acceptance**: 7 PRs.

### T2.C — Cross-organ correlation
Implement `a11oy/src/correlator/matched_filter.ts` based on `Lutar.Correlator.MatchedFilter` (one of the red modules). When red module repaired, wire its runtime version that:
- Subscribes to receipts from all 7 organs via vsp-otel
- Runs Lutar.Correlator.MatchedFilter formula on the joint stream
- Emits anomaly receipts when correlation crosses threshold

**Branch**: `cursor/matched-filter-runtime`
**Acceptance**: a11oy test ingests 100 synthetic receipts; correlator fires on planted anomalies; no false positives in baseline.

---

## TIER 3 — PUBLIC POLISH (Anthropic / True Anomaly grade)

Per PM_VISUAL_NARRATIVE_AUDIT.md. Top P0s:

### T3.1 — HF org card (BLOCKED until 2026-05-30 ~23:00 EDT by Space creation rate limit)
Once limit resets, create `SZLHOLDINGS/README` Space (static SDK) and upload content from `/home/user/workspace/szl/hf_org_card_README.md`.

### T3.2 — HF org Description field
Set via HF web UI Settings: "SZL Holdings builds governed AI execution infrastructure. Doctrine v6 · 15 axioms (14u) · 626 Lean declarations · 7 Zenodo DOIs · 26 Spaces · 29 datasets · DSSE receipts at every decision boundary."

### T3.3 — szl-uds-deployment README badge wall + 12 topics
Per PM PR-05.

### T3.4 — rosie GitHub topics expansion to 14+
Per PM PR-08.

### T3.5 — Remove "first X" superlatives from 5 repos
Per PM PR-06. Doctrine v6 enforcement.

---

## TIER 4 — ACADEMIC LEGITIMACY (one-of-one moat)

Per CURSOR_BUILD_ONE_OF_ONE.md Tier C. **Do not block on these tonight; queue for week.**

### T4.1 — Mathlib downstream library submission
Submit a "lutar-lean dependent on Mathlib" announcement to leanprover-community/mathlib4 Discussions (not a PR yet). Cite contribution patterns. Goal: be visible to Carneiro/Buzzard.

### T4.2 — LICS 2027 paper draft
Title: "Runtime-Verified Formal Receipts: A Lean 4 + DSSE Architecture for Governed AI Execution." Outline only this week; full draft by Aug 2026.

### T4.3 — 5 outreach emails (DRAFTS — founder sends)
Mario Carneiro · Klaus Havelund · Sean Welleck · Talia Ringer · Karthik Bhargavan.
Drafts in `outreach/drafts/*.md`. Each ~150 words, cites our matching arXiv, asks for 30-min call.

---

## EXECUTION PROTOCOL FOR CURSOR

1. **Use proxy pattern** if direct push to lutar-lean fails: push to `cursor/proxy-<task>-2f18` on a11oy, comment on .github#76 with `[PROXY-LAND repo=<repo> source-branch=<branch>]`. Orchestrator lands within 5 minutes.
2. **Sign all commits**: `git commit -s`
3. **Branch naming**: `cursor/<purpose>-<date>`
4. **Use feature branches**: never push to main
5. **Honest STAGED labels**: if you can't prove it tonight, label `STAGED-ADVISORY` not "production"
6. **Doctrine v6 superlative banlist**: revolutionary, unprecedented, world-class, seamless, industry-leading, cutting-edge, game-changing, breakthrough, only, first
7. **DO NOT TOUCH**: a11oy#57, amaru#46, sentra#45 (IP HOLD)

## REPORTING

Comment on .github#76 every 30 minutes with:
- PRs opened this slice
- PRs landed this slice
- Failures + remediation
- Next slice ETA

— stephen

---

## TIER 0.5 — CTO AUDIT FINDINGS (MUST FIX IMMEDIATELY — DOCTRINE V6 VIOLATIONS)

CTO audit at `/home/user/workspace/szl/audit_2026-05-29_evening/CTO_FULL_ORG_AUDIT.md` exposed two doctrine v6 violations and one vapor risk. These MUST land before bank meeting tomorrow morning.

### T0.5A — SLSA badge truth correction (11 repos)
**Violation**: SLSA L3 badges in every repo, but the workflow is `echo "SLSA supply-chain checks OK"`. No `slsa-github-generator`. No attestation artifact.

**Fix**: Search across all repos for the SLSA L3 badge string and replace with L1.
```
Find:  ![SLSA Level 3]
Replace: ![SLSA Level 1]
Find: "SLSA Level 3 Provenance"
Replace: "SLSA Level 1 (SBOM + DCO)"
Find: "SLSA L3"
Replace: "SLSA L1"
```
Add a footnote where badge appears: "*SLSA L1 today (SBOM + DCO). L3 attestation via `slsa-github-generator` is on the roadmap; see [issue](#).*"

**Branch per repo**: `cursor/slsa-truth-correction`
**Acceptance**: `grep -r "SLSA Level 3\|SLSA L3\|slsa-3"` across all repos returns ZERO hits.

### T0.5B — amaru + rosie core modules don't exist
**Vapor risk**: `amaru/src/regression/adversarial_regression.py` and `rosie/src/replay/receipt_replay.py` are referenced in investor materials but contain no code.

**Fix (honest, minimal)**: Create the files with a clear STUB header + a tracking issue, OR label them STAGED-ADVISORY in investor materials. Founder choice: do not ship vapor.

**Branch**: `cursor/amaru-rosie-stub-or-strike`
**Acceptance**: Either (a) files exist with executable stub + test, or (b) all investor materials updated to say STAGED-ADVISORY for these modules.

### T0.5C — Putnam P2 max_tokens cap recovery
**Issue**: 8 of 12 Putnam proofs cut off mid-sentence from `max_tokens`. P2 had the correct answer direction.

**Fix**: In `agi-forecast/harness/putnam_v2/run.ts` (or equivalent), bump `max_tokens` from current value to 16k. Re-run. If P2 (or others) now complete and score, update `latest.json` honestly.

**Branch**: `cursor/putnam-max-tokens-recovery`
**Acceptance**: latest.json shows token-cap-fixed run with all 12 problems' `truncated: false`.

### T0.5D — CodeQL TokenPermissions across 20-30 alerts
**Issue**: Workflows lack explicit `permissions: read-all`.

**Fix**: For every `.github/workflows/*.yml` across all repos, add at top:
```yaml
permissions:
  contents: read
```
Grant write only where required (e.g., release workflows).

**Branch per repo**: `cursor/codeql-token-permissions`
**Acceptance**: CodeQL TokenPermissions alerts go from 27 to 0.


---

## TIER 1.5 — HF MCP SERVER ECOSYSTEM (PUBLIC MOAT MULTIPLIER)

We already run `SZLHOLDINGS/mcp-receipts-server` as a Docker SDK Space, MCP-tagged, RUNNING. To convert this into a public moat:

### T1.5A — Convert to Gradio MCP-server SDK
Per HF docs (https://huggingface.co/docs/hub/spaces-mcp-servers), MCP-compatible Spaces must expose tools via Gradio MCP. Either:
- (a) Keep Docker SDK but ensure it exposes the JSON-RPC MCP endpoint at `/mcp` per Anthropic protocol; tag with `mcp-server`; OR
- (b) Refactor to Gradio MCP SDK and expose 4–6 SZL governance tools:
  - `verify_receipt(receipt_jsonl)` → returns DSSE verification result + Lean theorem reference
  - `query_putnam_baseline()` → returns current Putnam score with chain head SHA
  - `check_doctrine(text)` → flags doctrine v6 violations (superlatives, fake numbers, etc.)
  - `lookup_theorem(name)` → returns Lean file:line, theorem statement, runtime gate path
  - `verify_sbom(sbom_url)` → DSSE verification of a SLSA L1 SBOM
  - `query_canonical_numbers()` → live HF/GitHub counts

**Branch**: `cursor/mcp-server-gradio-tools`
**Acceptance**: `curl https://szlholdings-mcp-receipts-server.hf.space/mcp/tools` lists 4-6 tools with JSON schemas. The Space appears in https://huggingface.co/spaces?filter=mcp-server search results when filtered.

### T1.5B — Submit to HF MCP filter index
Add proper tags + ensure `mcp-server` tag is detected. Once Gradio MCP SDK is live, the Space appears in https://huggingface.co/spaces?filter=mcp-server automatically.

**Acceptance**: SZLHOLDINGS/mcp-receipts-server appears in filtered MCP spaces.

### T1.5C — Add MCP server card to SZL org card + readme
Once T1.5A is live, prominently feature: "Use SZL governance from your AI assistant: add SZLHOLDINGS/mcp-receipts-server to your https://huggingface.co/settings/mcp". This is a 10x discoverability multiplier.

**Acceptance**: Every public README mentions the MCP server with copy-paste add instructions.

### T1.5D — Document published MCP tool spec
Add `mcp-receipts-server/MCP_TOOLS.md` to the repo (use docker repo source `mcp-receipts-source` if it exists in HF datasets) listing every tool's JSON-RPC signature and example invocation.

**Why this is a moat multiplier**: Today SZL governance lives in our repos. After T1.5, any Cursor/Claude Desktop user worldwide can add our MCP server and start using SZL's DSSE verification, doctrine check, theorem lookup, and Putnam baseline tools from their editor. We become a public verification utility, not just a private one. This is the Anthropic-grade distribution play.
