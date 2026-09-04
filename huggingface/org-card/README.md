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

Frontier infrastructure for decisions that must remain bounded, inspectable,
and reproducible.

[**Enter the product**](https://a-11-oy.com) ·
[**Build from source**](https://github.com/szl-holdings) ·
[**Inspect evidence**](https://a11oy.net) ·
[**Browse the Hub**](https://huggingface.co/SZLHOLDINGS)

</div>

## Choose a path

### Understand

Start with [A11oy](https://a-11-oy.com) for the product, operating boundary,
and outcome. Review [diligence and evidence](https://a11oy.net) before relying
on a capability claim.

### Build

Use [GitHub](https://github.com/szl-holdings) for source, tests, contracts, and
quick starts. Use the [Hub](https://huggingface.co/SZLHOLDINGS) for published
models, kernels, datasets, and demonstrations.

### Verify

Inspect the [trust boundary](https://github.com/szl-holdings/.github/blob/main/TRUST.md),
exact revisions, limitations, and the
[served source binding](https://szlholdings-readme.static.hf.space/deployment.json).

## Command fabric

**A11oy** governs decisions and bounded execution.

**Khipu models** and **SZL kernels** expose their own lineage, intended use,
evaluation, compatibility, and limitation claims.

**Killinchu** is a public synthetic counter-UAS reference. Public actuation is
**SIMULATED**; no live weapon command is claimed.

**Receipt Verifier** checks scoped integrity and origin. It does not prove
truth, safety, performance, compliance, or authorization.

**SZL Lake** carries admitted evidence and data artifacts. Freshness,
completeness, jurisdiction, and source limits remain explicit.

<details>
<summary><strong>Evidence architecture</strong></summary>

<img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp"
     alt="A bounded signal path entering a verification lattice"
     width="100%" />

</details>

## Artifact contract

Evidence labels and operational state are separate. A running Space or HTTP
200 proves reachability only. Lambda uniqueness remains **Conjecture 1**.
[`SZLHOLDINGS/SZLHOLDINGS`](https://huggingface.co/datasets/SZLHOLDINGS/SZLHOLDINGS)
is a **HISTORICAL** mirror.

## Current state

[A11oy readiness](https://a-11-oy.com/api/a11oy/v1/readiness) ·
[Killinchu build](https://szlholdings-killinchu.hf.space/api/build-info) ·
[Served source](https://szlholdings-readme.static.hf.space/deployment.json)

No production authorization, regulatory approval, adoption, or investment
outcome is claimed.

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

**Understand · build · verify**

</div>
