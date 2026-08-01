---
title: SZL Holdings — Governed Decision Infrastructure
emoji: 🛡️
colorFrom: gray
colorTo: indigo
sdk: static
short_description: Governed AI that can explain, constrain, and verify action
thumbnail: https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp
pinned: true
license: apache-2.0
---

<!-- markdownlint-disable MD013 MD033 MD041 -->

<p align="center">
  <img src="https://huggingface.co/spaces/SZLHOLDINGS/README/resolve/main/assets/evidence-lattice-v2.webp"
       alt="A bounded signal path entering a holographic verification lattice"
       width="100%" />
</p>

<div align="center">

## Models, data, and demonstrations with explicit boundaries

SZL Holdings publishes the artifact layer for governed systems that must
reason, act within authority, and return evidence another party can verify.

[**Enter a11oy →**](https://a-11-oy.com) ·
[**Verify evidence →**](https://a11oy.net) ·
[**Inspect source →**](https://github.com/szl-holdings) ·
[**Read the docs →**](https://holdings.a-11-oy.com/docs-site/)

</div>

---

## Start with the artifact you need

| Need | Canonical artifact | Boundary |
| --- | --- | --- |
| Propose governed receipts | [SZL-Forge-1.5B-ReceiptAgent](https://huggingface.co/SZLHOLDINGS/SZL-Forge-1.5B-ReceiptAgent) | A model artifact; autonomy requires a separately validating controller |
| Navigate the estate with cited retrieval | [SZL-Khipu-1.5B](https://huggingface.co/SZLHOLDINGS/SZL-Khipu-1.5B) | Verify retrieved sources independently |
| Evaluate a local quantization | [SZL-Khipu-1.5B-GGUF](https://huggingface.co/SZLHOLDINGS/SZL-Khipu-1.5B-GGUF) | Evaluate the exact quantized file and runtime |
| Inspect receipt and evidence records | [szl-lake](https://huggingface.co/datasets/SZLHOLDINGS/szl-lake) | Each record carries its own provenance and admission scope |
| Study the operator research corpus | [killinchu-osint-corpus](https://huggingface.co/datasets/SZLHOLDINGS/killinchu-osint-corpus) | Public-source research, not an operational intelligence feed |
| Explore the governed command surface | [a11oy Space](https://huggingface.co/spaces/SZLHOLDINGS/a11oy) | Demonstration reachability and operational capability are separate claims |

Download counters are Hub-reported events, not unique users, deployments,
customers, model quality, or revenue.

## One governed loop

```text
signal → reason → policy → bounded action → receipt → independent verification
                     ↑                                      │
                     └──────────── verified feedback ───────┘
```

The model proposes. A separately named policy layer validates authority and
evidence. The runtime executes only within a declared bound. The receipt lets a
separate party inspect what happened.

## The publication contract

| Artifact class | Required evidence | Does not imply |
| --- | --- | --- |
| **Trained weights** | Base and license lineage, hashes, clean load, held-out evaluation, restart reproduction, resource envelope | Autonomous authority or production readiness |
| **Datasets** | Sources, licenses, schema, splits, consent and PII posture, validation, quarantine, gaps, update policy | Training admission or universal reuse rights |
| **Kernels and tools** | Canonical source revision, hardware matrix, executable tests, benchmark protocol | Model training, capability, or safety |
| **Spaces** | Source revision, dependency pins, privacy behavior, limitations, local reproduction, served-revision binding | Production deployment or current capability |

A model card is documentation, not operational proof. A Space in `RUNNING`
state proves transport availability only. A signed receipt establishes
integrity and origin within its stated scope; it does not automatically
establish correctness, safety, performance, or authorization to operate.

## Evidence language

Claims use **PROVED**, **MEASURED**, **REPORTED**, **MODELED**,
**CONJECTURE**, or **ROADMAP**. Runtime status is a separate axis:
**OPERATIONAL**, **PARTIAL**, **DEGRADED**, **UNAVAILABLE**, or
**HISTORICAL**.

Lambda uniqueness remains **Conjecture 1**, not a theorem. No artifact is
promoted solely because it has a card, a counter, a live route, or a filename
that sounds like a model.

## Reproduce and inspect

This front door is source-controlled in
[`szl-holdings/.github`](https://github.com/szl-holdings/.github/tree/main/huggingface/org-card)
and published from an exact protected Git revision. The running static Space
exposes the served revision and managed file hashes in
[`deployment.json`](https://szlholdings-readme.static.hf.space/deployment.json).

Run the static surface locally from a checkout:

```bash
python -m http.server 8000 --directory huggingface/org-card
```

- [Security policy](https://github.com/szl-holdings/.github/security/policy)
- [Trust posture](https://github.com/szl-holdings/.github/blob/main/TRUST.md)
- [Support](https://github.com/szl-holdings/.github/blob/main/SUPPORT.md)
- [Honest disclosure](./HONEST_DISCLOSURE.md)

---

<div align="center">

Govern · execute · prove

[a-11-oy.com](https://a-11-oy.com) ·
[a11oy.net](https://a11oy.net) ·
[GitHub](https://github.com/szl-holdings)

</div>
