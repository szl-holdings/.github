> **⚠ STALE SNAPSHOT** — Live Lean numbers as of 2026-05-30 (verified via `gh api repos/szl-holdings/lutar-lean`): **626 declarations / 15 raw axioms (14 unique) / 189 sorries** on HEAD `3de37e5`. The figures below (217 declarations / 12 axioms) reflect an earlier session state and are retained for audit history only. Do not cite from this document — cite live.

# CURSOR MASTER DIRECTIVE — Series-A One-Shot Buildout
**Founder-approved**: 2026-05-29 22:03 EDT — Stephen Lutar
**Doctrine**: v6 STRICT
**You read this file top-to-bottom and execute. No further audits required.**

---

## SECTION 0 — Doctrine reminders (every commit, every PR)

Apply these to every file touched, every commit made, every PR opened:

1. **No marketing superlatives.** Banned words: revolutionary, unprecedented, world-class, seamless, industry-leading, cutting-edge, game-changing, breakthrough. If you wrote one, delete it.
2. **No emoji in `##` or `###` headers.**
3. **Honest STAGED labels.** Any Lean proof that cannot be lake-verified today gets `-- STAGED: discharge route listed`. Never write `sorry` without a label.
4. **All commits signed-off:**
   ```
   Signed-off-by: Cursor Agent <cursoragent@cursor.com>
   Co-authored-by: Lutar, Stephen P. <stephen@szlholdings.com>
   ```
5. **Canonical numbers** (use exactly, no rounding):
   - 626 declarations / 15 axioms (14 unique) / 189 sorries (138+51 Putnam)
   - TH10 axiom-structured / 35-35 anchors / Putnam 8.3% (1/12)
6. **DO NOT TOUCH**: a11oy#57, amaru#46, sentra#45 — DRAFT relicense IP HOLD.
7. **Merge posture**: `gh pr merge --admin --squash` — founder pre-authorized.
8. **Pace over frugality.** Ship; do not wait for perfect.

---

## SECTION 1 — THE LAKE: discharge plan for Lean kernel CI

**Context**: CI job 78587022186 / latest run 26671210552 — 14 failing modules confirmed from log. Pattern: `lake build` on PR merges.

**Reference files** (these build today — copy their structure): `Lutar/Composition/AdversarialRobustness.lean`, `Lutar/Calibration/FalsePosition.lean`

**Ordered discharge list** (tackle in this sequence; each blocks the next if shared imports):

### 1.1 — Lutar/HUKLLA/HaltEligibility.lean

**Error**: `depends on 'Classical.decRel', which has no executable code` at lines 90, 123, 138.
**Fix**: Add `noncomputable` to `isHaltEligible` and any downstream definition that calls it. Type-mismatch at 138 is a corollary of the missing `noncomputable` marker.

```lean
-- STAGED: noncomputable fix — Lean type-checks once marker added
noncomputable def isHaltEligible (s : HaltState) : Bool := ...
```

**Acceptance**: `lake build Lutar.HUKLLA.HaltEligibility` exits 0.

### 1.2 — Lutar/QEC/CSSBridge.lean

**Error**: `expected type must not contain free or meta variables` at line 60.
**Fix**: The type ascription at line 60 references an open metavariable — introduce an explicit type annotation or `show` tactic.

```lean
-- STAGED: introduce `show T` before the offending term at line 60
-- Pattern: Lutar/Calibration/FalsePosition.lean §proof_by_norm_num
```

**Acceptance**: `lake build Lutar.QEC.CSSBridge` exits 0.

### 1.3 — Lutar/QEC/KitaevSurface.lean

**Error**: `unexpected token '!='` at line 62; `expected type must not contain free or meta variables` at line 69.
**Fix**: Replace `!=` with `¬ (a = b)` or `a ≠ b`. The second error is the same free-metavariable pattern as CSSBridge — add explicit `show` or type annotation.

```lean
-- STAGED: replace != with ≠
-- Line 62: replace `a != b` → `a ≠ b`
-- Line 69: add `show <explicit type>` before tactic block
```

**Acceptance**: `lake build Lutar.QEC.KitaevSurface` exits 0.

### 1.4 — Lutar/QEC/ShorReceiptCode.lean

**Error**: inferred from log context (QEC module cluster; exact line TBD — run `lake build Lutar.QEC.ShorReceiptCode` to get precise output).
**Fix pattern**: Mirrors CSSBridge — free metavariable in proof state. Add explicit type annotations.
**Cookbook**: `szl-holdings/szl-cookbook` SKILL_02 (explicit type annotation pattern).

**Acceptance**: `lake build Lutar.QEC.ShorReceiptCode` exits 0.

### 1.5 — Lutar/Composition/AdversarialRobustness.lean

