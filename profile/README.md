<div align="center">

<img src="https://raw.githubusercontent.com/szl-holdings/szl-brand/main/kit/logos/png/kanchay-512.png" alt="SZL Holdings — kanchay mark" width="120" />

# SZL Holdings — Sovereign Governed AI

**Provable by math, signed by receipts, runs on your hardware.**

### 5/5 flagships live · 5/5 cosign-signed via Sigstore Rekor · 749 declarations · 14 axioms · 163 sorries · Doctrine v11 LOCKED

[Quickstart](https://docs.szlholdings.com/quickstart) · [Docs](https://docs.szlholdings.com) · [Cookbook](https://github.com/szl-holdings/szl-cookbook) · [Verify](https://github.com/szl-holdings/szl-cookbook/blob/main/recipes/01-verify-a-receipt-end-to-end.md) · [Cite](#citation) · [Releases](https://github.com/orgs/szl-holdings/repositories)

[GitHub: szl-holdings](https://github.com/szl-holdings) · [ORCID 0009-0001-0110-4173](https://orcid.org/0009-0001-0110-4173) · [Docs Site](https://github.com/szl-holdings/docs-site) · Apache-2.0 OSS

</div>

> **What changed:** Repos consolidated for Series-A clarity. The org now holds **39 repositories — 21 active and 18 archived** (32 public + 7 private; archived repos carry redirect notices). Counts verified live against the GitHub org API (`type=all`) on 2026-06-03. See the [org consolidation report](https://github.com/szl-holdings/.github) for the full log.

---

## Flagships

Five live organs of the mesh. Each exposes a `/healthz` board reporting the same locked doctrine numbers.

| Module | Space | Badge | One line |
|---|---|---|---|
| **a11oy** | [SZLHOLDINGS/a11oy](https://huggingface.co/spaces/SZLHOLDINGS/a11oy) | [![a11oy CI](https://github.com/szl-holdings/a11oy/actions/workflows/ci.yml/badge.svg)](https://github.com/szl-holdings/a11oy/actions/workflows/ci.yml) | Governance gate — Λ-gate router, policy enforcement, MCP host. |
| **sentra** | [SZLHOLDINGS/sentra](https://huggingface.co/spaces/SZLHOLDINGS/sentra) | [![sentra CI](https://github.com/szl-holdings/sentra/actions/workflows/ci.yml/badge.svg)](https://github.com/szl-holdings/sentra/actions/workflows/ci.yml) | Policy immune system — dual-use filter and egress inspection. |
| **amaru** | [SZLHOLDINGS/amaru](https://huggingface.co/spaces/SZLHOLDINGS/amaru) | [![amaru CI](https://github.com/szl-holdings/amaru/actions/workflows/ci.yml/badge.svg)](https://github.com/szl-holdings/amaru/actions/workflows/ci.yml) | Memory cortex — hash-linked DSSE receipt chain. |
| **rosie** | [SZLHOLDINGS/rosie](https://huggingface.co/spaces/SZLHOLDINGS/rosie) | [![rosie CI](https://github.com/szl-holdings/rosie/actions/workflows/ci.yml/badge.svg)](https://github.com/szl-holdings/rosie/actions/workflows/ci.yml) | Operator console — audit-grade copilot across the mesh. |
| **killinchu** | [SZLHOLDINGS/killinchu](https://huggingface.co/spaces/SZLHOLDINGS/killinchu) | [![killinchu CI](https://github.com/szl-holdings/killinchu/actions/workflows/ci.yml/badge.svg)](https://github.com/szl-holdings/killinchu/actions/workflows/ci.yml) | Sovereign defense organ — UDS-aware gate for air-gapped deployment. |

---

## 📖 Start here — the SZL Cookbook

New to the platform? The **[SZL Cookbook](https://github.com/szl-holdings/szl-cookbook)** is the
first-touch resource: 15 runnable recipes showing how to use the five flagships. The flagship
recipe — **[Verify a receipt end-to-end](https://github.com/szl-holdings/szl-cookbook/blob/main/recipes/01-verify-a-receipt-end-to-end.md)** —
cryptographically validates a real DSSE receipt in under a minute, no credentials required.

> **Customer-facing URL:** <https://github.com/szl-holdings/szl-cookbook>

### Try it now

| Try in | Link |
|---|---|
| 🤗 **Hugging Face Spaces** | [a11oy](https://huggingface.co/spaces/SZLHOLDINGS/a11oy) · [sentra](https://huggingface.co/spaces/SZLHOLDINGS/sentra) · [amaru](https://huggingface.co/spaces/SZLHOLDINGS/amaru) · [rosie](https://huggingface.co/spaces/SZLHOLDINGS/rosie) · [killinchu](https://huggingface.co/spaces/SZLHOLDINGS/killinchu) |
| ✅ **Verify a receipt** | [Recipe 01 — end-to-end, no credentials](https://github.com/szl-holdings/szl-cookbook/blob/main/recipes/01-verify-a-receipt-end-to-end.md) |
| 📦 **Signed images (GHCR)** | `cosign verify ghcr.io/szl-holdings/<flagship>:uds-v0.2.0` — keyless OIDC, Rekor-anchored |

**Used by / for:** Defense Unicorns UDS air-gapped deployments · Warhacker DoD pier demo (Jun 16–19, 2026) · Series-A diligence reviewers.

---

## Core Substrate

Runtime and formal substrate the flagships call. Not products — plumbing.

| Repo | Badge | Role |
|---|---|---|
| [**platform**](https://github.com/szl-holdings/platform) | [![platform CI](https://github.com/szl-holdings/platform/actions/workflows/ci.yml/badge.svg)](https://github.com/szl-holdings/platform/actions/workflows/ci.yml) | Monorepo — Ouroboros runtime, Lutar formulas, dual-witness adapters. Now includes `services/` (5 microservices merged 2026-06-03). |
| [**lutar-lean**](https://github.com/szl-holdings/lutar-lean) | [![lutar-lean CI](https://github.com/szl-holdings/lutar-lean/actions/workflows/ci.yml/badge.svg)](https://github.com/szl-holdings/lutar-lean/actions/workflows/ci.yml) | Lean 4 + Mathlib kernel proofs — Λ invariant, QEC, KS-18. Doctrine v11 @ `c7c0ba17`. |
| [**ouroboros**](https://github.com/szl-holdings/ouroboros) | [![ouroboros CI](https://github.com/szl-holdings/ouroboros/actions/workflows/ci.yml/badge.svg)](https://github.com/szl-holdings/ouroboros/actions/workflows/ci.yml) | Bounded recursion runtime, governance loops, and receipt emission spine. |

---

## UDS Stack

Defense Unicorns Unified Defense Stack integration — air-gapped, Zarf-native, cosign-signed.

| Repo | Role |
|---|---|
| [**szl-fleet-overlay**](https://github.com/szl-holdings/szl-fleet-overlay) | UDS fleet overlay — Package CRs, pepr policies, upstream contributions. |
| [**uds-bundles**](https://github.com/szl-holdings/uds-bundles) | Zarf bundle definitions for all 5 flagships. |
| [**szl-uds-deployment**](https://github.com/szl-holdings/szl-uds-deployment) | Deployment manifests — Pepr + Kyverno policies, k3d configs. |
| [**szl-mesh**](https://github.com/szl-holdings/szl-mesh) | Mesh spec and proto — BFT wiring, 3-of-4 quorum. |
| [**szl-lake**](https://github.com/szl-holdings/szl-lake) | Live governance data lake — audit fiber, receipt indexing, replay substrate. |

---

## Trust + Proof

| Repo | Badge | Role |
|---|---|---|
| [**khipu-consensus**](https://github.com/szl-holdings/khipu-consensus) | [![khipu CI](https://github.com/szl-holdings/khipu-consensus/actions/workflows/ci.yml/badge.svg)](https://github.com/szl-holdings/khipu-consensus/actions/workflows/ci.yml) | BFT Khipu DAG consensus — 3-of-4 threshold DSSE receipt chain. |
| [**lean-kernel**](https://github.com/szl-holdings/lean-kernel) | [![lean-kernel CI](https://github.com/szl-holdings/lean-kernel/actions/workflows/ci.yml/badge.svg)](https://github.com/szl-holdings/lean-kernel/actions/workflows/ci.yml) | Lean 4 kernel @ `c7c0ba17` — canonical locked proof state. |

---

## Docs, Brand, Customer

| Repo | Role |
|---|---|
| [**docs-site**](https://github.com/szl-holdings/docs-site) | Documentation monorepo. Now includes `developers/`, `cookbook/`, `trust/`, `investor/` (merged 2026-06-03). |
| [**szl-brand**](https://github.com/szl-holdings/szl-brand) | Brand assets — logos, tokens, typography. Includes `kit/` from former brand-kit. |
| [**.github**](https://github.com/szl-holdings/.github) | Org-wide workflows, templates, CODEOWNERS, doctrine-check. |

---

## Academic Corpus

| Repo | Role |
|---|---|
| [**szl-papers**](https://github.com/szl-holdings/szl-papers) | Academic corpus — preprints, thesis lineage, bounty problems, prior-art disclosures (consolidated 2026-06-03). |

---

## Sales

| Repo | Role |
|---|---|
| [**pitch-collateral**](https://github.com/szl-holdings/pitch-collateral) | Series-A pitch deck and investor materials (private). |

---

## Warhacker Demo

| Repo | Role |
|---|---|
| [**warhacker-demo**](https://github.com/szl-holdings/warhacker-demo) | Warhacker DoD pier demo — killinchu C-UAS live, UDS Zarf bundle, Ken agent loop. June 16–19, 2026. |

---

## What is honest right now

SZL Holdings builds a formally-verified governance gate for agentic AI. The Λ aggregator is proved in Lean 4 (Mathlib v4.13.0) against **749 declarations · 14 unique axioms · 163 tracked sorries**, lutar-lean @ `c7c0ba17`. Every gate decision emits an ECDSA P-256 DSSE-signed receipt onto a hash-linked Khipu Merkle DAG.

- **Λ uniqueness = Conjecture 1** — not a closed theorem.
- **SLSA L1 honest** — real cosign-signed provenance, Sigstore Rekor anchored.
- **Doctrine v11 LOCKED** — 749 / 14 / 163, locked at `c7c0ba17`.
- **Section 889 vendors:** Huawei, ZTE, Hytera, Hikvision, Dahua (exactly 5 — no others claimed).
- Apache-2.0 across all open-source repos.

## Citation

```bibtex
@software{szl_holdings_2026,
  author    = {Lutar, Stephen P.},
  title     = {SZL Holdings: Sovereign Governed AI --- a formally-verified governance substrate for agentic systems},
  year      = {2026},
  publisher = {Zenodo},
  version   = {Doctrine v11 LOCKED},
  doi       = {10.5281/zenodo.20434276},
  url       = {https://github.com/szl-holdings},
  note      = {749 declarations / 14 axioms / 163 sorries, kernel c7c0ba17}
}
```

---

## Built with / learned from

Our publication and documentation conventions were learned from open-source leaders — we
adapted their *patterns*, not their words. Inspired by patterns from **Polymathic AI**
([the_well](https://github.com/PolymathicAI/the_well), [walrus](https://github.com/PolymathicAI/walrus)),
**Anthropic**, **OpenAI** ([whisper](https://github.com/openai/whisper)),
**Stripe** (docs craft), Google DeepMind ([alphafold3](https://github.com/google-deepmind/alphafold3)),
Meta FAIR ([segment-anything](https://github.com/facebookresearch/segment-anything)),
EleutherAI ([lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness)),
and Hugging Face ([transformers](https://github.com/huggingface/transformers)).
We are a precision substrate, not a vibes company — the math is the load-bearing part.

---

[Founder's personal visualizations →](https://huggingface.co/betterwithage)

---

<sub>Doctrine v11 LOCKED · 749 / 14 / 163 · 🪢 Khipu chain · Lean 4 · Sigstore Rekor · Apache-2.0 OSS · DOI [10.5281/zenodo.20434276](https://doi.org/10.5281/zenodo.20434276) · 39 repos (21 active · 18 archived), consolidated 2026-06-03 for Series-A clarity · Founder: Stephen Paul Lutar Jr · [ORCID 0009-0001-0110-4173](https://orcid.org/0009-0001-0110-4173)</sub>
