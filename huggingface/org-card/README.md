---
title: SZL — Governed AI Command Fabric
emoji: 🛡️
colorFrom: indigo
colorTo: gray
sdk: static
short_description: Trace governed AI artifacts to source and evidence.
thumbnail: https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp
pinned: true
license: apache-2.0
---

<!-- markdownlint-disable MD013 MD033 MD041 -->
<p><a href="https://huggingface.co/spaces/SZLHOLDINGS/szl-command-lab"><img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/szl-mark-holographic.svg" alt="SZL Holdings" width="144" /></a></p>

# Governed intelligence. Checkable results.

SZL Holdings builds AI software and research tools with checkable sources. Inspect each artifact's stage and use limits.

[**Explore Command Lab →**](https://huggingface.co/spaces/SZLHOLDINGS/szl-command-lab) · [**Build with the source →**](https://github.com/szl-holdings)

## Repeat a public calculation

[Input and hash](https://github.com/szl-holdings/governed-receipt-spec/tree/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell#public-data-and-attribution) → [Executed code](https://github.com/szl-holdings/governed-receipt-spec/blob/160e39b1383a0e249399b6dfb72983b67aef7fe8/examples/public-single-cell/run_example.py) → [Retained result](https://github.com/szl-holdings/governed-receipt-spec/blob/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell/observed-run.json) → [Repeat](https://github.com/szl-holdings/governed-receipt-spec/tree/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell#reproduce-the-recorded-run) → [Limits](https://github.com/szl-holdings/governed-receipt-spec/tree/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell#outputs-and-verification-boundary)

Public GEO GSE85241 example: integrity and repeatability checks, unsigned receipt, no biological or clinical claim.

## Choose a path

- **Use:** [A11oy](https://a-11-oy.com), with its current capability state.
- **Build:** [models, kernels, datasets and Spaces](https://huggingface.co/SZLHOLDINGS).
- **Verify:** [computation records](https://a11oy.net) and their stated limits.

## Inference flagship

<!-- SZL_LLM_ROUTER_FLAGSHIP:BEGIN -->
[SZL Router](https://github.com/szl-holdings/szl-router) exposes an OpenAI-compatible gateway. [Status](https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live) · [A11oy integration](https://a-11-oy.com/code) · [Route map](https://raw.githubusercontent.com/szl-holdings/.github/main/profile/assets/hf-card-router.svg). Provider availability requires separate evidence.
<!-- SZL_LLM_ROUTER_FLAGSHIP:END -->

Killinchu's public effectors remain **SIMULATED**.

## Current state

<!-- szl:public-inventory:start -->
The source-bound public inventory records **34 public Spaces, 47 model repositories, 14 native kernels, 37 datasets** at **2026-10-04T15:36:53Z** under `hf-public-author-membership/v2`. This is a dated observation, not a live count. Native kernel IDs may also appear in the model namespace; these figures do not count unique projects or trained language models. [Inventory binding](https://github.com/szl-holdings/.github/blob/main/profile/public-inventory.json) · [Exact source](https://github.com/szl-holdings/a11oy/blob/4346b821d0f971646b59fa90940af764ce59224f/docs/huggingface-ecosystem-manifest.json) · [Current Hub listing](https://huggingface.co/SZLHOLDINGS). Hub inventory is registry evidence, not availability, operational readiness, or publication policy. It does not establish model quality.
<!-- szl:public-inventory:end -->

**HISTORICAL** estate-alignment v1 described 16 portfolio Spaces and 1 inventory-only Space, with 45 models and 34 datasets. The [`SZLHOLDINGS/SZLHOLDINGS` dataset](https://huggingface.co/datasets/SZLHOLDINGS/SZLHOLDINGS) is also historical. Neither supplies current readiness.

<details>
<summary>Reproduction, provenance and portfolio details</summary>

[Architecture](https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/estate-command-system.svg).

[`deployment.json`](https://szlholdings-readme.static.hf.space/deployment.json) records the source revision. Compare its digests with the [publisher manifest](https://github.com/szl-holdings/.github/blob/main/huggingface/org-card.manifest.json). A signature proves scoped integrity and origin, never accuracy or fitness.

```bash
preview_dir="$(mktemp -d)"
python .github/scripts/hf_static_space_deploy.py --repo-root . \
  --manifest huggingface/org-card.manifest.json \
  --source-sha "$(git rev-parse HEAD)" --materialize "$preview_dir"
python -m http.server 8000 --directory "$preview_dir"
```

### Portfolio roles

- **Three commercial flagships:** A11oy, Killinchu, Forge.
- **One inference flagship:** SZL Router.
- **Five public domain bodies:** Terra, Killinchu, PRISM Counsel, PURIQ Finance, LYTE.
- **Six internal engines:** CHAPAQ (folded into Killinchu), Lyte, Killinchu, Finance, Terra, Counsel.


</details>
