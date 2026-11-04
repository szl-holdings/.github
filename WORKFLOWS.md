# SZL Holdings — Reusable Workflows

This repo hosts the reusable GitHub Actions workflows shared across the
organization. Every public repo in `szl-holdings` should consume these instead
of redefining the same logic locally.

## Why reusable

- Single source of truth — fix once, every repo gets the fix
- Centralized supply-chain hygiene — third-party actions are SHA-pinned in one place
- Consistent reporting — same job names, same SARIF categories, same artifact layout

## Available workflows

| Workflow | Purpose | Triggers it pairs with |
|---|---|---|
| `reusable-node-ci.yml` | Lint / typecheck / test / build for Node/TS repos | `push`, `pull_request` |
| `reusable-codeql.yml` | CodeQL static analysis | `push` to default, `pull_request`, weekly cron |
| `reusable-dependency-review.yml` | Block PRs adding vulnerable or non-permissive deps | `pull_request` only |
| `reusable-secret-scan.yml` | TruffleHog committed-secret detection | `push`, `pull_request`, weekly cron |
| `reusable-scorecard.yml` | OpenSSF Scorecard supply-chain hygiene | weekly cron, `branch_protection_rule` |
| `reusable-trivy.yml` | Trivy filesystem vulnerability scan | `push`, weekly cron |
| `reusable-hf-candidate-plan.yml` | Build a provider-free exact base-to-head Dockerfile payload plan and revalidate the live PR pair | base-controlled `pull_request_target` |
| `reusable-hf-module-drift-check.yml` | Detect drift between a repo's source-of-truth and its live Hugging Face Space | caller-chosen |

### Repository-native provenance compatibility

`.github/workflows/solo-builder-provenance.yml` provides exact-head provenance because
ruleset `19755620` requires the eight FORGE-9 gates and `deploy/staging`; commit-trailer enforcement is retired for the solo-builder model.
It does not require a developer signature or trailer. Protected
`pull_request_target` logic validates the live PR/base/head tuple without
checking out or executing proposed content; merge-group logic revalidates the
live queue refs with read-only permission. All real build and security checks
remain independent requirements.

Until the ruleset can require this specific workflow (or a distinct App-owned
status), any context emitted by GitHub Actions has the provider limitation that
the context name alone does not identify a unique workflow. Proposed changes to
`.github/workflows/**` therefore fail the protected provenance check and need an
explicitly reviewed owner migration.

## Calling a reusable workflow

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  ci:
    uses: szl-holdings/.github/.github/workflows/reusable-node-ci.yml@main
    with:
      node-version: '20'
      package-manager: 'pnpm'
      pnpm-version: '10'

  codeql:
    uses: szl-holdings/.github/.github/workflows/reusable-codeql.yml@main
    with:
      languages: '["javascript-typescript"]'

  secrets:
    uses: szl-holdings/.github/.github/workflows/reusable-secret-scan.yml@main
