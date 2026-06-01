<!-- Organization profile README — rendered at github.com/szl-holdings -->
<!-- Doctrine v7. Updated 2026-05-31 post-K10v2 lutar-lean discharge + HF strict-7 cleanup. -->

<div align="center">

# SZL Holdings

### Formally-verified governance gate for agentic AI

SZL Holdings builds a formally-verified governance gate for agentic AI. The Λ aggregator is proved in Lean 4 against **749 declarations / 14 unique axioms / 168 tracked sorries**. Every gate decision emits a DSSE-signed receipt onto a hash-linked Khipu Merkle DAG with summation-checked integrity, packaged as a UDS-deployable bundle and aligned with EU AI Act Article 12 and NIST AI RMF.

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20434276.svg)](https://doi.org/10.5281/zenodo.20434276)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-0B1F3A.svg?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)
[![Doctrine](https://img.shields.io/badge/Doctrine-v7-7c5cff?style=flat-square)](https://github.com/szl-holdings/.github/blob/main/DOCTRINE_V7.md)
[![SLSA](https://img.shields.io/badge/SLSA-L1_honest-22c55e?style=flat-square)](https://slsa.dev/spec/v1.0/levels)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0001--0110--4173-A6CE39?style=flat-square&logo=orcid&logoColor=white)](https://orcid.org/0009-0001-0110-4173)

[Hugging Face](https://huggingface.co/SZLHOLDINGS) · [Live mesh demo](https://huggingface.co/spaces/SZLHOLDINGS/uds-demo) · [Org page](https://github.com/szl-holdings)

</div>

---

## Live Hugging Face Spaces (canonical 7)

| Space | What it is | Link |
|---|---|---|
| **a11oy** | Policy + receipt substrate — every action signed, every decision gated, every receipt verifiable | [SZLHOLDINGS/a11oy](https://huggingface.co/spaces/SZLHOLDINGS/a11oy) |
| **amaru** | Cortex memory + reasoner — every inference cites its source, every memory carries its receipt; live API + DSSE-wrapped tick endpoint | [SZLHOLDINGS/amaru](https://huggingface.co/spaces/SZLHOLDINGS/amaru) |
| **sentra** | Policy immune system — deny by default, allow with proof; eight gates evaluate every action | [SZLHOLDINGS/sentra](https://huggingface.co/spaces/SZLHOLDINGS/sentra) |
| **vessels** | Packaging + supply-chain (UDS-deployable bundles, Pepr fail-CLOSED admission) | [SZLHOLDINGS/vessels](https://huggingface.co/spaces/SZLHOLDINGS/vessels) |
| **rosie** | Operator console — human-facing UI for verdicts and the live receipt stream | [SZLHOLDINGS/rosie](https://huggingface.co/spaces/SZLHOLDINGS/rosie) |
| **uds-demo** | Full mesh in one Space — Λ aggregator, Khipu Merkle DAG, EU AI Act Article 12 + NIST AI RMF alignment | [SZLHOLDINGS/uds-demo](https://huggingface.co/spaces/SZLHOLDINGS/uds-demo) |
| **README** | Org card — character showcase + organ anatomy | [SZLHOLDINGS/README](https://huggingface.co/spaces/SZLHOLDINGS/README) |

---

## Active repositories (governance substrate)

| Repo | Role |
|---|---|
| [`a11oy`](https://github.com/szl-holdings/a11oy) | Policy + receipt substrate (TypeScript packages, MCP server) |
| [`amaru`](https://github.com/szl-holdings/amaru) | Cortex memory + reasoner (FastAPI, 7-chakra runtime) |
| [`sentra`](https://github.com/szl-holdings/sentra) | Immune / red-team (egress inspector + tripwires, Wire B live) |
| [`vessels`](https://github.com/szl-holdings/vessels) | UDS packaging (Zarf, Pepr admission controller, cosign signing) |
| [`rosie`](https://github.com/szl-holdings/rosie) | Operator console + receipt stream UI (Wire C live) |
| [`lutar-lean`](https://github.com/szl-holdings/lutar-lean) | Lean 4 + Mathlib proofs of the Λ aggregator |
| [`platform`](https://github.com/szl-holdings/platform) | Composing monorepo for the substrate runtime |
| [`du-upstream-contributions`](https://github.com/szl-holdings/du-upstream-contributions) | Upstream patches to Defense Unicorns UDS (Pepr fail-CLOSED, etc.) |
| [`szl-trust`](https://github.com/szl-holdings/szl-trust) | Trust tier specs + compliance documentation |
| [`uds-mesh`](https://github.com/szl-holdings/uds-mesh) | UDS span schemas + governance receipts |
| [`agi-forecast`](https://github.com/szl-holdings/agi-forecast) | PAC-Bayes governance trajectory forecasts |
| [`ouroboros`](https://github.com/szl-holdings/ouroboros) | Bounded-recursion runtime |
| [`ouroboros-thesis`](https://github.com/szl-holdings/ouroboros-thesis) | DOI-pinned thesis substrate |
| [`szl-cookbook`](https://github.com/szl-holdings/szl-cookbook) | Governed-AI recipes |
| [`szl-brand`](https://github.com/szl-holdings/szl-brand) | Visual doctrine + anatomy |
| [`vsp-otel`](https://github.com/szl-holdings/vsp-otel) | OpenTelemetry exporter for Λ-axis spans |

---

## What is honest right now

- **Formal proof posture:** 749 declarations, 14 unique axioms (15 raw, 1 duplicate), 168 tracked sorries on `lutar-lean@main`. Λ uniqueness is currently a **Conjecture**, not a closed theorem — it depends on a CAUCHY_ND sorry and a missing symmetry axiom.
- **Receipts:** DSSE envelopes ship from the amaru tick endpoint today. Sigstore CI wiring is **pending** — signature fields are honestly labeled as "PLACEHOLDER — signing not yet wired into CI".
- **Wires:** Wire B (a11oy ↔ sentra immune) and Wire C (a11oy ↔ rosie receipt stream) are LIVE on `main`. Wire D (W3C traceparent across the mesh) is **not yet implemented**.
- **SLSA:** Honest L1 (was previously claimed as L3; corrected in platform PR #235).
- **Compliance:** Aligned with EU AI Act Article 12 (record-keeping for high-risk AI systems) and NIST AI RMF (MANAGE function).

---

## Operating doctrine

- **Doctrine v7** — language hygiene + banned identity tokens enforced by CI grep
- **Watunakuy** — testing discipline (Four Strikes · Five Boots · Five Passes)
- **Zero-Bandaid Law** — every output must survive Series-A diligence read

Full spec: [DOCTRINE_V7.md](https://github.com/szl-holdings/.github/blob/main/DOCTRINE_V7.md)

---

## Founder guides

Step-by-step Word guides to stand the ecosystem up from zero:

- **Environment Setup Guide** — hardware to buy, tools to install (with links), accounts, secret keys, 10-step first-time setup: [docs/SZL_ENVIRONMENT_SETUP_GUIDE.docx](https://github.com/szl-holdings/.github/blob/main/docs/SZL_ENVIRONMENT_SETUP_GUIDE.docx)
- **UDS Run Guide** — sign bundles, build Zarf, k3d deploy, verify, Warhacker demo script, founder action queue: [docs/SZL_UDS_RUN_GUIDE.docx](https://github.com/szl-holdings/.github/blob/main/docs/SZL_UDS_RUN_GUIDE.docx)
- Mirrored on Hugging Face: [SZLHOLDINGS/doctrine-v10-v11](https://huggingface.co/datasets/SZLHOLDINGS/doctrine-v10-v11) under `founder-guides/`

---

## Contact

- Founder: Stephen P. Lutar Jr. · [stephen@szlholdings.com](mailto:stephen@szlholdings.com) · ORCID [0009-0001-0110-4173](https://orcid.org/0009-0001-0110-4173)
- Security: [`security@szlholdings.com`](mailto:security@szlholdings.com) · [security policy](https://github.com/szl-holdings/.github/security/policy)
- Citation: [CITATION.cff](https://github.com/szl-holdings/.github/blob/main/CITATION.cff) · DOI [10.5281/zenodo.20434276](https://doi.org/10.5281/zenodo.20434276)

---

<sub>© 2026 SZL Holdings · Apache-2.0 · Doctrine v7 · Updated 2026-05-31 post-K10v2 + HF strict-7 cleanup</sub>
