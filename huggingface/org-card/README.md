---
title: SZL — Governed AI Command Fabric
emoji: 🛡️
colorFrom: gray
colorTo: indigo
sdk: static
short_description: Governed AI, inference routing, kernels, and verifiable outcomes.
thumbnail: https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp
pinned: true
license: apache-2.0
---

<!-- markdownlint-disable MD013 MD033 MD041 -->

<p align="center">
  <img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/estate-command-system.svg"
       alt="SZL governed AI command fabric with bounded paths to understand, build, route, and verify"
       width="100%" />
</p>

<div align="center">

# Governed AI. Inference. Command systems.

Bounded, inspectable, reproducible.

[**Enter the product**](https://a-11-oy.com) ·
[**Open the router**](https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live) ·
[**Inspect evidence**](https://a11oy.net) ·
[**Build from source**](https://github.com/szl-holdings) ·
[**Browse artifacts**](https://huggingface.co/SZLHOLDINGS)

</div>

## Choose a path

**Understand.** Start with [A11oy](https://a-11-oy.com) for the product and operating boundary.

**Route.** [SZL Router](https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live) is the inference flagship: one OpenAI-compatible gateway, owned compute first, bounded hosted fallback, and a receipt for every routed answer.

**Explore.** [SZL Atlas](https://huggingface.co/spaces/SZLHOLDINGS/szl-command-lab) maps models, kernels, datasets, Spaces, source links, and evidence boundaries.

**Build.** Use [GitHub](https://github.com/szl-holdings) for source, tests, contracts, and quick starts.

**Verify.** Inspect the [trust boundary](https://github.com/szl-holdings/.github/blob/main/TRUST.md), exact revisions, limitations, and [served source binding](https://szlholdings-readme.static.hf.space/deployment.json).

## Inference flagship

<p align="center">
  <a href="https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live">
    <img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/hf-card-router.svg"
         alt="SZL Router flagship connecting owned compute, bounded hosted fallback, and receipt verification"
         width="100%" />
  </a>
</p>

### SZL Router

A source-owned, OpenAI-compatible routing gateway with deterministic logical routes, explicit provider admission, bounded failover, provenance, and signed receipts when a persistent signing key is armed.

[**Launch the public Space**](https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live) ·
[**Inspect the gateway source**](https://github.com/szl-holdings/szl-router) ·
[**Open the A11oy integration**](https://a-11-oy.com/code) ·
[**Review proof and bounds**](https://a11oy.net)

The public Space exposes redacted status, source binding, and receipt evidence. Provider credentials, internal addresses, and private topology are not published. A running Space is not proof that every provider or model is configured, reachable, performant, compliant, or authorized.

## Estate map

Three commercial flagships: **A11oy, Killinchu, Forge**.

One inference flagship: **SZL Router**.

Five public domain bodies: **Terra, Killinchu, PRISM Counsel, PURIQ Finance, LYTE**.

Six internal engines: **Sentra, Lyte, Killinchu, Finance, Terra, Counsel**.

**17 public Spaces, 45 models, 34 datasets.**

Portfolio authority is narrower: **16 portfolio Spaces** plus **1 inventory-only Space**, Yarqa, with `governedKeep=false` and disposition `FOLD`.

Hub inventory is registry-only—not availability, operational readiness, or publication policy. KEEP authority: [`docs/CANONICAL_FLEET.md`](https://github.com/szl-holdings/.github/blob/main/docs/CANONICAL_FLEET.md).

## Command fabric

A11oy governs decisions and bounded execution. SZL Router owns the gateway and routing evidence. Khipu models and SZL kernels provide portable reasoning and compute primitives.

The source chain is:

```text
GitHub source → Hugging Face runtime mirror → A11oy product integration → a11oy.net proof
```

Killinchu is a public synthetic counter-UAS reference. Public actuation is **SIMULATED**; no live weapon command is claimed.

Receipt Verifier checks scoped integrity and origin. It does not prove truth, safety, performance, compliance, or authorization.

<img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp"
     alt="A bounded signal path entering a verification lattice"
     width="100%" />

## Current state

Lambda uniqueness remains **Conjecture 1**. [`SZLHOLDINGS/SZLHOLDINGS`](https://huggingface.co/datasets/SZLHOLDINGS/SZLHOLDINGS) is a **HISTORICAL** mirror. A running Space, public listing, download count, or HTTP 200 is not a production certificate. No production authorization or approval is claimed.

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

**Understand · route · explore · build · verify**

</div>
