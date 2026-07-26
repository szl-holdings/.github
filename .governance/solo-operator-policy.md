# Solo-operator governance

SZL Holdings currently has one human organization member. The merge policy
therefore does not claim independent human review.

## Enforced control model

- Pull requests are mandatory and direct pushes remain blocked.
- Commits must be signed, linear, DCO-signed, and conventionally named.
- Eight repository-specific, fail-closed checks must pass for the exact head.
- A successful `staging` deployment is required.
- `qillqaq-attestor[bot]` verifies the gates, creates a signed merge BAP, and
  enqueues the exact pull request through the merge queue.
- The App has read-only Contents access and cannot alter repository code.
- Ruleset bypass actors remain empty.

The App is a distinct machine identity, not an independent human reviewer.
The ruleset therefore requires zero human approvals; its protection comes from
the mandatory checks, deployment, signed evidence, and queue.

The merge queue and App enqueue path apply to the default branch. GitHub does
not support wildcard refs in a merge-queue ruleset, so `release/*` uses a
separate ruleset with the same gates, signatures, staging, and pull-request
requirements but no queue.

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

PR #312 is the one-time bootstrap that installs the evaluator itself. It may be
merged only after all pre-existing hosted checks are green and the organization
ruleset is changed transparently from one impossible human approval to the
solo-operator model. No bypass actor, force merge, or administrator override is
permitted. The final ruleset is applied immediately after the workflows land.
