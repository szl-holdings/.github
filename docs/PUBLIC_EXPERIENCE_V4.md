# SZL Public Experience v4 — audience readiness

Public Experience v4 is the release gate shared by the SZL product domain, proof origin, A11oy, Killinchu, David Leads, Terra, Sentra, PRISM Counsel, PURIQ Finance, Vessels, and Lyte.

## Audience hierarchy

Every public surface must let three audiences answer a distinct question without searching the repository:

1. **User:** What does this product do, what is its current state, and what can I safely do next?
2. **Developer:** Where are the API, source, schema, build identity, and technical evidence?
3. **Investor or reviewer:** Where are the proof, source authority, governance boundary, limitations, and deployment evidence?

These paths use progressive disclosure. A phone view is not a desktop dashboard scaled down, and investor proof does not displace the primary user task.

## Browser matrix

The durable read-only auditor evaluates:

- 320×568 and 375×812 phone layouts;
- 768×1024 tablet layout;
- 1440×900 desktop layout;
- 200% and 400% reflow equivalents;
- reduced-motion phone behavior;
- keyboard focus on phone and desktop.

## Required behavior

A target passes only when it:

- returns an exact HTTP 200 root;
- renders a nonempty title, `lang`, `h1`, and main landmark;
- has no document-level horizontal overflow;
- keeps visible touch targets at least 44 pixels where direct spacing is not independently attested;
- exposes visible focus and a usable keyboard path;
- removes long motion when reduced motion is requested;
- avoids a full-viewport interactive overlay;
- exposes visible developer and investor/proof paths;
- avoids insecure `http://` links and uncaught page errors;
- publishes the Public Experience source marker for every Hugging Face Space.

## Truth and authority

The browser auditor is read-only. It does not log in, submit a form, invoke an action-bearing route, mutate DNS, write a Space, alter Cloudflare, change hardware, or convert an unavailable provider into a successful claim.

Each run retains JSON, Markdown, screenshots, browser errors, failed subresources, target summaries, and SHA-256 screenshot and Proof Chain digests for 180 days. One durable issue records the newest observed state; the immutable artifact preserves the full historical evidence.

## Design influence boundary

The contract adopts durable interaction principles common to strong consumer and developer products—clear hierarchy, focused primary action, generous touch geometry, responsive composition, progressive disclosure, direct technical evidence, and restrained motion. It does not copy another company’s source, wording, visual identity, trade dress, assets, or page composition.
