# CURSOR INSTILLATION OPERATIONAL PLAN
## SZL Holdings — Theorems + Formulas Zoom-Out

**Date:** 2026-05-30  
**Prepared by:** Theorems+Formulas Zoom-Out subagent (Perplexity Computer)  
**Doctrine:** v6 — no hallucinations, no bandaids, Series-A discipline  
**DO NOT AUTO-MERGE any PR in this plan**  
**Forbidden:** DO NOT touch a11oy#57, amaru#46, sentra#45 (DRAFT relicense HOLD)  
**Forbidden:** DO NOT toggle branch protection  
**Commits:** All commits must include `-s` (DCO sign-off: `Signed-off-by: Cursor AI <cursor@szlholdings.com>`)

---

## How to Use This Plan

Each gap below is a self-contained unit of work. Cursor reads this file on each loop and picks the next gap to close. Work top-to-bottom. All PRs open as `NOT auto-merge`. Perplexity Computer reviews.

For each gap:
1. Create branch from organ's `main`
2. Add the runtime file and test file listed
3. Verify: `pnpm test` (TS) or `pytest` (Python) green locally
4. Open PR with title in the format shown
5. Add `szl.formula.*` attributes / receipt fields / gate decisions exactly as specified

---

## TIER 1 — Highest Ecosystem Leverage

### GAP-01: Anchor Formulas → amaru (Phase 1 Track 2b)

**Gap**: 5 anchor formulas (liu_hui_pi, madhava_bound, false_position, summation_invariant, adversarial_robustness) have zero wiring in amaru  
**Organ owner**: `szl-holdings/amaru`  
**Lean theorem refs**:
- `Lutar.Banach.LiuHuiPi.sideSquared_bounds` (LiuHuiPi.lean:56)
- `Lutar.PACBayes.MadhavaBound.madhavaRemainderBound_nonneg` (MadhavaBound.lean:49)
- `Lutar.Calibration.FalsePosition.false_position_correct` (FalsePosition.lean:44)
- `Lutar.Khipu.SummationInvariant.khipuReceipt_checksum_invariant` (SummationInvariant.lean:217)
- `Lutar.Composition.AdversarialRobustness.robustness_preserved_by_composition` (AdversarialRobustness.lean:88)

**Runtime implementation files**:
- `src/formulas/anchorFormulas.ts` — import from ouroboros `@szl-holdings/formulas` package; re-export with amaru-specific typed witnesses
- `src/formulas/anchorFormulaWitness.ts` — `FormulaWitness` type per formula; `emitAnchorWitness(formulaId, inputs, output)` → DSSE envelope
- `src/scheduler/formulaCheckpoint.ts` — integrate formula witnesses at RUWAY (chakra 5) and HATUN (chakra 7) checkpoints

**Test file**: `src/formulas/__tests__/anchorFormulas.test.ts`  
Test assertions:
- Each formula emits a `FormulaWitness` with `lean_theorem_ref`, `lean_commit_sha`, `lambda_score`
- `madhava_bound` witness has `remainder_bound ≤ 0.01` at default N=10
- `adversarial_robustness` witness has `epsilon2 = lipschitz1 * lipschitz2 * delta`
- DSSE PAE v1 signature verifies on each witness

**Receipt schema field** (add to amaru DSSE receipt):
```json
{
  "formula_witnesses": [
    {
      "formula_id": "madhava_bound",
      "lean_theorem_ref": "Lutar.PACBayes.MadhavaBound.madhavaRemainderBound_nonneg",
      "lean_commit_sha": "c4d13795689601324fce0236351bfe0ade990a43",
      "lambda_score": 0.9524,
      "timestamp": "..."
    }
  ]
}
```

**Branch name**: `cursor/perplexity-instill-anchor-formulas-amaru`  
**PR title**: `feat(formulas): instill 5 anchor SZL formulas — amaru L2+L5 wiring`  
**Acceptance test**: `pnpm test:anatomy-alive` L2 row for amaru shows PASS with formula_witnesses populated  
**Estimated hours**: 16h

---

### GAP-02: Anchor Formulas → rosie (Phase 1 Track 2c)

