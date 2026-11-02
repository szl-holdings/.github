# Ayllu publisher qualification proposal — NOT ADMITTED

This source proposal extends draft #975 at
`d01c03deaae348bc926f567f475ae33ab8271be3`, based on `.github` main
`d356dcbcc758bda8039dbb86560f96712eaec7fa`. It is **NOT ADMITTED** and
**NOT DEPLOYABLE**. No consumer pin, owner decision, deployment, credential,
access setting or existing A11oy/Seismic publisher is changed.

Ayllu run 41375444857 failed before jobs because its historical reusable pin
could not resolve; the same caller/pin had worked in run 40792286799. This
proposal supplies a separate bounded graph rather than selecting the current
A11oy-only workflow. Neither local binding results nor a passing hosted source
witness constitute authorization to publish.

## Publication contract

The existing caller contract is `.hf-space.json` and
`.github/workflows/hf-space.yml` in `szl-holdings/ayllu` at
`e9a48b261348b0b08e36810ba10aa67952972090`:

- Fixed repository, `hf-space.yml`, main ref, push/dispatch event, exact event
  SHA, and target `SZLHOLDINGS/ayllu`.
- Immutable tools checkout and fixed caller checkout; current-default-tip
  validation remains immediately before the Hub mutation.
- Dockerfile COPY-derived files, README, COPY-directory-scoped pruning,
  ten fixed smoke paths and a 900-second runtime convergence budget.
- `HF_TOKEN` appears only in the publishing job; its admission job is
  credentialless. Repository contents permissions remain read-only.
- The existing `hf-deploy-SZLHOLDINGS/ayllu` publisher lock spans commit and
  running-byte readback. The unchanged caller separately retains its
  `hf-write/space/SZLHOLDINGS/ayllu` lock through receipt verification.
- The evidence artifact remains `hf-deploy-evidence`; manifest SHA, created
  Hub commit, exact RUNNING revision, bytes and smoke probes feed the unchanged
  independent caller receipt. No source variable/file write, restart, Space
  creation, hardware change or alternate target is added.

## Proposed admission boundary

The checker recognizes only the exact Ayllu workflow, witness and validator
hashes. Dependencies comprise the validator, unchanged deployment helper and
hash-locked package closure. Any source drift denies under the existing pins.
The declaration explicitly accounts for these external effect sites:

| Effect | Fixed resource | Maximum sites |
| --- | --- | --- |
| Commit COPY-derived files | `huggingface:space:SZLHOLDINGS/ayllu` | 1 |
| Prune managed COPY directories | `huggingface:space:SZLHOLDINGS/ayllu:copy-derived-files` | 1 |
| Upload deployment evidence | Ayllu `hf-deploy-evidence` artifact | 1 |
| Runner monitoring | `stepsecurity:monitor:szl-holdings/ayllu` | 1 |

The generic deployment helper also contains restart code. The proposed
recognizer excludes it only when both workflow and helper bytes match their
separate exact digests: the two fixed CLI invocations select `deploy` and
`attest`, and neither can select `--restart-space`. Tests execute argument
dispatch with mutation functions mocked and show that changed helper bytes
restore conservative restart accounting and deny. No other publisher receives
this exception. Source-variable tooling is absent from Ayllu's dependency set.

The new push-only witness passes literal `contract-only: true` and a read-only
GitHub token. Only the two tools checkouts and source checks are reachable;
publication requires literal false. Its exact workflow/ref/source identity is
validated before execution. It adds no dispatch surface or live HF credential.

The policy changes are proposed source requiring authentic owner review.
The unchanged trust-root path and protected merge processes remain in force.
No owner acceptance record or synthetic admission receipt is included.
The complete local proposal remains `REVIEW_REQUIRED`: in addition to the
trust-root changes, the existing `hf-space-lifecycle-reconcile.yml` and this
publisher both claim `huggingface:space:SZLHOLDINGS/ayllu`. No resource-conflict
waiver, lifecycle trigger change or new publishing authority is supplied.

## Validation and remaining dependencies

Offline regression suites cover caller/target/ref drift, witness credential
separation, exact helper/lock/validator closure, mutation budgets, scoped prune,
fixed CLI dispatch and unchanged A11oy/Seismic admission. Mock provider results
are synthetic test fixtures, never production evidence.

The new publisher selects Python 3.12.14 with the unchanged 26-package lock,
matching the runtime proposal in open #971 at
`759c067304087d0b59ee52599d14de482c027fd3`. Existing publishers and their tests
retain their current runtime here. The clean hosted runtime proof must be
reconciled with #971 and rerun on the final exact source; local Python 3.12.14
tests do not substitute for a clean runner install.

Actionlint 1.7.12 reports its existing unsupported `job.workflow_sha` and
`job.workflow_repository` context fields. No further findings remain when
those two known version limitations are filtered. The exact-source witness
must establish their actual hosted behavior on the final source.

Before any caller migration: independent source/effect and owner review,
required exact-head CI, clean runtime and source witness, then an admitted
publisher merge. Only a subsequent caller PR may select its real immutable
merged SHA, retaining the caller receipt and lock. No dispatch or provider
publication is authorized by this document.
