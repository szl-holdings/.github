# Merge-group Actions delivery blocker

Status: `EXTERNAL_BLOCKER`

Owner: Stephen Lutar

Next review: 2026-07-27

## Observed evidence

- PR #317 proved that main ruleset version `44456196` could dispatch and pass
  the `FORGE-9 gates` and `FORGE-9 staging` workflows for a `merge_group`.
- PR #319 head `ec3a604efb074c6d834c621a57d489492056998e`
  is GitHub-verified and DCO-signed. All pull-request checks passed.
- Attestor run `30191721186` passed P1-P7, signed and uploaded the BAP, recorded
  an exact-head App approval, published `attestation/qillqaq`, and used the
  repository token to request the queue.
- The active main ruleset has zero bypass actors and requires exactly the eight
  gates plus `deploy/staging`. Its substantive state is identical to historical
  version `44456196`.
- New synthetic queue heads, including
  `24edfb6b93142dbfe99a1b071c79d36c06f4cafb` and
  `bed40b0271f3e9963f85cada0aa41afee1ebff7e`, were GitHub-signed but received
  zero check suites and zero statuses.
- Refreshing the queue ruleset and disabling then immediately re-enabling the
  two active workflows while the queue was empty did not restore event
  delivery.
- GitHub's public status API reported Actions, Pull Requests, APIs, and webhooks
  operational with no unresolved incident.
- PR #320 independently proved AT-22: it was automatically enqueued after App
  attestation, then marked `UNMERGEABLE` behind PR #319 because both PRs added
  the same path with different content. It was closed without merge.

## Impact

The queue remains fail-closed in `AWAITING_CHECKS`. There is no honest merge
path while GitHub does not emit the required `merge_group` event. No bypass
actor, administrator merge, required-check removal, or fabricated status is
permitted.

## Minimum legitimate action

GitHub must restore `merge_group` `checks_requested` delivery for the repository
or provide a supported recovery action that causes the two active workflows to
run on the synthetic queue SHA. After that, rerun PR #319 through the automatic
attestor request and verify the final rule-suite result before claiming pilot or
estate-wide completion.