**Gap**: 5 anchor formulas have zero formula gate wiring in rosie  
**Organ owner**: `szl-holdings/rosie`  
**Lean theorem refs**: same as GAP-01

**Runtime implementation files**:
- `src/formulas/anchorReplay.ts` — receipt replay with formula witness verification; `replayFormulaWitness(receipt)` → `{verified: boolean, formulaId, lambdaScore}`
- `src/formulas/formulaPanel.ts` — exports `formulaPanelData()` for the operator console formula tab

**Test file**: `src/formulas/__tests__/anchorReplay.test.ts`  
Test assertions:
- Replay of a valid `madhava_bound` witness succeeds
- Tampered witness (wrong `lambda_score`) fails replay
- All 5 anchor formulas covered in replay tests

**Receipt schema**: rosie replay record adds `formula_witness_verified: true|false` field  

**Branch name**: `cursor/perplexity-instill-anchor-formulas-rosie`  
**PR title**: `feat(formulas): instill 5 anchor SZL formulas — rosie L2+L5 receipt replay`  
**Acceptance test**: rosie operator console "Live Formulas" tab shows formula replay status for all 5 anchors  
**Estimated hours**: 16h

---

### GAP-03: QEC Lineage → vsp-otel + uds-mesh (L4 + L5)

**Gap**: QEC theorems (Hamming, Shor, CSS, Kitaev) exist in Lean with 0 sorry, 0 axiom but have no L4 OTel span attributes and no L5 DSSE receipt field  
**Organ owners**: `szl-holdings/vsp-otel` (L4), `szl-holdings/uds-mesh` (L5)  
**Lean theorem refs**:
- `Lutar.QEC.HammingFoundations.hamming_dist_self` (HammingFoundations.lean:49)
- `Lutar.QEC.ShorReceiptCode.shor_single_fault_corrects` (ShorReceiptCode.lean:76)
- `Lutar.QEC.CSSBridge.css_bridge_consistent` (CSSBridge.lean:56)
- `Lutar.QEC.KitaevSurface.kitaev_single_site_flips_parity_n` (KitaevSurface.lean:65)

**vsp-otel implementation file**: `runtime/src/formulas/qecLineage.ts`
```typescript
export interface QECLineageDescriptor {
  hamming_distance: number;           // computed Hamming distance of receipt pair
  shor_fault_correctable: boolean;    // single-fault correction result
  css_bridge_consistent: boolean;     // CSS bridge consistency check
  kitaev_parity_zero: boolean;        // Kitaev parity syndrome result
  lean_commit_sha: string;
}

export function qecLineageSpan(opts: QECLineageOptions): {span: OtelSpan, descriptor: QECLineageDescriptor}
```

OTel attributes: `szl.qec.hamming_distance`, `szl.qec.shor_fault_correctable`, `szl.qec.css_bridge_consistent`, `szl.qec.kitaev_parity_zero`, `szl.qec.lean_commit_sha`

**uds-mesh implementation file**: add `qec_witness` field to `formula_receipts.py`
```python
QEC_WITNESS_SCHEMA = {
    "formula": "qec_lineage",
    "hamming_distance": int,
    "shor_fault_correctable": bool,
    "css_bridge_consistent": bool,
    "kitaev_parity_zero": bool,
    "lean_theorems": ["Lutar.QEC.HammingFoundations.hamming_dist_self", ...],
    "lean_commit_sha": str,
    "timestamp": str,
    "signature": str
}
```

**Test files**: `runtime/src/formulas/__tests__/qecLineage.test.ts` (15 tests); `tests/test_qec_receipts.py` (20 pytest tests)  
**Branch names**: 
- `cursor/perplexity-instill-qec-lineage-vsp-otel`
- `cursor/perplexity-instill-qec-lineage-uds-mesh`
**PR titles**:
- `feat(formulas): instill QEC lineage — L4 vsp-otel OTel spans`
- `feat(formulas): instill QEC lineage — L5 uds-mesh DSSE receipts`
**Estimated hours**: 8h total

---

### GAP-04: Wheeler Delayed-Choice → vsp-otel + uds-mesh + a11oy (L4 + L5 + L6)

