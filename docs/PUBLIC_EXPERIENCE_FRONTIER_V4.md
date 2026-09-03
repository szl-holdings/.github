# SZL Public Experience Frontier v4

Status: governing public-surface standard for active SZL Holdings websites, web applications, and canonical Hugging Face flagship Spaces.

## Purpose

Every public SZL surface must be immediately understandable to a first-time user, usable on phones and tablets, efficient for developers, credible for investors and diligence reviewers, and honest about what is live, measured, modeled, reported, or unavailable.

This standard adapts durable interaction principles from leading technology companies without copying their branding. Apple emphasizes hierarchy, consistency, adaptable layouts, familiar interactions, multiple input methods, and sufficiently large controls. NVIDIA publicly targets WCAG 2.2 Level AA and incorporates accessibility into its brand and development workflow. SZL adopts those principles as engineering requirements while preserving its own visual identity.

## Required viewport contract

Every active public surface must be verified at 320x568, 375x812, 390x844, 430x932, 768x1024, 1024x768, 1440x900, 1920x1080, 2560x1440, and 3440x1440. No required workflow may depend on hover. There must be no unintended horizontal page overflow at any registered viewport.

The layout must be mobile-first. Compact screens use one-column composition, tablet screens use adaptive grids, desktop uses bounded readable widths, and theatre/ultrawide screens use additional structure rather than simply stretching text.

## Interaction and accessibility contract

Interactive controls must provide at least a 44x44 CSS-pixel target, with 48px preferred for touch-first contexts. All workflows must be keyboard-operable. Focus indicators must remain visible. Inputs on mobile must avoid browser zoom caused by undersized text. Safe-area insets must be respected. Reduced-motion, increased-contrast/forced-colors, and print modes must degrade cleanly.

Information cannot be conveyed by color alone. Tables, code, logs, charts, long URLs, and JSON must remain readable without breaking page width. Modals and drawers must fit within the dynamic viewport and remain dismissible by keyboard.

## First-30-seconds user contract

A new visitor must be able to answer, without reading a README:

1. What is this product?
2. Who is it for?
3. What can I do here now?
4. What is actually live versus modeled or unavailable?
5. Where is the source/evidence?
6. What should I click next?

Each flagship therefore needs a concise hero, one primary action, one evidence/status surface, and clearly labeled secondary paths.

## Developer contract

Every product-facing surface must expose or link to canonical source, API/build information when available, documentation, evidence semantics, and a reproducible path for local or integration use. Technical payloads should be progressively disclosed so first-time users are not greeted by raw JSON while developers can still inspect exact responses.

README and public cards must include: purpose, architecture boundary, quick start, API/health endpoints where applicable, source ownership, license, evidence/truth vocabulary, and current runtime boundary.

## Investor and diligence contract

Every flagship must make the business and proof story legible without marketing overclaim. A diligence visitor should be able to find the vertical, user problem, differentiated capability, current operational proof, canonical repository, portfolio context, and evidence boundary in two interactions or fewer.

Do not fabricate users, revenue, deployment scale, certifications, performance, model quality, or production status. Use the SZL evidence vocabulary consistently: MEASURED, REPORTED, MODELED, UNAVAILABLE, UNSIGNED, and CONJECTURE.

## Visual system contract

Keep the SZL dark/holographic identity, but prioritize content hierarchy over decoration. Use restrained motion, large typography with bounded line lengths, clear section rhythm, predictable navigation, high-contrast controls, and consistent component behavior. Decorative 3D/holographic effects must never block content, keyboard navigation, touch targets, or reduced-motion users.

## Canonical nine Hugging Face flagship targets

The public estate is limited to A11oy Command, Killinchu, Terra, Sentra, PRISM Counsel, PURIQ Finance, Vessels, Lyte, and David Leads. Folded or private laboratory Spaces are not independent public products and should not be reintroduced into public navigation.

All nine flagships must meet this standard before being represented as polished public demos.

## Release gate

A public-experience change is merge-ready only when its relevant CI is green and the change preserves source/evidence honesty. Runtime-changing work additionally requires live verification after deployment. Responsive styling must not mutate evidence semantics, security controls, approval boundaries, model claims, or receipt behavior.
