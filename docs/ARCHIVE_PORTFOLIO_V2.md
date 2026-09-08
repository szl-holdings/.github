# Archived repository portfolio v2 — corrected source-authority wave

## Decision

The authenticated GitHub inventory observed **34 public archived repositories** on
2026-09-06. The September 8 recovery review expands the original four to six repositories because they still own
unique, maintained capabilities. The other twenty-eight remain archived: twenty-two
are consolidation sources and six are immutable historical records.

| Disposition | Count | Meaning |
|---|---:|---|
| Restore | 6 | Active source owner with a distinct operational role |
| Consolidate | 22 | Reusable material moves through reviewed PRs into an active canonical owner |
| Historical | 6 | Evidence or reproducibility record remains immutable |

## Exact restoration wave

| Repository | Why it remains valuable | Hugging Face presentation |
|---|---|---|
| `szl-atelier` | Canonical model-card explorer with an already merged Python 3.12/FastAPI runtime, readiness, source binding, receipt verification, and model catalog | Restore `SZLHOLDINGS/szl-atelier`; Forge retains training and model-publication authority |
| `szl-mesh` | Declared active DDIL/CRDT coordination authority; distinct from the frozen OTel evidence record and from the general substrate | A source-owned module inside `SZLHOLDINGS/szl-constellation` |
| `szl-router` | OpenAI-compatible sovereign-first routing gateway with bounded failover, per-answer receipts, cost/provider evidence, and a source-owned status surface | Forge inference module plus Constellation discovery; not a new product |
| `uds-bundles` | Maintained UDS/Zarf manifest, signed air-gap packaging, SBOM and provenance authority | Deployment/air-gap module inside `SZLHOLDINGS/szl-constellation` |
| `szl-build-env` | Source-owned development and runtime acceptance tools missing from Forge, including router receipt verification | Existing estate discovery only; no new Space |
| `vsp-otel` | Source-owned OTLP collector, signed-span exporter and Helm package missing from substrate | Existing Lyte/Constellation discovery only; no new Space |

See [the September 8 source comparison](ARCHIVE_RECOVERY_20260908.md) for the recovery evidence and remaining runtime limits.

The restoration governor permits only `archived: true -> false` for these six
exact names. It does not write into their source trees. Each repository receives
its own modernization PR after provider readback confirms that GitHub restored
write access.

## Corrected consolidation boundaries

This v2 contract removes the conflicts that invalidated the earlier v1 attempt:

- `counsel` consolidates into the active A11oy Counsel vertical and
  `vertical-services`; it is not delegated to Ayllu.
- `immune-lattice` remains an archived GitHub tombstone while the active
  `immune` repository owns both Hub channels.
- `docs-site` remains retired; reusable documentation belongs in `a11oy-net`.
- the active `szl-constellation` source supersedes `holographic-unify`.
- `szl-formula-ledger` remains archived because its attributed corpus is vendored
  into `szl-formulas` and formal truth remains in `lutar-lean`.
- event snapshots (`szl-fleet-overlay`, `szl-uds-deployment`,
  `warhacker-demo`) remain immutable evidence rather than release authorities.

The complete repository-by-repository mapping is
`governance/archive-portfolio-v2.json`.

## Backend modernization contract

Each restored source owner must land a dedicated PR that provides:

1. exact source-revision identity and controlled-file SHA-256 commitments;
2. bounded health, readiness, build-info, catalog, or manifest endpoints
   appropriate to the repository;
3. deterministic receipts and explicit `UNAVAILABLE` states rather than inferred
   provider, model, accelerator, energy, or runtime claims;
4. source-native tests, pinned dependencies, input bounds, and secret-free logs;
5. one exact Hugging Face publisher where a Space exists, with post-publication
   commit, file, runtime, and live-source readback.

A packaging or protocol repository is not given a pretend inference backend.
Its API exposes manifests, compatibility, receipts, and verification evidence.

## Frontend modernization contract

Each user-facing surface receives the source-local Holographic Space Fabric and
Public Experience contracts while retaining its own product information
architecture:

- phone widths from 320px, compact landscape, tablet, desktop, theatre, and
  ultrawide presentation;
- no document-level horizontal overflow;
- local scrolling for code, receipts, and tables;
- keyboard navigation and visible focus;
- coarse-pointer controls, safe areas, and readable form sizing;
- 200% and 400% zoom/reflow;
- reduced motion, increased contrast, forced colors, low-power, and print modes;
- local assets only: no CDN, analytics, cookies, or browser storage introduced by
  the shared layer.

## Hugging Face consolidation law

GitHub remains the source authority. Hugging Face remains a generated artifact
and runtime registry. Constellation composes discovery and evidence; it does not
absorb the restored repositories' histories or become their code owner.

No source merge is represented as a provider publication. No provider commit is
represented as a running, source-matched Space until exact readback succeeds.

## Execution order

1. merge this reviewed contract through the normal checks;
2. run the protected-main restoration job;
3. verify all six repositories report `archived=false`;
4. create dedicated backend/frontend modernization PRs in each restored source;
5. qualify and merge those exact heads;
6. publish only through the existing canonical Hugging Face writer;
7. read back exact Hub commit, controlled bytes, runtime state, and live source
   identity;
8. update the public ATTIC index and organization front doors from measured state.