```

For maximum supply-chain hygiene, replace `@main` with a 40-character SHA from
this repository. Organization refs are exempt from the automated pin check, but
immutable pins remain preferred for non-experimental consumers.

## Nexus explicit release approval

Source PR admission is not permission to publish to `SZLHOLDINGS/nexus`.
`publish-nexus-space.yml` accepts only an owner `workflow_dispatch` on this
repository's protected `main`, with required `source_sha`: exactly 40 lowercase
hexadecimal characters naming the current Nexus `main` tip. There is no cron,
push publisher, floating revision, or rollback override. Ordinary `tests.yml`
PR/main checks validate the release contract even when the publisher is disabled.

The read-only validation job checks the exact requested source and Docker source
binding before the dependent publish job can enter the existing fixed
`production` environment. Its summary and pending publish job name display the
requested revision. The release owner must review that exact commit and approve
the environment deployment; this is separate from reviewing or merging a source
PR. Reuse the existing environment protections, including its owner-review and
wait timer. This change neither configures those protections nor requires a
second human. It does not enable an administratively disabled workflow.

After approval, the publisher fetches the requested immutable SHA again, never a
replacement revision. It aborts if Nexus `main` has moved, checks again before
loading provider credentials, and retains the deployer's immediate pre-mutation
default-tip guard. A stale request needs a new dispatch and new approval, not an
automatic upgrade. Release jobs share one fixed concurrency group with
`cancel-in-progress: false`; GitHub may replace pending queued jobs, but must not
cancel a publication already in progress. Read-only validation is not serialized.

Release-owner sequence: inspect the desired Nexus `main` commit and central
policy; separately authorize enabling the disabled publisher if appropriate;
dispatch on central `main` with that exact `source_sha`; inspect the validation
summary and requested SHA in the pending job; approve the fixed `production`
deployment; then inspect the manifest, running-byte/source readbacks and smoke
results. A successful workflow alone is not complete runtime qualification.

This is a gate on this one content publisher, not a universal deployment lock.
The target-recovery bootstrap has no content-publication/restart authority.
Other estate operators can independently restart an existing Hub revision;
their actions and any external integrations require their own authorization.

CP-eBOM declares this policy as `nexus-manual-production-release-v2`, with the
scoped `nexus-manual-production/v1` graph/critical-command contract. It rejects
automatic events, missing approval/dependency, stale or substituted source,
unguarded mutation stages, and a cancelling or dynamic publish lock, even when
source pins are recomputed. Other workflows retain their existing contracts.
Dropping the new intent/contract cannot restore automatic Nexus publication.
Exact source/dependency and observed-unknown pins remain required; this bounded
model is not a proof about arbitrary shell or provider authentication. Changing
the policy or analyzer is a trust-root transition: retain its
`REVIEW_REQUIRED` receipt and obtain the exact-head owner attestation and real
protected checks described in `docs/CONTROL_PLANE_EFFECTS.md`. No attestation,
independent review, or deployment authorization is implied by this proposal.

## HF Space module drift

Spaces built by Dockerfile `COPY` can silently diverge from GitHub source. Two
layers guard this:

- `.github/workflows/hf-module-drift-check.yml` runs the organization sweep over
  `.github/data/hf_space_registry.json`.
- Repositories may call `reusable-hf-module-drift-check.yml` for local fail-fast
  coverage.

Both honor `.github/hf-module-drift-allow.json`. They never overwrite either
side automatically because drift can originate in GitHub or Hugging Face.

Candidate admission is deliberately separate from live drift. A protected
base-controlled workflow may call `reusable-hf-candidate-plan.yml` with the
exact pull-request base and head SHAs. The reusable workflow executes only this
repository's protected verifier revision, treats candidate Git objects as
data, revalidates the live GitHub PR tuple immediately before planning and after
artifact upload, makes no Hugging Face or runtime request, and emits a
deterministic Dockerfile-managed payload plan. Live source, deployment, and
runtime identity remain distinct post-merge gates.

## Org code-security config drift (`code-security-drift.yml`)

`code-security-drift.yml` verifies that **SZL Holdings Managed Security**
(configuration `252588`) remains enforced on every non-archived repository and
remains the default for new repositories.

### Authentication migration

The workflow is designed for automatic, fail-closed migration:

1. It first attempts a short-lived `qillqaq-attestor` installation token with
   organization `Administration: read`.
2. GitHub has recorded that permission in the reviewed App manifest, but the
   installed App cannot use a newly added permission until an organization
   owner approves the installation update.
3. Until that approval is active, the workflow uses the existing governed
   `SZL_GITHUB_TOKEN` for this exact read-only organization endpoint. A bounded
   capability probe on July 26, 2026 returned HTTP 200 without recording the
   token value, prefix, length, hash, identity, headers, or response body.
4. Once the App token mints successfully, the workflow selects it automatically
   and stops using the fallback for that run.

The governed token is not treated as a neutral bypass. Missing, expired,
under-scoped, or API-failing credentials are terminal `NOT_VERIFIED` results.

### Result contract

| State | Result | CI status |
|---|---|---|
| App token works and all active repositories are enforced | verified | pass |
| App permission is pending, governed token works, and coverage is clean | verified with migration evidence | pass + warning |
| Repository detached, attached elsewhere, or default changed | drift | fail |
| Credential missing, expired, under-scoped, or endpoint fails | not verified | fail |

### Evidence and secret boundaries

Every run uploads `reports/code-security-drift.json` as a 90-day immutable
artifact. Evidence records only the selected credential name, authentication
mode, endpoint-completion result, source SHA, and workflow run. It explicitly
records `value_recorded: false`.

The workflow never prints, hashes, persists, copies, or returns a credential
value. Generated reports are not committed or pushed directly to protected
`main`.

Configured references:

- variable: `QILLQAQ_CLIENT_ID`
- secret: `QILLQAQ_PRIVATE_KEY`
- migration credential: `SZL_GITHUB_TOKEN`

Approving the qillqaq installation permission remains the final cutover step.
After a protected-main run proves `authentication.mode=github_app`, the legacy
migration credential can be removed from this workflow and later rotated or
deleted only after all other consumers are independently inventoried.

## Dependabot

A default `.github/dependabot.yml` lives in this repo. Every repository without
its own file inherits weekly GitHub Actions updates from here.

## Issue and pull-request templates

Default issue forms and the pull-request template in `.github/` apply to every
repository that does not override them locally.

## CODEOWNERS

`@stephenlutar2-hash` is the default code owner. Per-repository CODEOWNERS files
take precedence.
