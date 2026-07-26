# FORGE-9 post-activation pilot

This inert record is the governed change used by pull request #319 to test the
fully activated solo-operator path. It does not assert its own success.

Acceptance requires immutable live GitHub evidence that:

- all eight FORGE-9 gates and `deploy/staging` pass on the PR head;
- `qillqaq-attestor` signs a BAP, approves the exact PR head, and publishes the
  App-pinned `attestation/qillqaq` status;
- the attestor's repository-scoped workflow token requests the protected queue
  without a manual enqueue;
- the same gates, staging status, and App-pinned attestation pass again on the
  synthetic merge-group commit; and
- the final rule-suite evaluation passes with no bypass actor or protection
  override.

The pull request timeline, Actions runs, signed BAP artifacts, commit status,
merge-queue events, and rule-suite record are the source of truth.
