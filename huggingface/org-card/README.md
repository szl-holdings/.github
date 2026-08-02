---
title: SZL Holdings — Governed Decision Infrastructure
emoji: 🛡️
colorFrom: gray
colorTo: yellow
sdk: static
short_description: Governed AI that can explain, constrain, and verify action
pinned: true
license: apache-2.0
---

<!-- markdownlint-disable MD013 MD033 MD041 -->

<p align="center">
  <img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/estate-command-system.svg"
       alt="SZL Holdings — autonomy, under authority"
       width="100%" />
</p>

<div align="center">

# Governed models, data, and demonstrations

SZL Holdings publishes the model and data layer for systems that must reason,
act within authority, and return evidence that is independently auditable.

[**Open a11oy**](https://a-11-oy.com) ·
[**Inspect evidence**](https://a11oy.net) ·
[**View source**](https://github.com/szl-holdings) ·
[**Read documentation**](https://holdings.a-11-oy.com/docs-site/)

</div>

---

## Start here

| Need | Canonical artifact | Boundary |
| --- | --- | --- |
| Governed receipt generation | [SZL-Forge-1.5B-ReceiptAgent](https://huggingface.co/SZLHOLDINGS/SZL-Forge-1.5B-ReceiptAgent) | A model artifact; autonomy requires a validating controller |
| Grounded estate navigation | [SZL-Khipu-1.5B](https://huggingface.co/SZLHOLDINGS/SZL-Khipu-1.5B) | Use cited retrieval and verify sources independently |
| Local quantized evaluation | [SZL-Khipu-1.5B-GGUF](https://huggingface.co/SZLHOLDINGS/SZL-Khipu-1.5B-GGUF) | Quantization changes runtime characteristics; evaluate the exact file |
| Receipt and evidence records | [szl-lake](https://huggingface.co/datasets/SZLHOLDINGS/szl-lake) | Records are admitted by their own provenance and license state |
| Public OSINT corpus | [killinchu-osint-corpus](https://huggingface.co/datasets/SZLHOLDINGS/killinchu-osint-corpus) | Public-source research corpus; not an operational intelligence feed |
| Product demonstration | [a11oy Space](https://huggingface.co/spaces/SZLHOLDINGS/a11oy) | A demonstration surface; verify live state and exact source separately |

Download counters are Hub-reported events, not unique users, deployments,
customers, model quality, or revenue.

## Artifact contract

Every promoted artifact must identify what it is and what evidence exists.

### Trained weights

- exact base model and license lineage;
- weight or adapter hashes;
- clean load and inference receipt;
- held-out and adversarial evaluation;
- restart and reproduction evidence;
- latency, memory, and energy context;
- an explicit autonomy boundary.

### Datasets

- source and license provenance at row or source-family scope;
- schema, splits, sizes, and validation results;
- privacy, consent, PII, and update policy;
- known omissions, quarantine counts, and intended use.

### Kernels and tools

- canonical source repository and immutable revision;
- supported hardware and software matrix;
- executable tests and benchmark protocol;
- no implied training receipt or model capability.

### Spaces

- canonical source and deployment revision;
- pinned dependencies and runtime behavior;
- privacy and retention behavior;
- visible limitations and reproducible local path.

A model card is not operational proof. A Space in `RUNNING` state proves
transport availability only. A signed receipt establishes integrity and origin
within its stated scope; it does not automatically establish correctness,
safety, or authorization to operate.

### Model status

- **PROVED:** independently verified by a signed artifact in declared scope.
- **MEASURED:** measured on a defined, reproducible dataset and test path.
- **REPORTED:** reported by trusted telemetry or published evidence.
- **MODELED:** mathematically/architecturally inferred and clearly bounded.
- **CONJECTURE:** plausible but not yet externally measured.
- **ROADMAP:** explicit next-step work plan.

### Runtime status classes

- **OPERATIONAL**
- **PARTIAL**
- **DEGRADED**
- **UNAVAILABLE**
- **HISTORICAL**

Lambda uniqueness remains **Conjecture 1**, not a theorem. No artifact is
promoted solely because it has a card, a counter, a live route, or a filename
that sounds like a model.

## One governed loop

```text
signal → reason → policy → bounded action → receipt → independent verification
                     ↑                                      │
                     └────────────── verified feedback ──────┘
```

The model proposes. The controller validates authority and evidence. The
runtime executes only within a declared bound. The receipt lets a separate
party inspect what happened.

## Source and support

This company front door is source-controlled at
[`szl-holdings/.github`](https://github.com/szl-holdings/.github/tree/main/huggingface/org-card)
and deployed with an exact source-revision manifest. Inspect
[`deployment.json`](https://szlholdings-readme.static.hf.space/deployment.json)
on the running static Space for the served source binding.

- [Security policy](https://github.com/szl-holdings/.github/security/policy)
- [Trust posture](https://github.com/szl-holdings/.github/blob/main/TRUST.md)
- [Support](https://github.com/szl-holdings/.github/blob/main/SUPPORT.md)
- [Honest disclosure](./HONEST_DISCLOSURE.md)

---

<div align="center">

**Govern · execute · prove**

[a-11-oy.com](https://a-11-oy.com) ·
[a11oy.net](https://a11oy.net) ·
[GitHub](https://github.com/szl-holdings)

</div>
