# SZL Holdings

  > Governed AI decision infrastructure for organizations that cannot afford silent failures, invisible risk, or unaccountable AI.

  [![szlholdings.com](https://img.shields.io/badge/web-szlholdings.com-0a0a0a?style=flat-square)](https://szlholdings.com)
  [![CodeQL](https://img.shields.io/badge/CodeQL-passing-2da44e?style=flat-square&logo=github)](https://github.com/szl-holdings/szl-holdings-platform/actions)
  [![Ouroboros tests](https://img.shields.io/badge/ouroboros%20tests-1%2C372%2F1%2C372-2da44e?style=flat-square)](https://github.com/szl-holdings/ouroboros)
  [![Paper v3](https://img.shields.io/badge/paper-v3.0.0%20Lutar%20Invariant-c4356b?style=flat-square)](https://github.com/szl-holdings/ouroboros-thesis/tree/main/papers/v3)
  [![Zenodo v3](https://zenodo.org/badge/DOI/10.5281/zenodo.19951520.svg)](https://doi.org/10.5281/zenodo.19951520)
  [![Government Readiness](https://img.shields.io/badge/NYSTEC%20audit-2026--04--30-2b6cb0?style=flat-square)](https://github.com/szl-holdings/ouroboros/blob/main/docs/audit/szl-government-readiness.md)
  [![License](https://img.shields.io/badge/license-Proprietary-red?style=flat-square)](https://github.com/szl-holdings/szl-holdings-platform/blob/master/LICENSE.md)

  ---

  ## What we build

  A **three-platform stack** — A11oy (orchestration), Sentra (security), Amaru (data sync) — plus four product surfaces (Counsel, Terra, Vessels, Carlota Jo) on top of a shared, replay-safe runtime: the **Ouroboros loop kernel** and **Codex decision-receipt kernel**.

  Every agent action produces a cryptographically traceable receipt, an append-only log, and a primary-source hash. Human approval is enforced at risk tiers R3/R4. Every conclusion can be replayed and verified.

  ## Government readiness scorecard

  April 30, 2026 NYSTEC pre-briefing audit — Empire APEX Accelerator (Mercy McInnis, Procurement Counselor). Full report: [`docs/audit/szl-government-readiness.md`](https://github.com/szl-holdings/ouroboros/blob/main/docs/audit/szl-government-readiness.md).

  | Platform | Governance | Proof Chain | Auditability | Human Oversight | Cert Path | Overall |
  |---|---|---|---|---|---|---|
  | **A11oy**  | ✅ Strong | ✅ Strong | ✅ Strong | ✅ Strong | ⚠️ In progress | **72/100** |
  | **Sentra** | ✅ Strong | ✅ Strong | ✅ Strong | ✅ Strong | ⚠️ Needs SOC 2 | **68/100** |
  | **Amaru**  | ✅ Strong | ✅ Strong | ✅ Strong | ✅ Strong | ⚠️ Needs privacy docs | **65/100** |

  ### NIST AI RMF — full coverage across all four functions

  | Function | A11oy | Sentra | Amaru |
  |---|---|---|---|
  | **GOVERN**  | Validator registry, loop policy, operator modes | Risk tier governance | Source priority + merge safety |
  | **MAP**     | Domain pack router, task-type routing | Threat loop profiles | Schema variant mapping |
  | **MEASURE** | Delta, consistency, uncertainty per step | Risk tier scoring | Consistency scoring |
  | **MANAGE**  | Approval gate, halt conditions, replay | Evidence packs, escalation | Conflict reconciliation |

  ### DoD Responsible AI Tenets — 4 of 5 covered

  | Tenet | Status |
  |---|---|
  | Responsible | ✅ Human approval at R3/R4, validator hard stops |
  | Equitable   | ⚠️ Bias-testing methodology in 30-day roadmap |
  | Traceable   | ✅ Full trace runtime, append-only logs, receipts |
  | Reliable    | ✅ Golden runs, replay verification, consistency gates |
  | Governable  | ✅ Approval gate, halt conditions, operational modes |

  ### GSAR 552.239-7001 (proposed) — 5 of 10 covered, 5 documented gaps

  Covered: human oversight, summarized intermediate processing, model routing rationale, RAG source attribution, complete audit trail. Gaps (all documentation, no architectural rework needed): NIST AI RMF written documentation, 72-hour incident reporting procedure, no-cross-customer-training contractual commitment, American AI Systems vendor disclosure, formal bias audit plan.

  ---

  ## Repositories

  ### Runtime + thesis

  | Repo | Purpose | Status |
  |---|---|---|
  | [`ouroboros`](https://github.com/szl-holdings/ouroboros) | `@szl-holdings/ouroboros` v6.1.0 — bounded-loop runtime implementing the Lutar Invariant Λ across nine axes | **1,372/1,372 tests** passing (925 TS + 447 Py) |
  | [`ouroboros-thesis`](https://github.com/szl-holdings/ouroboros-thesis) | Architectural rationale + v6 operational contract JSON. **v3 paper** — [The Lutar Invariant](https://doi.org/10.5281/zenodo.19951520) | v3 published 2026-05-01 |

  ### Three-platform stack

  | Repo | Purpose | Readiness |
  |---|---|---|
  | [`a11oy`](https://github.com/szl-holdings/a11oy)   | Orchestration control plane — agent ecosystem brain, validator registry, approval gate | **72/100** |
  | [`sentra`](https://github.com/szl-holdings/sentra) | Governed security and threat intelligence — recursive threat modeling, evidence packs | **68/100** |
  | [`amaru`](https://github.com/szl-holdings/amaru)   | Convergent data sync and reconciliation — append-only delta log, consistency gates | **65/100** |

  ### Domain product surfaces

  | Repo | Purpose |
  |---|---|
  | [`counsel`](https://github.com/szl-holdings/counsel)       | Legal matter command — policy-gated human review |
  | [`terra`](https://github.com/szl-holdings/terra)           | NYC distress pipeline + AI-assisted real-estate workflow |
  | [`vessels`](https://github.com/szl-holdings/vessels)       | Maritime fleet intelligence — sanctions screening, dark-vessel detection |
  | [`carlota-jo`](https://github.com/szl-holdings/carlota-jo) | Premium UHNW advisory operations portal with Proof-Chain delivery |

  ### Platform monorepo

  [`szl-holdings-platform`](https://github.com/szl-holdings/szl-holdings-platform) — full monorepo. Latest release: [`v1.0.2-codex-kernel`](https://github.com/szl-holdings/szl-holdings-platform/releases) (2026-04-30).

  ---

  ## Security & supply-chain posture

  - **Dependabot alerts**: 0 open across all 11 org repositories.
  - **CodeQL**: enabled on the platform monorepo, all checks passing.
  - **Dependency hygiene**: 3 dependabot PRs merged this cycle (react-ecosystem, vite-build, ui-components in progress).
  - **CMMC / FedRAMP / SOC 2**: roadmap items, disclosed in audit; NIST SP 800-171 gap assessment scoped.

  ---

  ## Contact

  [szlholdings.com](https://szlholdings.com) · [inquiries@szlholdings.com](mailto:inquiries@szlholdings.com) · [LinkedIn](https://linkedin.com/in/stephen-l-279315240)

  © 2026 SZL Holdings. All rights reserved.
  