**Gap**: Wheeler closure theorems (7 proven, 0 sorry, 0 axiom) have no L4/L5/L6 wiring  
**Organ owners**: vsp-otel, uds-mesh, a11oy  
**Lean theorem refs**:
- `Lutar.Wheeler.DelayedChoiceClosure.delayed_choice_idempotent` (DelayedChoiceClosure.lean:101)
- `Lutar.Wheeler.DelayedChoiceClosure.wheeler_window_safety` (DelayedChoiceClosure.lean:111)
- `Lutar.Wheeler.DelayedChoiceClosure.early_receipt_rejected` (DelayedChoiceClosure.lean:144)

**vsp-otel implementation**: `runtime/src/formulas/wheelerClosure.ts`  
OTel attributes: `szl.wheeler.window_ticks` (default 1000), `szl.wheeler.offset_within_window`, `szl.wheeler.admit_decision`

**uds-mesh implementation**: add `wheeler_witness` to DSSE receipt:
```json
{"formula": "wheeler_closure", "window_ticks": 1000, "offset": 42, "admit": true, "lean_theorem_ref": "Lutar.Wheeler.DelayedChoiceClosure.wheeler_window_safety"}
```

**a11oy implementation**: `packages/policy/src/gates/wheelerClosure_gate.ts`  
Gate: allow when `offset ∈ [0, W)` where W = window_ticks; cite `wheeler_window_safety`

**Branch name**: `cursor/perplexity-instill-wheeler-closure-l4-l5-l6`  
**Acceptance test**: vsp-otel emits `szl.wheeler.admit_decision=true` on valid span; a11oy gate rejects `offset > W`  
**Estimated hours**: 12h

---

### GAP-05: Shannon Doctrine Code → vsp-otel + a11oy (L4 + L6)

**Gap**: Shannon doctrine theorems (7 proven, 0 sorry, 0 axiom) have no L4/L6 wiring  
**Organ owners**: vsp-otel, a11oy  
**Lean theorem refs**:
- `Lutar.Shannon.DoctrineEntropy.doctrine_alphabet_size_4` (DoctrineEntropy.lean:68)
- `Lutar.Shannon.DoctrineEntropy.kraft_inequality_doctrine` (DoctrineEntropy.lean:122)
- `Lutar.Shannon.DoctrineEntropy.channel_rate_bound` (DoctrineEntropy.lean:154)

**vsp-otel implementation**: `runtime/src/formulas/shannonDoctrine.ts`  
OTel attributes: `szl.shannon.doctrine_label` (one of Bot/L1/L2/Top), `szl.shannon.codeword` (2-bit code), `szl.shannon.kraft_sum` (always 1), `szl.shannon.channel_rate_bound`

**a11oy implementation**: `packages/policy/src/gates/shannonDoctrine_gate.ts`  
Gate: allow when codeword ∈ {00, 01, 10, 11} and kraft_sum = 1; cite `kraft_inequality_doctrine`

**Branch name**: `cursor/perplexity-instill-shannon-doctrine-l4-l6`  
**Acceptance test**: a11oy gate rejects unknown doctrine codeword; vsp-otel span has `szl.shannon.kraft_sum=1`  
**Estimated hours**: 8h

---

### GAP-06: DPI/TH6 → uds-mesh + a11oy (L5 + L6)

**Gap**: `dpi_receipt_chain_entropy_bound` proven but not used in any receipt factory or gate  
**Organ owners**: uds-mesh, a11oy  
**Lean theorem refs**:
- `Lutar.DPI.TH6_DPI_Soundness.dpi_receipt_chain_entropy_bound` (TH6_DPI_Soundness.lean:103)
- `Lutar.DPI.DPIBound.dpi_bound_positive` (DPIBound.lean:95)
- `Lutar.DPI.DPIBound.dpi_bound_monotone` (DPIBound.lean:106)

