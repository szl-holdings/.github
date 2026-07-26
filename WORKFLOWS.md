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
| `reusable-hf-module-drift-check.yml` | Detect drift between a repo's source-of-truth and its live Hugging Face Space (built by Dockerfile `COPY`) | caller-chosen (e.g. weekly cron, `workflow_dispatch`) |

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

For maximum supply-chain hygiene, replace `@main` with a 40-char SHA from this
repo. The org-wide pin-check exempts `szl-holdings/*` refs by design, but
pinning is still the recommendation for non-experimental repos.

## HF Space module drift

Repos whose Hugging Face Space is built by Dockerfile `COPY` from their GitHub
source can silently diverge from the live Space (the Space's files can be
edited directly on HF, and hf-sync only mirrors README + the front-door
HTML/JS). Two layers guard this:

- **Org-wide sweep** — `.github/workflows/hf-module-drift-check.yml` runs weekly
  over `.github/data/hf_space_registry.json`, comparing every registered
  GitHub<->HF pair via the git-tree API. Adding a repo to the registry is the
  only step needed to cover it — no per-repo copy-paste.
- **Per-repo fail-fast** — a repo calls
  `reusable-hf-module-drift-check.yml` to gate its own PRs/pushes/cron.

Both honor the repo's own `.github/hf-module-drift-allow.json` ratchet (known
drift warns; new drift fails) and never auto-overwrite. A human chooses the
source of truth because drift can run in either direction.

## Org code-security config drift (`code-security-drift.yml`)

`code-security-drift.yml` verifies that organization code-security
configuration **SZL Holdings Managed Security** (`252588`) remains attached and
**enforced** on every non-archived repository and remains the default for new
repositories.

### Governed credential order

The workflow uses a bounded two-candidate credential chain:

1. **Preferred:** a short-lived qillqaq GitHub App installation token requesting
   organization `Administration: read`.
2. **Fallback:** the existing governed `SZL_GITHUB_TOKEN` repository secret.

The fallback is temporary compatibility, not a silent downgrade. It remains in
use only until the organization approves qillqaq's tracked
`organization_administration: read` permission. Every configured candidate must
return HTTP `200` from the exact organization code-security configurations
endpoint before the checker receives it. The selector records only the
credential class and authorization outcome; it never records a value, length,
prefix, hash, identity, header, scope response, or response body.

The App remains preferred because its token is short-lived and automatically
revoked by `actions/create-github-app-token`. The fallback is already governed,
is currently authorized for the exact read endpoint, and is never used when the
App candidate succeeds.

### Fail-closed result contract

| State | Result | CI status |
|---|---|---|
| App authorized and every active repository enforced under `252588` | verified using `qillqaq_app` | pass |
| App unavailable but governed fallback authorized and estate clean | verified using `szl_github_token` | pass |
| Repository detached, attached elsewhere, or default changed | drift | fail |
| No configured candidate returns HTTP `200` from the exact endpoint | not verified | fail |
| Checker or persistent network/API failure | not verified | fail |

There is no neutral production skip. Missing, expired, under-scoped, or
unreachable credentials cannot be rendered as clean or skipped estate results.

### Evidence and secret boundaries

Every run uploads `reports/code-security-drift.json` as a 90-day immutable
workflow artifact. Clean and drift runs contain the full repository coverage
report plus the selected credential class. If selection or the API check aborts,
the workflow writes a bounded `NOT_VERIFIED` receipt containing no secret
material.

Generated reports are not committed or pushed directly to protected `main`.
The previous committed snapshot was removed because it had become stale and
under-counted the live organization. Pull-request CI locks credential order,
endpoint verification, fail-closed behavior, artifact publication, and the
no-direct-push contract without receiving credentials.

Authentication inputs are configuration references, never values in source:

- variable: `QILLQAQ_CLIENT_ID`;
- secret: `QILLQAQ_PRIVATE_KEY`;
- fallback secret: `SZL_GITHUB_TOKEN`.

Rotate the App private key or governed fallback in GitHub settings without
printing either value. Do not delete `SZL_GITHUB_TOKEN` until qillqaq's added
organization permission is approved and a protected-main run proves the App
path selected `qillqaq_app`.

## Dependabot

A default `.github/dependabot.yml` lives in this repo. Every repo without its
own `dependabot.yml` automatically inherits weekly GitHub Actions updates from
here.

## Issue & PR templates

Default issue forms and the PR template in `.github/` apply to every repo that
doesn't override them locally.

## CODEOWNERS

`@stephenlutar2-hash` is the default code owner. Per-repo CODEOWNERS files take
precedence.
