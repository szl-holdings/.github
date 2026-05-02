# SZL Holdings

  > Governed runtime infrastructure for AI-assisted decisions.

  [![Ouroboros tests](https://img.shields.io/badge/ouroboros%20tests-150%20declared-2da44e?style=flat-square)](https://github.com/szl-holdings/ouroboros)
  [![Paper v3](https://img.shields.io/badge/paper-v3.0.0%20Lutar%20Invariant-c4356b?style=flat-square)](https://github.com/szl-holdings/ouroboros-thesis/tree/main/papers/v3)
  [![Zenodo v3](https://zenodo.org/badge/DOI/10.5281/zenodo.19951520.svg)](https://doi.org/10.5281/zenodo.19951520)

  ---

  ## What is here

  The shipped, open-source piece is the **Ouroboros runtime** — `@szl-holdings/ouroboros` v6.1.0 — a bounded-loop runtime that implements the **Lutar Invariant Λ**, a closed-form scalar in [0, 1] that aggregates nine independent runtime-trust axes (Cleanliness, Horizon, Resonance, Frustum, Geometry, Invariance, Moral, Being, Non-measurability) into a single auditable number.

  The companion thesis ([`ouroboros-thesis`](https://github.com/szl-holdings/ouroboros-thesis)) carries the v1 position paper, the v2 empirical companion, and the v3 closed-form scalar law with its uniqueness proof under four axioms. Each version has a Zenodo DOI.

  Everything else in this org is at varying earlier stages of work.

  ---

  ## Repositories

  ### Runtime + thesis (shipped, open-source)

  | Repo | Purpose | Status |
  |---|---|---|
  | [`ouroboros`](https://github.com/szl-holdings/ouroboros) | `@szl-holdings/ouroboros` v6.1.0 — bounded-loop runtime implementing the Lutar Invariant Λ | **150 declared Vitest tests** in the single `ouroboros` package |
  | [`ouroboros-thesis`](https://github.com/szl-holdings/ouroboros-thesis) | v1 position paper, v2 empirical companion, v3 closed-form scalar law + v6 operational contract JSON | v3 published 2026-05-01 ([DOI](https://doi.org/10.5281/zenodo.19951520)) |

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
