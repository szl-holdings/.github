# Solo-operator governance

SZL Holdings currently has one human organization member. The merge policy
therefore does not claim independent human review.

## Enforced control model

- Pull requests are mandatory and direct pushes remain blocked.
- Commits must be signed, linear, DCO-signed, and conventionally named.
- Eight repository-specific, fail-closed checks must pass for the exact head.
- The `deploy/staging` check is required and pinned to GitHub Actions App ID
  `15368`; the workflow also emits the staging deployment record.
- `qillqaq-attestor[bot]` verifies the gates, creates a signed merge BAP, and
  records an approval for the exact head.
- The App then publishes `attestation/qillqaq`. The non-queued release ruleset
  requires it and pins it to App ID `4395545`; the default-branch queue records
  it as evidence. The App repeats gate verification, BAP signing, and status
  publication for the synthesized merge-group commit.
- The ephemeral repository token requests the protected merge queue only after
  the App attestation succeeds; it cannot approve or bypass the ruleset.
- The App has read-only Contents access and cannot alter repository code.
- Ruleset bypass actors remain empty.

The App is a distinct machine identity, not an independent human reviewer.
GitHub only counts approvals from people with write permission, so the human
approval count is zero. Enforcement comes from the App-owned required status on
non-queued release branches. On the queued default branch, enforcement comes
from mandatory exact-head and merge-group checks, staging, signatures, an empty
bypass list, and the queue. The App-owned review, signed BAP, status, and
automatic queue request remain independently attributable evidence.

The merge queue applies to the default branch. GitHub does not support wildcard
refs in a merge-queue ruleset, so `release/*` uses a separate ruleset with the
same gates, signatures, App-pinned staging, and required App-owned attestation
status but no queue. The same attestor submits release pull requests to their
protected auto-merge path.

## Governance changes

A pull request that edits the gate workflow, attestor workflow, or
`.governance/` must include both:

```text
Solo-Operator-Authorization: confirmed
Risk: D - <reason>
```

The attestor refuses such a change without both markers. The workflow executing
that decision is the version already present on the default branch, so a pull
request cannot weaken its own evaluator before approval.

## Bootstrap record

PR #316 is the signed one-time bootstrap that installed the evaluator itself.
It merged only after all pre-existing hosted checks were green and without a
bypass actor, force merge, or administrator override. The release ruleset
requires the distinct App attestation status for subsequent release changes.
The default branch records it without creating a merge-queue dispatch cycle.
