# Known limitations

- The estate has one human organization member. The policy is explicitly
  solo-operated and does not claim independent human review.
- The App ID and private key are environment secrets. The removed local private
  key cannot be recovered; rotation requires generating a new GitHub App key.
- The App review and merge-queue path must be proven on a post-bootstrap pilot
  before estate-wide activation is claimed.
- Gate mappings in this repository are specific to an organization-governance
  repository. Application repositories require their own real commands.
- Three archived repositories retain historical ruleset state that cannot be
  edited while archived. They have no active release path.

The `.github` repository is the pilot. Estate-wide completion is claimed only
after each active repository has compatible gates and staging evidence.