**uds-mesh implementation**: add to `formula_receipts.py`:
```python
def build_dpi_receipt(chain_length: int, receipt_entropy: float) -> dict:
    """DPI bound: H(f(R)) <= H(R). Cite: Lutar.DPI.TH6_DPI_Soundness.dpi_receipt_chain_entropy_bound"""
    bound = receipt_entropy  # DPI: output entropy cannot exceed input
    return {
        "formula": "dpi_bound",
        "chain_length": chain_length,
        "receipt_entropy": receipt_entropy,
        "bound": bound,
        "lean_theorem_ref": "Lutar.DPI.TH6_DPI_Soundness.dpi_receipt_chain_entropy_bound",
        "lean_commit_sha": LUTAR_LEAN_HEAD_SHA,
        ...
    }
```

**a11oy implementation**: `packages/policy/src/gates/dpiAdmit_gate.ts`  
Gate: allow when `entropy_bound > 0` (cite `dpi_bound_positive`) and chain passes monotonicity check

**Branch name**: `cursor/perplexity-instill-dpi-th6-l5-l6`  
**Estimated hours**: 8h

---

### GAP-07: Graph Λ → agi-forecast (Production Build FG-S1→S4)

**Gap**: `Λ_graph_automorphism_invariant` and related graph theorems proven but agi-forecast uses no Lean-cited formula  
**Organ owner**: `szl-holdings/agi-forecast`  
**Lean theorem refs**:
- `Lutar.GraphLambda.Λ_graph_automorphism_invariant` (GraphLambda.lean:144)
- `Lutar.GraphLambda.Λ_graph_le_one` (GraphLambda.lean:91)

**Runtime implementation file**: `src/forecasts/graph_lambda_forecast.py`
```python
@dataclass
class GraphLambdaForecast:
    vertex_lambdas: list[float]          # per-vertex Λ scores
    graph_lambda: float                  # geometric mean of vertex Λs
    automorphism_invariant_verified: bool
    lean_theorem_ref: str               # "Lutar.GraphLambda.Λ_graph_automorphism_invariant"
    lean_commit_sha: str
```

**Test file**: `tests/test_graph_lambda_forecast.py` (20 pytest tests)  
Tests: graph Λ ≤ 1; automorphism-invariant check; receipt DSSE verification; synthetic flag

**Branch name**: `cursor/perplexity-instill-graph-lambda-agi-forecast`  
**PR title**: `feat(forecast): instill Graph-Λ theorem — agi-forecast FG-S1 production build`  
**Acceptance test**: `pytest tests/test_graph_lambda_forecast.py` green; forecast receipt has `lean_theorem_ref` field  
**Estimated hours**: 12h

---

### GAP-08: PAC-Bayes → amaru + agi-forecast

**Gap**: PAC-Bayes arithmetic theorems proven; neither amaru nor agi-forecast emits PAC-Bayes bounds in receipts  
**Organ owners**: amaru, agi-forecast  
**Lean theorem refs**:
- `Lutar.PACBayes.pacBayesBound_mono_kl` (PACBayes.lean:102)
- `Lutar.PACBayes.governanceHead_PACBayes_bound` (PACBayes.lean:146)
- `Lutar.PACBayes.hoeffding_mgf_tail_bound` (PACBayes.lean:354)

**amaru implementation**: `src/reasoning/pacBayesQuality.ts`  
Emits `reasoning_quality_bound` field in HATUN (chakra 7) receipt with McAllester bound for reasoning confidence

**agi-forecast implementation**: `src/forecasts/pac_bayes_envelope.py`  
Computes PAC-Bayes slack for each forecast trajectory; emits in forecast receipt

**Branch names**:
- `cursor/perplexity-instill-pac-bayes-amaru`
- `cursor/perplexity-instill-pac-bayes-agi-forecast`
**Estimated hours**: 16h

---

## TIER 2 — Sorry Discharges (Lean-Only Work)

These are Lean-file-only changes in `szl-holdings/lutar-lean`. Each creates a PR on lutar-lean.

### SORRY-01: Discharge `madhava_alt_series_bound` (S3)

**File**: `Lutar/PACBayes/MadhavaBound.lean:110-130`  
**Current**: `sorry` at line 126  
**Proof route**: Mathlib `Real.tendsto_sum_alternating` or manual alternating-series bound using `List.alternating_sum_le`  
**Lean theorem name**: `Lutar.PACBayes.MadhavaBound.madhava_alt_series_bound`  
**Branch**: `cursor/perplexity-discharge-madhava-alt-series-s3`  
**Acceptance**: `lake build` (or `#check madhava_alt_series_bound`) with no sorry in file  
**Estimated hours**: 8h

