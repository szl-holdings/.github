# Estate alignment current-main successor

- `workcell_id`: `SZL-ESTATE-ALIGNMENT-CURRENT-MAIN-20260905`
- `source_base`: `48af5555ddd103f37b4d27de4e99b21ee5b91251`
- `supersedes_candidate`: `#682`
- `state`: `OPEN_REPAIR`

## Objective

Port the reviewed estate-alignment source/workflow/publication contract from #682 onto current protected main and close the unresolved org-card source-binding P1.

## Required correction

`SZLHOLDINGS/README` must be a first-class source-bound control surface tied to the exact current `szl-holdings/.github` protected-main SHA through the static Space origin `https://szlholdings-readme.static.hf.space` and its `deployment.json` evidence. Presence-only evidence is insufficient. Missing, stale, conflicting, or cross-origin evidence must fail closed.

Preserve the 16 portfolio-Space count: README is a control surface, not a portfolio member. Preserve existing publisher authority, host-isolated front-door rules, publication manifest ownership, and provider boundaries.

## Acceptance

Port only the necessary current-main-compatible alignment files; add adversarial org-card binding regressions; run focused estate, public-front-door, publication, host-isolated, and doctrine checks; require fresh exact-head CI and independent review. No provider mutation, secret readback, ruleset weakening, or direct-main write is authorized.
