<!-- Organization profile README — rendered at github.com/szl-holdings -->
<!-- Series-A grade. Bounded recursion. Auditable AI by construction. -->

<div align="center">

# SZL Holdings

### Governed AI infrastructure for high-consequence enterprise operations

**Bounded recursion as a system primitive. Proof-chain receipts on every decision. Sub-millisecond audit closure.**

<br/>

[![Research — Ouroboros Thesis](https://img.shields.io/badge/research-Ouroboros%20Thesis-1F78B4?style=for-the-badge&logo=readthedocs&logoColor=white)](https://github.com/szl-holdings/ouroboros-thesis)
[![Runtime — 172/172 tests](https://img.shields.io/badge/runtime-172%2F172%20tests-2DA44E?style=for-the-badge&logo=jest&logoColor=white)](https://github.com/szl-holdings/ouroboros)
[![SDK — @szl-holdings/sdk](https://img.shields.io/badge/SDK-%40szl--holdings%2Fsdk-01696F?style=for-the-badge&logo=npm&logoColor=white)](https://github.com/szl-holdings/szl-sdk)
[![Trust Center](https://img.shields.io/badge/trust-center-C8B26A?style=for-the-badge&logo=letsencrypt&logoColor=white)](https://github.com/szl-holdings/trust)

[![ORCID](https://img.shields.io/badge/ORCID-0009--0001--0110--4173-A6CE39?style=flat-square&logo=orcid&logoColor=white)](https://orcid.org/0009-0001-0110-4173)
[![Concept DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.19944926-01696F?style=flat-square&logo=doi&logoColor=white)](https://doi.org/10.5281/zenodo.19944926)
[![Research license — CC BY 4.0](https://img.shields.io/badge/research-CC%20BY%204.0-1F78B4?style=flat-square)](https://github.com/szl-holdings/ouroboros-thesis/blob/main/LICENSE)
[![Runtime license — Apache 2.0](https://img.shields.io/badge/runtime-Apache%202.0-2DA44E?style=flat-square)](https://github.com/szl-holdings/ouroboros/blob/main/LICENSE)
[![Platform license — BSL 1.1](https://img.shields.io/badge/platform-BSL%201.1-28251D?style=flat-square)](https://github.com/szl-holdings/platform)

[![OpenSSF Scorecard — runtime](https://api.securityscorecards.dev/projects/github.com/szl-holdings/ouroboros/badge)](https://securityscorecards.dev/viewer/?uri=github.com/szl-holdings/ouroboros)
[![OpenSSF Scorecard — thesis](https://api.securityscorecards.dev/projects/github.com/szl-holdings/ouroboros-thesis/badge)](https://securityscorecards.dev/viewer/?uri=github.com/szl-holdings/ouroboros-thesis)
[![Security Policy](https://img.shields.io/badge/security-policy-01696F?style=flat-square&logo=github&logoColor=white)](https://github.com/szl-holdings/.github/security/policy)

</div>

---

## The thesis

Every enterprise AI deployment fails the same diligence question: **"prove what your model decided, why, and that it was within policy."** Most can't. We can. Our runtime emits a **proof-chain receipt** for every decision — bounded loop trace, policy gates traversed, evidence cited, convergence verified — recorded against an audit-closure operator (Λ) with sub-millisecond per-request overhead. The receipt is the deliverable. The loop is the product.

The math is published as a thesis. The runtime is shipped as a library. The fabric is shipped as a platform. Six product surfaces sit on top.

## Architecture

```mermaid
flowchart TD
    classDef research fill:#28251D,stroke:#C8B26A,color:#F7F6F2,stroke-width:1.5px;
    classDef runtime  fill:#1B474D,stroke:#01696F,color:#F7F6F2,stroke-width:1.5px;
    classDef sdk      fill:#0E3A3F,stroke:#C8B26A,color:#F7F6F2,stroke-width:1.5px;
    classDef platform fill:#01696F,stroke:#C8B26A,color:#F7F6F2,stroke-width:1.5px;
    classDef surface  fill:#F7F6F2,stroke:#01696F,color:#1B474D,stroke-width:1.5px;

    T["📄 Ouroboros Thesis<br/>preprints · Zenodo DOIs · CC BY 4.0"]:::research
    R["⚙️ Ouroboros Runtime v6.2.0<br/>bounded loops · 172/172 tests · Apache-2.0"]:::runtime
    L["Λ Audit-Closure Operator<br/>sub-millisecond per-request overhead"]:::runtime
    SDK["📦 @szl-holdings/sdk<br/>public TypeScript SDK · Apache-2.0"]:::sdk
    P["🏛️ Platform<br/>governed AI decision infrastructure · BSL-1.1"]:::platform

    A["A11oy<br/>agentic execution fabric"]:::surface
    AM["Amaru<br/>convergent data sync"]:::surface
    S["Sentra<br/>cyber resilience"]:::surface
    CJ["Carlota Jo<br/>UHNW advisory"]:::surface
    V["Vessels<br/>maritime intel"]:::surface
    TE["Terra<br/>real estate intel"]:::surface
    C["Counsel<br/>legal matter command"]:::surface

    T --> R --> L --> P
    SDK -.public surface.-> P
    P --> A
    P --> AM
    P --> S
    P --> CJ
    P --> V
    P --> TE
    P --> C
```

## Open source pillars

| Pillar | Repo | License | What it is |
|---|---|---|---|
| 📄 **Research** | [`ouroboros-thesis`](https://github.com/szl-holdings/ouroboros-thesis) | CC BY 4.0 | The thesis. Bounded recursive computation as a system primitive. Zenodo DOIs. |
| ⚙️ **Runtime** | [`ouroboros`](https://github.com/szl-holdings/ouroboros) | Apache-2.0 | Reference TypeScript implementation. 172/172 tests passing. Audit-closure operator Λ. |
| 📦 **SDK** | [`szl-sdk`](https://github.com/szl-holdings/szl-sdk) | Apache-2.0 | Public TypeScript SDK. `npm install @szl-holdings/sdk` to integrate with the platform. |
| 🛡️ **Trust** | [`trust`](https://github.com/szl-holdings/trust) | CC BY 4.0 | Public Trust Center. Security disclosures, sub-processors, SOC 2 roadmap, DPA template. |
| 📝 **Engineering** | [`engineering`](https://github.com/szl-holdings/engineering) | CC BY 4.0 | Technical posts on Λ, proof-chain, bounded recursion, governed AI architecture. |

## Product surfaces

| Surface | Repo | Domain |
|---|---|---|
| **A11oy** | [`a11oy`](https://github.com/szl-holdings/a11oy) | Governed agentic execution. Policy gates, proof ledger, human checkpoints. |
| **Amaru** | [`amaru`](https://github.com/szl-holdings/amaru) | Convergent multi-source data sync. Append-only delta logs, hash-verified ingest. |
| **Sentra** | [`sentra`](https://github.com/szl-holdings/sentra) | Cyber resilience. Posture drift, incident response, policy-gated remediation. |
| **Carlota Jo** | [`carlota-jo`](https://github.com/szl-holdings/carlota-jo) | UHNW advisory operations. Concierge workflow with proof-chain delivery. |
| **Vessels** | [`vessels`](https://github.com/szl-holdings/vessels) | Maritime fleet intel. Sanctions screening, dark-vessel detection, ownership graphs. |
| **Terra** | [`terra`](https://github.com/szl-holdings/terra) | Real estate intel. Deal pipeline scoring, AI-assisted underwriting. |
| **Counsel** | [`counsel`](https://github.com/szl-holdings/counsel) | Legal matter command. Document review, obligation mapping, proof-chain delivery. |

## How to engage

- **Builders / integrators** → start with the [SDK](https://github.com/szl-holdings/szl-sdk) and the [runtime](https://github.com/szl-holdings/ouroboros).
- **Researchers** → read the [thesis preprints](https://github.com/szl-holdings/ouroboros-thesis), cite via Zenodo DOI.
- **Security / procurement** → see the [Trust Center](https://github.com/szl-holdings/trust) and our [Security Policy](https://github.com/szl-holdings/.github/security/policy).
- **Enterprise customers** → [stephen@szlholdings.com](mailto:stephen@szlholdings.com)
- **Press / partnerships** → [stephen@szlholdings.com](mailto:stephen@szlholdings.com)

## Operating principles

1. **Bounded recursion is a system primitive.** Convergence is measurable; the loop trace is the audit deliverable.
2. **The receipt is the product.** Every decision emits a proof-chain receipt that downstream audit and procurement can consume.
3. **Policy gates are first-class.** Governance is not a wrapper. It is in the execution path.
4. **Sub-millisecond overhead is the bar.** Λ adds ≤ 0.59 ms median per request across our routes. Measured, not claimed.
5. **DOI-pinned research, SHA-pinned runtime, signed releases.** Provenance is non-negotiable.

---

<div align="center">

**SZL Holdings, LLC** · Founded by [Stephen P. Lutar Jr.](https://orcid.org/0009-0001-0110-4173) · [szlholdings.com](https://szlholdings.com)

[![CITATION.cff](https://img.shields.io/badge/cite-CITATION.cff-blue?style=flat-square)](https://github.com/szl-holdings/ouroboros-thesis/blob/main/CITATION.cff)
[![Software Heritage](https://archive.softwareheritage.org/badge/origin/https://github.com/szl-holdings/ouroboros-thesis/)](https://archive.softwareheritage.org/browse/origin/?origin_url=https://github.com/szl-holdings/ouroboros-thesis)

</div>
