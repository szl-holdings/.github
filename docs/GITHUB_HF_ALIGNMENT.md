# GitHub ↔ Hugging Face alignment

**Status:** `SOURCE_MIRROR_REGISTRY_PUBLISHED`  
**Captured:** 2026-08-29T00:31:00-04:00  
**Evidence class:** REPORTED  
**Runtime:** DEMO

GitHub `szl-holdings` is protected source. Hugging Face `SZLHOLDINGS` is the
artifact, evaluation, and demonstration mirror — not customer production SaaS.

This registry classifies **existing** cards against **existing** repositories.
It does not mint a new public GitHub repository or Hugging Face Space.

## Live recapture

| Surface | Count | Source |
| --- | ---: | --- |
| GitHub authenticated search | 82 | `user:szl-holdings` |
| GitHub org page shown | 69 | github.com/szl-holdings |
| GitHub private observed | 5 | same search |
| GitHub archived observed | 7 | same search |
| Hub model cards | 40 | `/api/models?author=SZLHOLDINGS` |
| Hub datasets | 28 | `/api/datasets?author=SZLHOLDINGS` |
| Hub Spaces (API) | 31 | `/api/spaces?author=SZLHOLDINGS` |
| Hub Spaces (org card) | 30 | huggingface.co/SZLHOLDINGS |
| Hub collections | 13 | org card |
| Kernel-tagged model cards | 15 | Hub tags `kernels` |

Packet 4 snapshot remains 76 GitHub rows / 17 dedicated model cards / 27 Spaces.
Delta is sprawl to classify, not a new product line.

Remaining open PR: [`szl-holdings/.github#465`](https://github.com/szl-holdings/.github/pull/465)
(external GitHub App permission — not closed by this map).

## Rule

1. Exact-name Kernel Hub packages already have GitHub twins. Hub is the publish mirror.
2. Weight and adapter cards bind to [`szl-forge`](https://github.com/szl-holdings/szl-forge). GGUF children bind to [`szl-serve`](https://github.com/szl-holdings/szl-serve).
3. Numpy silhouettes bind to [`szl-khipu`](https://github.com/szl-holdings/szl-khipu). Atlas stays [`SZLHOLDINGS/anatomy`](https://huggingface.co/spaces/SZLHOLDINGS/anatomy).
4. Roadmap names (`qantu`, `waman`, `chakana`, `tinku`, `KILLINCHU-EYE`, org stub) stay Hub cards. Do not mint GitHub products for them.
5. Spaces without a dedicated repo fold into anatomy, Forge, kernels, or Evidence Studio. Do not mint `cosmos` or `holographic` repositories.
6. Wave 0 still **DENY**s new public repositories, Spaces, and product names.

## Exact kernel / software twins

| Hub | GitHub |
| --- | --- |
| SZLHOLDINGS/szl-kernels | szl-holdings/szl-kernels |
| SZLHOLDINGS/szl-invariants | szl-holdings/szl-invariants |
| SZLHOLDINGS/szl-blocked | szl-holdings/szl-blocked |
| SZLHOLDINGS/szl-govsign | szl-holdings/szl-govsign |
| SZLHOLDINGS/szl-provctl | szl-holdings/szl-provctl |
| SZLHOLDINGS/szl-ouroboros | szl-holdings/szl-ouroboros |
| SZLHOLDINGS/szl-formulas | szl-holdings/szl-formulas |
| SZLHOLDINGS/szl-lambda-gate | szl-holdings/szl-lambda-gate |
| SZLHOLDINGS/szl-governed-norm | szl-holdings/szl-governed-norm |
| SZLHOLDINGS/governed-inference-meter | szl-holdings/governed-inference-meter |
| SZLHOLDINGS/szl-receipt-attn | szl-holdings/szl-receipt-attn |
| SZLHOLDINGS/szl-maskmod | szl-holdings/szl-maskmod |
| SZLHOLDINGS/szl-block-kv | szl-holdings/szl-block-kv |
| SZLHOLDINGS/YARQA-ATTN | szl-holdings/YARQA-ATTN |
| SZLHOLDINGS/szl-nemo | szl-holdings/szl-nemo |
| SZLHOLDINGS/szl-khipu | szl-holdings/szl-khipu |
| SZLHOLDINGS/szl-lake | szl-holdings/szl-lake |

## Weight lineage (Forge)

SZL-Khipu-1.5B, SZL-Forge-1.5B-ReceiptAgent, szl-receiptagent-qwen35-0.8b-v2,
SZL-Khipu-1.5B-abstain, KHIPU-R2, WILLAY, chaski, chaski-5050, chaski-r2,
szl-training-scripts → `szl-holdings/szl-forge`.

SZL-Khipu-1.5B-GGUF → `szl-holdings/szl-serve`.
A11OY-MINI → `szl-holdings/a11oy`.
TinyKhipu-Nano / ReceiptAgent-Nano / Moons-Nano → `szl-holdings/szl-khipu`.
MiniEmbed-Nano / szl-khipu-kernels → `szl-holdings/szl-kernels`.

## Flagship Spaces (paired)

a11oy, killinchu, anatomy, yarqa, hatun-mcp, sda, immune, david-leads,
szl-khipu, ayllu, nexus, plus the hologram twins
(governed-norm-holo, lambda-gate-holo, energy-attest-holo, receipt-chain-live,
szl-provctl-live, szl-kernels-live).

`SZLHOLDINGS/cosmos` has no GitHub twin — fold into anatomy. Do not mint.

## What this is not

- Not ATO, paid pilot, ROI, or live BFT.
- Not 9000 invented live nodes. Second-brain count remains UNAVAILABLE.
- Not a Hugging Face mutation. This OS cannot write the Hub.
- Not a pin change. Front-door pin target remains
  `.github`, `a11oy`, `platform`, `docs-site`, `a11oy-net`, `killinchu`.

Λ uniqueness remains **Conjecture 1**. Khipu BFT remains **Conjecture 2**.
