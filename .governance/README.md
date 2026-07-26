# FORGE-9 Section 18 bootstrap

This directory is the reviewed bootstrap pack for the FORGE-9 merge protocol.
It is intentionally not activated by copying the ruleset first. Required checks
that do not yet exist would lock a repository without producing evidence.

## Solo-operator invariants

- Every active ruleset has an empty `bypass_actors` array.
- The estate does not claim independent human review while it has one human
  member. GitHub's human approval count is zero by design.
- Eight fail-closed checks, App-pinned staging, signed commits, an App-owned
  required attestation status, and merge queue execution replace the impossible
  second-human requirement.
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
not a human review, and GitHub does not count it toward required approvals from
people with write permission. The App therefore publishes
`attestation/qillqaq` only after a signed BAP verifies the successful gate
checks. On pull-request heads, the App also records and verifies an exact-head
review before publishing the status. On merge-group heads, it independently
attests the synthesized queue commit so the queue cannot reuse stale PR-head
evidence. Both rulesets require that status and pin it to App ID `4395545`.

GitHub rejected queue entry while a separate `required_deployments` rule was
active even though the exact-head `staging` deployment was successful. The
enforceable queue-compatible control is the required `deploy/staging` check,
pinned to GitHub Actions App ID `15368`. The staging workflow still creates the
deployment and runs for both pull requests and merge groups, so the queue must
reverify staging against the synthesized merge-group commit.

The App needs `Administration: read` to inspect repository Actions policy and
rulesets. It keeps `Contents: read` and does not receive merge or queue
authority. GitHub rejected the GraphQL enqueue mutation for the installation
token even with the merge-queue permission. After the App signs the BAP and
records its approval, the repository-scoped ephemeral `GITHUB_TOKEN` uses
GitHub's supported `gh pr merge` path to request the protected queue. That token
cannot approve reviews and cannot bypass the ruleset. `id-token: write` is a
workflow permission, not a GitHub App permission.

The attestor uses a repository Actions variable for the public App client ID
and a repository Actions secret for the private key. It does not enter the
`production` environment. Production deployment approval therefore remains a
separate, identity-bound release control.

## Activation order

1. Merge this bootstrap using the documented one-time solo bootstrap record.
2. Create `staging` and keep the manual reviewer on `production`.
3. Apply `ruleset-main.json` to the default branch. GitHub does not allow a
   merge-queue ruleset to contain wildcard refs.
4. Apply `ruleset-release.json` separately to `release/*`; it retains the gates,
   signatures, App-pinned staging, and App attestation status without a queue.
5. Verify the active gate, staging, attestor, BAP, and queue on a pilot PR.
6. Roll out only to active repositories with mapped gates and staging evidence.

Never apply either ruleset before its checks and deployment exist.

## Live bootstrap state

As of 2026-07-26, `qillqaq-attestor` is registered as App ID `4395545`
and installed as installation `149072489` on all current and future
`szl-holdings` repositories. The `.github` repository stores the App client ID
as an Actions variable and the private key as an Actions secret. This branch
activates the attestor, eight-gate workflow, and staging deployment workflow.
