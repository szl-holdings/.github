# GitHub ↔ Hugging Face alignment — 2026-09-25 recapture

**Status:** `RECAPTURE_DRAFT`  
**Captured:** 2026-09-25T19:30:00-04:00  
**Actor:** estate operator via connected GitHub identity `stephenlutar2-hash`  
**Evidence class:** MEASURED where a public API or authenticated GitHub search returned a count; REPORTED for org-card copy.  
**Runtime:** not certified. `certified_production_ready: false`  
**Λ:** Conjecture 1 (advisory, never a theorem)

GitHub `szl-holdings` remains protected source.  
Hugging Face `SZLHOLDINGS` remains the public artifact / runtime mirror.  
This file classifies existing cards against existing repositories. It does not mint a new public GitHub repository or Hugging Face Space.

## What this pass authorizes

- Record current public inventory so the 2026-08-29 / 2026-09-11 alignment docs are not the only recapture.
- Keep Wave 1 bounds from `docs/GREEN_LIGHT.md`: truth and PR closure on existing repositories.

## What this pass does not authorize

- No new public GitHub repository.
- No new Hugging Face Space or model-brand.
- No production ATO.
- No merge of a red required check.
- No Hub write. This session has no Hugging Face write connector. Owner-queue HF write token remains required for card apply.

## Measured this pass

| Surface | Count | Source |
| --- | ---: | --- |
| GitHub repository search | 126 | `org:szl-holdings` authenticated search |
| GitHub org page shown | 118 | github.com/orgs/szl-holdings/repositories |
| Open org pull requests | 2 | `org:szl-holdings is:open` |
| Open Dependabot pull requests | 0 | same search |
| Hub models (public API) | 49 | `/api/models?author=SZLHOLDINGS&limit=100` |
| Hub datasets (public API) | 32 | `/api/datasets?author=SZLHOLDINGS&limit=100` |
| Hub Spaces (public API) | 22 | `/api/spaces?author=SZLHOLDINGS&limit=100` |
| Hub org-card displayed | 49 models / 35 datasets / 23 Spaces / 21 collections | huggingface.co/SZLHOLDINGS |

Org-card dataset (35) and Space (23) counts exceed the anonymous list APIs (32 / 22). Treat the delta as unauthenticated-visibility or pagination remainder, not as new products. Do not invent the missing names.

Prior recapture `GITHUB_HF_ALIGNMENT_2026-09-11.md` recorded anonymous Hub 46 / 35 / 21. Model count grew 46 → 49 MEASURED. Dataset and Space list-API vs org-card still disagree.

## Open pull requests (do not merge)

