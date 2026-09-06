# Archive Portfolio v1

**Decision date:** 2026-09-06  
**Authority:** `governance/archive-portfolio-v1.json`  
**Rule:** restore only unique maintained authorities; consolidate reusable source into active canonicals; preserve immutable evidence as tombstones.

The authenticated archive inventory contains **34 public repositories**. This wave restores **5**, consolidates **23**, and preserves **6** as immutable historical evidence.

## Restoration wave

| Repository | Canonical role | Hugging Face presentation |
|---|---|---|
| `docs-site` | Versioned documentation, SDK, cookbook, and evidence portal | Linked from `SZLHOLDINGS/szl-constellation`; no duplicate docs Space |
| `szl-atelier` | Presentation-only model catalog and interactive model walk | Existing flagship `SZLHOLDINGS/szl-atelier`; Forge keeps training/publication authority |
| `szl-mesh` | DDIL/CRDT coordination and offline reconciliation | Module in `SZLHOLDINGS/szl-constellation`; no new Space until a measured runtime exists |
| `szl-router` | Sovereign OpenAI-compatible inference gateway | Route/evidence view inside Atelier; no provider secrets or second inference Space |
| `uds-bundles` | Maintained air-gap packaging source | Deployment/evidence module in Constellation; frozen WarHacker repos remain archived |

Restoration alone does not make a repository production-ready. Each restored repository must receive source-bound CI, security coverage, backend health/readiness/source identity, responsive and accessible frontend contracts, and an exact Hugging Face or domain readback before any live claim.

## Consolidation and historical disposition

| Archived repository | Decision | Canonical target(s) | Existing Hugging Face showcase |
|---|---|---|---|
| `cosmos` | CONSOLIDATE | `szl-constellation`, `anatomy` | `SZLHOLDINGS/szl-constellation` |
| `counsel` | CONSOLIDATE | `ayllu` | `SZLHOLDINGS/ayllu` |
| `developers` | CONSOLIDATE | `docs-site` | `SZLHOLDINGS/szl-atelier` |
| `energy-attest-holo` | CONSOLIDATE | `szl-energy-attest`, `szl-constellation` | `SZLHOLDINGS/szl-constellation` |
| `evidence-typed-formula-governance` | HISTORICAL | immutable evidence | `SZLHOLDINGS/szl-constellation` |
| `fail-closed-governed-ai-services` | HISTORICAL | immutable evidence | `SZLHOLDINGS/szl-constellation` |
| `governed-inference-meter` | CONSOLIDATE | `szl-energy-attest`, `szl-kernels` | `SZLHOLDINGS/szl-constellation` |
| `governed-norm-holo` | CONSOLIDATE | `szl-kernels`, `szl-constellation` | `SZLHOLDINGS/szl-constellation` |
| `immune-lattice` | CONSOLIDATE | `immune` | `SZLHOLDINGS/immune` |
| `khipu-lab` | CONSOLIDATE | `szl-khipu` | `SZLHOLDINGS/szl-khipu` |
| `khipu-pages` | CONSOLIDATE | `szl-khipu` | `SZLHOLDINGS/szl-khipu` |
| `lambda-gate-holo` | CONSOLIDATE | `szl-lambda-gate`, `szl-constellation` | `SZLHOLDINGS/szl-constellation` |
| `lean-kernel` | CONSOLIDATE | `lutar-lean`, `szl-kernels` | `SZLHOLDINGS/szl-kernels` |
| `ouroboros` | CONSOLIDATE | `platform`, `szl-ouroboros` | `SZLHOLDINGS/szl-constellation` |
| `receipt-chain-live` | CONSOLIDATE | `szl-receipt`, `a11oy-net` | `SZLHOLDINGS/governed-receipt-verifier` |
| `szl-build-env` | CONSOLIDATE | `szl-forge` | `SZLHOLDINGS/szl-atelier` |
| `szl-cookbook` | CONSOLIDATE | `docs-site`, `szl-forge` | `SZLHOLDINGS/szl-atelier` |
| `szl-experiments` | CONSOLIDATE | `szl-frontier` | `SZLHOLDINGS/szl-constellation` |
| `szl-fleet-overlay` | HISTORICAL | immutable evidence | `SZLHOLDINGS/szl-constellation` |
| `szl-formula-ledger` | CONSOLIDATE | `lutar-lean`, `szl-formulas` | `SZLHOLDINGS/szl-constellation` |
| `szl-governed-norm` | CONSOLIDATE | `szl-kernels` | `SZLHOLDINGS/szl-kernels` |
| `szl-kernels-live` | CONSOLIDATE | `szl-kernels` | `SZLHOLDINGS/szl-kernels` |
| `szl-organ-integrity` | CONSOLIDATE | `anatomy`, `a11oy` | `SZLHOLDINGS/anatomy` |
| `szl-otel-mesh` | HISTORICAL | immutable evidence | `SZLHOLDINGS/szl-constellation` |
| `szl-provctl-live` | CONSOLIDATE | `szl-provctl` | `SZLHOLDINGS/szl-provctl` |
| `szl-telemetry` | CONSOLIDATE | `szl-substrate`, `lyte-services` | `SZLHOLDINGS/lyte-lattice` |
| `szl-uds-deployment` | HISTORICAL | immutable evidence | `SZLHOLDINGS/szl-constellation` |
| `vsp-otel` | CONSOLIDATE | `szl-substrate`, `lyte-services` | `SZLHOLDINGS/lyte-lattice` |
| `warhacker-demo` | HISTORICAL | immutable evidence | `SZLHOLDINGS/szl-constellation` |

## Upgrade sequence

1. Restore only the five manifest-authorized repositories and verify GitHub provider readback.
2. Regenerate `ATTIC.md`; no stale archive count is accepted.
3. Apply organization rulesets, code scanning, dependency updates, and exact-source CI to every restored repo.
4. Migrate reusable code and tests from consolidated tombstones into their named active owners through reviewed PRs.
5. Upgrade the five maintained surfaces:
   - `szl-router`: typed provider adapters, bounded retries/circuit breakers, rate limits, auth, receipt verification, cost/energy honesty, OpenTelemetry, and an operator-safe frontend.
   - `szl-mesh`: deterministic CRDT/event model, signed transitions, offline reconciliation, conflict receipts, simulation/fault tests, and a topology/witness frontend.
   - `uds-bundles`: reproducible package lock, SBOM/provenance, air-gap rehearsal, current image digests, and a deployment evidence frontend.
   - `docs-site`: one docs/cookbook/developer route, generated API reference, search, source-bound deployment manifest, accessibility and mobile/theatre tests.
   - `szl-atelier`: model catalog readback, evidence filters, source/revision lineage, responsive 3D/card frontend, and strict separation from Forge model authority.
6. Consolidate the public showcase in existing `SZLHOLDINGS/szl-constellation`, `szl-atelier`, `szl-khipu`, `immune`, `anatomy`, and `lyte-lattice` surfaces. Creating another Space requires a separate measured need.
7. Publish only after GitHub source, artifact digest, Hugging Face revision, runtime identity, and public readback converge.

## Safety boundary

The governor can only set `archived=false` for manifest rows whose disposition is `restore`. It cannot archive repositories, change visibility, delete history, rewrite refs, alter branch protection, or mutate Hugging Face. Consolidation is performed later by source PRs, never by deleting tombstones.
