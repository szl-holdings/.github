<!--
  SZL Holdings — organization profile README (szl-holdings/.github -> profile/README.md)
  Investor-readable rewrite · 2026-06-30 · Honesty doctrine LOCKED.
  Canonical numbers (source of truth: lutar-lean@main, kernel c7c0ba17):
    Locked-proven (kernel-verified) = EXACTLY 8 formulas {F1, F4, F7, F11, F12, F18, F19, F22}
    ~185 machine-checked Lean theorems total (Waves 11–23)
    Lambda-uniqueness = Conjecture 1 (unconditional uniqueness machine-checked FALSE; conditional Theorem U proven, axiom-free)
    Khipu BFT safety = Conjecture 2 (Wave23 conditional only)
    SLSA posture = L1 honest · L2 build-attested · L3 roadmap. No FedRAMP/ATO without "roadmap".
  NOT accredited. Sign-off: Stephen Lutar <stephenlutar2@gmail.com>. DCO + Conventional Commits.
-->

<div align="center">

<img src="https://raw.githubusercontent.com/szl-holdings/.github/main/profile/assets/banner-org.png" alt="SZL Holdings — Governed AI you can prove." width="100%" />

# SZL Holdings

### Every AI decision comes with a signed, machine-verifiable receipt.

[![locked-proven](https://img.shields.io/badge/locked--proven-8%20formulas-c9b787?style=flat-square)](https://github.com/szl-holdings/lutar-lean)
[![Lean 4](https://img.shields.io/badge/Lean%204-machine--checked-5fb3a3?style=flat-square)](https://github.com/szl-holdings/lutar-lean)
[![Λ](https://img.shields.io/badge/%CE%9B-Conjecture%201%20%C2%B7%20Theorem%20U%20conditional-B79BD6?style=flat-square)](https://github.com/szl-holdings/lutar-lean/blob/main/BOUNTY.md)
[![Zenodo DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.19944926-01696F?style=flat-square)](https://doi.org/10.5281/zenodo.19944926)
[![Rekor](https://img.shields.io/badge/cosign-keyless%20%C2%B7%20public%20Rekor-5fb3a3?style=flat-square)](https://search.sigstore.dev/)
[![License](https://img.shields.io/badge/code-Apache--2.0-5fb3a3?style=flat-square)](https://github.com/szl-holdings)

</div>

---

## What we do

Modern AI makes consequential decisions — in defense, finance, and critical operations — with no way to verify afterward what it decided, why, or whether the record was changed.

SZL closes that gap. We build a **governance substrate**: a layer that sits between an AI model and its actions, forcing every decision through a policy check, binding it to evidence, scoring it with a trust function, and sealing it into a **cryptographically signed receipt** anyone can verify offline. Think of it as a flight recorder for AI — one that can't be quietly edited after the fact.

The trust math is pinned in **Lean 4** and checked by a proof machine. We publish exactly what is proven, what remains a conjecture, and where the guarantees stop. That discipline is the moat.

---

## The flagship — a11oy

**[a11oy](https://a-11-oy.com)** is SZL's governed-AI Command Center. One interface for ask-and-act: deny-by-default safety gates, trust scoring, a live decision feed, and a signed receipt for every action.

- Every request passes through five transparent classifiers. Declined requests return a signed receipt naming the exact rule that fired — nothing is hidden.
- The trust ceiling is **0.97** by doctrine — never claimed at 100%.
- Deployable on your own hardware, air-gapped. No cloud dependency required.

**[Open a11oy →](https://a-11-oy.com)** · **[Try on Hugging Face →](https://huggingface.co/spaces/SZLHOLDINGS/a11oy)**

---

## Defense vertical — counter-UAS governance

We apply the same governance substrate to autonomous systems in the field. Our counter-UAS and maritime command tool provides live tracking, multi-sensor fusion, maritime vessel screening (sanctions + dark-vessel detection), engagement rules, and **signed engagement receipts** — so every governance decision is verifiable, not just auditable in principle.

**[See the live demo →](https://szlholdings-killinchu.hf.space/elite)**

> The governance loop is real. The effector link is a demonstrated simulation — labeled honestly as a command demonstration, not a live engagement.

---

## The proof — honest and checkable

We do not claim "formally verified." We claim something narrower and more useful: **specific theorems, locked in a proof kernel, that underwrite specific runtime guarantees.**

| What is proven | Status |
|---|---|
| **8 formulas locked-proven** in the Lean 4 kernel — receipt replay, DAG acyclicity, FIFO ordering, ledger conservation, bounded coupling, Reed–Solomon recovery, entropy budget, append-only monotonicity | **LOCKED · kernel c7c0ba17** |
| ~185 machine-checked theorems (Waves 11–23) | **CI-verified · not in the locked 8** |
| Λ uniqueness under separability assumption (Theorem U) | **PROVEN axiom-free** |
| Λ unconditional uniqueness | **Conjecture 1 — machine-checked false** (we found a counterexample and publish it) |
| Signed DSSE receipts on every governed decision | **LIVE · ECDSA-P256** |
| Public Rekor transparency log entry | **LIVE** |
| FedRAMP / ATO / CMMC / Iron Bank | **ROADMAP — not claimed today** |

Thesis and DOI: **[Zenodo 10.5281/zenodo.19944926](https://doi.org/10.5281/zenodo.19944926)**

Verify a receipt yourself:
```bash
curl -s https://szlholdings-killinchu.hf.space/cosign.pub -o cosign.pub
curl -s https://szlholdings-killinchu.hf.space/api/killinchu/v1/receipt/export > receipt.json
# Tamper one byte → "Verification failure"
```

---

## Where to start

| If you want to… | Go to |
|---|---|
| **Try the Command Center** | [a-11-oy.com](https://a-11-oy.com) · [Hugging Face Space](https://huggingface.co/spaces/SZLHOLDINGS/a11oy) |
| **See the defense demonstration** | [killinchu live demo](https://szlholdings-killinchu.hf.space/elite) |
| **Read the math** | [lutar-lean](https://github.com/szl-holdings/lutar-lean) · [Zenodo DOI](https://doi.org/10.5281/zenodo.19944926) |
| **Build on it** | [developers](https://github.com/szl-holdings/developers) · [szl-cookbook](https://github.com/szl-holdings/szl-cookbook) |
| **Verify the chain** | [szl-trust](https://github.com/szl-holdings/szl-trust) · [szl-lake](https://github.com/szl-holdings/szl-lake) |
| **Read the doctrine** | [szl-doctrine](https://github.com/szl-holdings/szl-doctrine) · [szl-papers](https://github.com/szl-holdings/szl-papers) |

---

## Work with us

We are looking for design partners, independent auditors, and engineers who care about provable AI governance.

**[stephen@szlholdings.com](mailto:stephen@szlholdings.com)**

---

<div align="center">

Built by **Stephen P. Lutar Jr.** · Honest by design · [a-11-oy.com](https://a-11-oy.com) · [🤗 SZLHOLDINGS](https://huggingface.co/SZLHOLDINGS) · [github.com/szl-holdings](https://github.com/szl-holdings)

<sub>Not affiliated with Defense Unicorns · SZL mark USPTO Serial 99831122 · No production ATO claimed · SLSA L1 honest · L2 build-attested · L3 roadmap · Λ = Conjecture 1 · trust never 100%</sub>

</div>
