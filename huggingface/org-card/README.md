---
title: SZL — Governed AI Command Fabric
emoji: 🛡️
colorFrom: gray
colorTo: indigo
sdk: static
short_description: Governed AI routing, kernels, and verifiable outcomes.
thumbnail: https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp
pinned: true
license: apache-2.0
---

<!-- markdownlint-disable MD013 MD033 MD041 -->

<p align="center">
  <img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/estate-command-system.svg"
       alt="SZL governed AI command fabric"
       width="100%" />
</p>

# Governed AI. Inference. Command systems.

[**Product**](https://a-11-oy.com) · [**Router**](https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live) · [**Proof**](https://a11oy.net) · [**Source**](https://github.com/szl-holdings) · [**Artifacts**](https://huggingface.co/SZLHOLDINGS)

## Choose a path

**Understand:** A11oy. **Route:** SZL Router. **Explore:** SZL Atlas. **Build:** GitHub. **Verify:** the [trust boundary](https://github.com/szl-holdings/.github/blob/main/TRUST.md) and served [`deployment.json`](https://szlholdings-readme.static.hf.space/deployment.json).

## Inference flagship

<p align="center">
  <a href="https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live">
    <img src="https://raw.githubusercontent.com/szl-holdings/.github/main/profile/assets/hf-card-router.svg"
         alt="SZL Router flagship"
         width="100%" />
  </a>
</p>

### SZL Router

A source-owned OpenAI-compatible gateway with owned compute first, explicit hosted fallback, deterministic logical routes, provenance, and per-answer receipts.

[**Launch**](https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live) · [**Gateway source**](https://github.com/szl-holdings/szl-router) · [**A11oy integration**](https://a-11-oy.com/code) · [**Proof**](https://a11oy.net)

Provider credentials, private addresses, and topology are not published. A running Space does not prove every provider is configured or authorized.

## Estate map

Three commercial flagships: **A11oy, Killinchu, Forge**.

One inference flagship: **SZL Router**.

Five public domain bodies: **Terra, Killinchu, PRISM Counsel, PURIQ Finance, LYTE**.

Six internal engines: **Sentra, Lyte, Killinchu, Finance, Terra, Counsel**.

**17 public Spaces, 45 models, 34 datasets.** Portfolio authority is narrower: **16 portfolio Spaces** plus **1 inventory-only Space**.

Hub inventory is registry-only—not availability, operational readiness, or publication policy.

## Current state

Killinchu public actuation is **SIMULATED**. `SZLHOLDINGS/SZLHOLDINGS` is **HISTORICAL**. Λ uniqueness remains **Conjecture 1**. HTTP 200 is not a production certificate.

<img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp"
     alt="A bounded signal path entering a verification lattice"
     width="100%" />

## Reproduce and verify

```bash
preview_dir="$(mktemp -d)"
python .github/scripts/hf_static_space_deploy.py \
  --repo-root . \
  --manifest huggingface/org-card.manifest.json \
  --source-sha "$(git rev-parse HEAD)" \
  --materialize "$preview_dir"
python -m http.server 8000 --directory "$preview_dir"
```
