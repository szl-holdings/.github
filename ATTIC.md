# ATTIC — SZL Holdings repository lifecycle index

<!-- GENERATED FILE — do not edit by hand. -->
<!-- Regenerate: python scripts/build_attic_index.py --write -->

This index joins live public GitHub repository state with the reviewed `governance/archive-portfolio-v1.json` lifecycle authority. Repository descriptions are informative only; they cannot silently choose a successor.

**Rule.** Restore only unique maintained authorities. Move reusable source from consolidation tombstones into named active owners through reviewed PRs. Keep published evidence immutable. Present the result through existing Hugging Face flagships rather than multiplying Spaces.

## Estate shape

| Metric | Count |
|---|---:|
| Public repositories total | 117 |
| Active public repositories | 83 |
| Archived public repositories | 34 |
| Strategic restorations pending | 5 |
| Strategic restorations completed | 0 |
| Consolidation tombstones | 23 |
| Immutable historical records | 6 |
| Structural defects | 0 |

## Strategic restoration wave

A pending row remains archived because repository-administration authority has not yet produced provider readback. It is not presented as an active source until GitHub reports `archived=false`.

| Repository | State | Maintained role | Hugging Face showcase |
|---|---|---|---|
| `docs-site` | `PENDING_ADMIN_AUTHORITY` | The live versioned documentation portal needs an active source and release path. Restore it as docs authority; a11oy-net remains the proof site. | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) |
| `szl-atelier` | `PENDING_ADMIN_AUTHORITY` | Existing flagship Hugging Face model-walk surface. Restore the source repo as a presentation-only authority while szl-forge retains training/publication authority. | [`SZLHOLDINGS/szl-atelier`](https://huggingface.co/spaces/SZLHOLDINGS/szl-atelier) |
| `szl-mesh` | `PENDING_ADMIN_AUTHORITY` | Strategic DDIL/CRDT coordination layer required by Beacon and physical-edge work. Restore with a narrow mesh authority distinct from the general substrate. | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) |
| `szl-router` | `PENDING_ADMIN_AUTHORITY` | Unique sovereign OpenAI-compatible routing gateway with receipt, cost, provider-attempt, and ownership evidence. Restore as runtime gateway; A11oy remains the governance/control plane. | [`SZLHOLDINGS/szl-atelier`](https://huggingface.co/spaces/SZLHOLDINGS/szl-atelier) |
| `uds-bundles` | `PENDING_ADMIN_AUTHORITY` | Unique air-gap packaging authority for Zarf/UDS bundle manifests. Restore as the maintained packaging source, separate from frozen event snapshots. | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) |

## Consolidation tombstones

