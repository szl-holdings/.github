# Cursor Roadmap v2 — Walk the Thesis, Make It Real, Innovate + Evolve

**Owner:** Cursor (GitHub side, code-execution authority)
**Author:** Perplexity Computer (HF side, curation authority)
**Founder mandate:** "He needs to know to go through all my thesis and it needs to be real and made and a11oy and the rest innovate and evolve"
**Doctrine:** v6 strict — no hallucinations, no bandaids, no marketing superlatives

---

## The mandate, plain

**Walk the entire thesis chapter by chapter. For every theorem, lemma, definition, and module reference, do this:**

1. **Confirm Lean status** — is it `lake-verified` (134), `skeleton (sorry)` (241), or missing?
2. **Confirm runtime status** — is there a real, executable counterpart in `a11oy`, `ouroboros`, `uds-mesh`, `sentra`, `amaru`, `rosie`, or `vsp-otel`?
3. **If skeleton → close the sorry.** If runtime missing → build the runtime. If runtime exists → innovate + evolve (extend coverage, harden gates, add provider plug-ins, add benchmarks).
4. **Tie everything back** via cross-link tables: thesis line → Lean file:line → runtime path → CI gate → HF Space tab.

When done, the SZL substrate is no longer "papers + receipts." It's a living, falsifiable, end-to-end-verified governance fabric.

---

## What's already done (do NOT redo)

