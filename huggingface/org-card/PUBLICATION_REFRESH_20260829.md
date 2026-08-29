# Organization-card publication refresh — 2026-08-29

## Observed state

- last organization-card content revision: `szl-holdings/.github@219a1f7bd4702beecfdeeb198873b285d2ebb4fa`
- protected repository main before this refresh: `szl-holdings/.github@efa0485e53cad22cc2b21de5e5bb6949f4249638`
- live `deployment.json` source revision: `fba2755a14bed4d48befce97e0acc96f3b58f0f5`
- target: `SZLHOLDINGS/README`
- live base URL: `https://szlholdings-readme.static.hf.space`

## Purpose

This source-bound receipt intentionally touches the organization-card publication path so the existing protected-main workflow republishes the already reviewed Series A card from the exact resulting repository revision and verifies that revision through the live deployment readback.

The profile-only commit after the card-content revision did not alter the card manifest or public bundle, but it advanced protected repository `main`; the publication contract must therefore bind the exact new signed squash revision produced by this refresh PR.

It changes no model, dataset, kernel, evaluation, capability, authorization, deployment-quality, or investment claim. The production workflow and its immutable readback remain the authority for completion.
