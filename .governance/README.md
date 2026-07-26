# FORGE-9 governance controls

This directory defines the review and merge controls for the organization
governance repository. The artifacts are fail-closed and intentionally expose
the current one-human-owner blocker.

## PROVED invariants

- Every ruleset has an explicit empty `bypass_actors` array.
- Default and `release/*` branches require one approval of the latest push.
- Stale approvals are dismissed and review threads must be resolved.
- Eight repository-specific checks, signed commits, staging evidence, and
  conventional commits are mandatory.
- Machine attestations are evidence only. They cannot approve or merge a pull
  request and do not replace an independent human reviewer.
- No workflow lowers approval counts, adds an administrator bypass, force
  merges, auto-merges, or treats a placeholder as evidence.

GitHub does not support merge queues on wildcard refs, so `forge9-main` targets
only the default branch and `forge9-release` protects `release/*` without a
queue. Both require the same checks, signatures, staging deployment, and review
policy.

**MEASURED:** The organization currently has one human member. See
`independent-review-policy.md` for the binding two-owner rule and blocked state.

## Activation order

1. **PLANNED:** Add a second human organization owner with 2FA.
2. Independently review and merge this policy through the protected path.
3. Verify the exact live rulesets against `ruleset-main.json` and
   `ruleset-release.json`.
4. Roll out only to active repositories with mapped, real gate commands and
   staging evidence.
