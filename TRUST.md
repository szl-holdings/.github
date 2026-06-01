# Trust

This document records the verifiable trust posture of SZL Holdings. Every claim
below resolves to a link, a commit SHA, or a CI workflow run. Claims that are not
yet verifiable are marked as roadmap items, not as current state.

This file is governed by [SZL Doctrine v7](doctrine/DOCTRINE_V7.md), in
particular §2 (No Hallucinations / No Fake Green) and §7 (Every Claim Citable).

## Doctrine v7

Governance doctrine, including the banned-token policy and the honesty rules
that bind this document: [`doctrine/DOCTRINE_V7.md`](doctrine/DOCTRINE_V7.md).

## Provenance — SLSA Level 1 (honest)

Provenance is documented at SLSA Level 1: source and build steps are recorded.
The truth pass that set this level honestly (rather than asserting an
unverifiable higher level) is recorded in
[PR szl-holdings/.github#103](https://github.com/szl-holdings/.github/pull/103).

Levels 2 and 3 (Sigstore signing + isolated, hardened builders) are roadmap
items and are NOT claimed here.

## Signed commits (DCO)

Commits carry a Developer Certificate of Origin sign-off
(`Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>`), enforced by
the DCO check. This requirement is set in
[Doctrine v7 §5](doctrine/DOCTRINE_V7.md#5--signed-commits-dco).

## CODEOWNERS coverage

Default code ownership for the org is declared in
[`.github/CODEOWNERS`](.github/CODEOWNERS). Repositories that do not define
their own CODEOWNERS inherit this default; per-repo files override it.

## CodeQL

CodeQL static analysis runs in CI. A recent completed run with a `success`
conclusion on the `.github` repository (commit `d304951`):
[run 26699048618](https://github.com/szl-holdings/.github/actions/runs/26699048618).

A recent completed CodeQL run with a `success` conclusion on the `platform`
repository (commit `90ad450`):
[run 26699466180](https://github.com/szl-holdings/platform/actions/runs/26699466180).

CodeQL status reflects the run linked above at the SHA shown. It is not a
standing guarantee about later commits.

## SSRF guards

Server-side request forgery protection: an SSRF allowlist validation on webhook
delivery was added to the platform in
[PR szl-holdings/platform#252](https://github.com/szl-holdings/platform/pull/252).

## No-marketing-token policy

Public artifacts are screened against a banned-token list (marketing
superlatives). The policy and the token list are defined in
[Doctrine v7 §1 — No Marketing Superlatives](doctrine/DOCTRINE_V7.md#1--no-marketing-superlatives).

## Founder identity

- Founder and CEO: Stephen P. Lutar Jr.
- ORCID: [0009-0001-0110-4173](https://orcid.org/0009-0001-0110-4173)
- GitHub: [stephenlutar2-hash](https://github.com/stephenlutar2-hash) and
  [betterwithage](https://github.com/betterwithage)
- Corporate email: stephen@szlholdings.com
- DCO sign-off email: stephenlutar2@gmail.com

## Live numbers

The following Lean proof-corpus numbers were verified at a specific commit. They
may drift as the corpus changes; re-verify against current HEAD before reuse.

Verified at commit
[`c7c0ba17`](https://github.com/szl-holdings/lutar-lean/commit/c7c0ba17)
(`lutar-lean`, tag `lutar-v18.0.0`, Doctrine v11):

- Declarations: 749
- Unique axioms: 14
- Sorries: 163

Source of truth: [`.github/data/lean_numbers.json`](./.github/data/lean_numbers.json)
(measured 2026-05-31, method documented in `.github/scripts/lean_numbers.py`).
The previous figures (626 declarations / 189 sorries) were accurate at the
earlier commit `3de37e5` and are superseded by the v11-locked counts above.

## Deliberately NOT claimed

To stay within Doctrine v7 §2, this document does NOT assert:

- SOC 2, ISO 27001, or any external audit certification (none held).
- A "trusted by" customer or logo list.
- Any badge or status not backed by a resolving link or SHA above.
