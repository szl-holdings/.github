# Solo-operator governance

SZL Holdings currently has one human organization member. The merge policy
therefore does not claim independent human review.

## Enforced control model

- Pull requests are mandatory and direct pushes remain blocked.
- Commits must be signed, linear, DCO-signed, and conventionally named.
- Eight repository-specific, fail-closed checks must pass for the exact head.
- A successful `staging` deployment is required.
- `qillqaq-attestor[bot]` verifies the gates, creates a signed merge BAP, and
  records an approval for the exact head.
- The ephemeral repository token requests the protected merge queue only after
  the App attestation succeeds; it cannot approve or bypass the ruleset.
- The App has read-only Contents access and cannot alter repository code.
- Ruleset bypass actors remain empty.

The App is a distinct machine identity, not an independent human reviewer.
The ruleset requires one App approval for the exact latest push. Its protection
comes from that mechanically constrained approval together with the mandatory
checks, deployment, signed evidence, and queue.

The merge queue applies to the default branch. GitHub does not support wildcard
refs in a merge-queue ruleset, so `release/*` uses a separate ruleset with the
same gates, signatures, staging, and exact-head App approval but no queue. The
same attestor submits release pull requests to their protected auto-merge path.

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
bypass actor, force merge, or administrator override. The repository-specific
rulesets require the distinct App approval for subsequent changes.