| Archived repository | Canonical owner(s) | Hugging Face showcase | Rationale |
|---|---|---|---|
| `cosmos` | [`szl-constellation`](https://github.com/szl-holdings/szl-constellation), [`anatomy`](https://github.com/szl-holdings/anatomy) | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | Move the best 3D estate and anatomy views into the canonical Constellation and Anatomy surfaces. |
| `counsel` | [`ayllu`](https://github.com/szl-holdings/ayllu) | [`SZLHOLDINGS/ayllu`](https://huggingface.co/spaces/SZLHOLDINGS/ayllu) | Counsel is an Ayllu capability; preserve history and move maintained backend/frontend work into Ayllu. |
| `developers` | [`docs-site`](https://github.com/szl-holdings/docs-site) | [`SZLHOLDINGS/szl-atelier`](https://huggingface.co/spaces/SZLHOLDINGS/szl-atelier) | Developer onboarding and SDK navigation belong in the restored docs hub. |
| `energy-attest-holo` | [`szl-energy-attest`](https://github.com/szl-holdings/szl-energy-attest), [`szl-constellation`](https://github.com/szl-holdings/szl-constellation) | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | Energy measurement remains in its canonical service; the hologram becomes a Constellation module. |
| `governed-inference-meter` | [`szl-energy-attest`](https://github.com/szl-holdings/szl-energy-attest), [`szl-kernels`](https://github.com/szl-holdings/szl-kernels) | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | Move metering semantics to the energy authority and kernel contracts to the kernel suite. |
| `governed-norm-holo` | [`szl-kernels`](https://github.com/szl-holdings/szl-kernels), [`szl-constellation`](https://github.com/szl-holdings/szl-constellation) | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | Keep kernel semantics in szl-kernels and presentation in Constellation. |
| `immune-lattice` | [`immune`](https://github.com/szl-holdings/immune) | [`SZLHOLDINGS/immune`](https://huggingface.co/spaces/SZLHOLDINGS/immune) | Move COP/lattice presentation into the canonical IMMUNE service and its existing Space channel. |
| `khipu-lab` | [`szl-khipu`](https://github.com/szl-holdings/szl-khipu) | [`SZLHOLDINGS/szl-khipu`](https://huggingface.co/SZLHOLDINGS/szl-khipu) | Migrate the interactive kernel-lab UI and browser fixtures into the canonical KHIPU source; do not maintain a second kernel authority. |
| `khipu-pages` | [`szl-khipu`](https://github.com/szl-holdings/szl-khipu) | [`SZLHOLDINGS/szl-khipu`](https://huggingface.co/SZLHOLDINGS/szl-khipu) | Merge the static showcase into the canonical KHIPU frontend instead of maintaining a second Pages source. |
| `lambda-gate-holo` | [`szl-lambda-gate`](https://github.com/szl-holdings/szl-lambda-gate), [`szl-constellation`](https://github.com/szl-holdings/szl-constellation) | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | Keep lambda-gate computation canonical and show it through the consolidated constellation. |
| `lean-kernel` | [`lutar-lean`](https://github.com/szl-holdings/lutar-lean), [`szl-kernels`](https://github.com/szl-holdings/szl-kernels) | [`SZLHOLDINGS/szl-kernels`](https://huggingface.co/SZLHOLDINGS/szl-kernels) | Formal source belongs in lutar-lean; the governed kernel suite is the public Hugging Face artifact. |
| `ouroboros` | [`platform`](https://github.com/szl-holdings/platform), [`szl-ouroboros`](https://github.com/szl-holdings/szl-ouroboros) | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | Product implementation belongs in platform; bounded-loop kernel semantics belong in szl-ouroboros. |
| `receipt-chain-live` | [`szl-receipt`](https://github.com/szl-holdings/szl-receipt), [`a11oy-net`](https://github.com/szl-holdings/a11oy-net) | [`SZLHOLDINGS/governed-receipt-verifier`](https://huggingface.co/spaces/SZLHOLDINGS/governed-receipt-verifier) | Receipt implementation belongs in szl-receipt; public verification belongs on the proof surface. |
| `szl-build-env` | [`szl-forge`](https://github.com/szl-holdings/szl-forge) | [`SZLHOLDINGS/szl-atelier`](https://huggingface.co/spaces/SZLHOLDINGS/szl-atelier) | Build environment ownership belongs in the canonical Forge release plane. |
| `szl-cookbook` | [`docs-site`](https://github.com/szl-holdings/docs-site), [`szl-forge`](https://github.com/szl-holdings/szl-forge) | [`SZLHOLDINGS/szl-atelier`](https://huggingface.co/spaces/SZLHOLDINGS/szl-atelier) | Keep recipes in the restored docs hub; executable model recipes remain owned by Forge. |
| `szl-experiments` | [`szl-frontier`](https://github.com/szl-holdings/szl-frontier) | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | All experimental work should enter through one frontier/evidence lane. |
| `szl-formula-ledger` | [`lutar-lean`](https://github.com/szl-holdings/lutar-lean), [`szl-formulas`](https://github.com/szl-holdings/szl-formulas) | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | Formal truth remains in Lean; public formula packaging remains in szl-formulas. |
| `szl-governed-norm` | [`szl-kernels`](https://github.com/szl-holdings/szl-kernels) | [`SZLHOLDINGS/szl-kernels`](https://huggingface.co/SZLHOLDINGS/szl-kernels) | Keep one governed-kernel suite and one Hugging Face mirror. |
| `szl-kernels-live` | [`szl-kernels`](https://github.com/szl-holdings/szl-kernels) | [`SZLHOLDINGS/szl-kernels`](https://huggingface.co/SZLHOLDINGS/szl-kernels) | Use the canonical kernel suite for code, releases, and Hub mirrors. |
| `szl-organ-integrity` | [`anatomy`](https://github.com/szl-holdings/anatomy), [`a11oy`](https://github.com/szl-holdings/a11oy) | [`SZLHOLDINGS/anatomy`](https://huggingface.co/spaces/SZLHOLDINGS/anatomy) | Integrity views belong in Anatomy; admission and outcome authority belong in A11oy. |
| `szl-provctl-live` | [`szl-provctl`](https://github.com/szl-holdings/szl-provctl) | [`SZLHOLDINGS/szl-provctl`](https://huggingface.co/SZLHOLDINGS/szl-provctl) | Use one provenance-control implementation and one card. |
| `szl-telemetry` | [`szl-substrate`](https://github.com/szl-holdings/szl-substrate), [`lyte-services`](https://github.com/szl-holdings/lyte-services) | [`SZLHOLDINGS/lyte-lattice`](https://huggingface.co/spaces/SZLHOLDINGS/lyte-lattice) | Telemetry vocabulary belongs in the shared substrate; operational UX belongs in Lyte. |
| `vsp-otel` | [`szl-substrate`](https://github.com/szl-holdings/szl-substrate), [`lyte-services`](https://github.com/szl-holdings/lyte-services) | [`SZLHOLDINGS/lyte-lattice`](https://huggingface.co/spaces/SZLHOLDINGS/lyte-lattice) | Fold semantic conventions into the substrate and observability presentation into Lyte. |

## Immutable historical evidence

| Archived repository | Public showcase | Retention rationale |
|---|---|---|
| `evidence-typed-formula-governance` | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | Published reproducibility package. Preserve immutably and cite it from papers/docs. |
| `fail-closed-governed-ai-services` | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | Published reproducibility package. Preserve immutably and cite it from papers/docs. |
| `szl-fleet-overlay` | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | Frozen WarHacker fleet-overlay evidence snapshot. Do not revive as a current product authority. |
| `szl-otel-mesh` | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | DOI-bound OpenTelemetry/DSSE research artifact. Keep immutable; maintained mesh work belongs in restored szl-mesh. |
| `szl-uds-deployment` | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | Frozen WarHacker deployment evidence snapshot. Maintained bundle work moves to restored uds-bundles. |
| `warhacker-demo` | [`SZLHOLDINGS/szl-constellation`](https://huggingface.co/spaces/SZLHOLDINGS/szl-constellation) | Completed WarHacker 2026 dry-run snapshot. Keep immutable for provenance; surface its verified artifacts through docs and the deployment portfolio. |

---

Generated by `scripts/build_attic_index.py`. CI runs `--check`; unclassified archives, hidden reactivations, missing canonical targets, and stale provider state are terminal.
