# Archive revival wave — 2026-09-06

This directory records the corrected, source-bound archive disposition. The live
authenticated inventory contained **34 public archived repositories**.

The governed v2 contract is implemented by:

- `governance/archive-portfolio-v2.json`
- `.github/scripts/archive_portfolio_governor_v2.py`
- `.github/tests/test_archive_portfolio_governor_v2.py`
- `.github/workflows/archive-portfolio-governor-v2.yml`
- `docs/ARCHIVE_PORTFOLIO_V2.md`

## Decision

Restore exactly four unique source owners:

- `szl-atelier`
- `szl-mesh`
- `szl-router`
- `uds-bundles`

Retain twenty-four consolidation tombstones and six immutable historical records.
The manifest contains the exact canonical target and Hugging Face showcase for
every archived repository.

## Evidence boundary

Merging this source contract is not an unarchive claim. The protected-main
workflow must report provider readback with `archived=false` for all four exact
repositories. Source modernization, Hugging Face publication, runtime readiness,
and exact live source binding remain separate evidence stages.

No direct default-branch write, visibility change, history rewrite, protection
change, secret mutation, or direct Hugging Face mutation is authorized.
