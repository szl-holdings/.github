# FORGE-9 Section 18 bootstrap

This directory is the reviewed bootstrap pack for the FORGE-9 merge protocol.
It is intentionally not activated by copying the ruleset first. Required checks
that do not yet exist would lock a repository without producing evidence.

## Non-negotiable invariants

- Every active ruleset has an empty `bypass_actors` array.
- One independent approval is required; stale approvals are dismissed and the
  last push must be approved.
- The ordinary `GITHUB_TOKEN` cannot approve pull request reviews.
- The attestor uses a GitHub App installation token minted from a private key.
  GitHub Actions OIDC is used only for keyless Sigstore signing.
- No workflow lowers approval counts, adds an administrator bypass, disables a
  ruleset, force-merges, or treats a placeholder as evidence.
- A governance self-edit is refused by the attestor and must use the documented
  founder breakglass process.

## Corrections to the proposed protocol

GitHub Apps cannot be organization team members or CODEOWNERS. Consequently the
ruleset keeps code-owner review disabled and uses the App's independently
authenticated review as the required approval. This must be proven in a pilot
repository before the estate ruleset is activated.

The App needs `Administration: read` to inspect repository Actions policy and
rulesets. It keeps `Contents: read` and uses the dedicated
`Merge queues: write` permission to enqueue through GraphQL; it never calls the
direct merge endpoint. `id-token: write` is a workflow permission, not a GitHub
App permission.

The production environment is referenced explicitly by the attestor because
environment secrets are unavailable otherwise. A required human environment
reviewer makes every attestation manual; that tradeoff remains founder-gated and
is recorded in `KNOWN_LIMITATIONS.md`.

## Activation order

1. Merge this bootstrap through the current protected pull-request path.
2. Register and install `qillqaq-attestor` with the permissions in
   `github-app-manifest.json`.
3. Create the `production` environment, store `QILLQAQ_APP_ID` and
   `QILLQAQ_PRIVATE_KEY`, and choose the environment-review policy explicitly.
4. Copy the templates into `.github/workflows/` in one pilot repository.
5. Populate every command in `gates.json`; an absent command fails closed.
6. Prove AT-18 through AT-24, including an App approval that GitHub counts.
7. Create the `staging` environment and prove its deployment receipt.
8. Apply `ruleset-main.json` to the pilot, then verify the live ruleset.
9. Roll out only to active repositories whose eight gates and staging
   deployment are already green.

Never apply the ruleset before steps 2 through 7 are complete.
