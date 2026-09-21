![SZL Holdings evidence lattice](./assets/evidence-lattice-v2.webp)

# SZL Holdings

**Governed AI. Evidence you can inspect.**

Source, running software, and model evaluations are separate claims. Follow the evidence for the exact artifact and revision; unknowns remain visible instead of being filled in.

## Start here

1. **Explore the product** — [a-11-oy.com](https://a-11-oy.com): A11oy, current capability status, and governed workflows.
2. **Inspect the evidence** — [a11oy.net](https://a11oy.net): proof, receipts, evaluations, and known bounds.
3. **Browse the artifacts** — [Hugging Face / SZLHOLDINGS](https://huggingface.co/SZLHOLDINGS): models, software kernels, datasets, and Spaces. Check each artifact's evidence and limitations.
4. **Inspect the source estate** — [GitHub / szl-holdings](https://github.com/szl-holdings): canonical source, evaluation lanes, and repository-specific controls.

## Current state

**21 public Spaces, 46 models, 35 datasets.** Observed **2026-09-10T03:20:41Z** under the anonymous `hf-public-author-membership/v1` predicate. These are public API repository counts, not the authenticated organization total, the governed keep-list, or a count of production-ready models. Software kernels count once as model repositories; private assets, collections, and buckets are outside these totals.

[Source-pinned inventory](https://github.com/szl-holdings/a11oy/blob/4c6621b17ba452d5af7aa2460462fdfbe513509f/docs/huggingface-ecosystem-manifest.json) · [Generation and verification](https://github.com/szl-holdings/a11oy/actions/runs/34432937958) · [Machine-readable binding](https://github.com/szl-holdings/.github/blob/main/profile/public-inventory.json)

## Inference flagship

**One inference flagship:** [SZL Router](https://github.com/szl-holdings/szl-router) is source-owned at `szl-holdings/szl-router`; its public presentation target is [`SZLHOLDINGS/llm-router-live`](https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live), product integration is [https://a-11-oy.com/code](https://a-11-oy.com/code), and proof originates at [a11oy.net](https://a11oy.net).

Portfolio roles distinguish **one inference flagship**, **three commercial flagships**, **five public domain bodies**, and **six internal engines**. Those labels describe topology, **not availability, operational readiness, or publication policy**.

## Historical estate contract

**HISTORICAL:** estate-alignment contract v1 recorded **16 portfolio Spaces**, **1 inventory-only Space**, **45 models**, and **34 datasets**. Those figures are retained only as the prior contract snapshot; they do not override the dated current public observation above. Its named topology includes **A11oy**, **Forge**, **Killinchu**, **Terra**, **PRISM Counsel**, **PURIQ Finance**, and **LYTE**.

## Diligence paths

**Receipt verification:** [a11oy source](https://github.com/szl-holdings/a11oy) contains the source and verification contracts.

**Model training and evaluation:** [szl-forge](https://github.com/szl-holdings/szl-forge) contains kits, datasets, runbooks, measured limits, and frontier evaluation lanes.

**Governance for MCP:** [hatun-mcp](https://github.com/szl-holdings/hatun-mcp) contains the governed MCP surface.

**Qualification evidence:** [szl-frontier](https://github.com/szl-holdings/szl-frontier) records exact-source frontier admissions and HOLD/EVALUATION boundaries.

## Evidence boundary

**Current state** is a dated observation, not a promise of future availability. **HISTORICAL** evidence remains historical even when a newer source exists. **SIMULATED** results are not measured production results and must stay labeled as such.

Pre-launch. A passing source check does not establish a live deployment, and a signed record does not establish independent model quality. Runtime status, verification evidence, and remaining gaps are separate diligence inputs.

*Doctrine: give away the format, sell the control plane, keep the proof.*

---

## Research showcase proposal — September 21, 2026

> Draft proposal retained for review, not an admitted replacement for the front door above. The measurements and publication assertions below still require source-pinned receipt verification and exact-head CI before this pull request can be merged. They do not establish current production behavior or override the dated inventory and evidence boundaries above.

**We build AI systems that have to show their work — and we publish the parts that do not work yet.**

Most AI claims are unfalsifiable by construction. Ours are built so you can check them, and so that we find out when we are wrong. Sometimes that means shipping a result that makes us look worse. That is the point.

---

## For anyone

Three things we measured this week, in plain terms.

**We checked our own triage engine against our own rulebook, and it failed.** Our production governance gate checks **13** separate qualities, and every one has to clear its own bar on its own. The engine we had deployed checks **4** and multiplies them together, which lets a strong score cover for a weak one. On 100 examples our own reviewers had labelled, the deployed engine would have approved **35** that the rulebook refuses.

**We tried to train a small model on our own data, and our own checker blocked it.** The data turned out to be near-duplicates of itself — the two most similar examples differed by a single word. A model trained on it would have scored brilliantly and learned nothing. No model was published.

**We wrote down every time we were wrong.** Corrections are recorded permanently in an append-only ledger, including corrections to claims we had made earlier the same day, each with a test attached so the mistake cannot quietly return.

---

## For engineers

| Measurement | Result | Receipt |
|---|---|---|
| Gate shape: canonical vs deployed | 13 axes, non-compensatory, per-axis floors vs 4 axes, compensatory | `out/yuyay_gate_conformance.json` |
| Rows where the product admits what the conjunction refuses | 35 of 100 | same |
| Aggregator properties | monotone, homogeneous, idempotent, bounded — **not symmetric**, on 447 of 895 vectors | `out/axiom_conformance.json` |
| Corpus contamination | **REFUSED** at max char-5gram Jaccard 0.8378 | `out/leakage_gate.json` |
| Estate repositories audited | 88 public, 689 distinct receipt schemas found, 75 never previously assessed | `out/estate_audit.json` |
| Human-ratified evaluation rows | 42 | `out/ratified_scoreboard.json` |

### How the estate is organised

- **Kernels** — shared primitives: signing, provenance, invariants, bounded loops, honest BLOCKED states.
- **Formalisation** — a Lean 4 + Mathlib library behind the governance mathematics. Our central aggregator uniqueness claim is a **conjecture, disproved as stated**; only a conditional result is proved, and the distinction is enforced in CI rather than trusted to prose.
- **Products** — governed command surfaces emitting a signed receipt per decision.
- **Evidence** — an append-only receipt lake, verifiable offline.

### Reading our labels

- **MEASURED** — produced by a run, with a receipt.
- **BLOCKED** — a gate refused. Deliberate, not broken.
- **UNAVAILABLE** — the capability was absent, and absence is never converted into a pass.
- **surrogate / test-fixture / roadmap** — not a production artefact, and tagged so.
- **no-weights / curriculum-only** — nothing to load; present for provenance.

### What we do not claim

- No leaderboard win, no baseline beaten, no comparison against another vendor.
- No proof-kernel verification outside the formalisation repository itself; elsewhere, symbols are bound by name.
- Supply-chain posture is level one honest, with level two on the roadmap. Nothing beyond that is claimed.
- Energy is reported as measured, or as unavailable. Never estimated.

---

*Verification proves integrity and origin. It does not prove accuracy or performance, and we do not let it pretend to.*

A gate that only ever agrees with you is decoration.
