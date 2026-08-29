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

Models, kernels, data, and demonstrations that operate within authority and
leave inspectable evidence.

[**Open a11oy**](https://a-11-oy.com) ·
[**Verify evidence**](https://a11oy.net) ·
[**Killinchu**](https://huggingface.co/spaces/SZLHOLDINGS/killinchu) ·
[**Source**](https://github.com/szl-holdings)

</div>

## Four paths

### 01 / Command

[**a11oy**](https://huggingface.co/spaces/SZLHOLDINGS/a11oy) provides governed
inference, bounded action, and portable receipts.

### 02 / Intelligence

[**Killinchu**](https://huggingface.co/spaces/SZLHOLDINGS/killinchu) supports
public observation, fusion, and operator decisions. Feeds may be live or
unavailable; samples remain labeled. Effectors and public actuation are
**SIMULATED**. The Space does not command a live weapon or establish production
authorization.

### 03 / Models + kernels

Ready-to-wear—weights exist, proposal-only:
[**Khipu 1.5B**](https://huggingface.co/SZLHOLDINGS/SZL-Khipu-1.5B),
[**Forge ReceiptAgent**](https://huggingface.co/SZLHOLDINGS/SZL-Forge-1.5B-ReceiptAgent),
[**ReceiptAgent 0.8B**](https://huggingface.co/SZLHOLDINGS/szl-receiptagent-qwen35-0.8b-v2),
and [**szl-kernels**](https://huggingface.co/SZLHOLDINGS/szl-kernels).

Fall 2026—**CUTTING**, cards only, no weights:
[**KHIPU-R2**](https://huggingface.co/SZLHOLDINGS/KHIPU-R2),
[**WILLAY**](https://huggingface.co/SZLHOLDINGS/WILLAY),
[**KILLINCHU-EYE**](https://huggingface.co/SZLHOLDINGS/KILLINCHU-EYE),
[**YARQA-ATTN**](https://huggingface.co/SZLHOLDINGS/YARQA-ATTN), and
[**A11OY-MINI**](https://huggingface.co/SZLHOLDINGS/A11OY-MINI).

Admitted evidence lives in
[**szl-lake**](https://huggingface.co/datasets/SZLHOLDINGS/szl-lake).
We use public research as inspiration while preserving original SZL
implementations and lineage; third-party weights are never relabeled.

### 04 / Evidence

[**Receipt verifier**](https://huggingface.co/spaces/SZLHOLDINGS/governed-receipt-verifier)
supports replay. A running Space proves reachability, not capability; a
signature establishes scoped integrity and origin, not accuracy, safety, or
authorization.

<details>
<summary><strong>Artifact and truth contract</strong></summary>

- Weights require lineage, hashes, evaluation, and an autonomy boundary.
- Claims use PROVED, MEASURED, REPORTED, MODELED, CONJECTURE, or ROADMAP.
- Lambda uniqueness remains Conjecture 1, not a theorem.
- [`SZLHOLDINGS/SZLHOLDINGS`](https://huggingface.co/datasets/SZLHOLDINGS/SZLHOLDINGS)
  is a **HISTORICAL** mirror, not the current card, inventory, or runtime source.

</details>

## Current state

[Served source](https://szlholdings-readme.static.hf.space/deployment.json) ·
[a11oy readiness](https://a-11-oy.com/api/a11oy/v1/readiness) ·
[Killinchu build](https://szlholdings-killinchu.hf.space/api/build-info)

Links change. No authorization, approval, adoption, or investment outcome is
claimed.

## Reproduce and verify

Source:
[`szl-holdings/.github`](https://github.com/szl-holdings/.github/tree/main/huggingface/org-card).
The Space exposes its exact GitHub revision through
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
[Limitations](./HONEST_DISCLOSURE.md) ·
[Hugging Face organization](https://huggingface.co/SZLHOLDINGS)

---

<div align="center">

**Govern · execute · prove**

</div>
