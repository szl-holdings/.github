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

<p align="center"><img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp" alt="A signal entering the SZL evidence lattice" width="100%" /></p>

# SZL Holdings

**Control before action. Evidence after.** Explore SZL models, data, software, and demonstrations. Each artifact has its own source, limits, and proof; a running Space does not qualify the estate.

## Choose a path

- **Operate:** [A11oy command center](https://a-11-oy.com) · inspect the live capability state before relying on a route.
- **Build:** [GitHub source](https://github.com/szl-holdings) · pin the exact revision behind an artifact.
- **Research:** [Hugging Face portfolio](https://huggingface.co/SZLHOLDINGS) · compare models, datasets, kernels, and Spaces.
- **Verify:** [A11oy proof registry](https://a11oy.net) · follow receipts outside the product interface.

## Inference flagship

<!-- SZL_LLM_ROUTER_FLAGSHIP:BEGIN -->
**SZL Router** exposes an OpenAI-compatible gateway with route state and provenance. [Open the Space](https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live), [inspect source](https://github.com/szl-holdings/szl-router), [A11oy integration](https://a-11-oy.com/code), or [view the route map](https://raw.githubusercontent.com/szl-holdings/.github/main/profile/assets/hf-card-router.svg). Its providers require separate qualification.
<!-- SZL_LLM_ROUTER_FLAGSHIP:END -->

## Portfolio at a glance

**Three commercial flagships:** A11oy, Killinchu, Forge. **One inference flagship:** SZL Router. **Five public domain bodies:** Terra, Killinchu, PRISM Counsel, PURIQ Finance, LYTE. **Six internal engines:** Sentra, Lyte, Killinchu, Finance, Terra, Counsel. These are product roles, not availability claims.

[Killinchu](https://huggingface.co/spaces/SZLHOLDINGS/killinchu) presents public observation and operator decisions; its effectors are **SIMULATED**. [Read its source](https://github.com/szl-holdings/killinchu) and readiness before using its outputs. [Explore the architecture image](https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/estate-command-system.svg).

## Current state

The last source-bound public inventory snapshot recorded **21 public Spaces, 46 models, 35 datasets** at **2026-09-10T03:20:41Z** under `hf-public-author-membership/v1`. Dated snapshot, not a live count; Hub inventory is registry evidence, not availability, operational readiness, or publication policy. [Read `profile/public-inventory.json`](https://github.com/szl-holdings/.github/blob/main/profile/public-inventory.json), bound to A11oy source `4c6621b17ba452d5af7aa2460462fdfbe513509f`, then browse the [live Hub listing](https://huggingface.co/SZLHOLDINGS).

**HISTORICAL** estate-alignment v1 described 16 portfolio Spaces and 1 inventory-only Space, with 45 models and 34 datasets. The [`SZLHOLDINGS/SZLHOLDINGS` dataset](https://huggingface.co/datasets/SZLHOLDINGS/SZLHOLDINGS) is also historical. Neither supplies current readiness.

## Reproduce and verify

The served [`deployment.json`](https://szlholdings-readme.static.hf.space/deployment.json) names the source revision. Compare its file digests with the [GitHub publisher](https://github.com/szl-holdings/.github/blob/main/huggingface/org-card.manifest.json) and the Hub commit. A signature proves scoped integrity and origin, never accuracy or fitness.

```bash
preview_dir="$(mktemp -d)"
python .github/scripts/hf_static_space_deploy.py --repo-root . \
  --manifest huggingface/org-card.manifest.json \
  --source-sha "$(git rev-parse HEAD)" --materialize "$preview_dir"
python -m http.server 8000 --directory "$preview_dir"
```