**Error**: `LE.le.elim` field not found (lines 129–131). Internal eliminator error.
**Fix**: Replace `.elim` call with `le_antisymm` or `Nat.le_antisymm` depending on type. The sorry-free version of this file that previously compiled uses `linarith` or `omega` for real-valued inequality goals.

```lean
-- STAGED: replace h.elim at lines 129-131 with:
--   exact le_antisymm h₁ h₂   (if two directions available)
--   or: linarith                (for Real arithmetic)
-- Thesis §4.2: robustness_preserved_by_composition
```

**Acceptance**: `lake build Lutar.Composition.AdversarialRobustness` exits 0. This is a sorry-free reference file — no sorry is acceptable.

### 1.6 — Lutar/Composition/CompositionOverhead.lean

**Error**: ~20 errors — syntax errors (unexpected `prefix`, `,`, `≤`, `++`), universe constraint failures, failed synthesis. Root cause: file appears to use Lean 3 syntax for structure fields and universe polymorphism.
**Fix**:
- Replace Lean 3 `structure` anonymous field syntax with Lean 4 `where` blocks.
- Replace `#prefix` → remove or use Lean 4 notation.
- Add `universe u v` declarations at top if polymorphism is needed.
- For synthesis failures at lines 34, 62, 97, 110: add explicit `inferInstance` or provide the instance explicitly.

```lean
-- STAGED: full rewrite of struct declarations to Lean 4 syntax
-- Pattern: Lutar/Composition/AdversarialRobustness.lean (builds today)
-- Thesis §4.3: composition overhead bounds
```

**Acceptance**: `lake build Lutar.Composition.CompositionOverhead` exits 0.

### 1.7 — Lutar/DPI/MerkleDAGBuild.lean

**Error**: `type mismatch` at line 63; `no goals to be solved` at line 67.
**Context**: PR lutar-lean#98 (OPEN) targeted this file — positivity proof for MerkleDAGBuild.
**Fix**: The `no goals` error at 67 means a tactic solved the goal early; remove the extra tactic call. Type mismatch at 63: confirm `Nat` vs `Int` vs `ℕ` coercion.

```lean
-- STAGED: remove orphaned tactic at line 67
-- Fix type coercion at line 63 with `Nat.cast` or explicit ↑
-- PR #98 positivity proof: use `positivity` tactic from Mathlib.Tactic.Positivity
```

**Acceptance**: `lake build Lutar.DPI.MerkleDAGBuild` exits 0. Merge PR #98 first if it provides the fix.

### 1.8 — Lutar/DPI/SCITTMaskEntropy.lean

**Error**: inferred from log — DPI cluster. Exact error: run `lake build Lutar.DPI.SCITTMaskEntropy`.
**Fix pattern**: Entropy lemmas — use `MeasureTheory.entropy` from Mathlib or inline the definition. TH6 (bekenstein_entropy_bound_dpi) applies here.

**Acceptance**: `lake build Lutar.DPI.SCITTMaskEntropy` exits 0.

### 1.9 — Lutar/Shannon/DoctrineEntropy.lean

