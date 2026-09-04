# SZL Frontier Design Kernel v1

## Decision

A11oy, Killinchu, and Hatun are one ecosystem, not three unrelated templates and not three recolored copies. They share a single versioned visual grammar while retaining distinct product identities.

| Surface | Role | Distinct identity |
|---|---|---|
| A11oy | governed command fabric | graphite, cyan, and restrained gold; alloy-lattice geometry |
| Killinchu | aerial intelligence and defense | deep navy, electric sky, and condor amber; directional flight lines |
| Hatun | sovereign orchestration layer | obsidian violet, orchid, and mineral green; radial khipu rings |

## Shared grammar

The kernel standardizes:

- spacing and readable content widths;
- typography and hierarchy;
- one compact ecosystem rail;
- cards, buttons, chips, tables, code surfaces, and form controls;
- visible keyboard focus and 44-pixel minimum controls;
- responsive horizontal navigation instead of clipped navigation;
- reduced-motion, forced-colors, and print behavior;
- progressive reveal motion that disappears when reduced motion is requested.

It does **not** standardize product-specific information architecture, hero copy, application workflows, data semantics, or operational status language.

## Runtime boundary

The CSS and JavaScript are vendored into each target repository at an exact reviewed Git SHA. They make no network request and contain no CDN, analytics, cookie, local-storage, authentication, API, model, or mutation dependency. The top rail's “Public surface” chip means only that the presentation shell loaded; it is not a backend-health claim.

The JavaScript performs additive progressive enhancement:

1. identifies the declared brand from `data-szl-frontier`;
2. installs one accessible ecosystem rail if absent;
3. upgrades only explicitly marked components;
4. observes explicitly marked reveal elements;
5. emits `szl:frontier-ready` with `authority: PRESENTATION_ONLY`.

## Source and rollout

Authoritative files:

```text
.github/design/frontier-v1/brands.json
.github/design/frontier-v1/szl-frontier.css
.github/design/frontier-v1/szl-frontier.js
.github/scripts/rollout_frontier_design.py
.github/workflows/frontier-design-rollout.yml
```

Every rollout follows:

```text
Resolve registered repository
→ Discover bounded entry points
→ Clone default branch
→ Create candidate branch
→ Vendor exact CSS/JS
→ Add marker-delimited hooks
→ Write source-binding contract
→ Run offline tests and Python compilation
→ Push candidate branch
→ Open protected pull request
→ Merge only through repository governance
→ Deploy through that repository's existing canonical publisher
→ Verify the live public surface
```

The rollout controller never pushes a target default branch, alters branch protection, changes DNS, changes Hugging Face hardware, changes billing, writes runtime data, or exposes a token. Hatun repository discovery is explicit: it checks registered dedicated repositories first and uses the registered A11oy `/wires` source only when no dedicated runnable entry point exists.

## Installation contract

Each target receives:

```text
design/szl-frontier-contract.json
<served-asset-root>/szl/frontier-v1/szl-frontier.css
<served-asset-root>/szl/frontier-v1/szl-frontier.js
tests/test_szl_frontier_design.py  # or root fallback when no tests directory exists
```

Page hooks are bounded by these markers:

```html
<!-- szl-frontier-design:head:v1 -->
<link rel="stylesheet" href=".../szl-frontier.css" data-szl-frontier-asset="css-v1">
<!-- /szl-frontier-design:head:v1 -->

<body class="szl-frontier" data-szl-frontier="a11oy|killinchu|hatun">

<!-- szl-frontier-design:body:v1 -->
<script src=".../szl-frontier.js" defer data-szl-frontier-asset="js-v1"></script>
<!-- /szl-frontier-design:body:v1 -->
```

Re-running the patcher replaces its own marker blocks and preserves all other page content.

## Acceptance gates

A candidate is not rollout-ready unless:

- the registry contains exactly the three reviewed brand adapters;
- the CSS contains all three unique token scopes and the shared accessibility behavior;
- the JavaScript has no network, storage, cookie, `eval`, or `innerHTML` path;
- every modified entry point contains exactly one head and body marker;
- asset bytes match the SHA-256 values in the target contract;
- `git diff --check` passes;
- modified Python-rendered pages compile;
- a protected pull request exists or the target is already aligned.

Live deployment remains the responsibility of each product repository's existing canonical publisher. A merged design PR is not represented as live until its public origin is observed with the expected assets and brand marker.
