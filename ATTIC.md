# ATTIC — SZL Holdings archived-repository index

<!-- GENERATED FILE — do not edit by hand. -->
<!-- Regenerate: python scripts/build_attic_index.py --write -->

Every public archived repository in the `szl-holdings` organization, mapped to the canonical repository that superseded it. Generated from the live GitHub API, never hand-maintained, so the index cannot drift from the public estate.

**Doctrine.** Honest UNKNOWN over fabricated green: an archived repo with no discoverable successor appears below as UNKNOWN and requires an owner decision. This index never invents a plausible-looking successor.

## Estate shape

| Metric | Count |
|---|---:|
| Public repositories total | 95 |
| Active public repositories | 60 |
| Archived public repositories (tombstones) | 35 |
| Tombstones with a resolved successor | 28 |
| Tombstones terminal by design | 6 |
| Tombstones with UNKNOWN successor | 1 |
| Structural defects | 0 |

## Resolved tombstones

| Archived repo | Canonical successor | Language | Last push |
|---|---|---|---|
| `cosmos` | [`anatomy`](https://github.com/szl-holdings/anatomy) | JavaScript | 2026-08-29 |
| `counsel` | [`ayllu`](https://github.com/szl-holdings/ayllu) | Python | 2026-08-29 |
| `david-leads` | [`a11oy`](https://github.com/szl-holdings/a11oy) | Python | 2026-08-28 |
| `developers` | [`a11oy-net`](https://github.com/szl-holdings/a11oy-net) | HTML | 2026-07-29 |
| `docs-site` | [`a11oy-net`](https://github.com/szl-holdings/a11oy-net) | JavaScript | 2026-08-28 |
| `energy-attest-holo` | [`szl-energy-attest`](https://github.com/szl-holdings/szl-energy-attest) | Python | 2026-08-18 |
| `governed-inference-meter` | [`szl-energy-attest`](https://github.com/szl-holdings/szl-energy-attest) | Python | 2026-08-30 |
| `governed-norm-holo` | [`szl-lambda-gate`](https://github.com/szl-holdings/szl-lambda-gate) | Python | 2026-08-29 |
| `holographic-unify` | [`a11oy`](https://github.com/szl-holdings/a11oy) | TypeScript | 2026-08-29 |
| `immune-lattice` | [`immune`](https://github.com/szl-holdings/immune) | TypeScript | 2026-08-29 |
| `khipu-lab` | [`szl-khipu`](https://github.com/szl-holdings/szl-khipu) | TypeScript | 2026-08-29 |
| `khipu-pages` | [`szl-khipu`](https://github.com/szl-holdings/szl-khipu) | HTML | 2026-08-29 |
| `lambda-gate-holo` | [`szl-lambda-gate`](https://github.com/szl-holdings/szl-lambda-gate) | Python | 2026-08-29 |
| `lean-kernel` | [`lutar-lean`](https://github.com/szl-holdings/lutar-lean) | Python | 2026-08-28 |
| `ouroboros` | [`platform`](https://github.com/szl-holdings/platform) | TypeScript | 2026-08-28 |
| `receipt-chain-live` | [`szl-receipt`](https://github.com/szl-holdings/szl-receipt) | Python | 2026-08-26 |
| `szl-build-env` | [`szl-forge`](https://github.com/szl-holdings/szl-forge) | Python | 2026-08-28 |
| `szl-cookbook` | [`szl-forge`](https://github.com/szl-holdings/szl-forge) | TypeScript | 2026-08-31 |
| `szl-experiments` | [`a11oy`](https://github.com/szl-holdings/a11oy) | Python | 2026-08-29 |
| `szl-formula-ledger` | [`lutar-lean`](https://github.com/szl-holdings/lutar-lean) | Python | 2026-07-22 |
| `szl-governed-norm` | [`szl-lambda-gate`](https://github.com/szl-holdings/szl-lambda-gate) | Python | 2026-08-08 |
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
| `szl-fleet-overlay` | Frozen WarHacker-2026 UDS fleet-overlay evidence snapshot. Retained for provenance; it has no active software successor. |
| `szl-otel-mesh` | Published OpenTelemetry/DSSE research artifact with DOI 10.5281/zenodo.20434276. Immutable archival evidence by design. |
| `szl-uds-deployment` | Frozen WarHacker-2026 UDS deployment evidence snapshot. Retained for reproducibility; it has no active software successor. |
| `warhacker-demo` | One-off WarHacker-2026 hardware and air-gap dry-run snapshot. The archived demonstration is retained as evidence, not a maintained product. |

## ⚠️ UNKNOWN successor — owner decision required

These archived repositories carry no `Canonical:` pointer and are not declared terminal. Each needs one of: a successor pointer added to its description, or an entry in `TERMINAL_BY_DESIGN` in the generator explaining why it is terminal. **They are reported, not guessed.**

| Archived repo | Description | Last push |
|---|---|---|
| `uds-bundles` | SZL UDS Zarf bundles for the two products (a11oy + killinchu) and their capability services — airgap-deploy... | 2026-06-30 |

---

Generated by `scripts/build_attic_index.py`. CI runs `--check` so this file cannot silently drift from the live public estate.
