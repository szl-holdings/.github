# SZL Holdings — a governance layer for AI systems that need cryptographic proof and honest uncertainty

> We make AI decisions you can **verify**, not just trust. Every action an AI takes leaves a signed, tamper-evident receipt — and we are honest about what we have proven versus what we are still proving.

## See It Live

Five working products, each a one-click demo — no install, no login:

| Product | What it does in one line | Try it |
|---|---|---|
| **a11oy** | Captures every AI decision as a signed receipt | [Live demo](https://huggingface.co/spaces/SZLHOLDINGS/a11oy) |
| **sentra** | Verifies every claim with cryptographic proof | [Live demo](https://huggingface.co/spaces/SZLHOLDINGS/sentra) |
| **amaru** | Reasoning that refuses to fabricate — every answer cites a real source | [Live demo](https://huggingface.co/spaces/SZLHOLDINGS/amaru) |
| **killinchu** | Edge defense with a verifiable record for every decision | [Live demo](https://huggingface.co/spaces/SZLHOLDINGS/killinchu) |
| **rosie** | Operator console that routes decisions across the mesh | [Live demo](https://huggingface.co/spaces/SZLHOLDINGS/rosie) |

![SZL Holdings live demo](https://raw.githubusercontent.com/szl-holdings/.github/main/profile/assets/hero.png)

## Why It Matters

AI is moving into decisions that carry real consequences — defense, finance, critical infrastructure — but today there is no standard way to prove *why* an AI did what it did. SZL Holdings turns every AI action into a **signed, replayable receipt**: a buyer, auditor, or regulator can independently verify the decision after the fact, on their own hardware, with public tooling. We sell the one thing the AI market still can't buy off the shelf: **proof**.

## The Shipping Artifact

Everything ships as signed container images you can verify yourself:

```bash
cosign verify ghcr.io/szl-holdings/a11oy:uds-v0.2.0 \
  --certificate-identity-regexp="^https://github.com/szl-holdings/" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com"
```

Air-gap-deployable bundles for all five products: **[uds-bundles](https://github.com/szl-holdings/uds-bundles)**.

## Status

![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)
![Demos](https://img.shields.io/badge/live_demos-5%2F5_running-2C5F2D.svg)
![Provenance](https://img.shields.io/badge/SLSA-L1_honest-2C5F2D.svg)
![Doctrine](https://img.shields.io/badge/Doctrine-v11_LOCKED-2a3550.svg "v11 LOCKED — internal stability marker")

*"Doctrine v11 LOCKED" is our internal stability marker — it means the governance kernel our claims rest on hasn't shifted under our feet, so investors and customers see consistent numbers from one week to the next.*

## Latest Math Result

Λ (our decision-aggregation rule) now has a **conditional uniqueness theorem** machine-checked on the `lutar-lean` main branch. The unconditional case remains an open problem we publish honestly as **Conjecture 1** — we do not claim it as a theorem. (Details below the fold.)

---

## Technical Depth (for engineers + math reviewers)

*This section is for those who want to verify the claims. Investors can stop reading above this line — the business case is complete.*

### Cryptographic Provenance

- **All 5 organs are SLSA Build L1 honest** (hosted GitHub Actions builder + cosign-signed images, independently verifiable via `cosign verify`). **L2 (isolated, attested build-service provenance) is roadmap via Wire D — not yet claimed. L3 not claimed.**
- Every artifact is **cosign keyless-signed** against the public Sigstore Rekor transparency log.
- Verification: `cosign verify ghcr.io/szl-holdings/<organ>:uds-v0.2.0` (organs: a11oy · sentra · amaru · killinchu · rosie).
- Every governance decision emits an **ECDSA P-256 DSSE-signed receipt** onto a hash-linked Khipu Merkle DAG.

### Mathematical Foundation

- **Governance kernel:** Doctrine v11 LOCKED — 749 declarations / 14 unique axioms / 163 tracked sorries, pinned at `lutar-lean` commit [`c7c0ba17`](https://github.com/szl-holdings/lutar-lean/commit/c7c0ba17).
- **Λ (verdict aggregator):** a *conditional* uniqueness theorem is checked on `lutar-lean` main; the *unconditional* case remains **Conjecture 1** — not a closed theorem.
- **Thesis:** [v22 — Convergence](https://github.com/szl-holdings/szl-papers/tree/main/thesis/ouroboros/papers/v22) (published) + v23 (in progress).
- **Lean 4 kernel:** [lutar-lean](https://github.com/szl-holdings/lutar-lean) — the formal math substrate (Mathlib v4.13.0).
- **Open bounty:** [Λ-Uniqueness — Conjecture 1](https://github.com/szl-holdings/lutar-lean/blob/main/BOUNTY.md), arbitrated by no-bypass CI on [lambda-bounty](https://github.com/szl-holdings/lambda-bounty).

### License & Compliance

- **Apache-2.0** for source code; **CC-BY-4.0** for papers and brand assets.
- **DCO sign-off required** on every commit.
- **Section 889** — exactly 5 vendors disclosed: Huawei, ZTE, Hytera, Hikvision, Dahua. No others claimed.
- **Honest non-claims:** no Iron Bank, no FedRAMP, no CMMC; SLSA L2/L3 are roadmap-only, not yet claimed anywhere.

### Citation

```bibtex
@software{szl_holdings_2026,
  author    = {Lutar, Stephen P.},
  title     = {SZL Holdings: a formally-grounded governance substrate for agentic AI},
  year      = {2026},
  publisher = {Zenodo},
  version   = {Doctrine v11 LOCKED},
  doi       = {10.5281/zenodo.20434276},
  url       = {https://github.com/szl-holdings},
  note      = {749 declarations / 14 axioms / 163 sorries, kernel c7c0ba17}
}
```

---

<sub>Doctrine v11 LOCKED · 749 / 14 / 163 · kernel c7c0ba17 · Λ = Conjecture 1 (not a theorem) · Apache-2.0 code / CC-BY-4.0 papers · DOI [10.5281/zenodo.20434276](https://doi.org/10.5281/zenodo.20434276) · [ORCID 0009-0001-0110-4173](https://orcid.org/0009-0001-0110-4173)</sub>

Signed-off-by: Yachay <yachay@szlholdings.ai>
