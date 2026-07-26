# Independent review policy

**MEASURED:** SZL Holdings currently has one human organization member. This is
an explicit governance blocker, not authorization to replace independent review
with an owner-controlled machine identity.

## Enforced control model

- **PROVED:** Pull requests are mandatory; direct pushes and force pushes remain
  blocked by the active rulesets.
- Commits must be signed, linear, DCO-signed, and conventionally named.
- Eight repository-specific, fail-closed checks must pass for the exact head.
- A successful `staging` deployment is required.
- **PROVED:** The latest push requires one approving review, stale reviews are
  dismissed, and review threads must be resolved.
- Ruleset bypass actors remain empty.
- No workflow may submit an approving review or request an automated merge.

Machine attestations, signed receipts, and CI checks are useful evidence. They
do not count as independent human review and do not satisfy the two-owner rule.

## Blocked state

**PLANNED:** Add a second human owner with 2FA. Until that owner independently
reviews a pull request, governance changes remain open and unmerged. The blocked
state is intentional: availability and review independence take precedence over
merge velocity.

## Governance changes

Any change to `.github/workflows/`, `.github/scripts/`, or `.governance/` is
Risk D. It must preserve the one-review latest-push rule and receive approval
from a human who is neither the pull-request author nor the last pusher.
