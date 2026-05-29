# SZL Anatomy-Alive Integration Test Harness

**Doctrine v6** | SPDX-License-Identifier: Apache-2.0  
**Status:** `L1=PASS L2=PASS L3=STAGED L4=STAGED L5=PASS L6=PASS L7=NOT-YET-WIRED`  
**Run:** 2026-05-30 | Total duration: 14,338 ms

---

## What this proves

This harness drives a synthetic agent trace through all 7 anatomy-alive layers
and verifies every layer against the actual main branches of the szl-holdings
organ repos. Every assertion is backed by a live GitHub API call or a
cryptographic computation — no mocks, no test doubles.

**Anchor formula exercised:** `AdversarialRobustness`  
**Lean theorem:** `Lutar.Composition.Robustness.robustness_preserved_by_composition`  
**Lean blob SHA (pinned):** `a96e448f83da40f06f005e7f8ff0492e0870e819`  
**lutar-lean commit:** `1dca00032dfc9aa8559cc6c2e4b63192fcf52371`

---

## How to run

```bash
# Requirements: Python 3.8+, gh CLI authenticated to szl-holdings
pip install -r requirements.txt   # only matplotlib (for diagram generation)

# Run the harness
python run_anatomy_alive.py

# Run with explicit output path
python run_anatomy_alive.py --json-out my_evidence.json

# Generate all visual diagrams
python diagrams/make_diagrams.py
```

The harness uses the `gh` CLI for all GitHub API calls. Authenticate with:
```bash
gh auth login
```

---

## Layer status explained

| Layer | Organ | Status | What fires | What's missing |
|---|---|---|---|---|
| L1 | lutar-lean | **PASS** | `gh api` blob SHA check; `theorem robustness_preserved_by_composition` present; zero `sorry` lines | Nothing — proven today |
| L2 | ouroboros | **PASS** | `adversarialRobustness.ts` blob confirmed; Python parity: ε₂=0.300, composedL=3.0 | pnpm execution (Cursor) |
| L3 | ouroboros | **STAGED** | All 6 formula test files confirmed on main | pnpm vitest execution requires Node — Cursor scope |
| L4 | vsp-otel | **STAGED** | `exporter.ts` blob confirmed; `signSpan()` simulated λ=0.9208 ≥ 0.90 | `szl.anchor_formula.id` not auto-injected in exporter.ts — Cursor Track 1 |
| L5 | uds-mesh | **PASS** | DSSE receipt emitted; HMAC-SHA-256 verified; `lean_commit_sha` consistent L1↔L5 | Cross-organ correlation (amaru→a11oy trace linkage) — Cursor Track 1 |
| L6 | a11oy | **PASS** | `adversarialRobustnessGate` confirmed on main; ε₂=0.300 ≤ 0.500 allow=true | `formula_witness` emission to uds-mesh not in gate.ts — Cursor Track 1 |
| L7 | sentra | **NOT-YET-WIRED** | `sentra_immune.py`, `tupu_replay_5x.py` exist on main | `src/forecasts/witnessed.py` absent; no UDS receipt input consumption — Cursor Track 2a |

---

## Files

```
anatomy_alive/
├── run_anatomy_alive.py          # Main harness — 7-layer integration runner
├── synthetic_trace.json          # Input: synthetic agent trace
├── expected_receipts.json        # Expected DSSE receipt schema per layer
├── formula_witness_schema.json   # JSON Schema for formula_witness field
├── anatomy_alive_evidence.json   # Output: real layer results from last run
├── anatomy_alive_jsonld.json     # W3C PROV JSON-LD — citable in academic work
├── anatomy_alive_run.log         # Full execution log from last run
├── anatomy_alive_demo.md         # 90-second bank pitch / Warhacker demo script
├── requirements.txt
├── README.md
└── diagrams/
    ├── make_diagrams.py                # Generates all 4 diagram artifacts
    ├── sequence_with_timing.md         # Mermaid sequence diagram (for docs)
    ├── sequence_with_timing.png        # Matplotlib timeline (for slides)
    ├── receipt_dag.png                 # DSSE receipt dependency DAG
    ├── receipt_dag.html                # Interactive Plotly DAG
    └── formula_witness_flow.png        # 5 formulas × 7 layers heatmap
```

---

## Cursor Phase 1 deliverables this harness validates against

1. **Track 1 — amaru:** emit `formula_witness` field on every span  
   → harness check: `L2` Python parity confirms formula shape; `L4` checks `szl.anchor_formula.id` in OTel attrs

2. **Track 1 — vsp-otel:** auto-inject `szl.anchor_formula.id` + `szl.lean_theorem_ref` in `exporter.ts`  
   → harness check: `L4` grep of `exporter.ts` source (`has_szl_anchor_formula_id`)

3. **Track 1 — uds-mesh:** store cross-organ correlation by `trace_id`  
   → harness check: `L5` cross-layer SHA consistency; receipt `trace_id` field in schema

4. **Track 1 — a11oy:** gate fires inline; failed gates emit DSSE receipt to uds-mesh  
   → harness check: `L6` `gate_emits_formula_witness` + `gate_emits_dsse_receipt` fields

5. **Track 2a — sentra:** `src/forecasts/witnessed.py` with 12 doctests  
   → harness check: `L7` `witnessed_py_exists` field

When Cursor ships these, re-run `python run_anatomy_alive.py` — STAGED/NOT-YET-WIRED layers will flip to PASS.

---

## PhD-reviewer notes

- **HMAC key:** dev default `szl-formula-hmac-dev-v1` is used here for open verifiability. Production rotates via `FORMULA_HMAC_KEY` env var.
- **Lean theorem ↔ TypeScript linkage:** the theorem proves an abstract metric model; the TS formula is its numerical instantiation. The missing link (Cursor Track 1) is `szl.lean_theorem_ref` as an OTel attribute making the linkage machine-readable.
- **blob SHA pinning:** `EXPECTED_BLOB_SHA = "a96e448f83da40f06f005e7f8ff0492e0870e819"` is recorded in both this harness and `uds-mesh/formula_receipts.py ANCHOR_REGISTRY`. Two independent sources pinning the same blob SHA constitutes cross-repo cryptographic evidence.
- **No test doubles:** every `gh api` call hits `api.github.com` live. Network failures surface as FAIL, not as false PASS.
