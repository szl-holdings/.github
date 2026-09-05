---
title: SZL — Governed AI Command Fabric
emoji: 🛡️
colorFrom: gray
colorTo: indigo
sdk: static
short_description: Governed AI, inference, kernels, and verifiable outcomes.
thumbnail: https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp
pinned: true
license: apache-2.0
---

<!-- markdownlint-disable MD013 MD033 MD041 -->

<p align="center">
  <img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/estate-command-system.svg"
       alt="SZL governed AI command fabric with a pixel-built mark, holographic evidence chamber, and clear paths to understand, build, and verify"
       width="100%" />
</p>

<div align="center">

# Governed AI. Inference. Command systems.

Bounded, inspectable, reproducible.

[**Enter the product**](https://a-11-oy.com) ·
[**Explore SZL Atlas**](https://huggingface.co/spaces/SZLHOLDINGS/szl-command-lab) ·
[**Inspect evidence**](https://a11oy.net) ·
[**Build from source**](https://github.com/szl-holdings)

</div>

## Choose a path

### Understand

Start with [A11oy](https://a-11-oy.com) for the product, operating boundary,
and outcome. Review [diligence and evidence](https://a11oy.net) before relying
on a capability claim.

### Explore

[**SZL Atlas**](https://huggingface.co/spaces/SZLHOLDINGS/szl-command-lab)
maps models, kernels, datasets, Spaces, source links, and evidence boundaries.

[Models](https://huggingface.co/SZLHOLDINGS/models) ·
[Kernels](https://huggingface.co/SZLHOLDINGS/kernels) ·
[Datasets](https://huggingface.co/SZLHOLDINGS/datasets) ·
[Spaces](https://huggingface.co/SZLHOLDINGS/spaces) ·
[Collections](https://huggingface.co/SZLHOLDINGS/collections)

### Build

Use [GitHub](https://github.com/szl-holdings) for source, tests, contracts, and
quick starts. Each published artifact owns its lineage, intended use,
evaluation, compatibility, and limitations.

### Verify

Inspect the [trust boundary](https://github.com/szl-holdings/.github/blob/main/TRUST.md),
exact revisions, limitations, and the
[served source binding](https://szlholdings-readme.static.hf.space/deployment.json).

## Estate map

Three commercial flagships: A11oy,Killinchu,Forge. Five public domain bodies:
Terra,Killinchu,PRISM Counsel,PURIQ Finance,LYTE. Six internal engines:
Sentra,Lyte,Killinchu,Finance,Terra,Counsel.

**17 portfolio Spaces · 45 models · 34 datasets.**

Hub inventory is registry-only—not availability, operational readiness, or
publication policy. KEEP authority:
[`docs/CANONICAL_FLEET.md`](https://github.com/szl-holdings/.github/blob/main/docs/CANONICAL_FLEET.md).

## Command fabric

**A11oy** governs decisions and bounded execution. **Khipu models** and
**SZL kernels** provide portable reasoning and compute primitives.

**Killinchu** is a public synthetic counter-UAS reference. Public actuation is
**SIMULATED**; no live weapon command is claimed.

**Receipt Verifier** checks scoped integrity and origin. It does not prove
truth, safety, performance, compliance, or authorization.

<details>
<summary><strong>Evidence architecture</strong></summary>

<img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp"
     alt="A bounded signal path entering a verification lattice"
     width="100%" />

</details>

## Artifact contract

A running Space, public listing, download count, or HTTP 200 proves neither
readiness nor superiority. Lambda uniqueness remains **Conjecture 1**.
[`SZLHOLDINGS/SZLHOLDINGS`](https://huggingface.co/datasets/SZLHOLDINGS/SZLHOLDINGS)
is a **HISTORICAL** mirror.

## Current state

[Atlas health](https://szlholdings-szl-command-lab.hf.space/healthz) ·
[Live catalog](https://szlholdings-szl-command-lab.hf.space/api/catalog) ·
[Atlas source binding](https://szlholdings-szl-command-lab.hf.space/api/build-info) ·
[A11oy readiness](https://a-11-oy.com/api/a11oy/v1/readiness)

No production authorization or approval is claimed.

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

---

<div align="center">

**Understand · explore · build · verify**

</div>
