---
title: SZL Holdings — Governed Decision Infrastructure
emoji: 🛡️
colorFrom: gray
colorTo: indigo
sdk: static
short_description: Control before action. Evidence after.
thumbnail: https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp
pinned: true
license: apache-2.0
---

<!-- markdownlint-disable MD013 MD033 MD041 -->

<p align="center">
  <img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp"
       alt="A bounded signal path entering a holographic verification lattice"
       width="100%" />
</p>

<div align="center">

# Control before action. Evidence after.

Models, kernels, and demonstrations that act within authority and leave
inspectable evidence. Cut like a house, not a dump.

[**Open a11oy**](https://a-11-oy.com) ·
[**Verify evidence**](https://a11oy.net) ·
[**Killinchu**](https://huggingface.co/spaces/SZLHOLDINGS/killinchu) ·
[**View source**](https://github.com/szl-holdings)

</div>

## Four paths

### 01 / Command

[**a11oy**](https://huggingface.co/spaces/SZLHOLDINGS/a11oy) — governed
inference and bounded action with portable receipts.

### 02 / Intelligence

[**Killinchu**](https://huggingface.co/spaces/SZLHOLDINGS/killinchu) — public
observation, fusion, and operator-decision workflows. Public feeds may be live
or unavailable; samples remain labeled. Effectors and public actuation are
**SIMULATED**. This Space does not command a live weapon or establish
production authorization.

### 03 / Models + kernels

Ready-to-wear (weights exist, proposal-only):
[**Khipu 1.5B**](https://huggingface.co/SZLHOLDINGS/SZL-Khipu-1.5B),
[**Forge ReceiptAgent**](https://huggingface.co/SZLHOLDINGS/SZL-Forge-1.5B-ReceiptAgent),
[**ReceiptAgent 0.8B**](https://huggingface.co/SZLHOLDINGS/szl-receiptagent-qwen35-0.8b-v2),
[**szl-kernels**](https://huggingface.co/SZLHOLDINGS/szl-kernels).

Fall 2026 collection (**CUTTING** — cards only, no weights yet):
[**KHIPU-R2**](https://huggingface.co/SZLHOLDINGS/KHIPU-R2),
[**WILLAY**](https://huggingface.co/SZLHOLDINGS/WILLAY),
[**KILLINCHU-EYE**](https://huggingface.co/SZLHOLDINGS/KILLINCHU-EYE),
[**YARQA-ATTN**](https://huggingface.co/SZLHOLDINGS/YARQA-ATTN),
[**A11OY-MINI**](https://huggingface.co/SZLHOLDINGS/A11OY-MINI).

Admitted evidence lives in [**szl-lake**](https://huggingface.co/datasets/SZLHOLDINGS/szl-lake).
Gucci rule: silhouette from the runway, original SZL cut. We do not relabel
someone else's weights.

### 04 / Evidence

[**Receipt verifier**](https://huggingface.co/spaces/SZLHOLDINGS/governed-receipt-verifier)
supports replay. [**SZL Kernels**](https://huggingface.co/SZLHOLDINGS/szl-kernels)
publishes source-bound runtime artifacts.

> A running Space proves reachability, not capability. A signature establishes
> integrity and origin within scope—not accuracy, safety, or authorization.

<details>
<summary><strong>Artifact and truth contract</strong></summary>

- **Weights and adapters** require lineage, hashes, evaluation, and an autonomy
  boundary.
- **Software and substrate**, **surrogates and recipes**, **datasets and
  evidence**, and **Spaces and demonstrations** remain explicitly classified;
  repository type does not redefine them.
- Claims use **PROVED**, **MEASURED**, **REPORTED**, **MODELED**,
  **CONJECTURE**, or **ROADMAP**. Runtime state is separate:
  **OPERATIONAL**, **PARTIAL**, **DEGRADED**, **UNAVAILABLE**, or
  **HISTORICAL**.
- Lambda uniqueness remains **Conjecture 1**, not a theorem.
- [`SZLHOLDINGS/SZLHOLDINGS`](https://huggingface.co/datasets/SZLHOLDINGS/SZLHOLDINGS)
  is a **HISTORICAL profile mirror**, not a current organization card,
  inventory, or runtime source.

</details>

## Current state

[Served source](https://szlholdings-readme.static.hf.space/deployment.json) ·
[a11oy readiness](https://a-11-oy.com/api/a11oy/v1/readiness) ·
[Killinchu build](https://szlholdings-killinchu.hf.space/api/build-info) ·
[Public-risk status](https://szlholdings-killinchu.hf.space/api/public-risk-status) ·
[Killinchu readiness](https://szlholdings-killinchu.hf.space/api/killinchu/readyz)

Links change. No authorization, approval, adoption, or investment outcome is
claimed.

## Reproduce and verify

Source: [`szl-holdings/.github`](https://github.com/szl-holdings/.github/tree/main/huggingface/org-card).
The Space exposes its exact GitHub revision at
[`deployment.json`](https://szlholdings-readme.static.hf.space/deployment.json).

```bash
preview_dir="$(mktemp -d)"
python .github/scripts/hf_static_space_deploy.py \
  --repo-root . \
  --manifest huggingface/org-card.manifest.json \
  --source-sha "$(git rev-parse HEAD)" \
  --materialize "$preview_dir"
python -m http.server 8000 --directory "$preview_dir"
```

[Security](https://github.com/szl-holdings/.github/security/policy) ·
[Trust](https://github.com/szl-holdings/.github/blob/main/TRUST.md) ·
[Support](https://github.com/szl-holdings/.github/blob/main/SUPPORT.md) ·
[Limitations](./HONEST_DISCLOSURE.md) ·
[Hugging Face organization](https://huggingface.co/SZLHOLDINGS)

---

<div align="center">

**Govern · execute · prove**

</div>