---

### SORRY-02: Discharge `madhava_arctan_remainder` (S4)

**File**: `Lutar/PACBayes/MadhavaBound.lean:132-150`  
**Current**: `sorry` at line 145  
**Proof route**: `Real.arctan` renamed — use `Real.arctan_eq_pi_div_two_sub_arctan_inv` or the correct Mathlib v4.13 name  
**Branch**: `cursor/perplexity-discharge-madhava-arctan-s4`  
**Estimated hours**: 4h

---

### SORRY-03: Discharge `double_count` KS identity (S5)

**File**: `Lutar/TwoWitness.lean:140-170`  
**Current**: `sorry` at line 163  
**Proof route**: Finite combinatorial identity over Cabello 18/9 structure; `Finset.sum_comm` + integer arithmetic  
**Branch**: `cursor/perplexity-discharge-double-count-ks-s5`  
**Estimated hours**: 6h

---

### SORRY-04: Discharge `lutar_is_geomean` CAUCHY_ND (S6) — HIGHEST PRIORITY

**File**: `Lutar/Uniqueness.lean:117-130`  
**Current**: `sorry -- CAUCHY_ND: Aczel 1966 Thm 5.1` at line 120  
**Proof route**: Mathlib `ContinuousLinearMap.toFun_eq_coe` + `MeasurableEquiv` continuity argument; the continuity of solutions to the multiplicative Cauchy equation on ℝ>0 via A1 (monotonicity implies measurability, which implies continuity, Aczel 1966 §5)  
**Note**: This sorry makes the investor claim "TH10 machine-checked uniqueness" false. Discharge is the single highest-value sorry fix.  
**Branch**: `cursor/perplexity-discharge-cauchy-nd-uniqueness-s6`  
**Estimated hours**: 20h

---

### SORRY-05: Discharge Axiom → Theorem: `r1_invariance` (A9)

**File**: `Lutar/Knot/ReidemeisterConjecture.lean:173`  
**Current**: `axiom r1_invariance` — Λ invariant under axis permutation  
**Proof route**: Λ_k = (∏x_i)^(1/k); product of all x_i is symmetric → permutation-invariant; `Finset.prod_comm` + `Finset.prod_perm`  
**Branch**: `cursor/perplexity-discharge-r1-invariance-axiom-a9`  
**Estimated hours**: 4h

---

### SORRY-06: Discharge Axiom → Theorem: `lambda_schur_concave_n_axis` (A11)

**File**: `Lutar/Lambda/SchurConcave.lean:188`  
**Current**: `axiom lambda_schur_concave_n_axis` — honest-gap axiom, Mathlib4 majorization API incomplete  
**Proof route**: Marshall-Olkin-Arnold (2011) Prop 3.F.2; Mathlib `Majorized.sum_le_sum` or manual proof via AM-GM + Finset induction  
**Branch**: `cursor/perplexity-discharge-schur-concave-n-axis-a11`  
**Estimated hours**: 8h

---

## TIER 3 — Innovation Additions (Phase 4 HIGH-benefit items)

These are NEW formulas that do NOT yet exist in lutar-lean but solve real operational problems.

### INNOV-01: Wasserstein Distance Bound → sentra forecast confidence

**Problem it solves**: sentra's forecast envelope has no metric for distributional distance between predicted and actual governance trajectories  
**Formula**: W₁(P, Q) ≤ √(2 · KL(P‖Q)) (Pinsker-type bound for Wasserstein); or direct W₁ bound via transport theory  
**Lean theorem to add**: `Lutar.Sentra.WassersteinBound.wasserstein_kl_bound`  
**Target module**: `Lutar/Sentra/WassersteinBound.lean` (new file)  
**Runtime target**: `sentra/src/forecasts/wasserstein_envelope.py`  
**Doctrine benefit**: closes the "no metric for forecast drift" finding from PhD audit Lens 3  
**Rating**: HIGH benefit; MEDIUM difficulty (Mathlib has Wasserstein basics); doctrine v6 accepts (operationally necessary)  
**Branch**: `cursor/perplexity-innov-wasserstein-bound-sentra`  
**Estimated hours**: 20h (Lean: 12h + runtime: 8h)

