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
