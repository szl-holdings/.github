---
title: SZL Holdings
emoji: 🛡️
colorFrom: gray
colorTo: gray
sdk: static
short_description: Checkable computations, public data, reproducible examples.
thumbnail: https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp
pinned: true
license: apache-2.0
---

<!-- markdownlint-disable MD013 MD033 MD041 -->
<!-- markdownlint-configure-file {"MD025": {"front_matter_title": ""}} -->

# SZL Holdings

We build tools that make computational results checkable.

A computation receipt records the exact input file, the code that ran, and
the output hash. Someone else can repeat the calculation and compare its
bytes with the retained result. If a check cannot run, it reports
**not verified**. It never counts a missing check as passed.

## See it on real data

Our [worked single-cell example](https://github.com/szl-holdings/governed-receipt-spec/tree/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell)
downloads the public GEO GSE85241 file and summarizes all **3,072 submitted
cell columns**, retaining **4 source donor labels**. It records **19,059
endogenous features** and **81 ERCC spike-in rows** separately. The original
researchers produced the data; the example does not redistribute the matrix.

The [recorded run](https://github.com/szl-holdings/governed-receipt-spec/blob/320983d22e76fc9b26af0b2cd20799c5000543fc/examples/public-single-cell/observed-run.json)
produced byte-identical summary output twice. Changed summary bytes and
changed receipt payloads were rejected against the unchanged retained reference.
The example links its exact executed source, public CPU run, and reproduction commands.

## What the checks mean

This is a demonstration of **integrity and reproducibility**. The receipt
is **unsigned**: it does not verify authorship or prevent replacement of
all files and hashes together.

It runs **no gene-signature scoring**, reports **no biological findings**,
and claims no superiority over AUCell, UCell, or Seurat. Donor summaries
are descriptive; cells are not treated as independent biological replicates
in a hypothesis test. It makes **no clinical-use claim**.

## Language-model evaluation records

Our [evaluation receipts dataset](https://huggingface.co/datasets/SZLHOLDINGS/szl-frontier-evaluation-receipts)
contains separate language-model evaluation records. Read each record's
inputs, execution details, and limitations; it does not validate the
single-cell example or establish general model superiority.

For other Python tools, browse the [published packages](https://pypi.org/user/betterwithage/) and their [package manifest](https://github.com/szl-holdings/szlholdings.com/blob/main/pypi/pypi-packages.v1.json). Reproduce this example with its recorded setup.

[Product](https://a-11-oy.com) ·
[Source of this page](https://szlholdings-readme.static.hf.space/deployment.json)