---

### INNOV-02: Hoeffding-Azuma Inequality → agi-forecast multi-judge ensemble

**Problem it solves**: FG-S3 multi-judge ensemble confidence has no formal bound on the spread of judge scores  
**Formula**: For bounded independent random variables X_i ∈ [a_i, b_i]: Pr[|Σ(X_i - E[X_i])| ≥ t] ≤ 2 exp(−2t²/Σ(b_i-a_i)²)  
**Lean theorem to add**: `Lutar.PACBayes.HoeffdingAzuma.hoeffding_bounded_ensemble_bound`  
**Note**: `hoeffding_mgf_tail_bound` already exists in `Lutar/PACBayes.lean:354` — this adds the concentration-inequality form directly applicable to ensemble scoring  
**Runtime target**: `agi-forecast/src/forecasts/ensemble_confidence.py`  
**Doctrine benefit**: FG-S3 multi-judge gets a machine-checked confidence guarantee (not just empirical spread)  
**Rating**: HIGH benefit; LOW difficulty (Hoeffding proof is 4h; MGF bound already in Lean); doctrine v6 accepts  
**Branch**: `cursor/perplexity-innov-hoeffding-azuma-agi-forecast`  
**Estimated hours**: 12h (Lean: 4h + runtime: 8h)

---

### INNOV-03: Galois Connection → a11oy + amaru policy gate composition

**Problem it solves**: a11oy policy gates and amaru reasoning gates compose by conjunction; no formal monotone Galois adjunction proves this is the unique minimum-fixing-point composition  
**Formula**: For a Galois connection (f, g): f(x) ≤ y ↔ x ≤ g(y); policy gate composition P₁ ∧ P₂ is the greatest lower bound in the Galois lattice  
**Lean theorem to add**: `Lutar.Doctrine.GaloisGateComposition.galois_policy_adjunction`  
**Target module**: `Lutar/Doctrine/GaloisGateComposition.lean` (new file)  
**Runtime target**: `a11oy/packages/policy/src/composition/galoisComposition.ts`  
**Doctrine benefit**: gives a11oy's conjunctive AND a category-theoretic foundation (beyond just set-intersection); relevant to the TH1 composition claim  
**Rating**: HIGH benefit; MEDIUM difficulty; doctrine v6 accepts (operationally grounds the gate composition claim)  
**Branch**: `cursor/perplexity-innov-galois-connection-a11oy-amaru`  
**Estimated hours**: 24h (Lean: 16h + runtime: 8h)

---

### INNOV-04: Pinsker's Inequality → uds-mesh receipt divergence bounds

**Problem it solves**: `pinsker` is currently an axiom (`DPOFeasibility.lean:143`); discharging it AND wiring it to uds-mesh receipt comparison closes a real gap  
**Note**: This overlaps with SORRY-05 (DPO context) — but the uds-mesh instillation is a separate deliverable  
**Lean work**: Discharge `axiom pinsker` in `DPOFeasibility.lean` + add `Lutar.Information.Pinsker.pinsker_tv_kl_bound` as a standalone theorem  
**Runtime target**: `uds-mesh/formula_receipts.py` — add `pinsker_divergence_receipt`  
**Doctrine benefit**: closes the receipt-comparison divergence gap; uds-mesh can attest that two receipt chains are within a KL-bounded TV distance  
**Rating**: HIGH benefit; MEDIUM difficulty; doctrine v6 accepts  
**Branch**: `cursor/perplexity-innov-pinsker-uds-mesh`  
**Estimated hours**: 16h (Lean: 8h + runtime: 8h)

---

### INNOV-05: Lyapunov Stability → rosie observability over time

