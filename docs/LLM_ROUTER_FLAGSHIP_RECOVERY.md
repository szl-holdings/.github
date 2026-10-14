# SZL LLM Router — Flagship Recovery

**Decision date:** 2026-09-08  
**Classification:** FLAGSHIP  
**Canonical source:** `szl-holdings/szl-router`  
**Hugging Face runtime/showcase:** `SZLHOLDINGS/llm-router-live`

## Decision

The August 29 consolidation treatment that made `llm-router-live` private and
paused is superseded **for the LLM Router only**. Historical ledgers remain in
place as records of what happened; they are not the current operating order for
this asset.

The intended authority chain is:

```text
szl-holdings/szl-router@main
        ↓ exact immutable source revision
SZLHOLDINGS/llm-router-live
        ↓ integrated product route
https://a-11-oy.com/code
        ↓ receipts, evaluations, known bounds
https://a11oy.net
```

`szl-router` is the canonical router source. A11oy remains the portfolio control
plane and integrated operator interface; it is not a license for an independent,
divergent router implementation. The Hugging Face Space is the public runtime and
showcase mirror, not the source of truth.

## Required state

- GitHub repository is public and unarchived.
- Repository metadata identifies the router as a flagship and names
  `SZLHOLDINGS/llm-router-live` as its runtime mirror.
- The Hugging Face Space is public, running, and published from the exact GitHub
  source revision under `space/`.
- The Hugging Face organization card contains the source-controlled flagship
  block.
- The A11oy `/code` route remains the integrated operator-facing interface.
- Runtime status is one of `LIVE`, `CONFIGURED_UNVERIFIED`,
  `OFFLINE_UNTIL_KEYED`, or `UNAVAILABLE`; a provider is never implied to be
  active merely because a card or Space is visible.

## Product contract

The flagship router exposes the OpenAI-compatible logical model surface:

- `szl-auto`
- `szl-fast`
- `szl-large`
- `szl-coder`

Its durable differentiation is not a larger model claim. It is a sovereign-first
provider route, deterministic or policy-informed model selection, explicit
fallback attempts, and a receipt that preserves the routing rationale and
serving provenance.

## Authority and secret boundary

- Provider credentials remain deployment secrets and are never committed.
- A public Space may show whether a provider is configured or observed; it may
  not expose a secret value.
- A routing receipt proves the recorded routing event under its stated scope. It
  does not prove model quality, factual truth, regulatory compliance, or
  authorization.
- Model output does not authorize consequential action.
- Lambda remains advisory; Lambda uniqueness remains Conjecture 1 — open.

## Automation

**Retired 2026-10-13.** `.github/workflows/restore-llm-router-flagship.yml` and
`.github/workflows/restore-llm-router-flagship-v2.yml` are disabled stubs: they
run only on dispatch, their single job is `if: ${{ false }}`, and they hold no
credential, checkout or write authority. Their GitHub administration writes went
through a variable HTTP method that the CP-eBOM checker cannot model or budget,
and every edit to their sources started a live `--apply` run (the #894 merge on
2026-10-11 did so and stopped after partial writes). The Space's public/RUNNING
state is owned by `.github/workflows/hf-space-lifecycle-reconcile.yml`, and the
organization card by `.github/workflows/hf-org-card-autopublish.yml`. Apart from
the bounded `archived: true -> false` restore in
`.github/workflows/archive-portfolio-governor-v2.yml`, no workflow in this
repository now edits `szl-holdings/szl-router` metadata (description, homepage,
issues, topics) or publishes its `space/` tree to the Space. The controller
scripts under `scripts/` are kept as historical source and are no longer run.

Historically, `.github/workflows/restore-llm-router-flagship.yml` performed the
bounded restoration after protected merge. It:

1. unarchives and relabels the existing GitHub repository;
2. obtains its exact `main` revision;
3. downloads the source archive and stages only the source-owned `space/`
   directory;
4. writes the exact source revision and provenance record into the staging
   context;
5. makes the existing Hugging Face Space public, uploads the exact staged
   context, restarts it, and waits for a terminal running state;
6. inserts the source-controlled router block into the Hugging Face organization
   card;
7. verifies the A11oy `/code` product surface;
8. emits an immutable restoration receipt.

The controller will not create a second router Space when the expected Space is
missing or inaccessible. It fails with an exact credential or provider blocker
instead.
