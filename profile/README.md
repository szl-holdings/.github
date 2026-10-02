<!-- markdownlint-disable MD013 MD041 -->

![SZL Holdings evidence lattice](./assets/evidence-lattice-v2.webp)

# SZL Holdings

**Make the computation checkable.** We build software for inspecting computational results and repeating calculations. A computation receipt records the input, code, and output hash; it does not establish scientific correctness or make a model suitable for a particular use.

## Start here

- **Use the product:** [a-11-oy.com](https://a-11-oy.com) shows A11oy's tools and their reported availability.
- **Inspect records:** [a11oy.net](https://a11oy.net) publishes computation records; read each record's checks and limits.
- **Repeat a public example:** [The worked single-cell example](https://github.com/szl-holdings/governed-receipt-spec/tree/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell) gives the input, calculation, retained result, and explicit verification limits.
- **Read source:** [github.com/szl-holdings](https://github.com/szl-holdings) contains the software source.
- **Install published packages:** [PyPI](https://pypi.org/user/betterwithage/) lists the available Python packages; verify each package's own release evidence.

## How the pieces fit

**A11oy** provides an interface for using tools and inspecting results. **[SZL Router](https://github.com/szl-holdings/szl-router)** routes requests to language models, with a [public status page](https://huggingface.co/spaces/SZLHOLDINGS/llm-router-live), [operator interface](https://a-11-oy.com/code), and [route map](https://raw.githubusercontent.com/szl-holdings/.github/main/profile/assets/hf-card-router.svg). **Killinchu** demonstrates observations and operator decisions; its public action outputs remain **SIMULATED**. **Forge** houses model and software research. [The example introduction](https://huggingface.co/spaces/SZLHOLDINGS/README) explains a reproducible calculation and its limits.

Published source, a successful build, running software, and independently checked results establish different things. Labels such as `MEASURED`, `REPORTED`, `UNKNOWN`, and `UNAVAILABLE` state what was observed. Read the supporting record and its limits. The [authorization rules](https://github.com/szl-holdings/.github/blob/main/TRUST.md) explain who may authorize an action.

## Current state

The last source-bound public inventory snapshot recorded **21 public Spaces, 46 models, 35 datasets** at **2026-09-10T03:20:41Z** under `hf-public-author-membership/v1`. This is a dated observation, not a live count. [Read `profile/public-inventory.json`](https://github.com/szl-holdings/.github/blob/main/profile/public-inventory.json), bound to A11oy source `4c6621b17ba452d5af7aa2460462fdfbe513509f`. For a specific published artifact, inspect the [language-model evaluation records](https://huggingface.co/datasets/SZLHOLDINGS/szl-frontier-evaluation-receipts) and their stated limits.

**HISTORICAL:** an earlier inventory described 16 portfolio Spaces, 1 inventory-only Space, 45 models, and 34 datasets. The [`SZLHOLDINGS/SZLHOLDINGS` dataset](https://huggingface.co/datasets/SZLHOLDINGS/SZLHOLDINGS) is a historical profile mirror. It does not establish today's inventory, readiness, or model quality.

*Trace the source. Check the state. Read the limit.*
