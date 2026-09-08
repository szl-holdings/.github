# Archive revival wave — 2026-09-06

This directory records the original September 6 inventory of **34 public
archived repositories** and its current governed disposition. The September 8
[executable recovery review](../../docs/ARCHIVE_RECOVERY_20260908.md) supersedes
the original four-owner decision with the six-owner set below.

The governed v2 contract is implemented by:

- `governance/archive-portfolio-v2.json`
- `.github/scripts/archive_portfolio_governor_v2.py`
- `.github/tests/test_archive_portfolio_governor_v2.py`
- `.github/workflows/archive-portfolio-governor-v2.yml`
- `docs/ARCHIVE_PORTFOLIO_V2.md`

## Decision

Restore exactly six unique source owners:

- `szl-atelier`
- `szl-build-env`
- `szl-mesh`
- `szl-router`
- `uds-bundles`
- `vsp-otel`

Retain twenty-two consolidation tombstones and six immutable historical records.
The manifest contains the exact canonical target and Hugging Face showcase for
every archived repository.

## Production review

The restoration job retains the `production` environment gate. A solo-builder
owner review is admitted only through
`.github/workflows/owner-deployment-review-bridge.yml`, which requires an issue
authored by the exact estate owner and binds the decision to one repository, one
protected-main SHA, one workflow run, one workflow path, and the exact
`production` environment ID. Its provider review and post-review readback are
retained as a secret-free artifact and issue receipt.

The review bridge cannot approve another workflow, environment, branch, SHA, or
repository, and it cannot mutate repository settings, source, visibility,
protections, secrets, or Hugging Face.

## Evidence boundary

Merging this source contract is not an unarchive claim. The protected-main
workflow must report provider readback with `archived=false` for all six exact
repositories. Source modernization, Hugging Face publication, runtime readiness,
and exact live source binding remain separate evidence stages.

No direct default-branch write, visibility change, history rewrite, protection
change, secret mutation, or direct Hugging Face mutation is authorized.
