# Organization CodeQL Baseline v2

This control converges GitHub native code scanning across the active public `szl-holdings` repository estate without replacing existing analysis rails.

## Admission model

A repository is eligible only when it is public, active, non-archived, non-disabled, non-fork, has a default branch, and contains at least one language supported by GitHub CodeQL.

For each eligible repository, the controller follows this order:

1. Read the repository language inventory.
2. Read GitHub CodeQL default-setup state.
3. Preserve a complete existing default setup.
4. When default setup is absent or incomplete, check for an existing code-scanning analysis.
5. Preserve any existing CodeQL advanced setup or third-party SARIF analysis.
6. Configure native default setup only when no scanning rail exists.
7. Poll GitHub until provider readback reports `configured` with every detected CodeQL language.
8. Record every terminal outcome in a secret-free JSON receipt and the organization security issue.

## Mutation boundary

The controller may call only GitHub's native `code-scanning/default-setup` configuration endpoint and may create or update its command issue. It does not modify repository source, branches, refs, rulesets, branch protection, visibility, archive state, secrets, provider resources, billing, models, datasets, or deployment infrastructure.

## Terminal outcomes

- `ALREADY_CONFIGURED`
- `PRESERVED_EXISTING_ANALYSIS`
- `CONFIGURED`
- `WOULD_CONFIGURE`
- `SKIPPED_NO_SUPPORTED_LANGUAGE`
- `BLOCKED`

An apply run returns nonzero when any eligible repository remains `BLOCKED`. Partial coverage is therefore visible and cannot be presented as complete.

## Evidence

The protected workflow emits `org-code-scanning-baseline-v2.json`, verifies that no token-shaped value was persisted, and uploads the receipt as a 90-day immutable workflow artifact. The command issue remains open whenever managed prerequisites or repository-specific blockers remain.
