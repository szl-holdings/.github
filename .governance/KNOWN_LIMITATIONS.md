# Known limitations

- The estate has one human organization member. The policy is explicitly
  solo-operated and does not claim independent human review.
- The App ID and private key are repository Actions secrets. The removed local
  private key cannot be recovered; rotation requires generating a new App key.
- The App review and merge-queue path must be proven on a post-bootstrap pilot
  before estate-wide activation is claimed.
- Gate mappings in this repository are specific to an organization-governance
  repository. Application repositories require their own real commands.
- GitHub merge queues cannot be enabled in a ruleset that targets wildcard
  refs. `forge9-main` queues the default branch; `forge9-release` protects
  `release/*` with the same gates, staging, and App approval but no queue.
- GitHub rejected `enqueuePullRequest` for the App installation token despite
  its live merge-queue grant. The App retains attestation and approval duties;
  the ephemeral repository token requests the protected queue after attestation.
- Three archived repositories retain historical ruleset state that cannot be
  edited while archived. They have no active release path.

The `.github` repository is the pilot. Estate-wide completion is claimed only
after each active repository has compatible gates and staging evidence.
