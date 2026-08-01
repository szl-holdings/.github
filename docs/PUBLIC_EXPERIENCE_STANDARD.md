<!-- markdownlint-disable MD013 -->

# SZL public experience standard

Status: **ADOPTED AS A ROLLOUT CONTRACT**. Individual surfaces remain
unchanged until their own protected pull requests pass verification.

This standard makes the SZL estate legible as one company while preserving
the technical and evidentiary boundaries of each product. It governs public
websites, GitHub repositories, Hugging Face artifacts, documentation, demos,
and investor-facing materials.

## Audience order

Every public surface must serve one primary audience and provide direct exits
for the other two.

1. **Investor or buyer:** What category is this, who needs it, what outcome
   does it create, and what evidence supports the claim?
2. **Builder or integrator:** How can I run, evaluate, integrate, and debug it?
3. **Verifier or reviewer:** Where are the exact source, policy, evaluation,
   receipt, security, and limitation records?

Do not make all three audiences read the same long page in the same order.

## Surface responsibilities

| Surface | Primary job | Must not become |
| --- | --- | --- |
| `a-11-oy.com` | Product narrative, use cases, demonstrations, conversion | A raw evidence dump or repository index |
| `a11oy.net` | Independent proof registry and receipt verification | A duplicate marketing homepage |
| Killinchu | Operator-focused demonstration and mission workflow | An ungrouped collection of technology tabs |
| GitHub organization | Company thesis, product map, diligence, developer routing | A full Space directory or live status dashboard |
| GitHub repository | Project outcome, maturity, quickstart, architecture, limits | Generic company boilerplate before the project |
| Hugging Face organization | Curated model, dataset, and Space portfolio | An unordered artifact feed |
| Model or dataset card | Reproducible artifact contract and limitations | Marketing copy without metadata or evaluation |
| Documentation site | Task-oriented learning and complete reference | A product homepage duplicate |

## Shared navigation

Product websites should use at most seven stable top-level destinations:

1. Product
2. Solutions
3. Developers
4. Evidence
5. Research
6. Company
7. Get started

Use task-specific secondary navigation. Every deep page must expose its active
section, a route home, and a route to documentation or evidence. The canonical
labels must stay consistent across domains.

## Visual system

The KANCHAY system is the single source of visual language.

### Token authority

