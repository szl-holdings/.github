<!--
  SZL Holdings — organization profile README (szl-holdings/.github → profile/README.md)
  Genius Series-A grade. Honesty doctrine LOCKED.
  TWO-TIER PROOF STORY (honest, do NOT inflate):
    LOCKED kernel (source of truth: lutar-lean@main, kernel c7c0ba17, Lean v4.13.0):
      749 declarations · 14 unique axioms · 163 tracked sorries
      locked-proven = EXACTLY 5 formulas {F1, F11, F12, F18, F19} (machine-enforced, no-axiom theorem)
    EXPERIMENTAL tier (CI-green on main, Lean v4.18.0):
      ~119 kernel-clean theorems across Waves 11-19; every #print axioms ⊆ {propext, Classical.choice, Quot.sound}.
      Kernel-verified, CI-green, NEVER folded into the locked count.
    Λ-uniqueness = Conjecture 1 (unconditional uniqueness machine-checked FALSE);
      proven CONDITIONAL on slice-multiplicativity/separability (CUT-2, axiom-free).
    Byzantine BFT safety = Conjecture 2 (faulty organ can equivocate).
    SLSA = Build L1 honest posture / L2 build-attestation present; L2-verified + L3 + FedRAMP = roadmap
      (NOT L2-verified / L3 / FedRAMP / Iron Bank / CMMC).
  Two-product end-state: a11oy (orchestration / Command Platform, incl. a11oy.code) + killinchu (maritime + counter-UAS C2).
  Warhacker is independent work referencing Defense Unicorns UDS — NOT an affiliation.
  IMAGE POLICY: raster assets via ABSOLUTE raw.githubusercontent URLs; diagrams use native mermaid so they always render.
-->

<div align="center">

<img src="https://raw.githubusercontent.com/szl-holdings/.github/main/profile/assets/png/szl-holdings-logo.png" alt="SZL Holdings" width="420" />

# SZL Holdings

### Governed-AI decision infrastructure with a machine-checked Lean 4 proof backbone — and a *published honesty boundary*.

**Every AI decision becomes a cryptographically signed, replayable, tamper-evident receipt** — accountability that no observability or AI-security incumbent ships today. Two live products run on one substrate.

