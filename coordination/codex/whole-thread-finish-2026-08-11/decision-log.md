# Phase 0 decision log

Observation date: 2026-08-20.

Coordination base:
`efbd45ffa094f4e702ce3fbc470dd4a36705eb3e`.

## D-001 — Current evidence supersedes historical checkpoints

The v16.7 package and the 2026-08-13 recapture remain historical inputs only.
All mutable repository, Hub, runtime, domain, and database facts in this Phase 0
candidate were read again on 2026-08-20.

## D-002 — W0R is blocked, not falsely promoted

W0R is recorded as `BLOCKED_MANAGED_PREREQUISITE`. Public GitHub and
Hugging Face coverage is extensive and current, but authenticated private Hub
completeness, the exact platform production database target, and an estate-wide
source-to-artifact-to-deployment provenance matrix remain unavailable.

## D-003 — Source parity is observation, not deployment provenance

The A11oy runtime twice declared
`f5440d365471d656807a617e6b73b5b4dbe939ea`. Protected main then advanced
through PRs 1352 and 1351 to
`1b2d20e4633bb5e35181a84bdbdfdec206531198`, then PR 1349 merged as
`59f6027ad268875900cc73b2b7501e267c76d6b9`. At 10:12:40Z the runtime
declared that latest main while the Hub API reported `RUNNING` at Space
revision `e2a8312405ddf8d6875d69de7886feff17ffd991`.

This is a live deployment transition with observed source parity at its latest
read. It is not terminal deployment proof or a signed receipt because no
captured artifact digest binds the source, Space revision, and runtime readback.

## D-004 — Issue 415 contains a stale PR 411 merge SHA

The August 11 issue comment names `aef1784988…` for PR 411. Current GitHub
evidence identifies the protected merge commit as
`0d5637707cd491e7de8740e1773b205e9dda2e45`. The live PR record wins.

## D-005 — Issue 1258 labels do not alter the canonical graph

A11oy issue 1258 and related PRs use their own W1/W2/W3 labels. Those labels do
not change the W0R-W9 dependencies in this directory. No Hub or state-runtime
PR is promoted merely because a local label resembles a canonical node.

## D-006 — The visible Neon validation project is not production

`a11oy-memory-covenant-validation-20260811` is read-only validation evidence.
It is not the platform production target. The unrelated
`david-leads-production` project is outside the platform cutover scope.

## D-007 — Migration drift blocks cutover claims

Platform main contains 149 Drizzle SQL files and 148 journal entries.
`0146_eval_registry_foundation.sql` is not journaled. No migration or backfill
was attempted, and this evidence PR does not authorize a database cutover.

## D-008 — Publish evidence through a protected draft PR only

This candidate changes coordination evidence only. It does not modify workflows,
rulesets, secrets, applications, databases, Hub assets, or deployments. It must
remain unmerged until exact-head DCO, signature, hosted checks, and review-thread
gates are terminal.

## D-009 — Live estate drift is part of the evidence

The recapture is intentionally marked non-atomic. A11oy main advanced three
times as PRs 1352, 1351, and 1349 merged; the bounded readiness repair PR 1358
appeared during the observation window. Coordination PRs also changed.
Mutable heads must be recaptured again immediately before any promotion.