The versioned
[`szl-brand` color tokens](https://github.com/szl-holdings/szl-brand/blob/cebb154c6445b1eefc5024f5d988bb701bbdded2/kit/tokens/COLOR_TOKENS.json)
and
[`szl-design-system.css`](https://github.com/szl-holdings/szl-brand/blob/cebb154c6445b1eefc5024f5d988bb701bbdded2/kit/tokens/szl-design-system.css)
are the canonical token authority. Consumers import the JSON, CSS, SCSS, or
Tailwind representation from `szl-brand`; this document defines usage and does
not duplicate color values.

Color is never the only carrier of state. Every state includes a visible text
label and, where appropriate, a timestamp and source.

### Typography and layout

- Use one sans-serif family for interface and prose and one monospace family
  for evidence, code, identifiers, and metrics.
- Keep body text between 60 and 78 characters per line.
- Use an 8-pixel spacing base and a restrained type scale.
- Prefer one strong visual or product capture over decorative card walls.
- Reserve motion for state change or spatial explanation; honor reduced motion.
- Avoid fake terminal decoration, ornamental grids, and glowing effects when
  they do not explain a product behavior.

## Narrative sequence

An investor-facing product page should follow this order:

1. Category, audience, outcome, and primary action in the first viewport.
2. Product in context: a real interface, workflow, or verified demonstration.
3. The problem and the economic or operational consequence.
4. Three to five capabilities expressed as outcomes.
5. Evidence with source, scope, and date.
6. Architecture and differentiation.
7. Security, limitations, and operational status.
8. Developer path and integration options.
9. Company, contact, and final action.

Metrics without a current source, timestamp, unit, and scope do not ship.
Customer logos, certifications, authorizations, and performance claims require
their own evidence.

## Evidence vocabulary

| Label | Contract |
| --- | --- |
| **PROVED** | Machine-checked statement with exact theorem or artifact scope |
| **MEASURED** | Direct observation with disclosed instrument, time, and context |
| **REPORTED** | Identified upstream statement, not independently measured here |
| **MODELED** | Simulation, projection, or analytical derivation |
| **CONJECTURE** | Formal hypothesis that remains unproved |
| **ROADMAP** | Planned capability with no operational claim |

Operational status is separate from evidence class. Use **OPERATIONAL**,
**PARTIAL**, **DEGRADED**, **UNAVAILABLE**, or **HISTORICAL**. Never use green
styling for conjectures, roadmap items, partial capability, or unavailable
evidence.

Lambda is an advisory score. A separately named policy gate is the enforcing
control. Public copy must not call Lambda both advisory and an enforcement gate.

## Repository front door

Every active repository README must include, in this order:

1. Project name and one-sentence user outcome.
2. Maturity/status with a linked source.
3. Product, docs, demo, or evidence actions when applicable.
4. Problem and capabilities.
5. A tested quickstart that takes less than ten minutes.
6. Architecture and trust boundaries.
7. Configuration without secret values.
8. Native verification commands.
9. Limits and non-goals.
10. Security, contribution, support, changelog, and actual license.

Badges are supporting metadata, not the hero. Do not use a green status badge
unless the linked source establishes that exact state.

## Hugging Face portfolio

### Organization card

The organization card must state the company thesis, link the product and
evidence surfaces, explain the artifact taxonomy, and feature only canonical
release families. It must route users to support and security reporting.

Use four explicit artifact classes:

- **trained weights** with training, evaluation, and lineage evidence;
- **datasets** with provenance, schema, privacy, and validation evidence;
- **governed kernels and tools** with source and executable-test evidence, but
  no implied model-training receipt;
- **Spaces** with source, immutable dependencies, runtime behavior, and
  demonstration limits.

### Collections

Collections represent a release family or a complete workflow:

- one canonical model family per collection;
- related adapters, quantizations, datasets, evaluations, and demos;
- explicit ordering from primary artifact to derived artifacts;
- a short scope and maturity statement;
- no duplicate or unexplained entries.

### Models

Model cards require valid metadata, immutable revision guidance, intended and
excluded uses, architecture, training and data lineage, preprocessing,
evaluation protocol and results, safety and bias limits, hardware needs,
reproducible usage, license, citation, support, and changelog.

### Datasets

Dataset cards additionally require schema, splits, sizes, provenance and
consent, PII handling, validation, known gaps, and update policy. Synthetic,
public, licensed, and derived data must remain distinguishable.

### Spaces

Every Space states its source repository, pinned model and dataset revisions,
runtime status behavior, data retention or privacy behavior, limitations, and
a reproducible local path. A visible demo is not evidence of production
readiness.

Use the templates in [`templates/`](../templates/README.md) as the adoption
baseline.

## Accessibility and performance gate

Critical user flows target WCAG 2.2 AA. Verification includes keyboard-only
navigation, visible focus, semantic landmarks, heading order, labels, contrast,
200 percent zoom, mobile reflow, reduced motion, and useful error messages.

For public websites, measure both mobile and desktop at the 75th percentile:

- Largest Contentful Paint at or below 2.5 seconds;
- Interaction to Next Paint at or below 200 milliseconds;
- Cumulative Layout Shift at or below 0.1.

Do not trade accessibility, truth labels, or core product usability for a
perfect synthetic performance score.

## Protected rollout gate

Each surface upgrades independently through normal protection:

1. Refresh the exact default-branch base and active ownership locks.
2. Inventory routes, entry points, content sources, deployment owners, and
   generated evidence.
3. Make the smallest coherent surface change.
4. Run native lint, type, test, build, link, metadata, and accessibility checks.
5. Exercise the primary investor, builder, and verifier journeys end to end.
6. Confirm no unresolved review findings and no source drift.
7. Merge normally; do not bypass, self-approve, or weaken a gate.
8. Verify the deployed immutable revision before calling the surface upgraded.

An approved standard is not evidence that all surfaces have adopted it. Track
adoption by repository and immutable revision, and label unmodified surfaces
as pending.

## Rollout order

1. Organization profile, templates, and brand tokens.
2. Company homepage and documentation navigation.
3. Flagship product and proof registry.
4. Killinchu information architecture and operator flows.
5. Canonical GitHub repositories by product family.
6. Hugging Face organization card and release-family collections.
7. Model, dataset, and Space cards, prioritized by active usage.
8. Long-tail repositories and historical surface cleanup.

This order creates a dependable source of truth before multiplying changes
across the estate.
