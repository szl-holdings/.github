# Known limitations

The following blockers are explicit and must not be described as complete:

- `qillqaq-attestor` is not yet registered or installed.
- No private key or App ID has been placed in the `production` environment.
- GitHub App approvals have not been proven to satisfy the estate's required
  review rule.
- The estate has one human organization member, so a human cannot independently
  approve that same member's pull requests.
- Requiring the founder to approve access to the `production` environment would
  make each attestation manual. Removing that environment review is a separate
  founder security decision.
- The eight gate commands and `staging` deployment must be mapped and proven per
  repository before any FORGE-9 ruleset is activated.
- Three archived repositories retain historical ruleset state that cannot be
  edited while archived. They have no active release path.

Until these items are resolved, the pack is bootstrap material, not evidence of
an operating two-principal merge protocol.
