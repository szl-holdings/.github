<!-- markdownlint-disable MD013 MD033 MD041 -->

<div align="center">

<img src="./assets/evidence-lattice-v2.webp"
     alt="A bounded signal path entering a holographic verification lattice"
     width="100%" />

# Governed AI for decisions that must survive scrutiny

SZL Holdings builds systems that can reason, act within authority, and return
evidence that another party can verify.

[**Evaluate the company**](#investor-path) |
[**Build with SZL**](#developer-path) |
[**Inspect models and data**](https://huggingface.co/SZLHOLDINGS) |
[**Check current state**](#current-state)

</div>

---

## Start with your question

<table>
<tr>
<td width="33%" valign="top">

<strong>Investor</strong><br><br>
Understand the category, product boundaries, research lineage, and trust
posture.

<a href="#investor-path">Evaluate the company -></a>

</td>
<td width="33%" valign="top">

<strong>Developer</strong><br><br>
Choose an artifact class, inspect its contract, and reproduce the integration
path.

<a href="#developer-path">Build with SZL -></a>

</td>
<td width="33%" valign="top">

<strong>Evaluator</strong><br><br>
Separate evidence, runtime state, and authorization before drawing a
conclusion.

<a href="#current-state">Inspect current evidence -></a>

</td>
</tr>
</table>

## The company

AI capability is moving faster than institutional control. SZL focuses on the
boundary between a model recommendation and an authorized action:

```text
signal -> reason -> policy -> bounded action -> receipt -> independent verification
                    ^                                      |
                    +------------ verified feedback -------+
```

The model proposes. A controller validates policy, authority, and evidence.
The runtime acts only inside a declared bound. A portable receipt lets another
party inspect what happened.

### Products

| Product | Public role | Reality boundary | Enter |
| --- | --- | --- | --- |
| **a11oy** | Governed inference and agentic execution for regulated workflows | Product reachability, provider availability, signing, and per-action readiness are separate states | [Product](https://a-11-oy.com) / [Source](https://github.com/szl-holdings/a11oy) |
| **Killinchu** | Counter-UAS and maritime observation, fusion, and operator-decision demonstration | Public feeds may be live or unavailable; sample fallbacks are labeled; effectors and public actuation are **SIMULATED** | [Operator application](https://szlholdings-killinchu.hf.space/elite) / [Source](https://github.com/szl-holdings/killinchu) |

The [Killinchu Common Operating Picture](https://szlholdings-killinchu.hf.space/elite/cop)
is an observation and decision-support surface. It can exercise real public-feed
ingestion, fusion, provenance, and receipt paths when their dependencies answer.
It does not command a live weapon or represent production authorization.

## Artifact map

Hugging Face repository type does not establish artifact type. The portfolio
uses these boundaries:

| Artifact class | What it is | Representative entry | What it is not |
| --- | --- | --- | --- |
| **Trained weights and adapters** | Neural weights, adapters, or quantized files with their own lineage and evaluation | [SZL-Khipu-1.5B](https://huggingface.co/SZLHOLDINGS/SZL-Khipu-1.5B) | Automatic proof of quality, safety, or production readiness |
| **Software and substrate artifacts** | Source, manifests, kernels, meters, or governance packages published through a model-shaped repository | [a11oy-v19-substrate](https://huggingface.co/SZLHOLDINGS/a11oy-v19-substrate) | Trained model weights |
| **Surrogates and recipes** | Small structural classifiers, compatibility artifacts, or model recipes | [szl-governed-norm](https://huggingface.co/SZLHOLDINGS/szl-governed-norm) | A substitute for the governed runtime or upstream foundation model |
| **Datasets and evidence** | Corpora, receipts, evaluations, manifests, proofs, and historical snapshots | [szl-lake](https://huggingface.co/datasets/SZLHOLDINGS/szl-lake) | Automatic admission for training, deployment, or a performance claim |
| **Spaces and demonstrations** | Public interfaces, verifiers, consoles, and status surfaces | [SZL Holdings README Space](https://huggingface.co/spaces/SZLHOLDINGS/README) | End-to-end operational proof merely because transport is reachable |

Each artifact owns its exact license, lineage, hashes, evaluation, runtime,
privacy, and limitation evidence. Hub download events are not treated as unique
users, customers, deployments, revenue, or model quality.

## Investor path

1. Read the [public company front door](https://huggingface.co/spaces/SZLHOLDINGS/README).
2. Inspect the [product and evidence registry](https://a11oy.net).
3. Follow the [research lineage](https://github.com/szl-holdings/szl-papers).
4. Review [security](https://github.com/szl-holdings/.github/security/policy),
   [trust](https://github.com/szl-holdings/.github/blob/main/TRUST.md), and
   [support](https://github.com/szl-holdings/.github/blob/main/SUPPORT.md).
5. Confirm current runtime state from the linked sources below rather than a
   screenshot, badge, card, or cached count.

No production authorization, regulatory approval, universal safety guarantee,
customer adoption, or investment outcome is claimed by this profile.

## Developer path

1. Read the [documentation hub](https://holdings.a-11-oy.com/docs-site/).
2. Start with the [a11oy source](https://github.com/szl-holdings/a11oy) and its
   declared architecture and policy boundaries.
3. Emit or verify a receipt with
   [`szl-receipt`](https://github.com/szl-holdings/szl-receipt).
4. Add governed tools through
   [Hatun MCP](https://github.com/szl-holdings/hatun-mcp).
5. Inspect shared runtime packages in
   [`szl-substrate`](https://github.com/szl-holdings/szl-substrate).
6. Select model, dataset, or Space artifacts from the
   [Hugging Face organization](https://huggingface.co/SZLHOLDINGS) only after
   reading the artifact-specific card and files.

Organization-wide public conventions are defined in the
[public experience standard](https://github.com/szl-holdings/.github/blob/main/docs/PUBLIC_EXPERIENCE_STANDARD.md).
Repository lifecycle and canonical successors are recorded in the
[estate lifecycle map](https://github.com/szl-holdings/.github/blob/main/docs/ESTATE_LIFECYCLE.md).

## Current state

Status is linked, not copied into this profile. These sources can change without
a profile edit:

| Question | Current source |
| --- | --- |
| Which Hugging Face front door is canonical? | [SZLHOLDINGS/README](https://huggingface.co/spaces/SZLHOLDINGS/README) |
| Which source revision produced the served org card? | [Org-card deployment evidence](https://szlholdings-readme.static.hf.space/deployment.json) |
| Is a11oy ready at this moment? | [a11oy readiness](https://a-11-oy.com/api/a11oy/v1/readiness) |
| Which Killinchu revision is served? | [Killinchu build identity](https://szlholdings-killinchu.hf.space/api/build-info) |
| Is the Killinchu public-risk gate available? | [Killinchu public-risk status](https://szlholdings-killinchu.hf.space/api/public-risk-status) |
| Is the Killinchu service ready? | [Killinchu readiness](https://szlholdings-killinchu.hf.space/api/killinchu/readyz) |

The dataset [`SZLHOLDINGS/SZLHOLDINGS`](https://huggingface.co/datasets/SZLHOLDINGS/SZLHOLDINGS)
is a **HISTORICAL profile mirror**. It is not the current organization card and
must not be used to infer the present estate, inventory, or runtime state.

## Evidence language

Public claims and operational state remain separate axes.

| Evidence class | Meaning |
| --- | --- |
| **PROVED** | Machine-checked statement with exact theorem and artifact scope |
| **MEASURED** | Direct observation with instrument, time, and context |
| **REPORTED** | Identified upstream statement, not independently measured here |
| **MODELED** | Simulation, projection, or analytical derivation |
| **CONJECTURE** | Open hypothesis; never rendered as proved |
| **ROADMAP** | Planned work with no operational claim |

Operational states are **OPERATIONAL**, **PARTIAL**, **DEGRADED**,
**UNAVAILABLE**, and **HISTORICAL**. Lambda uniqueness remains
**Conjecture 1**, not a theorem; consult the canonical proof sources for current
scope and revision.

Reachability is not capability. A signed receipt proves integrity and origin
within its stated scope; it does not automatically prove accuracy, safety,
performance, compliance, or authorization to deploy.

---

<div align="center">

Govern | execute | prove

[a-11-oy.com](https://a-11-oy.com) |
[a11oy.net](https://a11oy.net) |
[Documentation](https://holdings.a-11-oy.com/docs-site/) |
[GitHub](https://github.com/szl-holdings) |
[Hugging Face](https://huggingface.co/SZLHOLDINGS)

</div>
