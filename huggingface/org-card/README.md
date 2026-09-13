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
       alt="SZL governed AI command fabric" width="100%" />
</p>

# Governed AI. Inference. Command systems.

[**Product**](https://a-11-oy.com) · [**Proof**](https://a11oy.net) · [**Source**](https://github.com/szl-holdings) · [**Artifacts**](https://huggingface.co/SZLHOLDINGS)

## Choose a path

**Understand:** A11oy. **Route:** SZL Router. **Explore:** SZL Atlas. **Build:** GitHub. **Verify:** the [trust boundary](https://github.com/szl-holdings/.github/blob/main/TRUST.md) and served [`deployment.json`](https://szlholdings-readme.static.hf.space/deployment.json).

<!-- SZL_LLM_ROUTER_FLAGSHIP:BEGIN -->
## SZL LLM Router · Flagship Inference Control Plane

<img src="https://raw.githubusercontent.com/szl-holdings/.github/main/profile/assets/hf-card-router.svg" alt="SZL Router flagship" width="100%" />

OpenAI-compatible `/v1/chat/completions`: owned-compute preference, explicit hosted fallback, route provenance and inspectable receipts.

`szl-auto` · `szl-fast` · `szl-large` · `szl-coder`

[**Launch**](https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live) · [**Gateway source**](https://github.com/szl-holdings/szl-router) · [**A11oy integration**](https://a-11-oy.com/code)

Runtime states: `LIVE`, `CONFIGURED_UNVERIFIED`, `OFFLINE_UNTIL_KEYED`, `UNAVAILABLE`. A running Space proves neither provider configuration nor authorization. Credentials, private addresses and topology stay private. Model output never creates execution authority.
<!-- SZL_LLM_ROUTER_FLAGSHIP:END -->

## Cyber-physical flagship: Killinchu

Counter-UAS and maritime intelligence with governed decisions and DSSE Khipu receipt evidence. Public effectors remain **SIMULATED**; human authority binds engagement.

[**Launch /elite**](https://szlholdings-killinchu.hf.space/elite) · [**Space**](https://huggingface.co/spaces/SZLHOLDINGS/killinchu) · [**Source**](https://github.com/szl-holdings/killinchu) · [**OSINT corpus**](https://huggingface.co/datasets/SZLHOLDINGS/killinchu-osint-corpus)

Inspect the Space's self-reported `/api/killinchu/v1/honest`; self-reporting is not independent qualification.

## Estate map

Commercial flagships: **A11oy, Killinchu, Forge**. Inference: **SZL Router**.

Public domains: **Terra, Killinchu, PRISM Counsel, PURIQ Finance, LYTE**.

Internal engines: **Sentra, Lyte, Killinchu, Finance, Terra, Counsel**.

**HISTORICAL estate-alignment v1:** 17 public Spaces, 45 models, 34 datasets; 16 portfolio Spaces plus one inventory-only Space.

## Current state

**21 public Spaces, 46 models, 35 datasets**, observed **2026-09-10T03:20:41Z** under anonymous public-only `hf-public-author-membership/v1`. Kernels count once as model repositories. Private assets, collections and buckets are excluded. These are registry counts—not quality, availability or production authorization.

[**Inventory binding**](https://github.com/szl-holdings/.github/blob/main/profile/public-inventory.json) · [**Admitted source manifest**](https://github.com/szl-holdings/a11oy/blob/4c6621b17ba452d5af7aa2460462fdfbe513509f/docs/huggingface-ecosystem-manifest.json)

`SZLHOLDINGS/SZLHOLDINGS` is **HISTORICAL**. Λ uniqueness remains **Conjecture 1 — open**. HTTP 200 is not a production certificate.

<img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp" alt="A bounded signal path entering a verification lattice" width="100%" />

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
