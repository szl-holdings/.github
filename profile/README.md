# SZL Holdings

  > A Series-A holding company building governed AI-augmented control surfaces across seven domains, all powered by the **Ouroboros runtime** — bounded loops with measurable convergence.

  ## Portfolio

  | Product | Domain | Proof Route | Repository |
  | --- | --- | --- | --- |
  | **Amaru** | Multi-source data sync | `PRF_DATA_SYNC` | [`amaru`](https://github.com/szl-holdings/amaru) |
  | **A11oy** | Cross-domain agent fabric | `PRF_SYSTEM_CLAIMS` | [`a11oy`](https://github.com/szl-holdings/a11oy) |
  | **Sentra** | Cyber resilience command | `PRF_SECURITY_ACTIONS` | [`sentra`](https://github.com/szl-holdings/sentra) |
  | **Counsel** | Legal matter command | `PRF_SYSTEM_CLAIMS` | [`counsel`](https://github.com/szl-holdings/counsel) |
  | **Terra** | Real-estate intelligence | `PRF_SYSTEM_CLAIMS` | [`terra`](https://github.com/szl-holdings/terra) |
  | **Vessels** | Maritime fleet intelligence | `PRF_SYSTEM_CLAIMS` | [`vessels`](https://github.com/szl-holdings/vessels) |
  | **Carlota Jo** | Premium UHNW advisory ops | `PRF_SYSTEM_CLAIMS` | [`carlota-jo`](https://github.com/szl-holdings/carlota-jo) |

  ## Foundations

  - 📜 **[`ouroboros-thesis`](https://github.com/szl-holdings/ouroboros-thesis)** — the architectural rationale (full v2 thesis + operational contract JSON)
  - 🔁 **[`ouroboros`](https://github.com/szl-holdings/ouroboros)** — the runtime: loop kernel, depth allocator, consistency, proof-route resolver, risk-tier escalation gate, almanac cycle advancer
  - 🏛 **[`szl-holdings-platform`](https://github.com/szl-holdings/szl-holdings-platform)** — the canonical pnpm monorepo (private; the seven product repos above are public mirrors of their READMEs)

  ## Operational substrate

  Every commit-bearing decision in every product binds to:

  1. a **decision receipt** (replayable, hash-verified),
  2. a **proof route** (`PRF_SYSTEM_CLAIMS` / `PRF_SECURITY_ACTIONS` / `PRF_DATA_SYNC`),
  3. a **risk tier** (R1 → R4, with R3 gating manual approval and R4 force-escalating),
  4. an **almanac cycle position** (Madrid 1, Paris 3, Grolier 2 — bounded periodic coordination).

  The `/api/healthz` endpoint exposes a deployment health contract that probes each subsystem and degrades the service to advisory mode when any critical check fails.

  ---

  © 2026 SZL Holdings. All rights reserved.
  