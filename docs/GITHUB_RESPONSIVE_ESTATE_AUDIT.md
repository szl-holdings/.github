# GitHub responsive estate audit

This control closes a gap that the Hugging Face and public-origin browser audit
cannot close by itself: every GitHub repository must first be classified before
any UI requirement is applied.

## Scope

The audit authenticates to the complete `szl-holdings` repository estate using
the same App-first, governed-token fallback and canonical-inventory proof used
by the CI Health Digest. It then reads each active default-branch tree at an
exact Git blob lineage and classifies the repository as one of:

- `PUBLIC_WEB` or `PRIVATE_WEB` — browser-facing source;
- `API_SERVICE` — network service without a detected browser interface;
- `LIBRARY`, `RESEARCH`, `DOCS`, or `CONTROL_PLANE` — no responsive layout
  requirement unless browser source is detected;
- `ARCHIVED` — historical and not release-bearing;
- `UNKNOWN` — explicit review required, never silently called compliant.

Only `PUBLIC_WEB` and `PRIVATE_WEB` repositories are evaluated against the
responsive source contract. This prevents meaningless mass CSS changes to
libraries, APIs, papers, governance repositories, and archived projects.

## Responsive source contract

For each UI-bearing repository, the bounded source sampler records evidence for:

- a mobile viewport contract;
- responsive layout primitives;
- document-level overflow containment;
- reduced-motion behavior;
- contrast/forced-colors behavior;
- coarse-pointer touch targets;
- safe-area and dynamic viewport support;
- zoom/reflow and local scrolling for wide tables or code;
- SZL Public Experience v3 integration;
- repository-native Playwright, Lighthouse, axe, accessibility, responsive,
  E2E, or visual-regression automation.

The four release-blocking public-web minimums are viewport, responsive layout,
overflow containment, and reduced motion. A public UI with incomplete inventory
or unavailable bounded source evidence also fails closed.

## Evidence and mutation boundary

The audit emits JSON and Markdown artifacts retained for 90 days and reconciles
one durable issue containing the exact action queue. It performs no repository,
branch, ruleset, deployment, DNS, Hugging Face, or secret mutation.

This audit proves repository classification and sampled source posture. It does
not replace live browser verification. Runtime phone-through-ultrawide proof
continues under `SZL Public Experience v3`, while each product's deployment
workflow remains responsible for exact source-to-runtime readback.
