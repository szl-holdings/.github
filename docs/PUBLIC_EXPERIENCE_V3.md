# SZL Public Experience v3.1

## Purpose

Every public SZL product must remain functional and legible from a 320px phone
through a 3440px ultrawide theatre display while retaining its own product
identity. Shared mechanics may be centralized; product information architecture,
data, workflows, evidence semantics, and visual motif remain source-owned.

The target is not one generic skin. The target is one predictable operating
language across distinct products: clear purpose, one obvious first action,
progressive disclosure, inspectable proof, and full reflow for touch, keyboard,
zoom, assistive technology, and command-room displays.

## Design synthesis

The standard adapts established public principles without copying proprietary
layouts, branding, assets, or source code:

- **Apple:** fit primary content to the screen, avoid horizontal scrolling,
  preserve familiar interactions, provide comfortable hit targets, support
  larger text, and keep controls near the content they affect.
- **NVIDIA:** treat WCAG 2.2 AA as a development standard rather than a final
  audit checkbox, and continuously audit the whole public surface.
- **Material:** change the scaffold at meaningful breakpoints instead of merely
  shrinking a desktop canvas.
- **Fluent:** retain functionality at 400% zoom, manage keyboard focus, and
  collapse complex controls into simpler responsive forms when space is tight.
- **SZL:** preserve a unique motif and business workflow for every product while
  sharing accessibility, navigation, evidence labels, and source/proof handoffs.

Authoritative references:

- Apple Human Interface Guidelines — Accessibility:
  `https://developer.apple.com/design/human-interface-guidelines/accessibility/`
- Apple UI Design Dos and Don'ts:
  `https://developer.apple.com/design/tips/`
- NVIDIA.com Accessibility Help:
  `https://www.nvidia.com/en-us/about-nvidia/accessibility/`
- Material Design canonical adaptive layouts:
  `https://m3.material.io/foundations/layout/canonical-examples/overview`
- Fluent 2 Accessibility:
  `https://fluent2.microsoft.design/accessibility`

## Audience-first information contract

Every flagship surface must support four concise journeys without duplicating
or falsifying information:

| Audience | First question | Required first-order path |
|---|---|---|
| User | What can I accomplish here? | Outcome, primary action, current state, next step |
| Operator | What requires attention now? | Signals, blocked actions, approvals, evidence, rollback |
| Developer | How does this work and how do I reproduce it? | Source, API or contract, local run path, tests, limitations |
| Investor | What is the wedge and what is proved? | Market problem, product differentiation, live proof, architecture, explicit gaps |

The shared runtime exposes only a local `data-szl-audience` state and a
read-only `window.SZLPublicExperience.snapshot()` helper. Products may use that
state to prioritize navigation or documentation, but it never changes business
logic, claims, model behavior, policy, or evidence status.

## Public origin roles

| Origin | Role | Runtime contract |
|---|---|---|
| `https://a-11-oy.com` | Static product front door | Root GET 200, clear product/runtime handoff, no claim that Pages is the application API |
| `https://szlholdings-a11oy.hf.space` | Canonical A11oy application runtime | Source-bound deployment, application routes and APIs, live runtime probes |
| `https://a11oy.net` | Independent proof origin | Static forensic record, local proof assets, separate failure domain |
| `https://*.hf.space` / `https://*.static.hf.space` | Product-specific public Spaces | Public root GET 200, source-owned app, deterministic identity, responsive v3 marker |

The apex and application runtime remain separate until an independently proved
edge configuration makes them the same origin. An HTTP 200 on one origin cannot
substitute for a runtime pass on another.

## Required viewport and reflow matrix