[![Lean 4 proofs](https://img.shields.io/badge/Lean%204-5%20locked%20%2B%20~119%20experimental-c9b787?style=flat-square)](https://github.com/szl-holdings/lutar-lean)
[![SLSA Build L1 honest](https://img.shields.io/badge/SLSA-Build%20L1%20honest%20%C2%B7%20L2%20roadmap-2C5F2D?style=flat-square)](https://slsa.dev/spec/v1.0/levels)
[![cosign keyless](https://img.shields.io/badge/cosign-keyless%20signed-7C3AED?style=flat-square)](https://search.sigstore.dev/)
[![Λ = Conjecture 1](https://img.shields.io/badge/%CE%9B-Conjecture%201-b3541e?style=flat-square)](https://github.com/szl-holdings/lutar-lean/blob/main/BOUNTY.md)
[![Concept DOI](https://img.shields.io/badge/concept%20DOI-10.5281%2Fzenodo.19944926-01696F?style=flat-square)](https://doi.org/10.5281/zenodo.19944926)
[![License](https://img.shields.io/badge/code-Apache--2.0-5fb3a3?style=flat-square)](https://github.com/szl-holdings)

</div>

---

## Two products, one substrate

| Product | What it does | Open it |
|---|---|---|
| **a11oy — Orchestration / Command Platform** | One pane of glass for governed AI: ask & act, deny-by-default safety gates, trust scoring with confidence intervals, a live decision feed, readiness & compliance, forecasting, signed receipts, formal-proof status, a live threat library (CVE / KEV / MITRE), and model routing. Includes **`a11oy.code`** — a *governed* coding assistant that routes the top open models behind a **Λ-gate** with **signed receipts** per generation. | [Open a11oy →](https://szlholdings-a11oy.hf.space/) |
| **killinchu — Maritime + Counter-UAS C2** | Autonomous-systems C2 for air and sea: live **ADS-B / AIS** feeds, multi-sensor fusion, maritime picture (sanctions screening + dark-vessel detection), engagement rules, earthquake forecasting, a **4/4-online governance quorum (3-of-4 majority) reading CONSENSUS HOLDS**, and **verify-it-yourself** signed engagement receipts. | [Open killinchu →](https://szlholdings-killinchu.hf.space/elite) |

**a11oy is the orchestrating brain.** Its reasoning, policy, and operator capabilities are built in as one receipt-bound fabric, and it governs the field tool with the same trust scoring, consensus, and signed receipts. `a11oy.code` is a *governed* LLM surface — not a frontier-weights claim: it routes the strongest **open** models through the Λ-gate and binds every generation to a signed Khipu receipt, so you get top-tier code *with* an audit trail.

> **Warhacker 2026 (June 16–19).** SZL builds toward the Defense Unicorns Warhacker problem statement and runs each challenge end to end. This is **independent work that references Defense Unicorns' UDS ecosystem** — *not affiliated with, sponsored by, or endorsed by Defense Unicorns.*

---

## The ecosystem at a glance — an honest capability matrix

| Layer | Repos | What it provides | Maturity (honest) |
|---|---|---|---|
| **Flagship apps** | [a11oy](https://github.com/szl-holdings/a11oy) · [killinchu](https://github.com/szl-holdings/killinchu) | Governed-AI command platform (incl. `a11oy.code`) · maritime + counter-UAS C2 | **Live** (HF Spaces); receipts signed where a key is present |
| **Formal-methods spine** | [lutar-lean](https://github.com/szl-holdings/lutar-lean) · [lean-kernel](https://github.com/szl-holdings/lean-kernel) · [lambda-bounty](https://github.com/szl-holdings/lambda-bounty) | Lean 4 + Mathlib proofs: **locked-5** {F1,F11,F12,F18,F19} · **~119-theorem experimental tier (Waves 11–19)** · Λ **Conjecture 1** | 5 locked-proven + experimental CI-green; Λ conditional only |
| **Bounded-recursion runtime** | [ouroboros](https://github.com/szl-holdings/ouroboros) · [platform](https://github.com/szl-holdings/platform) | Agent loop with proven early-exit / convergence envelope; substrate monorepo | Reference runtime; dual-witness receipts |
| **Receipt / lake / trust** | [szl-lake](https://github.com/szl-holdings/szl-lake) · [szl-trust](https://github.com/szl-holdings/szl-trust) · [khipu-consensus](https://github.com/szl-holdings/khipu-consensus) | Append-only DSSE receipt store · public proof portal · 3-of-4 witness quorum | Append-only, tamper-evident, offline-verifiable; BFT safety = **Conjecture 2** |
| **Mesh / observability** | [szl-mesh](https://github.com/szl-holdings/szl-mesh) · [uds-mesh](https://github.com/szl-holdings/uds-mesh) · [vsp-otel](https://github.com/szl-holdings/vsp-otel) | Doctrine-pinned CRDT mesh · span schemas · Λ-signed OTel exporter | Schemas + exporter shipped |
| **Sovereign deploy (UDS)** | [uds-bundles](https://github.com/szl-holdings/uds-bundles) · [szl-uds-deployment](https://github.com/szl-holdings/szl-uds-deployment) · [szl-fleet-overlay](https://github.com/szl-holdings/szl-fleet-overlay) · [szl-build-env](https://github.com/szl-holdings/szl-build-env) | Zarf bundles · UDS-core packages · Pepr/Helm overlay · kind+Istio build env | **SLSA Build L1 honest**; cosign keyless; **L2-verified / L3 = roadmap** |
| **Developer surface** | [developers](https://github.com/szl-holdings/developers) · [docs-site](https://github.com/szl-holdings/docs-site) · [szl-cookbook](https://github.com/szl-holdings/szl-cookbook) · [hatun-mcp](https://github.com/szl-holdings/hatun-mcp) | API hub · docs · recipes · doctrine-aware MCP server | Public, Apache-2.0 |
| **Research / brand** | [szl-papers](https://github.com/szl-holdings/szl-papers) · [szl-doctrine](https://github.com/szl-holdings/szl-doctrine) · [szl-brand](https://github.com/szl-holdings/szl-brand) · [warhacker-demo](https://github.com/szl-holdings/warhacker-demo) | Preprints · governance doctrine · brand assets · sovereign demo | Papers CC-BY-4.0; code Apache-2.0 |

---

## The thesis — a proof layer for consequential AI

Modern AI gives you answers; it does not give you **accountability**. SZL turns the governance layer into a substrate — a **Proof Chain** where each decision is policy-checked, evidence-bound, and replayable, then sealed in a DSSE receipt over a SHA-256 hash chain. Trust is scored by a single aggregator, **Λ**, over thirteen axes (provenance, containment, coherence, convergence, …) — and we are explicit about exactly how far that math is proven.

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

Read the full thesis → [szl-papers](https://github.com/szl-holdings/szl-papers) · DOI lineage on [Zenodo](https://doi.org/10.5281/zenodo.19944926).

---

## Proven formulas — what is machine-checked, and exactly how far

The honest core never moves. **Exactly 5 formulas are formally proven and locked** {`F1, F11, F12, F18, F19`} in the kernel (`c7c0ba17`, `749 / 14 / 163`, Lean `v4.13.0`, `lake build` clean) — machine-enforced by `locked_count_five` (depends on **no** axioms). On top of that floor, a larger experimental tier is **kernel-clean and CI-green on `main`** (Lean `v4.18.0`): **~119 theorems across Waves 11–19**, every one with `#print axioms ⊆ {propext, Classical.choice, Quot.sound}` — no new axiom, no `sorry`. Experimental results are labeled as such and are **never** folded into the locked count.

### Locked kernel — proven, sorry-free (exactly 5, machine-enforced)

| Formula | Status | Kernel |
|---|---|---|
| **F1, F11, F12, F18, F19** | **PROVEN** — sorry-free, Lean-core axioms only `[propext, Classical.choice, Quot.sound]` | `c7c0ba17` · `749 / 14 / 163` · Lean `v4.13.0` |

The count of **exactly 5** is itself a Lean theorem (`locked_count_five`, depends on **no** axioms) — the locked set cannot silently grow.

### Experimental tier — kernel-clean, CI-green (Waves 11–19, ~119 theorems) — NOT in the locked 5

| Wave / result | What it is |
|---|---|
| **Wave 11** | CF-1 graph-auto distance invariance, CF-2 KV-cache slots, CF-3 loop early-exit, CF-5 Neyman–Pearson optimality (24 theorems) |
| **Wave 12 — CUT-2** | `lambda_unique_of_separable`: Λ uniqueness **conditional** on {A1,A2,A3,A5 + separability}, **axiom-free** — Λ off bare conjecture, no new axiom |
| **Wave 13** | replay-root completeness, non-Byzantine single-valued vote (shadow, **not** Conjecture 2), HM-bottleneck |
| **Wave 14** | CF-18 alternating-series / Mādhava, CF-19 Reed–Solomon MDS, CF-20 VCG efficiency & truthfulness, CF-21 Cover–Thomas log-sum / Gibbs |
| **Wave 15 — CF-22** | `dpo_klDivergence_nonneg_on_simplex`: conditionally **repairs** the FALSE-as-stated DPO axiom (KL ≥ 0 **on the simplex**), axiom-free |
| **Wave 16** | CF-23 binary-KL crux, CF-24 `geoBin` satisfies full Aczel quasi-arithmetic axioms (real CUT-1 progress), CF-25 Λ scale-invariance, CF-26 place-value |
| **Wave 17 — CF-23** | **full binary Pinsker** `binary_pinsker`: `2(p−q)² ≤ KL` — the long-sought headline; CF-27 monotone-DEQ unique equilibrium; CF-28 recurrent-depth contraction |
| **Waves 18–19** | continued CUT-1 reduction — the full Λ-uniqueness route now hinges on **one published lemma**, `dyadic_image_dense` (BKS, [arXiv:2208.07083](https://arxiv.org/abs/2208.07083)) |

### Λ — the honest line on uniqueness

> **What we proved:** the strongest **axiom-free conditional** uniqueness — any A1–A5 aggregator whose per-axis slices are multiplicative / separable **equals Λ** (`lambda_unique_of_separable`, **CUT-2**, no new axiom token), CI-green. All Λ-impostor deaths (AM, HM, PM², max, min) are axiom-free. The remaining unconditional route is now reduced to **one published lemma**, `dyadic_image_dense` (BKS, [arXiv:2208.07083](https://arxiv.org/abs/2208.07083)).
>
> **What we don't claim:** unconditional uniqueness under the base axioms A1–A5. That statement is **machine-checked false** (`Round13.maxAgg_ne_Lambda`). Λ-uniqueness therefore stays **Conjecture 1** — never a theorem. Open bounty: [BOUNTY.md](https://github.com/szl-holdings/lutar-lean/blob/main/BOUNTY.md).

Full proof table with verbatim `#print axioms` → **[PROVEN_FORMULAS.md](https://github.com/szl-holdings/lutar-lean/blob/main/PROVEN_FORMULAS.md)**.

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
| **Exactly 5 formulas formally proven & locked in Lean** (machine-checked, sorry-free): `F1, F11, F12, F18, F19` — the count is itself a no-axiom Lean theorem. Plus a **~119-theorem experimental tier, kernel-clean & CI-green on `main` across Waves 11–19** (every `#print axioms ⊆ {propext, Classical.choice, Quot.sound}`), labeled experimental. | The remaining formulas as "proven." The experimental theorems are **experimental / CI-green**, labeled as such — never folded into the locked five. |
| **Λ uniqueness is Conjecture 1** unconditionally. It is proven **CONDITIONAL** on slice-multiplicativity (separability) under {A1,A2,A3,A5}, axiom-free — **CUT-2** (`lambda_unique_of_separable`); the unconditional route is reduced to one published lemma (`dyadic_image_dense`). | Λ as an unconditional theorem. Unconditional uniqueness is machine-checked **false** (`Round13.maxAgg_ne_Lambda`). **Byzantine BFT safety is Conjecture 2**, not a theorem. |
| **`a11oy.code` is the best _governed_ LLM surface** — it routes the strongest **open** models through a Λ-gate with signed receipts. | A frontier-weights / "best LLM in the world" claim. We do not train a frontier model. |
| **SLSA Build L1 (honest)** — documented source + build provenance, cosign keyless-signed images, Rekor-anchored; **L2 build-attestation present**. | **NOT** SLSA L2-verified, L3, FedRAMP, Iron Bank, or CMMC. L2-verified + L3 + FedRAMP are **roadmap**. |
| Receipts are genuinely signed where a signing key is present, **honestly marked unsigned** otherwise. AIS / ADS-B feeds are live where available. | Fabricated signatures or fabricated metrics — ever. |

**Locked doctrine** · kernel `c7c0ba17` · **749** declarations / **14** unique axioms / **163** tracked sorries · `lake build` clean. Experimental frontier: Waves 11–19, CI-green.

---

## Deploy the whole mesh — one signed bundle

```bash
uds deploy oci://ghcr.io/szl-holdings/szl-mesh:0.4.0 --confirm
```

Cosign-signed, Rekor-anchored bundle (SLSA Build L1 honest; L2-verified provenance on the roadmap). The deployment story lives in [uds-bundles](https://github.com/szl-holdings/uds-bundles), [szl-mesh](https://github.com/szl-holdings/szl-mesh), [uds-mesh](https://github.com/szl-holdings/uds-mesh), [szl-uds-deployment](https://github.com/szl-holdings/szl-uds-deployment), and [szl-fleet-overlay](https://github.com/szl-holdings/szl-fleet-overlay).

---

## Where to start

| If you want to… | Go to |
|---|---|
| **See the product** | [a11oy](https://szlholdings-a11oy.hf.space/) · [killinchu](https://szlholdings-killinchu.hf.space/elite) |
| **Read the math** | [lutar-lean](https://github.com/szl-holdings/lutar-lean) (Lean 4 kernel) · [PROVEN_FORMULAS.md](https://github.com/szl-holdings/lutar-lean/blob/main/PROVEN_FORMULAS.md) · [szl-papers](https://github.com/szl-holdings/szl-papers) |
| **Build on it** | [developers](https://github.com/szl-holdings/developers) (API hub) · [szl-cookbook](https://github.com/szl-holdings/szl-cookbook) (recipes) · [docs-site](https://github.com/szl-holdings/docs-site) |
| **Deploy it** | [uds-bundles](https://github.com/szl-holdings/uds-bundles) · [szl-mesh](https://github.com/szl-holdings/szl-mesh) · [hatun-mcp](https://github.com/szl-holdings/hatun-mcp) |
| **Verify the chain** | [szl-trust](https://github.com/szl-holdings/szl-trust) (public proof portal) · [khipu-consensus](https://github.com/szl-holdings/khipu-consensus) |

---

<div align="center">

Built by **Stephen P. Lutar Jr.** · Honest by design · Counsel-governed · [🤗 SZLHOLDINGS](https://huggingface.co/SZLHOLDINGS) · [github.com/szl-holdings](https://github.com/szl-holdings) · [ORCID 0009-0001-0110-4173](https://orcid.org/0009-0001-0110-4173)

</div>
