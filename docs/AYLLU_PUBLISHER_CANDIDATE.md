# Ayllu publisher candidate — NOT ADMITTED

The Ayllu `hf-space` run 41375444857 failed before creating jobs because GitHub
could not resolve the pinned reusable publisher. The same caller/pin previously
worked in run 40792286799. Restoring resolution alone does not supply publication
admission: historical pin `a9546a72c550a83ed5ae535bdab61ccdfa689e65` has no
publisher declaration in its effect policy. Current canonical publisher versions
are limited to A11oy and are not compatible Ayllu replacements.

This source-only draft adds a separate reusable publisher and offline invocation
tests. It does not change the Ayllu caller, its immutable pin, credentials,
existing A11oy or Seismic publishers, or any effect/admission policy. No automatic
consumer adoption or deployment is enabled. It is **NOT DEPLOYABLE** in this state.

## Derived scope

The caller contract is `.hf-space.json` plus `.github/workflows/hf-space.yml` in
`szl-holdings/ayllu` at `e9a48b261348b0b08e36810ba10aa67952972090`:

- Exact caller `szl-holdings/ayllu`, workflow `hf-space.yml`, main ref, push or
  workflow-dispatch event, exact event SHA, and target `SZLHOLDINGS/ayllu`.
- Unchanged Dockerfile COPY-derived files, README, COPY-scoped pruning, current
  default-tip guard at the mutation boundary, ten smoke paths and 900-second wait.
- Required `HF_TOKEN`, with no provider credential exposed to the invocation job.
  `GITHUB_TOKEN` is read-only for exact source/default-tip verification.
- Same publisher lock `hf-deploy-SZLHOLDINGS/ayllu` as the old generic publisher,
  held through publication and readback; the caller independently retains
  `hf-write/space/SZLHOLDINGS/ayllu`.
- Exact tools checkout, hash-locked publisher dependencies and existing
  manifest/created-commit/running-byte checks. The artifact stays named
  `hf-deploy-evidence`, preserving the existing caller's receipt consumer.
- No Space creation, restart, variable write, hardware change, alternate target
  or weakening of the existing caller's independent post-deploy receipt check.

The workflow structure follows the current dedicated Seismic publisher at
`.github` revision `d356dcbcc758bda8039dbb86560f96712eaec7fa`. Seismic's source
variable/file binding is intentionally not copied: those writes are absent from
the Ayllu caller contract. Ayllu source identity remains bound by exact checkout,
manifest source SHA, exact published commit, byte readback and its caller receipt.

## Admission and runtime work still required

The unchanged effect checker denies the new workflow with
`WORKFLOW_DECLARATION_MISSING`; its script is consequently an
`UNBOUND_EXECUTABLE_CHANGE`. The changed test workflow also needs its exact source
and dependency closure reviewed under its existing declaration.

Raw analysis identifies additional unsupported checkout/action boundaries for
this new fixed caller. A narrow Ayllu recognizer and exact source/effect declaration
must be reviewed before admission. The draft does not add a generic allowlist,
alter default denial, invent an approval record or teach the checker to accept
unknown resources. Relevant unknown classes include
`CHECKOUT_SOURCE_BOUNDARY_UNSUPPORTED`, `ACTION_RESOURCE_OVERRIDE_UNSUPPORTED`
and `ACTION_EXTRA_EFFECT_UNSUPPORTED`.

This draft retains the current publisher's Python 3.12.10 pin. Pending #971
changes publisher qualification to Python 3.12.14; reconcile that change and
rerun its exact clean-runtime closure checks before qualifying this publisher.
Local tests on Python 3.12.14 do not establish the pinned runtime's qualification.

After normal source/effect review, required CI, and an exact-source witness,
merge the admitted publisher first. Only then propose an Ayllu caller update
pinned to the actual merged immutable SHA, preserving its receipt job and lock.
Read-only resolution evidence is required before any owner-authorized publication.

## Current validation

- Eight offline invocation/workflow tests pass, covering correct push/dispatch,
  wrong caller/workflow/target/ref/SHA, missing inputs, changed effects, malformed
  or incomplete smoke paths, credential separation, fixed publication arguments,
  immutable action/runtime pins and artifact compatibility.
- All 124 existing Dockerfile publisher regressions pass against unchanged source.
- YAML parse/structure passes and the new publisher exposes only `workflow_call`.
- The unchanged effect gate returns DENY in an isolated two-commit fixture with
  current policy; this is refusal evidence, not an admission receipt.
- Actionlint was not installed in the local environment; hosted lint is pending.

No remote provider call, live token probe, workflow dispatch or deployment was
performed to validate this draft. Mock provider outputs in the existing test
suite are synthetic and are not live operational evidence.