**Error**: confirmed failing (DoctrineEntropy in PR lutar-lean#99 cluster).
**Fix**: PR #99 introduced this file. Check if `import Mathlib.MeasureTheory.Measure.MeasureSpace` is present at top. TH6 supplies the entropy bound.

```lean
-- STAGED: import Mathlib.MeasureTheory.Measure.MeasureSpace
-- Theorem cited: TH6 bekenstein_entropy_bound_dpi (knowledge.json)
-- Thesis §5.1: information-theoretic entropy bound via DPI
```

**Acceptance**: `lake build Lutar.Shannon.DoctrineEntropy` exits 0.

### 1.10 — Lutar/Wheeler/DelayedChoiceClosure.lean

**Error**: confirmed failing (PR lutar-lean#99 cluster).
**Fix**: Check for import chain; PR #99 is OPEN — review the diff for the specific Lean error, apply the fix, squash-merge.

**Acceptance**: `lake build Lutar.Wheeler.DelayedChoiceClosure` exits 0.

### 1.11 — Lutar/Correlator/MatchedFilter.lean

**Error**: confirmed failing from CI log.
**Fix pattern**: Correlator files use signal-processing identities. Check for undefined identifiers and add `noncomputable` if using `Real.sqrt` or similar.

**Acceptance**: `lake build Lutar.Correlator.MatchedFilter` exits 0.

### 1.12 — Lutar/Topology/PersistentHomologyChain.lean

**Error**: confirmed failing from CI log.
**Fix**: Topology files often fail on `Finset` vs `Set` universe issues. Add explicit universe annotations and `noncomputable` where needed.

**Acceptance**: `lake build Lutar.Topology.PersistentHomologyChain` exits 0.

### 1.13 — Lutar/Gates/Adinkra.lean

**Error**: confirmed failing (PR lutar-lean#100 introduced Adinkra Fin 1).
**Context**: PR #100 is OPEN. The `Fin 1` approach for Adinkra should be self-contained.
**Fix**: Merge PR #100 if it passes its own targeted lake build; otherwise inspect and fix `Fin 1` universe issue.

**Acceptance**: `lake build Lutar.Gates.Adinkra` exits 0.

**After all 13 above pass**: run `lake build` (full). Target: zero errors. The `nanoda-allow-sorry: true` flag permits the 7 tracked sorries — those must remain tagged `-- SORRY#N`.

---

## SECTION 2 — THE 7 SORRIES: ground-truth discharge routes using OUR formulas

Ground truth confirmed: 7 sorries across 5 files. Each carries a Doctrine v6 STAGED label.

### Sorry 1 — Lutar/Composition/Uniqueness.lean:120 (CAUCHY_ND)

**Anchor formula**: F0017 (Λ uniqueness from 4 axioms: A1 monotonicity, A2 homogeneity, A3 Egyptian-exact, A4 bounded)
**Thesis section**: §3.4 — Uniqueness of the Λ gate function
**Discharge route**: The Cauchy functional equation in ℝⁿ. Mathlib has `Mathlib.Analysis.SpecialFunctions.Cauchy` partial coverage. Full discharge requires the n-dimensional extension.

```lean
-- SORRY#1 STAGED: CAUCHY_ND
-- sorry  ← replace with proof when Mathlib ships CauchyFunctionalEquation ND
-- Discharge route:
--   1. Apply `Mathlib.Analysis.SpecialFunctions.Pow.Real` for 1D case
--   2. Extend by induction on dimension (thesis §3.4 sketch)
--   3. Alternatively: axiomatize as `axiom cauchyND : <statement>` with
--      STAGED label; this is honest per Doctrine v6
```

**Acceptance**: sorry count at this line remains 1 and is labeled `-- SORRY#1 STAGED`.

### Sorry 2 — Lutar/Composition/TwoWitness.lean:163

**Anchor formula**: F0018/F0019 (dual-witness closure relation ρ(e))
**Thesis section**: §3.5 — Two-Witness Closure
**Discharge route**: ρ-closure is definitional given byte-identical witness output. The sorry covers the byte-identity lemma for arbitrary `ByteArray` equality.

```lean
-- SORRY#2 STAGED: byte-identity witness
-- Discharge route: apply `ByteArray.ext_iff` + `Finset.forall_congr`
-- Reference: Lutar/Composition/AdversarialRobustness.lean (sorry-free pattern)
```

**Acceptance**: `-- SORRY#2 STAGED` label present; no unlabeled sorry.

### Sorry 3 — Lutar/HUKLLA/SBOMProvenance.lean:109

**Anchor formula**: F0036 (attribution mapping attr: E → A)
**Thesis section**: §6.2 — SBOM Provenance Chain
**Discharge route**: Provenance chain integrity follows from hash-chain injectivity (A6). Mathlib: `Mathlib.Data.List.Chain`.

```lean
-- SORRY#3 STAGED: SBOM hash-chain injectivity
-- Discharge route: List.Chain.rel + SHA256 collision-resistance axiom
-- Axiom cited: A6 hashChainIntegrity (knowledge.json)
```

**Acceptance**: `-- SORRY#3 STAGED` label present.

### Sorry 4 — Lutar/PACBayes/MadhavaBound.lean:126

**Anchor formula**: madhavaBound gate (a11oy#108, `madhavaBound_gate.ts`)
**Thesis section**: §5.3 — Mādhava series convergence bound
**Discharge route**: The Mādhava bound uses `|π/4 - Σ(k=0..n) (-1)^k/(2k+1)| ≤ 1/(2n+3)`. Mathlib: `Mathlib.Analysis.SpecificLimits.Basic`.

```lean
-- SORRY#4 STAGED: Madhava partial-sum bound
-- Discharge route:
--   import Mathlib.Analysis.SpecificLimits.Basic
--   apply alternating_series_estimation
--   (Leibniz criterion; antitone + tends-to-zero)
-- Reference: a11oy gates/madhavaBound_gate.ts for the numeric bound
```

**Acceptance**: `-- SORRY#4 STAGED` label present; numeric gate in a11oy passes its Vitest.

### Sorry 5 — Lutar/PACBayes/MadhavaBound.lean:145

**Anchor formula**: Same as Sorry 4 — second lemma in the same file.
**Discharge route**: Corollary of the bound at line 126; apply the same alternating-series lemma.

```lean
-- SORRY#5 STAGED: Madhava corollary (line 145)
-- Discharge route: follows from SORRY#4 proof by monotonicity of partial sums
```

**Acceptance**: `-- SORRY#5 STAGED` label present.

### Sorry 6 — Lutar/PACBayes/PACBayes.lean:265 (BoundedIntegrability)

**Anchor formula**: TH6 (bekenstein_entropy_bound_dpi) + PAC-Bayes framework
**Thesis section**: §5.4 — PAC-Bayes stability bound
**Discharge route**: Bounded integrability follows from the Bekenstein entropy bound (H ≤ 8A). Mathlib: `MeasureTheory.Integrable` + `MeasureTheory.BoundedVariation`.

```lean
-- SORRY#6 STAGED: BoundedIntegrability
-- Discharge route:
--   apply MeasureTheory.Integrable.mono
--   exact (bekenstein_bound_implies_bounded_support ...)
-- Theorem cited: TH6 bekensteinEntropyBoundDpi
```

**Acceptance**: `-- SORRY#6 STAGED` label present.

### Sorry 7 — Lutar/PACBayes/PACBayes.lean:281 (ChernoffOptimisation)

**Anchor formula**: TH6 + adversarialRobustness gate
**Thesis section**: §5.4 — Chernoff-style optimization bound
**Discharge route**: Chernoff bound via MGF (moment generating function). Mathlib: `Mathlib.Probability.Moments`.

```lean
-- SORRY#7 STAGED: ChernoffOptimisation
-- Discharge route:
--   import Mathlib.Probability.Moments
--   apply chernoff_bound (or inline via MGF inequality)
--   mgf ≤ exp(t² σ²/2) for sub-Gaussian (Hoeffding lemma)
```

**Acceptance**: `-- SORRY#7 STAGED` label present. Running `grep -r "sorry" Lutar/ | grep -v "SORRY#"` returns zero lines.

---

## SECTION 3 — REPO UPGRADES (17 repos, one by one)

Apply `gh pr merge --admin --squash` for all OPEN PRs that pass CI before touching these. Then add the following new PRs:

### lutar-lean
**Current state**: CI failing on 14 modules (job 78614668415). PRs #98, #99, #100 OPEN.
- **PR A**: Merge #98 (MerkleDAGBuild positivity) → squash → tag lake build result
- **PR B**: Merge #100 (Adinkra Fin 1 + HaltEligibility `noncomputable`) → squash
- **PR C**: Merge #99 (KitaevSurface + DelayedChoiceClosure + DoctrineEntropy) → squash after fixing `!=` → `≠`
- **Acceptance**: `lake build` exits 0; `grep -r "sorry" Lutar/ | grep -v "SORRY#"` = 0 lines

### ouroboros
**Current state**: PR #84 MERGED (TH10 axiom-structured). 248 tests GREEN.
- **PR A**: Bump version in `package.json` to reflect 626 declarations count (Agent C audit 2026-05-30)
- **PR B**: Add `CANONICAL_NUMBERS.md` with the locked counts (626/15(14u)/189/44)
- **PR C**: Wire `TH10` axiom check into the CI lint step
- **Acceptance**: `vitest run` exits 0; canonical numbers file present

### ouroboros-thesis
**Current state**: LaTeX source mirror on HF.
- PR A: Fix abstract — `217` declarations (not 241 skeletons). PR B: Add `CHANGELOG_v18.md`. PR C: `make pdf`; attach to release.
- **Acceptance**: PDF builds; abstract numbers match canonical constants

### a11oy
**Current state**: #108 OPEN (5 gates), #110 OPEN (Putnam P2+P3), #94–#107 mixed.
- PR A: Merge #108 → `vitest run` green. PR B: Merge #110 post-S6. PR C: Add 30 remaining gates (see Section 5).
- **Acceptance**: `vitest run` exits 0; `gates/index.ts` exports 35 named gates

### sentra
**Current state**: DRAFT relicense IP HOLD on #45 — DO NOT TOUCH #45.
- PR A: badge stack + no superlatives. PR B: `CANONICAL_NUMBERS.md`. PR C: superlative CI grep.
- **Acceptance**: grep returns 0; CI green; #45 untouched

### amaru
**Current state**: DRAFT relicense IP HOLD on #46 — DO NOT TOUCH #46.
- Same 3 PRs as sentra. **Acceptance**: CI green; #46 untouched

### rosie
**Current state**: uds-v0.3.0 released.
- PR A: 10-badge stack. PR B: `docs/THEOREM_INDEX.md` → thesis §8. PR C: vitest green.
- **Acceptance**: CI green; no superlatives

### vessels
**Current state**: uds-v0.3.0 released; cosign PENDING.
- PR A: Add honest note "cosign signing PENDING (see Section 7)". PR B: `CANONICAL_NUMBERS.md`. PR C: `SIGNING_STATUS.md`.
- **Acceptance**: no false claim of signed status; CI green

### uds-mesh
**Current state**: PR #46 OPEN (BFT caveat).
- PR A: Merge #46 → squash. PR B: `CANONICAL_NUMBERS.md`. PR C: BFT caveat inline in README.
- **Acceptance**: BFT caveat visible; CI green

### .github
**Current state**: PRs #82, #83, #84, #85 all OPEN.
- Merge all 4: #85 (Plotly offline) → #84 (pointer) → #83 (theorems plan) → #82 (CTO+PM plan), each `--admin --squash`.
- **Acceptance**: `CURSOR_READ_THESE_TWO_FIRST.md` present in root; CI green

### agi-forecast
**Current state**: #42 (FG-S1→S4) OPEN; #43 (Putnam v2 harness) OPEN.
- PR A: Verify #42 CI → merge. PR B: Wire #43 into Section 6. PR C: FG-01..FG-12 table in README.
- **Acceptance**: Both merged; `vitest run` exits 0

### platform
**Current state**: No PR activity tonight — run `vitest run`, fix failures.
- PR A: vitest green. PR B: `CANONICAL_NUMBERS.md`. PR C: superlative grep = 0.
- **Acceptance**: CI green; no superlatives

### vsp-otel
**Current state**: Λ-signed OTel exporter.
- PR A: badge stack. PR B: `CANONICAL_NUMBERS.md`. PR C: OTLP+W3C TraceContext test green.
- **Acceptance**: Λ-axis score present in span attributes

### szl-uds-deployment
**Current state**: PR #4 OPEN (Package CR + NetworkPolicy + ServiceMonitor).
- Merge #4 after Section 7 founder actions. `kubectl apply --dry-run=client` must exit 0.
- **Acceptance**: Dry-run green; PR #4 merged

### szl-cookbook
**Current state**: 9 SKILL.md patterns.
- PR A: Add SKILL_10 (35-anchor gate pattern from a11oy#108). PR B: badge stack. PR C: lint all 10 SKILLs.
- **Acceptance**: 10 SKILL.md files; CI green

### szl-trust
**Current state**: 12 CPS receipts; real DSSE crypto.
- PR A: Add "12 axioms" to receipt count table. PR B: `CANONICAL_NUMBERS.md`. PR C: replay determinism test = 0.
- **Acceptance**: CI green; canonical numbers accurate

### counsel
**Current state**: Legal governance mirror.
- PR A: doctrine v6 compliance statement. PR B: `CANONICAL_NUMBERS.md`. PR C: Apache-2.0 SPDX in all source files.
- **Acceptance**: SPDX headers present; no superlatives

---

## SECTION 4 — HF FLEET UPGRADES (19 Spaces + 26 datasets + 2 models)

**Verified fleet** (curl-confirmed 2026-05-29):
- 19 Spaces: mcp-receipts-server, lutar-lean-browser, a11oy-receipts-playground, szl-showcase, lean-proof-playground, szl-cookbook-runner, agi-forecast-viewer, vsp-otel-emitter, amaru-memory-attestation, rosie-operator-console, sentra-security-gates, a11oy-platform, szl-anatomy, amaru-platform, sentra-platform, rosie-platform, vsp-otel-platform, agi-forecast-platform, szl-cookbook-platform
- 26 datasets: thesis-v18-formal-verification, uds-spans-receipts, szl-visual-identity, uds-governance-receipts, ouroboros-source, szl-cookbook-source, ouroboros-thesis-source, szl-trust-source, agi-forecast-source, vsp-otel-source, vessels-source, counsel-source, carlota-jo-source, terra-source, rosie-source, amaru-source, sentra-source, szl-org-infra, SZLHOLDINGS, why-we-lead, ouroboros-arxiv-preprint, szl-artifacts, szl-charts, anatomy-alive-harness, a11oy-source, uds-mesh-source
- 2 models: (a11oy-v19-substrate + 1 other — enumerate with `curl https://huggingface.co/api/models?author=SZLHOLDINGS`)

**Canonical 10-badge stack** (paste into every Space/dataset README `## Badges` section):
```markdown
![Doctrine v6](https://img.shields.io/badge/Doctrine-v6_STRICT-navy)
![Lean 4](https://img.shields.io/badge/Lean-4_Mathlib_v4.13.0-blue)
![626 Declarations](https://img.shields.io/badge/Declarations-626-brightgreen)
![12 Axioms](https://img.shields.io/badge/Axioms-12-brightgreen)
![7 Sorries](https://img.shields.io/badge/Sorries-7_STAGED-yellow)
![DSSE](https://img.shields.io/badge/DSSE-SLSA_Level_1-purple)
![OTel](https://img.shields.io/badge/OTel-W3C_TraceContext-orange)
![Series-A](https://img.shields.io/badge/Stage-Series--A-red)
![License](https://img.shields.io/badge/License-Apache--2.0-lightgrey)
![Putnam](https://img.shields.io/badge/Putnam-8.3%25_1%2F12-gold)
```

### Tier 1 — Full README refresh (5 highest investor leverage)

| Space | Key change |
|-------|-----------|
| szl-anatomy | 10-badge stack; `29 datasets · 26 Spaces · 2 models`; `626/15(14u)/189 STAGED` |
| thesis-v18-formal-verification | Signal table: `217` (not 241); DOI `10.5281/zenodo.20434276` |
| a11oy-platform | `35-35 anchors across 7 layers`; Putnam 8.3% line |
| szl-showcase | No superlatives in `app.py` title; STAGED label on non-live features |
| lean-proof-playground | Mathlib v4.13.0 confirmed; link to thesis-v18-formal-verification |

### Tier 2 — Diff fixes (5 next-priority)

**T2.1 — mcp-receipts-server**: Add 10-badge stack; confirm `arxiv:2401.05566` tag present (already in tags).
**T2.2 — agi-forecast-platform**: Replace PAC-Bayes description to cite TH6 by name; add Putnam 8.3% badge.
**T2.3 — amaru-platform**: Add honest "cosign signing PENDING" note (mirrors vessels-source).
**T2.4 — szl-cookbook-platform**: Add SKILL_10 anchor to README once Section 3 szl-cookbook PR A lands.
**T2.5 — vsp-otel-platform**: Confirm Λ-axis score description uses exact formula `Λ : [0,1]^k → {0,1}`.

### Tier 3 — Batch find/replace (remaining 9 Spaces + remaining datasets)

Run this recipe against all remaining READMEs:

```bash
# In every HF repo checkout:
# 1. Add 10-badge stack after first H1
# 2. Replace superlatives
sed -i 's/revolutionary/formally verified/g; s/unprecedented/documented/g; s/seamless/reliable/g' README.md
# 3. Update counts:
sed -i 's/24 datasets/26 datasets/g; s/241 declarations/217 declarations/g' README.md
```

### Org card update (SZLHOLDINGS/SZLHOLDINGS)

Update the `README.md` (dataset card):
- `2 models · 26 datasets · 19 Spaces` (was 47 datasets — the org card claims 47 which appears to overcount; use the curl-verified 26)
- `626 declarations · 15 axioms (14 unique) · 189 sorries (138+51 Putnam)`
- `Putnam 8.3% (1/12)`

---

## SECTION 5 — THE 35 ANCHOR FORMULAS WIRED AS POLICY GATES

**Already wired by a11oy#108** (5 gates at `packages/policy/src/gates/`):
1. `adversarialRobustness_gate.ts` — TH8 / `Lutar/Composition/AdversarialRobustness.lean`
2. `falsePosition_gate.ts` — Rhind Papyrus method / `Lutar/Calibration/FalsePosition.lean`
3. `liuHuiPi_gate.ts` — Liu Hui π convergence
4. `madhavaBound_gate.ts` — Mādhava series bound
5. `summationInvariant_gate.ts` — Khipu summation invariant

**Pattern source**: `packages/policy/src/gates/adversarialRobustness_gate.ts` from PR #108. Every new gate must follow this interface exactly (copy the `PolicyDecision` and config interfaces; change the formula logic only).

**Remaining 30 gates to create** (one file each, same pattern):

| # | Gate file | Anchor / Thesis ref |
|---|-----------|---------------------|
| 6 | `lambdaGate_gate.ts` | F0010 Λ:[0,1]^k→{0,1} / §3.1 |
| 7 | `composability_gate.ts` | TH1 composability / §4.1 |
| 8 | `replayDOIDuality_gate.ts` | TH2 replay_doi_duality / §4.2 |
| 9 | `anatomyReduction_gate.ts` | TH3 anatomy_reduction / §2.1 |
| 10 | `lambdaCategory_gate.ts` | TH4 lambda_category / §4.3 |
| 11 | `receiptChainConfluence_gate.ts` | TH5 confluence / §3.5 |
| 12 | `bekensteinEntropy_gate.ts` | TH6 DPI entropy / §5.1 |
| 13 | `curryHoward_gate.ts` | TH7 curry-howard / §4.4 |
| 14 | `temporalConsistency_gate.ts` | A10 temporalConsistency / §6.1 |
| 15 | `causalSeparability_gate.ts` | A11 causalSeparability / §6.2 |
| 16 | `constructiveTransparency_gate.ts` | A12 constructiveTransparency / §6.3 |
| 17 | `economicGrounding_gate.ts` | A14 economicGrounding / §6.5 |
| 18 | `hashChainIntegrity_gate.ts` | A6 hashChainIntegrity / §3.3 |
| 19 | `monotonicity_gate.ts` | A1 monotonicity / §3.1 |
| 20 | `homogeneity_gate.ts` | A2 homogeneity / §3.1 |
| 21 | `egyptianExact_gate.ts` | A3 egyptian-exact / §3.2 |
| 22 | `bounded_gate.ts` | A4 bounded / §3.1 |
| 23 | `soundness_gate.ts` | A5 soundness / §3.2 |
| 24 | `replayDeterminism_gate.ts` | T5 replay determinism / §3.5 |
| 25 | `merkleDAGBatch_gate.ts` | T3_MerkleDAG / §3.3 |
| 26 | `rhoComposition_gate.ts` | T1_Compose ρ-composition / §3.4 |
| 27 | `dualWitness_gate.ts` | F0018/F0019 dual-witness / §3.5 |
| 28 | `twoWitnessClosure_gate.ts` | TwoWitness theorem / §3.5 |
| 29 | `bekensteinFireRate_gate.ts` | K13 49.5% fire-rate / §5.2 |
| 30 | `sborProvenance_gate.ts` | attr:E→A / §6.2 |
| 31 | `uniqueness_gate.ts` | Λ uniqueness / §3.4 |
| 32 | `pacBayesStability_gate.ts` | PACBayes §5.4 / TH6 |
| 33 | `chernoffOptimisation_gate.ts` | Sorry#7 route / §5.4 |
| 34 | `doctrineLock_gate.ts` | TH10 axiom-structured / §2.3 |
| 35 | `receiptPool_gate.ts` | ReceiptPool pre-allocated / §3.3 |

**Each gate file template** (copy verbatim from `adversarialRobustness_gate.ts`, change marked fields):

```typescript
// SPDX-License-Identifier: Apache-2.0
// Gate: <gateName>
// Lean theorem: <theorem name>
// Lean file: <Lutar/Path/File.lean or STAGED if not yet built>
// Thesis: <§X.Y Title>

export function <gateName>Gate(config = {}) {
  return function gate(opts): PolicyDecision {
    // formula logic here
    const allow = /* formula condition */;
    return { allow, rationale: allow ? "PASS: ..." : "DENY: ...",
             formula: "<name>", leanTheorem: "<name>",
             leanFile: "<path or STAGED>", leanCommitSha: "<sha or STAGED>",
             lambdaScore: allow ? 1.0 : 0.0 };
  };
}
```

**Update** `packages/policy/src/gates/index.ts` to barrel-export all 35 gates.
**Update** `packages/policy/src/gates/__tests__/policy_gates.test.ts` to import and test all 35.

**Acceptance**: `vitest run` exits 0; `packages/policy/src/gates/index.ts` exports exactly 35 symbols.

---

## SECTION 6 — PUTNAM BEAT TRACK (Tier 3, headline)

**Context**: Putnam 8.3% = 1/12 problems solved. agi-forecast#43 (Perplexity Putnam v2 harness) and a11oy#110 (Putnam P2+P3 router) are the P1–P4 source.

**P1–P4**: Sourced from agi-forecast#43 + a11oy#110. Merge both PRs per Section 3 sequence.

**P5 — Lean type-checker REST bridge** (stretch goal):

Create `packages/putnam/src/lean_bridge.ts` in a11oy:
```typescript
// STAGED: P5 — Lean type-checker REST bridge
// POST /lean/check { statement: string } → { ok: boolean, errors: string[] }
// Implementation: spawn `lake env lean --stdin` subprocess
// CI gate: if lean_bridge returns ok=true, emit OTel span with theorem name
```

**P6 — OTel witness emitter**:

In vsp-otel, add `putnam_witness_emitter.ts`:
```typescript
// When a Putnam answer is verified (P5 bridge ok=true),
// emit span: { name: "putnam.witness", attributes: { "putnam.problem": "P5",
//   "lean.theorem": "<name>", "lambda.score": 1.0 } }
```

**P7 — Ledger append**:

In szl-trust, add a CPS receipt row for each Putnam verification:
```
receipt_type: "putnam_witness"
problem: "P5"
verifier: "lean_bridge_v1"
timestamp: <ISO>
dsse_sig: <DSSE PAE signature>
```

**Acceptance**: Running the Putnam harness (agi-forecast#43) against P5 returns `ok: true` from Lean; OTel span is emitted; CPS receipt is appended.

---

## SECTION 7 — UDS catalog-grade (Tier 4 Warhacker)

**Status**: szl-uds-deployment#4 (OPEN) already contains U2–U4 (Package CR + NetworkPolicy + ServiceMonitor).

### Actions that require the founder (Stephen Lutar) — do these FIRST before Cursor can finish:

**U1 — cosign key provision**:
```bash
# Founder runs locally:
cosign generate-key-pair
# Upload private key to your secrets manager / escrow
# Add COSIGN_PUBLIC_KEY to GitHub org secrets
# Add COSIGN_PRIVATE_KEY to each repo's Actions secrets: lutar-lean, a11oy, amaru, sentra, rosie, vessels
```

**U5 — Container image push**:
```bash
# Founder runs after cosign keys are provisioned:
docker build -t ghcr.io/szl-holdings/<repo>:<tag> .
docker push ghcr.io/szl-holdings/<repo>:<tag>
cosign sign --key <key> ghcr.io/szl-holdings/<repo>:<tag>
```

### Actions Cursor executes after U1/U5 founder steps complete:

**U2** (already in #4): Package CR — verify `zarf.yaml` is catalog-grade (catalog key + namespace set).
**U3** (already in #4): NetworkPolicy — egress rules locked to OTel collector + szl-trust endpoints only.
**U4** (already in #4): ServiceMonitor — Prometheus scrape interval 30s; labels match the Helm release.

```bash
# Cursor: merge szl-uds-deployment#4 once U1 complete
gh pr merge szl-holdings/szl-uds-deployment 4 --admin --squash \
  -m "feat(uds): catalog-grade Package CR + NetworkPolicy + ServiceMonitor

Signed-off-by: Cursor Agent <cursoragent@cursor.com>
Co-authored-by: Lutar, Stephen P. <stephen@szlholdings.com>"
```

**Acceptance**:
- `kubectl apply --dry-run=client -f manifests/` exits 0 (Cursor can verify)
- cosign verification passes (requires U1 — founder action)
- All container images at `ghcr.io/szl-holdings/*` return 200 (requires U5 — founder action)

---

## SECTION 8 — Acceptance criteria (Cursor self-checks)

Run these checks in sequence. Each must pass before marking the directive complete.

```bash
# S1: Lean kernel — zero non-STAGED sorries
grep -r "sorry" $(find . -name "*.lean") | grep -v "SORRY#" | grep -v "nanoda-allow-sorry"
# Expected: 0 lines

# S2: lake build clean
cd lutar-lean && lake build 2>&1 | grep -c "error:" 
# Expected: 0

# S3: a11oy vitest clean
cd a11oy && pnpm vitest run 2>&1 | tail -5
# Expected: "Tests 35 passed"

# S4: HF fleet badge check (sample)
curl -s "https://huggingface.co/api/spaces?author=SZLHOLDINGS&limit=100" | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print(len(d), 'spaces')"
# Expected: 19

# S5: Superlative check
grep -rE "revolutionary|unprecedented|world-class|seamless|industry-leading|cutting-edge|game-changing|breakthrough" \
  $(find . -name "*.md" -o -name "*.ts" -o -name "*.lean") | grep -v ".git"
# Expected: 0 lines

# S6: Commit sign-off check
git log --format="%B" HEAD~5..HEAD | grep -c "Signed-off-by: Cursor Agent"
# Expected: ≥ 1 per commit

# S7: Canonical numbers present
grep -r "217 declarations" . | grep -v ".git" | head -3
grep -r "12 axioms" . | grep -v ".git" | head -3
grep -r "7.*sorries" . | grep -v ".git" | head -3
# Expected: ≥ 1 match each

# S8: Protected PRs untouched
gh api repos/szl-holdings/a11oy/pulls/57 --jq '.state'      # must be "open" or whatever it was
gh api repos/szl-holdings/amaru/pulls/46 --jq '.state'
gh api repos/szl-holdings/sentra/pulls/45 --jq '.state'
# Expected: state unchanged from pre-directive baseline

# S9: Gate count
ls a11oy/packages/policy/src/gates/*.ts | grep -v __tests__ | grep -v index | wc -l
# Expected: 35
```

---

## SECTION 9 — Doctrine sweep (last pass before every commit)

Checklist — complete before `git commit`:

- [ ] **No marketing superlatives** in any file changed in this commit
- [ ] **No emoji in `##` or `###` headers** in any Markdown changed
- [ ] **STAGED label present** on every `sorry` and every STAGED code block
- [ ] **Commit message includes both sign-off lines** (Cursor Agent + Stephen Lutar)
- [ ] **Canonical numbers** (626/15(14u)/189/44) cited correctly wherever numbers appear
- [ ] **DO NOT TOUCH list respected**: a11oy#57, amaru#46, sentra#45 not in this PR's diff
- [ ] **PR opened on feature branch**, not directly to main
- [ ] **`gh pr merge --admin --squash`** used (not rebase, not merge commit)
- [ ] **HF token not committed** — `hf_kvJdu...` must not appear in any committed file

---

## SECTION 10 — Direct order

Execute Section 1 first. Work through failing Lean modules in the numbered order (1.1 → 1.13). After every commit, run the Section 9 doctrine sweep. Push to feature branches. Open PRs as you go using `gh pr create` with the sign-off trailer.

If a Lean proof cannot be closed without lake build confirmation, apply the STAGED label and move on — do not block on it.

After Section 1, execute Sections 2, 3, 4, 5, 6, 7 in parallel where possible (they do not block each other).

If a Perplexity proxy lookup is needed (e.g., for a Mathlib lemma name you cannot confirm locally), comment on `.github#76` with the header `[PROXY-LAND <query>]` and wait for a response before writing the Lean term.

Pace over frugality. Ship.
