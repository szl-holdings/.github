# Research showcase proposal — September 21, 2026

**Status: DRAFT / NOT QUALIFIED FOR PUBLIC PROFILE PUBLICATION.**

This document preserves the proposal from PR #753, originally at commit `f36618bb9f910cf2410e28dfe08abef414e908ed`. The proposed copy below is retained for review; it is not an admitted statement of current deployed behavior, human ratification, model publication, or estate-wide measurement. Its assertions require source-pinned receipts and independent review before they can be presented as findings. This document is not linked from the public organization profile.

The existing profile remains governed by its compact, table-free front-door contract. Moving this review draft does not change or exempt it from evidence qualification, doctrine checks, or source review. It does not authorize deployment, inference, trading, or model training.

## Qualification required before promotion

- Bind each receipt below to its exact repository, full source revision, artifact path, and reproducible execution evidence. Relative `out/...` names alone do not identify an immutable source.
- Establish whether each observation concerns a test fixture, offline evaluation, candidate implementation, or deployed production revision. Do not substitute one category for another.
- Verify the claimed human-ratification process, sample sizes, aggregation semantics, model-publication disposition, and any correction-ledger guarantees.
- Replace relative timing such as "this week" with the actual measurement interval and distinguish historical inventory from current observations.
- Qualify and rewrite any eventual profile excerpt to fit the existing mobile-friendly, table-free word budget; keep detailed receipts in the research documentation.

## Proposed copy retained for review

The following is the original proposal, not an endorsement of its claims.

---

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
