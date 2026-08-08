<!-- markdownlint-disable MD013 -->

# Public front-door experience audit — 2026-08-01

Status: **SOURCE REVIEWED; DEPLOYMENT NOT CLAIMED**

This audit is intentionally limited to files in the public `.github`
repository and public URLs already named by those files. It contains no
non-public inventory, private identifiers, or non-public operating details.

## Release scope

The release unifies two organization front doors:

- the GitHub organization profile in `profile/README.md`;
- the Hugging Face organization card in `huggingface/org-card/`.

It does not claim that every repository, model card, dataset card, or Space has
been restyled. It does not infer production readiness from a reachable page,
published artifact, badge, signature, screenshot, or download count.

## Design direction

The shared system uses one mission sentence, a restrained evidence-lattice
visual, four audience routes, and compact cards with explicit evidence labels.
It borrows broad product-design principles—strong hierarchy, disciplined
typography, operational clarity, and technical restraint—without copying a
third party's assets, text, or layout.

The organization card is built as a host-isolated component:

- every class uses the `szl-hf-` namespace;
- every CSS selector is scoped below `#szl-hf-org-card`;
- the root declares its embed-safety contract;
- runtime assets use an exact HTTPS URL on the served Space origin;
- navigation uses HTTPS URLs or same-document fragments only;
- no script, external stylesheet, or third-party runtime dependency is used.

## Responsive acceptance

The source contract covers phone, tablet, landscape, laptop, and wide desktop
layouts. Release evidence must demonstrate:

- no horizontal page overflow at 320, 390, 768, 844, and 1440 CSS pixels;
- minimum 44 CSS-pixel interactive targets;
- readable single-column cards on narrow screens;
- keyboard focus visibility and a working skip link;
- reduced-motion, increased-contrast, and forced-colors behavior;
- useful first-screen copy even if the decorative visual does not paint.

## Publication boundary

Hugging Face publication is authorized only from an exact protected `main`
push through the repository's protected `production` environment. The
publication workflow has no manual dispatch path. The deployment report must
remain fail-closed until all of the following are observed for the same
attempt:

1. the Space runtime reports `RUNNING`;
2. `deployment.json` is served from the expected origin and exactly matches the
   attempted source binding before and after the runtime sweep;
3. the root smoke page is served from the expected origin and contains the
   required marker;
4. every manifest file and `deployment.json` match exact bytes at the immutable
   Hugging Face commit;
5. every runtime file is hashed and satisfies its explicit exact or transformed
   readback policy;
6. no unapproved remote path is pruned.

A created Hugging Face commit without that complete readback is
`COMMIT_CREATED_UNVERIFIED`, not deployed or promoted evidence.

## Truth boundaries

- `PROVED` is reserved for a scoped proof or verified integrity statement.
- `MEASURED` names an observation with a source and time boundary.
- `REPORTED`, `MODELED`, `CONJECTURE`, and `ROADMAP` remain visibly distinct.
- Runtime reachability is not feature correctness, safety, quality, adoption,
  profitability, compliance, or authority to operate.
- Killinchu's public actuation boundary remains **SIMULATED**; this surface does
  not command a live weapon or establish production authorization.
- The historical profile mirror is not a current organization card, inventory,
  runtime source, or release witness.

## Release evidence required

Before merge:

- signed commits and DCO trailers;
- terminal exact-head checks and App attestation;
- zero unresolved review threads;
- host-isolation, publication, responsive, accessibility, and privacy
  regressions passing on the exact head;
- normal protected merge-queue admission with no bypass or self-approval.

After merge:

- a verified protected-main merge commit and exact tree readback;
- an approved `production` environment deployment from that merge revision;
- a `VERIFIED` report with immutable and runtime per-file evidence and no
  unexpected deletions;
- live browser checks at the target phone, tablet, landscape, and desktop
  sizes.

Until those observations exist, this document describes reviewed source only.
