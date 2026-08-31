# Solo-operator governance

SZL Holdings currently has one human organization member. The merge policy
therefore does not claim independent human review.

## Enforced control model

- Pull requests are mandatory and direct pushes remain blocked.
- Pull-request heads must have exact protected provenance, linear history, and
  conventional names. Developer commit signatures and trailers are not
  required.
- Eight repository-specific, fail-closed checks must pass for the exact head.
- The `deploy/staging` check is required and pinned to GitHub Actions App ID
  `15368`; the workflow also emits the staging deployment record.
- `qillqaq-attestor[bot]` verifies the gates, creates a signed merge BAP, and
  records an approval for the exact head.
- The App then publishes `attestation/qillqaq`. The non-queued release ruleset
  requires it and pins it to App ID `4395545`; the default-branch queue records
  it as evidence. The App repeats gate verification, BAP signing, and status
  publication for the synthesized merge-group commit.
- A trusted-default-branch `workflow_run` controller requests the protected
  main queue only after exact gate-generation, body, base, App-status, and App-
  review evidence matches. Its governed token is never exposed to PR code.
- The ephemeral repository token requests only the non-queued `release/*`
  auto-merge path after App attestation; it cannot approve or bypass the
  ruleset.
- The App has read-only Contents access and cannot alter repository code.
- Ruleset bypass actors remain empty.

The App is a distinct machine identity, not an independent human reviewer.
GitHub only counts approvals from people with write permission, so the human
approval count is zero. Enforcement comes from the App-owned required status on
non-queued release branches. On the queued default branch, enforcement comes
from mandatory exact-head and merge-group checks, staging, an empty bypass
list, and the queue. The App-owned review, signed BAP, status, and
automatic queue request remain independently attributable evidence.

The merge queue applies to the default branch. GitHub does not support wildcard
refs in a merge-queue ruleset, so `release/*` uses a separate ruleset with the
same gates, App-pinned staging, and required App-owned attestation status but no
queue. The same attestor submits release pull requests to their protected
auto-merge path. Existing server-side signature settings remain configuration
drift to remove when repository ruleset administration becomes available; they
are not the developer contribution policy.

## Governance changes

A pull request that edits the gate, attestor, merge-queue controller, staging
workflow, or `.governance/` must include exactly one of these authorization
markers:

```text
Solo-Operator-Authorization: confirmed
Solo-Operator-Authorization: CONFIRMED
```

The authorization value is case-sensitive. Mixed-case values, prefixes,
suffixes, and additional text are invalid. The pull request must also include:

```text
Risk: D - <reason>
```

The attestor refuses such a change without both markers. The workflow executing
that decision is the version already present on the default branch, so a pull
request cannot weaken its own evaluator before approval.

## Bootstrap record

PR #316 is the one-time protected bootstrap that installed the evaluator itself.
It merged only after all pre-existing hosted checks were green and without a
bypass actor, force merge, or administrator override. The release ruleset
requires the distinct App attestation status for subsequent release changes.
The default branch records it without creating a merge-queue dispatch cycle.
