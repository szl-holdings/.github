---
title: SZL — Governed AI Command Fabric
emoji: 🛡️
colorFrom: gray
colorTo: indigo
sdk: static
short_description: Governed AI, inference, kernels, and verifiable outcomes.
thumbnail: https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/szl-command-fabric-v3.svg
pinned: true
license: apache-2.0
---

<!-- markdownlint-disable MD013 MD033 MD041 -->

<p align="center">
  <img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/szl-command-fabric-v3.svg"
       alt="SZL governed AI command fabric with a pixel-built mark, holographic evidence chamber, and paths to understand, build, and verify"
       width="100%" />
</p>

<div align="center">

# Governed AI. Inference. Command systems.

Frontier infrastructure for decisions that must remain bounded, inspectable,
and reproducible.

[**Enter the product**](https://a-11-oy.com) ·
[**Build from source**](https://github.com/szl-holdings) ·
[**Inspect the evidence**](https://a11oy.net) ·
[**Browse the Hub**](https://huggingface.co/SZLHOLDINGS)

</div>

## Choose a path

| You are here to… | Start here | Verify here |
| --- | --- | --- |
| **Understand** the company, products, and operating boundaries | [a-11-oy.com](https://a-11-oy.com) | [Diligence and evidence](https://a11oy.net) |
| **Build** with source, models, kernels, datasets, and demonstrations | [GitHub source](https://github.com/szl-holdings) | [Hub artifacts](https://huggingface.co/SZLHOLDINGS) |
| **Review** exact revisions, limitations, and receipts | [Trust boundary](https://github.com/szl-holdings/.github/blob/main/TRUST.md) | [Served source binding](https://szlholdings-readme.static.hf.space/deployment.json) |

## Command fabric

```text
signal → reason → policy → bounded action → receipt → independent verification
                     ↑                                      │
                     └──────────── evidence loop ────────────┘
```

| Surface | Role | Public boundary |
| --- | --- | --- |
| [**A11oy**](https://a-11-oy.com) | Governed decision and execution fabric | Product origin; source and live state must be checked separately |
| [**Khipu model family**](https://huggingface.co/SZLHOLDINGS/SZL-Khipu-1.5B) | Compact model artifacts and governed reasoning experiments | Each model card governs its own lineage, evaluation, and intended-use claims |
| [**SZL kernels**](https://huggingface.co/SZLHOLDINGS/szl-kernels) | Reproducible compute and inference primitives | Publication does not establish benchmark superiority or production suitability |
| [**Killinchu**](https://huggingface.co/spaces/SZLHOLDINGS/killinchu) | Public synthetic counter-UAS reference | Public actuation is **SIMULATED**; no live weapon command is claimed |
| [**Receipt verifier**](https://huggingface.co/spaces/SZLHOLDINGS/governed-receipt-verifier) | Independent receipt inspection and replay | Verification proves scoped integrity and origin, not truth or authorization |
| [**SZL Lake**](https://huggingface.co/datasets/SZLHOLDINGS/szl-lake) | Admitted public evidence and data artifacts | Freshness, completeness, jurisdiction, and source limitations remain explicit |

## Artifact contract

A polished card is navigation—not evidence. Every consequential artifact should
identify its exact source, revision, license, intended use, known limitations,
and evaluation or benchmark evidence when that evidence exists.

- Evidence labels use **PROVED**, **MEASURED**, **REPORTED**, **MODELED**,
  **CONJECTURE**, **ROADMAP**, **UNKNOWN**, or **UNAVAILABLE**.
- Operational state is separate: **OPERATIONAL**, **PARTIAL**, **DEGRADED**,
  **UNAVAILABLE**, or **HISTORICAL**.
- A running Space or HTTP 200 proves reachability only.
- A signature establishes scoped integrity and origin; it does not establish
  accuracy, safety, compliance, performance, or authorization to deploy.
- Lambda uniqueness remains **Conjecture 1**, not a theorem.
- [`SZLHOLDINGS/SZLHOLDINGS`](https://huggingface.co/datasets/SZLHOLDINGS/SZLHOLDINGS)
  is a **HISTORICAL** mirror, not the current inventory or runtime source.

## Current state

[Served source](https://szlholdings-readme.static.hf.space/deployment.json) ·
[A11oy readiness](https://a-11-oy.com/api/a11oy/v1/readiness) ·
[Killinchu build](https://szlholdings-killinchu.hf.space/api/build-info)

Links and runtime state can change. This card does not claim production
authorization, regulatory approval, customer adoption, or an investment outcome.

## Reproduce and verify

The canonical card source is
[`szl-holdings/.github`](https://github.com/szl-holdings/.github/tree/main/huggingface/org-card).
The published Space exposes the exact GitHub revision through
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

**Understand · build · verify**

</div>
