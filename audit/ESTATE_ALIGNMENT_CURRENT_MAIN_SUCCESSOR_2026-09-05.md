# Estate alignment current-main successor

- `workcell_id`: `SZL-ESTATE-ALIGNMENT-CURRENT-MAIN-20260905`
- `source_base`: `48af5555ddd103f37b4d27de4e99b21ee5b91251`
- `supersedes_candidate`: `#682`
- `state`: `IMPLEMENTED_PENDING_EXACT_HEAD_CI`

## Objective

Port the reviewed estate-alignment source, workflow, and publication contract from #682 onto current protected main and close the unresolved organization-card source-binding P1.

## Required correction

`SZLHOLDINGS/README` must be a first-class source-bound control surface tied to the exact current `szl-holdings/.github` protected-main SHA through the static Space origin `https://szlholdings-readme.static.hf.space` and its `deployment.json` evidence. Presence-only evidence is insufficient. Missing, stale, conflicting, or cross-origin evidence must fail closed.

Preserve the measured public inventory without conflating inventory with portfolio authority:

- **16** governed portfolio Spaces;
- **1** inventory-only research Space, `SZLHOLDINGS/yarqa`, with disposition `FOLD` and no keeper authority;
- **17** public Spaces in total;
- **45** public model repositories; and
- **34** public datasets.

`SZLHOLDINGS/README` remains a source-bound organization control surface outside both the 16-Space portfolio and the 17-Space public product/research inventory count. Preserve existing publisher authority, host-isolated front-door rules, publication-manifest ownership, and provider boundaries.

## Acceptance

Port only the necessary current-main-compatible alignment files; add adversarial organization-card binding regressions; run focused estate, public-front-door, publication, host-isolated, and doctrine checks; require fresh exact-head CI and independent review. No provider mutation, secret readback, ruleset weakening, direct-main write, inventory exclusion, or presence-only substitution is authorized.

## Forward implementation

The current-main successor treats `SZLHOLDINGS/README` as a separate, source-bound control surface. Its only accepted runtime evidence is `https://szlholdings-readme.static.hf.space/deployment.json`, observed twice with cache-busting and constrained to the same origin, and it must match the exact protected-main revision of `szl-holdings/.github`.

The evidence is emitted separately as `organization_card_source_binding`; `runtime_source_bindings` covers the governed public runtime estate and keeps inventory-only research classification explicit. Focused regressions cover stale revisions, conflicting revisions, cross-origin failures, the static-host path, inventory decomposition, and count preservation. This is not a merge or live-deployment claim; exact-head CI, live readback, and protected review remain required.
