# Known limitations

- The estate has one human organization member. The policy is explicitly
  solo-operated and does not claim independent human review.
- GitHub records the App review but does not count it toward approval rules that
  require a person with write permission. The enforceable equivalent is the
  App-owned `attestation/qillqaq` required status, pinned to App ID `4395545`.
- The public App client ID is a repository Actions variable and the private key
  is a repository Actions secret. The removed local private key cannot be
  recovered; rotation requires generating a new App key.
- The App review and merge-queue path must be proven on a post-bootstrap pilot
  before estate-wide activation is claimed.
- Gate mappings in this repository are specific to an organization-governance
  repository. Application repositories require their own real commands.
- GitHub merge queues cannot be enabled in a ruleset that targets wildcard
  refs. `forge9-main` queues the default branch; `forge9-release` protects
  `release/*` with the same gates, staging, and App attestation but no queue.
- GitHub rejected `enqueuePullRequest` for the App installation token despite
  its live merge-queue grant. The App retains attestation and approval duties;
  the ephemeral repository token requests the protected queue after attestation.
- GitHub also rejected queue entry when `required_deployments` was active even
  with a successful exact-head `staging` deployment. Staging is therefore
  enforced by the `deploy/staging` required check pinned to GitHub Actions; the
  workflow still creates deployment evidence and reruns on `merge_group`.
- Required statuses also apply to the synthesized merge-group commit. The
  attestor therefore signs and publishes a second BAP for that SHA; App review
  and the queue request remain PR-head-only operations.
- Commit metadata rules evaluate the full squash message, including the PR
  body. The rulesets enforce the conventional first line and allow the
  remaining body so GitHub's queue-generated commit can pass.
- Three archived repositories retain historical ruleset state that cannot be
  edited while archived. They have no active release path.

The `.github` repository is the pilot. Estate-wide completion is claimed only
after each active repository has compatible gates and staging evidence.
