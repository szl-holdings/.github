# A11oy Holo-Constellation — Space Estate Rollout

This controller extends the reviewed Holo-Constellation v2 system from the two public origins into the source repositories that publish the `SZLHOLDINGS` Hugging Face Space estate.

## Goal

Every Space should feel deliberately designed for its own purpose while still belonging to the same ecosystem. Shared mechanics are consistent; visual identity is Space-specific.

### Shared mechanics

- Command / Products / Proof / Source / Spaces navigation;
- 44px interaction targets and visible keyboard focus;
- reduced-motion, increased-contrast, forced-colors, narrow-screen, safe-area, and print behavior;
- first-party local assets with no analytics, cookies, storage, runtime fetch, CDN, or external font;
- a clear truth boundary: decorative motion is not measured telemetry.

### Unique identity

Each Space receives a deterministic palette derived from its slug. Spaces associated with a product family also receive the relevant SZL motif:

- Lyte — signal aurora;
- Vessels — bathymetric radar;
- Terra — topographic parcels;
- Aegis — threat lattice;
- PRISM Counsel — case facets;
- Carlota Jo — editorial orbit;
- Nexus — connection field;
- Factory / Forge / Atelier — assembly circuit;
- Ouroboros — recursive ring;
- KHIPU — woven proof;
- Killinchu — governed agent swarm.

Two Spaces in the same product family retain the family motif but receive separate deterministic palettes and labels. Unknown future Space slugs receive a stable independent motif and palette; themes never reshuffle between deployments.

## Source authority

The controller reads the current public Hugging Face inventory and resolves GitHub source repositories through:

1. the canonical `a11oy` Space source map;
2. an exact normalized repository-name match.

It writes only to GitHub review branches. It does not push directly to Hugging Face. The existing canonical publisher remains the release authority.

Unmapped, archived, ambiguous, or unsupported sources are reported without mutation.

## Supported adapters

### Static HTML

Local CSS and JavaScript are written beside the selected entrypoint, and exactly one stylesheet and script binding are added.

### Next.js layout/document

Local assets are written under the appropriate `public` directory and bound in the selected root layout or document.

### Gradio

A local Python helper embeds the reviewed CSS and a Space-specific JavaScript runtime. The controller uses Python AST positions to add or compose `css=` and `head=` arguments. Existing string-compatible CSS and head expressions are preserved and extended rather than overwritten.

### Streamlit

A local CSS-only helper is installed after `st.set_page_config`, preserving Streamlit ordering requirements. It supplies the Space-specific palette and shared ecosystem rail without attempting unsupported parent-frame JavaScript.

## Fail-closed rules

The controller refuses to guess when:

- a Space has no source-of-truth mapping;
- a repository tree is truncated;
- the frontend entrypoint is not one of the supported shapes;
- multiple Spaces collide on the same source files;
- a review branch exists without an open pull request;
- a Gradio custom expression cannot be safely composed;
- Python or HTML cannot be parsed with confidence.

No default-branch writes, force pushes, protection changes, direct Hugging Face writes, or secret values appear in the report.

## Dry run

```bash
python .github/scripts/holo_space_rollout_v2.py \
  --report reports/holographic-space-rollout-v2.json
```

## Apply

```bash
GH_ORG_TOKEN=... python .github/scripts/holo_space_rollout_v2.py \
  --apply \
  --report reports/holographic-space-rollout-v2.json
```

The organization workflow performs the apply pass only after this controller has merged through protected `main`. Every generated source change remains a normal pull request and must satisfy that repository's CI before promotion.
