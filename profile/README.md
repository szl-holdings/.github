<!--
  SZL Holdings — organization profile README (szl-holdings/.github → profile/README.md)
  Genius Series-A grade. Honesty doctrine v11 LOCKED.
  TWO-TIER PROOF STORY (honest, do NOT inflate):
    LOCKED kernel (source of truth: lutar-lean@main, kernel c7c0ba17, Lean v4.13.0):
      749 declarations · 14 unique axioms · 163 tracked sorries
      locked-proven = exactly 5 formulas {F1, F11, F12, F18, F19} (machine-enforced)
    EXPERIMENTAL scope (CI-green on main @ 7885fd9, Lean v4.18.0, 1304 decls / 22 axioms):
      ~36 experimental theorems — waves 5/6/7/8 + agentic P1–P6 + airtight Λ (Set α/δ) + coder.
      Kernel-verified, CI-green, NOT folded into the locked count.
    Λ-uniqueness = Conjecture 1 (never a theorem; unconditional uniqueness machine-checked FALSE)
    SLSA Build L1 + L2 on service images (NOT L3 / FedRAMP / Iron Bank / CMMC)
  Two-product end-state: a11oy (command platform) + killinchu (drones & vessels).
  Zero user-facing dead-organ references — internal capabilities are presented as reasoning / policy / operator.
  IMAGE POLICY: all raster assets referenced by ABSOLUTE raw.githubusercontent URLs (relative
  paths break on the org profile render); all diagrams use native mermaid so they ALWAYS render.
-->

<div align="center">

<img src="https://raw.githubusercontent.com/szl-holdings/.github/main/profile/assets/png/szl-holdings-logo.png" alt="SZL Holdings" width="420" />

# SZL Holdings

### Governed AI you can *prove*.

**Every AI decision becomes a cryptographically signed, replayable, tamper-evident receipt** — accountability that no observability or AI-security incumbent ships today. Two live products run on one substrate.

<a href="https://github.com/szl-holdings"><img src="https://raw.githubusercontent.com/szl-holdings/.github/main/profile/assets/png/org_card.png" alt="SZL Holdings — 5 locked-proven {F1,F11,F12,F18,F19} + ~36 experimental theorems CI-green · 749/14/163 locked kernel · Λ = Conjecture 1" width="860" /></a>

