# DECISION-0001 — The canonical spine: platform vs. product front-ends

- **Status:** Accepted
- **Date:** 2026-07-06
- **Owner:** Stephen P. Lutar Jr. (SZL Holdings)
- **Applies to:** the whole `szl-holdings` org (architecture + naming + governance)

## Context

Governance docs across the org have used inconsistent, sometimes contradictory
language about "the consolidated home." Most notably,
[`a11oy/CONSOLIDATION.md`](https://github.com/szl-holdings/a11oy/blob/main/CONSOLIDATION.md)
called **a11oy** "the TRUE consolidated home of the SZL platform," which conflates
two different things — the shared **platform code spine** and a **product front-end**
that consumes it. That conflation is the root of repeated confusion about what is
canonical, what depends on what, and which site serves which product.

This decision names the canonical spine once, so every other doc can point here
instead of re-deciding it.

## Decision

1. **`platform` is the canonical code spine.** The shared substrate, runtime,
   agentic layer, and MCP infrastructure live in
   [`szl-holdings/platform`](https://github.com/szl-holdings/platform). This is the
   single source of truth for shared code. Shared behavior is published as
   **shared packages** consumed by the products.

2. **`a11oy` and `killinchu` are product front-ends, not forks.** They are distinct
   products that **depend on the shared packages** from the spine. They must not
   re-fork or silently re-vendor spine code; where they hold local copies for
   provenance, those copies are labeled as source-only ingests, not the live path.

3. **Two sites, two products.**
   - **`a-11-oy.com` → the a11oy platform product.** (Canonical a11oy domain.)
   - **`a11oy.net` → the killinchu product.**

4. **"Consolidated home" language is retired.** No single product repo is "the true
   home of the platform." The platform is the spine; the products are front-ends over
   it. Docs that previously claimed otherwise are corrected to reference this record.

## Consequences

- `a11oy/CONSOLIDATION.md`'s "a11oy is the TRUE consolidated home" line is superseded
  by this decision and updated to point here (separate PR on the `a11oy` repo).
- Future architecture and diligence docs cite **DECISION-0001** as the authority on
  spine-vs-front-end naming and on the two-site mapping, rather than re-litigating it.
- This record does not move, delete, or archive any repository. It is a naming and
  dependency-direction decision only.

## Doctrine alignment

- Honest-by-design (Doctrine v11): this record removes a contradictory/overclaiming
  "true home" statement rather than adding a new claim.
- Canonical domain for the a11oy platform remains **a-11-oy.com**, consistent with
  standing doctrine.

Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
