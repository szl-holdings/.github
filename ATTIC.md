# ATTIC — SZL Holdings archived-repository index

<!-- GENERATED FILE — do not edit by hand. -->
<!-- Regenerate: python scripts/build_attic_index.py --write -->

Every public archived repository in the `szl-holdings` organization, mapped to the canonical repository that superseded it. Generated from the live GitHub API, never hand-maintained, so the index cannot drift from the public estate.

**Doctrine.** Honest UNKNOWN over fabricated green: an archived repo with no discoverable successor appears below as UNKNOWN and requires an owner decision. This index never invents a plausible-looking successor.

## Estate shape

| Metric | Count |
|---|---:|
| Public repositories total | 95 |
| Active public repositories | 61 |
| Archived public repositories (tombstones) | 34 |
| Tombstones with a resolved successor | 27 |
| Tombstones terminal by design | 2 |
| Tombstones with UNKNOWN successor | 5 |
| Structural defects | 0 |

## Resolved tombstones

| Archived repo | Canonical successor | Language | Last push |
|---|---|---|---|
| `cosmos` | [`anatomy`](https://github.com/szl-holdings/anatomy) | JavaScript | 2026-08-29 |
| `counsel` | [`ayllu`](https://github.com/szl-holdings/ayllu) | Python | 2026-08-29 |
| `david-leads` | [`a11oy`](https://github.com/szl-holdings/a11oy) | Python | 2026-08-28 |
| `docs-site` | [`a11oy-net`](https://github.com/szl-holdings/a11oy-net) | JavaScript | 2026-08-28 |
| `energy-attest-holo` | [`szl-energy-attest`](https://github.com/szl-holdings/szl-energy-attest) | Python | 2026-08-18 |
| `governed-norm-holo` | [`szl-governed-norm`](https://github.com/szl-holdings/szl-governed-norm) | Python | 2026-08-29 |
| `holographic-unify` | [`a11oy`](https://github.com/szl-holdings/a11oy) | TypeScript | 2026-08-29 |
| `immune-lattice` | [`immune`](https://github.com/szl-holdings/immune) | TypeScript | 2026-08-29 |
| `khipu-lab` | [`szl-khipu`](https://github.com/szl-holdings/szl-khipu) | TypeScript | 2026-08-29 |
| `khipu-pages` | [`szl-khipu`](https://github.com/szl-holdings/szl-khipu) | HTML | 2026-08-29 |
| `lambda-gate-holo` | [`szl-lambda-gate`](https://github.com/szl-holdings/szl-lambda-gate) | Python | 2026-08-29 |
| `lean-kernel` | [`lutar-lean`](https://github.com/szl-holdings/lutar-lean) | Python | 2026-08-28 |
| `ouroboros` | [`szl-ouroboros`](https://github.com/szl-holdings/szl-ouroboros) | TypeScript | 2026-08-28 |
| `receipt-chain-live` | [`szl-receipt`](https://github.com/szl-holdings/szl-receipt) | Python | 2026-08-26 |
| `szl-atelier` | [`szl-forge`](https://github.com/szl-holdings/szl-forge) | Python | 2026-08-29 |
| `szl-build-env` | [`szl-forge`](https://github.com/szl-holdings/szl-forge) | Python | 2026-08-28 |
| `szl-cookbook` | [`szl-forge`](https://github.com/szl-holdings/szl-forge) | TypeScript | 2026-08-26 |
| `szl-experiments` | [`a11oy`](https://github.com/szl-holdings/a11oy) | Python | 2026-08-29 |
| `szl-fleet-overlay` | [`killinchu`](https://github.com/szl-holdings/killinchu) | Python | 2026-08-26 |
| `szl-formula-ledger` | [`lutar-lean`](https://github.com/szl-holdings/lutar-lean) | Python | 2026-07-22 |
| `szl-kernels-live` | [`szl-kernels`](https://github.com/szl-holdings/szl-kernels) | Python | 2026-08-18 |
| `szl-mesh` | [`szl-substrate`](https://github.com/szl-holdings/szl-substrate) | Python | 2026-08-26 |
| `szl-organ-integrity` | [`a11oy`](https://github.com/szl-holdings/a11oy) | HTML | 2026-08-29 |
| `szl-provctl-live` | [`szl-provctl`](https://github.com/szl-holdings/szl-provctl) | Python | 2026-08-18 |
| `szl-router` | [`a11oy`](https://github.com/szl-holdings/a11oy) | Python | 2026-08-26 |
| `szl-telemetry` | [`szl-substrate`](https://github.com/szl-holdings/szl-substrate) | Python | 2026-08-29 |
| `vsp-otel` | [`szl-substrate`](https://github.com/szl-holdings/szl-substrate) | TypeScript | 2026-08-26 |

## Terminal by design (no successor)

| Archived repo | Why it has no successor |
|---|---|
| `evidence-typed-formula-governance` | Archival preprint + reproducibility package. Immutable by design — a published record must not be superseded in place. |
| `fail-closed-governed-ai-services` | Archival preprint + reproducibility package. Immutable by design — a published record must not be superseded in place. |

## ⚠️ UNKNOWN successor — owner decision required

These archived repositories carry no `Canonical:` pointer and are not declared terminal. Each needs one of: a successor pointer added to its description, or an entry in `TERMINAL_BY_DESIGN` in the generator explaining why it is terminal. **They are reported, not guessed.**

| Archived repo | Description | Last push |
|---|---|---|
| `developers` | Build on SZL — developer hub: API reference for all 5 flagships, 5-min quickstart, MCP integration (Claude/... | 2026-07-29 |
| `szl-otel-mesh` | szl-otel-mesh — UDS cross-component OTel span schemas + DSSE governance receipts onto Khipu Merkle DAG. Lay... | 2026-07-17 |
| `szl-uds-deployment` | Live UDS governance-receipt deployment (Warhacker 2026) — k3d + uds-cli + Pepr DSSE receipt policy, cosign-... | 2026-07-01 |
| `uds-bundles` | SZL UDS Zarf bundles for the two products (a11oy + killinchu) and their capability services — airgap-deploy... | 2026-06-30 |
| `warhacker-demo` | SOVEREIGN Warhacker demo dry-run for the RTX 4060 Ti tower: one-command tower verification, GPU k3d + UDS d... | 2026-07-21 |

---

Generated by `scripts/build_attic_index.py`. CI runs `--check` so this file cannot silently drift from the live public estate.