[![Doctrine v11 LOCKED](https://img.shields.io/badge/Doctrine-v11%20LOCKED-0B1F3A?style=flat-square)](https://github.com/szl-holdings/.github/tree/main/doctrine)
[![SLSA Build L1 + L2](https://img.shields.io/badge/SLSA-Build%20L1%20%2B%20L2-2C5F2D?style=flat-square)](https://slsa.dev/spec/v1.0/levels)
[![cosign keyless](https://img.shields.io/badge/cosign-keyless%20signed-7C3AED?style=flat-square)](https://search.sigstore.dev/)
[![Lean 4 proofs](https://img.shields.io/badge/Lean%204-5%20locked%20%2B%20~36%20experimental-c9b787?style=flat-square)](https://github.com/szl-holdings/lutar-lean)
[![Λ = Conjecture 1](https://img.shields.io/badge/%CE%9B-Conjecture%201-b3541e?style=flat-square)](https://github.com/szl-holdings/lutar-lean/blob/main/BOUNTY.md)
[![License](https://img.shields.io/badge/code-Apache--2.0-5fb3a3?style=flat-square)](https://github.com/szl-holdings)

</div>

---

## Two products, one substrate

| Product | What it does | Open it |
|---|---|---|
| **a11oy — Command Platform** | One pane of glass for governed AI: ask &amp; act, deny-by-default safety gates, trust scoring with confidence intervals, a live decision feed, readiness &amp; compliance, forecasting, signed receipts, formal-proof status, a live threat library (CVE / KEV / MITRE), and model routing. | [Open a11oy →](https://szlholdings-a11oy.hf.space/) |
| **killinchu — Drones &amp; Vessels** | Autonomous-systems field tool for air and sea: live track board, multi-sensor fusion, maritime picture (sanctions screening + dark-vessel detection), engagement rules, swarm / autonomy governance, and **verify-it-yourself** signed engagement receipts. | [Open killinchu →](https://szlholdings-killinchu.hf.space/elite) |

**a11oy is the orchestrating brain.** Its reasoning, policy, and operator capabilities are built in as one receipt-bound fabric, and it governs the field tool with the same trust scoring, consensus, and signed receipts. The platform runs every Warhacker challenge problem end to end.

---

## The thesis — a proof layer for consequential AI

Modern AI gives you answers; it does not give you **accountability**. SZL turns the governance layer into a substrate — a **Proof Chain** where each decision is policy-checked, evidence-bound, and replayable, then sealed in a DSSE receipt over a SHA-256 hash chain. Trust is scored by a single aggregator, **Λ**, over four axes — provenance, containment, coherence, and convergence — and we are explicit about exactly how far that math is proven.

```mermaid
flowchart LR
  decision([decision]) --> POLICY[POLICY<br/>deny-by-default gates]
  POLICY --> EVIDENCE[EVIDENCE<br/>bound &amp; cited]
  EVIDENCE --> LAMBDA["Λ score<br/>(advisory · Conjecture 1)"]
  LAMBDA --> RECEIPT[DSSE receipt<br/>cosign-signed]
  RECEIPT --> LEDGER[(hash-chained ledger<br/>replayable · tamper-evident)]
  LEDGER -. "verify offline, trusting no one" .-> decision
  classDef g fill:#0d1322,stroke:#5ad1ff,color:#e8ecf6;
  classDef gold fill:#0d1322,stroke:#c9a227,color:#e8ecf6;
  classDef green fill:#0d1322,stroke:#7CFFB2,color:#e8ecf6;
  class decision,POLICY,EVIDENCE g; class LAMBDA gold; class RECEIPT,LEDGER green;
```

### The substrate — how a governed run flows

```mermaid
flowchart LR
  LL["lutar-lean<br/>(Lean 4 kernel)"] --> OB[ouroboros]
  LL --> A[a11oy]
  OB --> POL[policy]
  A --> POL
  A --> REA[reasoning]
  A --> KD[(Khipu Merkle DAG)]
  POL --> OP[operator console]
  REA --> OP
  classDef k fill:#0d1322,stroke:#7CFFB2,color:#e8ecf6;
  classDef c fill:#0d1322,stroke:#5ad1ff,color:#e8ecf6;
  classDef p fill:#0d1322,stroke:#8b7bff,color:#e8ecf6;
  class LL,KD k; class OB,A,POL,REA c; class OP p;
```

Read the full thesis (v23, *“The Unified Substrate”*) → [szl-papers/thesis/v23](https://github.com/szl-holdings/szl-papers) · DOI lineage on [Zenodo](https://doi.org/10.5281/zenodo.19944926).

---

## Proven formulas — what is machine-checked, and exactly how far

The honest core never moves. **Exactly 5 formulas are formally proven and locked** {`F1, F11, F12, F18, F19`} in the Doctrine-v11 kernel (`c7c0ba17`, `749 / 14 / 163`, Lean `v4.13.0`, `lake build` clean) — machine-enforced by `Lutar.Wave8.AxiomDisclosure.locked_count_five` (depends on NO axioms). On top of that locked floor, **~36 experimental theorems** are kernel-verified and **CI-green on `main` @ `7885fd9`** (Lean `v4.18.0`, `1304` declarations / `22` unique axioms): waves 5/6/7/8 + agentic P1–P6 + airtight Λ (Set α/δ) + coder. Experimental results are labeled as such and are **never** folded into the locked count. **Λ-uniqueness is Conjecture 1** — proven *only conditionally* within strengthened axiom classes, machine-checked *false* unconditionally.

### Locked kernel — proven, sorry-free (exactly 5, machine-enforced)

| Formula | Status | Kernel |
|---|---|---|
| **F1, F11, F12, F18, F19** | **PROVEN** — sorry-free, Lean-core axioms only `[propext, Classical.choice, Quot.sound]` | `c7c0ba17` · `749 / 14 / 163` · Lean `v4.13.0` |

The count of **exactly 5** is itself a Lean theorem (`Lutar.Wave8.AxiomDisclosure.locked_count_five`, depends on **no** axioms) — the locked set cannot silently grow.

### Experimental, kernel-verified (CI-green) — labeled experimental, NOT in the locked 5

| Campaign | Result | PR | CI-green head |
|---|---|---|---|
| **Agentic loop P1–P6** | Governed RAG→MCP→kernel→receipt loop proven as a **system** (14 axiom-free; P5 axiom-gated on hash-CR) | [#188](https://github.com/szl-holdings/lutar-lean/pull/188) | `2ede47a2` |
| **Wave-5** | AM–GM, Cauchy–Schwarz, conformal coverage, receipt-collision pigeonhole, optional-stopping (11) | [#186](https://github.com/szl-holdings/lutar-lean/pull/186) | `b71114cf` |
| **Wave-6** | Graph substrate: Λ-graph iso-invariance, GNN≤1-WL ceiling, spectral contraction, DAG termination (11) | [#189](https://github.com/szl-holdings/lutar-lean/pull/189) | `dc7ae26d` |
| **Wave-7** | Conformal rank-count/p-value, Doob two-sided audit envelope, PAC-Bayes routing envelope (10) | [#190](https://github.com/szl-holdings/lutar-lean/pull/190) | `d6a232ba` |
| **Mathlib-bump C3/C4/C5** | Concentration / KL re-exports, CI-green | [#187](https://github.com/szl-holdings/lutar-lean/pull/187) | — |
| **Coder formulas** | Code-substrate formula ports, CI-green | [#193](https://github.com/szl-holdings/lutar-lean/pull/193) | — |
| **Λ-uniqueness (Set α + Set δ) — airtight Λ** | Conditional uniqueness within **strengthened** axiom classes, CI-green (`lambda_unique_setAlpha` uses Lean-core axioms only); 10 impostor-deaths axiom-free | [#192](https://github.com/szl-holdings/lutar-lean/pull/192) | `5f0bb5ee` |
| **Wave-8 (10 theorems)** — disclosure-soundness, hash-chain tamper-evidence, split-conformal coverage, CPA minimality, Simplex switching safety, Byzantine n=3f+1, min-gate uniqueness, density-matrix PSD, governance spectral, Λ strict monotonicity | [lutar-lean@main](https://github.com/szl-holdings/lutar-lean) | `7885fd9` |

**Key Wave-8 results (with benefit):** `Ph1 disclosure_sound` (axiom-honesty gate) · `M2 hashchain_tamper_evident` (Cannonico tamper-evidence; `#print axioms` = `[propext]` only) · `CP1` split-conformal **marginal** coverage (trust intervals — *split-conformal, NOT Hoeffding*) · `G1` CPA minimality (collision) · `S2` Simplex switching safety · `B1` Byzantine `n=3f+1` · `L2` min-gate deny-by-default uniqueness · `Q1` density-matrix PSD · `Q2` governance spectral (real) · `L3` Λ strict monotonicity. Core axioms `[propext, Classical.choice, Quot.sound]`; `0 sorryAx`.

### Λ — the honest line on uniqueness

> **What we proved:** Λ (the geometric-mean trust aggregator) is **unique within strengthened axiom classes** — Set α `{symmetry, idempotency, all-strict-monotonicity, continuity, multiplicativity}` and Set δ `{reflexivity, symmetry, bisymmetry, per-argument strict monotonicity, multiplicativity}` — each *conditional on explicitly declared, cited bridge axioms*, CI-green ([PR #192](https://github.com/szl-holdings/lutar-lean/pull/192) @ `5f0bb5ee`). Λ-membership and all ten impostor-deaths (AM, HM, PM², max, min) are **axiom-free**.
>
> **What we don't claim:** unconditional uniqueness under the original weaker axioms A1–A5. That statement is **machine-checked false** (`Round13.maxAgg_ne_Lambda`, in-tree). Λ-uniqueness therefore stays **Conjecture 1** — never a theorem. Open bounty: [BOUNTY.md](https://github.com/szl-holdings/lutar-lean/blob/main/BOUNTY.md).

Full proof table with verbatim `#print axioms`, run IDs, and per-result maturity → **[PROVEN_FORMULAS.md](https://github.com/szl-holdings/lutar-lean/blob/main/PROVEN_FORMULAS.md)** · methodology → [lutar-lean](https://github.com/szl-holdings/lutar-lean).

---

## Verify it yourself — trust nothing

Engagement decisions on the **killinchu** surface are signed with a real ECDSA-P256 cosign key. Verify a receipt **offline**, trusting neither us nor the server:

```bash
curl -s https://szlholdings-killinchu.hf.space/cosign.pub -o cosign.pub
curl -s https://szlholdings-killinchu.hf.space/api/killinchu/v1/receipt/export > receipt.json
# verify the DSSE signature offline   ->  "Verified OK"
# tamper a single byte and re-verify   ->  "Verification failure"
```

That is the whole product in one command: a third party can confirm a decision happened, exactly as recorded, with zero trust in SZL.

---

## What we claim — and what we don't

We surface only what is machine-checked as fact. Everything else is labeled honestly in the apps.

| We claim | We do **not** claim |
|---|---|
| **Exactly 5 formulas formally proven in Lean** (machine-checked, sorry-free): `F1, F11, F12, F18, F19` — the count is itself a no-axiom Lean theorem. Plus **~36 experimental theorems CI-green on `main` @ `7885fd9`** (waves 5–8, agentic P1–P6, airtight Λ), labeled experimental. | The remaining formulas as “proven.” The ~36 experimental theorems (waves 5/6/7/8 + the agentic loop + airtight Λ) are **experimental / CI-green**, labeled as such — not part of the locked proven set. |
| **Λ-uniqueness is Conjecture 1** — unique *only conditionally* (strengthened axiom classes, CI-green). Open bounty: [BOUNTY.md](https://github.com/szl-holdings/lutar-lean/blob/main/BOUNTY.md). | Λ as an unconditional theorem. Unconditional uniqueness is machine-checked **false**, and we say so. |
| **SLSA Build L1 + L2** on all service images (cosign + `slsa.dev/provenance/v0.2` attestation). | L3, FedRAMP, Iron Bank, or CMMC. |
| Receipts are genuinely signed where a signing key is present, **honestly marked unsigned** otherwise. | Fabricated signatures or fabricated metrics — ever. |
| Maritime AIS uses a clearly-labeled **sample / replay** dataset. | A live production AIS feed. |

**Locked doctrine: v11** · kernel `c7c0ba17` · **749** declarations / **14** unique axioms / **163** tracked sorries · `lake build` clean.

---

## Deploy the whole mesh — one signed bundle

```bash
uds deploy oci://ghcr.io/szl-holdings/szl-mesh:0.4.0 --confirm
```

Cosign-signed bundle; each service image carries its own SLSA L2 provenance. The deployment story lives in [uds-bundles](https://github.com/szl-holdings/uds-bundles), [szl-mesh](https://github.com/szl-holdings/szl-mesh), [uds-mesh](https://github.com/szl-holdings/uds-mesh), [szl-uds-deployment](https://github.com/szl-holdings/szl-uds-deployment), and [szl-fleet-overlay](https://github.com/szl-holdings/szl-fleet-overlay).

---

## Where to start

| If you want to… | Go to |
|---|---|
| **See the product** | [a11oy](https://szlholdings-a11oy.hf.space/) · [killinchu](https://szlholdings-killinchu.hf.space/elite) |
| **Read the math** | [lutar-lean](https://github.com/szl-holdings/lutar-lean) (Lean 4 kernel) · [PROVEN_FORMULAS.md](https://github.com/szl-holdings/lutar-lean/blob/main/PROVEN_FORMULAS.md) · [szl-papers](https://github.com/szl-holdings/szl-papers) (thesis v1→v23) |
| **Build on it** | [developers](https://github.com/szl-holdings/developers) (API hub) · [szl-cookbook](https://github.com/szl-holdings/szl-cookbook) (recipes) · [docs-site](https://github.com/szl-holdings/docs-site) |
| **Deploy it** | [uds-bundles](https://github.com/szl-holdings/uds-bundles) · [szl-mesh](https://github.com/szl-holdings/szl-mesh) · [hatun-mcp](https://github.com/szl-holdings/hatun-mcp) |
| **Verify the chain** | [szl-trust](https://github.com/szl-holdings/szl-trust) (public proof portal) · [khipu-consensus](https://github.com/szl-holdings/khipu-consensus) |

---

<div align="center">

Built by **Stephen P. Lutar Jr.** · Honest by design · Counsel-governed · [🤗 SZLHOLDINGS](https://huggingface.co/SZLHOLDINGS) · [github.com/szl-holdings](https://github.com/szl-holdings)

</div>
