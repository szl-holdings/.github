---
viewer: false
license: apache-2.0
pretty_name: SZL Holdings
tags:
- org-profile
- doi:10.5281/zenodo.19944926
size_categories:
- n<1K
task_categories:
- other
language:
- en
---

# SZL Holdings - organization profile metadata

> **Lifecycle: INFORMATIONAL_METADATA_ONLY. Production-candidate: false.** At exact
> upstream revision `fdca3ff2d26bc25080a87a75c02994055f2e01bb`, this repository
> contains three metadata files and no dataset payload, records, schema,
> configuration, or generated artifact. It must not be treated as training data.

## Evidence and machine-readable status

- [`provenance.json`](./provenance.json) binds this candidate to the exact
  Hugging Face dataset repository identity, revision, and upstream file manifest.
- [`status.json`](./status.json) blocks dataset-artifact, training-suitability,
  deployment, and production claims until source and artifact evidence exists.
- [`LICENSE`](./LICENSE) materializes the standard Apache License 2.0 text solely
  because the existing dataset card explicitly declares `apache-2.0`. This does
  not establish chain of title, consent, source-data rights, or a license for any
  future dataset artifact.
- `SZL_ESTATE_MANAGED.json` is preserved unchanged as legacy estate metadata. It
  is not treated as artifact, deployment, or runtime proof.

## Current evidence boundary

| Subject | Evidence state | Basis |
|---|---|---|
| Repository identity and head | **OBSERVED** | Authenticated exact-revision read on 2026-08-30. |
| Dataset payload | **BLOCKED** | No data-bearing file exists in the captured manifest. |
| Source dataset and collection | **UNKNOWN** | No source, collection, consent, or transformation record exists. |
| Dataset artifact license | **BLOCKED** | No dataset artifact exists; repository metadata cannot license absent data. |
| Repository materials license | **OBSERVED** | Existing card metadata explicitly declares `apache-2.0`; candidate adds standard text. |
| Training suitability | **BLOCKED** | No records, schema, quality evidence, PII review, or usage analysis exists. |
| Promoted or production-candidate status | **BLOCKED** | Informational profile metadata only. |

This repository is an organization-profile mirror. It is not a model-training
corpus and does not contain the thesis datasets named below.

## Thesis and research references

The card references the SZL Holdings research program and concept DOI
[`10.5281/zenodo.19944926`](https://doi.org/10.5281/zenodo.19944926). The
concept DOI is not an artifact-specific DOI for this repository and does not
prove that a dataset payload exists here.

- Canonical timeline:
  [THESIS_LINEAGE.md](https://github.com/szl-holdings/szl-papers/blob/main/thesis/THESIS_LINEAGE.md)
- Research repository:
  [szl-papers](https://github.com/szl-holdings/szl-papers)
- Organization profile:
  [SZLHOLDINGS](https://huggingface.co/SZLHOLDINGS)

### Separate Hugging Face datasets

The following are separate repositories. Their existence does not supply source
or artifact provenance for this metadata-only repository.

| Dataset | Described contents |
|---|---|
| [`SZLHOLDINGS/thesis-v18-formal-verification`](https://huggingface.co/datasets/SZLHOLDINGS/thesis-v18-formal-verification) | Per-theorem Lean mechanisation index |
| [`SZLHOLDINGS/thesis-corpus-v18`](https://huggingface.co/datasets/SZLHOLDINGS/thesis-corpus-v18) | Thesis text corpus |
| [`SZLHOLDINGS/ouroboros-arxiv-preprint`](https://huggingface.co/datasets/SZLHOLDINGS/ouroboros-arxiv-preprint) | arXiv preprint package |

## Intended use

- Organization-profile and research-program navigation.
- Human-readable references to separately governed repositories.

## Prohibited interpretations

- A dataset payload or row collection.
- A training, evaluation, or benchmark dataset.
- Evidence that referenced repositories, deployments, theorem counts, or runtime
  claims were independently verified by this repository.
- Evidence of source-data rights, consent, privacy review, or chain of title.

## Citation boundary

The concept DOI and author metadata may be used to identify the broader research
program. No artifact-specific DOI is established for this metadata-only dataset
repository.

Repository materials are declared Apache-2.0. Dataset-artifact provenance and
licensing remain **BLOCKED** because no dataset artifact is present.
