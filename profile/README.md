<p><a href="https://huggingface.co/spaces/SZLHOLDINGS/szl-command-lab"><img src="https://raw.githubusercontent.com/szl-holdings/.github/main/profile/assets/szl/logos/szl_mark_holographic.svg" alt="SZL Holdings" width="144" /></a></p>

# Governed intelligence. Checkable results.

SZL Holdings builds AI software, models and research tools that connect an output to its source and evidence. Explore the systems, inspect what is available, and reproduce the work behind each claim.

[**Explore Command Lab →**](https://huggingface.co/spaces/SZLHOLDINGS/szl-command-lab) · [**Build with the source →**](https://github.com/szl-holdings)

## Repeat a public calculation

[Input and hash](https://github.com/szl-holdings/governed-receipt-spec/tree/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell#public-data-and-attribution) → [Executed code](https://github.com/szl-holdings/governed-receipt-spec/blob/160e39b1383a0e249399b6dfb72983b67aef7fe8/examples/public-single-cell/run_example.py) → [Retained result](https://github.com/szl-holdings/governed-receipt-spec/blob/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell/observed-run.json) → [Repeat](https://github.com/szl-holdings/governed-receipt-spec/tree/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell#reproduce-the-recorded-run) → [Limits](https://github.com/szl-holdings/governed-receipt-spec/tree/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell#outputs-and-verification-boundary)

The single-cell example summarizes public GEO GSE85241 data and checks integrity and repeatability. Its receipt is unsigned; it makes no biological or clinical claim.

## Choose a path

- **Explore:** [Command Lab](https://huggingface.co/spaces/SZLHOLDINGS/szl-command-lab) brings the public portfolio into one searchable interface.
- **Use:** [A11oy](https://a-11-oy.com) exposes tools and their current capability state.
- **Build:** browse [models, kernels, datasets and Spaces](https://huggingface.co/SZLHOLDINGS), or [published Python packages](https://pypi.org/user/betterwithage/).
- **Verify:** [a11oy.net](https://a11oy.net) links computation records and their limits, with [evidence diagrams](https://a11oy.net/diagrams/) drawn from recorded runs.

<a href="https://a11oy.net/diagrams/"><img src="https://raw.githubusercontent.com/szl-holdings/.github/main/profile/assets/diagrams/evidence-diagrams-overview.png" alt="Overview of four SZL evidence diagrams" width="720" /></a>

## What we build

**A11oy** connects governed workflows. **[SZL Router](https://github.com/szl-holdings/szl-router)** routes model requests through [A11oy Code](https://a-11-oy.com/code) and publishes a [status surface](https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live). **Killinchu** demonstrates public observation and operator decisions; public effectors remain **SIMULATED**. **Forge** houses model and software research.

A published file, running application and independently checked result establish different things. Each artifact needs its own evidence and use limits.


## The flagship estate

| Flagship | What it is | Live |
|---|---|---|
| **a11oy** | The governed runtime — x402-monetized API surfaces, receipts, doctrine | [a-11-oy.com](https://a-11-oy.com) · [Space](https://huggingface.co/spaces/SZLHOLDINGS/a11oy) |
| **Living Anatomy** | The canonical anatomy engine — org Space, verified publish (run #874) | [szlholdings-anatomy.hf.space](https://szlholdings-anatomy.hf.space) · [repo](https://github.com/szl-holdings/anatomy) |
| **Second Brain** | The estate's memory and knowledge plane | [Space](https://huggingface.co/spaces/SZLHOLDINGS/szl-second-brain) · [repo](https://github.com/szl-holdings/szl-second-brain) |
| **hatun-mcp** | Production MCP tooling on sovereign compute (A6000) | [repo](https://github.com/szl-holdings/hatun-mcp) · [mcp.a-11-oy.com](https://mcp.a-11-oy.com) |
| **killinchu** | Counter-UAS intelligence, continuously certified | [killinchu.a-11-oy.com](https://killinchu.a-11-oy.com) · [repo](https://github.com/szl-holdings/killinchu) |

## Measured result: the confabulation floor

One 6-probe battery, every model receipted, every failure published — [receipts](https://huggingface.co/datasets/SZLHOLDINGS/model-eval-receipts).

| Model | Method | Abstained | Verdict |
|---|---|---|---|
| Estate students (0.8B–4B) | SFT · ouroboros · DPO ×2 · cookie-DPO | 0–2/6 | **FAIL** |
| Qwen3-8B | open weights | 1/6 | **FAIL** |
| Qwen3-14B | open weights | 1/6 | **FAIL** |
| Estate teacher + copy-constrained decoding | logits masked to source tokens | **21.9%** capture (46/210) | **16× the free-decoding floor** |
| Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) | frontier alignment | **5/6** | **PASS — first in the arc** |

**The law, measured nine ways:** the confabulation floor is an *alignment property expressed through decoding* — estate training at ≤4B does not move it, open-model scale to 14B does not move it, constrained decoding moves it 16×, frontier alignment clears it. Papers: [P8](https://doi.org/10.5281/zenodo.24043620) · [P9](https://doi.org/10.5281/zenodo.24043622).

## Current state

<!-- szl:public-inventory:start -->
The source-bound public inventory records **40 public Spaces, 41 model repositories, 14 native kernels, 38 datasets** at **2026-11-01T22:56:52Z** under `hf-public-author-membership/v2`. This is a dated observation, not a live count. Native kernel IDs may also appear in the model namespace; these figures do not count unique projects or trained language models. [Inventory binding](https://github.com/szl-holdings/.github/blob/main/profile/public-inventory.json) · [Exact source](https://github.com/szl-holdings/a11oy/blob/fef0c7e1223f91a78253f6a3ef1abe33173418c8/docs/huggingface-ecosystem-manifest.json) · [Current Hub listing](https://huggingface.co/SZLHOLDINGS). Hub inventory is registry evidence, not availability, operational readiness, or publication policy. It does not establish model quality.
<!-- szl:public-inventory:end -->

**HISTORICAL:** estate-alignment v1 described 16 portfolio Spaces, 1 inventory-only Space, 45 models, and 34 datasets. The [`SZLHOLDINGS/SZLHOLDINGS` dataset](https://huggingface.co/datasets/SZLHOLDINGS/SZLHOLDINGS) is a historical profile mirror. It does not establish today's inventory, readiness, or model quality.

<details>
<summary>Reproduce an example and inspect the architecture</summary>

[Architecture image](./assets/evidence-lattice-v2.webp) · [Authorization rules](https://github.com/szl-holdings/.github/blob/main/TRUST.md)

### Portfolio roles

- **Three commercial flagships:** A11oy, Killinchu, Forge.
- **One inference flagship:** SZL Router.
- **Five public domain bodies:** Terra, Killinchu, PRISM Counsel, PURIQ Finance, LYTE.
- **Six internal engines:** CHAPAQ (folded into Killinchu), Lyte, Killinchu, Finance, Terra, Counsel.

These are architecture roles. Inspect each artifact's source and stated use limits before choosing a use.

</details>

Measured runtime snapshot: [full audit](../docs/LIVING_SOULS_INFRASTRUCTURE_AUDIT_2026-10-17.md).