| Case | CSS viewport | Purpose |
|---|---:|---|
| phone | `320 × 800` | Minimum supported width and 400%-equivalent reflow pressure |
| phone | `375 × 812` | Common modern handset |
| tablet | `768 × 1024` | Portrait tablet and two-column transition |
| desktop | `1024 × 768` | Compact desktop / landscape tablet |
| desktop | `1440 × 900` | Standard working canvas |
| theatre | `2560 × 1440` | High-density command-room display |
| ultrawide | `3440 × 1440` | Theatre-scale spatial presentation without unbounded reading lines |
| reduced motion | `375 × 812` | Equivalent content and controls with decorative motion suppressed |
| zoom | `1280 × 900 @ 200%` | Reflow and control access under magnification |
| zoom | `1280 × 900 @ 400%` | Maximum required magnification pressure |

## Blocking browser findings

A measured case is not green when any of the following is present:

- root navigation is not HTTP 200;
- the document has no title or meaningful content;
- document-level horizontal overflow exceeds two CSS pixels;
- a public Hugging Face application does not expose the v3 identity marker;
- a visible touch control is smaller than 44 by 44 CSS pixels, excluding
  ordinary inline prose links governed by target-spacing rules;
- an interactive fixed element unintentionally covers more than 88% of the
  viewport;
- the page raises an uncaught browser exception.

Console errors and missing `main` landmarks remain explicit warnings and must be
triaged; they are not silently converted to PASS. A bounded `networkidle`
timeout is also recorded as a warning rather than a failure because operational
dashboards may intentionally retain polling or streaming connections after the
document is interactive.

## Shared responsive mechanics

The shared layer provides:

- dynamic viewport units with a JavaScript `visualViewport` fallback;
- explicit CSS-zoom detection and an effective layout width for 200% and 400%
  reflow tests;
- safe-area-aware shared navigation whose mobile menu is bounded in document
  flow rather than becoming a full-screen fixed sheet;
- phone, compact, tablet, desktop, wide, theatre, and ultrawide tiers;
- bounded media, dialogs, code blocks, wide tables, Gradio, and Streamlit
  containers;
- long-token and URL wrapping;
- 44px minimum controls and 48px coarse-pointer controls;
- a non-destructive fallback title only when a public Space has no title;
- local-only assets with no analytics, cookies, storage, external fonts, or
  runtime CDN;
- reduced-motion, increased-contrast, forced-colors, print, and zoom behavior;
- concise Command → Proof → Spaces → Source navigation.

## Product-specific identity

The shared layer must not turn the estate into one recolored template. Named
products keep deterministic motifs such as signal aurora, maritime radar,
parcel topography, threat lattice, case lines, editorial orbit, graph mesh,
build circuit, recursive weave, agent swarm, cell membrane, and checksum ledger.
Unknown public Space slugs receive a stable deterministic identity rather than a
random theme.

## Developer contract

Every generated source PR must identify:

- canonical GitHub source and mapped Hugging Face Space;
- exact adapter and entrypoint;
- changed paths and asset digest;
- viewport, touch, zoom, keyboard, motion, contrast, forced-color, and print
  requirements;
- the repository's own required checks;
- deployment and live-verification boundaries.

The shared assets expose no network calls, analytics, cookies, storage, model
state, or hidden telemetry. A source merge is not a deployment claim.

## Delivery sequence

1. Audit the current public inventory and canonical source map.
2. Bootstrap or refresh every high-confidence static, Next.js, Gradio, or
   Streamlit source repository on `design/szl-public-experience-v3`.
3. Run the repository-owned `SZL Public Experience v3 Contract`.
4. Squash-merge only after reported checks complete green.
5. Let the source-owned publisher deploy the application.
6. Let the Living Constellation operator restart only eligible runtimes and
   read them back.
7. Browser-audit every public Space and both canonical domains.
8. Keep exact residuals open; never label a merge, restart request, or source
   file as a live deployment by itself.

## Truth boundary

This standard proves responsive presentation and bounded runtime reachability
only for the recorded observation window. It does not prove model quality,
dataset freshness, policy correctness, receipt truth, source parity, or future
availability unless the corresponding independent evidence contract also
passes.
