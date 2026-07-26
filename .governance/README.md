# FORGE-9 Section 18 bootstrap

This directory is the reviewed bootstrap pack for the FORGE-9 merge protocol.
It is intentionally not activated by copying the ruleset first. Required checks
that do not yet exist would lock a repository without producing evidence.

## Solo-operator invariants

- Every active ruleset has an empty `bypass_actors` array.
- The estate does not claim independent human review while it has one human
  member. Human approval count is zero by design.
- Eight fail-closed checks, staging deployment, signed commits, App attestation,
  and merge queue execution replace the impossible human-review requirement.
- The ordinary `GITHUB_TOKEN` cannot approve pull request reviews.
- The attestor uses a GitHub App installation token minted from a private key.
  GitHub Actions OIDC is used only for keyless Sigstore signing.
- No workflow lowers approval counts, adds an administrator bypass, disables a
  ruleset, force-merges, or treats a placeholder as evidence.
- A governance self-edit requires the explicit founder authorization and Risk D
  markers defined in `solo-operator-policy.md`.

## Corrections to the proposed protocol

GitHub Apps cannot be organization team members or CODEOWNERS. Consequently the
ruleset keeps code-owner review disabled. The App review is machine attestation,
not a human approval, and is not counted toward a human-review requirement.

The App needs `Administration: read` to inspect repository Actions policy and
rulesets. It keeps `Contents: read` and uses the dedicated
`Merge queues: write` permission to enqueue through GraphQL; it never calls the
direct merge endpoint. `id-token: write` is a workflow permission, not a GitHub
App permission.

The production environment is referenced explicitly by the attestor because
environment secrets are unavailable otherwise. It has no deployment reviewer;
the minimally privileged App credential is usable only by the default-branch
attestor workflow.

## Activation order

1. Merge this bootstrap using the documented one-time solo bootstrap record.
2. Remove the manual reviewer from `production` and create `staging`.
3. Verify the active gate, staging, and attestor workflows on a pilot PR.
4. Apply `ruleset-main.json` to the pilot and verify its live state.
5. Roll out only to active repositories with mapped gates and staging evidence.

Never apply the ruleset before steps 2 through 7 are complete.

## Live bootstrap state

As of 2026-07-25, `qillqaq-attestor` is registered as App ID `4395545`
and installed as installation `149057850` on all current and future
`szl-holdings` repositories. The `.github` repository's `production`
environment stores the App ID and private key. This branch activates the
attestor, eight-gate workflow, and staging deployment workflow.