- HF org: 2 models · 22 datasets · **11 Spaces** (all RUNNING) · Team plan
- 3 HF buckets seeded (`szl-artifacts` public, `szl-payloads`/`szl-evidence` private)
- Org card has "By the numbers" + "Style Canon 10/10" blocks
- DCO workflow merged on platform ([PR #210](https://github.com/szl-holdings/platform/pull/210))
- 11 superseded duplicate PRs closed
- All 5 parallel agents landed: PhD Observability+Law, Real+Operational Verifier, UDS Component Spaces, Utility Spaces, **Lean Proof Playground** (live: [lean-proof-playground](https://huggingface.co/spaces/SZLHOLDINGS/lean-proof-playground))
- Cursor handoff PR queue doc merged ([PR #54 to .github](https://github.com/szl-holdings/.github/pull/54))

---

## Thesis chapter → runtime traceability matrix

This is Cursor's actual to-do list. Each chapter row gets two columns: **what theorems live there** and **what runtime/code must exist or evolve to make those theorems real.**

| # | Chapter | Theorem load | Lean target | Runtime owner | Innovate + evolve action |
|---|---------|-------------|-------------|--------------|--------------------------|
| 1 | **Introduction** (`01_introduction.tex`) | 2 theorems | — | — | Ensure all numbers cited (76, 134, 248, 269, 32) match `theorems_index.json` and per-repo CI exactly |
| 2 | **Mathematical Foundations** (`02_mathematical_foundations.tex`) | **31 theorems** (densest) | `Lutar/PACBayes`, `Lutar/Banach`, `Lutar/Calibration`, `Lutar/Crt`, `Lutar/Khipu`, `Lutar/Thresholds`, `Lutar/Composition` | `ouroboros/agentic/a11oy-core`, `ouroboros/agentic/formulas` | **Close all 241 skeleton sorries here first** — this is the bedrock. Madhava bound, false-position, Liu Hui sqrt, Babylonian contraction, etc. |
| 3 | **Runtime Substrate** (`03_runtime_substrate.tex`) | 5 theorems | `Lutar/Khipu/SummationInvariant`, `Lutar/DPOFeasibility`, `Lutar/Uniqueness` | `ouroboros/agentic/agents`, `ouroboros/agentic/mcp-server`, `OUROBOROS_RUN_ALL.py` | Ensure every theorem invoked at runtime emits a DSSE receipt; add provider plug-ins (Sigstore, AWS KMS, GCP KMS) to MCP receipts server |
| 4 | **Agentic Substrate** (`04_agentic_substrate.tex`) | 1 theorem | `Lutar/Composition/AdversarialRobustness` | `a11oy/packages/a11oy-knowledge`, `a11oy/packages/measurement`, `a11oy/packages/policy`, `a11oy/packages/qec-integrity`, `amaru`, `rosie` | **Innovate:** ship `amaru` 7-chakra scheduler as a real Pip-installable + npm package; extend `a11oy-knowledge` with the live theorem index; productize `rosie` operator console (real-time span feed) |
| 5 | **Observability, Security, Governance** (`05_observability_security_governance.tex`) | 1 theorem | `Lutar/SBOMProvenance` (← **the residual sorry at line 109**) | `uds-mesh`, `vsp-otel`, `sentra` | **Close the SBOMProvenance.lean:109 sorry.** Build `vspreceiver`/`vspprocessor` as real Go OTel Collector contrib components. Wire `sentra` as required CI gate. |
| 6 | **New Formulas + Extended Theorems** (`06_new_formulas.tex`) | **16 theorems** | `Lutar/Feynman/FeynmanLineage`, `Lutar/Feynman/PathIntegralAuditSum`, `Lutar/PACBayes/MadhavaBound` (already exists; verify) | `ouroboros/agentic/formulas` | Each new formula must ship with: (a) closed Lean proof, (b) `formulas/<name>.ts` runtime, (c) `tests/<name>.test.ts` parity test, (d) benchmark in `OUROBOROS_RUN_ALL.py` |
| 7 | **Formal Validation — Lean Czar Catalogue** (`07_formal_validation.tex`) | **16 theorems** | All `Lutar/*` | All packages | Make the catalogue auto-generated from `theorems_index.json`. The chapter source should be `\input{generated/czar_catalogue.tex}` regenerated from the JSON on every CI run. |
| 8 | **Conclusion and Future Work** (`08_conclusion.tex`) | 0 | — | — | Convert "future work" items into GitHub issues, one per item, with labels `tier:research` |

**Note:** Chapter 2 alone holds 31 theorems — more than 40% of the named theorems. Make it the first sustained push.

---

## TIER 0 — Drain the open PR queue first (≤ 6 hrs)

Cursor cannot innovate while CI is red. Same as v1 of this roadmap:

| Repo | PR | Action |
|------|----|--------|
| lutar-lean | #66 | Rebase + merge `--admin`. **Fixes the 11 modules currently failing kernel-check on main** ([CI run 26616523354](https://github.com/szl-holdings/lutar-lean/actions/runs/26616523354)) |
| lutar-lean | #74 | Rebase + merge `--admin` (doc-only) |
| lutar-lean | #56 | Close as SUPERSEDED (content on main) |
| lutar-lean | #78 | Close as SUPERSEDED if #66 fixes kernel |
| lutar-lean | #80 | Rebase + merge last (Adinkra graft net-new) |
| platform | #202 | Rebase + merge `--admin` |
| a11oy | #69, #70, #71 | Convert DRAFT → ready, merge `--admin` |
| amaru | #55 | Convert DRAFT → ready, merge `--admin` |
| rosie | #32 | Convert DRAFT → ready, merge `--admin` |
| uds-mesh | #31 | Convert DRAFT → ready, merge `--admin`. **Close #32 as duplicate** |
| ouroboros | #69 | Convert DRAFT → ready, merge `--admin` |
| a11oy #57, amaru #46, sentra #45 | DRAFT relicense | **DO NOT MERGE.** Maintain rebase only. Founder IP decision. |

Acceptance: `gh pr list --state open` across all 20 repos ≤ 3 (only DRAFT relicense PRs remain).

---

## TIER 1 — Walk the thesis, close every reachable sorry

**Goal:** drive `skeleton (sorry)` from **241 → 0** (or whatever stays as named-axiom open problems with A15 disclosure).

### T1.1 — Chapter 2: Mathematical Foundations (31 theorems, densest)

Order of attack (do them in this order — earlier ones unlock later ones):

| Sub-area | Lean files | Why first |
|----------|-----------|-----------|
| `Lutar/Calibration/FalsePosition` | `FalsePosition.lean` | Lake-verified anchor; reference for the proof style |
| `Lutar/Banach/LiuHuiPi` + `Lutar/Banach/BabylonianContraction` | 2 files | Currently failing kernel-check (Chapter 5 sqrt convergence depends on these) |
| `Lutar/Crt/WeightChunking` | 1 file | Failing kernel-check; used by `OUROBOROS_RUN_ALL.py` weight-chunking module |
| `Lutar/PACBayes/MadhavaBound` | 1 file | Already exists; verify proof closes; this is a named-public-theorem anchor |
| `Lutar/Thresholds/QuadraticCompletion` | 1 file | Failing; gate threshold math |
| `Lutar/Composition/AdversarialRobustness` | 1 file | Bridges to Chapter 4 |
| `Lutar/Khipu/SummationInvariant` | 1 file | Failing; bridges to Chapter 3 |

For each: open a PR titled `feat(lean): close <Module> sorries (chapter 2 sweep)`. Commit per theorem so revert is granular. CI must pass `Lean kernel check` before merge.

### T1.2 — Chapter 3: Runtime Substrate (5 theorems)

| File | Connect to |
|------|-----------|
| `Lutar/Khipu/SummationInvariant.lean` | `ouroboros/agentic/agents/khipu_runner.py` |
| `Lutar/DPOFeasibility.lean` | `ouroboros/agentic/agents/dpo_gate.py` |
| `Lutar/Uniqueness.lean` | `ouroboros/agentic/a11oy-core/uniqueness.ts` |

For each closed theorem in Chapter 3:
- Add a parity test: `tests/parity/lean_vs_runtime_<name>.test.ts` that runs the runtime against 1000 random inputs and verifies the theorem's claim holds on every input.
- Emit a DSSE receipt on each parity-test run.

### T1.3 — Chapter 4: Agentic Substrate

The bridge theorem is `AdversarialRobustness`. Once closed:

- `a11oy/packages/policy` exports a `robustness_certificate(...)` function whose output cites the Lean theorem name + commit SHA.
- `a11oy/packages/measurement` gains a `RobustnessProbe` that emits this certificate as part of its 248-test corpus.
- `amaru` (7-chakra scheduler) embeds the certificate in its receipt envelope.

### T1.4 — Chapter 5: Observability, Security, Governance

**The 1 residual sorry lives here**: [`Lutar/SBOMProvenance.lean:109`](https://github.com/szl-holdings/lutar-lean/blob/main/Lutar/SBOMProvenance.lean#L109).

The proof obligation (per Lean playground Tab 6): demonstrate that the SBOM provenance ledger is closed under composition of attested releases. The mathematical content is standard for SBOM lineage; the obstacle is Mathlib-bridging the OCI manifest digest comparison.

**Acceptance:** `Lutar/SBOMProvenance.lean` builds with `lake build` and `grep -c sorry Lutar/SBOMProvenance.lean` returns 0.

### T1.5 — Chapter 6: New Formulas

The 16 theorems in this chapter are SZL's novel claims. They must each ship with **4 parts**:

| Part | File path | Doctrine v6 |
|------|-----------|-------------|
| Lean proof | `repos/lutar-lean/Lutar/<area>/<name>.lean` | lake-verified, no `sorry` |
| TS runtime | `repos/ouroboros/agentic/formulas/<name>.ts` | exported, typed, doc-commented |
| Parity test | `repos/ouroboros/agentic/formulas/<name>.test.ts` | 1k randomized inputs, all pass |
| Benchmark | `OUROBOROS_RUN_ALL.py` module | included in the 32 GREEN; updates count to 33+ |

A new formula is **not real** until all 4 parts are GREEN on `main`.

### T1.6 — Chapter 7: Make the Lean Czar Catalogue auto-generated

The chapter currently lists 16 theorems by hand. That drifts. Cursor builds a generator:

```bash
# repos/ouroboros-thesis/scripts/regen_czar_catalogue.py
# Reads: hf_szl_holdings_launch/lutar_lean_space/theorems_index.json
# Writes: thesis_v18/chapters/generated/czar_catalogue.tex
# Tex source: \input{chapters/generated/czar_catalogue.tex}
```

Wire into CI: `regen-czar-catalogue.yml` runs on every push that touches `theorems_index.json` or any `*.lean` file; opens a PR if the generated tex diverges.

Acceptance: a manual sorry-close in `Lutar/X.lean` automatically updates the thesis Chapter 7 listing on next CI run.

---

## TIER 2 — Innovate + evolve each substrate

For every repo, take what's there and push it from "Series-A ready" to "Series-A live."

### T2.1 — `a11oy` (alignment instrumentation)

Today: 248 tests GREEN, 4 web packages, 4 backend packages. Innovate:

| Area | Action | Acceptance |
|------|--------|-----------|
| `a11oy-core` | Add live theorem-index query API: `POST /lookup {theorem}` → returns Lean file:line + status + last commit | Cursor curls it; gets correct JSON |
| `a11oy-knowledge` | Auto-mirror `theorems_index.json` on every CI; expose as `/api/theorems` paginated | HTTP 200 + 375 entries |
| `measurement` | Add 50 new tests (248 → 298) targeting the Chapter 6 new formulas | CI shows 298 GREEN |
| `policy` | Implement deny-by-default policy DSL grounded in Lean theorems; `policy_v2.yaml` | Lint passes |
| `qec-integrity` | Add Reed-Solomon code over the receipt chain; verify under single-bit corruption | parity test passes |
| `a11oy-ledger` (web) | Add `ledger.export()` that bundles a Merkle-rooted receipt set + Lean proof URIs | exported bundle verifies offline |

### T2.2 — `lutar-lean` (Lean 4 substrate)

Today: 6,022 .lean files, 134 lake-verified, 241 skeletons, 13 named axioms, 1 residual sorry. Innovate:

- **Build a `Lutar.Frontier` module** that re-exports the named axioms + a `frontier_status : List FrontierItem` value queryable by other modules
- **CI matrix:** lake build on Lean 4.13.0 (current) + 4.14.0 (next) — catch drift earlier
- **Doc generation:** `lake exe doc-gen4` on every push → publish to GitHub Pages
- **Mathlib upgrade lane:** dedicated branch + bot that opens a PR when Mathlib publishes a stable tag

### T2.3 — `ouroboros` (runtime substrate)

Today: 32 modules GREEN via `OUROBOROS_RUN_ALL.py`. Innovate:

- Promote to **33+** by adding each Chapter 6 new-formula benchmark
- **OTel-native:** every module emits OTLP spans (the run currently emits internal receipts; bridge them to OTLP via `vsp-otel`)
- **Replay harness:** `ouroboros_replay.py <receipt_chain.jsonl>` re-runs any historical attestation chain deterministically
- **Differential testing** against [`anthropic/anthropic-cookbook`](https://github.com/anthropics/anthropic-cookbook) governance examples — show our chain catches violations theirs miss (documented honestly, no superlatives)

### T2.4 — `uds-mesh` (Universal Decision Span)

Today: 269 tests GREEN, schemas in `schemas/`, extended attestations as JSONL. Innovate:

- **OTel Collector contrib:** ship `vspreceiver` + `vspprocessor` in Go to [open-telemetry/opentelemetry-collector-contrib](https://github.com/open-telemetry/opentelemetry-collector-contrib). Open the upstream PR.
- **Span field → backend mapping** (from PhD Obs+Law report): publish as the canonical `MAPPING.md` consumed by Datadog/Honeycomb/Tempo/Jaeger users
- **SLSA L1 → L3:** wire `slsa-github-generator` reusable workflow for releases

### T2.5 — `sentra` (security gates)

Today: 6-gate scanner Space ([sentra-security-gates](https://huggingface.co/spaces/SZLHOLDINGS/sentra-security-gates)) with research-backed patterns (arXiv:2403.04957, arXiv:2302.12173). Innovate:

- Productize the Space into a **reusable GitHub Action**: `szl-holdings/sentra-action@v1`
- Mark **required** on `a11oy` + `ouroboros` first
- Add **runtime scanner** that reads OTLP spans live and gates execution (not just CI)
- Publish threat-model TM-01.md + TM-02.md grounded in the cited arXiv papers

### T2.6 — `amaru` (7-chakra memory attestation)

Today: HF Space ([amaru-memory-attestation](https://huggingface.co/spaces/SZLHOLDINGS/amaru-memory-attestation)) with Plotly receipt-chain graph. Innovate:

- Ship as a real **Python package** (`pip install szl-amaru`) and **npm package** (`@szl-holdings/amaru`)
- Add **Postgres backing** so receipt chains survive process restarts
- Add **multi-tenant** attestation chains (one chain per `tenant_id`)
- Add **cross-chain reconciliation** between amaru chains and uds-mesh extended-attestation JSONL

### T2.7 — `rosie` (operator console)

Today: HF Space ([rosie-operator-console](https://huggingface.co/spaces/SZLHOLDINGS/rosie-operator-console)) with Doctrine v6 ban-word sweep. Innovate:

- **Real-time span feed** from `uds-spans-receipts` (websocket subscribe)
- **Receipt-chain viewer** (Plotly) tied to live emission
- **Gate-flip alerts** (per FG-S1..S4 thresholds from `agi-forecast`)
- **One-click receipt re-verification**
- **Operator notebook** — every alert produces a runbook entry with the cited Lean theorem governing the decision

### T2.8 — `vsp-otel`

Today: HF Space ([vsp-otel-emitter](https://huggingface.co/spaces/SZLHOLDINGS/vsp-otel-emitter)) — pure-Python port of the TypeScript exporter. Innovate:

- Promote to real OTel Collector contrib (T2.4 shares this)
- Add **Λ-axis sliders → live OTLP emission to a public Tempo demo**
- Add **flame chart export** as a static PNG saved to `szl-evidence/flame-charts/`

---

## TIER 3 — Productize for Series-A

### T3.1 — Investor deck v1

10 slides. Cursor codes the data pipeline that pulls live numbers (76, 134, 248, 269, 32, 11 Spaces, 7 DOIs) at deck-build time so the deck cannot drift. Perplexity drives the asset generation via the `pptx` skill.

### T3.2 — Gartner MQ submission packet

`szl-holdings/.github/evidence/gartner-mq/`:
- Reference architecture diagram
- 4 case studies
- Pricing + positioning vs Anthropic RSP / OpenAI Preparedness / Google DeepMind

### T3.3 — Customer pilot pipeline

New private repo `szl-holdings/customer-pilots`:
- One folder per pilot
- NDA + scope-of-work + weekly receipt log
- Private dashboard Space showing pilot health

---

## Coordination contract (Doctrine v6, signed 2026-05-29)

| Surface | Owner | Authority |
|---------|-------|-----------|
| `szl-holdings/*` GitHub | **Cursor** | Push + merge `--admin` (founder pre-authorized) |
| `SZLHOLDINGS/*` HF | **Perplexity** | Push + curation |
| Cross-link tables (HF ↔ GitHub) | **Both** | Either may update; both maintain |
| DRAFT relicense PRs (a11oy#57, amaru#46, sentra#45) | **Founder only** | Cursor rebases, never merges |
| Production release tags | **Cursor + founder approval** | DCO-sign required |
| Token rotation | **Founder only** | Cursor consumes via GH Actions secret |

---

## Daily reporting cadence (Cursor → main)

Cursor pushes `szl-holdings/.github/coordination/daily-status-YYYY-MM-DD.md`:

```markdown
## Date: YYYY-MM-DD
## Sorries closed today: K (running total: ... / 241)
## CI green ratio: M / 17
## Open PRs: N (target ≤ 3)
## Theorems made real this week (chapter:name): ...
## Founder action queue: ...
## Blockers: ...
```

Perplexity reads this on each session, syncs HF state, verifies no drift.

---

## Definition of Done

This roadmap is COMPLETE when:

- [ ] **0 skeleton sorries** in `lutar-lean` (or all remaining `sorries` are named-axiom open problems with A15 disclosure)
- [ ] **The 1 residual `sorry` at `SBOMProvenance.lean:109` is closed**
- [ ] Every Chapter 6 new formula has all 4 parts GREEN (Lean + TS + parity + benchmark)
- [ ] Chapter 7 Czar Catalogue is auto-generated and matches `theorems_index.json` byte-for-byte
- [ ] `gh pr list --state open` ≤ 3 (only DRAFT relicense PRs)
- [ ] All 17 production repos: main CI all-green
- [ ] `slsa-verifier` returns OK for latest release of each release-eligible repo
- [ ] `lutar-lean` kernel check is required + GREEN
- [ ] `vspreceiver` + `vspprocessor` upstream PR opened to OTel Collector contrib
- [ ] `sentra-action@v1` published + marked required on `a11oy` and `ouroboros`
- [ ] `amaru` + `vsp-otel` shipped as pip + npm packages
- [ ] arXiv ID minted + replacing `arXiv:TBD` everywhere
- [ ] Investor deck v1 + Gartner MQ packet ready
- [ ] 1+ customer pilot in progress

---

**This is the single source of truth. Update this file; do not duplicate it.**

— Perplexity Computer, 2026-05-29 04:48 UTC
