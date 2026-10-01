# Source-bound Space deployment transactions

The Dockerfile deployer can publish one frozen plan with Hugging Face provider
compare-and-set. This mode is opt-in so existing reusable workflow callers keep
their current behavior while each canonical owner adopts the transaction.

First derive the plan with `--dry-run --manifest-out`. Its `manifest_sha256`
binds the complete derivation, including the source revision, target paths,
source mappings, exact byte hashes, sizes, Dockerfile, build-context policy,
and declared smoke paths. Only generation time and result fields are excluded.
Inspect this plan before publication. Derivation may materialize an explicitly
requested new source-revision file locally; dry-run performs no provider writes.

For publication, use the exact source commit as both `--ref` and `--source-sha`,
enable `--require-default-branch-tip`, and provide all four transaction options:

- `--expected-hf-parent`: the observed 40-character Hub commit.
- `--operation-id`: a fresh 64-character lowercase hexadecimal operation ID.
- `--expected-manifest-sha256`: the inspected dry-run plan identity.
- `--transaction-journal`: a new local evidence path outside the payload tree.

The journal must have an existing parent directory. It cannot overwrite an
earlier intent or be published as part of the image payload. The controller
flushes and fsyncs `OUTCOME_UNCERTAIN` intent before its single `create_commit`
call. The provider receives `parent_commit`; a concurrent publication therefore
cannot silently change the expected parent. The controller does not retry a
commit. A valid provider acknowledgement is recorded as `COMMIT_ACKNOWLEDGED`,
which remains separate from running-image and functional-route attestation.

If an upload times out, a worker dies, or the acknowledgement cannot be parsed,
retain the original journal and run `--reconcile-transaction <journal>`.
This mode performs reads only. It checks a bounded recent commit history for
the unique operation marker, matching manifest/parent markers, adjacent expected
parent, and every immutable target byte. It also checks declared deletions.
It reports `CONFIRMED`, `SUPERSEDED`, `HOLD_BYTE_MISMATCH`,
`HOLD_PRUNE_MISMATCH`, or `OUTCOME_UNCERTAIN`. Only `CONFIRMED` exits zero.

Reconciliation does not republish, change variables, restart a Space, delete a
journal, or manufacture a receipt when history is unavailable. An unobserved
operation is uncertain; absence from the bounded history does not prove that
no upload occurred. A superseded matching operation cannot be bound as the
current application source.

The hashes and provider metadata bind this operation's bytes. They are not an
independent signature, publisher-identity witness, scientific validation,
authorization grant, or runtime proof. Canonical callers must retain this
journal with their run evidence, verify protected source and exact hosted
checks, and separately attest the running commit and functional routes.
Existing callers without the four options do not gain transaction guarantees.
