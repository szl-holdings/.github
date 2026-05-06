# SZL Holdings — Reusable Workflows

This repo hosts the reusable GitHub Actions workflows shared across the
organization. Every public repo in `szl-holdings` should consume these
instead of redefining the same logic locally.

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

## Calling a reusable workflow

```yaml
# .github/workflows/ci.yml in any consumer repo
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

For maximum supply-chain hygiene, replace `@main` with a 40-char SHA from
this repo. The org-wide pin-check exempts `szl-holdings/*` refs by design,
but pinning is still the recommendation for non-experimental repos.

## Dependabot

A default `.github/dependabot.yml` lives in this repo. Every repo without
its own `dependabot.yml` automatically inherits weekly GitHub Actions
updates from here.

## Issue & PR templates

Default issue forms and the PR template in `.github/` apply to every repo
that doesn't override them locally.

## CODEOWNERS

`@stephenlutar2-hash` is the default code owner. Per-repo CODEOWNERS
files take precedence.
