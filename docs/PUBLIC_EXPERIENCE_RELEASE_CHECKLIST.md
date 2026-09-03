# Public Experience Release Checklist

Use this checklist for every active SZL website, web app, and canonical Hugging Face flagship Space.

## Mobile and responsive
- [ ] 320x568: no unintended horizontal page overflow.
- [ ] 375x812: core workflow usable one-handed.
- [ ] 390x844 and 430x932: controls, cards, tables, code, and dialogs remain contained.
- [ ] 768x1024 and 1024x768: tablet composition uses space intentionally.
- [ ] 1440x900 and 1920x1080: bounded readable line lengths and no excessive empty canvas.
- [ ] 2560x1440 and 3440x1440: theatre layout adds structure rather than stretching content.
- [ ] Phone landscape: primary controls remain reachable.
- [ ] Safe-area insets are respected.

## Accessibility
- [ ] Primary interactive targets are at least 44x44 CSS px; 48px preferred on coarse pointers.
- [ ] Visible keyboard focus on all interactive elements.
- [ ] Every required workflow works without hover.
- [ ] Reduced-motion mode removes nonessential animation.
- [ ] Increased contrast / forced colors remain usable.
- [ ] Information is not encoded by color alone.
- [ ] Semantic headings, landmarks, labels, and button names are present.
- [ ] Tables, logs, code, JSON, URLs, charts, and media do not break the viewport.

## First-time user
- [ ] Product purpose is clear in one sentence.
- [ ] Intended user is clear.
- [ ] One primary action is visually dominant.
- [ ] Live/status/evidence state is understandable without reading raw JSON.
- [ ] Empty, loading, error, and UNAVAILABLE states are explicit and useful.
- [ ] Navigation uses familiar labels.

## Developer experience
- [ ] Canonical GitHub source is linked.
- [ ] Build/version or source revision is available where applicable.
- [ ] API/health endpoints are documented where applicable.
- [ ] README/card includes quick start and architecture boundary.
- [ ] Raw evidence remains inspectable through progressive disclosure.
- [ ] License and contribution path are discoverable.

## Investor / diligence experience
- [ ] Vertical and user problem are immediately legible.
- [ ] Differentiated capability is stated without unverifiable claims.
- [ ] Operational proof or current boundary is linked.
- [ ] Portfolio context is reachable in <=2 interactions.
- [ ] MEASURED / REPORTED / MODELED / UNAVAILABLE / UNSIGNED / CONJECTURE labels are used consistently.

## Release evidence
- [ ] Relevant CI is green.
- [ ] Responsive/accessibility regression test is included for significant UI changes.
- [ ] No source/evidence/security/approval semantics changed unintentionally.
- [ ] Runtime deployment is live-verified when runtime files changed.
