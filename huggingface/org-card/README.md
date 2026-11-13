---
title: SZL — Governed AI Command Fabric
emoji: 🛡️
colorFrom: indigo
colorTo: gray
sdk: static
app_file: index.html
short_description: Trace governed AI artifacts to source and evidence.
thumbnail: https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp
pinned: true
license: apache-2.0
---

<!-- markdownlint-disable MD013 MD033 MD041 -->
<p><a href="https://huggingface.co/spaces/SZLHOLDINGS/szl-command-lab"><img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/szl-mark-holographic.svg" alt="SZL Holdings" width="144" /></a></p>

# Governed intelligence. Checkable results.

SZL Holdings builds source-traceable AI research software.

[**Explore Command Lab**](https://huggingface.co/spaces/SZLHOLDINGS/szl-command-lab) · [**Build source**](https://github.com/szl-holdings)

## Repeat a public calculation

[Input and hash](https://github.com/szl-holdings/governed-receipt-spec/tree/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell#public-data-and-attribution) [Executed code](https://github.com/szl-holdings/governed-receipt-spec/blob/160e39b1383a0e249399b6dfb72983b67aef7fe8/examples/public-single-cell/run_example.py) [Retained result](https://github.com/szl-holdings/governed-receipt-spec/blob/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell/observed-run.json) [Repeat](https://github.com/szl-holdings/governed-receipt-spec/tree/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell#reproduce-the-recorded-run) [Limits](https://github.com/szl-holdings/governed-receipt-spec/tree/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell#outputs-and-verification-boundary)

GEO GSE85241: integrity and repeatability checks; unsigned receipt; no biological or clinical claim.

## Choose a path

- **Use:** [A11oy](https://a-11-oy.com), with its current capability state.
- **Build:** [models, kernels, datasets and Spaces](https://huggingface.co/SZLHOLDINGS).
- **Verify:** [computation records](https://a11oy.net), [evidence diagrams](https://a11oy.net/diagrams/) and stated limits.

## Inference flagship

<!-- SZL_LLM_ROUTER_FLAGSHIP:BEGIN -->
[SZL Router](https://github.com/szl-holdings/szl-router) exposes an OpenAI-compatible gateway. [Status](https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live) · [A11oy integration](https://a-11-oy.com/code) · [Route map](https://raw.githubusercontent.com/szl-holdings/.github/main/profile/assets/hf-card-router.svg). Provider availability requires separate evidence.
<!-- SZL_LLM_ROUTER_FLAGSHIP:END -->

Killinchu's public effectors remain **SIMULATED**.

[Receipt gallery](https://szlholdings-readme.static.hf.space/evidence.html)

## Current state

<!-- szl:public-inventory:start -->
The source-bound public inventory records **52 public Spaces, 138 model repositories, 14 native kernels, 68 datasets** at **2026-11-14T04:09:48Z** under `hf-public-author-membership/v2`. This is a dated observation, not a live count. Native kernel IDs may also appear in the model namespace; these figures do not count unique projects or trained language models. [Inventory binding](https://github.com/szl-holdings/.github/blob/main/profile/public-inventory.json) · [Exact source](https://github.com/szl-holdings/a11oy/blob/dac5a4cac8011af907146e813b0e8996a3bee424/docs/huggingface-ecosystem-manifest.json) · [Current Hub listing](https://huggingface.co/SZLHOLDINGS). Hub inventory is registry evidence, not availability, operational readiness, or publication policy. It does not establish model quality.
<!-- szl:public-inventory:end -->

Supplemental observation on 2026-11-13: the public page listed 107 model repositories, 68 datasets, 53 Spaces and 14 kernels; the API listed 52 Spaces. That discrepancy remains unresolved.

**HISTORICAL** estate-alignment v1 records 16 portfolio Spaces, 1 inventory-only Space, 45 models and 34 datasets; the [legacy dataset](https://huggingface.co/datasets/SZLHOLDINGS/SZLHOLDINGS) is not current readiness evidence.

<details>
<summary>Reproduction and provenance</summary>

[Architecture](https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/estate-command-system.svg).

Check source and digests in [`deployment.json`](https://szlholdings-readme.static.hf.space/deployment.json) against the [manifest](https://github.com/szl-holdings/.github/blob/main/huggingface/org-card.manifest.json). Signatures establish scoped integrity and origin, never accuracy or fitness.

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