**Problem it solves**: rosie's ban-word scanner and doctrine label over time has no formal stability guarantee — does the system drift?  
**Formula**: V(x) ≥ 0, V(0) = 0, dV/dt ≤ 0 → system is Lyapunov-stable; applied to governance score sequence Λ_t  
**Lean theorem to add**: `Lutar.Stability.Lyapunov.lambda_lyapunov_stable`  
**Target module**: `Lutar/Stability/Lyapunov.lean` (new file)  
**Runtime target**: `rosie/src/stability/lyapunov_monitor.ts`  
**Doctrine benefit**: rosie's observability panel gains a stability certificate over time; prevents silent Λ drift  
**Rating**: HIGH benefit; MEDIUM difficulty; doctrine v6 accepts (real operational gate, not decoration)  
**Branch**: `cursor/perplexity-innov-lyapunov-stability-rosie`  
**Estimated hours**: 20h (Lean: 12h + runtime: 8h)

---

## DEFERRED / NOT RECOMMENDED (Phase 4 LOW-benefit)

| Proposal | Reason deferred |
|----------|-----------------|
| Kolmogorov-Sinai entropy bounds | No receipt chain uses mixing-time dynamics; adds mathematical complexity without operational gate |
| Borel-Cantelli lemma | agi-forecast tail risk is better served by Hoeffding-Azuma; Borel-Cantelli is asymptotic, not finite-sample |
| Kelly criterion | agi-forecast resource allocation is not a betting game; Kelly applies to repeated binary gambles, not governance trajectories |
| Bregman divergence | Forecast comparison is better served by Wasserstein (INNOV-01); Bregman adds redundant complexity |
| Hilbert space duality | OTel span compression is an engineering problem, not a Hilbert-space problem; no clear gate |
| Group cohomology | Receipt chain integrity is addressed by DPI+Shor+Kitaev; group cohomology adds theory without new gates |
| Stochastic gradient convergence | No organ currently runs gradient descent at inference time; premature |

---

## Execution Order (Cursor reads top-to-bottom)

1. GAP-01 (amaru anchor formulas) — 16h
2. GAP-02 (rosie anchor formulas) — 16h
3. GAP-03 (QEC OTel + DSSE) — 8h
4. GAP-04 (Wheeler L4+L5+L6) — 12h
5. GAP-05 (Shannon L4+L6) — 8h
6. GAP-06 (DPI/TH6 L5+L6) — 8h
7. GAP-07 (Graph Λ agi-forecast) — 12h
8. GAP-08 (PAC-Bayes amaru + agi-forecast) — 16h
9. SORRY-04 (CAUCHY_ND uniqueness — highest priority sorry) — 20h
10. SORRY-01 (madhava alt series) — 8h
11. SORRY-02 (madhava arctan) — 4h
12. SORRY-03 (double_count KS) — 6h
13. SORRY-05 (r1_invariance axiom→theorem) — 4h
14. SORRY-06 (Schur concave axiom→theorem) — 8h
15. INNOV-01 (Wasserstein + sentra) — 20h
16. INNOV-02 (Hoeffding-Azuma + agi-forecast) — 12h
17. INNOV-03 (Galois connection + a11oy) — 24h
18. INNOV-04 (Pinsker discharge + uds-mesh) — 16h
19. INNOV-05 (Lyapunov + rosie) — 20h

**Total estimated: ~238h (≈6 Cursor-weeks at 40h/week)**

---

## Acceptance Test Reference

| Test command | What it validates |
|-------------|-------------------|
| `pnpm test:anatomy-alive` | Full L1-L7 anatomy harness — all layers PASS |
| `cd amaru && pnpm test` | amaru formula witnesses green |
| `cd rosie && pnpm test` | rosie formula replay green |
| `cd vsp-otel && pnpm test` | vsp-otel QEC+Wheeler+Shannon spans green |
| `cd uds-mesh && pytest` | uds-mesh QEC+Wheeler+DPI+Pinsker receipts green |
| `cd a11oy && pnpm test` | a11oy Wheeler+Shannon+DPI+CrossComponent gates green |
| `cd agi-forecast && pytest` | agi-forecast Graph-Λ+PAC-Bayes+Hoeffding forecasts green |
| `cd lutar-lean && lake build` | 0 new sorry; axiom count ≤ 8 (4 axioms discharged) |
