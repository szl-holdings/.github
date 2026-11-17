# SZL source map

> Front end, back end, and Python — one estate, every layer public where it can be.
> All counts and links are dated observations (2026-11-17). Registry evidence is not availability, readiness, or quality. Λ = Conjecture 1 (advisory).

## Product surfaces (live, measured 2026-11-17)

- [a-11-oy.com](https://a-11-oy.com) — the product front door; `/healthz` returned HTTP 200 (doctrine v11)
- [inference.a-11-oy.com](https://inference.a-11-oy.com) — x402-metered LLM inference, the monetization surface; unpaid completions return an HTTP 402 x402 v2 payment challenge (Base/USDC)
- [a11oy.net](https://a11oy.net) — the proof surface: records, limits, evidence diagrams
- [killinchu.a-11-oy.com](https://killinchu.a-11-oy.com) — counter-UAS research demo (effectors SIMULATED)
- [mcp.a-11-oy.com](https://mcp.a-11-oy.com) — production MCP tooling

## Front end

- [wink-observatory](https://github.com/szl-holdings/wink-observatory) — live 3D estate telemetry: witness records, receipt-trippability audit, fleet telemetry
- [szl-khipu-scholar](https://github.com/szl-holdings/szl-khipu-scholar) — khipu explorer: provenance-first corpus, OKR-derived QA dataset, receipts API
- [A11oy](https://huggingface.co/spaces/SZLHOLDINGS/a11oy) — the governed product surface (Space)
- [Command Lab](https://huggingface.co/spaces/SZLHOLDINGS/szl-command-lab) — searchable portfolio
- [llm-router-live](https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live) — router status surface

## Back end

- [a11oy](https://github.com/szl-holdings/a11oy) — governed runtime: deny by default, signed receipts, x402 APIs
- [szl-inference-gateway](https://github.com/szl-holdings/szl-inference-gateway) — production x402-metered LLM inference on SaladCloud GPUs
- [szl-router](https://github.com/szl-holdings/szl-router) — OpenAI-compatible gateway with a receipt on every answer
- [hatun-mcp](https://github.com/szl-holdings/hatun-mcp) — doctrine-aware MCP server
- [szl-estate-os](https://github.com/szl-holdings/szl-estate-os) — governed control plane for the GitHub, Hugging Face, and domain estate (private)
- [killinchu](https://github.com/szl-holdings/killinchu) — counter-UAS field tool, DSSE receipt per engagement

## Python on PyPI

19 packages under [betterwithage](https://pypi.org/user/betterwithage/) observed 2026-11-17:
[szl-frontier-control-plane](https://pypi.org/project/szl-frontier-control-plane/) ·
[szl-os](https://pypi.org/project/szl-os/) ·
[szl-kernel-attest](https://pypi.org/project/szl-kernel-attest/) ·
[szl-lyte-enterprise](https://pypi.org/project/szl-lyte-enterprise/) ·
[szl-re](https://pypi.org/project/szl-re/) ·
[szl-drift](https://pypi.org/project/szl-drift/) ·
[szl-atelier](https://pypi.org/project/szl-atelier/) ·
[quant-curve](https://pypi.org/project/quant-curve/) ·
[szl-wave1-report](https://pypi.org/project/szl-wave1-report/) ·
[yarqa](https://pypi.org/project/yarqa/) ·
[szl-serve](https://pypi.org/project/szl-serve/) ·
[szl-second-brain](https://pypi.org/project/szl-second-brain/) ·
[szl-vertical-forge](https://pypi.org/project/szl-vertical-forge/) ·
[szl-khipu](https://pypi.org/project/szl-khipu/) ·
[szl-ouroboros](https://pypi.org/project/szl-ouroboros/) ·
[szl-mesh](https://pypi.org/project/szl-mesh/) ·
[khipu-consensus](https://pypi.org/project/khipu-consensus/) ·
[a11oy-factory](https://pypi.org/project/a11oy-factory/) ·
[szl-router](https://pypi.org/project/szl-router/)

Also live: [khipu-x1](https://pypi.org/project/khipu-x1/) and [szl-provctl](https://pypi.org/project/szl-provctl/). Ownership and versions are what PyPI serves; audit each project page before depending on it.

## Hugging Face alignment

- Org: [huggingface.co/SZLHOLDINGS](https://huggingface.co/SZLHOLDINGS) — org card, models, datasets, Spaces
- Public inventory (2026-11-15): 22 public Spaces, 121 public model repositories, 14 native kernels, 69 datasets
- Frontier receipts: [frontier-54-runs](https://huggingface.co/datasets/SZLHOLDINGS/frontier-54-runs) (system of record) · [frontier-55-runs](https://github.com/szl-holdings/frontier-55-runs) (public GitHub mirror, anonymous-only)

## Frontier, in flight (observed 2026-11-17)

`szl-frontier54-v2r-all` — the flagship-54 successor resumed from [salad-flagship54-v1/checkpoint-37000](https://huggingface.co/SZLHOLDINGS/salad-flagship54-v1/tree/main/checkpoint-37000) on an all-estates curriculum: the three pinned phases (doctrine · math+governance · replay-reweight) kept exactly, then 93 additional estate datasets (axioms, Lean proofs, khipu corpora, doctrine, math, thesis lineage) across two new phases; budget 54h → 78h. Training-in-progress observation; no capability claim until receipts land in frontier-54-runs.

## Cloudflare and monetization

- The a-11-oy.com routes are served through Cloudflare (Workers and tunnels)
- Monetization is live at the inference gateway via x402 payment challenges (measured 2026-11-15 and 2026-11-17)
- Owner-gated (deliberately not done by agents): Cloudflare dashboard POST-charging confirmation; Zero Trust on salad.a-11-oy.com

## Claim boundaries

Counts are dated observations, not live guarantees. A green check is not a deployment; a deployment is not a proof. Nothing here asserts model quality, SLA, or production readiness.
