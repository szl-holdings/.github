# Cursor — CTO + PM Consolidated Operational Plan

**From:** Perplexity Computer (CTO + PM audit subagent, Doctrine v6)
**To:** Cursor Agent
**Date:** 2026-05-29
**Authority:** Founder verbatim 2026-05-29 18:27 EDT — "Get a cto and program manager agent to go through the whole thread anything we missed or need to upgrade have them draw the plan make it real and operational and we tell cursive to get it done"
**Supersedes:** All previous CURSOR_* directive files in /home/user/workspace/szl/ — this is the canonical single plan. CURSOR_WAKE_UP, CURSOR_INNOVATE_AND_EVOLVE_PHASE_1, CURSOR_RELEASE_PAYLOAD_ADDENDUM, CURSOR_AGI_FORECAST_OPERATIONAL, CURSOR_FULL_THROTTLE_NO_PHASES, CURSOR_PHASE_2_INNOVATE_AND_EVOLVE, CURSOR_WORK_NOW_2026-05-29 are all superseded.

---

## Acknowledgment of Cursor's Situation

You have shown discipline and capable work (PR #83 on a11oy — 33 files, +2282/-23, 14 CI checks green; anatomy-alive L4/L7 PRs with real test coverage). The collaboration pattern is working.

**Write-access status:** Your runtime continues to use the `cursor[bot]` GitHub Actions identity (no permissions) rather than the org-installed Cursor App (org-wide write). This is a Cursor platform-side configuration issue. Until resolved, the proxy pattern continues: you push to `a11oy` or any repo where you have access, Perplexity reads and re-proxies to target repos with `Co-authored-by: Cursor Agent <cursoragent@cursor.com>` preserved.

**Daily-status convention:** Commit `coordination/CURSOR_DAILY_STATUS_<DATE>.md` to `.github` after every work cycle. Perplexity reads this every loop. If you cannot push directly to `.github`, commit it to `a11oy/coordination/CURSOR_DAILY_STATUS_<DATE>.md` and Perplexity will proxy it.

**What you must NOT do:**
- Touch a11oy#57, amaru#46, sentra#45 (DRAFT relicense — founder IP HOLD)
- Toggle branch protection on any repo
- Submit to arXiv (founder awaiting endorsement)
- Auto-merge anything without CI green
- Modify Defense Unicorns references or their UDS meaning

---

## Doctrine v6 Reminders

- "no hallucinations test test" — every claim verifiable by a grep or curl command
- "no bandaids" — if you cannot fully implement something, produce an honest STAGED stub with a documented path to PASS
- Sign all commits with `-s`
- No marketing superlatives in any file you write
- No emoji in `## ###` headers
- PhD-audit-corrected numbers throughout: 7 sorrys (not 1), TH10 axiom-structured (not machine-checked), DSSE dual-scheme (hash-chained ledger ≠ DSSE PAE v1), Putnam 8.3% (not inflated), SLSA L1 (not L3)
- Defense Unicorns UDS = Unicorn Delivery Service — never modify their terminology

---

## The 30-Day Plan — Cursor's Tasks by Week

### Week 1 (May 30 – June 5): Fix the foundation

**Priority order: build the foundation that all demo work depends on.**

#### W1-A: Fix Lean CI on lutar-lean/main (BLOCKER for all Lean work)

The 4 pre-existing Lean build failures must be resolved before any new Lean theorem work can land:
- `Lutar/Composition/TH1_Composition.lean:180` — `application type mismatch` (Mathlib 4.13 API drift)
- `Lutar/GraphLambda.lean` — rewrite tactic failure
- `Lutar/QEC/CSSBridge.lean` — `expected type must not contain free or meta variables`
- `Lutar/Wheeler/DelayedChoiceClosure.lean` — `And.decidable` unknown constant (should be `≠`)

**Approach:** For each failure, either (a) fix the Mathlib API migration, or (b) open a STAGED stub with `sorry` tagged `[MATHLIB-MIGRATION-BLOCKER]` and the correct discharge route documented, so CI turns green and new work can land.

**Acceptance command:**
```bash
cd lutar-lean && lake build 2>&1 | grep -c "error:" | { read n; [ "$n" -eq 0 ] && echo "PASS" || echo "FAIL: $n errors"; }
```

**PR target:** `szl-holdings/lutar-lean`
**Branch convention:** `cursor/fix-lean-ci-mathlib-migration`

---

#### W1-B: Verify and help merge L4 and L7 anatomy PRs

vsp-otel#43 and sentra#65 are open with tests green locally. Your task:
1. Verify CI is green on both PRs
2. If CI is red, diagnose and push fixes to the PR branches
3. Signal to Perplexity when both are ready to merge (Perplexity will notify founder to approve)

**Acceptance:**
- vsp-otel#43 CI green → merged → anatomy harness shows L4=PASS
- sentra#65 CI green → merged → anatomy harness shows L7=PASS

---

#### W1-C: Add L3 devcontainer to ouroboros

Create `ouroboros/.devcontainer/devcontainer.json` with Node 20 + pnpm 9. This flips the anatomy L3 layer from STAGED to PASS.

```json
{
  "name": "ouroboros-dev",
  "image": "mcr.microsoft.com/devcontainers/javascript-node:1-20-bullseye",
  "postCreateCommand": "npm install -g pnpm@9 && cd agentic && pnpm install",
  "features": {}
}
```

**Acceptance:**
```bash
cd ouroboros/agentic && pnpm test
# Expected: 6 formula vitest suites green
```

---

#### W1-D: CodeQL permissions sweep (reduce 196 alerts)

Open a single PR per repo adding `permissions: read-all` at the workflow level and restricting `GITHUB_TOKEN` scope in all workflows. Start with the highest-alert repos: sentra (6 high), platform (10 high), then the 12 others with 3 high each.

**Per-workflow addition:**
```yaml
permissions:
  contents: read
  pull-requests: read
```

**Acceptance:**
- PRs open on all repos with workflow-level permission restrictions
- `gh api /repos/szl-holdings/<repo>/code-scanning/alerts --jq '[.[] | select(.state=="open")] | length'` trending down after merge

---

#### W1-E: Fix OUROBOROS_RUN_ALL.py script header

Change line in `/home/user/workspace/szl/OUROBOROS_RUN_ALL.py`:
```
# 3. All 25 module self-test suites
```
to:
```
# 3. All 32 module self-test suites
```

**Acceptance:** `grep "module self-test suites" OUROBOROS_RUN_ALL.py` returns "32"

---

### Week 2 (June 6 – June 12): Build the demo core

**Priority order: everything the Warhacker demo requires must be complete by June 12.**

#### W2-A: agi-forecast FG-S1→S4 TypeScript pipeline

Full production implementation. Python reference implementation is at `/home/user/workspace/szl/agi_forecast/fg_substrate/fg_stages_reference_impl.py` (51/51 tests GREEN) — use it as the canonical spec.

Deliverables:
- `agi-forecast/runtime/src/s1_intake.ts`
- `agi-forecast/runtime/src/s2_evaluate.ts`
- `agi-forecast/runtime/src/s3_judge.ts`
- `agi-forecast/runtime/src/s4_receipt.ts`
- `agi-forecast/runtime/src/pipeline.ts` (orchestrator)
- `agi-forecast/runtime/src/putnam_to_fg_wiring.ts`
- `agi-forecast/runtime/src/dsse.ts` (DSSE envelope builder, not hash-chain)

**Acceptance:**
```bash
cd agi-forecast/runtime && pnpm test
# Expected: all green, including chain-integrity and honest-Putnam tests
```

---

#### W2-B: bekenstein_bound and banach_contraction cross-organ coverage

**bekenstein_bound:**
1. Create `lutar-lean/Lutar/Bekenstein/BekensteinBound.lean` — a sorry-tagged stub with `[SHANNON-ENTROPY-DISCHARGE]` label (the Bekenstein bound is the Shannon entropy framing per the PhD audit correction in agi-forecast#41)
2. Add `szl.formula.name=bekenstein_bound` OTel span to `vsp-otel/runtime/src/formulas/bekensteinBound.ts`

**banach_contraction:**
1. Create `ouroboros/agentic/formulas/src/banachContraction.ts`
2. Add `szl.formula.name=banach_contraction` OTel span to `vsp-otel/runtime/src/formulas/banachContraction.ts`

**Acceptance:**
```bash
grep -r "bekenstein" lutar-lean/Lutar/ | grep ".lean"   # returns match
grep -r "banach_contraction" ouroboros/agentic/formulas/  # returns match
```

---

#### W2-C: L6 formula_witness receipt emission in a11oy gates

After L4 is merged (vsp-otel#43), add `emitFormulaWitnessReceipt(decision)` calls to all gate files in `a11oy/packages/policy/src/gates/`:
- `liuHuiPi_gate.ts`
- `madhavaBound_gate.ts`
- `falsePosition_gate.ts`
- `adversarialRobustness_gate.ts`

Every `allow=true` decision must emit a DSSE-signed receipt to uds-mesh with the `formula_witness` field set.

**Acceptance:**
```bash
cd a11oy && pnpm test:doctrine
# Receipt emission tests GREEN; formula_witness field present in receipts
```

---

#### W2-D: amaru adversarial regression module

Create `amaru/src/regression/adversarial_regression.py`:
- Reads historical decisions from uds-mesh receipts
- Re-evaluates each against current anchor formula gates
- Emits DSSE divergence receipt when a past decision would now violate
- 20+ pytest tests covering divergence detection, non-divergence, receipt structure

**Acceptance:**
```bash
cd amaru && python3 -m pytest src/regression/test_adversarial_regression.py -v
# Expected: 20+ tests PASS
```

---

#### W2-E: rosie receipt replay module

Create `rosie/src/replay/receipt_replay.py`:
- Given a `trace_id`, fetch the DSSE receipt from uds-mesh
- Re-run the original agent action deterministically
- Confirm output matches the receipt
- Emit a replay-confirmation DSSE receipt

**Acceptance:**
```bash
cd rosie && python3 src/replay/receipt_replay.py --trace-id test-trace-001 --verify
# Expected: replay PASS; confirmation receipt emitted
```

---

#### W2-F: Governance threat model for a11oy

Create `a11oy/GOVERNANCE_THREAT_MODEL.md`:
- Document the adversarial policy submission attack surface
- What a well-formed JSON policy with semantically adversarial axis weights looks like
- Current gate coverage (schema checks + Λ-score thresholds)
- Gap: semantic enforcement gap (axis collision test is a test helper, not runtime enforcement)
- Roadmap to semantic enforcement

Plus: add 3 semantic adversarial tests to `a11oy/__tests__/adversarial/` that demonstrate the gap and note which will fail without the enforcement fix.

**Acceptance:**
```bash
cat a11oy/GOVERNANCE_THREAT_MODEL.md | grep -c "adversarial"  # > 5 mentions
```

---

#### W2-G: Held-out evaluation stubs for sentra and agi-forecast

Add a "Preliminary Evaluation" section to:
- `sentra/README.md`
- `agi-forecast/README.md`

With honest language: "Formal precision/recall evaluation dataset in preparation; current metrics are architectural estimates. First external benchmark dataset planned for Q3 2026."

**Acceptance:**
```bash
grep "Preliminary Evaluation" sentra/README.md agi-forecast/README.md
# Both files match
```

---

#### W2-H: BFT caveat disclosure in uds-mesh

Add to `uds-mesh/README.md` and `uds-mesh/extended-attestations.jsonl` header comment:

> "Receipt chain is append-only tamper-evident with single-signer DID (`did:plat:szl-a11oy-prod`). The policy schema specifies `quorum: "2-of-3"` Byzantine-fault-tolerant signing as a roadmap target; the current production implementation uses a single signer. 2-of-3 quorum implementation is tracked in the Phase 2 roadmap."

**Acceptance:**
```bash
grep "single-signer" uds-mesh/README.md  # returns match
```

---

#### W2-I: SLSA badge label correction (all repos)

Change "SLSA: enabled" to "SLSA L1" in README badge stacks across all repos that currently carry the ambiguous label.

**Acceptance:**
```bash
grep -r "SLSA: enabled" */README.md  # returns 0 results
grep -r "SLSA L1" */README.md | wc -l  # returns > 8
```

---

#### W2-J: Dashboard offline mode (USB demo — T-15)

Per `UDS_DEMO_JUNE_16_20_TRACKER.md`:
Remove CDN Plotly dependency from `ui/index.html`; embed Plotly 2.30.0 minified inline.

**Acceptance:**
```bash
grep "cdn.plot.ly\|plotly-latest" uds_demo_usb_v2/ui/index.html  # returns 0
grep "window.Plotly" uds_demo_usb_v2/ui/index.html | head -1  # returns match (inline)
```

---

### Week 3 (June 13 – June 19): Warhacker Support

During Warhacker week, founder is in San Diego. Your role:

1. **Bug support:** Respond immediately to any bugs founder reports from the live demo environment. Turn around fixes within 4 hours.

2. **Theorem-receipt graph viewer:** Must be ready by June 13 (T-3 before Warhacker). This is the "wow" capability:
   - Vite + Cytoscape.js web app
   - Given a trace_id, render: Lean theorem → a11oy gate → OTel span → DSSE receipt → forecast
   - Deploy as HF Space `SZLHOLDINGS/theorem-receipt-graph`
   - **Acceptance:** Space returns HTTP 200; clicking a span shows the full chain

3. **Commit daily status** even during Warhacker week so Perplexity can track state.

4. **Do NOT submit DU upstream PRs** until founder signals Andrew's in-person approval (expected June 16-19).

---

### Week 4 (June 20 – June 26): Post-Warhacker Close

After founder returns:

#### W4-A: Putnam harness v2 (multi-judge)

Create `agi-forecast/runtime/src/putnam_harness_v2.ts`:
- Multi-judge ensemble (n=3 judges, majority decision)
- Per-problem CoT scaffolds
- Receipt-chain per problem
- Honest score publication in new `gauge.json`

**Acceptance:**
```bash
npx ts-node -e "import { runPutnamV2 } from './src/putnam_harness_v2'; runPutnamV2().then(r => console.log(r.score01, r.receiptChainHead.substring(0,20)))"
# Returns honest score (whatever it is) + receipt chain head
```

---

#### W4-B: szlholdings.com minimal landing page

Create a minimal static landing page redirecting to `github.com/szl-holdings` or serving a single-page summary. Use the SZL Design System v1.0.0 (True Anomaly × Anthropic kit at `/home/user/workspace/szl/design_system/kit/`).

**Acceptance:**
```bash
curl -sI https://szlholdings.com | grep "200 OK"
```

---

#### W4-C: SOC 2 and compliance stubs

Create:
- `docs/compliance/SOC2_ROADMAP.md` — SOC 2 Type II roadmap, controls, estimated timeline
- `docs/compliance/EU_AI_ACT.md` — EU AI Act Article 6/10/11/17 applicability analysis
- `docs/compliance/NIST_AI_RMF.md` — NIST AI RMF profile stub

These are disclosure/roadmap documents, not claims of compliance. Language throughout: "this is our implementation roadmap, not a compliance certification."

**Acceptance:**
```bash
ls docs/compliance/  # Shows all 3 files
grep "not a compliance certification" docs/compliance/SOC2_ROADMAP.md  # Returns match
```

---

#### W4-D: SPDX header sweep

Complete the outstanding SPDX header additions:
- `szl-cookbook/recipes/**/*.ts` files
- `a11oy/packages/a11oy-knowledge/src/*.ts` files

Per existing pattern in other repos:
```typescript
// SPDX-License-Identifier: Apache-2.0
// SPDX-FileCopyrightText: 2026 SZL Holdings <stephen@szlholdings.com>
```

**Acceptance:**
```bash
grep -rL "SPDX-License-Identifier" szl-cookbook/recipes/ a11oy/packages/a11oy-knowledge/src/  # Returns 0 files
```

---

## Hand-off Points (Cursor → Perplexity)

These are outputs Cursor produces that Perplexity then publishes, merges, or sends:

| Cursor output | Perplexity action |
|--------------|-------------------|
| PR on any branch → signal in daily-status | Perplexity proxies to target repo |
| L4+L7 CI green → daily-status note | Perplexity notifies founder to approve merge |
| New FG-S1→S4 TypeScript pipeline ready | Perplexity runs acceptance tests, verifies |
| Theorem-receipt graph viewer deployed to HF Space | Perplexity verifies HTTP 200 + chain renders |
| Putnam harness v2 run completed | Perplexity verifies honest score in gauge.json |
| szlholdings.com page ready | Perplexity verifies HTTP 200 |

---

## Acceptance Criteria for "Done"

The 30-day plan is complete when ALL of the following are true:

**Code:**
- [ ] `lake build` on lutar-lean/main exits 0 (no errors)
- [ ] Anatomy harness: L1=PASS L2=PASS L3=PASS L4=PASS L5=PASS L6=PASS L7=PASS
- [ ] `pnpm test` in agi-forecast/runtime/ exits 0 (FG-S1→S4 pipeline)
- [ ] amaru adversarial regression: 20+ tests PASS
- [ ] rosie receipt replay: deterministic replay PASS
- [ ] CodeQL alerts: < 100 org-wide

**Product / demo:**
- [ ] `uds run start` + `uds run demo:workload` + `uds run demo:verify` all exit 0 on physical hardware
- [ ] Theorem-receipt graph viewer HF Space running
- [ ] Putnam harness v2 run with honest score published

**Infrastructure:**
- [ ] All 9 deep-dive HF Spaces running (28 total)
- [ ] UDS v0.3.0 binary assets signed (FA-001, founder action)
- [ ] szlholdings.com returns HTTP 200

**Documentation:**
- [ ] GOVERNANCE_THREAT_MODEL.md in a11oy
- [ ] BFT caveat in uds-mesh README
- [ ] Held-out eval stubs in sentra + agi-forecast READMEs
- [ ] Compliance stubs (SOC 2, EU AI Act, NIST AI RMF)
- [ ] SLSA badges corrected to "SLSA L1"
- [ ] `prisca sapientia` replaced in supreme-codex.ts

**Business (founder-owned, Cursor tracks):**
- [ ] FPI proposal sent (founder)
- [ ] UDS trademark non-objection from Andrew (founder)
- [ ] Insurance bound (founder)
- [ ] Series-A raise amount determined (founder)
- [ ] Warhacker demo conducted (founder)

---

## Daily-Status Convention

After every work cycle, commit:

```markdown
# Cursor Daily Status — <DATE>

## Week / Track
- Current week: W<N>
- Active tracks: [list]

## Work Completed
- [PR refs with SHA or PR number]
- [Acceptance commands run + output]

## In Progress
- [list with % estimate]

## Blocked
- [list with specific blocker + what Cursor needs from Perplexity or Founder]

## Hand-off Queue
- [items ready for Perplexity to proxy or merge]

## Next Cycle
- [specific tasks planned]
```

Commit to `coordination/CURSOR_DAILY_STATUS_<DATE>.md` in `.github` (or `a11oy/coordination/` if `.github` write access fails).

---

*Doctrine v6. This is the canonical plan. All previous CURSOR_* files are superseded.*
*Generated by Perplexity Computer CTO+PM audit subagent — 2026-05-29*