| PR | State | Why |
| --- | --- | --- |
| [szl-holdings/.github#773](https://github.com/szl-holdings/.github/pull/773) | draft `[HOLD]` | Body forbids merge to protected main. Provenance jobs red. |
| [szl-holdings/szl-forge#295](https://github.com/szl-holdings/szl-forge/pull/295) | draft `HOLD` | `observe (3.11)` and `observe (3.12)` red. Missing binary wheel for `openai-whisper>=20250625`. Result is `BLOCKED_OR_UNAVAILABLE`, not a runtime lock. |

`GREEN_LIGHT.md` does not override a red required check. Both PRs received a second-reader HOLD comment on 2026-09-25. `#295` was returned to draft.

## Stale leftover from older alignment docs

`.github#465` (`fix(app): grant qillqaq secret-name read`) is **closed without merge** (2026-08-29), superseded by `#485`. Do not treat it as an open App-permission PR.

## Public Spaces vs GitHub twins

Anonymous Hub Space list this pass:

| Hub Space | GitHub twin / note |
| --- | --- |
| SZLHOLDINGS/a11oy | szl-holdings/a11oy |
| SZLHOLDINGS/killinchu | szl-holdings/killinchu |
| SZLHOLDINGS/david-leads | szl-holdings/david-leads |
| SZLHOLDINGS/immune | szl-holdings/immune |
| SZLHOLDINGS/immune-lattice | szl-holdings/immune (canonical) |
| SZLHOLDINGS/szl-atelier | szl-holdings/szl-atelier |
| SZLHOLDINGS/szl-frontier | szl-holdings/szl-frontier |
| SZLHOLDINGS/szl-khipu | szl-holdings/szl-khipu |
| SZLHOLDINGS/llm-router-live | szl-holdings/szl-router (inference flagship) |
| SZLHOLDINGS/vertical-services | szl-holdings/vertical-services |
| SZLHOLDINGS/counsel | vertical / classified family; not a new flagship |
| SZLHOLDINGS/terra | binds to public-records surface; occupancy UNAVAILABLE unless measured |
| SZLHOLDINGS/sentra | vertical engine Space |
| SZLHOLDINGS/finance | vertical engine Space |
| SZLHOLDINGS/lyte | vertical engine Space |
| SZLHOLDINGS/szl-command-lab | lab, not a ninth flagship |
| SZLHOLDINGS/szl-constellation | owner-edited card; see HF_CARD_RECONCILIATION.md |
| SZLHOLDINGS/szl-constellation-staging | staging; not production |
| SZLHOLDINGS/szl-model-inference-lab | owner-queue private/fold candidate |
| SZLHOLDINGS/yarqa | inventory-only; `governedKeep=false`, disposition FOLD |
| SZLHOLDINGS/ayllu | classified family Space |
| SZLHOLDINGS/holographic-unify | not a commercial flagship |

Do not delete `SZLHOLDINGS/immune` or `SZLHOLDINGS/immune-lattice`.  
Do not mint a public `SZLHOLDINGS/nexus` Space.  
Do not recreate `yarqa` or `hatun-mcp` as warm-flagship incidents.

## Kernel / software twins (Hub is publish mirror)

| Hub | GitHub |
| --- | --- |
| SZLHOLDINGS/szl-kernels | szl-holdings/szl-kernels |
| SZLHOLDINGS/szl-invariants | szl-holdings/szl-invariants |
| SZLHOLDINGS/szl-blocked | szl-holdings/szl-blocked |
| SZLHOLDINGS/szl-govsign | szl-holdings/szl-govsign |
| SZLHOLDINGS/szl-provctl | szl-holdings/szl-provctl |
| SZLHOLDINGS/szl-ouroboros | szl-holdings/szl-ouroboros |
| SZLHOLDINGS/szl-formulas | szl-holdings/szl-formulas |
| SZLHOLDINGS/szl-lambda-gate | szl-holdings/szl-lambda-gate |
| SZLHOLDINGS/szl-governed-norm | szl-holdings/szl-governed-norm |
| SZLHOLDINGS/szl-maskmod | szl-holdings/szl-maskmod |
| SZLHOLDINGS/szl-block-kv | szl-holdings/szl-block-kv |
| SZLHOLDINGS/szl-khipu | szl-holdings/szl-khipu |

Weight and adapter cards continue to bind to `szl-holdings/szl-forge`. GGUF children bind to `szl-holdings/szl-serve` when that repo remains the serve authority.

## Owner-queue blockers for live Hub writes

From `docs/OWNER-ACTION-QUEUE.md` (still binding):

1. Hugging Face write token with org-Space write for `SZLHOLDINGS`.
2. Cloudflare API token (current connector fails `400 / 6003 / 6103`).
3. SZL-Nemo v3 signing ceremony (`szl-gpu-bridge#93` / `#20` expired jobspecs).
4. Org default code scanning enablement (admin:org).

This recapture cannot apply Hub card writes until (1) exists in the operator session.

## Security / upgrades observed

- No open Dependabot pull requests org-wide this pass.
- `a11oy` has open medium Dependabot alerts for vitest / `@vitest/mocker` (`CVE-2026-84373`, GHSA-82fw-gwwq-j7x9). Development-server path traversal. Fixed upstream in vitest 4.1.11 / 5.0.0. No critical alerts listed on `a11oy`. No high alerts listed on `platform`.
- Closed-unmerged PRs in the last seven days include intentional `DO NOT MERGE` work such as `a11oy#2271`. Do not reopen those without a signed successor.

## Rule

1. Exact-name kernel Hub packages already have GitHub twins. Hub is the publish mirror.
2. Flagship GitHub homepages stay on a-11-oy.com / a11oy.net when that is the product URL.
3. A public Space, HTTP 200, workflow success, or signature is not a production certificate.
4. Green light does not override a red required check.
