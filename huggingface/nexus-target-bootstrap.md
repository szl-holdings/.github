# Disabled Nexus target bootstrap

This source proposal preserves the exact public Docker Space target
`SZLHOLDINGS/nexus`. It does not authorize creation: the checked-in bootstrap
grant has `enabled: false`, and the separate lifecycle policy keeps
`boundaries.create: false`. The existing Nexus content publisher is unchanged.

The recovery workflow is a separately dispatched source path. Its checked-in
grant fails the credential-free preflight before the Hub client is installed
or provider credentials enter a step environment. Pull-request validation uses
synthetic provider objects and temporary fixtures only.

## Source and grant checks

An execution must identify the central GitHub repository, a protected `main`
dispatch, the exact workflow path, and matching workflow and checkout commit
identities. Both preflight and execution enforce those checks. The workflow
also compares the actual Git checkout with the native event commit.

The helper reads bounded regular JSON files, rejects duplicate keys, nonfinite
values and numeric overflow, and requires the exact future grant shape with a
literal boolean `true`. Integers and strings cannot authorize an effect. The
committed grant remains false; enabled values appear only in local test
fixtures.

The helper binds `requirements/hf-publisher.lock` to SHA-256
`eec9ee849129e2034d2c7880f0f3e32857cbfd7ceecfcb5f2eb7cb541b4e4d15`.
The workflow reruns that credential-free check immediately before installing
the lock with `--require-hashes --only-binary=:all:`. It checks the lock again
before provider execution. The effect analyzer does not recognize
`requirements/*.lock` as a dependency path; the digest constant in the
reviewed helper supplies this additional source binding without changing the
analyzer. These local checks assume the protected checkout remains cooperative;
they do not establish a sandbox against concurrent hostile filesystem changes.

## Future provider effect boundary

If a later protected source revision admits an enabled grant, credential
candidates are deduplicated. Identity and write checks can move to the next
candidate after a definite authentication rejection. The first `create_repo`
invocation ends credential selection, including after rejection or uncertainty.
An ambiguous outcome never causes another creation invocation.

The request names only `SZLHOLDINGS/nexus`, selects Space/Docker/public, and
uses `exist_ok=False`. An occupied target is held. Existing private or other-SDK
targets are held. Successful readback requires the exact name, public
visibility, Docker SDK, and write authority. No rename, deletion, visibility
change, content upload, runtime change, or second target is implemented here.

A Hub 404 remains ambiguous between absence and an inaccessible target. This
proposal does not establish authenticated absence, current target visibility,
creation, deployment, or runtime readiness. Error receipts omit credentials
and provider error bodies.

Before enabling any future grant, qualify the exact locked SDK's internal
request and retry behavior, the current protected source/grant authority, and
the current target and caller identity. One SDK invocation is not a claim of
one HTTP request: the effect analyzer counts invocation sites and does not
prove a network retry bound. Native workflow identity alone also does not prove
that a queued run or rerun still matches current `main`. These questions remain
part of the future effect-enablement review.

## Effect admission and checks

The two harden-runner actions use the same reviewed pin as current protected
workflows. Their monitoring writes are explicitly represented as two
StepSecurity telemetry sites. The declaration separately accounts for the
single recovery artifact, one latent SDK creation site, two checkouts, two
toolchain setups, and two local runner guard configurations. These are static
site budgets; the validation and recovery jobs are mutually exclusive.

The source declaration changes a policy trust root. Matching its exact bytes
does not authorize a provider effect. The whole-repository gate must retain
`TRUST_ROOT_CHANGED_REVIEW_REQUIRED` until protected source review is complete.

Focused local commands:

```sh
python -I -B .github/scripts/test_recover_nexus_target.py
python -I -B -O .github/scripts/test_recover_nexus_target.py
actionlint .github/workflows/recover-nexus-target.yml
```

The tests exercise source admission boundaries with synthetic provider replies.
They do not contact Hugging Face, create a Space, or qualify the live SDK's
internal transport behavior. Reverting an eventual source merge does not delete
provider data. A later actual provider effect would require its own retained
receipt and recovery decision.
