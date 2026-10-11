# Closed Nexus target bootstrap

The one-time recovery window for the exact public Docker Space
`SZLHOLDINGS/nexus` is closed in this protected successor. The bootstrap grant
is restored to `enabled: false`; the independent lifecycle policy continues to
keep global `boundaries.create: false`; and the central Nexus content publisher
remains manually disabled until its source-binding contract is repaired and
separately admitted.

## Immutable recovery evidence

Canonical Nexus source was protected-merged at
`szl-holdings/nexus@00edebc993282efd5b43b0144b3d3d27ab43e264` before provider
recovery. Protected `.github/main` then admitted the one-time grant at verified
merge `fede0b692612199f455fb049b9ad762339200f0f`.

Owner-dispatched workflow run `37837500766` executed from that exact protected
main revision and completed successfully on 2026-10-08. Its sanitized receipt:

- uses schema `szl.nexus-target-recovery/v1`;
- reports state `CREATED_PUBLIC_WRITE_CONFIRMED`;
- names only public Docker Space `SZLHOLDINGS/nexus`;
- records exactly one `create_readback` attempt with HTTP status 200;
- records no credential value (`token_recorded: false`); and
- has SHA-256
  `6e18a5892b7117f32b83b0bae690a548ba1236d8f71b3d0c66f24d858352f7d8`.

Independent anonymous provider readback returned exact ID
`SZLHOLDINGS/nexus`, `private: false`, SDK `docker`, provider revision
`7e83f67347ad507b1793ef719dc474d2a6f8d6fe`, and runtime stage
`NO_APP_FILE`. That runtime stage is expected for the deliberately empty target
and is not a publication or health claim. No Nexus application content was
uploaded by recovery.

The central `Publish Nexus Space` workflow, ID `349731106`, was changed from
`active` to `disabled_manually` with zero queued or running publisher runs
before grant admission. It remained disabled throughout recovery and remains
disabled in this successor. Therefore the grant is closed before any content
publisher dispatch, satisfying the final ordering boundary in C-1.

## Source and grant checks

The recovery workflow requires the central GitHub repository, protected
`main`, the exact workflow path, and matching workflow, event, checkout, and
commit identities. Its credential-free preflight runs before the Hub client is
installed or any provider credential enters a step environment.

The helper reads bounded regular JSON files, rejects duplicate keys, nonfinite
values and numeric overflow, and requires the exact authorization shape with a
literal boolean `true` before provider access. This successor restores the
committed value to the literal boolean `false`; integers, strings, and all other
values remain non-authorizing. The disabled-boundary regression constructs its
own false fixture, so the negative contract stays executable regardless of a
future candidate grant state.

The helper binds `requirements/hf-publisher.lock` to SHA-256
`eec9ee849129e2034d2c7880f0f3e32857cbfd7ceecfcb5f2eb7cb541b4e4d15`.
The lock is declared `text eol=lf` in `.gitattributes`, so this digest binds the
committed LF bytes identically on Windows and Linux checkouts. The workflow
checks those bytes before installing the hash-locked, binary-only SDK closure
and again before provider execution.

## Canonical acceptance contract

**C-1 -- Exact one-time NEXUS target recovery.** Recovery is admissible only
when all of the following hold together:

1. canonical `szl-holdings/nexus` source is protected-merged and its exact
   revision is independently readable;
2. dispatch runs from protected `.github/main` with matching workflow,
   checkout, event, and workflow-file commit identities;
3. the exact grant authorizes only public Docker Space `SZLHOLDINGS/nexus`
   while global lifecycle creation remains denied;
4. at most one SDK creation invocation occurs, credential candidates are
   deduplicated, and an ambiguous result is terminal;
5. provider readback proves exact target name, public visibility, Docker SDK,
   and caller write authority without uploading content or mutating another
   target; and
6. a separately reviewed protected successor restores `enabled: false` before
   the central content publisher is dispatched.

Items 1 through 5 are evidenced by the immutable revisions and receipt above.
This candidate implements item 6. Protected merge of this successor closes the
recovery authority; source admission alone is not provider-state proof and Git
reversion cannot delete or otherwise reverse the provider asset.

## Provider effect boundary

Credential candidates are deduplicated. Identity and write checks can move to
the next candidate only after a definite authentication rejection. The first
`create_repo` invocation ends credential selection, including after rejection
or uncertainty. An ambiguous outcome never causes another creation invocation.

The request names only `SZLHOLDINGS/nexus`, selects Space/Docker/public, and
uses `exist_ok=False`. An occupied target is held. Existing private or other-SDK
targets are held. Successful readback requires the exact name, public
visibility, Docker SDK, and write authority. No rename, deletion, visibility
change, content upload, runtime change, or second target is implemented by the
recovery path.

## Effect admission and checks

The recovery workflow's static declaration accounts for its single recovery
artifact, one SDK creation site, two checkouts, two toolchain setups, two local
runner guard configurations, and two StepSecurity telemetry sites. Validation
and recovery jobs are mutually exclusive.

The policy file is a trust root. Changing the reviewed grant hash must retain
the aggregate `TRUST_ROOT_CHANGED_REVIEW_REQUIRED` boundary until protected
source review is complete, even when each individual workflow declaration
remains `ALLOW`.

Focused local commands:

```sh
python -I -B .github/scripts/test_recover_nexus_target.py
python -I -B -O .github/scripts/test_recover_nexus_target.py
actionlint .github/workflows/recover-nexus-target.yml
```

The tests use synthetic provider replies and never contact Hugging Face.
Provider creation and public readback are claimed only from run `37837500766`,
the retained sanitized receipt, and the independent anonymous provider readback
recorded above. Model training, content publication, deployment, runtime health,
DNS, product-site changes, and proof-site changes remain outside this recovery
closure.
