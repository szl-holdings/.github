# One-time Nexus target bootstrap

This protected source candidate temporarily authorizes one exact recovery of
the public Docker Space target `SZLHOLDINGS/nexus` after canonical Nexus source
admission. The bootstrap grant has `enabled: true`; the separate lifecycle
policy still keeps global `boundaries.create: false`, and the existing Nexus
content publisher remains unchanged and cannot create the target.

After successful provider creation and exact public/Docker/write-authority
readback, a separate protected successor must restore `enabled: false` before
any Nexus content publication is dispatched. An occupied, private, wrong-SDK,
ambiguous, or unauthorized target remains a terminal hold rather than a reason
to retry creation or broaden policy.

The recovery workflow is a separately dispatched source path. Its grant is
checked in a credential-free preflight before the Hub client is installed or
provider credentials enter a step environment. Pull-request validation uses
synthetic provider objects and temporary fixtures only.

## Source and grant checks

An execution must identify the central GitHub repository, a protected `main`
dispatch, the exact workflow path, and matching workflow and checkout commit
identities. Both preflight and execution enforce those checks. The workflow
also compares the actual Git checkout with the native event commit.

The helper reads bounded regular JSON files, rejects duplicate keys, nonfinite
values and numeric overflow, and requires the exact grant shape with a literal
boolean `true`. Integers and strings cannot authorize an effect. The admitted
candidate grant is `true` only for this bounded one-time recovery window. Tests
that verify the disabled boundary derive a synthetic `false` fixture, so the
negative contract remains executable while the temporary authorization is
live. The provider receipt, not the source boolean alone, determines whether
the follow-up disablement can proceed.

The helper binds `requirements/hf-publisher.lock` to SHA-256
`eec9ee849129e2034d2c7880f0f3e32857cbfd7ceecfcb5f2eb7cb541b4e4d15`.
The lock is declared `text eol=lf` in `.gitattributes`, so this digest binds
the committed LF bytes identically on Windows and Linux checkouts.
The workflow reruns that credential-free check immediately before installing
the lock with `--require-hashes --only-binary=:all:`. It checks the lock again
before provider execution. The effect analyzer does not recognize
`requirements/*.lock` as a dependency path; the digest constant in the
reviewed helper supplies this additional source binding without changing the
analyzer. These local checks assume the protected checkout remains cooperative;
they do not establish a sandbox against concurrent hostile filesystem changes.

## Canonical acceptance contract

**C-1 ? Exact one-time NEXUS target recovery.** The recovery is admissible only
when all of the following hold together:

1. canonical `szl-holdings/nexus` source has been protected-merged and its
   exact merge revision is independently readable;
2. the dispatch runs from protected `.github/main` with matching workflow,
   checkout, event and workflow-file commit identities;
3. the exact grant authorizes only public Docker Space
   `SZLHOLDINGS/nexus`, while global lifecycle creation remains denied;
4. at most one SDK creation invocation occurs, credential candidates are
   deduplicated, and any ambiguous creation result is terminal;
5. provider readback proves exact target name, public visibility, Docker SDK
   and caller write authority without uploading content or mutating another
   target; and
6. a separately reviewed protected successor restores `enabled: false` before
   the central content publisher is dispatched.

This criterion authorizes neither model training nor a broader Hub lifecycle
exception. A sanitized recovery receipt is required evidence; source admission
alone is not provider-state proof.

## Provider effect boundary

Credential candidates are deduplicated. Identity and write checks can move to
the next candidate after a definite authentication rejection. The first
`create_repo` invocation ends credential selection, including after rejection
or uncertainty. An ambiguous outcome never causes another creation invocation.

The request names only `SZLHOLDINGS/nexus`, selects Space/Docker/public, and
uses `exist_ok=False`. An occupied target is held. Existing private or other-SDK
targets are held. Successful readback requires the exact name, public
visibility, Docker SDK, and write authority. No rename, deletion, visibility
change, content upload, runtime change, or second target is implemented here.

A Hub 404 remains ambiguous between absence and an inaccessible target. This
source candidate does not establish authenticated absence, current target
visibility, creation, deployment, or runtime readiness. Error receipts omit
credentials and provider error bodies.

Before dispatch, qualify the exact locked SDK's internal request and retry
behavior, the current protected source/grant authority, and the current target
and caller identity. One SDK invocation is not a claim of one HTTP request: the
effect analyzer counts invocation sites and does not prove a network retry
bound. Native workflow identity alone also does not prove that a queued run or
rerun still matches current `main`; exact source readback is required again at
execution.

## Effect admission and checks

The two harden-runner actions use the same reviewed pin as current protected
workflows. Their monitoring writes are explicitly represented as two
StepSecurity telemetry sites. The declaration separately accounts for the
single recovery artifact, one SDK creation site, two checkouts, two toolchain
setups, and two local runner guard configurations. These are static site
budgets; the validation and recovery jobs are mutually exclusive.

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
provider data. An actual provider effect requires its own retained receipt and
the separately protected grant-disable successor required by C-1.
