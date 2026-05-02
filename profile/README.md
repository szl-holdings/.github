# SZL Holdings

  > Governed runtime infrastructure for AI-assisted decisions.

  [![Ouroboros tests](https://img.shields.io/badge/ouroboros%20tests-150%20declared-2da44e?style=flat-square)](https://github.com/szl-holdings/ouroboros)
  [![Paper v2 (empirical)](https://img.shields.io/badge/paper-v2.0.0%20empirical-805ad5?style=flat-square)](https://github.com/szl-holdings/ouroboros-thesis/tree/main/v2)
  [![Zenodo v2](https://zenodo.org/badge/DOI/10.5281/zenodo.19934129.svg)](https://doi.org/10.5281/zenodo.19934129)
  [![Zenodo v1](https://zenodo.org/badge/DOI/10.5281/zenodo.19867281.svg)](https://doi.org/10.5281/zenodo.19867281)

  ---

  ## What is here

  The shipped, open-source piece is the **Ouroboros runtime** — `@szl-holdings/ouroboros` v6.1.0 — a bounded-loop runtime with measurable convergence as a system primitive. It ships the loop kernel, depth allocator, consistency scoring, proof-route resolver, risk-tier escalation gate, almanac cycle advancer, the v6 ecosystem layer (services, halts, routing, permissions, sandbox, agent registry), and a structured government-procurement readiness module. **150 declared Vitest tests pass** at v6.1.0.

  The companion thesis ([`ouroboros-thesis`](https://github.com/szl-holdings/ouroboros-thesis)) carries the v1 position paper and the v2 empirical companion. Each has a Zenodo DOI. v3 (Lutar Invariant) was retracted by the author on 2026-05-02 after a self-audit found overstated implementation and commercial claims; a rewritten v3 containing only verifiable claims is in preparation.

  Everything else in this org is at varying earlier stages of work.

  ---

  ## Repositories

  ### Runtime + thesis (shipped, open-source)

  | Repo | Purpose | Status |
  |---|---|---|
  | [`ouroboros`](https://github.com/szl-holdings/ouroboros) | `@szl-holdings/ouroboros` v6.1.0 — bounded-loop runtime, v6 ecosystem layer, government-readiness module | **150 declared Vitest tests** in the single `ouroboros` package |
  | [`ouroboros-thesis`](https://github.com/szl-holdings/ouroboros-thesis) | v1 position paper, v2 empirical companion, v6 operational contract JSON | v2 published 2026-04-30 ([DOI](https://doi.org/10.5281/zenodo.19934129)); v3 retracted 2026-05-02 |

  ### Product surfaces (varying stages)

  | Repo | Stage |
  |---|---|
  | [`a11oy`](https://github.com/szl-holdings/a11oy) | Public repo, README-stage |
  | [`sentra`](https://github.com/szl-holdings/sentra) | Public repo, README-stage |
  | [`amaru`](https://github.com/szl-holdings/amaru) | Public repo, README-stage |
  | [`counsel`](https://github.com/szl-holdings/counsel) | Public repo, README-stage |
  | [`terra`](https://github.com/szl-holdings/terra) | Public repo, README-stage |
  | [`vessels`](https://github.com/szl-holdings/vessels) | Public repo, README-stage |
  | [`carlota-jo`](https://github.com/szl-holdings/carlota-jo) | Public repo, README-stage |

  ### Platform monorepo

  [`szl-holdings-platform`](https://github.com/szl-holdings/szl-holdings-platform) — public monorepo, in active development. CI is currently flaky on master.

  ---

  ## Architecture principles

  - **AI governance by design.** Advisory agents cannot execute consequential actions without explicit human confirmation.
  - **Evidence-backed decisions.** Every recommendation includes source citations and retrieval provenance.
  - **Explicit over implicit.** Platform state is visible. No silent fallbacks. Failures surface.

  ---

  ## Contact

  [stephenlutar2@gmail.com](mailto:stephenlutar2@gmail.com) · [ORCID 0009-0001-0110-4173](https://orcid.org/0009-0001-0110-4173) · [LinkedIn](https://linkedin.com/in/stephen-l-279315240)

  © 2026 SZL Holdings.
