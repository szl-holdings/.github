# Frontier receipt artifact admission

This is an incremental PR740 successor on the actual `271eb23` source. It is not
an overlay of the earlier observer-v2 proposal targeting `7ff9877`. The current
protected-authorization queue adapter, empty authorization file, public machine
issue owner, privacy projection and existing operator suites are preserved.

## Test dependency closure

Both existing operator workflows use a fresh job-local virtual environment,
Linux CPython 3.12.14, and `requirements/frontier-observer-tests.lock` with wheel
hashes, no source distributions, and `pip check`. Normal and optimized runs cover
all existing operator tests plus the artifact guard. Plugin autoload is disabled;
no organization credential is supplied to the validation job. Python installation
and pip bootstrap remain provided by the pinned setup action, not independently
hermetic. The complete native installation must pass before promotion.

The contract workflow also handles `merge_group: checks_requested`. This adds
source tests to the native queue event; it does not enqueue, sign, approve or merge
anything. Existing required contexts and repository rules remain unchanged.

## Artifact publication boundary

The former upload step used `always()` even after receipt verification failed.
The upload now requires `steps.verify_receipt.outcome == 'success'`, and reads
only a separately staged, exclusive-create copy of the exact validated bytes.
The original local report is never overwritten by the guard.

`frontier_receipt_check.py` first bounds and strictly decodes the JSON, rejects
unknown fields, duplicate keys, non-finite values and untyped counters, and checks
source identity, timestamps, public-only coverage, reconstructed URLs, allowed
states and summary consistency. It independently rechecks each represented
repository's current public metadata through the existing read transport using
the repository credential, not the organization credential. Failed or ambiguous
visibility withholds the entire artifact. No free-form title, body, review/check
name, supplied URL or error message is permitted by the projection schema.

Only after all checks does the guard create a new directory under RUNNER_TEMP,
write/fsync the exact bytes and mark the staged file read-only. A fixed diagnostic
is printed on failure. No raw receipt, provider exception, identifier or path is
reflected in failure logs. Neither source nor existing staged evidence is deleted
or overwritten. A partial staging failure preserves uncertainty and the failed
step prevents upload. A safe PARTIAL_FAILURE receipt may be retained as evidence;
that does not change the operator step's nonzero exit or declare the run healthy.

## Limits

This is source/schema/privacy admission for a public report, not an authenticated
whole-estate census, private-alert review, model evaluation, queue attestation or
production qualification. Repository visibility reads are bounded and non-atomic.
A trusted ephemeral hosted runner is assumed: file mode and fsync are not a
hostile-process sandbox, signature or power-loss guarantee. Timestamp/source
checks do not independently attest the producer run. The separate native queue
controller and canonical publisher keep their own admission requirements.

The older source-only ZIP remains historical. No predecessor operator file or
test is substituted for the current implementation, and no unreviewed queue grant
is added. Existing publisher/credential holds and BETTERWITHAGE recovery claims
are unrelated and are not modified by this source-quality repair.

Primary references: GitHub Actions secure-use and merge-queue documentation;
PyPI version-specific JSON metadata for the five selected wheel hashes; Python
`os.fsync` documentation. Published hashes are integrity pins, not a statement
that every future dependency vulnerability is ruled out.
